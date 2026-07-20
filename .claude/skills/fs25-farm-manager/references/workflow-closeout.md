---
name: workflow-closeout
description: 'Closeout (menu code CO) — capture end state, write and save the closeout, check the skill''s honesty, log frictions, verify the sanctum, and sign off.'
firstStep: './closeout-steps/step-01-capture-end-state.md'
---

# Workflow: Closeout (menu code `CO`)

Triggered by "close out," "that's it for today," "end shift," or `/farm-closeout`.

The closeout is the only thing next session's briefing has to diff against. A session that
ends without one is a session that never happened, as far as the farm's memory is concerned.

## First — disarm the watcher, and verify it is off

If the briefing armed the event watcher (`scripts/wait_for_event.py`), **stop it before anything
else** — it is a live background process, and a forgotten one is a silent leak that keeps polling
after the session ends. Disarming is not done until you have *confirmed* it is gone:

1. **Stop it.** `TaskStop` the persistent Monitor task running the watcher; its clean exit
   (SIGTERM) removes `sanctum/watch.pid`. If a process lingers, stop **that pid** specifically —
   `kill "$(cat sanctum/watch.pid)"` — not a host-wide kill.
2. **Verify it is actually gone.** `pgrep -f wait_for_event.py` must return nothing; then
   reconcile the pidfile:
   - `pgrep` empty **and** `sanctum/watch.pid` absent → clean stop.
   - `pgrep` empty **but** `sanctum/watch.pid` still present → the watcher was hard-killed
     (SIGKILL / OOM) and never ran its cleanup, so the pidfile is stale. Remove it
     (`rm -f sanctum/watch.pid`) — the process is already gone.
   - `pgrep` non-empty → it is still running; stop that pid and re-check.
   A stop you didn't verify is not a stop (BP-066: silence is not success — a still-running
   watcher looks identical to a stopped one until you check).
3. **Report `watcher off, confirmed`** to the player before sign-off — only once `pgrep` is empty
   and no live watcher remains. Never sign off on an unverified watcher.

If no watcher was armed this session, say so and move on — there is nothing to disarm.

## Running this workflow

Begin at {firstStep} and follow each step's `nextStepFile` in order through step 7. The
honesty check (step 4) deliberately runs before the friction-log append (step 5), so a
fresh doc/code drift finding always has somewhere to land this session.

Load and follow: {firstStep}
