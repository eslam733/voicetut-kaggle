"""vk fetch says what a notebook is doing instead of looking for files it has not made yet."""
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from voicetut_kaggle import cli

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo")


class Fetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        project = os.path.join(self.tmp, "project")
        shutil.copytree(DEMO, project)
        self.config = os.path.join(project, "voices.yaml")
        with open(self.config, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        raw["kaggle"]["username"] = "tester"
        with open(self.config, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, allow_unicode=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fetch(self, status):
        with mock.patch.object(cli.kaggle, "kernel_status", return_value=status), \
                mock.patch.object(cli.kaggle, "find_output_files", return_value={}) as find:
            with self.assertRaises(SystemExit) as stopped:
                cli.main(["-c", self.config, "fetch", "check"])
        return str(stopped.exception), find

    def test_a_running_notebook_is_reported_as_not_finished(self):
        message, find = self.fetch("RUNNING")

        self.assertIn("vk-demo-check is RUNNING on Kaggle, not finished", message)
        find.assert_not_called()

    def test_a_failed_notebook_points_to_its_log(self):
        message, _ = self.fetch("ERROR")

        self.assertIn("failed; open it on kaggle.com", message)

    def test_a_finished_notebook_without_the_file_still_says_so(self):
        message, find = self.fetch("COMPLETE")

        self.assertIn("output has no ['voices_checked.zip']", message)
        find.assert_called_once()

    def test_status_prints_every_notebook_in_one_line(self):
        statuses = {"tester/vk-demo-part1": "COMPLETE", "tester/vk-demo-check": "RUNNING"}
        with mock.patch.object(cli.kaggle, "kernel_status", side_effect=lambda ref: statuses.get(ref, "NONE")), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            cli.main(["-c", self.config, "status"])

        self.assertEqual(out.getvalue().strip(), "part1=COMPLETE  check=RUNNING")


if __name__ == "__main__":
    unittest.main()
