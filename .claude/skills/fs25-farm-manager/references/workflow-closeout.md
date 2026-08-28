---
name: workflow-closeout
description: 'Closeout (menu code CO) — disarm the watcher, capture and record the delta, write the session record, close the plan, verify the sanctum, export issues, and sign off.'
firstStep: './closeout-steps/c1-capture-delta.md'
---

# Workflow: Closeout (menu code `CO`)

Triggered by "close out," "that's it for today," "end shift," or `/farm-closeout`.

The closeout is the only thing next session's briefing has to diff against. A session that ends
without one is a session that never happened, as far as the farm's memory is concerned.

## First — disarm the watcher, and verify it is off

If the briefing armed the event watcher (`scripts/wait_for_event.py`), **stop it before anything
else** — it is a live background process, and a forgotten one is a silent leak that keeps polling
after the session ends. Disarming is not done until you have *confirmed* it is gone:

1. **Stop it.** `TaskStop` the persistent Monitor task running the watcher; its clean exit (SIGTERM)
   removes `sanctum/watch.pid`. If a process lingers, stop **that pid** specifically —
   `kill "$(cat sanctum/watch.pid)"` — not a host-wide kill.
2. **Verify it is actually gone.** Check the pidfile, never a host-wide process-name search:
   `[ -f sanctum/watch.pid ] && kill -0 "$(cat sanctum/watch.pid)"`.
   - `sanctum/watch.pid` **absent** → clean stop. **Guard this case explicitly and stop there**: do
     not run `cat`/`kill` against a pidfile that doesn't exist — that only prints `cat:`/`kill:`
     errors for what is actually the common, healthy outcome (a clean SIGTERM exit removes its own
     pidfile).
   - `sanctum/watch.pid` present **and** `kill -0 "$(cat sanctum/watch.pid)"` succeeds → still
     running; stop **that pid** specifically and re-check.
   - `sanctum/watch.pid` present **and** `kill -0 "$(cat sanctum/watch.pid)"` fails → the watcher was
     hard-killed (SIGKILL / OOM) and never ran its cleanup, so the pidfile is stale. **Remove it**
     (`rm -f sanctum/watch.pid`) — the process is already gone. ⛔ **A stale pidfile is removed, not
     trusted**: treating it as a live watcher blocks the next arm, and treating it as proof of a
     running watcher is how a dead watcher gets reported as healthy.

   A stop you didn't verify is not a stop (BP-066: silence is not success — a still-running watcher
   looks identical to a stopped one until you check).
3. **Report `watcher off, confirmed`** to the player before sign-off — only once the pidfile check
   above resolves clean (absent, or a stale one already removed) and no live watcher remains. Never
   sign off on an unverified watcher.

If no watcher was armed this session, say so and move on — there is nothing to disarm.

⛔ **This precedes step 1 deliberately.** The watcher reacts to file writes, and the closeout is
about to write several; leaving it armed means it fires on the manager's own bookkeeping.

## Running this workflow

The closeout is **six steps**. Begin at {firstStep} and follow each step's `nextStepFile` in order
— **if you skip opening any of the six and improvise its step instead, say so out loud before
continuing, rather than letting the drop-out go unannounced.**

1. **C1 · Capture and record the delta** — `./closeout-steps/c1-capture-delta.md`
2. **C2 · Write the session record** — `./closeout-steps/c2-session-record.md`
3. **C3 · Close the plan** — `./closeout-steps/c3-close-plan.md`
4. **C4 · Verify the sanctum** — `./closeout-steps/c4-verify-sanctum.md`
5. **C5 · Export issues** — `./closeout-steps/c5-export-issues.md`
6. **C6 · Disarm and sign off** — `./closeout-steps/c6-signoff.md`

⚠ **The skill's own doc/code honesty check is not part of this workflow.** It is developer-facing,
lives under `references/dev-steps/`, and is run by hand when `scripts/` or `SKILL.md` changed during a
*development* session — **never inside a player's closeout**, and never wired into the chain above.
Its doc/code parity half runs automatically at build time.

Load and follow: {firstStep}
