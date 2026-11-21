# voicetut-kaggle

Record hundreds or thousands of **Egyptian Arabic** voice lines, in as many voices as you like,
on **Kaggle's free GPUs**, with every line checked by speech recognition.

- **Voices:** [VoiceTut-TTS](https://huggingface.co/mohammedaly22/VoiceTut-TTS) clones a voice from
  a short clip, or uses one of its built-in voices.
- **Check:** [QwenCleo-ASR](https://huggingface.co/mohammedaly22/QwenCleo-ASR) writes down what
  it hears in every clip. Lines that don't match are recorded again, and the best take is kept.
- **Workflow:** you describe the project in one file (`voices.yaml`). The `vk` command builds
  the Kaggle notebooks, starts them, downloads the results and turns them into small audio files
  for an app.
- **Three ways to use it:** the `vk` command, the **VoiceTut Kaggle** desktop app (see
  [The desktop app](#the-desktop-app)), or an AI assistant that runs `vk` for you (see
  [Using it with an AI assistant](#using-it-with-an-ai-assistant)).

It was first built to voice the characters of a children's learning app. Any project with many
fixed sentences fits: games, lessons, audio guides, voice prompts.

> **Use voices responsibly.** Clone a real person's voice only with that person's clear consent.
> Don't use cloned voices to impersonate, deceive or harm anyone, and say that the audio is
> synthetic where that matters. The models' own terms say the same (see [Licenses](#licenses)).

## Contents

1. [How it works](#how-it-works)
2. [What you need](#what-you-need)
3. [Install](#install)
4. [The desktop app](#the-desktop-app)
5. [Set up your Kaggle API token](#set-up-your-kaggle-api-token)
6. [Try the demo (about 30 minutes)](#try-the-demo-about-30-minutes)
7. [Your own project, step by step](#your-own-project-step-by-step)
8. [The project file](#the-project-file-voicesyaml)
9. [Fixing pronunciation](#fixing-pronunciation)
10. [Adding lines later](#adding-lines-later)
11. [Kaggle limits](#kaggle-limits)
12. [Troubleshooting](#troubleshooting)
13. [Licenses](#licenses)
14. [Using it with an AI assistant](#using-it-with-an-ai-assistant)
15. [Development](#development)

## How it works

```
 voices.yaml + sentences.json + voice clips
        │
        ▼  vk dataset --upload        1. private Kaggle dataset (sentences, clips)
        ▼  vk record                  2. builds recording notebooks part1..partN (+ the check)
        ▼  vk watch                   2. starts the parts as GPU slots free up, then the check
 ┌──────────────── Kaggle (GPU T4 x2 per notebook) ─────────────────┐
 │ partN:  VoiceTut records every line   → voices.zip               │
 │ check:  QwenCleo listens to each line, re-records bad ones       │
 │                                        → voices_checked.zip      │
 └──────────────────────────────────────────────────────────────────┘
        ▼  vk fetch check             4. downloads just the zip (no rate-limit trouble)
        ▼  vk listen                  5. local web page of the lines still flagged
        ▼  vk fix / vk use-take       6. try spellings for a bad clip, swap in the best take
        ▼  vk new-lines / vk merge    7. add sentences later without renumbering
        ▼  vk export                  8. small Opus files + lines.json for your app
```

Line `n` of a speaker is the **shared sentences first**, then that speaker's own sentences. Clips
are named `voices/<speaker>/<nnn>.flac`, for example `voices/guide/003.flac`.

## What you need

- **A Kaggle account with a verified phone number.** Kaggle only allows GPUs and internet in
  notebooks after phone verification (kaggle.com → *Settings* → *Phone verification*). The
  notebooks need the internet to install the models.
- **Python 3.9 or newer** and `git` on your computer. Nothing heavy runs locally: the models run
  on Kaggle.
- **ffmpeg**, for `vk export` (for example `sudo apt install ffmpeg` or `brew install ffmpeg`).
- **For cloned voices:** a clean 5–15 second clip of each voice, with one person speaking and
  no music, plus the exact words said in it. Get the speaker's consent. You can skip clips at
  first: the demo uses VoiceTut's built-in voices.

## Install

```bash
git clone https://github.com/eslam733/voicetut-kaggle.git
```

```bash
cd voicetut-kaggle && python3 -m venv .venv && . .venv/bin/activate && pip install -e .
```

This installs the `vk` command, plus `pyyaml`, `requests` and the official `kaggle` CLI. Check
that it works:

```bash
vk --help
```

## The desktop app

**VoiceTut Kaggle** is the same pipeline in a window, for when you'd rather not use a terminal.
It runs the same `vk` steps on the same project files, so you can switch between the app and the
command line at any time.

![VoiceTut Kaggle icon](desktop/src-tauri/icons/128x128.png)

### Install it (Linux)

On Debian or Ubuntu, after cloning the repo:

```bash
cd voicetut-kaggle && desktop/install.sh
```

- If system packages are missing, the script prints one `sudo apt-get install -y …` line and
  stops. Run that line, then run the script again.
- It installs Rust for your user if needed, a private Python environment, the app and its menu
  entry. The first build takes a few minutes.
- Then open **VoiceTut Kaggle** from the application menu (search for "VoiceTut"). Right-click it
  there to pin it to the taskbar or the desktop.
- After `git pull`, run `desktop/install.sh` again to update the app.

Windows and Mac: see [desktop/README.md](desktop/README.md). Those builds are not ready yet.

### Use it

The window has four tabs. Above them, the **status line** says what is happening on Kaggle, with
one tag per notebook (for example *part1 complete*, *check running*). It asks Kaggle again every
minute while a notebook is queued or running. The **Log** at the bottom shows the output of each
step.

1. **Setup**
   - **Folder:** your project folder. The app opens `~/my-voices` if it exists. An empty folder
     starts a new project.
   - **Project name** and **Kaggle username** (the name in `kaggle.com/<name>`).
   - **Kaggle token:** paste the token from kaggle.com → *Settings* → *API* and click **Save
     token**, or use **From file…**. A new token replaces the old one. It is saved in `~/.kaggle`,
     readable only by you, and never shown.
   - **Speakers:** each one is a built-in voice, a voice clip plus the exact words said in it, or a
     voice description. Use a real person's voice only with their consent.
   - **Lines:** one sentence per line. Every speaker says these lines.
   - **Save project** writes `voices.yaml` and the sentences file. Other settings in
     `voices.yaml` (pronunciation, recording, check, export) and each speaker's own lines are kept.
     Comments in `voices.yaml` are not.
2. **Record**
   - **Start recording** saves the project, uploads the dataset when Kaggle's copy is older, then
     starts the recording notebooks and the check. This uses your Kaggle GPU hours.
   - Closing the window stops following the run, not the run on Kaggle. **Resume** picks it up.
   - **Start over** (click twice) records every line again, for a run that failed or one you want
     to redo. Stop notebooks still running on kaggle.com first.
   - **Stop** stops the step running in the app; notebooks already started keep running.
3. **Results**
   - **Download results** when the check is *complete* (the button turns green).
   - **Listen** opens every line in your browser, with the flagged ones marked.
   - **Export…** asks for a folder and writes small Opus files plus `lines.json` for your app.
4. **Fix lines**, for a line that sounds wrong:
   1. **Add a line to fix**, then pick the speaker and the line.
   2. Write the sentence a few ways with the vowel marks you want, one per line. **Takes per
      spelling** is how many times each one is recorded (2 is usually enough).
   3. **Record fixes** (a few GPU minutes), then **Download takes** and **Listen to takes**.
   4. Pick one take per line and click **Use the picked takes**. The clip is replaced in
      `voices_checked.zip` (the original is kept once as `voices_checked.before-fixes.zip`), and
      the spelling is added to your pronunciation file so later recordings say it the same way.
      Then **Export** again.

Adding lines later is only on the `vk` command for now (see
[Adding lines later](#adding-lines-later)).

### When something goes wrong

| What you see | What to do |
|---|---|
| *No Kaggle token yet* | Setup tab: paste your token and click **Save token**. |
| *check is RUNNING on Kaggle, not finished* after Download | Wait. The status line says when the check is complete. |
| A notebook tag says *error* | Open it on kaggle.com for the log, then **Start over**. |
| *both Kaggle GPU slots are busy* | Another notebook is running on your account. Wait for it, or stop it on kaggle.com. |
| The window doesn't open from the menu | Run `~/.local/share/voicetut-kaggle/voicetut-kaggle-desktop` in a terminal and read the error. |

The app keeps everything in your project folder, as `vk` does (`voices.yaml`, the sentences,
`clips/`, `build/`). The app itself is in `~/.local/share/voicetut-kaggle`.

## Set up your Kaggle API token

1. On kaggle.com, open *Settings* → *API* → **Create New Token**, and copy the token.
2. Save it where the Kaggle CLI (and `vk`) look for it, readable only by you:

   ```bash
   mkdir -p ~/.kaggle && nano ~/.kaggle/access_token
   ```

   Paste the token, save, then:

   ```bash
   chmod 600 ~/.kaggle/access_token
   ```

3. Check it:

   ```bash
   kaggle kernels list --mine
   ```

An older `~/.kaggle/kaggle.json` key (`{"username": ..., "key": ...}`) works too, and so does the
`KAGGLE_API_TOKEN` environment variable. **Never commit a token.** This repo's `.gitignore`
already excludes `kaggle.json`, `access_token` and `.kaggle/`.

## Try the demo (about 30 minutes)

`examples/demo` records 5 short lines with two built-in VoiceTut voices (`narrator` = Karim,
`guide` = Yasmin). It uses about half an hour of your weekly Kaggle GPU quota.

1. Copy it and set your Kaggle username:

   ```bash
   cp -r examples/demo ~/my-voices && cd ~/my-voices
   ```

   Edit `voices.yaml`: replace `your-kaggle-username` with your Kaggle username.

2. Upload the dataset (about 1 minute):

   ```bash
   vk dataset --upload
   ```

3. Build the notebooks and start them. `vk watch` starts `part1`, waits for it, then starts
   `check` (about 10–15 minutes each, mostly installing and loading models):

   ```bash
   vk record && vk watch
   ```

4. Download the checked voices and listen to every line:

   ```bash
   vk fetch check && vk listen build/out/check/voices_checked.zip --all
   ```

   Open `build/listen/voices_checked/index.html` in a browser.

5. Make app-ready files (`build/app_audio/<speaker>/<nnn>.webm` and `lines.json`):

   ```bash
   vk export build/out/check/voices_checked.zip
   ```

Every command takes `-c path/to/voices.yaml`. Without it, `vk` uses `./voices.yaml`.
Generated files go in `build/` next to `voices.yaml`, and you can delete that folder at any time.

## Your own project, step by step

Rough speed on Kaggle at `num_step: 48`: one GPU records a short line in about 15 seconds, so a
recording notebook (2 GPUs) does roughly **450 lines an hour**. Each notebook also spends about
5–10 minutes installing and loading the models. For example, 20 speakers × 217 lines = 4,340
lines took 4 parts of about 2.5–3 hours each (two at a time), and the check took about 45 minutes.

### 1. Prepare and upload the dataset

Write `voices.yaml` (see [the project file](#the-project-file-voicesyaml)), `sentences.json`, and
optionally `pronunciation.json`. Then:

```bash
vk dataset --upload
```

This builds `build/kaggle/data/` and creates the private dataset `<username>/<project>-data`
(later runs add a new version). It waits until Kaggle reports the version **ready**: a notebook
started before that may still get the old version (see [Troubleshooting](#troubleshooting)).
Run it again whenever you change speakers, clips or sentences. Changes to the pronunciation file
need no upload, because that file is built into the notebooks.

### 2. Build and start the recording notebooks

```bash
vk record
```

This writes `build/kaggle/part1 … partN` (speakers split evenly) and `build/kaggle/check`. Set
`recording.parts` so that each part fits in one run: about 450 lines an hour, at most
`recording.hours` hours. With more lines than that, use more parts.

```bash
vk watch
```

`vk watch` starts every part. Kaggle runs two GPU notebooks at once, so the others wait, and it
retries every 5 minutes. When all parts are COMPLETE, it starts the check. You can stop it with
Ctrl+C at any time, and notebooks already started keep running; `vk watch --resume` then follows
the same run without pushing anything twice (it reads `build/kaggle/watch-state.json`, which
`vk record` resets). Options: `--parts part3 part4` (only those), `--no-check`. Run it in the background on a long job, for example
`nohup vk watch > watch.log 2>&1 &`.

To start a single notebook yourself:

```bash
vk push part1
```

If a part runs out of time, its `voices.zip` holds the lines it finished. Open the notebook on
kaggle.com, add its own output as input (*Add Input* → *Your Work*), and run it again. It skips
the lines it already has.

### 3. Run the check

`vk watch` starts it for you. To start it yourself, once every part is COMPLETE:

```bash
vk push check
```

It listens to every line and re-records those whose letter error is above `check.threshold`, up
to `check.max_takes` takes, keeping the best. Output: `voices_checked.zip`, with `report.json`
inside (for each line: the text, what was heard, the error and the take kept).

To see where every notebook stands, at any time:

```bash
vk status
```

It prints one line such as `part1=COMPLETE  check=RUNNING` (`NONE` means never started).

### 4. Fetch the output

```bash
vk fetch check
```

This downloads `voices_checked.zip` to `build/out/check/`. Other notebooks work the same way:
`vk fetch part2` (gets `voices.zip`), `vk fetch fix`, `vk fetch new-lines`, or name the files:
`vk fetch check report.json`. `vk` asks Kaggle for 500 output files per request and stops once
it has found yours, so big outputs don't hit the rate limit (see *HTTP 429* below).

### 5. Listen to the flagged lines

```bash
vk listen build/out/check/voices_checked.zip
```

This writes `build/listen/voices_checked/index.html`: every line the recognizer still flags, with
what it heard and the error score. Add `--all` for every line, or `--compare other.zip` to hear
another version of each line next to it (for example an earlier run). Many flags are only
spelling differences the recognizer makes, so trust your ears.

### 6. Re-record chosen clips with spelling variants

For a clip that still sounds wrong, list a few spellings to try in a small YAML file (see
`examples/demo/fixes.yaml`):

```yaml
takes: 2
lines:
  - line: 2
    speakers: [narrator, guide]
    spellings:
      - "بْرَافُو عَلِيك، إِجَابَة صَحّ!"
      - "بْرَافُو عَلِيك، إِجَابَة صَحْ!"
```

Then build and run the fix notebook, download its output, and compare the takes with the clips
in use now:

```bash
vk fix fixes.yaml && vk push fix
```

```bash
vk fetch fix && vk listen build/out/fix/fix.zip --compare build/out/check/voices_checked.zip
```

Takes are named `<speaker>_<line>_<spelling letter><take>`, for example `guide_002_b1`. Swap the
ones you like into a new zip:

```bash
vk use-take build/out/fix/fix.zip build/out/check/voices_checked.zip voices_final.zip guide_002_b1
```

`use-take` also prints the matching `"lines"` entries for your pronunciation file, so later
recordings use the same spelling.

### 7. Add new lines later

See [Adding lines later](#adding-lines-later).

### 8. Export app-ready audio

```bash
vk export voices_final.zip --out path/to/app/assets/voices
```

This writes `<speaker>/<nnn>.webm` (Opus, mono, `export.bitrate`, `-application voip`) and
`lines.json` (`{speaker: [sentence, ...]}`). At 20 kbps, 200 short lines come to about 2.3 MB per
speaker. Opus in WebM plays on Android 5+ and in browsers. Set `export.format: ogg` for Ogg Opus.
It stops if any line is missing from the zip.

## The project file (`voices.yaml`)

```yaml
project: my-voices            # Kaggle names: my-voices-data, my-voices-part1, my-voices-check, ...
kaggle:
  username: your-kaggle-username

speakers:
  - id: narrator              # lowercase letters, digits, - and _; used in file names
    builtin: Karim            # a VoiceTut built-in voice
  - id: grandma
    clip: clips/grandma.ogg   # your own clip (any format ffmpeg reads), relative to this file
    transcript: "يا حبيبي تعالى نقعد شوية"   # exactly the words said in the clip
  - id: robot
    instruct: "male, low pitch"   # a voice description (OmniVoice voice design; results vary)

sentences: sentences.json
pronunciation: pronunciation.json   # optional

recording: {parts: 1, num_step: 48, hours: 11}
check:     {threshold: 0.15, max_takes: 4}
export:    {bitrate: 20k, format: webm}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `project` | — | Prefix of every Kaggle name. 3–41 lowercase letters, digits, dashes. |
| `kaggle.username` | — | Your Kaggle username (the dataset and notebooks are created there, private). |
| `speakers[].builtin` | — | A built-in voice: `Ahmed Ali Hassan Karim Mahmoud Mohammed Mostafa Ramy Shaker Tareq Yehia Youssef` (male), `Hadeer Hanan Mariam Rana Sarah Yasmin Yara` (female). |
| `speakers[].clip` + `transcript` | — | Clone this voice. The transcript must match the clip word for word. |
| `speakers[].instruct` | — | Describe a voice instead (passed to VoiceTut as `instruct`). |
| `recording.parts` | 1 | Notebooks the speakers are split over (each one is a separate Kaggle run). |
| `recording.num_step` | 48 | VoiceTut quality steps. 16 is about 3× faster but sounds rougher. |
| `recording.hours` | 11 | When to stop recording and pack the results (Kaggle stops runs at 12 h). |
| `check.threshold` | 0.15 | Re-record when more than this share of letters is heard wrong. |
| `check.max_takes` | 4 | The first recording plus up to 3 new takes; the best take is kept. |
| `export.bitrate` / `format` | `20k` / `webm` | Opus bitrate, and `webm` or `ogg`. |

**`sentences.json`** is either a plain list (every speaker says every line):

```json
["أهلاً وسهلاً!", "يلا نبدأ."]
```

or shared lines plus lines for particular speakers (which come after the shared ones):

```json
{
 "shared": ["أهلاً وسهلاً!", "يلا نبدأ."],
 "per_speaker": {"narrator": ["أنا الراوي."], "guide": ["أنا المرشدة."]}
}
```

Shared items may also be objects with a `"text"` key (other keys are ignored), so a list your app
generates can be used directly.

## Fixing pronunciation

VoiceTut reads unvowelled text, and its own text normalizer **removes the vowel marks
(harakat) and shadda** you write. So `عدّ` is read as `عد`. To control pronunciation, `vk` vowels
the text itself, using your pronunciation file, and passes the result to VoiceTut with
`normalize=False`. For each sentence it:

1. removes any marks you wrote and turns Arabic digits into Western ones,
2. if the whole sentence is in `"lines"`, uses that spelling as is,
3. otherwise replaces `"phrases"` (for words said differently depending on the words around
   them), reads numbers as Egyptian Arabic words, and vowels each remaining word from `"words"`,
   falling back to VoiceTut's own word list.

```json
{
 "words":   {"النهارده": "النَّهَارْدَه", "تفاحات": "تُفَّاحَات"},
 "phrases": {"خطوة بخطوة": "خُطْوَة بْخُطْوَة"},
 "lines":   {"ممكن تعيد تاني؟": "مُمْكِن تْعِيد تَانِي؟"}
}
```

Keys are written **without** vowel marks, exactly as the words appear in your sentences.

**To fix a mispronounced word:**

1. Find it on the listening page (`vk listen …`), or by ear in the exported files.
2. Add the word to `"words"` with the vowel marks you want, for example `"صح": "صَحّ"`. If it's
   only wrong in one sentence, add the whole sentence to `"lines"` instead.
3. Not sure which spelling sounds right? Try several with `vk fix`, pick by ear, and
   `vk use-take` prints the `"lines"` entry to keep.
4. To re-record many lines with the new spellings, run `vk record` again and start the parts
   (the pronunciation file is built into the notebooks, so no dataset upload is needed).

## Adding lines later

Add the new sentences to the **end of `"shared"`** in `sentences.json`. Never insert them in the
middle, or every clip after them would be misnumbered. If the old file had `S` shared sentences
and you add `K`, the new lines are numbers `S … S+K-1`, and each speaker's own lines move up by
`K`. Then record and check only those lines, and merge them in:

```bash
vk dataset --upload && vk new-lines 4-5 && vk push new-lines
```

```bash
vk fetch new-lines && vk merge voices_final.zip build/out/new-lines/voices_checked.zip 4-5 voices_new.zip
```

`merge` shifts the old per-speaker clips up and slots the new ones in, so `voices_new.zip`
matches the new `sentences.json` line for line. The new-lines notebook records the lines itself
(it needs no recordings as input) and checks them with the same re-take rules.

## Kaggle limits

These are the limits at the time of writing. Kaggle changes them now and then, so check your
account page.

- **2 GPU sessions at once.** A third push fails with *Maximum batch GPU session count*
  (`vk watch` waits and retries).
- **GPU T4 ×2 per session:** two 16 GB T4 GPUs. The notebooks run one worker per GPU.
- **About 30 GPU hours a week**, reset weekly. Your remaining quota is shown on kaggle.com. Each
  running notebook uses quota for as long as it runs.
- **12 hours per run.** Recording stops at `recording.hours` (default 11) to leave time to pack
  the results. A part that doesn't finish can be resumed (see step 2).
- **Notebooks must be under 1 MB.** That's why the sentences and clips are in a dataset.
- The dataset and notebooks are created **private**.

## Troubleshooting

**`ModuleNotFoundError: No module named 'six'` on `vk dataset --upload`.** Kaggle 2.2.5 imports `six` and does not install it. Install this project again (`pip install -e .`); `six` is one of its dependencies.

**HTTP 429 (Too Many Requests) when downloading output.** `kaggle kernels output` lists 20 files
per request and walks through the whole output, so a notebook with thousands of files trips the
rate limit. Use `vk fetch`, which asks for 500 per request and stops early. If you still get a
429, wait a few minutes and try again.

**`pip install` times out in a notebook** (`ReadTimeoutError`, PyPI). The notebooks already use
`pip install --timeout 60 --retries 10`. If it still fails, Kaggle's network was having a bad
moment: run the notebook again.

**"This notebook got an older version of the … dataset".** You uploaded a new dataset version,
but Kaggle attached the previous one, which happens when a notebook starts before the new version
is processed. `vk dataset --upload` waits for *ready*. If you uploaded another way, check with
`kaggle datasets status <username>/<project>-data`, then push the notebook again. Also run
`vk dataset --upload` after any change to speakers, clips or sentences: each notebook checks that
the dataset matches what it was built from.

**"Maximum batch GPU session count of 2 reached".** Two GPU notebooks are already running (yours,
from any project). Wait for one to finish, or let `vk watch` retry. Stop a stray run on
kaggle.com (*Your Work* → the notebook → *Cancel run*).

**A notebook ended with ERROR.** Open it on kaggle.com and read the log. Common causes: phone not
verified (no GPU or internet), the dataset not attached (re-push from `build/kaggle/<name>`, whose
`kernel-metadata.json` lists it), or a wrong clip path.

**`vk fetch` says the output has no voices_checked.zip.** The notebook hasn't finished, or it
failed. Check with `kaggle kernels status <username>/<project>-check`.

**A cloned voice sounds off.** Use a cleaner clip (one speaker, no music or echo, 5–15 s), and
make sure `transcript` matches the clip word for word.

## Licenses

This project's code is released under the **Apache License 2.0** (see `LICENSE`). It downloads
and runs these models, which have their own terms:

| Model / package | License (as stated by its authors) |
|-----------------|-------------------------------------|
| [VoiceTut-TTS](https://huggingface.co/mohammedaly22/VoiceTut-TTS) and the `voicetut-tts` package | Apache-2.0. Fine-tuned from OmniVoice. |
| [OmniVoice](https://github.com/k2-fsa/OmniVoice), the base model | Code: Apache-2.0. **Pretrained model: CC BY-NC 4.0** (non-commercial), "due to constraints from its training data". |
| [QwenCleo-ASR](https://huggingface.co/mohammedaly22/QwenCleo-ASR) and the `qwen-asr` package | Apache-2.0, inheriting the license terms of its base, [Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) (Apache-2.0). |

**Before any commercial use**, read those licenses yourself. VoiceTut-TTS is labeled Apache-2.0,
but it's built on OmniVoice's pretrained model, which is licensed for **non-commercial use only**.
Whether that restriction carries over to VoiceTut-TTS and to the audio it makes is a legal
question this project can't answer for you. Both OmniVoice and VoiceTut-TTS forbid voice cloning
without consent, impersonation and fraud. This summary isn't legal advice. Licenses were checked
in November 2026.

## Using it with an AI assistant

AI coding assistants (Claude Code, Cursor, Codex and others) can run the whole pipeline for you
through the `vk` command. The repo has [AGENTS.md](AGENTS.md) for them: the commands, which ones
use Kaggle GPU time, and the rules they must follow. Cursor and Codex read `AGENTS.md` on their
own; `CLAUDE.md` points Claude Code to it.

Open this repo (or your project folder, see below) in your assistant and ask in plain words:

- "Set up a project in ~/my-voices with two built-in voices, narrator Karim and guide Yasmin,
  and these sentences: …"
- "Upload the dataset and start recording." It asks before anything that uses GPU time.
- "Is the check done? Download the results and tell me which lines are flagged."
- "Line 2 of the narrator sounds wrong: try صَحّ and صَحْ, two takes each."
- "Use take narrator_002_b1 and export the audio for my app."

What `AGENTS.md` tells the assistant:

- **Ask you first** before `vk watch`, `vk push` or recording again, since those use your
  GPU hours, and before the first dataset upload.
- **Never print or copy your token.** It only checks that one exists.
- Check progress with `vk status` (one line per notebook), at most once a minute, and read a
  failed notebook's log with `kaggle kernels output`.
- Only use voice clips you say you have consent for.

**If your assistant works in another folder** (for example your app's repo): install the package
into the Python it uses (`pip install -e /path/to/voicetut-kaggle`), then point it at the rules.
In Claude Code, add this line to that folder's `CLAUDE.md`:

```
@/path/to/voicetut-kaggle/AGENTS.md
```

In Cursor or Codex, copy `AGENTS.md` into that folder, or add a line to its own `AGENTS.md` saying
to follow `/path/to/voicetut-kaggle/AGENTS.md` for voice work.

## Development

```bash
pip install -e . && python -m unittest discover -s tests
```

The tests build every notebook from a copy of `examples/demo`, then run the notebooks' code on
your machine with stand-ins for the GPU models (`tests/fakes`). That covers recording, the check
with re-takes, the listening pages, fix and use-take, new lines and merge, and export (which needs
ffmpeg). They don't touch Kaggle.

Code map (`voicetut_kaggle/`): `config.py` reads `voices.yaml` · `dataset.py` step 1 ·
`record.py` / `watch.py` step 2 · `check.py` steps 3 and 7 · `kaggle.py` push, status and fetch ·
`listen.py` step 5 · `fix.py` step 6 · `merge.py` step 7 · `export.py` step 8 · `notebooks.py`
code shared by all notebooks · `pronounce.py` the vowelling, copied into every notebook ·
`desktop_project.py` / `desktop_api.py` what the desktop window (`desktop/`) reads and saves.
