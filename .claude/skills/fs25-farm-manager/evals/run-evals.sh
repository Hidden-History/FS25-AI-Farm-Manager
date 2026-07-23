#!/usr/bin/env bash
# Durable eval-runner harness for fs25-farm-manager (item 12).
#
# The bmad-eval-runner spawns `claude -p` in a from-scratch clean-room env with
# CLAUDE_CONFIG_DIR pointed at a per-case empty dir, so the spawn has NO auth.
# adapter.json (auto-discovered next to cases.json) lists CLAUDE_CONFIG_DIR in
# env_passthrough, which lets the runner FORWARD our host CLAUDE_CONFIG_DIR into
# each spawn — overriding the clean-room value. We point it at a dedicated
# eval-only config dir that carries real credentials, kept isolated from the
# live ~/.claude session. No secrets are hardcoded here: live credential files
# are copied at runtime.
set -euo pipefail

EVALS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$EVALS_DIR/.." && pwd)"
CASES="$EVALS_DIR/cases.json"
RUNNER="/mnt/e/projects/ai-memory-testV2/.claude/skills/bmad-eval-runner/scripts/run_evals.py"

LIVE_CFG="$HOME/.claude"
EVAL_CFG="$HOME/.claude-eval-only"

# --- refresh eval-only auth from the live session, only when stale -----------
# Copy .credentials.json (and .claude.json, if the live dir carries one) when
# the eval-only copy is missing or older than live. Everything else in
# ~/.claude-eval-only is preserved as-is.
refresh_file() {
  local name="$1"
  local src="$LIVE_CFG/$name"
  local dst="$EVAL_CFG/$name"
  [ -f "$src" ] || return 0
  if [ ! -f "$dst" ] || [ "$src" -nt "$dst" ]; then
    cp -p "$src" "$dst"
    echo "[run-evals] refreshed $name into eval-only config"
  else
    echo "[run-evals] $name already fresh"
  fi
}

mkdir -p "$EVAL_CFG"
refresh_file ".credentials.json"
refresh_file ".claude.json"

export CLAUDE_CONFIG_DIR="$EVAL_CFG"

OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fs25-evals.XXXXXX")"
echo "[run-evals] output dir: $OUT_DIR"
echo "[run-evals] runner:     $RUNNER"
echo "[run-evals] skill:      $SKILL_DIR"
echo "[run-evals] cases:      $CASES"
echo

python3 "$RUNNER" \
  --skill-path "$SKILL_DIR" \
  --cases "$CASES" \
  --output-dir "$OUT_DIR" \
  --mode quality \
  --runs 3
