"""Download pinned, data-only Whisper Turbo weights for offline transcription."""
import argparse
import os

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")

from huggingface_hub import snapshot_download

REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(f"Downloading {REPO} @ {REVISION}", flush=True)
    snapshot_download(REPO, revision=REVISION, local_dir=args.output,
                      allow_patterns=["config.json", "preprocessor_config.json", "model.bin",
                                      "tokenizer.json", "vocabulary.json"], max_workers=3)
    print("ASR_MODEL_READY", flush=True)
