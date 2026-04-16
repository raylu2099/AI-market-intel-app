#!/bin/bash
# Cron wrapper for market-intel. Sets up env and runs a slot.
# Usage: run-slot.sh <slot_name>
set -e

SLOT="$1"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$PROJECT_DIR/logs/slot.log"
ENV_FILE="$PROJECT_DIR/.env"

if [ -z "$SLOT" ]; then
    echo "Usage: $0 <slot_name>" >&2
    exit 1
fi

# Truncate log if > 1MB
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt 1048576 ]; then
    tail -300 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# Detect Python env: prefer project .venv, fall back to micromamba
if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
elif [ -n "$MAMBA_ROOT_PREFIX" ]; then
    PYTHON="$(command -v python3 2>/dev/null || echo python3)"
elif [ -x "$HOME/bin/micromamba" ]; then
    export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/micromamba}"
    eval "$("$HOME/bin/micromamba" shell hook -s bash 2>/dev/null)" || true
    micromamba activate ytdlp 2>/dev/null || true
    PYTHON="$(command -v python3)"
else
    PYTHON="python3"
fi

# Export CLAUDE_ROLE so hooks skip Telegram notifications for cron runs
export CLAUDE_ROLE=cron-intel

# Set PATH to include claude CLI
export PATH="$HOME/.local/bin:$HOME/bin:$PROJECT_DIR/.venv/bin:$PATH"

cd "$PROJECT_DIR"

echo "[$(date '+%F %T %Z')] slot=$SLOT starting" >> "$LOG"
"$PYTHON" -m intel.run "$SLOT" >> "$LOG" 2>&1
RC=$?
echo "[$(date '+%F %T %Z')] slot=$SLOT exit=$RC" >> "$LOG"
exit $RC
