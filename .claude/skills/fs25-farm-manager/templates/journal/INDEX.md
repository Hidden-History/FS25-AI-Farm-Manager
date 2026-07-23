---
class: pointer
load: C
owns: "a one-line-per-session index of the journal — the trend view without opening archived files"
cap_lines: 500
cap_kb: 50
rotation_trigger: none
archive_target: N/A
reconciliation: "one row per session ever, appended each closeout, never rewritten; nested rotation at hundreds-of-sessions scale is flagged, not yet solved (F4)"
format_version: 1
parity_spec:
  required_sections: ["## Session index"]
---

# Journal Index

_One row per session ever, appended at every closeout — the human-readable companion to the
per-session files in this directory. It exists so a trend question ("how has debt moved over ten
sessions?") is answerable from this one file, without opening every `{{date}}-session-{{n}}.md`
(hot or archived). Each row records the **in-game season and day** (from `read_environment.py`),
not just the real-world date — a farm's progress is paced by the game calendar (Spring day 3 →
Summer day 12), so the trend only reads meaningfully on that calendar. Append only; never rewrite
a past row. Newest at the bottom._

## Session index

| Date | Session # | In-game (season / day) | File | One-line + trend (cash / debt / land) |
|---|---|---|---|---|
| {{DATE}} | {{N}} | {{SEASON}} / day {{DAY}} | {{date}}-session-{{n}}.md | {{one-line summary — cash {{$}}, debt {{$}}, land {{ha}}}} |

_At ~500 lines this file itself will eventually need rotation (nested archive by year); flagged,
not yet solved — a farm reaching hundreds of sessions is a good problem to have first._
