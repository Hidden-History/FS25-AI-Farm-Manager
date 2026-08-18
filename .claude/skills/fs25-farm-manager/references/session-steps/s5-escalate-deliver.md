---
name: s5-escalate-deliver
description: 'Rank the findings, split DECIDED from ESCALATED, render the briefing in the manager''s own voice, and increment session_count — only here.'
---

# S5: Escalate and deliver

**Progress: Step 5 of 5** — Final step of the session-start sequence

S4 emitted 16 duties' worth of structured output. This step decides what the player actually
hears, and in what order.

## The schema is primary; the briefing is a consumer of it

**Rank on the schema, not on the prose.** The findings you rank are S4's structured outputs; the
briefing is a **rendering** of them and never their author. Two consequences worth stating: a
figure must not first appear at rendering time (if it is worth saying, it came from a duty), and
re-rendering the same findings differently — a card, a summary, a board — must not change what
they claim.

## ⛔ Split DECIDED from ESCALATED

Every duty's output is one of two things, and **conflating them is how a player gets told a
decision was made on their behalf**:

- **DECIDED** — a recommendation you can stand behind and act on within the standing directives
  and this farm's `identity/decision-making.md`. Say what you recommend and why.
- **ESCALATED** — the player's call, presented as a decision with its options and trade-offs, not
  as a nudge. **The register marks these `escalate: true`, and today that is exactly three
  duties**: crop planning (D-02), fleet capital (D-13), and buying land (D-16). Read the flag from
  the row — never from this list, which is a description of the register today and not its
  authority.

An `escalate: true` duty **never** becomes DECIDED because its answer looks obvious, and never
gets dropped because its input was blocked — a block is escalated *as a block*, with what it
prevents. Consult `identity/decision-making.md` for how this player wants to be presented with a
decision; that file, not this one, sets the shape.

## Compose the briefing

Use `templates/session-start-briefing.md` as the **shape**, but **write it in your own voice as
the manager**, not as a form dump. **Lead with what needs a decision today** — a briefing is not a
data dump, and the numbers are evidence for the recommendation rather than the point of the
exercise. Anything S2 or S3 degraded is stated in the briefing itself, in-band, not appended as a
caveat.

## If you push a card, record what it asked

Only push a card if it genuinely cannot wait to be asked (`references/notifications.md` — under-
sending is the whole discipline). When you do:

⛔ **Record the card's own `id` AND the question it asked, at send time.** **Nothing on the wire
carries a card's original text**, so a reply arrives identified only by its id. If the question
was not written down when it was sent, the answer cannot be traced back to what it asked — and a
reply matched to the wrong question is worse than a lost one, because it is actionable. Write both
as the card is sent, never afterwards from memory.

## Check the trend, then open this session's ledger row

Read `sanctum/state/finances-ledger.md` for the cash/loan trend **across** sessions — is the farm
actually getting healthier, or does it just look fine today? A single session's figures cannot answer
that, which is why the ledger exists. **Note a notable trend in the briefing.**

Then **append this session's cash/loan row now, at the start**, as an opening snapshot — so it is
captured even if the session turns out short. ⛔ **Closeout completes this row's Notes and never
appends a second one** (C2, and `references/sanctum-upkeep.md` holds the contract). One row per
session: opened here, completed at closeout.

## Increment `session_count` — here and nowhere else

**Increment `session_count`** in `sanctum/config.json`. **Only here — never again at closeout.**
Closeout deliberately does not touch it, and a second increment silently corrupts every
per-session count that reads it.

## Done

The session-start sequence is complete. Deliver the briefing, then conduct the rest of the session
per the **During the session** guidance in `references/workflow-briefing.md`.
