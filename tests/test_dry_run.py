"""Runs the whole pipeline locally: builds every notebook from a project like examples/demo, then
executes the notebooks' code with stand-in models (tests/fakes) in a fake /kaggle folder layout.

Needs ffmpeg (for the clip speaker and the export). Run: python -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import yaml

from voicetut_kaggle import cli

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(os.path.dirname(HERE), "examples", "demo")
FAKES = os.path.join(HERE, "fakes")

# Executes a notebook's code cells in order, skipping shell lines (!pip, !nvidia-smi).
RUNNER = """
import json, sys
cells = json.load(open(sys.argv[1]))["cells"]
scope = {"__name__": "__main__"}
for c in cells:
    if c["cell_type"] == "code":
        exec("\\n".join(l for l in c["source"].splitlines() if not l.lstrip().startswith("!")), scope)
"""


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def ffmpeg_tone(path, seconds=1):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}", path], check=True)


class DryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "project")
        shutil.copytree(DEMO, self.project, ignore=shutil.ignore_patterns("build"))
        os.makedirs(os.path.join(self.project, "clips"))
        ffmpeg_tone(os.path.join(self.project, "clips", "me.ogg"))
        self.config = os.path.join(self.project, "voices.yaml")
        with open(self.config) as f:
            cfg = yaml.safe_load(f)
        cfg["kaggle"]["username"] = "tester"
        cfg["speakers"].append({"id": "me", "clip": "clips/me.ogg", "transcript": "أهلاً"})
        cfg["recording"]["parts"] = 2
        with open(self.config, "w") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        self.build = os.path.join(self.project, "build")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def vk(self, *args):
        cli.main(["-c", self.config, *args])

    def execute(self, name, inputs):
        """Runs build/kaggle/<name> with the dataset and the given {folder: zip} as input."""
        work, input_dir = os.path.join(self.tmp, "work", name), os.path.join(self.tmp, "input", name)
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(input_dir, ignore_errors=True)
        os.makedirs(work)
        shutil.copytree(os.path.join(self.build, "kaggle", "data"), os.path.join(input_dir, "vk-demo-data"))
        for folder, path in inputs.items():
            os.makedirs(os.path.join(input_dir, folder))
            shutil.copy(path, os.path.join(input_dir, folder))
        asr_lib = os.path.join(self.tmp, "asrlib")
        shutil.copytree(FAKES, asr_lib, dirs_exist_ok=True)
        env = dict(os.environ, WORK=work, INPUT=input_dir, GPUS="2", REPORT_EVERY="1",
                   ASR_LIB=asr_lib, PYTHONPATH=FAKES)
        notebook = os.path.join(self.build, "kaggle", name, f"vk-demo-{name}.ipynb")
        done = subprocess.run([sys.executable, "-c", RUNNER, notebook], env=env, capture_output=True, text=True)
        return work, done

    def run_notebook(self, name, inputs):
        work, done = self.execute(name, inputs)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-3000:])
        return work

    def test_whole_pipeline(self):
        self.vk("dataset")
        self.vk("record")
        parts = {f"vk-demo-part{p}": os.path.join(self.run_notebook(f"part{p}", {}), "voices.zip")
                 for p in (1, 2)}

        checked = os.path.join(self.run_notebook("check", parts), "voices_checked.zip")
        with zipfile.ZipFile(checked) as z:
            report = json.loads(z.read("report.json"))
            self.assertEqual(len(report), 14)  # 4 shared lines x 3 speakers + 2 own lines
            self.assertIn("voices/narrator/004.flac", z.namelist())
        retaken = sorted(k for k, r in report.items() if r["take"] > 1)
        self.assertEqual(retaken, ["guide/003", "me/003", "narrator/003"])  # the question
        self.assertTrue(all(r["errors"] <= 0.15 for r in report.values()), report)

        self.vk("listen", checked, "--all")
        with open(os.path.join(self.build, "listen", "voices_checked", "index.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertEqual(page.count("<tr>"), 15)  # header + 14 lines

        self.vk("fix", os.path.join(self.project, "fixes.yaml"))
        fix_zip = os.path.join(self.run_notebook("fix", {}), "fix.zip")
        swapped = os.path.join(self.tmp, "swapped.zip")
        self.vk("use-take", fix_zip, checked, swapped, "guide_002_b1")
        with zipfile.ZipFile(swapped) as z, zipfile.ZipFile(checked) as old:
            self.assertEqual(z.read("voices/guide/002.flac").decode(), "بْرَافُو عَلِيك، إِجَابَة صَحْ!")
            self.assertEqual(z.read("voices/narrator/002.flac"), old.read("voices/narrator/002.flac"))
        self.vk("listen", fix_zip, "--compare", checked)

        sentences_path = os.path.join(self.project, "sentences.json")
        sentences = read_json(sentences_path)
        sentences["shared"].append("يلا بينا!")
        write_json(sentences_path, sentences)
        self.vk("dataset")
        self.vk("new-lines", "4-4")
        new = os.path.join(self.run_notebook("new-lines", {}), "voices_checked.zip")
        merged = os.path.join(self.tmp, "merged.zip")
        self.vk("merge", checked, new, "4-4", merged)
        with zipfile.ZipFile(merged) as z, zipfile.ZipFile(checked) as old:
            self.assertEqual(z.read("voices/narrator/005.flac"), old.read("voices/narrator/004.flac"))  # moved up
            self.assertEqual(z.read("voices/me/004.flac").decode(), "يلا بينا!")
            self.assertEqual(len([n for n in z.namelist() if n.endswith(".flac")]), 17)

    def test_notebook_refuses_an_old_dataset(self):
        self.vk("dataset")
        self.vk("record")
        speakers = os.path.join(self.build, "kaggle", "data", "speakers.json")
        info = read_json(speakers)
        info["version"] = "old"
        write_json(speakers, info)
        _, done = self.execute("part1", {})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("older version of the tester/vk-demo-data dataset", done.stderr)

    def test_export_makes_opus_files_and_lines_json(self):
        voices = os.path.join(self.tmp, "voices.zip")
        tone = os.path.join(self.tmp, "tone.flac")
        ffmpeg_tone(tone)
        with zipfile.ZipFile(voices, "w") as z:
            for speaker in ("narrator", "guide", "me"):
                for n in range(5):
                    z.write(tone, f"voices/{speaker}/{n:03d}.flac")
        self.vk("export", voices)
        out = os.path.join(self.build, "app_audio")
        self.assertEqual(sorted(os.listdir(os.path.join(out, "narrator"))), [f"{n:03d}.webm" for n in range(5)])
        self.assertEqual(len(os.listdir(os.path.join(out, "me"))), 4)  # shared lines only
        lines = read_json(os.path.join(out, "lines.json"))
        self.assertEqual(lines["narrator"][4], "أنا الراوي، وهحكيلك حكاية حلوة.")


if __name__ == "__main__":
    unittest.main()
