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

# Detect Python env: prefer project .venv, fall back to micromamba ytdlp env
MICROMAMBA="/volume1/homes/hellolufeng/bin/micromamba"
MAMBA_YTDLP_PYTHON="/volume1/homes/hellolufeng/micromamba/envs/ytdlp/bin/python3"

if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
elif [ -x "$MAMBA_YTDLP_PYTHON" ]; then
    # Direct path — works regardless of $HOME or cron user (root vs hellolufeng)
    PYTHON="$MAMBA_YTDLP_PYTHON"
    export MAMBA_ROOT_PREFIX="/volume1/homes/hellolufeng/micromamba"
else
    PYTHON="python3"
fi

# Export CLAUDE_ROLE so hooks skip Telegram notifications for cron runs
export CLAUDE_ROLE=cron-intel

# Set PATH to include claude CLI and micromamba tools (absolute paths for cron/root)
OWNER_HOME="/volume1/homes/hellolufeng"
export PATH="$OWNER_HOME/.local/bin:$OWNER_HOME/bin:$OWNER_HOME/micromamba/envs/ytdlp/bin:$PROJECT_DIR/.venv/bin:$PATH"
export HOME="$OWNER_HOME"

cd "$PROJECT_DIR"

echo "[$(date '+%F %T %Z')] slot=$SLOT starting" >> "$LOG"
"$PYTHON" -m intel.run "$SLOT" >> "$LOG" 2>&1
RC=$?
echo "[$(date '+%F %T %Z')] slot=$SLOT exit=$RC" >> "$LOG"
exit $RC
