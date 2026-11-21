"""vk watch with Kaggle replaced by a fake (the network boundary): what it pushes, and when."""
import argparse
import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from voicetut_kaggle import cli, config, desktop_api, watch

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo")


class FakeKaggle:
    """Each pushed notebook runs straight away and is COMPLETE on the next status call."""

    def __init__(self, busy=0):
        self.pushed = []
        self.busy = busy  # how many pushes are refused first with "both GPU slots are busy"
        self.status = {}

    def push(self, folder):
        if self.busy:
            self.busy -= 1
            return False
        name = os.path.basename(folder)
        self.pushed.append(name)
        self.status[name] = "RUNNING"
        return True

    def kernel_status(self, ref):
        name = ref.rsplit("-", 1)[1]
        status = self.status.get(name, "NONE")
        if status == "RUNNING":
            self.status[name] = "COMPLETE"
        return status


class Watch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "project")
        shutil.copytree(DEMO, self.project)
        path = os.path.join(self.project, "voices.yaml")
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        raw["kaggle"]["username"] = "tester"
        raw["recording"]["parts"] = 2
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, allow_unicode=True)
        self.config = path
        cli.main(["-c", path, "record"])
        self.cfg = config.load(path)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_watch(self, fake, **options):
        with mock.patch.object(watch.kaggle, "push", fake.push), \
                mock.patch.object(watch.kaggle, "kernel_status", fake.kernel_status), \
                mock.patch.object(watch.time, "sleep"):
            watch.watch(self.cfg, **options)

    def test_pushes_every_part_then_the_check_and_remembers_it(self):
        fake = FakeKaggle()

        self.run_watch(fake)

        self.assertEqual(fake.pushed, ["part1", "part2", "check"])
        self.assertEqual(watch.read_state(self.cfg), {"pushed": ["part1", "part2"], "check_pushed": True})

    def test_busy_gpu_slots_are_tried_again(self):
        fake = FakeKaggle(busy=3)

        self.run_watch(fake)

        self.assertEqual(fake.pushed, ["part2", "part1", "check"])

    def test_resume_pushes_only_what_was_not_pushed(self):
        first = FakeKaggle()
        with mock.patch.object(watch.kaggle, "push", first.push), \
                mock.patch.object(watch.kaggle, "kernel_status", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):  # the window closed while part1 and part2 ran
                watch.watch(self.cfg)
        again = FakeKaggle()
        again.status = {"part1": "RUNNING", "part2": "RUNNING"}

        self.run_watch(again, resume=True)

        self.assertEqual(again.pushed, ["check"])

    def test_resume_after_the_check_started_pushes_nothing(self):
        self.run_watch(FakeKaggle())
        again = FakeKaggle()
        again.status = {"part1": "COMPLETE", "part2": "COMPLETE"}

        self.run_watch(again, resume=True)

        self.assertEqual(again.pushed, [])

    def test_a_new_record_build_forgets_the_old_run(self):
        self.run_watch(FakeKaggle())

        cli.main(["-c", self.config, "record"])

        self.assertEqual(watch.read_state(self.cfg), {"pushed": [], "check_pushed": False})

    def test_the_window_gets_the_status_of_each_pushed_notebook(self):
        self.run_watch(FakeKaggle())
        kaggle_now = FakeKaggle()
        kaggle_now.status = {"part1": "COMPLETE", "part2": "COMPLETE", "check": "RUNNING"}

        with mock.patch.object(desktop_api.kaggle, "kernel_status", kaggle_now.kernel_status):
            answer = desktop_api.cmd_status(argparse.Namespace(folder=os.path.dirname(self.config)))

        self.assertEqual(answer["notebooks"], {"part1": "COMPLETE", "part2": "COMPLETE", "check": "RUNNING"})

    def test_nothing_pushed_means_no_status(self):
        answer = desktop_api.cmd_status(argparse.Namespace(folder=os.path.dirname(self.config)))

        self.assertEqual(answer["notebooks"], {})


if __name__ == "__main__":
    unittest.main()
