#!/usr/bin/env bash
# One-time setup of the VoiceTut Kaggle desktop app on Linux. Afterwards it is in the application
# menu and opens with a click. Run it again to update the app after pulling new code.
#
#   desktop/install.sh
#
# It changes nothing it does not need to, and never runs sudo: when system packages are missing
# it prints the one apt-get line to run, then stops.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/voicetut-kaggle"
NAME=voicetut-kaggle-desktop
WM_CLASS=voicetut-kaggle-desktop

# Tauri 2's Debian/Ubuntu build prerequisites, then what the app needs to run. The venv brings
# its own pip, so python3-pip is not needed.
BUILD_PACKAGES=(build-essential curl wget file libwebkit2gtk-4.1-dev libxdo-dev libssl-dev
                libayatana-appindicator3-dev librsvg2-dev)
RUN_PACKAGES=(python3 python3-venv ffmpeg)

step() { printf '\n== %s\n' "$*"; }

step "System packages"
if command -v dpkg-query >/dev/null; then
  missing=()
  for package in "${BUILD_PACKAGES[@]}" "${RUN_PACKAGES[@]}"; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed" \
      || missing+=("$package")
  done
  if ((${#missing[@]})); then
    echo "Missing: ${missing[*]}"
    echo "Install them, then run this script again:"
    echo
    echo "  sudo apt-get install -y ${missing[*]}"
    exit 1
  fi
  echo "all present"
else
  echo "Not a Debian/Ubuntu system: install Tauri's Linux prerequisites, python3 (with venv) and"
  echo "ffmpeg with your package manager (https://v2.tauri.app/start/prerequisites/). Continuing."
fi

if ! command -v npm >/dev/null; then
  echo "npm is missing: install Node.js 18 or newer, then run this script again."
  exit 1
fi

step "Rust"
if ! command -v cargo >/dev/null && [ -f "$HOME/.cargo/env" ]; then
  . "$HOME/.cargo/env"
fi
if ! command -v cargo >/dev/null; then
  echo "installing Rust for this user with rustup (no sudo)"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --profile minimal
  . "$HOME/.cargo/env"
fi
cargo --version

step "Python environment in $APP/venv"
mkdir -p "$APP"
[ -x "$APP/venv/bin/python" ] || python3 -m venv "$APP/venv"
PIP=("$APP/venv/bin/python" -m pip install --quiet --timeout 60 --retries 10)
"${PIP[@]}" "$REPO"
# Same version number as the last install, new code: replace the package itself.
"${PIP[@]}" --no-deps --force-reinstall "$REPO"
"$APP/venv/bin/kaggle" --version

step "Building the app (the first build takes several minutes)"
cd "$REPO/desktop"
npm ci --no-audit --no-fund
npm run tauri build -- --no-bundle
install -m 755 "src-tauri/target/release/$NAME" "$APP/$NAME"

step "Menu entry"
install -Dm644 src-tauri/icons/128x128@2x.png "$DATA/icons/hicolor/256x256/apps/$NAME.png"
mkdir -p "$DATA/applications"
# Desktop files do not expand ~ or $HOME, so this writes the full path.
cat > "$DATA/applications/$NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=VoiceTut Kaggle
Comment=Record voice lines on Kaggle GPUs
Exec="$APP/$NAME"
Icon=$NAME
Terminal=false
Categories=AudioVideo;Audio;
StartupWMClass=$WM_CLASS
EOF
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$DATA/applications" || true
fi
if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "$DATA/icons/hicolor" || true
fi

echo
echo "Done. Open VoiceTut Kaggle from the application menu."
echo "App: $APP/$NAME"
