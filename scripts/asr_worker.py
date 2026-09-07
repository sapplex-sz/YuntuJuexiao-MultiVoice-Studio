"""Isolated Whisper worker. Exiting releases all CUDA memory after each request."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--device-index", type=int, default=0)
    args = parser.parse_args()
    # Reuse the tested CUDA 12 / cuDNN 9 DLLs without importing Torch or
    # installing a second CUDA runtime into the speech generation environment.
    dll_handle = None
    if os.name == "nt":
        dll_dir = Path(__file__).resolve().parents[1] / ".venv/Lib/site-packages/torch/lib"
        if dll_dir.is_dir():
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
            dll_handle = os.add_dll_directory(str(dll_dir))
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    from opencc import OpenCC
    import numpy as np

    # The web component already decodes uploads. Decode again here to validate
    # duration; never silently truncate a reference and misalign its transcript.
    try:
        audio = decode_audio(args.audio, sampling_rate=16000)
    except Exception:
        return {"error": "无法读取这段音频，请重新上传有效的音频文件。"}
    duration = len(audio) / 16000
    if duration < 0.5:
        return {"error": "参考音频太短，请使用至少半秒的清晰人声。"}
    if duration > 120:
        return {"error": "自动识别限 2 分钟内的参考音频。建议截取 5～30 秒的单人人声，或手动填写原文。"}
    if not np.isfinite(audio).all() or not np.any(audio):
        return {"error": "音频为空或没有有效声音，请重新上传。"}
    if not get_speech_timestamps(audio, VadOptions(min_speech_duration_ms=250)):
        return {"error": "没有检测到清晰人声，请换一段音频，或手动填写原文。"}
    model = WhisperModel(args.model, device=args.device, device_index=args.device_index,
                         compute_type="float16" if args.device == "cuda" else "int8",
                         cpu_threads=8, num_workers=1, local_files_only=True)
    segments, info = model.transcribe(audio, language=None if args.language == "auto" else args.language,
                                     task="transcribe", beam_size=5, vad_filter=True,
                                     condition_on_previous_text=False)
    text = "".join(segment.text for segment in segments).strip()
    if info.language == "zh":
        text = OpenCC("t2s").convert(text)
    return {"text": text, "language": info.language, "duration": duration}


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False), flush=True)
