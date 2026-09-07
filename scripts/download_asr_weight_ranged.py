"""SHA-256 verified range fallback for the pinned Whisper Turbo weight."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse

from download_models_ranged import get_part, file_sha
from download_asr_model import REPO, REVISION

SIZE = 1617884929
SHA256 = "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "model.bin"
    if target.exists() and file_sha(target) == SHA256:
        print("ASR_WEIGHT_VERIFIED", flush=True)
        raise SystemExit(0)
    parts_dir = args.output / ".weight-parts"
    parts_dir.mkdir(exist_ok=True)
    chunk = 16 * 1024 * 1024
    jobs = [(f"https://huggingface.co/{REPO}/resolve/{REVISION}/model.bin?part={start}",
             parts_dir / f"{start:012d}.part", start, min(start + chunk, SIZE) - 1, SIZE)
            for start in range(0, SIZE, chunk)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, future in enumerate(as_completed([pool.submit(get_part, job) for job in jobs]), 1):
            future.result()
            print(f"ASR weight parts {i}/{len(jobs)}", flush=True)
    temporary = target.with_suffix(".verified-download")
    with temporary.open("wb") as output:
        for _, part, *_ in jobs:
            with part.open("rb") as stream:
                for data in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    output.write(data)
    if temporary.stat().st_size != SIZE or file_sha(temporary) != SHA256:
        raise RuntimeError("ASR weight checksum mismatch; refusing to deploy")
    temporary.replace(target)
    print("ASR_WEIGHT_VERIFIED", flush=True)
