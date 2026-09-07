"""Exercise real, offline ASR without loading another TTS model."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--module-root", type=Path, default=ROOT)
parser.add_argument("--audio", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.module_root))
import reference_asr
reference_asr.ROOT = ROOT

result = reference_asr.transcribe_reference(str(args.audio), "中文")
print(json.dumps(result, ensure_ascii=False), flush=True)
assert result["text"] and "识别完成" in result["status"], result
with tempfile.TemporaryDirectory(prefix="moss-asr-test-") as folder:
    for name, samples, expected in [("silent.wav", 16000, "没有有效声音"),
                                    ("short.wav", 1600, "太短"),
                                    ("long.wav", 121 * 16000, "2 分钟")]:
        path = Path(folder) / name
        sf.write(path, np.zeros(samples, dtype=np.float32), 16000)
        result = reference_asr.transcribe_reference(str(path))
        print(name, result["status"], flush=True)
        assert not result["text"] and expected in result["status"], result
print("ASR_SMOKE_PASSED", flush=True)
