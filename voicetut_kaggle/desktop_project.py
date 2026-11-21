"""The desktop form, saved as the same voices.yaml and sentences.json the vk command reads."""
import json
import os
import shutil

import yaml

from .config import ConfigError, load

# VoiceTut's built-in voices, as listed in the README.
BUILTIN_VOICES = (
    "Ahmed", "Ali", "Hassan", "Karim", "Mahmoud", "Mohammed", "Mostafa",
    "Ramy", "Shaker", "Tareq", "Yehia", "Youssef",
    "Hadeer", "Hanan", "Mariam", "Rana", "Sarah", "Yasmin", "Yara",
)

SENTENCES_FILE = "sentences.json"


class SpeakerDraft:
    """One speaker on the form. mode is builtin, clip, or instruct."""

    def __init__(self, speaker_id, mode, value, transcript=""):
        self.id = speaker_id.strip()
        self.mode = mode
        self.value = value.strip()
        self.transcript = transcript.strip()


class ProjectDraft:
    """What the window is editing. sentences are the shared lines, one string each."""

    def __init__(self, folder, project, username, speakers, sentences, own=None):
        self.folder = os.path.abspath(folder)
        self.project = project.strip()
        self.username = username.strip()
        self.speakers = list(speakers)
        self.sentences = [line.strip() for line in sentences if line.strip()]
        # Lines said only by one speaker. The window does not edit these; saving keeps them.
        self.own = {speaker_id: tuple(lines) for speaker_id, lines in (own or {}).items()}


def write_project(draft):
    """Writes the project files and returns the loaded config, which re-checks them."""
    if draft.username == "your-kaggle-username":
        raise ConfigError("voices.yaml: replace your-kaggle-username with your Kaggle username")
    if not draft.speakers:
        raise ConfigError("voices.yaml: add at least one speaker")
    if not draft.sentences:
        raise ConfigError("sentences file has no sentences")
    os.makedirs(draft.folder, exist_ok=True)
    speakers = [_speaker_entry(draft.folder, speaker) for speaker in draft.speakers]
    kept = {speaker.id for speaker in draft.speakers}
    own = {speaker_id: list(lines) for speaker_id, lines in draft.own.items() if speaker_id in kept and lines}
    sentences = {"shared": draft.sentences}
    if own:
        sentences["per_speaker"] = own
    path = os.path.join(draft.folder, "voices.yaml")
    # The form edits only these keys. Every other setting (pronunciation, recording, check,
    # export, ...) stays as it is in the file. YAML comments are not kept.
    document = _existing_document(path)
    document["project"] = draft.project
    document["kaggle"] = {**(document.get("kaggle") or {}), "username": draft.username}
    document["speakers"] = speakers
    document["sentences"] = document.get("sentences") or SENTENCES_FILE
    with open(os.path.join(draft.folder, document["sentences"]), "w", encoding="utf-8") as f:
        json.dump(sentences, f, ensure_ascii=False, indent=1)
        f.write("\n")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(document, f, allow_unicode=True, sort_keys=False)
    return load(path)


def _existing_document(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        document = yaml.safe_load(f) or {}
    if not isinstance(document, dict):
        raise ConfigError(f"{path} is not a YAML mapping; fix or remove it before saving")
    return document


def read_project(folder):
    """Reads a project folder back into a draft. Clip paths are relative to the folder."""
    cfg = load(os.path.join(folder, "voices.yaml"))
    speakers = []
    for speaker in cfg.speakers:
        value = speaker.value
        if speaker.mode == "clip":
            value = os.path.relpath(speaker.value, cfg.folder).replace(os.sep, "/")
        speakers.append(SpeakerDraft(speaker.id, speaker.mode, value, speaker.transcript))
    return ProjectDraft(cfg.folder, cfg.project, cfg.username, speakers, cfg.shared, cfg.own)


def _speaker_entry(folder, speaker):
    if not speaker.id:
        raise ConfigError("voices.yaml: a speaker is missing an id")
    if speaker.mode == "builtin":
        return {"id": speaker.id, "builtin": speaker.value}
    if speaker.mode == "instruct":
        return {"id": speaker.id, "instruct": speaker.value}
    if speaker.mode != "clip":
        raise ConfigError(f"speaker '{speaker.id}': choose a built-in voice or a clip")
    if not speaker.transcript:
        raise ConfigError(f"speaker '{speaker.id}': 'transcript' (the words said in the clip) is missing")
    return {"id": speaker.id, "clip": _store_clip(folder, speaker), "transcript": speaker.transcript}


def _store_clip(folder, speaker):
    """Keeps a clip inside the project folder and returns its path relative to voices.yaml."""
    source = speaker.value
    if not os.path.isabs(source):
        source = os.path.join(folder, source)
    if not os.path.isfile(source):
        raise ConfigError(f"speaker '{speaker.id}': clip {source} not found")
    source = os.path.abspath(source)
    try:
        inside = os.path.commonpath([folder, source]) == folder
    except ValueError:
        inside = False
    if inside:
        return os.path.relpath(source, folder).replace(os.sep, "/")
    ext = os.path.splitext(source)[1].lower() or ".ogg"
    relative = f"clips/{speaker.id}{ext}"
    dest = os.path.join(folder, "clips", f"{speaker.id}{ext}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(source, dest)
    return relative
