"""Resumable HTTP range fallback for networks that stall on multi-GB responses.

Only downloads pinned official repositories; every weight shard is SHA-256 checked.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import time

import requests

from download_models import MODELS

CHUNK = 32 * 1024 * 1024
MODELSCOPE_REVISIONS = {
    "MOSS-TTSD-v1.0": "fc51b6e7de189cdaca8977d2bb3db59881275358",
    "MOSS-Audio-Tokenizer": "1b3b842480c8fc415f373642fe78d896edc8a76d",
}


def get_with_retries(url, *, timeout, attempts=30, **kwargs):
    """Retry metadata and small-file requests on unstable model hosts."""
    for attempt in range(attempts):
        try:
            response = requests.get(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if attempt == attempts - 1:
                raise
            print(f"Retry request {url}: {type(exc).__name__}", flush=True)
            time.sleep(min(2 ** attempt, 15))


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def get_part(job):
    url, part, start, end, total = job
    expected = end - start + 1
    if part.exists() and part.stat().st_size == expected:
        return expected
    partial = part.with_suffix(".partial")
    for attempt in range(15):
        try:
            retained = partial.stat().st_size if partial.exists() else 0
            if retained == expected:
                partial.replace(part)
                return expected
            if retained > expected:
                raise RuntimeError(f"Oversized partial file: {partial}")
            next_start = start + retained
            with requests.get(url,
                              headers={"Range": f"bytes={next_start}-{end}", "Accept-Encoding": "identity"},
                              stream=True, timeout=(20, 30)) as response:
                response.raise_for_status()
                content_range = response.headers.get("Content-Range", "")
                if response.status_code != 206 or content_range != f"bytes {next_start}-{end}/{total}":
                    raise RuntimeError(f"Invalid range response: {response.status_code} {content_range}")
                received = retained
                with partial.open("ab") as stream:
                    for data in response.iter_content(1024 * 1024):
                        received += len(data)
                        if received > expected:
                            raise RuntimeError("Range response exceeds requested size")
                        stream.write(data)
                if received != expected:
                    raise RuntimeError(f"Short response: {received}/{expected}")
                partial.replace(part)
                return received
        except (requests.RequestException, RuntimeError) as exc:
            if attempt == 14:
                raise
            print(f"Retry {part.name}: {type(exc).__name__}", flush=True)
            time.sleep(min(2 ** attempt, 10))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--weight-source", choices=["huggingface", "modelscope"], default="huggingface")
    args = parser.parse_args()
    if args.proxy:
        os.environ["HTTPS_PROXY"] = args.proxy
    weights = []
    jobs = []
    for name, (repo, rev) in MODELS.items():
        manifest = Path(__file__).with_name(f"{name}-tree.json")
        using_local_manifest = manifest.exists()
        if using_local_manifest:
            entries = json.loads(manifest.read_text(encoding="utf-8"))
            print(f"Using pinned local manifest: {manifest.name}", flush=True)
        else:
            response = get_with_retries(
                f"https://huggingface.co/api/models/{repo}/tree/{rev}", timeout=(20, 60)
            )
            entries = response.json()
        root = args.root / name
        root.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            filename = entry["path"]
            if entry["type"] != "file" or "/" in filename or filename in {".gitattributes", "README.md"}:
                continue
            target = root / filename
            url = f"https://huggingface.co/{repo}/resolve/{rev}/{filename}"
            if filename.endswith(".safetensors"):
                total = entry["size"]
                sha = entry["lfs"]["oid"]
                if args.weight_source == "modelscope":
                    # These official OpenMOSS mirrors have the identical weight
                    # hashes. Config and Python code still come from pinned HF.
                    url = f"https://modelscope.cn/models/openmoss/{name}/resolve/{MODELSCOPE_REVISIONS[name]}/{filename}"
                if not re.fullmatch(r"[a-f0-9]{64}", sha):
                    raise RuntimeError("Missing official weight hash")
                if target.exists() and target.stat().st_size == total and file_sha(target) == sha:
                    print(f"Already verified: {name}/{filename}", flush=True)
                    continue
                parts_dir = root / ".parts" / filename
                parts_dir.mkdir(parents=True, exist_ok=True)
                parts = []
                for start in range(0, total, CHUNK):
                    part = parts_dir / f"{start:012d}.part"
                    parts.append(part)
                    jobs.append((url, part, start, min(start + CHUNK, total) - 1, total))
                weights.append((target, sha, parts, total))
            else:
                if target.exists():
                    data = target.read_bytes()
                    blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
                    if hashlib.sha1(blob).hexdigest() == entry["oid"]:
                        continue
                    if using_local_manifest and target.stat().st_size == entry["size"]:
                        print(f"Using size-verified existing metadata: {name}/{filename}", flush=True)
                        continue
                content = get_with_retries(url, timeout=(20, 60))
                tmp = target.with_suffix(target.suffix + ".download")
                tmp.write_bytes(content.content)
                tmp.replace(target)
        print(f"Metadata ready: {name}", flush=True)

    started = time.monotonic()
    size_done = 0
    size_all = sum(end - start + 1 for _, _, start, end, _ in jobs)
    cached_size = sum(end - start + 1 for _, part, start, end, _ in jobs
                      if part.exists() and part.stat().st_size == end - start + 1)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(get_part, job) for job in jobs]
        for count, future in enumerate(as_completed(futures), 1):
            size_done += future.result()
            elapsed = time.monotonic() - started
            print(f"{count}/{len(jobs)} parts | {size_done / 1e9:.2f}/{size_all / 1e9:.2f} GB | "
                  f"{max(0, size_done - cached_size) / max(elapsed, 1) / 1e6:.1f} MB/s new data", flush=True)
    for target, sha, parts, total in weights:
        assembled = target.with_suffix(".assembling")
        digest = hashlib.sha256()
        with assembled.open("wb") as output:
            for part in parts:
                with part.open("rb") as source:
                    for data in iter(lambda: source.read(8 * 1024 * 1024), b""):
                        digest.update(data)
                        output.write(data)
        if assembled.stat().st_size != total or digest.hexdigest() != sha:
            raise RuntimeError(f"SHA-256 mismatch: {target}")
        assembled.replace(target)
        print(f"Verified SHA-256: {target.name} {sha}", flush=True)
        for part in parts:
            part.unlink()
        parts[0].parent.rmdir()
    print("All model downloads completed and verified.", flush=True)


if __name__ == "__main__":
    main()
