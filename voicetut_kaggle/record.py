"""Step 2: the recording notebooks. Speakers are split over `recording.parts` notebooks, which run
at the same time on Kaggle (each gets its own two T4 GPUs; Kaggle allows two sessions at once).

Each notebook records its speakers' lines, one recorder per GPU, and packs them into voices.zip
(voices/<speaker>/<nnn>.flac). If a run hits the time limit, attach its output as input and run it
again: it keeps the lines already recorded and carries on.
"""
from . import notebooks

WORKER = r'''
"""Records every line of the speakers named on the command line, on one GPU."""
import json, os, sys, time
import soundfile as sf
from voices_lib import DATA, load_tts, say

OUT, DEADLINE = os.environ["OUT"], float(os.environ["DEADLINE"])
tts = load_tts()
for speaker in sys.argv[1:]:
    sentences = json.load(open(f"{DATA}/sentences/{speaker}.json"))
    os.makedirs(f"{OUT}/{speaker}", exist_ok=True)
    for n, text in enumerate(sentences):
        target = f"{OUT}/{speaker}/{n:03d}.flac"
        if os.path.exists(target):
            continue
        if time.time() > DEADLINE:
            print("time is up: stopping so the results can be packed", flush=True)
            sys.exit(0)
        started = time.time()
        wav = say(tts, text, speaker)
        sf.write(target + ".part.flac", wav, tts.sampling_rate)
        os.replace(target + ".part.flac", target)  # a file only appears once it is whole
        print(f"{speaker} {n:03d} {time.time() - started:5.1f}s  {text}", flush=True)
print("done", flush=True)
'''

PART_SETUP = r'''
OUT = f"{WORK}/voices"
DEADLINE = time.time() + float(os.environ.get("HOURS", "%(hours)s")) * 3600
SPEAKERS = info["order"][%(part)d::%(parts)d]  # this notebook's share of the speakers
make_refs(SPEAKERS)

# Carry on from an earlier run: if a voices.zip from one is attached as input, keep its lines.
os.makedirs(OUT, exist_ok=True)
for earlier in glob.glob(f"{INPUT}/**/voices.zip", recursive=True):
    with zipfile.ZipFile(earlier) as z:
        z.extractall(WORK)
    print("kept the lines from", earlier)
total = sum(len(json.load(open(f"{DATA}/sentences/{s}.json"))) for s in SPEAKERS)
print(f"{len(SPEAKERS)} speakers, {total} lines, {len(glob.glob(f'{OUT}/*/*.flac'))} already recorded")
'''

RUN = r'''
# One recorder per GPU (Kaggle's "GPU T4 x2" has two), each with its share of the speakers.
open(f"{WORK}/worker.py", "w").write(WORKER)
recorders = []
for g in range(min(GPUS, len(SPEAKERS))):
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g), OUT=OUT, DEADLINE=str(DEADLINE))
    log = open(f"{WORK}/recorder{g}.log", "w")
    recorders.append(subprocess.Popen([sys.executable, f"{WORK}/worker.py", *SPEAKERS[g::GPUS]],
                                      env=env, stdout=log, stderr=subprocess.STDOUT))
print(f"recording on {len(recorders)} GPU(s), {NUM_STEP} steps")

started, before = time.time(), len(glob.glob(f"{OUT}/*/*.flac"))
while any(r.poll() is None for r in recorders):
    time.sleep(int(os.environ.get("REPORT_EVERY", "300")))
    done = len(glob.glob(f"{OUT}/*/*.flac"))
    rate = (done - before) / max(time.time() - started, 1)
    left = (total - done) / rate / 3600 if rate else float("nan")
    print(f"{time.strftime('%H:%M')}  {done}/{total} lines, about {left:.1f} h left", flush=True)
for g, r in enumerate(recorders):
    print(f"recorder {g} finished with code {r.returncode}; last lines of its log:")
    print("".join(open(f"{WORK}/recorder{g}.log").readlines()[-3:]))
'''

PACK = r'''
# Pack every finished line into voices.zip (it appears in the notebook's Output).
done = sorted(glob.glob(f"{OUT}/*/*.flac"))
with zipfile.ZipFile(f"{WORK}/voices.zip", "w", zipfile.ZIP_STORED) as z:
    for path in done:
        z.write(path, os.path.relpath(path, WORK))
for speaker in SPEAKERS:
    want = len(json.load(open(f"{DATA}/sentences/{speaker}.json")))
    have = len(glob.glob(f"{OUT}/{speaker}/*.flac"))
    print(f"{speaker:12s} {have:4d}/{want}" + ("" if have == want else "  <- not finished"))
print(f"voices.zip: {len(done)}/{total} lines, {os.path.getsize(f'{WORK}/voices.zip') / 1e6:.0f} MB")
if len(done) < total:
    print("Not every line fit in this run: attach this output as input and run the notebook again.")
'''

INTRO = """# {project}: recording, part {part} of {parts}

Records every line of this part's speakers with VoiceTut-TTS. Needs the **{dataset}** dataset
as input, **GPU T4 x2** and **Internet on**. The result is **voices.zip** in the Output.
If a run stops before every line is done, attach its output as input and run again: it carries on.
"""


def part_names(cfg):
    return [f"part{p + 1}" for p in range(cfg.recording["parts"])]


def build(cfg):
    parts = cfg.recording["parts"]
    folders = []
    for part in range(parts):
        values = {"hours": cfg.recording["hours"], "part": part, "parts": parts}
        cells = [
            notebooks.cell("markdown", INTRO.format(project=cfg.project, part=part + 1, parts=parts,
                                                    dataset=cfg.ref(cfg.dataset_slug))),
            notebooks.cell("code", notebooks.INSTALL),
            notebooks.cell("code", notebooks.embedded_code(cfg, WORKER=WORKER)),
            notebooks.cell("code", notebooks.setup_code(cfg) + "\n" + PART_SETUP % values),
            notebooks.cell("code", RUN.strip()),
            notebooks.cell("code", PACK.strip()),
        ]
        folders.append(notebooks.write(cfg, f"part{part + 1}", cells))
    return folders
