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

**Migrate the sanctum forward if the mod restructured it.** A mod upgrade can change the
sanctum's structure (e.g. the old `identity/directives.md` folding into `plans/PLAN.md`).
Run the migration applier — it compares the sanctum's `sanctum_schema_version` marker to the
version this skill ships and applies any pending migrations in order:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/sanctum_maintain.py" migrate "<sanctum_dir>" --apply
```
It backs up the touched subtree to a dated backup dir **before** any write, conservation-proves
nothing is lost, then advances the marker. Read the JSON:
- `up_to_date: true` → nothing to do; say nothing to the player.
- one or more `steps` applied → tell the player in **one line** what changed and where the
  backup is: e.g. _"Migrated your plan to the new structure (folded directives into PLAN.md);
  pre-migration backup at `<the step's `backup` path>`."_ (DB-migration-on-launch UX.)
- an `error` (exit code 2 — e.g. `SchemaVersionError` when the marker is ahead of this skill
  or `config.json` is corrupt/unparseable, `MigrationError`, `ConservationError`) → nothing was
  **lost**. Most errors (`SchemaVersionError`, `MigrationError`, corrupt config) fail loud
  *before* any write, so the sanctum is untouched; a `ConservationError` can fire mid-apply after
  a partial write, but the pre-migration backup holds the original and the migration is
  **resumable** (it completes or rolls back on the next briefing). **Degrade gracefully: do NOT
  abort the briefing.** Surface the error to the player in one line — e.g. _"Heads-up: couldn't
  finish auto-migrating the sanctum (`<the error text>`); nothing was lost — anything partly
  changed is backed up and will sort itself on the next run. Continuing the briefing; we can look
  at the migration separately."_ Then continue with the rest of session start. A corrupt config
  or an ahead-version sanctum must never brick every briefing — it loudly SKIPS migration, not
  the briefing.

## Next

Once the sanctum is verified against the save, read fully and follow: {nextStepFile}
