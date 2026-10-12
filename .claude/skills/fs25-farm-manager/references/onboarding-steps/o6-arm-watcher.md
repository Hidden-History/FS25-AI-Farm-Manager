---
name: o6-arm-watcher
description: 'Arm the two-way watcher before the first session — check whether one is already live, arm it if not, and prove the arm actually took.'
---

# O6: Arm the watcher

**Progress: Step 6 of 6** — Final step of onboarding

## Why this step exists on the onboarding path specifically

The two-way bridge only works in one direction until the watcher is armed. Without it the player
can answer a card and save their game all night and **nothing reacts** — the manager sits idle,
the tabs keep showing old numbers, and there is no error anywhere, because nothing failed. A
watcher that was never armed looks exactly like a quiet farm.

⛔ **Onboarding is the path that misses this, and the reason is structural.** A normal session
starts at `references/workflow-briefing.md`, whose *During the session* conduct is the only other
place the arm is described. **None of onboarding's own steps open that file** — O1–O5 mention the
watcher nowhere. Before this step existed, the sole link to it was a parenthetical on O5's last
line, carrying none of the *"read fully and follow"* force every other transition here uses; and a
session that did follow it landed on conduct prose gated on a later conversational trigger
("when the player says they're in-game"), long after the step chain had ended. So on a fresh setup
the arm was not "easy to forget" — **nothing on the path executed it.**

## Check first — never assume

⛔ **Do not assume a watcher is running, and do not assume one is not.** Both guesses have a
failure mode: assume it is running and the farm goes unwatched all session; assume it is not and
you can stomp a live one. **Check, then act on what the check said.**

```bash
[ -f sanctum/watch.pid ] && kill -0 "$(cat sanctum/watch.pid)"
```

- **`sanctum/watch.pid` absent** → no watcher. **Arm one** (below). Guard this case explicitly: do
  not run `cat`/`kill` against a pidfile that isn't there — on a fresh setup this is the normal,
  expected outcome, not an error to investigate.
- **Present and `kill -0` succeeds** → a watcher is already live. **Say so and arm nothing.** Record
  that you checked and what you found — a session that reports "watcher already up, confirmed" has
  done this step; one that stays silent has not.
- **Present and `kill -0` fails** → a stale pidfile from a crashed run. The process is already gone,
  so **remove the file** (`rm -f sanctum/watch.pid`) and arm. Scope every stop to that pid; **never**
  a host-wide kill of matching processes, which could hit something unrelated.

## Arm it

Arm under a **persistent Monitor** so its stdout lines arrive as events while you keep working:

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/wait_for_event.py" --config sanctum/config.json
```

⚠ **`--config` is not optional here.** Without it the watcher still starts and still reports saves,
but regenerates **nothing** — it prints `refresh=off` and its own `WARN` line, and the tabs keep
showing old numbers. That is the exact defect the trigger exists to fix, so arm **with** `--config`
rather than working around it afterwards.

**Arming early costs nothing.** The watcher idles at ~zero token cost between events, so there is no
reason to defer this until the player says they are in-game — and deferring it is how it gets lost.

## Prove the arm took — silence is not success

⛔ **An arm you did not verify is not an arm.** Read the watcher's first line before you move on:

- **`STARTED wait_for_event pid=… refresh=auto:…`** → armed, and the save trigger is live. This is
  the only outcome that counts as done.
- **`STARTED …` carrying `refresh=off`** → armed but **deaf to saves**. Re-arm **with** `--config`.
- **An `ERROR …` line, a non-zero exit, or no `STARTED` line at all** → **the arm FAILED.**

## If it will not arm, fail loudly

⛔ **Never let a failed arm pass as a finished onboarding.** If you cannot get a `STARTED` line with
`refresh=auto:…`:

- **Say so plainly, in the player's language, naming what you tried and what came back.**
- ⛔ **Do not tell the player the farm is covered, watched, or that you will react when they save** —
  you will not, and that sentence is the whole harm: it converts a visible failure into a silent one.
- Record it in `sanctum/history/friction-log.md` so the next session inherits the finding rather than
  rediscovering it.
- Onboarding is otherwise complete, so **continue** — but continue honestly, with the gap stated.

## Done

Onboarding is complete and the bridge is two-way. Continue with the first session
(`references/workflow-briefing.md`). ⚠ That workflow opens by clearing a **stale** watcher before it
arms; a watcher armed here, in this same session, is **live and yours**, not stale — if it stops and
re-arms one it is doing its own job correctly, and the end state is still exactly one live watcher.
