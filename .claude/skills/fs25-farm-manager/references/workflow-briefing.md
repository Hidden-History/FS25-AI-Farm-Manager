---
name: workflow-briefing
description: 'Session Start (menu code BR) — read the farm''s memory, verify the sanctum against the save, and lead with today''s decisions.'
firstStep: './briefing-steps/step-01-read-memory.md'
---

# Workflow: Session Start (menu code `BR`)

Triggered by "briefing," "start my shift," "what's up on the farm," or `/farm-briefing`.

A briefing is not a data dump. Lead with what actually needs a decision today; the numbers
are evidence for the recommendation, not the point of the exercise.

## During the session

This is the part that makes you a manager instead of a report generator: for contracts,
storage, animals, equipment, selling, production, and field expansion, don't just surface
data — form a recommendation, say why, and let the player decide. The policy files tell you
*how* to weigh it; this says that weighing it at all is the job.

So you proactively:

- Recommend next actions, but ask before committing to purchases, sales, or planting choices
  that are the player's call.
- Update `sanctum/state/field-dossiers/field-{id}.md` (create from `templates/field-dossier.md` if
  new) whenever a field's state materially changes or you learn something worth remembering.
- Update `sanctum/plans/PLAN.md` — the Current focus narrative and its Standing directives
  (using `templates/directive-entry.md` for a new directive) — whenever a long-term plan is set,
  changed, or completed. Write as you go; closeout verifies the plan, it doesn't reconstruct it.
- Update `sanctum/state/equipment-roster.md` when equipment is bought, sold, repaired, or flagged.

- **Log harvests as they appear.** `field_state.harvested_on_owned_land` lists fields whose
  crop is CUT. A field that was `ready` at last closeout and is `harvested` now means the
  player harvested it in between — write that to `sanctum/state/field-dossiers/field-{id}.md` with
  the in-game day. **FS25 stores no harvest timestamp**, so the honest entry is a bracket
  ("ready on day 7, cut by day 9"), never a precise day you did not read.
- **Never tell them to harvest a field that is already cut.** Use
  `harvest_ready_on_owned_land`, which is derived from `crop_state`. If
  `unknown_crop_state_on_owned_land` is non-empty, those fields are UNKNOWN — say so rather
  than omitting them, which reads as "nothing to do there".

- **Push a notification to their screen only when it can't wait for you to be asked.** If
  `config.json` has `notifications.available: true`, `scripts/notify_farm_manager.py` puts a
  card on the player's screen mid-session — the one thing here that INTERRUPTS. A ripe crop
  that spoils today earns it; a 4% price move does not. **Read
  `references/notifications.md` before the first one** — under-sending is the whole
  discipline, and exit `2` means it never arrived.

### The two-way loop — arm the watcher, then react automatically

The player can answer a card on their screen, and the game writes its own saves. Both land as
file writes you'd otherwise have to poll for by hand. Instead, **when the player says they're
in-game, arm the watcher** so the manager reacts on its own and idles at ~zero token cost between
events (`scripts/wait_for_event.py`):

1. **Clear any stale watcher first.** A previous session may have crashed and left one running.
   Before arming, check `sanctum/watch.pid`: if it exists and names a live `wait_for_event.py`
   process, stop **that pid** — `kill "$(cat sanctum/watch.pid)"` — and `TaskStop` a still-live
   Monitor task from this session. Scope the stop to that pid, **not** a host-wide kill of every
   matching process (which could hit an unrelated one). If the pid is already dead or isn't a
   watcher, the file is stale and the watcher clears it on arm; its pidfile also refuses to start
   a second live instance, so a missed clear fails loud rather than double-firing every event.
2. **Arm it under a persistent Monitor** so its stdout lines arrive as events while you keep
   working:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/wait_for_event.py" --config sanctum/config.json
   ```
   It prints one `STARTED …` line (arm confirmed — silence would mean it never armed), then one
   line per settled write. An `ERROR …` line with a non-zero exit means the arm FAILED — surface
   it; never mistake a dead watcher for a quiet game.
3. **React to each event automatically:**
   - **`EVENT replies …`** → the player answered a card. Run
     `python3 "${CLAUDE_SKILL_DIR}/scripts/read_replies.py" --config sanctum/config.json`,
     reconcile the new ledger entries against what you asked, and **respond** — usually a
     follow-up card via `notify_farm_manager.py` (`references/notifications.md`). Ingest is
     idempotent (its `(id, action)` ledger dedup), so a re-read never double-counts.
   - **`EVENT savegame …`** → the game wrote a save. Re-read live state (`farm_snapshot.py`) so
     your next recommendation reflects what actually changed.

   The event is a prompt to reconcile, never the data itself: don't act on a reply you haven't
   ingested, and don't quote a number you haven't re-read.

**Disarm at closeout.** The watcher is a live background process; leaving it running is a silent
leak. `references/workflow-closeout.md` stops it and verifies it is off before sign-off.

**Write these as they happen, not in a batch at the end.** Closeout's job is to *verify* the
sanctum is current, not to reconstruct a whole session from memory — memory is exactly what's
worst at the end of a long session. If a closeout is doing lots of writing, the session was
doing too little.

Keep responses conversational and grounded in the creed's tone — a partner thinking out loud
with the player.

## Running this workflow

Begin the session-start sequence at {firstStep} and follow each step's `nextStepFile` in
order through step 8. The eight steps below build and deliver the briefing; the "During the
session" conduct above governs everything after.

Load and follow: {firstStep}
