#!/bin/bash
# Share Tablemates through a temporary public HTTPS link (Cloudflare quick tunnel).
# Runs a separate copy of the site on port 5051 so the local one on 5050 keeps working.
cd "$(dirname "$0")" || exit 1
echo "== Tablemates: share with a public link =="
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Installing cloudflared with Homebrew (first time only)..."
  brew install cloudflared || { echo "Could not install cloudflared."; read -r -p "Press Enter to close..."; exit 1; }
fi
if [ ! -x .venv/bin/python ]; then
  echo "Please run start-tablemates.command once first (it sets up the database and Python)."
  read -r -p "Press Enter to close..."; exit 1
fi

# Same database settings as the local launcher (Homebrew PostgreSQL, current Mac user)
for d in /opt/homebrew/opt/postgresql@*/bin /opt/homebrew/bin /usr/local/bin /Applications/Postgres.app/Contents/Versions/latest/bin /Library/PostgreSQL/*/bin; do
  [ -x "$d/pg_isready" ] && export PATH="$d:$PATH" && break
done
pg_isready -q -h localhost || { echo "PostgreSQL is not running. Run start-tablemates.command first."; read -r -p "Press Enter to close..."; exit 1; }
export DATABASE_URL="${DATABASE_URL:-postgresql://$USER@localhost:5432/friend_review}"

LOG=$(mktemp -t tablemates-tunnel)
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5051 >"$LOG" 2>&1 &
TUNNEL_PID=$!
trap 'kill $TUNNEL_PID 2>/dev/null' EXIT
echo "Creating public link..."
URL=""
for i in $(seq 1 40); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "$URL" ] && break; sleep 1
done
if [ -z "$URL" ]; then echo "Could not create a link. Log:"; cat "$LOG"; read -r -p "Press Enter to close..."; exit 1; fi

printf '%s' "$URL" | pbcopy
echo
echo "=============================================================="
echo " Public link (already copied - just paste it to your team):"
echo "   $URL"
echo " Keep this window open. Close it to stop sharing."
echo " Anyone with the link can use the demo account, so share it only with your team."
echo "=============================================================="
echo
export APP_PORT=5051 FRONTEND_ORIGIN="$URL" APP_HTTPS=1 APP_SECRET_KEY="tablemates-share-$(date +%s)"
(sleep 4; open "$URL") &
.venv/bin/python run.py
