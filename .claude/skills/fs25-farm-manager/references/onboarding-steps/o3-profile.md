---
name: o3-profile
description: 'Ask only the judgment questions the disk genuinely cannot answer — identity, doctrine, and declared intent.'
nextStepFile: './o4-bridge-check.md'
---

# O3: The profile conversation

**Progress: Step 3 of 5** — Next: Check the notification bridge

**Now ask the judgment questions**, informed by the position O2 just put on the table:

- **Identity — already answered; do NOT re-ask.** The player's `player_name` and `language` were
  asked at the very top of O1, before any command ran, and `farm_name` was confirmed at O2 ahead of
  the gate that needs it. All three are recorded in `config.json`. ⛔ **Re-asking any of them here
  tells the player you weren't listening** — and re-asking the language after ten minutes of
  speaking it is worse than not asking at all. ⭐ **You should already be speaking their language;
  keep doing so** for this interview, O4, O5 and every session after.
- **Doctrine**: open `templates/decision-making.md` and ask what its sections ask for. **That file
  is the source of truth for this interview**, and it covers more than a list here would keep up
  with — including how the player wants to be *told* things, which shapes tone more than any other
  answer. Work through it as a conversation in your own words, not a questionnaire. Don't assume
  every farm has a house rule — just ask; "none beyond the game's own rules" is a complete answer.
- **What the disk genuinely cannot answer** — the three items in SKILL.md's Ground Rules (plus the
  loan interest rate, which is conditionally derivable rather than on this list — see the same
  section). Short, and **neither hectares nor field ownership is on it.**
- **Scenario / playstyle** — ask this one outright, every onboarding; don't leave it implied. Is the
  player playing this save toward a specific scenario, challenge, or preset — a no-loan run, a
  hard-mode start-from-nothing, an organic-only game, a particular playstyle goal — or just an open
  career? This is **player-declared intent**, the one thing the save genuinely can't reveal (unlike
  day/season/difficulty, which it can), so it's a real judgment question, not a decode target.
  Record the answer in `decision-making.md`'s **Self-imposed constraints** (and, if it's a firm rule,
  in `config.json`'s `house_rules`). "Open career, no special goal" is a complete answer.

## ⛔ Never ask for anything the save already told you

**Never** fold in **cash, loan, land, hectares, land cost, field ownership, fleet, day, season,
weather, or store prices.** Every one of those came from O2's position, not from a question.

Asking for one is not a harmless double-check: it tells the player the manager didn't read their
save, and it invites an answer from memory that then **overwrites a correct reading with a
half-remembered one.** If a figure here looks wrong, go back to the view and say what disagrees —
don't ask the player to arbitrate a number you can read.

## Next

Once the judgment questions are answered, read fully and follow: {nextStepFile}
