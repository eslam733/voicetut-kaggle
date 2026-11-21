"""The window's fix step: which lines to re-record, the takes Kaggle made, and using the picked ones."""
import argparse
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

import yaml

from voicetut_kaggle import desktop_api
from voicetut_kaggle.config import ConfigError

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo")
SPELLINGS = ["بْرَافُو عَلِيك، إِجَابَة صَحّ!", "بْرَافُو عَلِيك، إِجَابَة صَحْ!"]


class FixStep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "project")
        shutil.copytree(DEMO, self.project)
        path = os.path.join(self.project, "voices.yaml")
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        raw["kaggle"]["username"] = "tester"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, allow_unicode=True)
        self.build = os.path.join(self.project, "build")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def call(self, command, stdin=None, **args):
        with mock.patch("sys.stdin", io.StringIO(json.dumps(stdin) if stdin else "")):
            return command(argparse.Namespace(folder=self.project, **args))

    def downloaded(self):
        """A checked zip (as `vk fetch check` leaves it) and a fix zip with two spellings x 2 takes."""
        os.makedirs(os.path.join(self.build, "out", "check"))
        os.makedirs(os.path.join(self.build, "out", "fix"))
        report = {f"{s}/{n:03d}": {"text": "x", "heard": "x", "errors": 0.3, "take": 1, "takes": 4}
                  for s in ("narrator", "guide") for n in range(5)}
        with zipfile.ZipFile(os.path.join(self.build, "out", "check", "voices_checked.zip"), "w") as z:
            z.writestr("report.json", json.dumps(report))
            for key in report:
                z.writestr(f"voices/{key}.flac", b"old " + key.encode())
        said = {f"narrator_002_{v}{t}": {"speaker": "narrator", "line": 2, "variant": v, "take": t, "text": text}
                for v, text in zip("ab", SPELLINGS) for t in (1, 2)}
        with zipfile.ZipFile(os.path.join(self.build, "out", "fix", "fix.zip"), "w") as z:
            z.writestr("fix/said.json", json.dumps(said, ensure_ascii=False))
            for name in said:
                z.writestr(f"fix/{name}.flac", name.encode())

    def checked(self, name):
        with zipfile.ZipFile(os.path.join(self.build, "out", "check", "voices_checked.zip")) as z:
            return z.read(name)

    def test_fix_save_writes_a_fixes_file_the_fix_notebook_accepts(self):
        answer = self.call(desktop_api.cmd_fix_save, stdin={
            "takes": 3, "lines": [{"speaker": "guide", "line": 2, "spellings": SPELLINGS}]})

        self.assertEqual(answer["clips"], 6)  # 2 spellings x 3 takes
        with open(answer["path"], encoding="utf-8") as f:
            self.assertEqual(yaml.safe_load(f)["lines"][0]["speakers"], ["guide"])

    def test_fix_save_refuses_a_line_the_speaker_does_not_have(self):
        with self.assertRaises(ConfigError) as refused:
            self.call(desktop_api.cmd_fix_save, stdin={
                "lines": [{"speaker": "guide", "line": 40, "spellings": SPELLINGS}]})

        self.assertIn("has no line 40", str(refused.exception))

    def test_takes_are_grouped_by_the_clip_they_replace(self):
        self.downloaded()

        clips = self.call(desktop_api.cmd_takes)["clips"]

        self.assertEqual([(c["speaker"], c["line"]) for c in clips], [("narrator", 2)])
        self.assertEqual([t["name"] for t in clips[0]["takes"]],
                         ["narrator_002_a1", "narrator_002_a2", "narrator_002_b1", "narrator_002_b2"])
        self.assertEqual(clips[0]["sentence"], "برافو عليك، إجابة صح!")

    def test_using_a_take_swaps_the_clip_keeps_the_original_and_remembers_the_spelling(self):
        self.downloaded()
        original = self.checked("voices/narrator/002.flac")

        answer = self.call(desktop_api.cmd_use_takes, takes=["narrator_002_b2"])
        self.call(desktop_api.cmd_use_takes, takes=["narrator_002_a1"])

        self.assertEqual(answer["swapped"], 1)
        self.assertEqual(self.checked("voices/narrator/002.flac"), b"narrator_002_a1")
        self.assertEqual(self.checked("voices/guide/002.flac"), b"old guide/002")
        with zipfile.ZipFile(answer["backup"]) as z:  # kept from before the first swap
            self.assertEqual(z.read("voices/narrator/002.flac"), original)
        self.assertEqual(json.loads(self.checked("report.json"))["narrator/002"]["fixed"], "narrator_002_a1")
        with open(os.path.join(self.project, "pronunciation.json"), encoding="utf-8") as f:
            lines = json.load(f)["lines"]
        self.assertEqual(lines["برافو عليك، إجابة صح!"], SPELLINGS[0])
        self.assertIn("ممكن تعيد تاني؟", lines)  # what was there stays

    def test_an_unknown_take_changes_nothing(self):
        self.downloaded()
        before = self.checked("voices/narrator/002.flac")

        with self.assertRaises(ValueError):
            self.call(desktop_api.cmd_use_takes, takes=["narrator_009_z9"])

        self.assertEqual(self.checked("voices/narrator/002.flac"), before)
        self.assertFalse(os.path.exists(os.path.join(self.build, "out", "check", "voices_checked.zip.new")))


if __name__ == "__main__":
    unittest.main()
