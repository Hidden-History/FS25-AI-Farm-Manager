---
name: step-04-check-parser-selfreport
description: 'Check what the parsers said about themselves — calibration flags, errors, failed gates — and adjust the reading.'
nextStepFile: './step-05-diff-closeout.md'
---

# Step 4: Check what the parsers said about themselves

**Progress: Step 4 of 8** — Next: Diff against the last closeout

**Check what the parsers said about themselves.** If any section carries
`"calibration_needed": true`, an `"error"`, or a failed gate, read its `generic_dump` for
the real tag names FS25 used and adjust your reading for this session. Mention it to the
player only if it blocks something they asked about — don't derail a briefing with
technical caveats. Then apply SKILL.md's sanity check to the sections that *didn't*
complain, because that flag alone doesn't catch a confident wrong answer.

**Then check what the game itself recorded** — the parsers read the save; the engine log
records what the save never will (a mod that failed to load, a crash last session):

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/read_game_log.py" "<savegame_path from config.json>"
```

Surface it to the player only when it bears on the farm: any `errors` (especially a
**mod-load failure** — a mod they think is running that silently didn't), or
`log_complete: false`, which means the last run **crashed, was killed, or is still open** —
worth a plain word, not a caveat dump. Zero errors is a *verified* clean run, not silence;
an `{"error": ...}` (no log found) is just "nothing to read," never "nothing went wrong."

## Next

Once the parser self-reports are read, read fully and follow: {nextStepFile}
