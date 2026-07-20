# Time mechanics in FS25

How in-game time actually moves. Load-bearing for any planning advice — "fast-forward to
harvest" is sound at one setting and absurd at another, and the manager cannot tell which
without this.

General FS25 knowledge (portable across farms), except where a value is marked as read from
the bound save.

## Three ways time advances — they are NOT interchangeable

| Mechanism | What it does | Real time cost | Continuous? |
|---|---|---|---|
| **Normal play** | Time runs at `timeScale` | proportional | yes |
| **Fast-forward** (`timeScale`) | Multiplier on the clock | divided by the multiplier | yes |
| **Sleep trigger** | Player sleeps *to a chosen time* | ~instant | **NO — discontinuous jump** |

**Sleep is the one that breaks naive reasoning.** It's a trigger the player walks to (a bed /
farmhouse), and it advances the world to a target time immediately. The world still moves —
crops grow, weeds spread, prices roll to the next period, contracts expire — but the player
spends no real time and burns no fuel getting there.

Told to us by the player, 2026-07-16. Not derivable from any savegame file.

## timeScale

- Lives in `careerSavegame.xml` → `<timeScale>`. Read it via `read_career.py`.
- **VERIFIED to update in the save**: observed 1.000000 → 3.000000 after the player changed it
  in-game (2026-07-16). It is not a load-time-only constant.
- **Steps are not the set we assumed.** We guessed 1/5/15/30/60/120; the player selected **×3**.
  Do not hardcode a step list — read the value.
- Higher = less real time per in-game day.

## daysPerPeriod, and why the calendar is tight here

- `<daysPerPeriod>` in environment.xml. **This save: 1** — so 1 in-game day = 1 month = 1
  period, and **12 days = 1 year**.
- That makes `economy.xml`'s 12-period price history a **12-day** cycle, not a 12-month one.
  Day 6 = LATE_SUMMER; MID_WINTER (the wheat/oat price peak) is **day 11**.
- It also compresses growth and spoilage brutally — a harvest window can be ~1 day wide.

## The real-time conversion — OPEN, and here's why it's hard

**Unresolved.** What's established:
- `dayTime` = minutes-of-day (0–1440). `playTime` = minutes. Both proven (F-002, F-022).
- At `timeScale 1.0` they advanced by **identical** deltas (+9.408623 vs +9.408630) — which is
  exactly why 1× can never settle it: *real* minutes and *game* minutes are the same thing at
  1×, so the two fields are indistinguishable.

The test, which needs ×≠1 (baseline captured at ×3: dayTime 650.463745, playTime 154.955917):
- `Δ dayTime / Δ playTime == timeScale` → `playTime` is REAL minutes; `timeScale` is game-min
  per real-min; one in-game day costs `1440 / timeScale` real minutes (8.0 h at ×3).
- `Δ dayTime / Δ playTime == 1` → `playTime` is GAME minutes and `timeScale` means something
  else.

> **The test is void if the player slept in the interval.** Sleep advances `dayTime` while
> `playTime` barely moves, so the ratio blows up and would "prove" an absurd time scale —
> confidently, and wrongly. **Before trusting any such measurement, ask the player whether they
> slept.** Do not infer it from the numbers; a big ratio and a fast setting look identical.

## Consequences for planning — the actual point

- **Never quote a real-time cost without reading `timeScale` first.** Same advice, opposite
  verdict at ×1 vs ×60.
- **Sleep is usually the cheap way to reach a future date** (a price peak, a growth stage) —
  it costs no real time and no fuel. But it is a *commitment*: everything with a deadline
  between now and the target resolves without the player. Before recommending sleep, check what
  gets skipped:
  - contracts expiring before the target (they'll be lost)
  - **standing harvest-ready crops — a harvest window here can be ~1 day; sleeping past it
    spoils the crop**
  - **animals needing feed/water** — read `farm_snapshot.py`; **never assume a farm has no
    husbandry.** An earlier version of this file asserted "(none on this farm)" here as
    portable fact. It was imported from a different farm and was **wrong** for the next
    one — that farm actually had livestock and production points — following this checklist
    verbatim would have cleared a sleep that could starve livestock.
  - **production chains needing input** — same rule, same reason: read it, don't assume it.
- **Weather matters when skipping**: hail/rain in the forecast can damage or block work.
- **Idle in-game days on a leveraged farm are not free, but not the way you'd guess** — loan
  interest is charged once at each **month-end**, on the balance (see `sanctum/identity/creed.md`), not
  accrued per day (F-124). Skipping days *within* the current month adds no extra interest;
  the cost only bites if the skip **crosses a month-end** — count month-ends crossed, not days
  skipped, and show that cost rather than assuming a per-day one.

## Save freshness — not a time mechanic, but constantly confused with one

The savegame's **mtime is the only honest freshness signal**. `autoSaveInterval` bounds
**nothing**: the interval elapsing only makes a save *due*, and FS25 defers the write until the
player next opens the map/menu. A save can be arbitrarily stale mid-session with nothing wrong
and nobody idle.

**Never infer player activity from write patterns.** The lead did exactly that — saw no writes,
announced "the player has paused", and was wrong; they were farming the whole time (F-023).
