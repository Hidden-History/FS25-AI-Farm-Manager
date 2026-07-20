---
name: workflow-onboarding
description: 'Onboarding (first time only, per project directory) — bind this manager to one save and write the farm''s memory from the templates.'
firstStep: './onboarding-steps/step-01-find-save.md'
---

# Workflow: Onboarding (first time only, per project directory)

Runs once, when `sanctum/config.json` doesn't exist yet. Binds this manager to exactly one
save and writes the farm's memory from the templates.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/init_sanctum.py" <project_dir>
```
Idempotent — safe to call even if part of the sanctum exists. It creates folders and copies
templates, but will **not** overwrite `config.json` or `identity/creed.md` if they already exist.

## The principle: read before you ask

**Don't ask the player for anything the disk can tell you; ask only for what it genuinely
cannot.** That ordering is the fix for a real, expensive mistake (`FRICTION-LOG.md` F-010):
an earlier session asked the player a judgment question while genuinely believing — from a
since-fixed parser bug — that the farm was a blank slate. It actually owned 18 parcels, 24
machines, and millions in debt-funded iron. The question got answered on a false premise, and
three sanctum files had to be rewritten afterward.

The save is what makes the questions meaningful. Read it first.

## Running this workflow

After running `init_sanctum.py` above, begin at {firstStep} and follow each step's
`nextStepFile` in order through step 7.

Among what onboarding establishes is `notifications.available`: step 5
(`./onboarding-steps/step-05-check-notification-mod.md`) looks for the notification mod and
confirms it is sound, then records the answer in `config.json` — so no later session discovers
it by sending a message into a void and misreading exit `2` as "the game is closed".

Load and follow: {firstStep}
