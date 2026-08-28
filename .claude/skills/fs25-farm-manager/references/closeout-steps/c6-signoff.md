---
name: c6-signoff
description: 'Confirm the watcher is actually gone — not merely signalled — then close warmly.'
---

# C6: Disarm and sign off

**Progress: Step 6 of 6** — Final step of the closeout

## Confirm the watcher is down — gone, not signalled

The closeout workflow stops the event watcher **before** step 1, because a live background process
left running is a silent leak that keeps polling after the session ends. This step is where you
confirm that stop actually took.

⛔ **A stop you didn't verify is not a stop.** Silence is not success — a still-running watcher looks
identical to a stopped one until you check. So check:

- Check the pidfile, never a host-wide process-name search:
  `[ -f sanctum/watch.pid ] && kill -0 "$(cat sanctum/watch.pid)"`.
- `sanctum/watch.pid` **absent** → clean stop. **Guard this explicitly**: do not run `cat`/`kill`
  against a pidfile that doesn't exist — that is the common, healthy outcome, not an error to probe
  further.
  `sanctum/watch.pid` present **and** `kill -0 "$(cat sanctum/watch.pid)"` fails → the watcher was
  hard-killed and never ran its cleanup, so the pidfile is **stale: remove it**
  (`rm -f sanctum/watch.pid`); the process is already gone.
  `sanctum/watch.pid` present **and** `kill -0 "$(cat sanctum/watch.pid)"` succeeds → it is still
  running; stop **that pid** and re-check.

**You should already have reported `watcher off, confirmed`** as the closeout's first action. If you
have not, do it now — **never sign off on an unverified watcher.** If no watcher was armed this
session, say so and move on; there is nothing to disarm.

## Sign off

**Give the player a short, warm sign-off** — not a corporate summary. A closeout is the end of a
shift worked together, and it should read like one.

## Done

The closeout is complete.
