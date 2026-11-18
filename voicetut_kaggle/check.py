"""Step 3: the check notebook. It listens to every recorded line and re-records the bad ones.

For each line, an Egyptian Arabic speech-to-text model (QwenCleo-ASR) writes down what it hears,
and that is compared with the sentence (character error rate, after both are spelled the same
way). A line whose error is above `check.threshold` is recorded again, up to `check.max_takes`
takes in all, and the take that matches best is kept.

QwenCleo-ASR needs an older `transformers` than the voice model, so it and those older libraries
are installed in their own folder (ASR_LIB), put first on the path only for the listening workers;
listening and recording take turns on the GPUs.

Inputs: the dataset and the recording notebooks' outputs (voices.zip). Output: voices_checked.zip
(voices/<speaker>/<nnn>.flac plus report.json). With line numbers (new lines added later), the
notebook records those lines itself first and needs no recordings as input.
"""
from . import notebooks, record

ASR_INSTALL = (
    "# The speech-to-text package needs older libraries than the voice model: its own folder.\n"
    f"!{notebooks.PIP} --no-deps -t /tmp/asrlib qwen-asr==0.0.6 transformers==4.57.6 "
    "accelerate==1.12.0 'huggingface-hub>=0.34,<1.0' 'tokenizers>=0.22,<0.23'\n"
    "# Only its unused forced aligner imports nagisa (which doesn't build on this Python).\n"
    "!echo '# not used' > /tmp/asrlib/nagisa.py"
)

ASR_WORKER = r'''
"""Writes down what is heard in each clip (runs with the speech-to-text libraries first on the path)."""
import json, os, sys, torch
from qwen_asr import Qwen3ASRModel

jobs, out = json.load(open(sys.argv[1])), sys.argv[2]
model = Qwen3ASRModel.from_pretrained("mohammedaly22/QwenCleo-ASR", dtype=torch.float32,
                                      device_map=os.environ.get("DEVICE", "cuda:0"))
heard = {}
for i in range(0, len(jobs), 8):
    batch = jobs[i:i + 8]
    results = model.transcribe(audio=[j["path"] for j in batch], language="Arabic")
    for job, result in zip(batch, results):
        heard[job["path"]] = result.text
    json.dump(heard, open(out, "w"), ensure_ascii=False)
    print(f"heard {len(heard)}/{len(jobs)}", flush=True)
'''

TTS_WORKER = r'''
"""Records new takes of the given lines (a different random start for every take)."""
import json, os, sys, torch
import soundfile as sf
from voices_lib import load_tts, say

jobs = json.load(open(sys.argv[1]))
tts = load_tts()
for i, job in enumerate(jobs):
    torch.manual_seed(job["take"] * 100003 + job["n"])
    wav = say(tts, job["text"], job["speaker"])
    os.makedirs(os.path.dirname(job["path"]), exist_ok=True)
    sf.write(job["path"] + ".part.flac", wav, tts.sampling_rate)
    os.replace(job["path"] + ".part.flac", job["path"])
    print(f"recorded {i + 1}/{len(jobs)}  {job['path']}", flush=True)
'''

CHECK_SETUP = r'''
import re
from voicetut_tts.normalization import ArabicNormalizer

ASR_LIB = os.environ.get("ASR_LIB", "/tmp/asrlib")
OUT, TAKES = f"{WORK}/voices", f"{WORK}/takes"
MAX_TAKES = int(os.environ.get("MAX_TAKES", "%(max_takes)d"))
THRESHOLD = float(os.environ.get("THRESHOLD", "%(threshold)s"))
# None: check the recording notebooks' lines. Otherwise only these line numbers, recorded here first.
LINE_NUMBERS = %(line_numbers)r
SPEAKERS = os.environ["ONLY"].split(",") if os.environ.get("ONLY") else info["order"]
make_refs(SPEAKERS)
recorded = glob.glob(f"{INPUT}/**/voices.zip", recursive=True)
assert recorded or LINE_NUMBERS, "attach the recording notebooks' outputs (voices.zip) as input"
for path in recorded:  # one per recording part
    with zipfile.ZipFile(path) as z:
        z.extractall(WORK)
print("recorded parts:", len(recorded))

# What should be said and what was heard are spelled the same way before comparing: numbers as
# words, no vowel marks or punctuation, and letters that Egyptian speech and spelling mix up merged.
normalizer = ArabicNormalizer()
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "ء", "ئ": "ء",
                      "ث": "ت", "ذ": "د", "ظ": "ض", "ـ": None})


def spelled(text):
    text = normalizer.normalize(text)
    text = re.sub(r"[ً-ْٰ]", "", text).translate(FOLD)
    return re.sub(r"[^ء-يa-zA-Z]", "", text)


def letter_errors(want, got):
    """Character error rate: edits needed to turn got into want, per letter of want."""
    a, b = spelled(want), spelled(got)
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1] / max(len(a), 1)


LINES = {}  # "speaker/000" -> the line
for speaker in SPEAKERS:
    sentences = json.load(open(f"{DATA}/sentences/{speaker}.json"))
    for n, text in enumerate(sentences):
        if LINE_NUMBERS is None or n in LINE_NUMBERS:
            LINES[f"{speaker}/{n:03d}"] = {"speaker": speaker, "n": n, "text": text}
first = {key: f"{OUT}/{key}.flac" for key in LINES if os.path.exists(f"{OUT}/{key}.flac")}
print(f"{len(LINES)} lines, {len(first)} recorded already")


def on_all_gpus(script, jobs, tag, path=None):
    """Runs a worker per GPU on its share of the jobs; returns the merged results (if any)."""
    open(f"{WORK}/{tag}.py", "w").write(script)
    runs = []
    for g in range(GPUS):
        share = jobs[g::GPUS]
        if not share:
            continue
        jobs_file, out_file, log = f"{WORK}/{tag}_jobs{g}.json", f"{WORK}/{tag}_out{g}.json", f"{WORK}/{tag}_{g}.log"
        json.dump(share, open(jobs_file, "w"), ensure_ascii=False)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g))
        if path:
            env["PYTHONPATH"] = path
        runs.append((subprocess.Popen([sys.executable, f"{WORK}/{tag}.py", jobs_file, out_file], env=env,
                                      stdout=open(log, "w"), stderr=subprocess.STDOUT), out_file, log))
    merged = {}
    for proc, out_file, log in runs:
        if proc.wait() != 0:
            print("".join(open(log).readlines()[-15:]))
            raise RuntimeError(f"{tag} worker failed (log above)")
        if os.path.exists(out_file):
            merged.update(json.load(open(out_file)))
    return merged
'''

CHECK = r'''
# Check, re-record what doesn't match, check the new takes, and so on, up to MAX_TAKES per line.
takes = {key: ([first[key]] if key in first else []) for key in LINES}
heard, errors = {}, {}
to_check = list(first.values())
started = time.time()
for attempt in range(1, MAX_TAKES + 1):
    if to_check:
        print(f"listening to {len(to_check)} clips...", flush=True)
        heard.update(on_all_gpus(ASR_WORKER, [{"path": p} for p in to_check], f"asr{attempt}", path=ASR_LIB))
    path_key = {p: k for k, ps in takes.items() for p in ps}
    for path in to_check:
        errors[path] = letter_errors(LINES[path_key[path]]["text"], heard.get(path, ""))
    best = {k: min(ps, key=errors.get) if ps else None for k, ps in takes.items()}
    bad = [k for k, p in best.items() if p is None or errors[p] > THRESHOLD]
    print(f"after {attempt} take(s): {len(LINES) - len(bad)}/{len(LINES)} lines match "
          f"({(time.time() - started) / 60:.0f} min)", flush=True)
    if not bad or attempt == MAX_TAKES:
        break
    jobs = []
    for key in bad:
        take = len(takes[key]) + 1
        path = f"{TAKES}/{key}_t{take}.flac"
        takes[key].append(path)
        jobs.append({**LINES[key], "take": take, "path": path})
    print(f"recording {len(jobs)} lines again...", flush=True)
    on_all_gpus(TTS_WORKER, jobs, f"tts{attempt}")
    to_check = [j["path"] for j in jobs if os.path.exists(j["path"])]
'''

PACK = r'''
# Keep the best take of each line, in the same layout as the recordings: voices/<speaker>/<nnn>.flac
report, final = {}, f"{WORK}/checked"
for key, line in LINES.items():
    path = best[key]
    if path is None:
        continue
    os.makedirs(os.path.dirname(f"{final}/voices/{key}.flac"), exist_ok=True)
    shutil.copy(path, f"{final}/voices/{key}.flac")
    report[key] = {"text": line["text"], "heard": heard.get(path, ""), "errors": round(errors[path], 3),
                   "take": takes[key].index(path) + 1, "takes": len(takes[key])}
json.dump(report, open(f"{WORK}/report.json", "w"), ensure_ascii=False, indent=1)
with zipfile.ZipFile(f"{WORK}/voices_checked.zip", "w", zipfile.ZIP_STORED) as z:
    for path in sorted(glob.glob(f"{final}/voices/*/*.flac")):
        z.write(path, os.path.relpath(path, final))
    z.write(f"{WORK}/report.json", "report.json")
still_bad = sorted((r["errors"], k) for k, r in report.items() if r["errors"] > THRESHOLD)
redone = sum(r["take"] > 1 for r in report.values())
print(f"{len(report)} lines kept; {redone} replaced by a better take; {len(still_bad)} still don't match")
for err, key in still_bad[-40:]:
    print(f"  {key}  {err:.0%}  wanted: {report[key]['text']}  heard: {report[key]['heard']}")
'''

INTRO = """# {project}: {what}

Listens to every line with QwenCleo-ASR (Egyptian Arabic speech-to-text), compares it with the
sentence it should say, records again the lines that don't match (up to {takes} takes) and keeps
the best. Needs the **{dataset}** dataset{inputs} as input, **GPU T4 x2** and **Internet on**.
Output: **voices_checked.zip** and **report.json**.
"""


def build(cfg, line_numbers=None):
    """[line_numbers]: record and check only these lines (added later), in their own notebook."""
    # New lines get their first take in this notebook too, so one more round.
    max_takes = cfg.check["max_takes"] + (1 if line_numbers else 0)
    values = {"threshold": cfg.check["threshold"], "max_takes": max_takes, "line_numbers": line_numbers}
    intro = INTRO.format(
        project=cfg.project, takes=max_takes, dataset=cfg.ref(cfg.dataset_slug),
        what=f"record and check lines {line_numbers[0]}-{line_numbers[-1]}" if line_numbers else "check",
        inputs="" if line_numbers else " and the recording notebooks' outputs")
    cells = [
        notebooks.cell("markdown", intro),
        notebooks.cell("code", notebooks.INSTALL + "\n" + ASR_INSTALL),
        notebooks.cell("code", notebooks.embedded_code(cfg, ASR_WORKER=ASR_WORKER, TTS_WORKER=TTS_WORKER)),
        notebooks.cell("code", notebooks.setup_code(cfg) + "\n" + CHECK_SETUP % values),
        notebooks.cell("code", CHECK.strip()),
        notebooks.cell("code", PACK.strip()),
    ]
    if line_numbers:
        return notebooks.write(cfg, "new-lines", cells)
    sources = [cfg.ref(cfg.kernel_slug(name)) for name in record.part_names(cfg)]
    return notebooks.write(cfg, "check", cells, kernel_sources=sources)


def check_line_numbers(cfg, first, last):
    """The line numbers first..last, if every speaker has them."""
    if first < 0 or last < first:
        raise ValueError(f"{first}-{last} is not a line range (FIRST-LAST, e.g. 12-15)")
    short = [i for i in cfg.speaker_ids() if len(cfg.lines(i)) <= last]
    if short:
        raise ValueError(f"speaker(s) {short} have no line {last}: add the new sentences first")
    return list(range(first, last + 1))
