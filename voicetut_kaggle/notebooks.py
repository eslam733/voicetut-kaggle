"""What every generated Kaggle notebook shares: install, setup, the voice helper, file writing.

Kaggle notebooks must be under 1 MB, so the sentences and voice clips live in a private Kaggle
dataset (see dataset.py); the notebook carries the code and the pronunciation file.
"""
import json
import os

from . import dataset

# The voice model and its engine, pinned to the versions this pipeline was tested with.
OMNIVOICE = "git+https://github.com/k2-fsa/OmniVoice.git@08be0b4ccbac3e13e374e86fbfead4b4cac343e2"
VOICETUT = "voicetut-tts==0.1.1"
PIP = "pip install -q --timeout 60 --retries 10"  # Kaggle's PyPI mirror times out now and then
INSTALL = f'!nvidia-smi -L\n!{PIP} "{OMNIVOICE}" {VOICETUT}'

VOICE_LIB = r'''
"""Used by the notebook's workers: loads VoiceTut and says a line in a speaker's voice."""
import json, os
from pronounce import prepare  # saved next to this file

DATA = os.environ["DATA"]
SPEAKERS = json.load(open(f"{DATA}/speakers.json"))["speakers"]
PRONUNCIATION = json.load(open(f"{DATA}/pronunciation.json"))


def load_tts():
    from voicetut_tts import VoiceTutTTS
    return VoiceTutTTS.from_pretrained("mohammedaly22/VoiceTut-TTS",
                                       device=os.environ.get("DEVICE", "cuda"), dtype="float32")


def voice(speaker):
    """VoiceTut's voice arguments: a reference clip, a built-in speaker, or a voice description."""
    s = SPEAKERS[speaker]
    if "clip" in s:
        return {"ref_audio": f"{DATA}/refs/{speaker}.wav", "ref_text": s["transcript"]}
    if "builtin" in s:
        return {"speaker": s["builtin"]}
    return {"instruct": s["instruct"]}


def say(tts, text, speaker, exact=False):
    """The waveform of [text]; [exact]: use the spelling as given, skipping the pronunciation file."""
    spoken = text if exact else prepare(text, tts.normalizer, PRONUNCIATION)
    return tts.synthesize(spoken, num_step=int(os.environ["NUM_STEP"]), normalize=False, **voice(speaker))
'''

SETUP = r'''
import glob, json, os, shutil, subprocess, sys, time, zipfile

WORK = os.environ.get("WORK", "/kaggle/working")
INPUT = os.environ.get("INPUT", "/kaggle/input")
DATA = f"{WORK}/data"
NUM_STEP = int(os.environ.get("NUM_STEP", "%(num_step)d"))

# The sentences and voice clips come from the attached dataset.
found = glob.glob(f"{INPUT}/**/speakers.json", recursive=True)
assert found, "add the %(dataset)s dataset as input"
shutil.copytree(os.path.dirname(found[0]), DATA, dirs_exist_ok=True)
info = json.load(open(f"{DATA}/speakers.json"))
assert info.get("version") == "%(version)s", (
    "This notebook got an older version of the %(dataset)s dataset than it was built for. "
    "Wait until `kaggle datasets status %(dataset)s` says ready, then run the notebook again.")
open(f"{WORK}/pronounce.py", "w").write(PRONOUNCE)
open(f"{WORK}/voices_lib.py", "w").write(VOICE_LIB)
json.dump(PRONUNCIATION, open(f"{DATA}/pronunciation.json", "w"), ensure_ascii=False)
sys.path.insert(0, WORK)
os.environ.update(DATA=DATA, NUM_STEP=str(NUM_STEP))
GPUS = max(int(os.environ.get("GPUS") or len(subprocess.run(
    ["nvidia-smi", "-L"], capture_output=True, text=True).stdout.strip().splitlines())), 1)


def make_refs(speakers):
    """Reference clips as VoiceTut wants them: mono, 24 kHz WAV."""
    os.makedirs(f"{DATA}/refs", exist_ok=True)
    for speaker in speakers:
        clip = info["speakers"][speaker].get("clip")
        if clip:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", f"{DATA}/{clip}",
                            "-ac", "1", "-ar", "24000", f"{DATA}/refs/{speaker}.wav"], check=True)
'''


def embedded_code(cfg, **scripts):
    """Notebook code defining PRONOUNCE, VOICE_LIB, PRONUNCIATION and the given worker scripts."""
    pronounce = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pronounce.py")
    with open(pronounce, encoding="utf-8") as f:
        sources = {"PRONOUNCE": f.read(), "VOICE_LIB": VOICE_LIB, **scripts}
    lines = [f"{name} = {source!r}" for name, source in sources.items()]
    lines.append(f"PRONUNCIATION = {cfg.pronunciation!r}")
    return "\n".join(lines)


def setup_code(cfg):
    return SETUP.strip() % {"num_step": cfg.recording["num_step"], "dataset": cfg.ref(cfg.dataset_slug),
                            "version": dataset.fingerprint(cfg)}


def cell(kind, source):
    c = {"cell_type": kind, "metadata": {}, "source": source}
    if kind == "code":
        c.update(execution_count=None, outputs=[])
    return c


def write(cfg, name, cells, kernel_sources=()):
    """Writes build/kaggle/<name>/ with the notebook and its kernel-metadata.json; returns the folder."""
    slug = cfg.kernel_slug(name)
    folder = os.path.join(cfg.build, "kaggle", name)
    os.makedirs(folder, exist_ok=True)
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                     "language_info": {"name": "python"}},
        "cells": cells,
    }
    with open(os.path.join(folder, f"{slug}.ipynb"), "w", encoding="utf-8") as f:
        json.dump(notebook, f, ensure_ascii=False, indent=1)
    metadata = {
        "id": cfg.ref(slug),
        "title": slug,  # Kaggle makes the slug from the title, so they must match
        "code_file": f"{slug}.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_tpu": "false",
        "enable_internet": "true",
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [cfg.ref(cfg.dataset_slug)],
        "competition_sources": [],
        "kernel_sources": list(kernel_sources),
        "model_sources": [],
    }
    with open(os.path.join(folder, "kernel-metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)
    size_kb = os.path.getsize(os.path.join(folder, f"{slug}.ipynb")) / 1e3
    if size_kb > 950:
        raise RuntimeError(f"{slug}.ipynb is {size_kb:.0f} KB; Kaggle refuses notebooks over 1 MB "
                           "(the pronunciation file is embedded in it: is it very large?)")
    print(f"wrote {folder} ({size_kb:.0f} KB)")
    return folder
