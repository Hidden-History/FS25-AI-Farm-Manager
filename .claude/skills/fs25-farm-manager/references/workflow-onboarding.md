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

⚠ **TWO narrow exemptions, and naming them is what keeps them narrow.**

**(1) The player's name and language — identity DATA, not judgments.** Asked at the very top of
**O1**, before `locate_save.py` or anything else runs. F-010's rule is that the position precedes
every **judgment** question — the ones whose answers are only meaningful once the player has seen
their real farm. **A name and a language are neither informed by the position nor changed by it**:
no briefing could alter what someone wants to be called or which language they read. They are
therefore not gated behind the read, and they *cannot* wait for it — every sentence O1 and O2 speak
is spoken in some language, so asking later means having already got it wrong. (BUG-025 (i) and
(ii), and LIVE TEST 5, where a full position briefing was delivered in English before the question
was reached.)

⚠ **Read F-010's recorded fix carefully, because its WORDING and its REASON do not agree here, and
the reason governs.** The fix is written as *"reorder to locate → collect → summarize the real
position → then ask identity and priorities"* — the word *identity* is in it. But the rationale it
gives for itself is that the ordering *"prevents the most expensive class of waste: asking a human
to DECIDE before I've read the facts."* **That reason is about decisions.** A name and a language
are not decisions the position informs: no figure in the briefing could change what someone wants
to be called or which language they read, so deferring them buys none of the waste-prevention
F-010 was written to buy — and costs a whole briefing spoken in the wrong language. The wording
swept identity in alongside priorities; the reason never reached it. **Priorities remain squarely
inside F-010 and still wait for O2.** ⛔ **Do not read this as licence to re-litigate F-010 by
finding a sympathetic reason for the next question** — the test is narrow and mechanical: *could
the position's contents change this answer?* If yes, it is a judgment and it waits.

**(2) The farm's name.** The state view
cannot be rendered at all until `config.json` carries a `farm_name` — `aggregate_render.build_header`
refuses a placeholder rather than inventing one from the sanctum directory name. So `farm_name` is a
datum that **asking supplies and reading requires**, and it is asked at the top of **O2**, ahead of
the read (BUG-025 (iii); the ordering rule above is F-010's fix, which never exempted it).
⛔ **These exemptions cover `player_name`, `language` and `farm_name` — and nothing else.** `farm_name` qualifies because it is an
*input to the read*, not a judgment the read informs; the other two because they are identity data
the read has no bearing on. The rule above still governs every question
whose answer would be meaningless, or wrong, without the position on the table. **Never generalise
it into "ask what you need up front"**: that is the shape of F-010 itself.

⛔ **And these are exemptions from the ORDERING, never from asking.** The player is asked before
anything is written — for all three keys. ⚠ **Until a key is answered it stays ABSENT from
`config.json`; it is never written as `"unknown"` to be corrected later.** Absence is the state
the freshness check can see; a placeholder that gets overwritten before the check ever runs is
invisible to every gate (LIVE TEST 5). Writing a plausible name first and asking for confirmation afterwards satisfies
the gate without answering the question and emits no error at all — the harm that made this a bug.

## Running this workflow

After running `init_sanctum.py` above, onboarding is **five steps**. Begin at {firstStep} and follow
each step's `nextStepFile` in order — **if you skip opening any of the five and improvise its step
instead, say so out loud before continuing, rather than letting the drop-out go unannounced.**

1. **O1 · Ask the player's name and language, then bind the save** — `./onboarding-steps/o1-bind-save.md`
2. **O2 · Confirm the farm name, take delivery, present the position** — `./onboarding-steps/o2-present-position.md`
3. **O3 · The profile conversation** (doctrine and priorities — ⚠ **identity was already settled at O1 and is not re-asked here**) — `./onboarding-steps/o3-profile.md`
4. **O4 · Check the notification bridge** — `./onboarding-steps/o4-bridge-check.md`
5. **O5 · Write the sanctum and confirm ready** — `./onboarding-steps/o5-write-sanctum.md`

Among what onboarding establishes is `notifications.available`: **O4**
(`./onboarding-steps/o4-bridge-check.md`) looks for the notification mod and confirms it is sound,
then records the answer in `config.json` — so no later session discovers it by sending a message into
a void and misreading exit `2` as "the game is closed".

Load and follow: {firstStep}
