#!/usr/bin/env bash
# Dream Built: one-command install for Apple-silicon Macs.
#
#   curl -fsSL https://raw.githubusercontent.com/RyFinance/dreambuilt/main/install.sh | bash
#
# Clones the repo (or updates it), sets up Python, downloads the local AI model
# (MiniCPM5-2B from Hugging Face, about 1.4 GB, once) and puts "Dream Built" in
# ~/Applications. Run it again any time to update.
set -euo pipefail

REPO="https://github.com/RyFinance/dreambuilt.git"
DIR="${DREAMBUILT_DIR:-$HOME/DreamBuilt}"
say() { printf "\033[38;5;173m▸\033[0m %s\n" "$*"; }
die() { printf "\033[31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "Dream Built runs on macOS."
[[ "$(uname -m)" == "arm64" ]] || die "Dream Built needs an Apple-silicon Mac (M1 or later)."
command -v git >/dev/null || die "git is missing: run  xcode-select --install"

PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$p" >/dev/null && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$p"; break
  fi
done
[[ -n "$PY" ]] || die "Python 3.10+ is needed: https://www.python.org/downloads/ or  brew install python"

if [[ -d "$DIR/.git" ]]; then
  say "Updating $DIR"
  git -C "$DIR" pull --ff-only --quiet
else
  say "Downloading Dream Built to $DIR"
  git clone --depth 1 --quiet "$REPO" "$DIR"
fi
cd "$DIR"

if [[ ! -x .venv/bin/python ]]; then
  say "Setting up Python ($("$PY" --version))"
  "$PY" -m venv .venv
fi
say "Installing packages (about 750 MB, first time only)"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[app,llm]"

say "Getting the AI model (MiniCPM5-2B, about 1.4 GB, first time only)"
.venv/bin/dreambuilt get-model

say "Adding Dream Built to ~/Applications"
.venv/bin/python tools/make_app.py --install >/dev/null

say "Done. Opening Dream Built."
open "$HOME/Applications/Dream Built.app" || true
