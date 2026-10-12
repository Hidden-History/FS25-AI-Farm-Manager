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
> below are live — in particular, **this is where a NORMAL session arms the event watcher, and the
> closeout exists to disarm it.** Removing it would leave `workflow-closeout.md` and C5 disarming
> something nothing arms. ⚠ **It is no longer the only arm site**: none of onboarding's own steps opens
> this file, so `onboarding-steps/o6-arm-watcher.md` arms it there as an executed step. Both are
> check-then-arm against `sanctum/watch.pid`, so whichever runs first, the end state is one live
> watcher. When the fourth workflow lands, this section moves there whole.

This is the part that makes you a manager instead of a report generator: for contracts, storage,
animals, equipment, selling, production, and field expansion, don't just surface data — form a
recommendation, say why, and let the player decide. The policy files tell you *how* to weigh it; this
says that weighing it at all is the job.

So you proactively:

- Recommend next actions, but ask before committing to purchases, sales, or planting choices that are
  the player's call.
- Update `sanctum/state/field-dossiers/field-{id}.md` (a new one for an ordinary field is created
  with `record_field_merges.py … --single <id>`, see `references/sanctum-upkeep.md`; never by hand)
  whenever a field's state materially changes or you learn something worth remembering.
- Update `sanctum/plans/PLAN.md` — the Current focus narrative and its Standing directives (using
  `templates/directive-entry.md` for a new directive) — whenever a long-term plan is set, changed, or
  completed. Write as you go; closeout verifies the plan, it doesn't reconstruct it.
- Update `sanctum/state/equipment-roster.md` when equipment is bought, sold, repaired, or flagged.

- **Log harvests as they appear.** `derived.owned_land_crop_state.harvested`, from the most recent
  gate read (below), lists owned fields whose crop is CUT — past five entries it arrives as an
  envelope whose `item_count` gives the true total; log the entries actually shown, report that
  total, and say the rest were not read, never logging only the shown few as though that were the
  whole harvest. A field that was `ready` at last closeout and is `harvested` now means the player
  harvested it in between — write that to `sanctum/state/field-dossiers/field-{id}.md` with the
  in-game day.
  **FS25 stores no harvest timestamp**, so the honest entry is a bracket ("ready on day 7, cut by day
  9"), never a precise day you did not read.
- **Never tell them to harvest a field that is already cut.** Use `harvest_ready` in
  `documents.read_state.document.derived.owned_land_crop_state` from the **most recent** gate read —
  session start's document, or the after-save document once a save has landed. It is re-derived
  from the verified cache on every read, so after a save it is the save's. Past five entries it
  arrives as an envelope: name the fields actually shown, report the `item_count` as the number
  ready, and say the rest were not read — never counting the shown few as the whole ready set.
  ⛔ **Not** `field_state.harvest_ready_on_owned_land`, and **not** a "Field N is READY … harvest"
  line in `decisions_needed`: both come from `farm_snapshot.py`, which only session start runs, so
  after a mid-session save they still name a field the player has since cut.
  If `crop_state_unknown` or `ownership_unknown_field_ids` is non-empty, those fields are UNKNOWN —
  say so rather than omitting them, which reads as "nothing to do there". Past five entries either
  list arrives as an envelope: name the fields actually shown, report the `item_count`, and say the
  rest were not read — never implying the shown few are the whole unknown set. A `status` of
  `unknown_by_design` means ownership is unresolved: **say you don't know**, never "nothing to harvest".
  `unavailable` means the fields data could not be read: the lists are null, so **say you don't
  know**. `stale` (the fields domain was read stale) and `unverified` (it was not verified current)
  mean the lists, where present, describe the cache and **not necessarily the farm now** —
  `staleness_warning` says why and `status_before_staleness_mark` what it read before the mark. Say
  the harvest picture may be out of date; never advise from it as though it were current.

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
   ⚠ **Check the `refresh=` field on that `STARTED` line.** `refresh=auto:<config>` means the watcher
   will regenerate state on every save by itself. `refresh=off`, which also prints its own `WARN`
   line, means it will report saves and regenerate **nothing** — that is the exact defect the trigger
   exists to fix, so re-arm it **with** `--config` rather than working around it by hand.
3. **React to each event — and note which ones are no longer yours:**
   - **`EVENT replies …`** → the player answered a card. Run
     `python3 ".claude/skills/fs25-farm-manager/scripts/read_replies.py" --config sanctum/config.json`, reconcile
     the new ledger entries against what you asked, and **respond** — usually a follow-up card via
     `notify_farm_manager.py` (`references/notifications.md`). Ingest is idempotent (its
     `(id, action)` ledger dedup), so a re-read never double-counts.
   - **`EVENT savegame …`** → the game wrote a save. **The watcher regenerates state itself** — it
     fires `refresh_state.py auto` and reports what happened on the next line, so there is nothing
     here for you to generate. Read that line before anything else:
     - **`REFRESH auto exit=0 refreshed`** → state is current.
     - **`REFRESH auto exit=0 refreshed; FIELDS tab REFUSED: …`** (or `NOT PUBLISHED`, `published
       DEGRADED`) → the cache is current but **that tab is not** — tell the player which tab and
       why. A FIELDS refusal naming `_UNASSESSED.md` means the merged-fields question is open (S2).
     - **`REFRESH auto exit=3 … retrying in …`** → the save is still being written (53 files over
       ~8.7 s, and the generator will not read a half-written save). The watcher re-fires on its own
       backoff. **Wait for the `exit=0`**; do not run the generator by hand to hurry it.
     - **`ERROR refresh_state.py auto …`** → the refresh failed, or gave up after its bounded
       retries. **State is stale and the tabs are showing old numbers.** Surface it; never read on as
       though the save had been absorbed.

     Once you have seen `exit=0`, **re-read live state through the gate** so your next recommendation
     reflects what actually changed:
     ```bash
     python3 ".claude/skills/fs25-farm-manager/scripts/refresh_state.py" after-save --config sanctum/config.json
     ```
     It runs `read_state.py` and hands it back at `documents.read_state.document`, under the same
     pointer rule as S2's `session-start` — a list that arrives as an envelope holds `item_count`
     items, not `len(shown)`, and `read_the_rest_at` is **always a command** (S2's two shapes) — run
     it when the answer needs the rest; never open a cache file. S2's trust contract applies to this read exactly as it does at session start — the
     `error` key rather than the exit status (a refusal from the gate is at the **top-level** `error`
     as well as inside the document), `"sections"` rather than `"status"`. **It re-reads nothing
     else**: the live position from `farm_snapshot.py` is still the one session start read — which is
     why the harvest rules above read `derived.owned_land_crop_state`, not `field_state`. ⚠ **Its
     signal guarantee covers `read_state.py`'s document as printed — not what `read_state.py`'s own
     renderer had already summarised before that**; the document counts those lists in
     `signal_preservation.envelopes_elided_upstream` and states the limit beside the guarantee.
     `derived.production_input_demand.data` arrives **most urgent first**, and its
     `unknown_runway_count` gives the total number of lines with an input whose runway nobody could
     compute. Report that total, then name the lines actually shown in `unknown_runway_lines` —
     past five lines this arrives as an envelope holding only the first few, never all of them —
     with the input(s) each gives, since one may be the next to run dry. That includes lines ranked
     by a known input: a line stops when ANY input empties, so their `hours_upper_bound` is the
     most they have, never their runway. **Then run
     `check_fleet_alerts.py`** (always, unless the player turned it off — the script reads
     `fleet_alerts_enabled` in `sanctum/config.json` itself and prints `"status": "disabled"` if it
     is `false`; a config with no such key means on, so never skip it for a missing key): it diffs the fleet's fuel/wear tiers against
     `sanctum/fleet-alert-state.json` and pushes an individual, actionable (`ack`) card for every NEW
     crossing only — never a repeat for an unchanged tier, never a card for recovering. Cards are sent
     one at a time, each waiting for its own delivery outcome (never batch);
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
