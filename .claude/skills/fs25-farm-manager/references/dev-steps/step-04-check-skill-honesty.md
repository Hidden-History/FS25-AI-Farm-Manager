---
name: dev-check-skill-honesty
description: 'Dev-facing (not player-facing). Check the skill''s wiring with check_skill_honesty.py if scripts/ or SKILL.md changed this development session; append any finding to the friction log before closing out.'
---

# Dev check: is the skill's wiring honest?

**This step is for a developer working on this skill's own tree, never for a player.**
It does not run inside the player closeout chain (`workflow-closeout.md` → C1–C5) and no
player session reaches it. The old combined honesty check is now split in two:

- **Doc/code parity** (`check_reachability`) now runs **automatically at build time**, in
  `tools/build_package.py`'s `GUARD_TESTS` (**BG-1**), whether or not a session remembers to
  check it. It needs no savegame and nothing here duplicates it. What it actually certifies:
  - **A script is reachable when the inventory `refresh_state.py --help` PRINTS names it** —
    not when `SKILL.md` mentions it. A `SKILL.md` mention does not satisfy a script at all,
    deliberately: accepting hand-maintained prose is the drift
    removed with the old script table. The hand-written `state_inventory.SETS` registry is
    asked separately, so a renderer that globbed `scripts/` could not make the check vacuous.
  - **A reference is reachable when ANY shipped document names it** — `SKILL.md`, another
    reference, or a template — checked recursively at every depth, because that is how this
    skill is actually read (`SKILL.md` → `workflow-*.md` → step files; `templates/` →
    `game-guide/`).
  - **Every `scripts/`, `references/` or `templates/` path `SKILL.md` names must exist**, and
    every `## section` it cites must be a heading in it.
  - It does **not** check `templates/` for orphaning, nor non-`.md` reference files.
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
