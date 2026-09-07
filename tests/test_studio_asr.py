from types import SimpleNamespace
import unittest

from studio_ui import (EXAMPLES, apply_transcription, build_studio,
                       prepare_transcription, select_example)


class StudioAsrTests(unittest.TestCase):
    def test_examples_clear_all_transcripts_and_sources(self):
        for name in EXAMPLES:
            values = select_example(name)
            self.assertEqual(len(values), 32)
            self.assertEqual(list(values[2:7]), [None] * 5)
            self.assertEqual(list(values[7:12]), [""] * 5)
            self.assertEqual(list(values[17:22]), [None] * 5)

    def test_source_change_clears_text_immediately(self):
        text, status, source = prepare_transcription("new.wav")
        self.assertEqual(text, "")
        self.assertEqual(source, "new.wav")
        self.assertIn("正在排队", status)

    def test_old_results_and_manual_corrections_are_not_overwritten(self):
        result = {"source": "old.wav", "text": "自动原文", "status": "完成"}
        self.assertEqual(apply_transcription("new.wav", "", result)[0], {"__type__": "update"})
        self.assertEqual(apply_transcription(None, "", result)[0], {"__type__": "update"})
        self.assertEqual(apply_transcription("old.wav", "手动修正", result)[0], {"__type__": "update"})
        self.assertEqual(apply_transcription("old.wav", "", result), ("自动原文", "完成", "old.wav"))

    def test_real_gradio_build_and_event_wiring(self):
        args = SimpleNamespace(model_path="", codec_path="", device="cuda:1",
            attn_implementation="sdpa", dtype="float16", codec_device="cuda:0")
        demo = build_studio(args, lambda *args: (None, "ok"), lambda count: [], 2000)
        functions = list(demo.fns.values())
        workers = [f for f in functions if f.name == "transcribe_reference"]
        self.assertEqual(len(workers), 5)
        self.assertTrue(all(f.concurrency_id == "speech-generation" for f in workers))
        self.assertEqual(sum(f.name == "select_library_voice" for f in functions), 5)
        self.assertEqual(sum(f.name == "save_library_voice" for f in functions), 5)
        generate = next(f for f in functions if f.name == "generate_with_progress")
        self.assertEqual(len(generate.inputs), 24)
        # Validation protects generation even if the user clicks during ASR.
        inputs = ["new.wav"] + [None] * 4 + [""] * 5 + ["[S1]你好", True, False, 1.1, .9, 50, 1.1, 2000] + ["new.wav"] + [None] * 4
        self.assertIn("等待", generate.fn(1, *inputs)[1])
        inputs[5] = "旧原文"
        inputs[-5] = "old.wav"
        self.assertIn("已经更换", generate.fn(1, *inputs)[1])


if __name__ == "__main__":
    unittest.main()
