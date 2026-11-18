"""Loads and checks voices.yaml: the one file that describes a voice project.

Every path in the file is relative to the file itself. Generated notebooks and downloads go in
<config folder>/build/, which is safe to delete.
"""
import json
import os
import re
from dataclasses import dataclass

import yaml

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,40}$")
SPEAKER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
BITRATE = re.compile(r"^\d{1,3}k$")
VOICE_MODES = ("clip", "builtin", "instruct")
AUDIO_FORMATS = ("webm", "ogg")

DEFAULTS = {
    "recording": {"parts": 1, "num_step": 48, "hours": 11},
    "check": {"threshold": 0.15, "max_takes": 4},
    "export": {"bitrate": "20k", "format": "webm"},
}
TOP_KEYS = {"project", "kaggle", "speakers", "sentences", "pronunciation", *DEFAULTS}


class ConfigError(ValueError):
    """voices.yaml (or a file it points to) is missing something or has a wrong value."""


@dataclass(frozen=True)
class Speaker:
    id: str
    mode: str  # one of VOICE_MODES
    value: str  # clip path, built-in speaker name, or voice description
    transcript: str = ""  # what is said in the clip (clip mode only)


@dataclass(frozen=True)
class Config:
    folder: str
    project: str
    username: str
    speakers: tuple
    shared: tuple  # sentences every speaker says, first
    own: dict  # speaker id -> tuple of sentences only that speaker says, after the shared ones
    pronunciation: dict
    recording: dict
    check: dict
    export: dict

    @property
    def build(self):
        return os.path.join(self.folder, "build")

    @property
    def dataset_slug(self):
        return f"{self.project}-data"

    def kernel_slug(self, name):
        """Kaggle notebook slug, e.g. kernel_slug("part1") -> "my-voices-part1"."""
        return f"{self.project}-{name}"

    def ref(self, slug):
        return f"{self.username}/{slug}"

    def lines(self, speaker_id):
        """Line n of a speaker: the shared sentences, then their own ones."""
        return list(self.shared) + list(self.own.get(speaker_id, ()))

    def speaker_ids(self):
        return [s.id for s in self.speakers]


def load(path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise ConfigError(f"{path} not found: pass the path of your voices.yaml with --config")
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    folder = os.path.dirname(path)
    _no_unknown_keys(raw, TOP_KEYS, "voices.yaml")
    speakers = _speakers(raw.get("speakers"), folder)
    ids = [s.id for s in speakers]
    shared, own = _sentences(_required(raw, "sentences"), folder, ids)
    sections = {name: _section(raw, name) for name in DEFAULTS}
    _check_numbers(sections, len(speakers))
    return Config(
        folder=folder,
        project=_matching(raw, "project", SLUG, "lowercase letters, digits and dashes, 3-41 long"),
        username=_matching(raw.get("kaggle") or {}, "username", USERNAME, "your Kaggle username"),
        speakers=tuple(speakers),
        shared=tuple(shared),
        own=own,
        pronunciation=_pronunciation(raw.get("pronunciation"), folder),
        **sections,
    )


def _required(raw, key):
    if raw.get(key) in (None, ""):
        raise ConfigError(f"voices.yaml: '{key}' is missing")
    return raw[key]


def _matching(raw, key, pattern, hint):
    value = str(_required(raw, key))
    if not pattern.match(value):
        raise ConfigError(f"voices.yaml: '{key}: {value}' is not valid ({hint})")
    return value


def _no_unknown_keys(raw, allowed, where):
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: expected a mapping (key: value lines)")
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {unknown}; allowed: {sorted(allowed)}")


def _speakers(raw, folder):
    if not isinstance(raw, list) or not raw:
        raise ConfigError("voices.yaml: 'speakers' must be a list with at least one speaker")
    speakers = [_speaker(entry, folder) for entry in raw]
    ids = [s.id for s in speakers]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ConfigError(f"voices.yaml: speaker id(s) used twice: {duplicates}")
    return speakers


def _speaker(entry, folder):
    _no_unknown_keys(entry, {"id", *VOICE_MODES, "transcript"}, "a speaker in voices.yaml")
    speaker_id = _matching(entry, "id", SPEAKER_ID, "lowercase letters, digits, - and _")
    modes = [m for m in VOICE_MODES if entry.get(m)]
    if len(modes) != 1:
        raise ConfigError(f"speaker '{speaker_id}': give exactly one of {list(VOICE_MODES)}")
    mode, value = modes[0], str(entry[modes[0]])
    if mode != "clip":
        return Speaker(speaker_id, mode, value)
    clip = os.path.join(folder, value)
    if not os.path.isfile(clip):
        raise ConfigError(f"speaker '{speaker_id}': clip {clip} not found")
    transcript = str(entry.get("transcript") or "").strip()
    if not transcript:
        raise ConfigError(f"speaker '{speaker_id}': 'transcript' (the words said in the clip) is missing")
    return Speaker(speaker_id, mode, clip, transcript)


def _read_json(folder, relative, what):
    path = os.path.join(folder, relative)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"{what} file {path} not found") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"{what} file {path} is not valid JSON: {e}") from None


def _sentences(relative, folder, speaker_ids):
    """A JSON list (every speaker says the same lines) or {"shared": [...], "per_speaker": {...}}."""
    data = _read_json(folder, relative, "sentences")
    if isinstance(data, list):
        data = {"shared": data}
    _no_unknown_keys(data, {"shared", "per_speaker"}, "sentences file")
    shared = [_text(item) for item in data.get("shared", [])]
    own = {k: tuple(_text(item) for item in v) for k, v in (data.get("per_speaker") or {}).items()}
    strangers = sorted(set(own) - set(speaker_ids))
    if strangers:
        raise ConfigError(f"sentences file: per_speaker has unknown speaker id(s) {strangers}")
    if not shared and not any(own.values()):
        raise ConfigError("sentences file has no sentences")
    return shared, own


def _text(item):
    text = item.get("text") if isinstance(item, dict) else item
    if not isinstance(text, str) or not text.strip():
        raise ConfigError(f"sentences file: {item!r} is not a sentence (a non-empty string)")
    return text.strip()


def _pronunciation(relative, folder):
    if not relative:
        return {}
    data = _read_json(folder, relative, "pronunciation")
    _no_unknown_keys(data, {"about", "words", "phrases", "lines"}, "pronunciation file")
    return {key: data.get(key) or {} for key in ("words", "phrases", "lines")}


def _section(raw, name):
    given = raw.get(name) or {}
    _no_unknown_keys(given, DEFAULTS[name], f"voices.yaml '{name}'")
    return {**DEFAULTS[name], **given}


def _check_numbers(sections, speaker_count):
    rec, check, export = sections["recording"], sections["check"], sections["export"]
    rules = [
        (isinstance(rec["parts"], int) and 1 <= rec["parts"] <= speaker_count,
         f"recording.parts must be 1..{speaker_count} (one notebook needs at least one speaker)"),
        (isinstance(rec["num_step"], int) and 4 <= rec["num_step"] <= 128, "recording.num_step must be 4..128"),
        (isinstance(rec["hours"], (int, float)) and 0.5 <= rec["hours"] <= 11.5,
         "recording.hours must be 0.5..11.5 (Kaggle stops a run at 12 hours)"),
        (isinstance(check["threshold"], (int, float)) and 0 < check["threshold"] < 1,
         "check.threshold must be between 0 and 1 (0.15 = 15% of letters may differ)"),
        (isinstance(check["max_takes"], int) and 1 <= check["max_takes"] <= 10, "check.max_takes must be 1..10"),
        (BITRATE.match(str(export["bitrate"])), "export.bitrate must look like 20k"),
        (export["format"] in AUDIO_FORMATS, f"export.format must be one of {list(AUDIO_FORMATS)}"),
    ]
    for ok, message in rules:
        if not ok:
            raise ConfigError(f"voices.yaml: {message}")
