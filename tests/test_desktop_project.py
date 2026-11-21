import os
import shutil
import tempfile
import unittest

from voicetut_kaggle.config import ConfigError, load
from voicetut_kaggle.desktop_project import ProjectDraft, SpeakerDraft, read_project, write_project

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo")


class WriteProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_a_built_in_voice_is_saved_and_read_back(self):
        draft = ProjectDraft(
            self.tmp, "my-voices", "tester",
            [SpeakerDraft("narrator", "builtin", "Karim")],
            ["أهلاً وسهلاً!", "يلا نبدأ."],
        )
        cfg = write_project(draft)
        self.assertEqual(cfg.lines("narrator"), ["أهلاً وسهلاً!", "يلا نبدأ."])
        self.assertEqual(cfg.speakers[0].mode, "builtin")
        self.assertEqual(cfg.speakers[0].value, "Karim")
        again = read_project(self.tmp)
        self.assertEqual(again.username, "tester")
        self.assertEqual(again.speakers[0].value, "Karim")
        self.assertEqual(again.sentences, ["أهلاً وسهلاً!", "يلا نبدأ."])

    def test_a_clip_outside_the_folder_is_copied_in(self):
        source = os.path.join(self.tmp, "outside.ogg")
        with open(source, "wb") as f:
            f.write(b"not really audio")
        project = os.path.join(self.tmp, "project")
        draft = ProjectDraft(
            project, "my-voices", "tester",
            [SpeakerDraft("me", "clip", source, "النهارده الجو حلو.")],
            ["أهلاً."],
        )
        cfg = write_project(draft)
        self.assertTrue(cfg.speakers[0].value.endswith(os.path.join("clips", "me.ogg")))
        self.assertEqual(cfg.speakers[0].transcript, "النهارده الجو حلو.")
        self.assertTrue(os.path.isfile(os.path.join(project, "clips", "me.ogg")))
        again = read_project(project)
        self.assertEqual(again.speakers[0].value, "clips/me.ogg")
        self.assertEqual(again.speakers[0].transcript, "النهارده الجو حلو.")

    def test_a_speakers_own_lines_survive_saving(self):
        draft = ProjectDraft(
            self.tmp, "my-voices", "tester",
            [SpeakerDraft("narrator", "builtin", "Karim"), SpeakerDraft("guide", "builtin", "Yasmin")],
            ["أهلاً."],
            {"narrator": ["أنا الراوي."], "guide": ["أنا المرشدة."]},
        )
        cfg = write_project(draft)
        self.assertEqual(cfg.lines("narrator"), ["أهلاً.", "أنا الراوي."])
        again = read_project(self.tmp)
        self.assertEqual(list(again.own["guide"]), ["أنا المرشدة."])

    def test_saving_keeps_the_settings_the_form_does_not_edit(self):
        project = os.path.join(self.tmp, "demo")
        shutil.copytree(DEMO, project)
        path = os.path.join(project, "voices.yaml")
        with open(path, encoding="utf-8") as f:
            text = f.read().replace("your-kaggle-username", "tester").replace("num_step: 48", "num_step: 16")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        before = load(path)

        after = write_project(read_project(project))

        self.assertEqual(len(before.pronunciation["words"]), 3)
        self.assertEqual(after.pronunciation, before.pronunciation)
        self.assertEqual(after.recording["num_step"], 16)
        self.assertEqual(after.check, before.check)
        self.assertEqual(after.export, before.export)
        self.assertEqual(after.lines("narrator"), before.lines("narrator"))

    def test_saving_keeps_the_sentences_file_name(self):
        draft = ProjectDraft(self.tmp, "my-voices", "tester", [SpeakerDraft("narrator", "builtin", "Karim")],
                             ["أهلاً."])
        write_project(draft)
        path = os.path.join(self.tmp, "voices.yaml")
        os.rename(os.path.join(self.tmp, "sentences.json"), os.path.join(self.tmp, "lines.json"))
        with open(path, encoding="utf-8") as f:
            text = f.read().replace("sentences.json", "lines.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

        draft.sentences = ["يلا نبدأ."]
        cfg = write_project(draft)

        self.assertEqual(cfg.lines("narrator"), ["يلا نبدأ."])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "sentences.json")))

    def test_the_placeholder_username_is_rejected(self):
        draft = ProjectDraft(
            self.tmp, "my-voices", "your-kaggle-username",
            [SpeakerDraft("narrator", "builtin", "Karim")],
            ["أهلاً."],
        )
        with self.assertRaises(ConfigError):
            write_project(draft)

    def test_a_clip_without_a_transcript_is_rejected(self):
        source = os.path.join(self.tmp, "me.ogg")
        with open(source, "wb") as f:
            f.write(b"x")
        draft = ProjectDraft(
            self.tmp, "my-voices", "tester",
            [SpeakerDraft("me", "clip", source, "  ")],
            ["أهلاً."],
        )
        with self.assertRaises(ConfigError):
            write_project(draft)
