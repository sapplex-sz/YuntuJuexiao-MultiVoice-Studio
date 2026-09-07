"""Persistent reference-voice library used by the Gradio studio."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

import numpy as np
import soundfile as sf


CATALOG_VERSION = 1
MIN_DURATION_SECONDS = 0.5
MAX_DURATION_SECONDS = 120.0
_LOCK = threading.RLock()


class VoiceLibraryError(ValueError):
    """A user-facing voice-library validation error."""


def default_library_root() -> Path:
    configured = os.environ.get("YUNTU_VOICE_LIBRARY_DIR")
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parent / "voice_library_data"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_text(value: str, *, field: str, maximum: int) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise VoiceLibraryError(f"请填写{field}。")
    if len(value) > maximum:
        raise VoiceLibraryError(f"{field}不能超过 {maximum} 个字符。")
    return value


class VoiceLibrary:
    """JSON catalog plus normalized WAV files, safe across app restarts."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or default_library_root()).expanduser().resolve()
        self.audio_dir = self.root / "audio"
        self.catalog_path = self.root / "library.json"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _read_catalog_unlocked(self) -> dict:
        if not self.catalog_path.exists():
            return {"version": CATALOG_VERSION, "voices": []}
        try:
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VoiceLibraryError("音色库索引无法读取，请管理员检查 library.json。") from exc
        if data.get("version") != CATALOG_VERSION or not isinstance(data.get("voices"), list):
            raise VoiceLibraryError("音色库索引版本不受支持，请管理员升级或修复。")
        return data

    def _write_catalog_unlocked(self, data: dict) -> None:
        temporary = self.catalog_path.with_name(f".{self.catalog_path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.catalog_path)

    def _audio_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise VoiceLibraryError("音色库包含不安全的音频路径。")
        resolved = (self.root / relative).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise VoiceLibraryError("音色库包含不安全的音频路径。") from exc
        return resolved

    def _store_audio(self, source_path: str | Path, target_name: str) -> tuple[str, float, int, str]:
        source = Path(source_path).expanduser()
        if not source.is_file():
            raise VoiceLibraryError("参考音频已经失效，请重新上传。")
        try:
            samples, sample_rate = sf.read(source, dtype="float32", always_2d=True)
        except Exception as exc:
            raise VoiceLibraryError("无法读取参考音频，请换用 WAV、MP3 或 FLAC 文件。") from exc
        if samples.size == 0 or sample_rate <= 0:
            raise VoiceLibraryError("参考音频为空。")
        duration = len(samples) / float(sample_rate)
        if not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
            raise VoiceLibraryError("参考音频时长需要在 0.5～120 秒之间。")
        mono = np.mean(samples, axis=1, dtype=np.float32)
        target = self.audio_dir / target_name
        temporary = self.audio_dir / f".{target.stem}.{uuid.uuid4().hex}.tmp.wav"
        try:
            sf.write(temporary, mono, sample_rate, subtype="PCM_16")
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target.relative_to(self.root).as_posix(), duration, int(sample_rate), digest

    def list_voices(self) -> list[dict]:
        with _LOCK:
            voices = []
            for raw in self._read_catalog_unlocked()["voices"]:
                if not isinstance(raw, dict) or not raw.get("id") or not raw.get("audio_file"):
                    continue
                path = self._audio_path(raw["audio_file"])
                if not path.is_file():
                    continue
                item = dict(raw)
                item["audio_path"] = str(path)
                voices.append(item)
        return sorted(voices, key=lambda item: (not bool(item.get("builtin")), item.get("name", "")))

    def choices(self) -> list[tuple[str, str]]:
        choices = [("不使用音色库", "")]
        for voice in self.list_voices():
            prefix = "内置" if voice.get("builtin") else "我的"
            choices.append((f"{prefix}｜{voice['name']}", voice["id"]))
        return choices

    def get(self, voice_id: str) -> dict | None:
        if not voice_id:
            return None
        for voice in self.list_voices():
            if voice["id"] == voice_id:
                return voice
        raise VoiceLibraryError("所选音色不存在或音频文件已经丢失，请刷新音色库。")

    def _upsert(self, entry: dict) -> dict:
        with _LOCK:
            catalog = self._read_catalog_unlocked()
            catalog["voices"] = [voice for voice in catalog["voices"] if voice.get("id") != entry["id"]]
            catalog["voices"].append(entry)
            self._write_catalog_unlocked(catalog)
        result = dict(entry)
        result["audio_path"] = str(self._audio_path(entry["audio_file"]))
        return result

    def save_user_voice(
        self,
        audio_path: str,
        prompt_text: str,
        name: str,
        language: str = "自动识别",
        *,
        rights_confirmed: bool = False,
    ) -> dict:
        if not rights_confirmed:
            raise VoiceLibraryError("保存前请确认你拥有该声音的使用授权。")
        if not audio_path:
            raise VoiceLibraryError("请先上传或选择参考音频。")
        name = _clean_text(name, field="音色名称", maximum=40)
        prompt_text = _clean_text(prompt_text, field="参考音频原文", maximum=2000)
        with _LOCK:
            if any(voice.get("name", "").casefold() == name.casefold()
                   for voice in self._read_catalog_unlocked()["voices"]):
                raise VoiceLibraryError("这个音色名称已经存在，请换一个名称。")
        voice_id = f"user-{uuid.uuid4().hex}"
        audio_file, duration, sample_rate, digest = self._store_audio(audio_path, f"{voice_id}.wav")
        return self._upsert({
            "id": voice_id,
            "name": name,
            "prompt_text": prompt_text,
            "language": language or "自动识别",
            "builtin": False,
            "source": "用户保存的授权参考音频",
            "license": "由保存者确认授权范围",
            "audio_file": audio_file,
            "duration_seconds": round(duration, 3),
            "sample_rate": sample_rate,
            "sha256": digest,
            "created_at": _utc_now(),
            "rights_confirmed_at": _utc_now(),
        })

    def install_builtin_voice(
        self,
        *,
        voice_id: str,
        name: str,
        audio_path: str | Path,
        prompt_text: str,
        speaker_id: str,
        age_group: str,
        gender: str,
        accent: str,
        force: bool = False,
    ) -> dict:
        voice_id = _clean_text(voice_id, field="音色编号", maximum=80)
        if not re.fullmatch(r"[a-z0-9-]+", voice_id):
            raise VoiceLibraryError("内置音色编号格式不正确。")
        existing = None
        try:
            existing = self.get(voice_id)
        except VoiceLibraryError:
            pass
        if existing and not force:
            return existing
        name = _clean_text(name, field="音色名称", maximum=40)
        prompt_text = _clean_text(prompt_text, field="参考音频原文", maximum=2000)
        audio_file, duration, sample_rate, digest = self._store_audio(audio_path, f"{voice_id}.wav")
        return self._upsert({
            "id": voice_id,
            "name": name,
            "prompt_text": prompt_text,
            "language": "中文",
            "builtin": True,
            "source": f"AISHELL-3 / {speaker_id}",
            "source_url": "https://www.openslr.org/93/",
            "license": "Apache-2.0",
            "speaker_id": speaker_id,
            "age_group": age_group,
            "gender": gender,
            "accent": accent,
            "audio_file": audio_file,
            "duration_seconds": round(duration, 3),
            "sample_rate": sample_rate,
            "sha256": digest,
            "created_at": _utc_now(),
        })


def describe_voice(voice: dict) -> str:
    origin = voice.get("source", "来源未记录")
    license_name = voice.get("license", "授权信息未记录")
    duration = voice.get("duration_seconds", 0)
    return f"已选择“{voice['name']}” · {origin} · {duration:g} 秒 · {license_name}"
