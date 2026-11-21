"""The desktop window's data calls, run the way the window runs them: as a separate process."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "examples", "demo")
TOKEN = "KGAT_not_a_real_token_0123456789"


class DesktopApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def api(self, *args, stdin=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("KAGGLE")}
        env.update(HOME=self.home, PYTHONPATH=ROOT)
        done = subprocess.run([sys.executable, "-m", "voicetut_kaggle.desktop_api", *args], input=stdin,
                              capture_output=True, text=True, env=env, cwd=self.tmp)
        return done, json.loads(done.stdout)

    def test_a_folder_without_a_project_opens_empty(self):
        done, answer = self.api("open", self.tmp)

        self.assertEqual(done.returncode, 0)
        self.assertIsNone(answer["project"])
        self.assertIn("Karim", answer["builtin_voices"])

    def test_save_then_open_keeps_each_speakers_own_lines(self):
        project = os.path.join(self.tmp, "demo")
        shutil.copytree(DEMO, project)
        _, opened = self.api("open", project)
        draft = dict(opened["project"], username="tester", sentences=["أهلاً."])
        del draft["own"]  # the window may leave them out: saving keeps what the file has

        done, answer = self.api("save", stdin=json.dumps(draft))
        _, again = self.api("open", project)

        self.assertEqual(answer, {"ok": True}, done.stderr)
        self.assertEqual(again["project"]["sentences"], ["أهلاً."])
        self.assertEqual(again["project"]["own"], opened["project"]["own"])
        self.assertEqual(again["run"]["unfinished"], False)
        self.assertEqual(again["dataset_current"], False)  # never uploaded from here

    def test_a_bad_draft_is_an_error_not_a_crash(self):
        done, answer = self.api("save", stdin=json.dumps({"folder": self.tmp}))

        self.assertEqual(done.returncode, 1)
        self.assertFalse(answer["ok"])
        self.assertIn("missing field", answer["error"])

    def test_token_is_reported_copied_and_never_printed(self):
        source = os.path.join(self.tmp, "my-token.txt")
        with open(source, "w") as f:
            f.write(TOKEN)

        _, before = self.api("token")
        done, after = self.api("token", "--copy", source)

        self.assertFalse(before["token"])
        self.assertTrue(after["token"])
        self.assertNotIn(TOKEN, done.stdout + done.stderr)
        self.assertEqual(self.stored("access_token"), TOKEN + "\n")
        self.assertEqual(os.stat(self.path("access_token")).st_mode & 0o777, 0o600)

    def test_a_pasted_token_replaces_the_old_one(self):
        self.api("token", "--set", stdin=TOKEN)

        done, answer = self.api("token", "--set", stdin="  KGAT_the_new_token_9876543210\n")

        self.assertTrue(answer["token"])
        self.assertNotIn("KGAT_the_new_token", done.stdout + done.stderr)
        self.assertEqual(self.stored("access_token"), "KGAT_the_new_token_9876543210\n")
        self.assertEqual(os.stat(self.path("access_token")).st_mode & 0o777, 0o600)
        self.assertEqual(sorted(os.listdir(os.path.join(self.home, ".kaggle"))), ["access_token"])

    def test_a_broken_paste_keeps_the_old_token(self):
        self.api("token", "--set", stdin=TOKEN)

        done, answer = self.api("token", "--set", stdin="KGAT_half of it")

        self.assertEqual(done.returncode, 1)
        self.assertIn("does not look like a Kaggle API token", answer["error"])
        self.assertEqual(self.stored("access_token"), TOKEN + "\n")

    def test_an_old_kaggle_json_goes_to_kaggle_json(self):
        key = json.dumps({"username": "tester", "key": "0123456789abcdef"})

        _, answer = self.api("token", "--set", stdin=key)

        self.assertTrue(answer["token"])
        self.assertEqual(json.loads(self.stored("kaggle.json"))["username"], "tester")

    def path(self, name):
        return os.path.join(self.home, ".kaggle", name)

    def stored(self, name):
        with open(self.path(name)) as f:
            return f.read()


if __name__ == "__main__":
    unittest.main()
