#!/usr/bin/env bash
# Starts Little Worlds for a live run. Secrets are typed at hidden prompts and exist only in this process:
# they are never written to a file, never put on the command line and never shown on screen.
#   scripts/start.sh
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || { echo "Run first:  python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"; exit 1; }

secret() { # name, label: ask with hidden input unless already set
  if [ -z "${!1}" ]; then read -r -s -p "$2: " value; echo; export "$1=$value"; fi
}
plain() {
  if [ -z "${!1}" ]; then read -r -p "$2: " value; export "$1=$value"; fi
}
secret OPENAI_API_KEY "OpenAI API key"
plain TWITCH_CLIENT_ID "Twitch client ID"
secret TWITCH_CLIENT_SECRET "Twitch client secret"
if [ -z "${PUBLIC_VIEWER_ORIGIN+x}" ]; then
  read -r -p "Tunnel address from cloudflared (blank = this computer only): " PUBLIC_VIEWER_ORIGIN
fi
[ -n "$PUBLIC_VIEWER_ORIGIN" ] && export PUBLIC_VIEWER_ORIGIN || unset PUBLIC_VIEWER_ORIGIN
export LITTLE_WORLDS_AI_ART="${LITTLE_WORLDS_AI_ART:-1}"
# Per-room cap on AI image attempts (previews, polish and !draw share it). The default stays at the approved 10;
# raise it deliberately, e.g.  LITTLE_WORLDS_ART_LIMIT=30 scripts/start.sh
export LITTLE_WORLDS_ART_LIMIT="${LITTLE_WORLDS_ART_LIMIT:-10}"
echo "AI attempts allowed per room: $LITTLE_WORLDS_ART_LIMIT"

"$PY" scripts/preflight.py
exec "$PY" server.py
