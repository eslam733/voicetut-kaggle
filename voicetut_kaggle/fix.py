"""Step 6: re-record a few clips with several spellings, a few takes each, to pick the best by ear.

The spellings come from a small YAML file (see examples/demo/fixes.yaml):
  takes: 2
  lines:
    - line: 3
      speakers: [narrator]
      spellings: ["...", "..."]
Each spelling is given to VoiceTut exactly as written (the pronunciation file is skipped).
Output: fix.zip with fix/<speaker>_<nnn>_<variant><take>.flac and said.json.
Then `use-take` swaps the picked takes into the checked voices.
"""
import json
import string
import zipfile

import yaml

from . import notebooks
from .config import ConfigError
from .pronounce import plain

RUN = r'''
import soundfile as sf
from voices_lib import load_tts, say

OUT = f"{WORK}/fix"
os.makedirs(OUT, exist_ok=True)
make_refs({job["speaker"] for job in JOBS})
tts = load_tts()
for job in JOBS:
    wav = say(tts, job["text"], job["speaker"], exact=True)
    sf.write(f"{OUT}/{job['name']}.flac", wav, tts.sampling_rate)
    print(job["name"], job["text"], flush=True)
said = {job.pop("name"): job for job in JOBS}
json.dump(said, open(f"{OUT}/said.json", "w"), ensure_ascii=False, indent=1)
shutil.make_archive(f"{WORK}/fix", "zip", WORK, "fix")
print("done:", len(said), "clips in fix.zip")
'''


def load_jobs(cfg, path):
    """One job per speaker x spelling x take, named <speaker>_<nnn>_<variant><take>."""
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    takes = spec.get("takes", 2)
    if not isinstance(takes, int) or not 1 <= takes <= 5:
        raise ConfigError(f"{path}: 'takes' must be 1..5")
    jobs = []
    for entry in spec.get("lines") or []:
        line, speakers, spellings = entry.get("line"), entry.get("speakers") or [], entry.get("spellings") or []
        if not spellings or len(spellings) > 26:
            raise ConfigError(f"{path}: line {line} needs 1 to 26 spellings")
        for speaker in speakers:
            if speaker not in cfg.speaker_ids() or not isinstance(line, int) or not 0 <= line < len(cfg.lines(speaker)):
                raise ConfigError(f"{path}: speaker '{speaker}' has no line {line}")
            for variant, text in zip(string.ascii_lowercase, spellings):
                jobs += [{"name": f"{speaker}_{line:03d}_{variant}{take}", "speaker": speaker, "line": line,
                          "variant": variant, "take": take, "text": text} for take in range(1, takes + 1)]
    if not jobs:
        raise ConfigError(f"{path}: no lines to re-record")
    return jobs


def build(cfg, path):
    jobs = load_jobs(cfg, path)
    cells = [
        notebooks.cell("markdown", f"# {cfg.project}: re-record a few clips\n\n"
                                   f"{len(jobs)} clips: several spellings, a few takes each."),
        notebooks.cell("code", notebooks.INSTALL),
        notebooks.cell("code", notebooks.embedded_code(cfg) + f"\nJOBS = {jobs!r}"),
        notebooks.cell("code", notebooks.setup_code(cfg)),
        notebooks.cell("code", RUN.strip()),
    ]
    return notebooks.write(cfg, "fix", cells)


def use_takes(cfg, fix_zip, base_zip, out_zip, names):
    """Copies base_zip to out_zip with the picked takes (e.g. narrator_003_b2) in place of the clips."""
    with zipfile.ZipFile(fix_zip) as fix:
        said = json.loads(fix.read("fix/said.json"))
        unknown = [n for n in names if n not in said]
        if unknown:
            raise ValueError(f"not in {fix_zip}: {unknown}; the takes are {sorted(said)[:6]}...")
        picked = {f"voices/{said[n]['speaker']}/{said[n]['line']:03d}.flac": fix.read(f"fix/{n}.flac")
                  for n in names}
    with zipfile.ZipFile(base_zip) as base, zipfile.ZipFile(out_zip, "w", zipfile.ZIP_STORED) as out:
        missing = sorted(set(picked) - set(base.namelist()))
        if missing:
            raise ValueError(f"{base_zip} has no {missing}")
        for name in base.namelist():
            out.writestr(name, picked.get(name) or base.read(name))
    print(f"{len(picked)} clip(s) swapped -> {out_zip}")
    print("To keep these spellings for future recordings, add them to the pronunciation file's \"lines\":")
    for n in names:
        sentence = plain(cfg.lines(said[n]["speaker"])[said[n]["line"]])
        print(f"  {json.dumps(sentence, ensure_ascii=False)}: {json.dumps(said[n]['text'], ensure_ascii=False)},")
