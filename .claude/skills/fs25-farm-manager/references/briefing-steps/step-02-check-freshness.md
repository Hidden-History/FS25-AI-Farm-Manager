---
name: step-02-check-freshness
description: 'Check the sanctum still matches the save with check_sanctum_freshness.py; fix what it flags before briefing on it.'
nextStepFile: './step-03-pull-live-state.md'
---

# Step 2: Check the sanctum still matches the save

**Progress: Step 2 of 8** — Next: Pull live game state

**Check the sanctum still matches the save** — before you trust a word of it:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check_sanctum_freshness.py" "<savegame_path>"
```
Fast, no `--debug` pass. It probes the handful of current-state claims a sanctum
legitimately makes (the interest rate, owned land, the offset, directive premises) and
fails when the save contradicts one. **Fix what it flags before briefing on it** — you are
about to speak in the creed's voice, and a stale creed briefs the player on a farm that no
longer exists (F-028). An `unverifiable` verdict is NOT a pass; read it.

## Next

Once the sanctum is verified against the save, read fully and follow: {nextStepFile}
