"""The listening page for a voices_checked.zip: flagged lines, or every line when none is flagged."""
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from types import SimpleNamespace

from voicetut_kaggle import listen

CFG = SimpleNamespace(check={"threshold": 0.15})


class FlaggedPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def page(self, errors, show_all=False):
        """A checked zip with one line per error score; returns the page's HTML."""
        path = os.path.join(self.tmp, "voices_checked.zip")
        report = {f"narrator/{n:03d}": {"text": f"سطر {n}", "heard": f"سطر {n}", "errors": e, "take": 1, "takes": 1}
                  for n, e in enumerate(errors)}
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("report.json", json.dumps(report))
            for key in report:
                z.writestr(f"voices/{key}.flac", b"clip")
        page = listen.build(CFG, path, os.path.join(self.tmp, "listen"), show_all=show_all)
        with open(page, encoding="utf-8") as f:
            return f.read()

    def test_when_every_line_passed_the_page_lists_them_all(self):
        page = self.page([0.0, 0.05, 0.1])

        self.assertIn("Every line passed the check (3 lines)", page)
        self.assertEqual(page.count("<audio"), 3)
        self.assertNotIn("class=f>flagged", page)

    def test_only_flagged_lines_by_default(self):
        page = self.page([0.0, 0.4, 0.1])

        self.assertIn("Lines the recognizer still flags (1 of 3)", page)
        self.assertEqual(page.count("<audio"), 1)

    def test_all_lines_marks_the_flagged_ones(self):
        page = self.page([0.0, 0.4, 0.1], show_all=True)

        self.assertIn("All lines (1 of 3 flagged)", page)
        self.assertEqual(page.count("<audio"), 3)
        self.assertEqual(page.count("class=f>flagged"), 1)


if __name__ == "__main__":
    unittest.main()
