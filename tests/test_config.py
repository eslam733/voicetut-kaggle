import json
import os
import shutil
import tempfile
import unittest

import yaml

from voicetut_kaggle import config

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo")


class LoadConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copytree(DEMO, self.tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns("build"))
        self.path = os.path.join(self.tmp, "voices.yaml")
        with open(self.path) as f:
            self.raw = yaml.safe_load(f)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def load_with(self, **changes):
        with open(self.path, "w") as f:
            yaml.safe_dump({**self.raw, **changes}, f, allow_unicode=True)
        return config.load(self.path)

    def test_demo_lines_are_shared_then_own(self):
        cfg = config.load(self.path)
        self.assertEqual(cfg.lines("narrator")[1], "عندي ٣ تفاحات.")
        self.assertEqual(cfg.lines("narrator")[4], "أنا الراوي، وهحكيلك حكاية حلوة.")
        self.assertEqual(cfg.kernel_slug("part1"), "vk-demo-part1")
        self.assertEqual(cfg.recording["num_step"], 48)

    def test_a_plain_list_of_sentences_is_said_by_everyone(self):
        with open(os.path.join(self.tmp, "list.json"), "w", encoding="utf-8") as f:
            json.dump(["واحد", "اتنين"], f, ensure_ascii=False)
        cfg = self.load_with(sentences="list.json")
        self.assertEqual(cfg.lines("guide"), ["واحد", "اتنين"])

    def test_rejects_wrong_values(self):
        cases = {
            "unknown key": {"projct": "x"},
            "bad project slug": {"project": "My Voices"},
            "two voice kinds": {"speakers": [{"id": "a", "builtin": "Karim", "instruct": "calm"}]},
            "duplicate ids": {"speakers": [{"id": "a", "builtin": "Karim"}, {"id": "a", "builtin": "Yasmin"}]},
            "missing clip": {"speakers": [{"id": "a", "clip": "nope.ogg", "transcript": "x"}]},
            "too many parts": {"recording": {"parts": 3}},
            "threshold out of range": {"check": {"threshold": 2}},
            "unknown export format": {"export": {"format": "mp3"}},
        }
        for name, change in cases.items():
            with self.subTest(name), self.assertRaises(config.ConfigError):
                self.load_with(**change)

    def test_clip_needs_its_transcript(self):
        open(os.path.join(self.tmp, "me.ogg"), "wb").close()
        with self.assertRaisesRegex(config.ConfigError, "transcript"):
            self.load_with(speakers=[{"id": "me", "clip": "me.ogg"}])


if __name__ == "__main__":
    unittest.main()
