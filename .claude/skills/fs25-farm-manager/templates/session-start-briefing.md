<!-- class: briefing-snapshot (compositional output, never persisted) — this is the SHAPE for the
     chat-composed morning briefing, not a stored sanctum file. No YAML frontmatter by design (nothing
     on disk to govern or rotate). Output target: ≤60 lines / ~500 words, "Needs attention" ≤5 bullets.
     See FRONTMATTER-PARITY-SCHEMA.md §3. -->

# Morning Briefing — {{DATE}} (Session #{{SESSION_NUMBER}})

*Compose in the manager's own voice (creed tone), not as a form — lead with what needs a decision
today; the numbers back the recommendation, they aren't the point. Fill only from live sources
(`farm_snapshot.py`, `history/closeout-latest.md` for what changed, `plans/PLAN.md` +
`identity/decision-making.md` for standing plans), never from memory of a prior session. Run
`check_sanctum_freshness.py` first — an `unverifiable` verdict is not a pass.*

**In-game:** {{INGAME_DATE_TIME_SEASON}}
**Since last time:** {{TIME_ELAPSED_OR_CHANGES_SINCE_LAST_CLOSEOUT}}

## 🔴 Needs attention today
{{The lead section — top 3–5 items that need a DECISION today (money low, contract expiring, field
about to spoil, equipment broken), NOT every deviation from baseline. Hard cap 5 bullets. If nothing
needs a decision, say so plainly — an empty urgent section is a correct briefing.}}

## 🌾 Fields
{{Only fields with a state change or action needed; rest link to their dossier, not restated. Never
call a field harvest-ready without checking it isn't already cut — cross-reference
`growthState`/`lastGrowthState` against `groundType` (a bare `groundType` read gave a 20% false
positive, F-117). If they disagree, surface it as UNRESOLVED, never a clean "go harvest." List
`unknown_crop_state_on_owned_land` fields as unknown — never silently drop them.}}

## 🚜 Equipment
{{Flags only — low fuel, high wear, idle — from `state/equipment-roster.md`, not a full roster dump.}}

## 📋 Active contracts
{{What's active and what's expiring, from the live contract/mission state — not a restatement of the
contract mechanic.}}

## 💰 Finances
{{Cash/loan headline + one-line trend note pulled from `state/finances-ledger.md`'s row history (not
recomputed). Loan interest bills once per calendar month (F-124) — never imply a daily tick.}}

## Standing directives check-in
{{Only directives due or relevant today, from `plans/PLAN.md` (its Standing directives, read in
light of the Current focus) — that file owns the content; this section just filters it.}}

---
What do you want to tackle first?
