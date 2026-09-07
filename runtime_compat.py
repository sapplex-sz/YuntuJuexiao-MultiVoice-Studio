"""Hardware-aware inference settings, including Volta / Tesla V100."""
import importlib.util

import torch


def resolve_dtype(device: torch.device, requested: str = "auto") -> torch.dtype:
    if requested == "auto":
        if device.type != "cuda":
            return torch.float32
        # Older cards can emulate BF16 in some PyTorch versions. Require native
        # hardware support instead of accepting the emulation capability probe.
        return torch.bfloat16 if torch.cuda.get_device_capability(device)[0] >= 8 else torch.float16
    choices = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}
    if requested not in choices:
        raise ValueError(f"Unknown dtype: {requested}")
    if requested == "bfloat16" and device.type == "cuda" and torch.cuda.get_device_capability(device)[0] < 8:
        raise ValueError("BF16 requires an Ampere or newer GPU; use float16 on Tesla V100.")
    return choices[requested]


def resolve_attn_implementation(requested: str, device: torch.device, dtype: torch.dtype) -> str | None:
    requested = (requested or "auto").strip().lower()
    flash_supported = (
        device.type == "cuda"
        and torch.cuda.get_device_capability(device)[0] >= 8
        and dtype in {torch.float16, torch.bfloat16}
        and importlib.util.find_spec("flash_attn") is not None
    )
    if requested in {"", "auto"}:
        return "flash_attention_2" if flash_supported else "sdpa"
    if requested == "flash_attention_2" and not flash_supported:
        raise ValueError("FlashAttention 2 requires Ampere+, FP16/BF16 and flash-attn; use sdpa on V100.")
    if requested == "none":
        return None
    if requested not in {"sdpa", "eager", "flash_attention_2"}:
        raise ValueError(f"Unknown attention implementation: {requested}")
    return requested


def configure_sdpa() -> None:
    # cuDNN attention is not usable on Volta. PyTorch dispatches SDPA to a
    # compatible efficient kernel or the math implementation automatically.
    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)
