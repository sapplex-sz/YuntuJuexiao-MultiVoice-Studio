"""Verify generated speech locally before making it downloadable."""
import json
import os
from pathlib import Path
import tempfile

import soundfile as sf

from reference_asr import ROOT, run_worker
from speech_guard import script_endpoint


def verify_generated_speech(audio, sample_rate, text):
    python = Path(os.environ.get("MOSS_ASR_PYTHON", str(
        ROOT / ".venv-asr" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))))
    model = Path(os.environ.get("MOSS_ASR_MODEL", str(ROOT.parent / "models" / "faster-whisper-large-v3-turbo")))
    if not python.is_file() or not (model / "model.bin").is_file():
        raise ValueError("成品核对环境不可用，请管理员检查本地语音识别服务。")
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    with tempfile.TemporaryDirectory(prefix="yuntu-verify-") as folder:
        path = Path(folder) / "speech.wav"
        sf.write(path, audio, sample_rate)
        command = [str(python), str(ROOT / "scripts/asr_worker.py"), "--audio", str(path),
                   "--model", str(model), "--timestamps", "--device", env.get("MOSS_ASR_DEVICE", "cuda"),
                   "--device-index", env.get("MOSS_ASR_DEVICE_INDEX", "0")]
        completed = run_worker(command, timeout=180, env=env)
        if completed.returncode:
            raise ValueError("成品核对暂时失败，本次未发布音频，请重试。")
        payload = json.loads(completed.stdout)
        endpoint = script_endpoint(text, payload.get("words", []))
        if not endpoint["ok"]:
            raise ValueError("本次声音与台词未通过完整性核对，已拦截异常成品。请重新生成；若多次失败，请换一个音色或缩短台词。")
        # Preserve a small release after the last word, not an entire ASR segment.
        end_sample = min(len(audio), round(endpoint["cut_at"] * sample_rate))
        trimmed = (len(audio) - end_sample) / sample_rate
        return audio[:end_sample], trimmed, endpoint["score"]
