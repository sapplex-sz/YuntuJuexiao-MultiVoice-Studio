import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from reference_asr import run_worker, transcribe_reference, result_is_current, validate_reference_sources


class ReferenceAsrTests(unittest.TestCase):
    def run_worker(self, stdout=None, returncode=0, side_effect=None):
        process = subprocess.CompletedProcess([], returncode, stdout or "{}", "test failure")
        with patch("reference_asr.Path.is_file", return_value=True), patch(
            "reference_asr.run_worker", return_value=process, side_effect=side_effect
        ) as run:
            result = transcribe_reference("voice.wav")
        return result, run

    def test_empty_upload_does_not_start_worker(self):
        with patch("reference_asr.run_worker") as run:
            self.assertEqual(transcribe_reference(None)["text"], "")
            run.assert_not_called()

    def test_success_and_offline_subprocess(self):
        result, run = self.run_worker(json.dumps({"text": "  你好。 ", "language": "zh"}))
        self.assertEqual(result["text"], "你好。")
        self.assertEqual(result["source"], "voice.wav")
        self.assertIn("识别完成", result["status"])
        self.assertEqual(run.call_args.kwargs["env"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(run.call_args.kwargs["timeout"], 180)
        self.assertIsInstance(run.call_args.args[0], list)

    def test_no_speech_and_worker_validation(self):
        result, _ = self.run_worker(json.dumps({"text": " "}))
        self.assertIn("没有识别到", result["status"])
        result, _ = self.run_worker(json.dumps({"error": "没有检测到清晰人声"}))
        self.assertEqual(result["status"], "没有检测到清晰人声")

    def test_timeout_and_crash_are_actionable(self):
        result, _ = self.run_worker(side_effect=subprocess.TimeoutExpired("asr", 180))
        self.assertIn("识别超时", result["status"])
        result, _ = self.run_worker(returncode=1)
        self.assertIn("手动填写", result["status"])
        self.assertEqual(result["text"], "")

    def test_replaced_or_cleared_audio_rejects_old_result(self):
        result = {"source": "A.wav"}
        self.assertFalse(result_is_current("B.wav", result))
        self.assertFalse(result_is_current(None, result))
        self.assertTrue(result_is_current("A.wav", result))

    def test_all_five_speakers_have_independent_sources(self):
        refs = [f"{i}.wav" for i in range(5)]
        self.assertIsNone(validate_reference_sources(refs, ["原文"] * 5, refs, 5))
        sources = refs.copy()
        sources[4] = "old.wav"
        self.assertIn("说话人 5", validate_reference_sources(refs, ["原文"] * 5, sources, 5))
        self.assertIsNone(validate_reference_sources(refs, ["原文"] * 5, sources, 4))

    def test_real_worker_timeout_terminates_process(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            run_worker([sys.executable, "-c", "import time; time.sleep(30)"],
                       env=os.environ.copy(), timeout=0.5)


if __name__ == "__main__":
    unittest.main()
