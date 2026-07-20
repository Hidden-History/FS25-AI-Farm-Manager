# Time & Calendar Settings

**Sources:** this file cannot be rebuilt against a manual PDF the way the rest of `game-guide/`
was — neither `FS25-manual_EN.pdf` nor `FS25HF-manual_EN.pdf` covers `daysPerPeriod`/`timeScale`/
sleep at all (confirmed by a full-text keyword scan of both editions for `day`/`month`/`period`/
`timeScale`/`sleep`: the only settings content in either manual is p.4's difficulty-preset "Mode
Options" and the multiplayer session settings — neither mentions this topic). Since there is no
PDF to cite, this file is instead re-grounded in the skill's own **verified, game-file-sourced**
references — primarily `time-mechanics.md` (its facts are confirmed against a live save, not
Academy-sourced) and `reading-the-save.md`, plus `game-guide/crops.md`/`finances.md` where a
manual page does corroborate an adjacent point. Content previously sourced to the FS25 Academy
(now a deprioritized source — see `game-guide/index.md`'s punch list) is either dropped where it
contradicts a verified fact, or kept only as an explicitly labeled unverified note.

**This file is a distillation, not the live source of truth** — see the in-game Help for the
live version of this content.

## Why this is planning-critical (unchanged from the prior pass)

Every time-based mechanic elsewhere in this skill scales with `daysPerPeriod`:

- **Crop growth, harvest, and spoilage windows** — `time-mechanics.md` confirms, on a save
  where `daysPerPeriod = 1`, "a harvest window can be ~1 day wide." That's a save-specific
  observation, not a portable constant — always read the bound farm's actual value (see below)
  before judging urgency. Cross-reference `crop-calendar.md`'s Spoilage section and
  `game-guide/crops.md`'s per-crop windows.
- **Loan interest** — `finances.md` establishes interest is billed once per month-end. The
  annualized-rate formula (`loanInterest × 12`) assumes this holds at every `daysPerPeriod`
  value, but **that flat-monthly assumption is explicitly not yet empirically confirmed on a
  save with `daysPerPeriod != 1`** (see `finances.md`'s own caveat) — don't overstate its
  certainty here either.
- **Animal feed/water cadence** and **contract deadlines** also run against the in-game
  calendar — see `animals.md` and `finances.md` respectively.

**Practical rule for the manager: always read the farm's actual `<daysPerPeriod>` (from
`environment.xml`, via `read_environment.py` — see `time-mechanics.md`/`reading-the-save.md`)
before giving any timing advice.** This is a game-file-sourced instruction, not a manual/Academy
claim.

## daysPerPeriod

**Verified mechanism (`time-mechanics.md`):** `<daysPerPeriod>` lives in `environment.xml`. It
sets how many in-game days make up one "period" (= one month in the game's own calendar
language) — e.g. a save with `daysPerPeriod = 1` has 1 in-game day = 1 month = 1 period.

**A year is always 12 periods, at any setting — grounded in a verified structural fact, not
Academy arithmetic:** `time-mechanics.md` notes `economy.xml`'s price-history table has exactly
12 period-cells (on a `daysPerPeriod = 1` save, that's a 12-*day* price cycle, not a 12-month
one). The 12-period structure is the file's own shape, independent of the `daysPerPeriod` value
— it's what makes a `× 12` annualization formula dimensionally sound at any setting, though see
above for the still-open question of whether the *amount* being annualized stays flat.

**Academy-sourced, NOT verified — kept only as a plausible note:** a previous pass cited Academy
news_id=289 for a specific adjustable range ("1 to 28 days per month") and a stated default
("one day per month"). Neither figure is confirmed by `time-mechanics.md`, `reading-the-save.md`,
or a PDF — **don't treat the range or default as fact.** If the exact configurable range matters
for a task, that's an in-game settings-menu question, not something this skill can currently
answer from a save file alone (a save only records the *current* value, not the valid range).

## timeScale (fast-forward)

`time-mechanics.md` owns this mechanic in full, verified against a live save: lives in
`careerSavegame.xml` → `<timeScale>`, read via `read_career.py`, confirmed to update live when
the player changes it in-game.

**Dropped, not carried forward:** a previous pass cited an Academy-sourced adjustable range
("between ×0.05 and ×360"). This **contradicts** `time-mechanics.md`'s own explicit, verified
finding: *"Steps are not the set we assumed. We guessed 1/5/15/30/60/120; the player selected
×3. Do not hardcode a step list — read the value."* That's a direct warning against assuming any
fixed range or step list for `timeScale` — the Academy figure is dropped here rather than kept
as "unverified," since it actively conflicts with a higher-trust source rather than merely
lacking corroboration.

## Sleep

`time-mechanics.md` owns this mechanic in full: a discontinuous jump (not proportional to
`timeScale`), told to the skill by the player directly and not derivable from a savegame file.
See that file for what to check before recommending it (standing harvest-ready crops, contract
deadlines, animal feed/husbandry, production-chain inputs).

## Seasonal Growth toggle

**Manual-sourced (`game-guide/crops.md`, FS25HF p.13, base manual agrees):** "Seasonal growth"
can be deactivated to allow planting/harvesting at any time, overriding the crop calendar
entirely. This is a separate on/off setting from `daysPerPeriod` — one controls whether the
calendar is enforced at all, the other controls how long a "month" lasts while it is. See
`game-guide/crops.md`'s Seasonal Farming section and `crop-calendar.md` for the calendar itself;
not duplicated here.

## Not covered by any source available to this skill

No source here (verified game-file facts, or either manual PDF) states: the exact configurable
range or default for `daysPerPeriod`, the exact configurable range for `timeScale`, or a formula
for how in-game month length "changes with the turn of the seasons" (a claim from a
now-deprioritized Academy source, never corroborated). None of these are asserted as fact.
