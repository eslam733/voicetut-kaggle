"""Starts the recording parts as Kaggle GPU slots free up, then the check once every part is done.

Kaggle runs at most two GPU notebooks at once and refuses a third push with "Maximum batch GPU
session count"; this keeps trying every few minutes. Stop it any time with Ctrl+C: what is already
running on Kaggle keeps running.
"""
import os
import time

from . import kaggle, record

DONE, FAILED = {"COMPLETE"}, {"ERROR", "CANCEL_REQUESTED", "CANCEL_ACKNOWLEDGED"}
STARTED = {"QUEUED", "RUNNING"}


def watch(cfg, parts=None, start_check=True, every=300):
    """[parts]: the part names still to push (default: all of them)."""
    names = record.part_names(cfg)
    pending = list(parts or names)
    seen_started = set(names) - set(pending)  # parts not pushed now count as started already
    while True:
        for name in list(pending):
            if kaggle.push(os.path.join(cfg.build, "kaggle", name)):
                pending.remove(name)
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
        time.sleep(every)
    print("every part is done")
    if start_check:
        while not kaggle.push(os.path.join(cfg.build, "kaggle", "check")):
            time.sleep(every)
        print(f"check started: follow it with `kaggle kernels status {cfg.ref(cfg.kernel_slug('check'))}`")
