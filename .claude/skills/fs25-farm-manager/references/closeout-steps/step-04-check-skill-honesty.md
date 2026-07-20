---
name: step-04-check-skill-honesty
description: 'Check the skill''s own honesty with check_skill_honesty.py if scripts/ or SKILL.md changed; runs before the friction-log append so a finding has somewhere to land.'
nextStepFile: './step-05-append-friction-log.md'
---

# Step 4: Check the skill's own honesty

**Progress: Step 4 of 7** — Next: Append this session's frictions

**Check the skill's own honesty, if anything in `scripts/` or `SKILL.md` changed this
session**:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check_skill_honesty.py" "<savegame_path>"
```
Exit `0` = the docs agree with the code. Exit `1` = SKILL.md denies a capability the code
has, or a capability is built but never reaches a workflow — report it; **fix the doc, not
the probe**, and carry any failure into step 5's friction-log entry (doc/code drift is
exactly what that log is for). Skip this step on an ordinary session where nothing in the
skill itself changed; it isn't part of the player-facing farm briefing. Runs BEFORE the
friction-log append below, so a finding here always has somewhere to land this session.

## Next

Once the honesty check is done (or deliberately skipped), read fully and follow: {nextStepFile}
