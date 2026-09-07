import unittest
from unittest.mock import patch

import torch

from runtime_compat import resolve_attn_implementation, resolve_dtype


class RuntimeCompatibilityTests(unittest.TestCase):
    def test_v100_uses_fp16_and_sdpa_even_with_flash_installed(self):
        with patch("torch.cuda.get_device_capability", return_value=(7, 0)), patch("importlib.util.find_spec", return_value=object()):
            device = torch.device("cuda:1")
            self.assertEqual(resolve_dtype(device), torch.float16)
            self.assertEqual(resolve_attn_implementation("auto", device, torch.float16), "sdpa")
            with self.assertRaises(ValueError):
                resolve_dtype(device, "bfloat16")
            with self.assertRaises(ValueError):
                resolve_attn_implementation("flash_attention_2", device, torch.float16)

    def test_ampere_retains_bf16_and_optional_flash(self):
        with patch("torch.cuda.get_device_capability", return_value=(8, 0)), patch("importlib.util.find_spec", return_value=object()):
            device = torch.device("cuda:0")
            self.assertEqual(resolve_dtype(device), torch.bfloat16)
            self.assertEqual(resolve_attn_implementation("auto", device, torch.bfloat16), "flash_attention_2")
        with patch("torch.cuda.get_device_capability", return_value=(8, 0)), patch("importlib.util.find_spec", return_value=None):
            self.assertEqual(resolve_attn_implementation("auto", device, torch.bfloat16), "sdpa")

    def test_cpu_needs_no_cuda_probe(self):
        with patch("torch.cuda.get_device_capability", side_effect=AssertionError("unexpected CUDA probe")):
            device = torch.device("cpu")
            self.assertEqual(resolve_dtype(device), torch.float32)
            self.assertEqual(resolve_attn_implementation("auto", device, torch.float32), "sdpa")


if __name__ == "__main__":
    unittest.main()
