---
name: step-02-read-everything
description: 'Read everything before asking anything else — the full raw snapshot plus read_career.py, not the digest.'
nextStepFile: './step-03-present-position.md'
---

# Step 2: Read everything

**Progress: Step 2 of 7** — Next: Present the real position

**Read everything** before asking anything else:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/collect_state.py" "<savegame_path>"
python3 "${CLAUDE_SKILL_DIR}/scripts/read_career.py" "<savegame_path>"
```
Onboarding is the one time to use the full raw snapshot rather than the digest — you're
building the farm's whole opening picture, not a briefing. `read_career.py` covers what
`collect_state.py` doesn't: map, difficulty, the save's *starting* money/loan, timeScale,
autoSaveInterval, and the mod list.

## Next

Once you've read the full opening picture, read fully and follow: {nextStepFile}
