"""Download the reviewed model revisions without modifying their source code."""
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")

from huggingface_hub import snapshot_download

MODELS = {
    "MOSS-TTSD-v1.0": ("OpenMOSS-Team/MOSS-TTSD-v1.0", "c7cd852d87aff71cab5bd2b9b05509cedc0ef1ba"),
    "MOSS-Audio-Tokenizer": ("OpenMOSS-Team/MOSS-Audio-Tokenizer", "3cd226ba2947efa357ef453bcad111b6eafba782"),
}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    for name, (repo, revision) in MODELS.items():
        print(f"Downloading {repo} @ {revision}", flush=True)
        snapshot_download(repo, revision=revision, local_dir=args.root / name, max_workers=4,
                          ignore_patterns=["images/*", "*.md", ".gitattributes"])
    print("All model downloads completed.", flush=True)
