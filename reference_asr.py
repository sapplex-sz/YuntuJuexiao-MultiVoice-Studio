"""Run local ASR in an isolated, short-lived process; never upload user audio."""
import json
import logging
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
LANGUAGES = {"自动识别": None, "中文": "zh", "英语": "en"}
IDLE_STATUS = "上传音频后自动识别原文；也可以手动填写。"


def run_worker(command, *, env, timeout):
    # Windows venv python.exe is a launcher with a child interpreter. Killing
    # only that launcher on timeout would leave the CUDA worker running.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace", env=env,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                taskkill = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe")
                subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            process.kill()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def transcribe_reference(audio_path, language="自动识别"):
    """Return the source path with results so the UI can reject stale responses."""
    result = {"source": audio_path, "text": "", "status": IDLE_STATUS}
    if not audio_path:
        return result
    started = time.monotonic()
    try:
        if language not in LANGUAGES:
            raise ValueError("请选择自动识别、中文或英语。")
        if not Path(audio_path).is_file():
            raise ValueError("参考音频已失效，请重新上传。")
        python = Path(os.environ.get("MOSS_ASR_PYTHON", str(
            ROOT / ".venv-asr" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))))
        model = Path(os.environ.get("MOSS_ASR_MODEL", str(ROOT.parent / "models" / "faster-whisper-large-v3-turbo")))
        if not python.is_file() or not (model / "model.bin").is_file():
            raise ValueError("自动识别环境尚未准备好，请先手动填写原文。")
        env = os.environ.copy()
        env.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
        command = [str(python), str(ROOT / "scripts/asr_worker.py"), "--audio", str(audio_path),
                   "--model", str(model), "--language", LANGUAGES[language] or "auto",
                   "--device", env.get("MOSS_ASR_DEVICE", "cuda"),
                   "--device-index", env.get("MOSS_ASR_DEVICE_INDEX", "0")]
        completed = run_worker(command, timeout=180, env=env)
        if completed.returncode:
            logging.error("[ASR] Worker failed: %s", completed.stderr[-2000:])
            raise RuntimeError("识别服务暂时不可用，请重试或手动填写原文。")
        payload = json.loads(completed.stdout)
        if payload.get("error"):
            raise ValueError(payload["error"])
        text = payload["text"].strip()
        if not text:
            raise ValueError("没有识别到清晰人声，请换一段音频，或手动填写原文。")
        result.update(text=text, status=f"识别完成，用时 {time.monotonic() - started:.1f} 秒。请核对人名、数字和漏字；原文可直接修改。")
        logging.info("[ASR] Completed in %.1fs, language=%s", time.monotonic() - started, payload.get("language"))
    except subprocess.TimeoutExpired:
        result["status"] = "识别超时，已结束本次识别。请使用更短的音频，或手动填写原文。"
    except (ValueError, RuntimeError) as exc:
        result["status"] = str(exc)
    except Exception:
        logging.exception("[ASR] Unexpected transcription error")
        result["status"] = "自动识别失败，请重新识别或手动填写原文。"
    return result


def result_is_current(audio_path, result):
    return bool(result) and result.get("source") == audio_path


def validate_reference_sources(refs, prompts, sources, count):
    for idx in range(int(count)):
        if refs[idx] and prompts[idx] and refs[idx] != sources[idx]:
            return f"说话人 {idx + 1} 的音频已经更换，请等待识别完成，或重新填写与当前音频一致的原文。"
    return None
