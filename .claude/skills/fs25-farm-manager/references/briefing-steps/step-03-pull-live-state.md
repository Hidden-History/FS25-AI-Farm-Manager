---
name: step-03-pull-live-state
description: 'Pull live game state via farm_snapshot.py — the digest, not the raw dump.'
nextStepFile: './step-04-check-parser-selfreport.md'
---

# Step 3: Pull live game state

**Progress: Step 3 of 8** — Next: Check what the parsers said about themselves

**Pull live game state** — the digest, not the raw dump:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/farm_snapshot.py" "<savegame_path from config.json>"
```
Reach for `collect_state.py` only if the briefing needs a field the digest lacks.

## Next

Once live state is in hand, read fully and follow: {nextStepFile}
