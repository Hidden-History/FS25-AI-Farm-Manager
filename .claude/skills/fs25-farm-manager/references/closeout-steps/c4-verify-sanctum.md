---
name: c4-verify-sanctum
description: 'Walk every sanctum file against its contract and rotate what is flagged as over its recommended size — check, don''t reconstruct.'
nextStepFile: './c5-export-issues.md'
---

# C4: Verify the sanctum

**Progress: Step 4 of 6** — Next: Export issues

**Walk the sanctum and verify each file against its contract.** `references/sanctum-upkeep.md`
names every one and says when it changes — **read it; this step is not doable from memory.**

⛔ **This step CHECKS. It does not reconstruct.** Most files should already be current from during
the session, so you are confirming, not rebuilding. If this step finds itself writing a lot, the
session was writing too little — and that gap belongs in the friction log, not silently patched
here at the end, when memory is at its worst.

## Run the upkeep tool

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/sanctum_maintain.py" check "<sanctum_dir>"
```

`check` reports each file against its cap and version contract. A shipped `cap_lines`/`cap_kb` is a
**recommendation, not a limit**: an over-cap file stays `FRESH` (or `UNVERIFIABLE`, per its own
contract) and carries a `warning` instead — that warning is your tripwire to rotate, repeated every
run for as long as it stays over. `STALE` is reserved for a real contract gap: a missing required
section, or (for `config.json`) a missing required key. An `UNVERIFIABLE` verdict is not a pass. Each
file's contract (`class`, `parity_spec`, `format_version`) is re-stamped from the current template,
so a template that changed shape shows up here as a mismatch rather than as silence.

⛔ **`check` does NOT detect a file whose template version is behind. Run `reconcile` too.**
`check` reports caps, frontmatter and required sections — it is **silent about `format_version`
drift**, so a roster still on an old template shape comes back `FRESH`. Only `reconcile` compares a
file's `format_version` to its current template. So always also run:

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/sanctum_maintain.py" reconcile "<sanctum_dir>"
```

Without `--apply` this **writes nothing** and prints a `plan` of `migrate_version` entries with
each file's `from_version` → `to_version`. **A non-empty plan is a finding, not noise**: those
files are being read against a contract they no longer match. Report it, and apply it with
`--apply` (content-preserving, backed up first) once the player is content. **Do not assume every
file steps to the same version** — read each entry's `to_version`; they differ per template.

⛔ **`reconcile` and `rotate` are DRY RUN without `--apply`.** They report the plan and write
nothing. **Running one without `--apply` and then reporting the rotation as done writes nothing and
claims otherwise** — the exact failure this warning exists for. When `rotate` reports
`action: "agent-rotation"`, that is **not** a failure: it means the file is one you rotate by hand
per its own instructions. Archive, never blind-delete.

## The three that catch people

- **`state/finances-ledger.md`** — **complete this session's existing row's Notes; never append a
  second row.** Rows are opening snapshots; a closeout row would mix opening and closing figures in
  one column and quietly corrupt the trend. C2 completed it — confirm that, don't redo it.
- **`config.json`** — ⛔ **`session_count` was already incremented at session start (S5). Don't
  double it.** Closeout deliberately never touches that field.
- **`identity/creed.md` / `identity/decision-making.md`** — identity and judgment. **Changing
  either needs the player's say-so, never your inference.**

If a file didn't change, say nothing. **Don't touch a file to prove you looked at it** — a no-op
edit is noise a future session has to read past.

## Next

Once every sanctum file is verified, read fully and follow: {nextStepFile}
