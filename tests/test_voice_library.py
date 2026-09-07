import tempfile
from pathlib import Path
import unittest
import wave

from voice_library import VoiceLibrary, VoiceLibraryError, describe_voice


def write_silence(path: Path, seconds: float = 1.0, sample_rate: int = 16000):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\0\0" * int(seconds * sample_rate))


class VoiceLibraryTests(unittest.TestCase):
    def test_user_voice_survives_new_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            write_silence(source)
            root = Path(directory) / "library"
            saved = VoiceLibrary(root).save_user_voice(
                str(source), "这是参考原文。", "我的主持人", "中文", rights_confirmed=True
            )
            reloaded = VoiceLibrary(root).get(saved["id"])
            self.assertEqual(reloaded["name"], "我的主持人")
            self.assertTrue(Path(reloaded["audio_path"]).is_file())
            self.assertIn(("我的｜我的主持人", saved["id"]), VoiceLibrary(root).choices())

    def test_requires_rights_name_transcript_and_unique_name(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            write_silence(source)
            library = VoiceLibrary(Path(directory) / "library")
            with self.assertRaisesRegex(VoiceLibraryError, "授权"):
                library.save_user_voice(str(source), "原文", "名字")
            with self.assertRaisesRegex(VoiceLibraryError, "名称"):
                library.save_user_voice(str(source), "原文", "", rights_confirmed=True)
            library.save_user_voice(str(source), "原文", "名字", rights_confirmed=True)
            with self.assertRaisesRegex(VoiceLibraryError, "已经存在"):
                library.save_user_voice(str(source), "另一段", "名字", rights_confirmed=True)

    def test_builtin_is_idempotent_and_attributed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            write_silence(source)
            library = VoiceLibrary(Path(directory) / "library")
            values = dict(voice_id="aishell3-ssb0005", name="青年女声·北方 01",
                          audio_path=source, prompt_text="测试原文。", speaker_id="SSB0005",
                          age_group="B", gender="女", accent="北方")
            first = library.install_builtin_voice(**values)
            second = library.install_builtin_voice(**values)
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(len(library.list_voices()), 1)
            self.assertIn("Apache-2.0", describe_voice(first))

    def test_rejects_audio_outside_duration_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "short.wav"
            write_silence(source, seconds=0.1)
            with self.assertRaisesRegex(VoiceLibraryError, "0.5"):
                VoiceLibrary(Path(directory) / "library").save_user_voice(
                    str(source), "原文", "太短", rights_confirmed=True
                )


if __name__ == "__main__":
    unittest.main()
