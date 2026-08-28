---
name: workflow-briefing
description: 'Session Start (menu code BR) — orient in the farm''s memory, take delivery of verified state, evaluate the duties, and lead with today''s decisions.'
firstStep: './session-steps/s1-orient.md'
---

# Workflow: Session Start (menu code `BR`)

Triggered by "briefing," "start my shift," "what's up on the farm," or `/farm-briefing`.

A briefing is not a data dump. Lead with what actually needs a decision today; the numbers are
evidence for the recommendation, not the point of the exercise.

## Running this workflow

Session start is **five steps**, and they are a pipeline: orient, take delivery, read the change,
evaluate, deliver. Begin at {firstStep} and follow each step's `nextStepFile` in order — **if you
skip opening any of the five and improvise its step instead, say so out loud before continuing,
rather than letting the drop-out go unannounced.**

1. **S1 · Orient** — `./session-steps/s1-orient.md` · read whose farm this is before reading a number
2. **S2 · Take delivery of the state** — `./session-steps/s2-take-delivery.md` · receive the verified
   view and **stop** if it cannot be trusted
3. **S3 · Read the change notice** — `./session-steps/s3-change-notice.md` · what moved since last
   session
4. **S4 · Evaluate the duty register** — `./session-steps/s4-evaluate-duties.md` · **this is PLAN**
5. **S5 · Escalate and deliver** — `./session-steps/s5-escalate-deliver.md` · **this is ESCALATE**

⛔ **The order is load-bearing.** S1 before S2 so the state is read in the context of the farm's
intent; S2's stop before S4 so no duty is ever evaluated against a view already judged
untrustworthy. **Do not compose any part of the briefing before S5** — S5 ranks across all 16 duties
and cannot do that until every one has reported.

The five steps above build and deliver the briefing; the **During the session** conduct below governs
everything after.

---

## During the session

> ⚠ **This conduct half is retained here deliberately, and its long-term home is elsewhere.** The
> design of record places ongoing session conduct in a separate fourth workflow that **is not built
> and whose steps are specified nowhere.** It is kept in place rather than shed, because the rules
> below are live — in particular, **this is the only place the event watcher is armed, and the
> closeout exists to disarm it.** Removing it would leave `workflow-closeout.md` and C5 disarming
> something nothing arms. When the fourth workflow lands, this section moves there whole.

This is the part that makes you a manager instead of a report generator: for contracts, storage,
animals, equipment, selling, production, and field expansion, don't just surface data — form a
recommendation, say why, and let the player decide. The policy files tell you *how* to weigh it; this
says that weighing it at all is the job.

So you proactively:

- Recommend next actions, but ask before committing to purchases, sales, or planting choices that are
  the player's call.
- Update `sanctum/state/field-dossiers/field-{id}.md` (create from `templates/field-dossier.md` if
  new) whenever a field's state materially changes or you learn something worth remembering.
- Update `sanctum/plans/PLAN.md` — the Current focus narrative and its Standing directives (using
  `templates/directive-entry.md` for a new directive) — whenever a long-term plan is set, changed, or
  completed. Write as you go; closeout verifies the plan, it doesn't reconstruct it.
- Update `sanctum/state/equipment-roster.md` when equipment is bought, sold, repaired, or flagged.

- **Log harvests as they appear.** `field_state.harvested_on_owned_land` lists fields whose crop is
  CUT. A field that was `ready` at last closeout and is `harvested` now means the player harvested it
  in between — write that to `sanctum/state/field-dossiers/field-{id}.md` with the in-game day.
  **FS25 stores no harvest timestamp**, so the honest entry is a bracket ("ready on day 7, cut by day
  9"), never a precise day you did not read.
- **Never tell them to harvest a field that is already cut.** Use `harvest_ready_on_owned_land`, which
  is derived from `crop_state`. If `unknown_crop_state_on_owned_land` is non-empty, those fields are
  UNKNOWN — say so rather than omitting them, which reads as "nothing to do there".

- **Push a notification to their screen only when it can't wait for you to be asked.** If
  `config.json` has `notifications.available: true`, `scripts/notify_farm_manager.py` puts a card on
  the player's screen mid-session — the one thing here that INTERRUPTS. A ripe crop that spoils today
  earns it; a 4% price move does not. **Read `references/notifications.md` before the first one** —
  under-sending is the whole discipline, and exit `2` means it never arrived. **Record every card's
  `id` and the question it asked, at send time** (S5) — nothing on the wire carries the card's
  original text, so a reply is otherwise untraceable to what it asked.

### The two-way loop — arm the watcher, then react automatically

The player can answer a card on their screen, and the game writes its own saves. Both land as file
writes you'd otherwise have to poll for by hand. Instead, **when the player says they're in-game, arm
the watcher** so the manager reacts on its own and idles at ~zero token cost between events
(`scripts/wait_for_event.py`):

1. **Clear any stale watcher first.** A previous session may have crashed and left one running. Before
   arming, check `sanctum/watch.pid`: if it exists and names a live `wait_for_event.py` process, stop
   **that pid** — `kill "$(cat sanctum/watch.pid)"` — and `TaskStop` a still-live Monitor task from
   this session. Scope the stop to that pid, **not** a host-wide kill of every matching process (which
   could hit an unrelated one). If the pid is already dead or isn't a watcher, the file is stale and
   the watcher clears it on arm; its pidfile also refuses to start a second live instance, so a missed
   clear fails loud rather than double-firing every event.
2. **Arm it under a persistent Monitor** so its stdout lines arrive as events while you keep working:
   ```bash
   python3 ".claude/skills/fs25-farm-manager/scripts/wait_for_event.py" --config sanctum/config.json
   ```
   It prints one `STARTED …` line (arm confirmed — silence would mean it never armed), then one line
   per settled write. An `ERROR …` line with a non-zero exit means the arm FAILED — surface it; never
   mistake a dead watcher for a quiet game.
3. **React to each event automatically:**
   - **`EVENT replies …`** → the player answered a card. Run
     `python3 ".claude/skills/fs25-farm-manager/scripts/read_replies.py" --config sanctum/config.json`, reconcile
     the new ledger entries against what you asked, and **respond** — usually a follow-up card via
     `notify_farm_manager.py` (`references/notifications.md`). Ingest is idempotent (its
     `(id, action)` ledger dedup), so a re-read never double-counts.
   - **`EVENT savegame …`** → the game wrote a save. **Re-read live state through the gate** so your
     next recommendation reflects what actually changed:
     ```bash
     python3 ".claude/skills/fs25-farm-manager/scripts/generate_state.py" --config sanctum/config.json
     python3 ".claude/skills/fs25-farm-manager/scripts/read_state.py"     --config sanctum/config.json
     ```
     S2's trust contract applies to this read exactly as it does at session start — the `error` key
     rather than the exit status, `"sections"` rather than `"status"`. **Then run
     `check_fleet_alerts.py`** (house rule set 2026-07-24 — `sanctum/config.json` →
     `house_rules.fuel_and_repair_alerts`): it diffs the fleet's fuel/wear tiers against
     `sanctum/fleet-alert-state.json` and pushes an individual, actionable (`ack`) card for every NEW
     crossing only — never a repeat for an unchanged tier, never a card for recovering. Cards are sent
     one at a time, each waiting for its own delivery outcome (never batch — see FRICTION-LOG F-210);
     if several land in the same event, only the last one survives on disk when the game is closed,
     which the script's own output flags rather than hides.

   The event is a prompt to reconcile, never the data itself: **don't act on a reply you haven't
   ingested, and don't quote a number you haven't re-read.**

**Disarm at closeout.** The watcher is a live background process; leaving it running is a silent leak.
`references/workflow-closeout.md` stops it and verifies it is off before sign-off.

**Write these as they happen, not in a batch at the end.** Closeout's job is to *verify* the sanctum
is current, not to reconstruct a whole session from memory — memory is exactly what's worst at the end
of a long session. If a closeout is doing lots of writing, the session was doing too little.

Keep responses conversational and grounded in the creed's tone — a partner thinking out loud with the
player.

Load and follow: {firstStep}
