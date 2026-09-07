import argparse
import functools
import re
import time
from pathlib import Path
from typing import Optional

import gradio as gr
import numpy as np
import torch
import soundfile as sf
from transformers import AutoModel, AutoProcessor

from runtime_compat import configure_sdpa, resolve_attn_implementation, resolve_dtype

configure_sdpa()

MODEL_PATH = "OpenMOSS-Team/MOSS-TTSD-v1.0"
CODEC_MODEL_PATH = "OpenMOSS-Team/MOSS-Audio-Tokenizer"
DEFAULT_ATTN_IMPLEMENTATION = "auto"
DEFAULT_MAX_NEW_TOKENS = 2000
MIN_SPEAKERS = 1
MAX_SPEAKERS = 5
@functools.lru_cache(maxsize=1)
def load_backend(model_path: str, codec_path: str, device_str: str, attn_implementation: str, dtype_str: str = "auto", codec_device_str: str | None = None):
    device = torch.device(device_str if torch.cuda.is_available() else "cpu")
    dtype = resolve_dtype(device, dtype_str)
    resolved_attn_implementation = resolve_attn_implementation(
        requested=attn_implementation,
        device=device,
        dtype=dtype,
    )

    processor = AutoProcessor.from_pretrained(
        model_path,
        trust_remote_code=True,
        codec_path=codec_path,
    )
    if hasattr(processor, "audio_tokenizer"):
        processor.audio_tokenizer = processor.audio_tokenizer.to(device=codec_device_str or device, dtype=torch.float32)
        processor.audio_tokenizer.eval()

    model_kwargs = {
        "trust_remote_code": True,
        "torch_dtype": dtype,
    }
    if resolved_attn_implementation:
        model_kwargs["attn_implementation"] = resolved_attn_implementation

    model = AutoModel.from_pretrained(model_path, **model_kwargs).to(device)
    model.eval()

    sample_rate = int(getattr(processor.model_config, "sampling_rate", 24000))
    return model, processor, device, sample_rate


def _resample_wav(wav: torch.Tensor, orig_sr: int, target_sr: int) -> torch.Tensor:
    if int(orig_sr) == int(target_sr):
        return wav
    new_num_samples = int(round(wav.shape[-1] * float(target_sr) / float(orig_sr)))
    if new_num_samples <= 0:
        raise ValueError(f"参考音频重采样失败（{orig_sr}Hz → {target_sr}Hz），请换一段音频重试。")
    return torch.nn.functional.interpolate(
        wav.unsqueeze(0),
        size=new_num_samples,
        mode="linear",
        align_corners=False,
    ).squeeze(0)


def _load_audio(audio_path: str) -> tuple[torch.Tensor, int]:
    path = Path(audio_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"找不到参考音频，请重新上传。")

    wav_np, sr = sf.read(path, dtype="float32", always_2d=True)
    if wav_np.size == 0:
        raise ValueError(f"参考音频为空，请上传包含人声的音频。")

    if wav_np.shape[1] > 1:
        wav_np = wav_np.mean(axis=1, keepdims=True)

    wav = torch.from_numpy(wav_np.T)
    return wav, int(sr)


def normalize_text(text: str) -> str:
    text = re.sub(r"\[(\d+)\]", r"[S\1]", text)
    remove_chars = "【】《》（）『』「」" '"-_“”～~‘’'

    segments = re.split(r"(?=\[S\d+\])", text.replace("\n", " "))
    processed_parts = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        matched = re.match(r"^(\[S\d+\])\s*(.*)", seg)
        tag, content = matched.groups() if matched else ("", seg)

        content = re.sub(f"[{re.escape(remove_chars)}]", "", content)
        content = re.sub(r"哈{2,}", "[笑]", content)
        content = re.sub(r"\b(ha(\s*ha)+)\b", "[laugh]", content, flags=re.IGNORECASE)

        content = content.replace("——", "，")
        content = content.replace("……", "，")
        content = content.replace("...", "，")
        content = content.replace("⸺", "，")
        content = content.replace("―", "，")
        content = content.replace("—", "，")
        content = content.replace("…", "，")

        internal_punct_map = str.maketrans(
            {"；": "，", ";": ",", "：": "，", ":": ",", "、": "，"}
        )
        content = content.translate(internal_punct_map)
        content = content.strip()
        content = re.sub(r"([，。？！,.?!])[，。？！,.?!]+", r"\1", content)

        if len(content) > 1:
            last_ch = "。" if content[-1] == "，" else ("." if content[-1] == "," else content[-1])
            body = content[:-1].replace("。", "，")
            content = body + last_ch

        processed_parts.append({"tag": tag, "content": content})

    if not processed_parts:
        return ""

    merged_lines = []
    current_tag = processed_parts[0]["tag"]
    current_content = [processed_parts[0]["content"]]
    for part in processed_parts[1:]:
        if part["tag"] == current_tag and current_tag:
            current_content.append(part["content"])
        else:
            merged_lines.append(f"{current_tag}{''.join(current_content)}".strip())
            current_tag = part["tag"]
            current_content = [part["content"]]
    merged_lines.append(f"{current_tag}{''.join(current_content)}".strip())

    return "".join(merged_lines).replace("‘", "'").replace("’", "'")


def _validate_dialogue_text(dialogue_text: str, speaker_count: int) -> str:
    text = (dialogue_text or "").strip()
    if not text:
        raise ValueError("请先填写要生成的台词。")

    tags = re.findall(r"\[S(\d+)\]", text)
    if not tags:
        raise ValueError("请在台词前添加说话人标记，例如：[S1]你好。")

    if not text.startswith("[S") or any(int(t) < 1 for t in tags):
        raise ValueError("请从 [S1] 开始填写台词，说话人编号应为 1～5。")
    max_tag = max(int(t) for t in tags)
    if max_tag > speaker_count:
        raise ValueError(
            f"台词使用了 [S{max_tag}]，但当前只有 {speaker_count} 位说话人。请增加人数或修改标记。"
        )
    return text


def update_speaker_panels(speaker_count: int):
    count = int(speaker_count)
    count = max(MIN_SPEAKERS, min(MAX_SPEAKERS, count))
    return [gr.update(visible=(idx < count)) for idx in range(MAX_SPEAKERS)]


def _merge_consecutive_speaker_tags(text: str) -> str:
    segments = re.split(r"(?=\[S\d+\])", text)
    if not segments:
        return text

    merged_parts = []
    current_tag = None
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        matched = re.match(r"^(\[S\d+\])\s*(.*)", seg, re.DOTALL)
        if not matched:
            merged_parts.append(seg)
            continue
        tag, content = matched.groups()
        if tag == current_tag:
            merged_parts.append(content)
        else:
            current_tag = tag
            merged_parts.append(f"{tag}{content}")
    return "".join(merged_parts)


def _normalize_prompt_text(prompt_text: str, speaker_id: int) -> str:
    text = (prompt_text or "").strip()
    if not text:
        raise ValueError(f"请填写说话人 {speaker_id} 的参考音频原文。")

    expected_tag = f"[S{speaker_id}]"
    if not text.lstrip().startswith(expected_tag):
        text = f"{expected_tag} {text}"
    return text


def _build_prefixed_text(
    dialogue_text: str,
    prompt_text_map: dict[int, str],
    cloned_speakers: list[int],
) -> str:
    prompt_prefix = "".join([prompt_text_map[speaker_id] for speaker_id in cloned_speakers])
    return _merge_consecutive_speaker_tags(prompt_prefix + dialogue_text)


def _encode_reference_audio_codes(
    processor,
    clone_wavs: list[torch.Tensor],
    cloned_speakers: list[int],
    speaker_count: int,
    sample_rate: int,
) -> list[Optional[torch.Tensor]]:
    encoded_list = processor.encode_audios_from_wav(clone_wavs, sampling_rate=sample_rate)
    reference_audio_codes: list[Optional[torch.Tensor]] = [None for _ in range(speaker_count)]
    for speaker_id, audio_codes in zip(cloned_speakers, encoded_list):
        reference_audio_codes[speaker_id - 1] = audio_codes
    return reference_audio_codes


def build_conversation(
    dialogue_text: str,
    reference_audio_codes: list[Optional[torch.Tensor]],
    prompt_audio: torch.Tensor | None,
    processor,
):
    if prompt_audio is None:
        return [[processor.build_user_message(text=dialogue_text)]], "generation", "Generation"

    user_message = processor.build_user_message(
        text=dialogue_text,
        reference=reference_audio_codes,
    )
    return (
        [
            [
                user_message,
                processor.build_assistant_message(audio_codes_list=[prompt_audio]),
            ],
        ],
        "continuation",
        "voice_clone_and_continuation",
    )


@torch.inference_mode()
def run_inference(speaker_count: int, *all_inputs):
    speaker_count = int(speaker_count)
    speaker_count = max(MIN_SPEAKERS, min(MAX_SPEAKERS, speaker_count))

    reference_audio_values = all_inputs[:MAX_SPEAKERS]
    prompt_text_values = all_inputs[MAX_SPEAKERS : 2 * MAX_SPEAKERS]
    dialogue_text = all_inputs[2 * MAX_SPEAKERS]
    text_normalize, sample_rate_normalize, temperature, top_p, top_k, repetition_penalty, max_new_tokens, model_path, codec_path, device, attn_implementation, dtype_str, codec_device_str = all_inputs[
        2 * MAX_SPEAKERS + 1 :
    ]

    started_at = time.monotonic()
    model, processor, torch_device, sample_rate = load_backend(
        model_path=str(model_path),
        codec_path=str(codec_path),
        device_str=str(device),
        attn_implementation=str(attn_implementation),
        dtype_str=str(dtype_str),
        codec_device_str=codec_device_str,
    )

    text_normalize = bool(text_normalize)
    sample_rate_normalize = bool(sample_rate_normalize)

    normalized_dialogue = str(dialogue_text or "").strip()
    if text_normalize:
        normalized_dialogue = normalize_text(normalized_dialogue)
    normalized_dialogue = _validate_dialogue_text(normalized_dialogue, speaker_count)

    cloned_speakers: list[int] = []
    loaded_clone_wavs: list[tuple[torch.Tensor, int]] = []
    prompt_text_map: dict[int, str] = {}
    for idx in range(speaker_count):
        ref_audio = reference_audio_values[idx]
        prompt_text = str(prompt_text_values[idx] or "").strip()

        has_reference = bool(ref_audio)
        has_prompt_text = bool(prompt_text)
        if has_reference != has_prompt_text:
            raise ValueError(
                f"说话人 {idx + 1} 的参考音频与原文需要一起填写；不使用参考音色时，请同时留空。"
            )

        if has_reference:
            speaker_id = idx + 1
            ref_audio_path = str(ref_audio)
            cloned_speakers.append(speaker_id)
            loaded_clone_wavs.append(_load_audio(ref_audio_path))
            prompt_text_map[speaker_id] = _normalize_prompt_text(prompt_text, speaker_id)

    prompt_audio: Optional[torch.Tensor] = None
    reference_audio_codes: list[Optional[torch.Tensor]] = []
    conversation_text = normalized_dialogue
    if cloned_speakers:
        conversation_text = _build_prefixed_text(
            dialogue_text=normalized_dialogue,
            prompt_text_map=prompt_text_map,
            cloned_speakers=cloned_speakers,
        )
        if text_normalize:
            conversation_text = normalize_text(conversation_text)
        conversation_text = _validate_dialogue_text(conversation_text, speaker_count)

        if sample_rate_normalize:
            min_sr = min(sr for _, sr in loaded_clone_wavs)
        else:
            min_sr = None

        clone_wavs: list[torch.Tensor] = []
        for wav, orig_sr in loaded_clone_wavs:
            processed_wav = wav
            current_sr = int(orig_sr)
            if min_sr is not None:
                processed_wav = _resample_wav(processed_wav, current_sr, int(min_sr))
                current_sr = int(min_sr)
            processed_wav = _resample_wav(processed_wav, current_sr, sample_rate)
            clone_wavs.append(processed_wav)

        reference_audio_codes = _encode_reference_audio_codes(
            processor=processor,
            clone_wavs=clone_wavs,
            cloned_speakers=cloned_speakers,
            speaker_count=speaker_count,
            sample_rate=sample_rate,
        )
        concat_prompt_wav = torch.cat(clone_wavs, dim=-1)
        prompt_audio = processor.encode_audios_from_wav([concat_prompt_wav], sampling_rate=sample_rate)[0]

    conversations, mode, mode_name = build_conversation(
        dialogue_text=conversation_text,
        reference_audio_codes=reference_audio_codes,
        prompt_audio=prompt_audio,
        processor=processor,
    )

    batch = processor(conversations, mode=mode)
    input_ids = batch["input_ids"].to(torch_device)
    attention_mask = batch["attention_mask"].to(torch_device)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=int(max_new_tokens),
            audio_temperature=float(temperature),
            audio_top_p=float(top_p),
            audio_top_k=int(top_k),
            audio_repetition_penalty=float(repetition_penalty),
        )

    messages = processor.decode(outputs)
    if not messages or messages[0] is None:
        raise RuntimeError("模型未返回可播放的音频，请缩短台词后重试。")

    audio = messages[0].audio_codes_list[0]
    if isinstance(audio, torch.Tensor):
        audio_np = audio.detach().float().cpu().numpy()
    else:
        audio_np = np.asarray(audio, dtype=np.float32)

    if audio_np.ndim > 1:
        audio_np = audio_np.reshape(-1)
    audio_np = audio_np.astype(np.float32, copy=False)

    if audio_np.size == 0 or not np.isfinite(audio_np).all():
        raise RuntimeError("生成的音频无效，请重试并检查服务器日志。")

    clone_summary = "自动生成音色" if not cloned_speakers else "、".join([f"说话人 {i}" for i in cloned_speakers])
    elapsed = time.monotonic() - started_at
    duration = audio_np.size / sample_rate
    status = (
        f"生成完成，可以试听或下载。\n"
        f"模式：{'参考音色续说' if cloned_speakers else '文字生成语音'} · {speaker_count} 位说话人\n"
        f"音频时长：{duration:.2f} 秒 · 本次耗时：{elapsed:.2f} 秒\n"
        f"参考音色：{clone_summary} · 采样率：{sample_rate / 1000:g} kHz"
    )
    return (sample_rate, audio_np), status


def generate_for_ui(speaker_count, *inputs):
    """Keep detailed failures in server logs and give the page actionable Chinese text."""
    try:
        return run_inference(speaker_count, *inputs)
    except (ValueError, FileNotFoundError) as exc:
        return None, f"请检查输入：{exc}"
    except torch.cuda.OutOfMemoryError:
        return None, "显存不足。请缩短台词或降低生成长度上限，确认其他任务未占用显卡后重试。"
    except Exception:
        import logging
        logging.exception("Speech generation failed")
        return None, "本次生成未成功。请确认参考音频可正常播放，然后重试；若仍失败，请检查服务器日志。"


def build_demo(args: argparse.Namespace):
    from studio_ui import build_studio
    return build_studio(args, generate_for_ui, update_speaker_panels, DEFAULT_MAX_NEW_TOKENS)


def main() -> None:
    parser = argparse.ArgumentParser(description="云途觉晓多人云音创作平台（基于 MOSS-TTSD）")
    parser.add_argument("--model_path", type=str, default=MODEL_PATH)
    parser.add_argument("--codec_path", type=str, default=CODEC_MODEL_PATH)
    parser.add_argument("--device", type=str, default="cuda:0")
    parser.add_argument("--attn_implementation", type=str, default=DEFAULT_ATTN_IMPLEMENTATION)
    parser.add_argument("--dtype", choices=["auto", "float16", "bfloat16", "float32"], default="auto")
    parser.add_argument("--codec_device", default=None, help="Audio codec device; defaults to the model device.")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7863)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    runtime_device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    runtime_dtype = resolve_dtype(runtime_device, args.dtype)
    args.attn_implementation = resolve_attn_implementation(
        requested=args.attn_implementation,
        device=runtime_device,
        dtype=runtime_dtype,
    ) or "none"
    print(f"[INFO] Using dtype={runtime_dtype}, attn_implementation={args.attn_implementation}, codec_device={args.codec_device or args.device}", flush=True)

    preload_started_at = time.monotonic()
    print(
        f"[Startup] Preloading backend: model={args.model_path}, codec={args.codec_path}, "
        f"device={args.device}, attn={args.attn_implementation}",
        flush=True,
    )
    load_backend(
        model_path=args.model_path,
        codec_path=args.codec_path,
        device_str=args.device,
        attn_implementation=args.attn_implementation,
        dtype_str=args.dtype,
        codec_device_str=args.codec_device,
    )
    print(
        f"[Startup] Backend preload finished in {time.monotonic() - preload_started_at:.2f}s",
        flush=True,
    )

    from studio_ui import CSS, LOCALE_HEAD
    demo = build_demo(args)
    demo.queue(default_concurrency_limit=1, max_size=8).launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        css=CSS,
        head=LOCALE_HEAD,
        footer_links=[],
    )


if __name__ == "__main__":
    main()
