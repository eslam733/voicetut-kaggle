"""Starts the recording parts as Kaggle GPU slots free up, then the check once every part is done.

Kaggle runs at most two GPU notebooks at once and refuses a third push with "Maximum batch GPU
session count"; this keeps trying every few minutes. Stop it any time with Ctrl+C: what is already
running on Kaggle keeps running, and `vk watch --resume` follows the same run again without
pushing anything twice (build/kaggle/watch-state.json remembers what was pushed).

Kaggle sometimes leaves a pushed notebook QUEUED for good even with a GPU slot free; pushing it
again starts it. So a notebook QUEUED for STUCK_AFTER seconds is pushed again (Kaggle refuses the
push while both GPU slots are really busy, and then it just keeps waiting).
"""
import json
import os
import time

from . import kaggle, record

DONE, FAILED = {"COMPLETE"}, {"ERROR", "CANCEL_REQUESTED", "CANCEL_ACKNOWLEDGED"}
STARTED = {"QUEUED", "RUNNING"}
STUCK_AFTER = 15 * 60


def state_path(cfg):
    return os.path.join(cfg.build, "kaggle", "watch-state.json")


def read_state(cfg):
    """{"pushed": [part names], "check_pushed": bool}; nothing pushed when there is no file."""
    try:
        with open(state_path(cfg), encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        return {"pushed": [], "check_pushed": False}
    return {"pushed": list(state.get("pushed", [])), "check_pushed": bool(state.get("check_pushed"))}


def forget(cfg):
    """A new build is a new run: nothing of it has been pushed yet."""
    try:
        os.remove(state_path(cfg))
    except FileNotFoundError:
        pass


def _save_state(cfg, state):
    with open(state_path(cfg), "w", encoding="utf-8") as f:
        json.dump(state, f)


def _push_again_if_stuck(cfg, status, queued_since):
    """status: {name: Kaggle status}; queued_since: {name: when first seen QUEUED}, kept by the caller."""
    now = time.monotonic()
    for name, s in status.items():
        if s != "QUEUED":
            queued_since.pop(name, None)
            continue
        waited = now - queued_since.setdefault(name, now)
        if waited < STUCK_AFTER:
            continue
        queued_since[name] = now
        if kaggle.push(os.path.join(cfg.build, "kaggle", name)):
            minutes = f"{waited // 60:.0f}"
            print(f"{time.strftime('%H:%M')} {name} had not started after {minutes} min: pushed it again")


def _wait_until_started(cfg, name, every):
    """Waits while Kaggle has not started the notebook yet (NONE: just pushed, not listed yet)."""
    queued_since = {}
    while True:
        status = kaggle.kernel_status(cfg.ref(cfg.kernel_slug(name)))
        if status not in ("QUEUED", "NONE"):
            return status
        _push_again_if_stuck(cfg, {name: "QUEUED"}, queued_since)  # NONE for that long: push again too
        time.sleep(every)


def watch(cfg, parts=None, start_check=True, every=300, resume=False):
    """[parts]: the part names still to push (default: all of them).

    resume: push only what watch-state.json says was not pushed yet.
    """
    names = record.part_names(cfg)
    if resume:
        state = read_state(cfg)
        pending = [name for name in names if name not in state["pushed"]]
    else:
        pending = list(parts or names)
        state = {"pushed": [name for name in names if name not in pending], "check_pushed": False}
    _save_state(cfg, state)
    seen_started = set(names) - set(pending)  # parts not pushed now count as started already
    queued_since = {}
    while True:
        for name in list(pending):
            if kaggle.push(os.path.join(cfg.build, "kaggle", name)):
                pending.remove(name)
                state["pushed"].append(name)
                _save_state(cfg, state)
            else:
                print(f"{time.strftime('%H:%M')} both GPU slots are busy; {name} waits")
        status = {name: kaggle.kernel_status(cfg.ref(cfg.kernel_slug(name))) for name in names}
        seen_started |= {name for name, s in status.items() if s in STARTED}
        print(time.strftime("%H:%M"), "  ".join(f"{n}={s}" for n, s in status.items()), flush=True)
        failed = [n for n, s in status.items() if s in FAILED]
        if failed:
            raise kaggle.KaggleError(f"{failed} failed or were cancelled: open them on kaggle.com to see the log")
        # A part pushed again shows its old COMPLETE status until the new run starts: wait for that.
        finished = not pending and all(status[n] in DONE and n in seen_started for n in names)
        if finished:
            break
        _push_again_if_stuck(cfg, {n: s for n, s in status.items() if n not in pending}, queued_since)
        time.sleep(every)
    print("every part is done")
    check_ref = cfg.ref(cfg.kernel_slug("check"))
    if not start_check:
        return
    if state["check_pushed"]:
        print("check was already pushed")
    else:
        while not kaggle.push(os.path.join(cfg.build, "kaggle", "check")):
            time.sleep(every)
        state["check_pushed"] = True
        _save_state(cfg, state)
    status = _wait_until_started(cfg, "check", every)
    print(f"check is {status}: follow it with `kaggle kernels status {check_ref}`")
