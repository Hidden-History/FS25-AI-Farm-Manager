---
name: step-01-capture-end-state
description: 'Capture the end state with farm_snapshot.py — the same digest shape next session''s briefing diffs against.'
nextStepFile: './step-02-write-closeout.md'
---

# Step 1: Capture the end state

**Progress: Step 1 of 8** — Next: Write the closeout

**Capture the end state:**
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/farm_snapshot.py" "<savegame_path from config.json>"
```
The same shape next session's briefing will diff against — that's why it's the digest and
not `collect_state.py`.

## Next

Once the end state is captured, read fully and follow: {nextStepFile}
