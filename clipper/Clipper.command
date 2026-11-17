#!/bin/bash
# Double-click to start Clipper. Keep this window open while you use it.
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ ! -x .venv/bin/python ]; then
  echo "First run: installing (takes a few minutes)..."
  PY=$(command -v python3.12 || command -v python3)
  "$PY" -m venv .venv || { echo "Python not found. Run: brew install python@3.12"; read -r; exit 1; }
fi
.venv/bin/pip install -q -r requirements.txt || { echo "Install failed. Send a screenshot."; read -r; exit 1; }

# Skip Streamlit's one-time "enter your email" prompt
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
  mkdir -p "$HOME/.streamlit" && printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

echo "Clipper is running. Your browser will open. Close this window to stop it."
exec .venv/bin/python -m streamlit run app.py
