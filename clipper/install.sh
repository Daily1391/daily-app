#!/bin/bash
# Clipper installer and updater for Mac.
# Install or update with one line in Terminal:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daily1391/daily-app/claude/bot-creation-lcbtji/clipper/install.sh)"
# Updating keeps your key, YouTube login, music and clips.
set -e

DIR="${CLIPPER_DIR:-$HOME/Clipper}"
BASE="https://raw.githubusercontent.com/Daily1391/daily-app/claude/bot-creation-lcbtji/clipper"
FILES="clipper.py app.py requirements.txt Clipper.command README.md .streamlit/config.toml"

echo "Clipper will live in: $DIR"

# 1. Homebrew, Python and ffmpeg (skipped if already installed)
if [ -z "$SKIP_BREW" ]; then
  if ! command -v brew >/dev/null 2>&1; then
    if [ -x /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    else
      echo "Installing Homebrew. It will ask for your Mac password (typing shows nothing, that's normal)."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      eval "$(/opt/homebrew/bin/brew shellenv)"
      grep -q "brew shellenv" "$HOME/.zprofile" 2>/dev/null || \
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
    fi
  fi
  for pkg in python@3.12 ffmpeg-full; do
    if brew list --versions "$pkg" >/dev/null 2>&1; then
      echo "Already installed: $pkg"
    else
      echo "Installing $pkg (a few minutes)..."
      brew install "$pkg"
    fi
  done
fi

# 2. The app's own files. Your .env, token.json, client_secret.json, music and output stay put.
mkdir -p "$DIR/.streamlit"
for f in $FILES; do
  curl -fsSL -o "$DIR/$f.download" "$BASE/$f"
  mv "$DIR/$f.download" "$DIR/$f"
done
chmod +x "$DIR/Clipper.command"

echo ""
echo "Done. Double-click Clipper.command in the folder that just opened."
echo "To update later, run the same install line again."
[ -z "$SKIP_OPEN" ] && open "$DIR" 2>/dev/null || true
