---
name: dev-check-skill-honesty
description: 'Dev-facing (not player-facing). Check the skill''s wiring with check_skill_honesty.py if scripts/ or SKILL.md changed this development session; append any finding to the friction log before closing out.'
---

# Dev check: is the skill's wiring honest?

**This step is for a developer working on this skill's own tree, never for a player.**
It does not run inside the player closeout chain (`workflow-closeout.md` → C1–C5) and no
player session reaches it. [[DEC-084]] split the old combined honesty check in two:

- **Doc/code parity** (`check_reachability` — does every script/reference reach `SKILL.md`,
  does every path `SKILL.md` names exist) now runs **automatically at build time**, in
  `tools/build_package.py`'s `GUARD_TESTS` (**BG-1**). It needs no savegame and nothing here
  duplicates it.
- **Capability wiring** (`check_honesty` — does a capability the code has actually reach the
  briefing, probed against a real save) **cannot run in a build gate** — several of its probes
  hard-fail against an absent savegame and would report a false "NOT WIRED". It stays
  **session-time**, run by hand here.

**If `scripts/` or `SKILL.md` changed this development session**, run:
```bash
python3 ".claude/skills/fs25-farm-manager/scripts/check_skill_honesty.py" "<savegame_path>"
```
Exit `0` = the docs agree with the code and every wired capability actually reaches a
workflow. Exit `1` = a capability is built but never reaches a workflow, or the docs deny
something the code can do — report it; **fix the doc, not the probe**.

**Append any finding to `sanctum/history/friction-log.md` before closing out this development
session** — same session, so the finding has somewhere to land. This is the property the
original M5 defect fixed and the split must not lose: a drift finding discovered here must
not sit unrecorded until the next session.

Skip this step entirely on an ordinary player session; it is not part of the farm briefing.
