# VoiceTut Kaggle desktop app

A Tauri 2 window for the `vk` pipeline. The page (`src/`) is plain HTML, CSS and JavaScript.
The Rust shell (`src-tauri/`) starts the Python package from its own virtualenv and passes its
answers and output to the page. The work itself is the Python code: `voicetut_kaggle.desktop_api`
for opening and saving a project and the Kaggle token, and the usual `vk` commands for every step.

## Linux

```bash
desktop/install.sh
```

The script:

1. Checks Tauri's build packages and `python3`, `python3-venv`, `ffmpeg`. When some are missing it
   prints the one `sudo apt-get install -y ...` line to run, and stops. Run it, then run the
   script again.
2. Installs Rust for your user with rustup, if `cargo` is missing.
3. Creates `~/.local/share/voicetut-kaggle/venv` and installs this repo into it.
4. Builds the app and copies it to `~/.local/share/voicetut-kaggle/voicetut-kaggle-desktop`.
5. Adds the icon and `~/.local/share/applications/voicetut-kaggle-desktop.desktop`.

Then open **VoiceTut Kaggle** from the application menu. It opens `~/my-voices` when that folder
has a `voices.yaml`, or the folder given as its first argument.

Run the script again after pulling new code. To remove the app, delete
`~/.local/share/voicetut-kaggle`, the `.desktop` file and the icon
(`~/.local/share/icons/hicolor/256x256/apps/voicetut-kaggle-desktop.png`).

## Windows and Mac

The same Tauri project builds there (`npm ci`, then `npm run tauri build`), giving a Start menu
shortcut from the NSIS or MSI installer on Windows and an `.app` in a `.dmg` on Mac. These builds
have not been made or tested yet, and one click is not enough there: the app expects Python 3.9+
with this package in a `venv` folder next to the app, and ffmpeg on `PATH`. No installer script
does that yet.

## Development

```bash
cd desktop
npm ci
VOICETUT_PYTHON=../.venv/bin/python npm run tauri dev
```

`VOICETUT_PYTHON` points the app at another Python environment than the one next to the binary.
