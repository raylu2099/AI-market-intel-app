#!/bin/bash
# Health check for market-intel. Tests each integration.
# Usage: ./bin/doctor.sh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# Detect Python
if [ -f .venv/bin/python ]; then
    PY=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
else
    echo "FAIL: no Python found"
    exit 1
fi

echo "=== market-intel doctor ==="
echo

$PY -c "
import sys, os, json, urllib.request, urllib.parse
from pathlib import Path

os.chdir('$PROJECT_DIR')
sys.path.insert(0, '.')

ok = 0
fail = 0

def check(name, fn):
    global ok, fail
    try:
        result = fn()
        print(f'  ✅ {name}: {result}')
        ok += 1
    except Exception as e:
        print(f'  ❌ {name}: {e}')
        fail += 1

# 1. Config loads
def test_config():
    from intel.config import load_config
    cfg = load_config()
    return f'watchlist={[t for t,_ in cfg.watchlist]}'
check('Config', test_config)

# 2. Perplexity API
def test_pplx():
    from intel.config import load_config
    cfg = load_config()
    body = json.dumps({'model':'sonar','messages':[{'role':'user','content':'ping'}],'max_tokens':5}).encode()
    req = urllib.request.Request('https://api.perplexity.ai/chat/completions',data=body,method='POST',
        headers={'Authorization':f'Bearer {cfg.perplexity_api_key}','Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    return f'model={d[\"model\"]}'
check('Perplexity API', test_pplx)

# 3. Telegram
def test_tg():
    from intel.config import load_config
    cfg = load_config()
    data = urllib.parse.urlencode({'chat_id':cfg.telegram_chat_id,'text':'🩺 market-intel doctor health check','disable_notification':'true'}).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode())
    return f'ok={d[\"ok\"]}'
check('Telegram Bot', test_tg)

# 4. yfinance
def test_yf():
    import yfinance as yf
    fi = yf.Ticker('NVDA').fast_info
    p = getattr(fi, 'last_price', None)
    return f'NVDA=\${p:.2f}' if p else 'no data'
check('yfinance', test_yf)

# 5. trafilatura
def test_traf():
    import trafilatura
    html = trafilatura.fetch_url('https://www.scmp.com/news/china')
    if not html:
        raise Exception('fetch failed')
    txt = trafilatura.extract(html)
    return f'{len(txt or \"\")} chars from SCMP'
check('trafilatura', test_traf)

# 6. Claude CLI
def test_claude():
    import subprocess
    r = subprocess.run(
        ['claude','--print','--dangerously-skip-permissions','--tools','',
         '--disable-slash-commands','--no-session-persistence','--output-format','text',
         'Reply with exactly: HEALTH_OK'],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, 'CLAUDE_ROLE':'cron-intel'}
    )
    if 'HEALTH_OK' in r.stdout:
        return 'claude -p responding'
    raise Exception(r.stderr[:200] or 'no HEALTH_OK in output')
check('Claude CLI', test_claude)

# 7. Data dirs
def test_dirs():
    from intel.config import load_config
    cfg = load_config()
    for d in [cfg.data_dir, cfg.logs_dir, cfg.prompts_dir]:
        if not d.exists():
            raise Exception(f'{d} missing')
    return 'all dirs exist'
check('Data dirs', test_dirs)

print()
print(f'Result: {ok} passed, {fail} failed')
sys.exit(1 if fail else 0)
"
