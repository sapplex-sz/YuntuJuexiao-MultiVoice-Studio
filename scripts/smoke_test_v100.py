"""Real end-to-end tests for generation, reference encoding and continuation."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import soundfile as sf
import torch

from gradio_demo import load_backend, run_inference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--codec_path", required=True)
    parser.add_argument("--device", default="cuda:1")
    parser.add_argument("--codec_device", default="cuda:1")
    parser.add_argument("--output", type=Path, default=Path("output/verification"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(42)
    started = time.monotonic()
    model, processor, device, sample_rate = load_backend(
        model_path=args.model_path, codec_path=args.codec_path, device_str=args.device,
        attn_implementation="sdpa", dtype_str="auto", codec_device_str=args.codec_device,
    )
    print(f"Loaded in {time.monotonic() - started:.1f}s; model dtype={next(model.parameters()).dtype}; "
          f"codec dtype={next(processor.audio_tokenizer.parameters()).dtype}; "
          f"attention={model.language_model.config._attn_implementation}", flush=True)
    assert next(model.parameters()).dtype == torch.float16
    assert next(processor.audio_tokenizer.parameters()).dtype == torch.float32
    assert model.language_model.config._attn_implementation == "sdpa"
    results = []
    cases = [
        ("chinese_single", 1, [None] * 5, [""] * 5,
         "[S1]你好，欢迎来到我们的语音工作室。今天我们来测试中文语音生成。"),
        ("chinese_dialogue", 2, [None] * 5, [""] * 5,
         "[S1]你好，欢迎来到我们的语音工作室。[S2]你好，今天我们来测试中文对话生成。"),
        ("voice_continuation", 1, [str(args.output / "chinese_single.wav")] + [None] * 4,
         ["[S1]你好，欢迎来到我们的语音工作室。今天我们来测试中文语音生成。"] + [""] * 4,
         "[S1]现在，让我们继续测试。希望你今天过得愉快。"),
    ]
    for name, count, refs, prompts, text in cases:
        for index in range(torch.cuda.device_count()):
            torch.cuda.reset_peak_memory_stats(index)
        result, status = run_inference(
            count, *refs, *prompts, text, True, False, 1.1, 0.9, 50, 1.1, 512,
            args.model_path, args.codec_path, args.device, "sdpa", "auto", args.codec_device,
        )
        assert load_backend.cache_info().misses == 1, "Unexpected duplicate model load"
        sr, audio = result
        assert np.isfinite(audio).all() and audio.size > sr
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        assert rms > 1e-5, f"Silent output: rms={rms}"
        sf.write(args.output / f"{name}.wav", audio, sr)
        record = {"name": name, "status": status, "duration_seconds": len(audio) / sr,
                  "sample_rate": sr, "rms": rms, "peak": float(np.max(np.abs(audio))),
                  "peak_memory_gib": {str(i): torch.cuda.max_memory_allocated(i) / 1024**3
                                      for i in range(torch.cuda.device_count())}}
        print(json.dumps(record, ensure_ascii=False), flush=True)
        results.append(record)
        (args.output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SMOKE TEST PASSED", flush=True)


if __name__ == "__main__":
    main()
