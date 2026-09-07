"""Install a compact, attributed 30-speaker AISHELL-3 reference library."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from voice_library import VoiceLibrary  # noqa: E402


HF_ROOT = "https://huggingface.co/datasets/AISHELL/AISHELL-3"
CONTENT_URL = f"{HF_ROOT}/resolve/main/test/content.txt"
API_TREE = "https://huggingface.co/api/datasets/AISHELL/AISHELL-3/tree/main/test/wav"
TARGET_SECONDS = 6.0

# All IDs and demographic labels come from AISHELL-3 spk-info.txt. Names describe
# only documented metadata; they intentionally avoid subjective claims such as
# “sweet” or “magnetic”.
BUILTIN_SPEAKERS = [
    ("SSB0273", "青年男声·北方 01", "B", "男", "北方"),
    ("SSB0241", "青年男声·北方 02", "B", "男", "北方"),
    ("SSB0073", "青年男声·北方 03", "B", "男", "北方"),
    ("SSB0316", "青年男声·北方 04", "B", "男", "北方"),
    ("SSB0394", "青年男声·北方 05", "B", "男", "北方"),
    ("SSB0631", "青年男声·南方 01", "B", "男", "南方"),
    ("SSB0375", "青年男声·南方 02", "B", "男", "南方"),
    ("SSB0139", "青年男声·南方 03", "B", "男", "南方"),
    ("SSB0623", "青年男声·南方 04", "B", "男", "南方"),
    ("SSB0710", "成熟男声·北方 01", "C", "男", "北方"),
    ("SSB0261", "成熟男声·北方 02", "C", "男", "北方"),
    ("SSB0407", "成熟男声·北方 03", "C", "男", "北方"),
    ("SSB0590", "成熟男声·北方 04", "C", "男", "北方"),
    ("SSB0609", "成熟男声·北方 05", "C", "男", "北方"),
    ("SSB0434", "长者男声·北方 01", "D", "男", "北方"),
    ("SSB0578", "青年女声·北方 01", "B", "女", "北方"),
    ("SSB0016", "青年女声·北方 02", "B", "女", "北方"),
    ("SSB0588", "青年女声·北方 03", "B", "女", "北方"),
    ("SSB0366", "青年女声·南方 01", "B", "女", "南方"),
    ("SSB0632", "青年女声·南方 02", "B", "女", "南方"),
    ("SSB0009", "青年女声·南方 03", "B", "女", "南方"),
    ("SSB0342", "青年女声·其他口音 01", "B", "女", "其他"),
    ("SSB0534", "成熟女声·北方 01", "C", "女", "北方"),
    ("SSB0666", "成熟女声·北方 02", "C", "女", "北方"),
    ("SSB0599", "成熟女声·北方 03", "C", "女", "北方"),
    ("SSB0341", "成熟女声·北方 04", "C", "女", "北方"),
    ("SSB0197", "成熟女声·南方 01", "C", "女", "南方"),
    ("SSB0737", "长者女声·北方 01", "D", "女", "北方"),
    ("SSB0309", "长者女声·北方 02", "D", "女", "北方"),
    ("SSB0606", "长者女声·北方 03", "D", "女", "北方"),
]


def fetch(url: str, *, attempts: int = 4) -> bytes:
    curl = "curl.exe" if os.name == "nt" else shutil.which("curl")
    if curl:
        completed = subprocess.run(
            [curl, "-L", "--fail", "--retry", "5", "--retry-all-errors", "--retry-delay", "1",
             "--connect-timeout", "15", "--max-time", "90", "-sS", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0:
            return completed.stdout
        message = completed.stderr.decode("utf-8", errors="replace")[-500:].strip()
        raise RuntimeError(f"下载失败：{url}（curl：{message}）")
    last_error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "YuntuJuexiao-VoiceLibrary/1.0"})
            with urlopen(request, timeout=45) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"下载失败：{url}（{last_error}）")


def parse_transcripts(raw: bytes) -> dict[str, str]:
    transcripts = {}
    for line in raw.decode("utf-8-sig").splitlines():
        if "\t" not in line:
            continue
        filename, annotated = line.split("\t", 1)
        tokens = annotated.split()
        text_tokens = [token for token in tokens if not re.fullmatch(r"[a-züv]+[0-5]", token, re.IGNORECASE)]
        transcripts[filename] = "".join(text_tokens)
    return transcripts


def speaker_files(speaker_id: str) -> list[str]:
    payload = json.loads(fetch(f"{API_TREE}/{quote(speaker_id)}?recursive=false&expand=false"))
    return sorted(item["path"].split("/")[-1] for item in payload if item.get("type") == "file")


def build_reference(speaker_id: str, transcripts: dict[str, str], output: Path) -> tuple[str, float]:
    chunks, texts, sample_rate = [], [], None
    duration = 0.0
    for filename in speaker_files(speaker_id):
        transcript = transcripts.get(filename)
        if not transcript:
            continue
        url = f"{HF_ROOT}/resolve/main/test/wav/{speaker_id}/{filename}?download=true"
        audio, rate = sf.read(io.BytesIO(fetch(url)), dtype="float32", always_2d=True)
        mono = np.mean(audio, axis=1, dtype=np.float32)
        if sample_rate is None:
            sample_rate = int(rate)
        if int(rate) != sample_rate:
            continue
        chunks.append(mono)
        texts.append(transcript)
        duration += len(mono) / sample_rate
        if duration >= TARGET_SECONDS:
            break
        chunks.append(np.zeros(int(sample_rate * 0.12), dtype=np.float32))
    if not chunks or sample_rate is None:
        raise RuntimeError(f"{speaker_id} 没有可用的音频与原文。")
    combined = np.concatenate(chunks)
    sf.write(output, combined, sample_rate, subtype="PCM_16")
    return "。".join(text.rstrip("。！？；") for text in texts) + "。", len(combined) / sample_rate


def main() -> None:
    parser = argparse.ArgumentParser(description="安装 30 个 AISHELL-3 中文参考音色")
    parser.add_argument("--library-root", default=None)
    parser.add_argument("--count", type=int, default=len(BUILTIN_SPEAKERS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    count = max(1, min(len(BUILTIN_SPEAKERS), args.count))
    library = VoiceLibrary(args.library_root)
    transcripts = parse_transcripts(fetch(CONTENT_URL))
    installed_ids = set()
    selected = list(enumerate(BUILTIN_SPEAKERS[:count], 1))
    with tempfile.TemporaryDirectory(prefix="yuntu-voices-") as directory:
        temporary_root = Path(directory)
        remaining = selected
        for round_number in range(1, 5):
            retry = []
            for index, (speaker_id, name, age, gender, accent) in remaining:
                voice_id = f"aishell3-{speaker_id.lower()}"
                if not args.force:
                    try:
                        if library.get(voice_id):
                            print(f"[{index}/{count}] 已存在：{name}", flush=True)
                            installed_ids.add(voice_id)
                            continue
                    except ValueError:
                        pass
                output = temporary_root / f"{voice_id}.wav"
                try:
                    prompt_text, duration = build_reference(speaker_id, transcripts, output)
                    library.install_builtin_voice(
                        voice_id=voice_id,
                        name=name,
                        audio_path=output,
                        prompt_text=prompt_text,
                        speaker_id=speaker_id,
                        age_group=age,
                        gender=gender,
                        accent=accent,
                        force=args.force,
                    )
                    installed_ids.add(voice_id)
                    print(f"[{index}/{count}] 已安装：{name}（{duration:.1f} 秒）", flush=True)
                except Exception as exc:
                    print(f"[{index}/{count}] 暂未完成：{name}（第 {round_number} 轮：{exc}）", flush=True)
                    retry.append((index, (speaker_id, name, age, gender, accent)))
            remaining = retry
            if not remaining:
                break
            print(f"还有 {len(remaining)} 个音色待重试，稍后开始第 {round_number + 1} 轮。", flush=True)
            time.sleep(3 * round_number)
    if remaining:
        names = "、".join(item[1][1] for item in remaining)
        raise RuntimeError(f"仍有 {len(remaining)} 个音色下载失败，可稍后重新运行安装器：{names}")
    print(f"完成：音色库共有 {len(library.list_voices())} 个可用音色，本次确认 {len(installed_ids)} 个。", flush=True)


if __name__ == "__main__":
    main()
