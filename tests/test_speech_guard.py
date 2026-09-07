import unittest
from speech_guard import generation_budget, script_endpoint


def words(text):
    return [{"word": c, "start": i * .1, "end": (i + 1) * .1} for i, c in enumerate(text)]


class SpeechGuardTests(unittest.TestCase):
    def test_short_script_does_not_inherit_160_second_limit(self):
        text = "[S1]唉，我录了好多遍，声音还是不够自然。[S2]别急！交给云途觉晓，让每个角色都能有声有色！"
        self.assertLess(generation_budget(text, 2000), 300)
        self.assertLessEqual(generation_budget(text, 128), 128)
        self.assertGreater(generation_budget(text * 5), generation_budget(text))

    def test_unrelated_tail_and_repeated_script_are_removed(self):
        script = "你好欢迎来到云途觉晓今天我们测试多人配音"
        for tail in ("接下来播报一些没有在台词里的新闻内容", script):
            result = script_endpoint("[S1]" + script, words(script + tail))
            self.assertTrue(result["ok"])
            self.assertAlmostEqual(result["end"], len(script) * .1)

    def test_incomplete_or_unrelated_output_is_blocked(self):
        script = "你好欢迎来到云途觉晓今天我们测试多人配音"
        self.assertFalse(script_endpoint(script, words(script[:12]))["ok"])
        self.assertFalse(script_endpoint(script, words("随便说一些别的内容" + script))["ok"])

    def test_punctuation_and_english_case_are_ignored(self):
        result = script_endpoint("[S1]Hello, world!", words("hello world. More text"))
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["end"], 1.1)

    def test_actual_short_ad_homophones_and_no_gap_to_hallucination(self):
        text = "[S1]唉，我录了好多遍，声音还是不够自然。[S2]别急，交给云途觉晓，让每个角色都能有声有色。"
        transcript = "哎我录了好多遍声音还是不够自然别急交给云图觉晓让每个角色都能有声有色"
        result = script_endpoint(text, words(transcript + "点剑跟猪庆幸这些额外内容"))
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["end"], len(transcript) * .1)
        self.assertEqual(result["cut_at"], result["end"])


if __name__ == "__main__":
    unittest.main()
