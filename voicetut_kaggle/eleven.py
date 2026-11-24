"""ElevenLabs instead of (or next to) Kaggle: the same lines, recorded in seconds with paid voices.

The flow mirrors the Kaggle one and ends in the same place:
  vk eleven credits                  how many characters your plan has left
  vk eleven voices                   one ElevenLabs voice per speaker, cloned from their clip
  vk eleven record 232-239           every speaker says these lines, `eleven.takes` takes each
  vk eleven record --fixes f.yaml    or: spellings to try, like `vk fix`
  vk listen build/out/eleven/eleven.zip --compare <voices zip>   pick by ear
  vk use-take build/out/eleven/eleven.zip <voices zip> <out zip> <picked takes>

The output is a fix.zip (fix/<speaker>_<nnn>_<variant><take>.flac and said.json), so the listening
page and use-take work on it unchanged. Plain recordings use variant "e"; --fixes uses a, b, c...
Every clip is kept in build/eleven/clips/, so running the same command again costs nothing.

The API key is read from $ELEVENLABS_API_KEY or `eleven.key_file` (never printed). Recording costs
characters of your plan: the command shows the estimate and asks before spending them.
"""
import concurrent.futures
import json
import os
import re
import shutil
import string
import subprocess
import tempfile
import time
import zipfile

import requests
import yaml

from .config import ConfigError
from .pronounce import DIGITS, plain, prepare

API = "https://api.elevenlabs.io"
TIMEOUT = 120
RATE = 24000  # pcm_24000 is on every plan (44.1 kHz PCM needs Pro)


class ElevenError(RuntimeError):
    """ElevenLabs said no: a bad key, no credits left, an unknown voice..."""


# Numbers as Egyptian Arabic words, vowelled: left as digits, ElevenLabs reads them in formal Arabic.
EGYPTIAN_NUMBERS = [
    "صِفْر", "وَاحِد", "اِتْنِين", "تَلَاتَة", "أَرْبَعَة", "خَمْسَة", "سِتَّة", "سَبْعَة", "تَمَانْيَة", "تِسْعَة",
    "عَشَرَة", "حِدَاشَر", "اِتْنَاشَر", "تَلَتْطَاشَر", "أَرْبَعْتَاشَر", "خَمَسْتَاشَر", "سِتَّاشَر", "سَبَعْتَاشَر",
    "تَمَنْتَاشَر", "تِسَعْتَاشَر", "عِشْرِين",
]


class _EgyptianNumbers:
    """VoiceTut's normalizer stand-in for prepare(): numbers 0-20 become Egyptian words."""
    _lexicon = {}
    _diacritics = {}

    @staticmethod
    def expand_numbers(text):
        def word(m):
            n = int(m.group(0))
            return EGYPTIAN_NUMBERS[n] if n < len(EGYPTIAN_NUMBERS) else m.group(0)
        return re.sub(r"\d+", word, text)


# ---- the API ----

def api_key(cfg):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        path = os.path.expanduser(cfg.eleven["key_file"])
        try:
            with open(path, encoding="utf-8") as f:
                key = f.read().strip()
        except FileNotFoundError:
            raise ElevenError(
                f"no ElevenLabs API key: put it in {path} (or $ELEVENLABS_API_KEY). "
                "Make one on elevenlabs.io: profile > API keys") from None
    if not key:
        raise ElevenError("the ElevenLabs API key is empty")
    return key


def _call(key, method, path, tries=5, **kwargs):
    """One API request, retried while ElevenLabs is busy (429) or briefly down (5xx)."""
    for attempt in range(tries):
        reply = requests.request(method, API + path, headers={"xi-api-key": key}, timeout=TIMEOUT, **kwargs)
        if reply.status_code == 429 or reply.status_code >= 500:
            time.sleep(min(30, 2 ** attempt))
            continue
        if reply.status_code >= 400:
            raise ElevenError(f"ElevenLabs {reply.status_code} on {path}: {_why(reply)}")
        return reply
    raise ElevenError(f"ElevenLabs stayed busy on {path} ({reply.status_code}); try again later")


def _why(reply):
    try:
        detail = reply.json().get("detail")
    except ValueError:
        return reply.text[:200]
    if isinstance(detail, dict):
        return detail.get("message") or detail.get("status") or str(detail)
    return str(detail)


def credits(cfg):
    """(characters used, character limit, plan name) of the account."""
    info = _call(api_key(cfg), "GET", "/v1/user/subscription").json()
    return info.get("character_count", 0), info.get("character_limit", 0), info.get("tier", "?")


def account_voices(cfg):
    """[(name, voice id, category)] of every voice in the account."""
    voices = _call(api_key(cfg), "GET", "/v1/voices").json().get("voices", [])
    return [(v.get("name", ""), v["voice_id"], v.get("category", "")) for v in voices]


def _speak(key, voice_id, text, settings, seed):
    """Raw 16-bit mono PCM at RATE of [voice_id] saying [text]."""
    body = {
        "text": text,
        "model_id": settings["model"],
        "seed": seed,
        "voice_settings": {
            "stability": settings["stability"],
            "similarity_boost": settings["similarity"],
            "style": settings["style"],
            "speed": settings["speed"],
            "use_speaker_boost": True,
        },
    }
    if settings["language"]:
        body["language_code"] = settings["language"]
    reply = _call(key, "POST", f"/v1/text-to-speech/{voice_id}", params={"output_format": f"pcm_{RATE}"},
                  json=body)
    return reply.content


def _to_flac(pcm, path):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg was not found: install it (e.g. `sudo apt install ffmpeg`)")
    tmp = path + ".part"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(RATE),
                    "-ac", "1", "-i", "pipe:0", "-c:a", "flac", "-f", "flac", tmp], input=pcm, check=True)
    os.replace(tmp, path)


# ---- voices: one per speaker ----

def _voices_file(cfg):
    return os.path.join(cfg.build, "eleven", "voices.json")


def voice_ids(cfg):
    """{speaker: ElevenLabs voice id}: the ones cloned here, overridden by `eleven.voices`."""
    try:
        with open(_voices_file(cfg), encoding="utf-8") as f:
            cloned = json.load(f)
    except FileNotFoundError:
        cloned = {}
    return {**cloned, **cfg.eleven["voices"]}


def make_voices(cfg, speakers=None, redo=False, from_zip=None, seconds=60):
    """Clones each speaker into an ElevenLabs voice (Instant Voice Cloning); returns the ids.

    From the speaker's clip, or with [from_zip] from about [seconds] of the speaker's own recorded
    lines in a voices zip: then the clone sounds like the recordings people already hear, not like
    the clip they were made from.
    """
    key = api_key(cfg)
    ids = voice_ids(cfg)
    cloned = {k: v for k, v in ids.items() if k not in cfg.eleven["voices"]}
    for speaker in cfg.speakers:
        if speakers and speaker.id not in speakers:
            continue
        if speaker.id in cfg.eleven["voices"]:
            print(f"{speaker.id}: {cfg.eleven['voices'][speaker.id]} (from voices.yaml)")
            continue
        if speaker.id in cloned and not redo:
            print(f"{speaker.id}: {cloned[speaker.id]} (already cloned)")
            continue
        if from_zip:
            name, audio = f"{speaker.id}_lines.wav", _lines_sample(from_zip, speaker.id, seconds)
            source = f"{seconds} s of its lines in {os.path.basename(from_zip)}"
        elif speaker.mode == "clip":
            with open(speaker.value, "rb") as f:
                name, audio, source = os.path.basename(speaker.value), f.read(), os.path.basename(speaker.value)
        else:
            raise ConfigError(f"speaker '{speaker.id}' has no clip to clone: use --from-zip, or give its "
                              "voice id in voices.yaml under eleven: voices:")
        if speaker.id in cloned:  # cloning again: free the old voice's slot first
            _call(key, "DELETE", f"/v1/voices/{cloned.pop(speaker.id)}")
        reply = _call(key, "POST", "/v1/voices/add", data={
            "name": f"{cfg.project}-{speaker.id}",
            "description": f"{speaker.id}, cloned by vk for {cfg.project} from {source}",
        }, files=[("files", (name, audio))])
        cloned[speaker.id] = reply.json()["voice_id"]
        os.makedirs(os.path.dirname(_voices_file(cfg)), exist_ok=True)
        with open(_voices_file(cfg), "w", encoding="utf-8") as f:
            json.dump(cloned, f, indent=1)
        print(f"{speaker.id}: {cloned[speaker.id]} (cloned from {source})")
    return voice_ids(cfg)


def _lines_sample(zip_path, speaker, seconds):
    """About [seconds] of a speaker's lines from a voices zip, spread over all of them, as one WAV."""
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(n for n in z.namelist() if n.startswith(f"voices/{speaker}/") and n.endswith(".flac"))
        if not names:
            raise ValueError(f"{zip_path} has no lines of '{speaker}'")
        with tempfile.TemporaryDirectory() as work:
            picked, total, step = [], 0.0, max(1, len(names) // 40)
            for i, member in enumerate(names[::step]):
                path = os.path.join(work, f"{i:03d}.flac")
                with open(path, "wb") as f:
                    f.write(z.read(member))
                length = _seconds(path)
                if 1.5 <= length <= 10:  # whole sentences, not one-word lines or long hints
                    picked.append(path)
                    total += length
                if total >= seconds:
                    break
            listing = os.path.join(work, "list.txt")
            with open(listing, "w") as f:
                f.writelines(f"file '{p}'\n" for p in picked)
            out = os.path.join(work, "sample.wav")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                            "-i", listing, "-ac", "1", "-ar", "44100", out], check=True)
            with open(out, "rb") as f:
                return f.read()


def _seconds(path):
    reply = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, check=True)
    return float(reply.stdout.strip() or 0)


def delete_voices(cfg, speakers=None):
    """Deletes the voices cloned here (all, or these speakers') to free voice slots.

    The recordings are kept; a speaker is simply cloned again by `make_voices` when needed.
    """
    key = api_key(cfg)
    cloned = {k: v for k, v in voice_ids(cfg).items() if k not in cfg.eleven["voices"]}
    for speaker, voice_id in list(cloned.items()):
        if speakers and speaker not in speakers:
            continue
        _call(key, "DELETE", f"/v1/voices/{voice_id}")
        del cloned[speaker]
        print(f"{speaker}: deleted {voice_id}")
    with open(_voices_file(cfg), "w", encoding="utf-8") as f:
        json.dump(cloned, f, indent=1)


# ---- recording ----

def line_jobs(cfg, first, last, speakers=None, takes=None):
    """Every speaker says lines first..last, `takes` times; the pronunciation file sets the spelling."""
    takes = takes or cfg.eleven["takes"]
    jobs = []
    for speaker in _chosen(cfg, speakers):
        lines = cfg.lines(speaker)
        if len(lines) <= last:
            raise ValueError(f"speaker '{speaker}' has no line {last}: add the sentences first")
        for n in range(first, last + 1):
            text = _spelled(cfg, lines[n])
            for take in range(1, takes + 1):
                jobs.append({"name": f"{speaker}_{n:03d}_e{take}", "speaker": speaker, "line": n,
                             "variant": "e", "take": take, "text": text})
    return jobs


def fix_jobs(cfg, path, speakers=None, takes=None):
    """Like `vk fix`: each spelling of each line in the YAML file, given exactly as written."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    takes = takes or int(raw.get("takes") or cfg.eleven["takes"])
    jobs = []
    for entry in raw.get("lines") or []:
        n, spellings = int(entry["line"]), [str(s) for s in entry.get("spellings") or []]
        if not spellings or len(spellings) > len(string.ascii_lowercase):
            raise ConfigError(f"{path}: line {n} needs 1 to 26 spellings")
        who = [s for s in (entry.get("speakers") or cfg.speaker_ids()) if not speakers or s in speakers]
        for speaker in who:
            if speaker not in cfg.speaker_ids():
                raise ConfigError(f"{path}: unknown speaker '{speaker}'")
            if n >= len(cfg.lines(speaker)):
                raise ConfigError(f"{path}: speaker '{speaker}' has no line {n}")
            for variant, text in zip(string.ascii_lowercase, spellings):
                for take in range(1, takes + 1):
                    jobs.append({"name": f"{speaker}_{n:03d}_{variant}{take}", "speaker": speaker, "line": n,
                                 "variant": variant, "take": take, "text": text})
    if not jobs:
        raise ConfigError(f"{path} has no lines to record")
    return jobs


def _chosen(cfg, speakers):
    unknown = sorted(set(speakers or ()) - set(cfg.speaker_ids()))
    if unknown:
        raise ConfigError(f"unknown speaker(s) {unknown}")
    return [s for s in cfg.speaker_ids() if not speakers or s in speakers]


def _spelled(cfg, sentence):
    """The sentence as the voice gets it: with the pronunciation file's vowel marks, if asked for."""
    if not cfg.eleven["vowels"]:
        return _EgyptianNumbers.expand_numbers(sentence.translate(DIGITS))
    return prepare(sentence, _EgyptianNumbers, cfg.pronunciation)


def _clip_path(cfg, job):
    return os.path.join(cfg.build, "eleven", "clips", f"{job['name']}.flac")


def _said_file(cfg, job):
    """How a kept clip was made: it is only reused for the same text, voice and settings."""
    return _clip_path(cfg, job)[:-5] + ".txt"


def _made_with(job, voice_id, settings):
    keys = ("model", "language", "stability", "similarity", "style", "speed")
    return json.dumps({"text": job["text"], "voice": voice_id, **{k: settings[k] for k in keys}},
                      ensure_ascii=False, sort_keys=True)


def _kept(cfg, job, voice_id, settings):
    try:
        with open(_said_file(cfg, job), encoding="utf-8") as f:
            return f.read() == _made_with(job, voice_id, settings) and os.path.isfile(_clip_path(cfg, job))
    except FileNotFoundError:
        return False


def record(cfg, jobs, out_zip, confirm=input, yes=False, settings=None):
    """Records the jobs (reusing kept clips) and writes out_zip; returns its path.

    [settings]: changes to `eleven` for this run only, e.g. {"stability": 0}.
    """
    settings = {**cfg.eleven, **(settings or {})}
    key = api_key(cfg)
    ids = voice_ids(cfg)
    missing = sorted({j["speaker"] for j in jobs} - set(ids))
    if missing:
        raise ConfigError(f"no ElevenLabs voice for {missing}: run `vk eleven voices` first")
    todo = [j for j in jobs if not _kept(cfg, j, ids[j["speaker"]], settings)]
    chars = sum(len(j["text"]) for j in todo)
    used, limit, tier = credits(cfg)
    left = max(0, limit - used)
    print(f"{len(jobs)} clips: {len(jobs) - len(todo)} kept, {len(todo)} to record, about {chars} characters "
          f"of the {left} left on your {tier} plan")
    if chars > left:
        raise ElevenError(f"not enough characters left ({left}) for {chars}: wait for the reset or upgrade")
    if todo and not yes and confirm("record them? [y/N] ").strip().lower() not in ("y", "yes"):
        raise ElevenError("stopped: nothing recorded")
    os.makedirs(os.path.dirname(_clip_path(cfg, jobs[0])), exist_ok=True)

    def one(job):
        voice_id = ids[job["speaker"]]
        pcm = _speak(key, voice_id, job["text"], settings, seed=job["take"] * 1000 + job["line"])
        _to_flac(pcm, _clip_path(cfg, job))
        with open(_said_file(cfg, job), "w", encoding="utf-8") as f:
            f.write(_made_with(job, voice_id, settings))
        return job["name"]

    with concurrent.futures.ThreadPoolExecutor(settings["at_once"]) as pool:
        for done, name in enumerate(pool.map(one, todo), 1):
            print(f"{done}/{len(todo)} {name}", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w") as z:
        for job in jobs:
            z.write(_clip_path(cfg, job), f"fix/{job['name']}.flac")
        said = {j["name"]: {k: v for k, v in j.items() if k != "name"} for j in jobs}
        z.writestr("fix/said.json", json.dumps(said, ensure_ascii=False, indent=1))
    print(f"{len(jobs)} clips -> {out_zip}")
    return out_zip
