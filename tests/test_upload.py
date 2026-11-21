"""vk record refuses to build notebooks for sentences Kaggle does not have yet (Kaggle is faked)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from voicetut_kaggle import cli, config, dataset

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo")


class Upload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "project")
        shutil.copytree(DEMO, self.project)
        self.config = os.path.join(self.project, "voices.yaml")
        with open(self.config, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        raw["kaggle"]["username"] = "tester"
        with open(self.config, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, allow_unicode=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def vk(self, *args):
        cli.main(["-c", self.config, *args])

    def upload(self):
        with mock.patch.object(dataset.kaggle, "dataset_exists", return_value=True), \
                mock.patch.object(dataset.kaggle, "run"), \
                mock.patch.object(dataset.kaggle, "wait_for_dataset"):
            self.vk("dataset", "--upload")

    def change_sentences(self):
        path = os.path.join(self.project, "sentences.json")
        with open(path, encoding="utf-8") as f:
            sentences = json.load(f)
        sentences["shared"].append("سطر جديد.")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sentences, f, ensure_ascii=False)

    def test_an_upload_remembers_the_version_it_sent(self):
        self.upload()

        cfg = config.load(self.config)
        self.assertEqual(dataset.uploaded_version(cfg), dataset.fingerprint(cfg))

    def test_record_refuses_sentences_changed_since_the_upload(self):
        self.upload()
        self.change_sentences()

        with self.assertRaises(SystemExit) as stopped:
            self.vk("record")

        self.assertIn("vk dataset --upload", str(stopped.exception))
        self.assertFalse(os.path.exists(os.path.join(self.project, "build", "kaggle", "part1")))

    def test_record_builds_after_the_new_upload(self):
        self.upload()
        self.change_sentences()
        self.upload()

        self.vk("record")

        self.assertTrue(os.path.isdir(os.path.join(self.project, "build", "kaggle", "part1")))


if __name__ == "__main__":
    unittest.main()
