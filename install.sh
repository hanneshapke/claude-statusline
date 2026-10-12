#!/usr/bin/env bash
# Installs the Claude Code status line into ~/.claude and registers it in settings.json.
set -euo pipefail

SRC="${STATUSLINE_URL:-https://raw.githubusercontent.com/hanneshapke/claude-statusline/main/statusline.py}"
DEST="$HOME/.claude/statusline.py"
SETTINGS="$HOME/.claude/settings.json"
PY="$(command -v python3 || true)"

[ -n "$PY" ] || { echo "python3 is required"; exit 1; }
mkdir -p "$HOME/.claude"

if [ -f "$(dirname "$0")/statusline.py" ]; then
  cp "$(dirname "$0")/statusline.py" "$DEST"
else
  curl -fsSL "$SRC" -o "$DEST"
fi
chmod +x "$DEST"

[ -f "$SETTINGS" ] && cp "$SETTINGS" "$SETTINGS.bak.pre-statusline"

"$PY" - "$SETTINGS" "$PY" "$DEST" <<'PYEOF'
import json, os, sys
path, py, dest = sys.argv[1:4]
s = json.load(open(path)) if os.path.exists(path) else {}
s["statusLine"] = {"type": "command", "command": f"{py} {dest}", "padding": 0, "refreshInterval": 30}
json.dump(s, open(path, "w"), indent=2)
PYEOF

echo "Installed. Open a new Claude Code session (or wait for the next refresh) to see the status line."
