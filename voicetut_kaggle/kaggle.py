"""Talks to Kaggle: the official `kaggle` CLI for pushing and status, its HTTP API for downloads."""
import json
import os
import re
import shutil
import subprocess
import time

import requests

API = "https://api.kaggle.com/v1"
TIMEOUT = 120  # seconds per HTTP request
STATUS = re.compile(r"KernelWorkerStatus\.([A-Z_]+)")
GPU_SLOTS_FULL = "Maximum batch GPU session count"


class KaggleError(RuntimeError):
    """A Kaggle command or request failed; the message says what Kaggle answered."""


def cli():
    path = os.environ.get("KAGGLE_CLI") or shutil.which("kaggle")
    if not path:
        raise KaggleError("the `kaggle` command was not found: `pip install kaggle` "
                          "(or set KAGGLE_CLI to its path)")
    return path


def run(*args, check=True):
    """Runs `kaggle <args>`, prints and returns its output."""
    done = subprocess.run([cli(), *args], capture_output=True, text=True)
    output = (done.stdout + done.stderr).strip()
    print(output)
    if check and done.returncode != 0:
        raise KaggleError(f"`kaggle {' '.join(args)}` failed (exit {done.returncode})")
    return output


def dataset_exists(ref):
    done = subprocess.run([cli(), "datasets", "status", ref], capture_output=True, text=True)
    return done.returncode == 0


def wait_for_dataset(ref, every=15, tries=60):
    """Kaggle processes a new dataset version for a while; notebooks pushed before see the old one."""
    for _ in range(tries):
        done = subprocess.run([cli(), "datasets", "status", ref], capture_output=True, text=True)
        status = done.stdout.strip()
        if status == "ready":
            print(f"{ref} is ready")
            return
        print(f"{ref}: {status or done.stderr.strip()[:200]} (checking again in {every}s)")
        time.sleep(every)
    raise KaggleError(f"{ref} is still not ready; check it with `kaggle datasets status {ref}`")


def kernel_status(ref):
    """RUNNING, QUEUED, COMPLETE, ERROR, CANCEL_ACKNOWLEDGED, ... or NONE (never pushed)."""
    done = subprocess.run([cli(), "kernels", "status", ref], capture_output=True, text=True)
    found = STATUS.search(done.stdout)
    return found.group(1) if found else "NONE"


def push(folder):
    """Pushes and starts a notebook. Returns False when both GPU slots are busy (try again later)."""
    output = run("kernels", "push", "-p", folder, check=False)
    if GPU_SLOTS_FULL in output:
        return False
    if "successfully pushed" not in output:
        raise KaggleError(f"pushing {folder} failed (Kaggle's answer is above)")
    return True


def _auth():
    """The same credentials the kaggle CLI uses: an API token, or the older kaggle.json key."""
    token = os.environ.get("KAGGLE_API_TOKEN")
    if token and os.path.isfile(token):
        token = _read(token)
    for path in ("~/.kaggle/access_token", "~/.kaggle/access_token.txt"):
        token = token or _read(os.path.expanduser(path))
    if token:
        return {"headers": {"Authorization": f"Bearer {token}"}}
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return {"auth": (os.environ["KAGGLE_USERNAME"], os.environ["KAGGLE_KEY"])}
    legacy = os.path.join(os.environ.get("KAGGLE_CONFIG_DIR", os.path.expanduser("~/.kaggle")), "kaggle.json")
    if os.path.isfile(legacy):
        with open(legacy) as f:
            creds = json.load(f)
        return {"auth": (creds["username"], creds["key"])}
    raise KaggleError("no Kaggle credentials: put your API token in ~/.kaggle/access_token (see README)")


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def find_output_files(username, slug, wanted):
    """{file name: download URL} for the wanted files of a notebook's latest output.

    The CLI's `kernels output` lists 20 files per request and walks through all of them, which
    trips Kaggle's rate limit (HTTP 429) on a big output; this asks for 500 at a time and stops
    as soon as every wanted file is found.
    """
    auth, found, page, pages = _auth(), {}, None, 0
    while True:
        body = {"userName": username, "kernelSlug": slug, "pageSize": 500}
        if page:
            body["pageToken"] = page
        reply = requests.post(f"{API}/kernels.KernelsApiService/ListKernelSessionOutput",
                              json=body, timeout=TIMEOUT, **auth)
        pages += 1
        if not reply.ok:
            raise KaggleError(f"listing the output of {slug}: HTTP {reply.status_code} {reply.text[:200]}")
        data = reply.json()
        found.update({f["fileName"]: f["url"] for f in data.get("files", []) if f.get("fileName") in wanted})
        page = data.get("nextPageToken")
        if wanted <= found.keys() or not page:
            return found
        time.sleep(5)  # stay well under the rate limit


def download(url, path):
    """Downloads to path (via a .part file, so a cut-off download never looks finished)."""
    with requests.get(url, stream=True, timeout=TIMEOUT) as reply:
        reply.raise_for_status()
        with open(path + ".part", "wb") as out:
            for chunk in reply.iter_content(1 << 20):
                out.write(chunk)
    os.replace(path + ".part", path)
    print(f"downloaded {path} ({os.path.getsize(path) / 1e6:.1f} MB)")
