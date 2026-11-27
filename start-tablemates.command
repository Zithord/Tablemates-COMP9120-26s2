#!/bin/bash
# Tablemates one-click launcher for macOS (no Docker needed).
cd "$(dirname "$0")" || exit 1
echo "== Tablemates launcher =="

# 1. Find PostgreSQL command-line tools
PGBIN=""
for d in /Library/PostgreSQL/*/bin /Applications/Postgres.app/Contents/Versions/latest/bin \
         /opt/homebrew/opt/postgresql@*/bin /opt/homebrew/bin /usr/local/opt/postgresql@*/bin /usr/local/bin; do
  [ -x "$d/psql" ] && PGBIN="$d"
done
if [ -z "$PGBIN" ]; then
  echo "Could not find PostgreSQL (psql). Install PostgreSQL (Homebrew, Postgres.app or the EDB installer) and run this file again."
  read -r -p "Press Enter to close..."; exit 1
fi
export PATH="$PGBIN:$PATH"
echo "PostgreSQL tools: $PGBIN"

# 2. Make sure the server is running, then work out how to log in
export PGHOST=localhost PGPORT=5432
if ! pg_isready -q; then
  echo "PostgreSQL server is not running - trying to start it..."
  BREW=$(command -v brew || ls /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1)
  if [ -n "$BREW" ]; then
    FORMULA=$("$BREW" list --formula 2>/dev/null | grep -E '^postgresql(@[0-9]+)?$' | sort -V | tail -1)
    if [ -n "$FORMULA" ]; then
      echo "Starting $FORMULA with Homebrew..."
      "$BREW" services start "$FORMULA"
      # Use the tools of the formula that is actually running
      [ -d "$("$BREW" --prefix "$FORMULA")/bin" ] && export PATH="$("$BREW" --prefix "$FORMULA")/bin:$PATH"
    fi
  fi
  for i in $(seq 1 20); do pg_isready -q && break; sleep 1; done
  if ! pg_isready -q; then
    echo "Could not start PostgreSQL automatically. Details:"; pg_isready
    read -r -p "Press Enter to close..."; exit 1
  fi
fi
echo "PostgreSQL server is running."
if psql -U "$USER" -d postgres -Atc 'select 1' >/dev/null 2>&1; then
  DBUSER="$USER"; PW=""
elif psql -U postgres -d postgres -w -Atc 'select 1' >/dev/null 2>&1; then
  DBUSER=postgres; PW=""
else
  echo "Note: $(psql -U "$USER" -d postgres -Atc 'select 1' 2>&1 | head -1)"
  DBUSER=postgres
  for attempt in 1 2 3; do
    read -r -s -p "Enter the password of PostgreSQL user 'postgres' (set when you installed it): " PW; echo
    export PGPASSWORD="$PW"
    if psql -U postgres -d postgres -Atc 'select 1' >/dev/null 2>&1; then break; fi
    ERR=$(psql -U postgres -d postgres -Atc 'select 1' 2>&1)
    echo "Login failed: $ERR"
    if echo "$ERR" | grep -qi "connection refused\|could not connect"; then
      echo "PostgreSQL server is not running. Start it (pgAdmin / Postgres.app) and run this file again."
      read -r -p "Press Enter to close..."; exit 1
    fi
    [ "$attempt" = 3 ] && { read -r -p "Press Enter to close..."; exit 1; }
  done
fi
echo "Connected to PostgreSQL as $DBUSER"

# 3. Create database, tables and demo data (first run only)
if ! psql -U "$DBUSER" -d postgres -Atc "select 1 from pg_database where datname='friend_review'" | grep -q 1; then
  echo "Creating database friend_review..."
  createdb -U "$DBUSER" friend_review || { read -r -p "Press Enter to close..."; exit 1; }
fi
if ! psql -U "$DBUSER" -d friend_review -Atc "select to_regclass('public.app_user')" | grep -q app_user; then
  echo "Creating tables and views..."
  psql -q -v ON_ERROR_STOP=1 -U "$DBUSER" -d friend_review -f sql/init/01_schema.sql || { read -r -p "Press Enter to close..."; exit 1; }
  psql -q -v ON_ERROR_STOP=1 -U "$DBUSER" -d friend_review -f sql/init/02_views.sql || { read -r -p "Press Enter to close..."; exit 1; }
fi

# 4. Python environment (first run only)
if [ ! -x .venv/bin/python ]; then
  echo "Setting up Python environment (first run, about 1 minute)..."
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt \
    || { echo "Python package install failed."; read -r -p "Press Enter to close..."; exit 1; }
fi

ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$PW")
if [ -n "$PW" ]; then
  export DATABASE_URL="postgresql://$DBUSER:$ENC@localhost:5432/friend_review"
else
  export DATABASE_URL="postgresql://$DBUSER@localhost:5432/friend_review"
fi

if [ "$(psql -U "$DBUSER" -d friend_review -Atc 'select count(*) from app_user')" = "0" ]; then
  echo "Importing demo data..."
  .venv/bin/python scripts/seed_data.py || { read -r -p "Press Enter to close..."; exit 1; }
fi

# 5. Start the website on port 5050 (macOS AirPlay uses 5000)
export APP_PORT=5050 APP_SECRET_KEY="tablemates-local-demo"
echo
echo "Website: http://127.0.0.1:5050/   (keep this window open; press Ctrl+C to stop)"
(sleep 3; open "http://127.0.0.1:5050/") &
exec .venv/bin/python run.py
