"""
Claude analyst runner. Two backends:

- "cli" (default): shells out to `claude -p` using the user's Claude Code
  subscription. No extra API cost but 10-20s cold-start per call.
- "api": calls the Anthropic Messages API directly with an API key. Faster
  and independent of Claude Code state, but billed per-token.

Both backends expose the same `analyze()` function: given a system prompt and
a user prompt, return a single string of assistant output.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from .config import Config


# Flags for the `claude -p` runner that keep it minimal:
#  --tools ""                 no tools available (pure text in -> text out)
#  --disable-slash-commands   skip loading skills
#  --no-session-persistence   don't write session state to disk
#  --dangerously-skip-permissions  match existing claude-tg/claude-rc pattern
#  --output-format text       plain stdout
#  --model <model>            pin analysis model
CLI_FLAGS = [
    "--print",
    "--dangerously-skip-permissions",
    "--tools", "",
    "--disable-slash-commands",
    "--no-session-persistence",
    "--output-format", "text",
]

# Env to set for cron `claude -p` runs so existing hooks skip Telegram
# notifications. Re-uses the existing CLAUDE_ROLE=rc convention.
CLI_ENV_OVERRIDES = {
    "CLAUDE_ROLE": "cron-intel",
}


def _run_cli(cfg: Config, system_prompt: str, user_prompt: str) -> str:
    # Use a temp system-prompt file; passing long text via argv is fragile.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as sp_file:
        sp_file.write(system_prompt)
        sp_path = sp_file.name

    cmd = [
        "claude",
        *CLI_FLAGS,
        "--model", cfg.claude_model,
        "--append-system-prompt-file", sp_path,
    ]

    env = os.environ.copy()
    env.update(CLI_ENV_OVERRIDES)
    # Run from a neutral cwd so the big parent CLAUDE.md is not auto-loaded.
    cwd = str(cfg.project_root)

    try:
        result = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=900,
        )
    finally:
        try:
            Path(sp_path).unlink()
        except OSError:
            pass

    if result.returncode != 0:
        raise RuntimeError(
            f"claude -p exit {result.returncode}: {result.stderr.strip()[:400]}"
        )
    return result.stdout.strip()


def _run_api(cfg: Config, system_prompt: str, user_prompt: str) -> str:
    if not cfg.anthropic_api_key:
        raise RuntimeError(
            "CLAUDE_RUNNER=api requires ANTHROPIC_API_KEY in .env"
        )
    body = json.dumps(
        {
            "model": cfg.claude_model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        method="POST",
        headers={
            "x-api-key": cfg.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        d = json.loads(resp.read().decode())
    parts = [c.get("text", "") for c in d.get("content", []) if c.get("type") == "text"]
    return "\n".join(parts).strip()


def analyze(cfg: Config, system_prompt: str, user_prompt: str) -> str:
    """Run an analysis. Backend picked by cfg.claude_runner."""
    if cfg.claude_runner == "api":
        return _run_api(cfg, system_prompt, user_prompt)
    return _run_cli(cfg, system_prompt, user_prompt)


def load_prompt(cfg: Config, name: str) -> str:
    """Load a prompt template from prompts/<name>.md."""
    path = cfg.prompts_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt template not found: {path}")
    return path.read_text(encoding="utf-8")
