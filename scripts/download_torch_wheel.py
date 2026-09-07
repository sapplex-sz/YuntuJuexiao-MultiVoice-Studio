"""Fetch and verify the V100-compatible Windows CPython 3.11 PyTorch wheel."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
from pathlib import Path

import requests

from download_models_ranged import CHUNK, file_sha, get_part

URL = "https://download-r2.pytorch.org/whl/cu124/torch-2.6.0%2Bcu124-cp311-cp311-win_amd64.whl"
SHA256 = "6a1fb2714e9323f11edb6e8abf7aad5f79e45ad25c081cde87681a18d99c29eb"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("wheelhouse"))
    parser.add_argument("--proxy", default=None)
    args = parser.parse_args()
    if args.proxy:
        os.environ["HTTPS_PROXY"] = args.proxy
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "torch-2.6.0+cu124-cp311-cp311-win_amd64.whl"
    if target.exists() and file_sha(target) == SHA256:
        print("PyTorch wheel already verified", flush=True)
        return
    response = requests.head(URL, timeout=30, allow_redirects=True)
    response.raise_for_status()
    total = int(response.headers["Content-Length"])
    parts_dir = args.output / ".torch-parts"
    parts_dir.mkdir(exist_ok=True)
    jobs = [(URL, parts_dir / f"{start:012d}.part", start, min(start + CHUNK, total) - 1, total)
            for start in range(0, total, CHUNK)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(get_part, job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            future.result()
            print(f"PyTorch wheel: {i}/{len(jobs)} parts", flush=True)
    temp = target.with_suffix(".assembling")
    digest = hashlib.sha256()
    with temp.open("wb") as stream:
        for _, part, _, _, _ in jobs:
            with part.open("rb") as source:
                for data in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    digest.update(data)
                    stream.write(data)
    if digest.hexdigest() != SHA256:
        raise RuntimeError("PyTorch wheel SHA-256 mismatch")
    temp.replace(target)
    for _, part, _, _, _ in jobs:
        part.unlink()
    parts_dir.rmdir()
    print(f"PyTorch wheel SHA-256 verified: {SHA256}", flush=True)


if __name__ == "__main__":
    main()
