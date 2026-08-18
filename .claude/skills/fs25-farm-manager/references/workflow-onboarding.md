---
name: workflow-onboarding
description: 'Onboarding (first time only, per project directory) — bind this manager to one save and write the farm''s memory from the templates.'
firstStep: './onboarding-steps/o1-bind-save.md'
---

# Workflow: Onboarding (first time only, per project directory)

⛔ **Runs once, and only when `sanctum/config.json` does not exist yet.** That absence is the gate —
if the config is there, this farm is already onboarded and this workflow must not run again. Binds
this manager to exactly one save and writes the farm's memory from the templates.

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/init_sanctum.py" <project_dir>
```

Idempotent — safe to call even if part of the sanctum exists. It creates folders and copies
templates, but ⛔ **will not overwrite `config.json` or `identity/creed.md` if they already exist.**
Those two are the farm's identity and its binding; silently replacing either would erase the player's
own answers and rebind the manager underneath them.

## The principle: read before you ask

**Don't ask the player for anything the disk can tell you; ask only for what it genuinely cannot.**

That ordering is the fix for a real, expensive mistake (`FRICTION-LOG.md` F-010): an earlier session
asked the player a judgment question while genuinely believing — from a since-fixed parser bug — that
the farm was a blank slate. It actually owned 18 parcels, 24 machines, and millions in debt-funded
iron. The question got answered on a false premise, and three sanctum files had to be rewritten
afterward.

The save is what makes the questions meaningful. **Read it first.**

## Running this workflow

After running `init_sanctum.py` above, onboarding is **five steps**. Begin at {firstStep} and follow
each step's `nextStepFile` in order — **if you skip opening any of the five and improvise its step
instead, say so out loud before continuing, rather than letting the drop-out go unannounced.**

1. **O1 · Bind the save** — `./onboarding-steps/o1-bind-save.md`
2. **O2 · Take delivery and present the position** — `./onboarding-steps/o2-present-position.md`
3. **O3 · The profile conversation** — `./onboarding-steps/o3-profile.md`
4. **O4 · Check the notification bridge** — `./onboarding-steps/o4-bridge-check.md`
5. **O5 · Write the sanctum and confirm ready** — `./onboarding-steps/o5-write-sanctum.md`

Among what onboarding establishes is `notifications.available`: **O4**
(`./onboarding-steps/o4-bridge-check.md`) looks for the notification mod and confirms it is sound,
then records the answer in `config.json` — so no later session discovers it by sending a message into
a void and misreading exit `2` as "the game is closed".

Load and follow: {firstStep}
