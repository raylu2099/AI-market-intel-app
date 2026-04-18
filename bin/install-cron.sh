#!/bin/bash
# Install cron entries for market-intel. Idempotent.
# Works on Synology DSM (/etc/crontab) and standard Linux (user crontab).
#
# Usage: sudo bash install-cron.sh        (Synology, needs root for /etc/crontab)
#        bash install-cron.sh             (standard Linux, user crontab)
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$PROJECT_DIR/bin/run-slot.sh"
USER="${CRON_USER:-$(whoami)}"
MARKER="# === market-intel slots ==="

# All times in the NAS local timezone (cron runs in system TZ)
# Simplified for long-term value investor focus: retains Claude-driven deep
# analysis (close, china_open, weekly_review) + per-stock news (Ray reads
# occasionally). Removed short-term slots (premarket, open, midday, watchdog)
# per user directive 2026-04-17 (shift to value-investing paradigm).
CRON_BLOCK="$MARKER
# Deep analysis slots (Claude)
30 18 * * * $USER $RUNNER china_open
0 13 * * 1-5 $USER $RUNNER close
# Per-stock news (occasional reading)
30 5 * * 1-5 $USER $RUNNER stocks_pre
30 13 * * 1-5 $USER $RUNNER stocks_post
# Weekly review (Fridays 14:00 PT)
0 14 * * 5 $USER $RUNNER weekly_review"

# Also remove old market-push entries if present
OLD_MARKER_1="# === Market push tasks ==="
OLD_MARKER_2="# === Stock news tasks ==="

install_synology() {
    CRONTAB="/etc/crontab"
    echo "Synology mode: editing $CRONTAB"

    # Remove old market-push entries if present
    for marker in "$OLD_MARKER_1" "$OLD_MARKER_2"; do
        if grep -q "$marker" "$CRONTAB" 2>/dev/null; then
            # Remove from marker line to next blank/marker line
            sed -i "/$marker/,/^$/d" "$CRONTAB"
            echo "  Removed old block: $marker"
        fi
    done

    if grep -q "$MARKER" "$CRONTAB" 2>/dev/null; then
        echo "  market-intel cron already present, skipping."
    else
        printf '\n%s\n' "$CRON_BLOCK" >> "$CRONTAB"
        echo "  Added market-intel cron block."
    fi

    # Reload
    if command -v synoservicectl >/dev/null 2>&1; then
        synoservicectl --reload crond 2>/dev/null || true
    elif command -v systemctl >/dev/null 2>&1; then
        systemctl restart cron 2>/dev/null || true
    fi
    echo "  crond reloaded."
}

install_standard() {
    echo "Standard Linux mode: editing user crontab"
    CURRENT="$(crontab -l 2>/dev/null || true)"
    if echo "$CURRENT" | grep -q "$MARKER"; then
        echo "  market-intel cron already present, skipping."
        return
    fi
    # Strip USER field from entries (user crontab doesn't use it)
    ENTRIES=$(echo "$CRON_BLOCK" | sed "s| $USER | |")
    echo "$CURRENT"$'\n'"$ENTRIES" | crontab -
    echo "  Added market-intel cron entries."
}

chmod +x "$RUNNER"

# A4: Timezone validation warning
SYSTEM_TZ=$(readlink -f /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||' || cat /etc/timezone 2>/dev/null || echo "unknown")
MARKET_TZ=$(grep "^MARKET_TZ=" "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "US/Pacific")
echo "System TZ: $SYSTEM_TZ"
echo "MARKET_TZ: $MARKET_TZ"
if [ "$SYSTEM_TZ" != "$MARKET_TZ" ] && [ "$SYSTEM_TZ" != "unknown" ]; then
    echo ""
    echo "⚠️  WARNING: System timezone ($SYSTEM_TZ) differs from MARKET_TZ ($MARKET_TZ)."
    echo "   Cron fires based on system TZ. If this is intentional (e.g. NAS in PT"
    echo "   but you set MARKET_TZ for label display), this is fine."
    echo "   If not, adjust cron times in the block below to match your market."
    echo ""
fi

if [ -f /etc/synoinfo.conf ] || [ -f /etc/crontab ] && [ "$(id -u)" = "0" ]; then
    install_synology
else
    install_standard
fi

echo "Done. Verify with: grep market-intel /etc/crontab  (or crontab -l)"
