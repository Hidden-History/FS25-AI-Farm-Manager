---
class: briefing-snapshot
load: B
owns: "the single most-recent session's closeout — the file every briefing reads first"
cap_lines: 90
cap_kb: 5
rotation_trigger: none
archive_target: N/A
reconciliation: "full overwrite every closeout IS the rotation; mirrors templates/session-closeout.md's shape; never a second copy of friction-log"
format_version: 1
parity_spec:
  required_sections: []
---

_No sessions yet. This file is written after the first closeout._

_What this file is: a single, always-current snapshot of the most recent
session's closeout -- not a log. It gets **fully overwritten** at the end of
every session with that session's write-up (it takes the same shape as
`templates/session-closeout.md`), while a permanent copy of each one is archived to
`sanctum/history/journal/{{date}}-session-{{n}}.md` so the history isn't lost. The full
overwrite each close **is** its rotation -- it never accumulates, so its only bloat risk is
per-session size, which the 90-line/5 KB cap bounds. The next session's briefing reads this file
first to know what changed and what to avoid repeating._

_The section worth never skipping, in the real file this becomes: **"What
didn't work."** A recommendation that missed, a contract that wasn't worth it,
a sale timed badly, a plan abandoned mid-session -- whatever it is, write it
down specifically. That section is the one thing standing between this session
and next session confidently suggesting the exact same mistake. "Nothing went
wrong this session" is a fine entry when it's true; inventing a problem to fill
the section is not. Don't restate a friction-log entry here -- cite its ID; this
file carries the decision narrative, `history/friction-log.md` carries the defect list._
