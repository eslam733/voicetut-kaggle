"""vk eleven: voices, recording and the zip it makes, against a fake ElevenLabs (no network, no credits)."""
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

import yaml

from voicetut_kaggle import config, eleven, listen

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo")


class FakeReply:
    def __init__(self, data=None, content=b""):
        self.data, self.content = data, content

    def json(self):
        return self.data


class FakeEleven:
    """Answers the calls eleven.py makes, and remembers them."""

    def __init__(self, used=0, limit=10000):
        self.used, self.limit, self.spoken, self.cloned, self.deleted = used, limit, [], [], []

    def __call__(self, key, method, path, tries=5, **kwargs):
        assert key == "test-key"
        if path == "/v1/user/subscription":
            return FakeReply({"character_count": self.used, "character_limit": self.limit, "tier": "starter"})
        if path == "/v1/voices/add":
            self.cloned.append(kwargs["data"]["name"])
            return FakeReply({"voice_id": f"v-{len(self.cloned)}"})
        if method == "DELETE":
            self.deleted.append(path.rsplit("/", 1)[1])
            return FakeReply({})
        if path.startswith("/v1/text-to-speech/"):
            body = kwargs["json"]
            self.spoken.append((path.rsplit("/", 1)[1], body["text"], body["seed"], body["voice_settings"]))
            return FakeReply(content=b"pcm:" + body["text"].encode())
        raise AssertionError(f"unexpected call {method} {path}")


def fake_flac(pcm, path):
    with open(path, "wb") as f:
        f.write(pcm)


class Eleven(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copytree(DEMO, self.tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns("build"))
        self.path = os.path.join(self.tmp, "voices.yaml")
        with open(self.path) as f:
            self.raw = yaml.safe_load(f)
        self.api = FakeEleven()
        for patch in (mock.patch.object(eleven, "_call", self.api),
                      mock.patch.object(eleven, "_to_flac", fake_flac),
                      mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key"})):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def load(self, **eleven_settings):
        raw = dict(self.raw)
        raw["eleven"] = {"voices": {"narrator": "v-narrator", "guide": "v-guide"}, **eleven_settings}
        with open(self.path, "w") as f:
            yaml.safe_dump(raw, f, allow_unicode=True)
        return config.load(self.path)

    def test_defaults_and_wrong_values(self):
        cfg = self.load()
        self.assertEqual(cfg.eleven["model"], "eleven_v3")
        self.assertEqual(cfg.eleven["takes"], 2)
        for name, change in {
            "v3 stability": {"stability": 0.3},
            "too many takes": {"takes": 20},
            "speed": {"speed": 2},
            "unknown speaker": {"voices": {"nobody": "v-1"}},
            "unknown key": {"stabilty": 0.5},
        }.items():
            with self.subTest(name), self.assertRaises(config.ConfigError):
                self.load(**change)

    def test_lines_get_the_pronunciation_files_spelling(self):
        cfg = self.load()
        jobs = eleven.line_jobs(cfg, 0, 0, speakers=["narrator"])
        self.assertEqual([j["name"] for j in jobs], ["narrator_000_e1", "narrator_000_e2"])
        self.assertIn("النَّهَارْدَه", jobs[0]["text"])  # vowelled from the pronunciation file
        plain = eleven.line_jobs(self.load(vowels=False), 0, 0, speakers=["narrator"])
        self.assertEqual(plain[0]["text"], cfg.lines("narrator")[0])

    def test_numbers_are_said_in_egyptian_arabic(self):
        said = eleven._spelled(self.load(), "عندي ٣ تفاحات و ١٣ تينة.")
        self.assertIn("تَلَاتَة", said)
        self.assertIn("تَلَتْطَاشَر", said)
        self.assertNotRegex(said, r"[0-9٠-٩]")
        self.assertEqual(eleven._spelled(self.load(vowels=False), "عندي 3 تفاحات."), "عندي تَلَاتَة تفاحات.")

    def test_record_writes_a_fix_zip_and_never_pays_twice(self):
        cfg = self.load(takes=1)
        jobs = eleven.line_jobs(cfg, 0, 1)
        out = os.path.join(self.tmp, "eleven.zip")
        eleven.record(cfg, jobs, out, yes=True)
        self.assertEqual(len(self.api.spoken), 4)  # 2 speakers x 2 lines x 1 take
        voice, _, seed, settings = self.api.spoken[0]
        self.assertEqual((voice, seed, settings["stability"]), ("v-narrator", 1000, 0.5))
        with zipfile.ZipFile(out) as z:
            said = json.loads(z.read("fix/said.json"))
            self.assertEqual(set(said), {j["name"] for j in jobs})
            self.assertEqual(said["guide_001_e1"]["line"], 1)
            self.assertTrue(z.read("fix/guide_001_e1.flac").startswith(b"pcm:"))
        # The same command again reuses the kept clips: nothing new is spoken.
        eleven.record(cfg, jobs, out, yes=True)
        self.assertEqual(len(self.api.spoken), 4)

    def test_a_new_voice_or_setting_records_again(self):
        cfg = self.load(takes=1)
        jobs = eleven.line_jobs(cfg, 0, 0, speakers=["guide"])
        out = os.path.join(self.tmp, "eleven.zip")
        eleven.record(cfg, jobs, out, yes=True)
        eleven.record(cfg, jobs, out, yes=True, settings={"stability": 0})
        self.assertEqual([s[3]["stability"] for s in self.api.spoken], [0.5, 0])

    def test_record_asks_first_and_stops_without_credits(self):
        cfg = self.load(takes=1)
        jobs = eleven.line_jobs(cfg, 0, 0, speakers=["guide"])
        out = os.path.join(self.tmp, "eleven.zip")
        with self.assertRaisesRegex(eleven.ElevenError, "nothing recorded"):
            eleven.record(cfg, jobs, out, confirm=lambda _: "n")
        self.api.used = self.api.limit
        with self.assertRaisesRegex(eleven.ElevenError, "not enough characters"):
            eleven.record(cfg, jobs, out, yes=True)
        self.assertEqual(self.api.spoken, [])

    def test_fixes_file_gives_one_variant_per_spelling(self):
        cfg = self.load()
        jobs = eleven.fix_jobs(cfg, os.path.join(self.tmp, "fixes.yaml"), takes=1)
        variants = {(j["speaker"], j["line"], j["variant"]) for j in jobs}
        self.assertTrue(variants)
        self.assertTrue(all(j["name"].endswith(f"_{j['variant']}1") for j in jobs))

    def test_voices_are_cloned_once_from_the_clips(self):
        clip = os.path.join(self.tmp, "me.ogg")
        with open(clip, "wb") as f:
            f.write(b"clip")
        raw = dict(self.raw, speakers=[{"id": "me", "clip": "me.ogg", "transcript": "أهلاً"}])
        raw["sentences"] = "list.json"
        with open(os.path.join(self.tmp, "list.json"), "w", encoding="utf-8") as f:
            json.dump(["واحد"], f, ensure_ascii=False)
        with open(self.path, "w") as f:
            yaml.safe_dump(raw, f, allow_unicode=True)
        cfg = config.load(self.path)
        self.assertEqual(eleven.make_voices(cfg), {"me": "v-1"})
        self.assertEqual(eleven.make_voices(cfg), {"me": "v-1"})  # kept: not cloned again
        self.assertEqual(self.api.cloned, ["vk-demo-me"])
        eleven.delete_voices(cfg)  # frees the slot; cloned again next time it is needed
        self.assertEqual((self.api.deleted, eleven.voice_ids(cfg)), (["v-1"], {}))

    def test_the_listening_page_has_pick_buttons_and_the_command(self):
        cfg = self.load(takes=2)
        out = os.path.join(self.tmp, "eleven.zip")
        eleven.record(cfg, eleven.line_jobs(cfg, 0, 0, speakers=["guide"]), out, yes=True)
        voices = os.path.join(self.tmp, "voices.zip")
        with zipfile.ZipFile(voices, "w") as z:
            z.writestr("voices/guide/000.flac", b"now")
        page = listen.build(cfg, out, os.path.join(self.tmp, "listen"), compare=voices)
        with open(page, encoding="utf-8") as f:
            html = f.read()
        self.assertEqual(html.count("class=pick"), 3)  # keep, e1, e2
        self.assertIn("value='guide_000_e2'", html)
        picked = os.path.join(self.tmp, "voices_picked.zip")
        self.assertIn(f"vk use-take {out} {voices} {picked}", html)


if __name__ == "__main__":
    unittest.main()
