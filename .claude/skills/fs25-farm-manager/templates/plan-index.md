---
class: pointer
load: C
owns: "a one-line-per-session index of the farm's plan history — which session decided what, without opening each session-plan file"
cap_lines: 500
cap_kb: 50
rotation_trigger: none
archive_target: N/A
reconciliation: "one row per session ever, appended each closeout, never rewritten; nested rotation at hundreds-of-sessions scale is flagged, not yet solved (mirrors journal/INDEX.md's F4)"
format_version: 1
parity_spec:
  required_sections: ["## Session plan index"]
---

# Plan Index

_One row per session ever, appended at every closeout — the human-readable companion to the
per-session files in `plans/sessions/`. It exists so a question like "when did we decide maize
on Field 70, and why" is answerable from this one file, without opening every
`{{date}}-session-{{n}}.md`. Each row records the **in-game season and day** (from
`read_environment.py`) alongside the real-world date — a farm's plan is paced by the game
calendar (Spring day 3 → Summer day 12), so the trail only reads meaningfully on that calendar.
Append only; never rewrite a past row. Newest at the bottom._

## Session plan index

| Date | Session # | In-game (season / day) | File | Key decisions this session |
|---|---|---|---|---|
| {{DATE}} | {{N}} | {{SEASON}} / day {{DAY}} | sessions/{{date}}-session-{{n}}.md | {{one line — the session's headline plan decision(s), e.g. "maize on Field 70; bought cannery"}} |

_At ~500 lines this file itself will eventually need rotation (nested archive by year); flagged,
not yet solved — a farm reaching hundreds of sessions is a good problem to have first._
