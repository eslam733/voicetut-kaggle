# Working with voicetut-kaggle (for AI assistants)

This repo records voice lines with VoiceTut-TTS on Kaggle's GPUs and checks them with speech
recognition. Drive it with the `vk` command. Don't write or edit Kaggle notebooks by hand: `vk`
builds them from the project file.

## Setup

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
```

- A **project** is a folder with `voices.yaml` (copy `examples/demo` to start). Run `vk` from that
  folder, or pass `-c <folder>/voices.yaml` before the command.
- The user's Kaggle token is in `~/.kaggle/access_token` (or `~/.kaggle/kaggle.json`). To check
  that one exists without reading it: `python -m voicetut_kaggle.desktop_api token` prints
  `"token": true/false`.

## Rules

1. **Ask before anything that uses Kaggle GPU time:** `vk watch`, `vk push <notebook>`, and running
   `vk record` followed by `vk watch` again (that records everything from the start). Say which
   notebooks will run. The user has about 30 free GPU hours a week.
2. **Ask before the first `vk dataset --upload`**: it creates a private dataset on the user's
   Kaggle account.
3. **Never print, copy or store the token.** Don't `cat` it, don't put it in `voices.yaml`, a
   script, a commit or a message.
4. **Voice clips need the speaker's consent.** Only use clips the user says they may use.
5. **Don't poll Kaggle faster than once a minute** (it answers HTTP 429). `vk watch` already waits
   5 minutes between checks; run it in the background and read its output.
6. **Don't edit files under `build/` by hand.** Re-run the command that makes them.
7. After changing sentences or speakers, run `vk dataset --upload` before `vk record` (`vk record`
   refuses otherwise, because the notebooks would stop on Kaggle with an old dataset).

## Commands

| Command | What it does | Kaggle cost |
|---|---|---|
| `vk dataset` | writes the dataset folder in `build/` | none |
| `vk dataset --upload` | uploads it as a new dataset version and waits until ready | no GPU |
| `vk record` | builds the recording notebooks `part1..N` and the `check` notebook | none |
| `vk watch` | pushes the parts as GPU slots free up, then the check | **GPU** |
| `vk watch --resume` | follows a run already started; pushes only what was not pushed | GPU only for unpushed parts |
| `vk status` | one line: each notebook's state (`QUEUED`, `RUNNING`, `COMPLETE`, `ERROR`, `NONE`) | none |
| `vk fetch check` | downloads `voices_checked.zip` (says so if the check is not finished) | none |
| `vk listen <zip> [--all]` | writes a local page to listen to the lines | none |
| `vk fix <fixes.yaml>` then `vk push fix` | re-records chosen lines with spellings to try | **GPU** |
| `vk fetch fix` | downloads `fix.zip` with the takes | none |
| `vk use-take <fix.zip> <base.zip> <out.zip> <take>...` | swaps picked takes in, prints spellings to keep | none |
| `vk new-lines FIRST-LAST`, `vk push new-lines`, `vk merge ...` | records lines added later without renumbering | **GPU** for the push |
| `vk export <zip> [--out DIR]` | small Opus files and `lines.json` for an app (needs ffmpeg) | none |
| `vk eleven credits` | characters left on the user's ElevenLabs plan | none |
| `vk eleven voices [--list]` | clones each speaker's clip into an ElevenLabs voice once (or lists the account's voices) | ElevenLabs voice slots |
| `vk eleven record FIRST-LAST` or `--fixes FILE` | records takes with ElevenLabs into `build/out/eleven/eleven.zip` (fix.zip form) | **the user's paid characters**: it asks first |

Line `n` of a speaker is the shared sentences first, then that speaker's own sentences. Takes are
named `<speaker>_<nnn>_<variant><take>`, for example `narrator_002_b1`.

## A typical run

```bash
vk dataset --upload          # ask the user first the first time
vk record
vk watch                     # ask first: GPU. Run in the background; it ends when the check starts
vk status                    # later: is the check COMPLETE?
vk fetch check
vk listen build/out/check/voices_checked.zip --all
vk export build/out/check/voices_checked.zip
```

To fix a line: write a fixes file like `examples/demo/fixes.yaml` (line, speakers, spellings
with vowel marks, takes), then `vk fix fixes.yaml`, ask, `vk push fix`, wait for `vk status`,
`vk fetch fix`, `vk listen build/out/fix/fix.zip --compare build/out/check/voices_checked.zip`,
and `vk use-take` with the take the user picks. Add the printed spelling to the pronunciation
file's `"lines"` so later recordings use it.

With ElevenLabs instead of Kaggle (paid, no GPU): `vk eleven credits`, `vk eleven voices`, then
`vk eleven record FIRST-LAST` (or `--fixes fixes.yaml`). It prints the characters it will spend
and asks; run it with `--yes` only after the user agreed to that number. Then `vk listen
build/out/eleven/eleven.zip --compare <voices zip>`: the user presses **use** on the takes they
want, and the page shows the `vk use-take` command to run. Never print or commit the API key.

## When a notebook fails

`vk status` shows `ERROR`. Read its log (no GPU):

```bash
kaggle kernels output <username>/<project>-part1 -p /tmp/vk-log
```

The log is `/tmp/vk-log/<project>-part1.log`, a JSON list; the error is near the end. A common
one is "got an older version of the dataset": upload the dataset, then record again.

## Changing the code

- Tests: `python -m unittest discover -s tests`. They never call Kaggle.
- The desktop app is in `desktop/` (Tauri). It runs the same `vk` commands; build and install it
  with `desktop/install.sh`.
- Keep the repo free of tokens, real voices and private sentences: `.gitignore` already excludes
  tokens, `build/` and audio files.
