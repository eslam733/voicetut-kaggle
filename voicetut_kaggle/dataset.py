"""Step 1: the Kaggle dataset the notebooks read (sentences, voice clips, speaker list).

Layout of build/kaggle/data/:
  speakers.json             {"version": ..., "order": [ids], "speakers": {id: {...voice...}}}
  sentences/<id>.json       line n of that speaker (shared sentences first, then their own)
  clips/<id>.<ext>          reference clips (clip speakers only)
  dataset-metadata.json     what the Kaggle CLI needs to upload it
"""
import hashlib
import json
import os
import shutil

from . import kaggle


def speaker_entries(cfg):
    """What the notebooks need to know about each speaker's voice."""
    entries = {}
    for s in cfg.speakers:
        if s.mode == "clip":
            ext = os.path.splitext(s.value)[1].lower()
            entries[s.id] = {"clip": f"clips/{s.id}{ext}", "transcript": s.transcript}
        else:
            entries[s.id] = {s.mode: s.value}
    return entries


def fingerprint(cfg):
    """Changes whenever the dataset content changes, so a notebook can tell it got an old version."""
    digest = hashlib.sha256()
    content = {"speakers": speaker_entries(cfg), "lines": {i: cfg.lines(i) for i in cfg.speaker_ids()}}
    digest.update(json.dumps(content, ensure_ascii=False, sort_keys=True).encode())
    for s in cfg.speakers:
        if s.mode == "clip":
            with open(s.value, "rb") as f:
                digest.update(f.read())
    return digest.hexdigest()[:12]


def folder(cfg):
    return os.path.join(cfg.build, "kaggle", "data")


def write(cfg):
    target = folder(cfg)
    shutil.rmtree(target, ignore_errors=True)
    os.makedirs(os.path.join(target, "sentences"))
    entries = speaker_entries(cfg)
    for s in cfg.speakers:
        _write_json(os.path.join(target, "sentences", f"{s.id}.json"), cfg.lines(s.id))
        if s.mode == "clip":
            os.makedirs(os.path.join(target, "clips"), exist_ok=True)
            shutil.copy(s.value, os.path.join(target, entries[s.id]["clip"]))
    _write_json(os.path.join(target, "speakers.json"),
                {"version": fingerprint(cfg), "order": cfg.speaker_ids(), "speakers": entries})
    _write_json(os.path.join(target, "dataset-metadata.json"),
                {"title": cfg.dataset_slug, "id": cfg.ref(cfg.dataset_slug), "licenses": [{"name": "other"}]})
    lines = sum(len(cfg.lines(i)) for i in cfg.speaker_ids())
    print(f"wrote {target}: {len(entries)} speakers, {lines} lines in all")
    return target


def upload(cfg, message):
    """Creates the private dataset the first time, then adds a new version; waits until it is ready."""
    target = folder(cfg)
    ref = cfg.ref(cfg.dataset_slug)
    if kaggle.dataset_exists(ref):
        kaggle.run("datasets", "version", "-p", target, "-r", "zip", "-m", message)
    else:
        kaggle.run("datasets", "create", "-p", target, "-r", "zip")
    kaggle.wait_for_dataset(ref)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
