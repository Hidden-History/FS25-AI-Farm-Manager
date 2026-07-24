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
#
# After the run this script GATES on fixture isolation (F-EVAL-1). The cases
# bind to a synthetic savegame under evals/fixture/, so nothing should ever
# reach the operator's real FS25 save. If a run does reach it anyway, the run
# FAILS loudly here rather than quietly baking real financials into the
# artifacts a grader then reads.
set -euo pipefail

EVALS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$EVALS_DIR/.." && pwd)"
CASES="$EVALS_DIR/cases.json"

# The bmad-eval-runner is a separately INSTALLED BMAD skill, not part of this
# repo, so where it lives is machine-specific. Resolve it instead of baking one
# machine's absolute path into a file that ships in the public package: an
# absolute /mnt/... or /home/... path here is both broken for everyone else and
# a quiet disclosure of the author's directory layout.
# Order: explicit override, then a project-level install beside this skill, then
# the user-level install. Never guess silently -- if none resolve, say so and
# name the override.
RUNNER_REL="skills/bmad-eval-runner/scripts/run_evals.py"
RUNNER="${FS25_EVAL_RUNNER:-}"
if [ -z "$RUNNER" ]; then
  for cand in \
    "$SKILL_DIR/../bmad-eval-runner/scripts/run_evals.py" \
    "$HOME/.claude/$RUNNER_REL"
  do
    if [ -f "$cand" ]; then RUNNER="$cand"; break; fi
  done
fi
if [ -z "$RUNNER" ] || [ ! -f "$RUNNER" ]; then
  {
    echo "[run-evals] cannot find the bmad-eval-runner (run_evals.py)."
    echo "[run-evals] Looked beside this skill and under ~/.claude/."
    echo "[run-evals] Set FS25_EVAL_RUNNER to its path, e.g.:"
    echo "[run-evals]   FS25_EVAL_RUNNER=/path/to/.claude/$RUNNER_REL $0"
  } >&2
  exit 2
fi

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

run_status=0
python3 "$RUNNER" \
  --skill-path "$SKILL_DIR" \
  --cases "$CASES" \
  --output-dir "$OUT_DIR" \
  --mode quality \
  --runs 3 || run_status=$?

# --- fixture-isolation gate (F-EVAL-1) --------------------------------------
# Matches a RESOLVED host save location: a concrete drive letter AND a concrete
# username. The placeholder forms the skill's own docs use (/mnt/<drive>/Users/
# <user>/..., /mnt/*/Users/*/...) do not match, so quoting locate_save.py's
# docstring is not a leak -- only a path that actually resolved on this machine
# is. The staged skill under <cwd>/.claude/skills/ is INPUT, not run output, so
# it is filtered out; everything the run itself produced stays in scope.
#
# BOTH path forms must be caught. The POSIX form (/mnt/<drive>/Users/<user>/...)
# is what the WSL-side parsers emit, but the game itself writes the WINDOWS form
# (C:/Users/<user>/Documents/My Games/FarmingSimulator2025/...) into its own log
# -- so a run that reads the real gameLog.txt leaks the save location in a shape
# the POSIX pattern alone would sail straight past.
_USER='[A-Za-z0-9._-]+'
_SAVE='(OneDrive/)?Documents/My Games/FarmingSimulator(2025|25)'
_MSPKG='AppData/Local/Packages/GIANTSSoftware\.FarmingSimulator25PC'
# Windows separator class: forward slash OR backslash. SINGLE-quoted on purpose,
# so the class reaches the regex engine as the literal text [\\/].
# In a DOUBLE-quoted shell string, "[\\/]" collapses to [\/] before grep ever sees
# it, and whether that still matches a backslash is engine-dependent: GNU grep
# accepts it, but a stricter engine reads the `\` as an escape and silently
# degrades the class to forward-slash-only -- letting C:\Users\... straight
# through. Observed exactly that while building this gate. Single quotes are
# correct under both, so the portable form is the one that is also unambiguous.
_SEP='[\\/]+'
LEAK_PAT="/mnt/[a-z]/Users/$_USER/$_SAVE|/mnt/[a-z]/Users/$_USER/$_MSPKG"
LEAK_PAT="$LEAK_PAT|[A-Za-z]:${_SEP}Users${_SEP}${_USER}${_SEP}(OneDrive${_SEP})?Documents${_SEP}My Games${_SEP}FarmingSimulator(2025|25)"
LEAK_PAT="$LEAK_PAT|[A-Za-z]:${_SEP}Users${_SEP}${_USER}${_SEP}AppData${_SEP}Local${_SEP}Packages${_SEP}GIANTSSoftware\.FarmingSimulator25PC"

echo
echo "[run-evals] fixture-isolation gate: scanning $OUT_DIR for real-save reads"
# -i because Windows paths are case-insensitive and round-trip through logs and
# tooling in mixed case (c:\users\<user>\..., /mnt/C/Users/...). A case-sensitive
# gate would call that clean.
# The exclusion is anchored to the PATH FIELD of grep's file:line:content output
# (^[^:]* = up to the first colon). Filtering on the whole line would drop a REAL
# leak whenever the matching line's CONTENT happened to mention that substring --
# a transcript quoting the staged skill's path would erase itself from the gate.
leaks="$(grep -rEni "$LEAK_PAT" "$OUT_DIR" 2>/dev/null | grep -vE '^[^:]*/cwd/\.claude/skills/' || true)"

if [ -n "$leaks" ]; then
  {
    echo
    echo "[run-evals] FIXTURE ISOLATION FAILED (F-EVAL-1)"
    echo "[run-evals] A run reached the operator's real FS25 save. These artifacts"
    echo "[run-evals] carry real data and are not deterministic -- do not grade them."
    echo
    printf '%s\n' "$leaks" | cut -c1-200 | head -40
    echo
    echo "[run-evals] Check that sanctum/config.json's savegame_path still resolves to"
    echo "[run-evals] the staged evals/fixture/ save: a binding that does not resolve is"
    echo "[run-evals] read as broken, and the manager correctly self-heals via"
    echo "[run-evals] locate_save.py, which globs /mnt and finds the real save."
  } >&2
  exit 1
fi

echo "[run-evals] fixture-isolation gate: clean (no real-save reads in artifacts)"
exit "$run_status"
