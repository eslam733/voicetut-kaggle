"""The small calls the desktop window needs as data. Each prints one JSON object on stdout.

    python -m voicetut_kaggle.desktop_api open FOLDER
    python -m voicetut_kaggle.desktop_api status FOLDER
    python -m voicetut_kaggle.desktop_api save            < draft.json
    python -m voicetut_kaggle.desktop_api token [--copy FILE | --set < token]
    python -m voicetut_kaggle.desktop_api fix-save FOLDER < lines.json
    python -m voicetut_kaggle.desktop_api takes FOLDER
    python -m voicetut_kaggle.desktop_api use-takes FOLDER TAKE...

The long steps (upload, record, watch, fetch, listen, export) are the `vk` commands themselves;
the window runs them and shows their output.
"""
import argparse
import contextlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

import yaml

from . import config, dataset, fix, kaggle, record, watch
from .desktop_project import BUILTIN_VOICES, ProjectDraft, SpeakerDraft, read_project, write_project

KAGGLE_DIR = os.path.expanduser("~/.kaggle")
MAX_TOKEN_FILE = 4096  # bytes; a Kaggle token or kaggle.json is far smaller
MIN_TOKEN = 16  # characters; anything shorter was not copied whole
# Where the window keeps the fix step's files, inside the project's build folder.
CHECKED = ("out", "check", "voices_checked.zip")
BEFORE_FIXES = ("out", "check", "voices_checked.before-fixes.zip")
FIX_ZIP = ("out", "fix", "fix.zip")
FIXES = ("fixes.yaml",)


def cmd_open(args):
    folder = os.path.abspath(os.path.expanduser(args.folder))
    answer = {"ok": True, "folder": folder, "project": None, "run": None, "builtin_voices": BUILTIN_VOICES}
    if not os.path.isfile(os.path.join(folder, "voices.yaml")):
        return answer
    try:
        draft = read_project(folder)
        cfg = config.load(os.path.join(folder, "voices.yaml"))
    except config.ConfigError as e:
        answer["problem"] = str(e)
        return answer
    answer["project"] = _draft_to_json(draft)
    state = watch.read_state(cfg)
    answer["run"] = {
        "parts": record.part_names(cfg),
        "pushed": state["pushed"],
        "check_pushed": state["check_pushed"],
        "unfinished": bool(state["pushed"]) and not state["check_pushed"],
    }
    # False also when this computer never uploaded it: the window uploads before recording.
    answer["dataset_current"] = dataset.uploaded_version(cfg) == dataset.fingerprint(cfg)
    return answer


def cmd_status(args):
    """Kaggle's status of each notebook this run pushed: QUEUED, RUNNING, COMPLETE, ERROR, ..."""
    cfg = config.load(os.path.join(os.path.abspath(os.path.expanduser(args.folder)), "voices.yaml"))
    state = watch.read_state(cfg)
    names = [name for name in record.part_names(cfg) if name in state["pushed"]]
    if state["check_pushed"]:
        names.append("check")
    statuses = {name: kaggle.kernel_status(cfg.ref(cfg.kernel_slug(name))) for name in names}
    if os.path.isfile(os.path.join(cfg.build, "kaggle", "fix", "kernel-metadata.json")):
        status = kaggle.kernel_status(cfg.ref(cfg.kernel_slug("fix")))
        if status != "NONE":  # built but never started: nothing to show
            statuses["fix"] = status
    return {"ok": True, "notebooks": statuses}


def cmd_fix_save(args):
    """Writes the lines to re-record (from the window) as a fixes file and checks it."""
    cfg = _load(args.folder)
    data = json.load(sys.stdin)
    spec = {"takes": data.get("takes", 2),
            "lines": [{"line": row["line"], "speakers": [row["speaker"]], "spellings": row["spellings"]}
                      for row in data["lines"]]}
    path = _build(cfg, *FIXES)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True, sort_keys=False)
    clips = len(fix.load_jobs(cfg, path))
    return {"ok": True, "path": path, "clips": clips}


def cmd_takes(args):
    """The downloaded takes, grouped by the clip they would replace."""
    cfg = _load(args.folder)
    with zipfile.ZipFile(_build(cfg, *FIX_ZIP)) as z:
        said = json.loads(z.read("fix/said.json"))
    groups = {}
    for name, job in sorted(said.items()):
        key = (job["speaker"], job["line"])
        groups.setdefault(key, []).append({"name": name, "variant": job["variant"], "take": job["take"],
                                           "text": job["text"]})
    return {"ok": True, "clips": [
        {"speaker": speaker, "line": line, "sentence": cfg.lines(speaker)[line], "takes": takes}
        for (speaker, line), takes in groups.items()]}


def cmd_use_takes(args):
    """Puts the picked takes into voices_checked.zip (the original is kept once, the first time)
    and adds their spellings to the pronunciation file, so later recordings say them the same way."""
    cfg = _load(args.folder)
    checked, before = _build(cfg, *CHECKED), _build(cfg, *BEFORE_FIXES)
    if not os.path.exists(before):
        shutil.copyfile(checked, before)
    new = checked + ".new"
    try:
        with contextlib.redirect_stdout(sys.stderr):  # stdout is for the one JSON answer
            lines = fix.use_takes(cfg, _build(cfg, *FIX_ZIP), checked, new, args.takes)
        os.replace(new, checked)
    finally:
        if os.path.exists(new):  # use_takes failed half way: voices_checked.zip is untouched
            os.remove(new)
    pronunciation = _remember_spellings(cfg, lines)
    return {"ok": True, "swapped": len(args.takes), "lines": lines, "pronunciation": pronunciation,
            "backup": before}


def _remember_spellings(cfg, lines):
    """Adds the lines to the project's pronunciation file; None when the project has none."""
    with open(os.path.join(cfg.folder, "voices.yaml"), encoding="utf-8") as f:
        relative = (yaml.safe_load(f) or {}).get("pronunciation")
    if not relative:
        return None
    path = os.path.join(cfg.folder, relative)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("lines", {}).update(lines)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return path


def _load(folder):
    return config.load(os.path.join(os.path.abspath(os.path.expanduser(folder)), "voices.yaml"))


def _build(cfg, *parts):
    return os.path.join(cfg.build, *parts)


def cmd_save(args):
    data = json.load(sys.stdin)
    folder = os.path.abspath(os.path.expanduser(data["folder"]))
    own = data.get("own")
    if own is None and os.path.isfile(os.path.join(folder, "voices.yaml")):
        own = read_project(folder).own  # the window never edits a speaker's own lines
    speakers = [SpeakerDraft(s["id"], s["mode"], s["value"], s.get("transcript", "")) for s in data["speakers"]]
    write_project(ProjectDraft(folder, data["project"], data["username"], speakers, data["sentences"], own))
    return {"ok": True}


def cmd_token(args):
    if args.copy:
        if os.path.getsize(args.copy) > MAX_TOKEN_FILE:
            raise ValueError(f"{args.copy} is too big to be a Kaggle token")
        with open(args.copy, encoding="utf-8") as f:
            _store_token(f.read())
    elif args.set:
        _store_token(sys.stdin.read(MAX_TOKEN_FILE + 1))
    return {"ok": True, "token": kaggle.has_credentials(), "kaggle_cli": _kaggle_cli()}


def _store_token(text):
    """Adds or replaces the token where the Kaggle CLI looks: ~/.kaggle/access_token, or
    kaggle.json for the older username + key file. Readable by this user only."""
    text = text.strip()
    if not text:
        raise ValueError("the token is empty")
    if len(text) > MAX_TOKEN_FILE:
        raise ValueError("that is too long to be a Kaggle token")
    if _is_legacy_key(text):
        name = "kaggle.json"
    elif len(text) < MIN_TOKEN or any(c.isspace() for c in text):
        raise ValueError("that does not look like a Kaggle API token (one word, no spaces); "
                         "copy it again from kaggle.com → Settings → API")
    else:
        name = "access_token"
    os.makedirs(KAGGLE_DIR, mode=0o700, exist_ok=True)
    # Write a new file, then swap it in: an old token is only replaced by a complete new one.
    descriptor, temporary = tempfile.mkstemp(dir=KAGGLE_DIR, prefix=f".{name}.")  # mode 0600
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        os.replace(temporary, os.path.join(KAGGLE_DIR, name))
    except BaseException:
        os.unlink(temporary)
        raise


def _is_legacy_key(text):
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, dict) and "username" in data and "key" in data


def _kaggle_cli():
    try:
        path = kaggle.cli()
    except kaggle.KaggleError:
        return None
    return path if os.path.isfile(path) else None


def _draft_to_json(draft):
    return {
        "folder": draft.folder,
        "project": draft.project,
        "username": draft.username,
        "speakers": [{"id": s.id, "mode": s.mode, "value": s.value, "transcript": s.transcript}
                     for s in draft.speakers],
        "sentences": list(draft.sentences),
        "own": {speaker_id: list(lines) for speaker_id, lines in draft.own.items()},
    }


def parser():
    p = argparse.ArgumentParser(prog="python -m voicetut_kaggle.desktop_api")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("open")
    s.add_argument("folder")
    s.set_defaults(run=cmd_open)
    s = sub.add_parser("status")
    s.add_argument("folder")
    s.set_defaults(run=cmd_status)
    s = sub.add_parser("fix-save")
    s.add_argument("folder")
    s.set_defaults(run=cmd_fix_save)
    s = sub.add_parser("takes")
    s.add_argument("folder")
    s.set_defaults(run=cmd_takes)
    s = sub.add_parser("use-takes")
    s.add_argument("folder")
    s.add_argument("takes", nargs="+")
    s.set_defaults(run=cmd_use_takes)
    s = sub.add_parser("save")
    s.set_defaults(run=cmd_save)
    s = sub.add_parser("token")
    new = s.add_mutually_exclusive_group()
    new.add_argument("--copy", metavar="FILE", help="add or replace the token from this file")
    new.add_argument("--set", action="store_true", help="add or replace the token read on stdin")
    s.set_defaults(run=cmd_token)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        answer = args.run(args)
    except (config.ConfigError, kaggle.KaggleError, ValueError, KeyError, OSError) as e:
        message = f"missing field {e}" if isinstance(e, KeyError) else str(e)
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(answer, ensure_ascii=False))


if __name__ == "__main__":
    main()
