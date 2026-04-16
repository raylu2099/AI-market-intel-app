#!/bin/bash
# market-intel setup script — one-shot install for a fresh host.
# Creates a venv, installs deps, and seeds .env from .env.example.
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "=== market-intel setup ==="
echo "Project dir: $PROJECT_DIR"

# --- Pick a Python interpreter ---
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    for cand in python3.12 python3.11 python3.10 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            ver=$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                PYTHON="$cand"
                break
            fi
        fi
    done
fi

if [ -z "$PYTHON" ]; then
    echo "ERROR: need Python 3.10+ on PATH (or set PYTHON=/path/to/python3)." >&2
    exit 1
fi

echo "Using Python: $PYTHON ($("$PYTHON" --version))"

# --- venv ---
if [ ! -d .venv ]; then
    echo "Creating .venv..."
    "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
echo "Dependencies installed."

# --- .env ---
if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
    echo "Created .env from .env.example. Edit it with your secrets before running."
else
    echo ".env already exists, leaving it alone."
fi

# --- Runtime dirs ---
mkdir -p data/sources data/analyses data/pushes logs

echo
echo "Setup complete."
echo "Next steps:"
echo "  1. Edit .env with your PERPLEXITY_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
echo "  2. MARKET_INTEL_DRY=1 ./bin/run-slot.sh china_open    # dry-run test"
echo "  3. ./bin/install-cron.sh                              # install scheduled tasks"
