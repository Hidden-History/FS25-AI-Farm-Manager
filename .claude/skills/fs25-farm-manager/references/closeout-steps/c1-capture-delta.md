---
name: c1-capture-delta
description: 'Take delivery of the end state and record this session''s delta — append-only, and honest in-band when the log has no history yet.'
nextStepFile: './c2-session-record.md'
---

# C1: Capture and record the delta

**Progress: Step 1 of 5** — Next: Write the session record

**Capture the end state.** Regenerate the cache so it reflects where the farm actually ended, then
take delivery of the verified view — the same gate, and the same trust rules, S2 used:

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/generate_state.py" --config sanctum/config.json
python3 ".claude/skills/fs25-farm-manager/scripts/read_state.py"     --config sanctum/config.json
```

This is the view next session's briefing will diff against, which is exactly why it is captured
through the gate rather than by eye. **The trust contract from S2 applies unchanged here**: read
the `error` key and never the exit status, detect the envelope on `"sections"` and never on
`"status"`, and surface a `blocked_by` distinctly rather than folding it into a healthy section. A
closeout written from an untrustworthy view poisons the next briefing rather than this one, which
makes it harder to catch, not easier.

## The delta entry is appended by the generator — one entry per run

**You do not hand-write the delta log.** `generate_state.py` appends **one entry per run** to
`sanctum/history/delta-log.jsonl` via `delta_log.py`. Your job is to confirm the entry landed and
to read what it says changed.

⛔ **It is append-only, and a rewrite is a failure — not a tidy-up.** Newest-last, never
newest-first: newest-first would mean rewriting the file on every entry, which is precisely the
operation the design forbids. **Never edit, reorder, reformat, de-duplicate or truncate this
file.** It is the one artifact in the system that cannot be regenerated — everything else the cache
layer writes can be rebuilt with one command, but a history that was not kept cannot be
reconstructed from anything on disk. You can check the discipline held:

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/lint_append_only.py" --config sanctum/config.json
```

**A gap is never filled, never interpolated, never smoothed.** If the chain has a break, the log
emits an explicit `gap` record naming what is missing. Report it as a named gap — **never as a
rate**, and never as "nothing changed". A rate computed across a gap is a fabrication. And note
that **a lost watermark is not a pass**: it degrades the check to UNCHECKABLE, which is a finding
for the friction log, not a clean result.

## ⛔ The log has no history yet — say so IN BAND

**The delta-log artifact does not exist on this farm yet.** The code is shipped, but the log's
history begins when it is first written, not when the code landed — so the first closeouts have
**no prior entry to compute a change against**, and an entry appended today has nothing behind it.

**Do not present a first entry as a computed change notice, and do not go quiet about it.** Report
the delta the way S3 does — a diff against the previous closeout and the view you just took — and
say in one line that the computed record is only now starting to accumulate:

> *"Logged this session's delta; the change log is still building its history, so 'what moved' is
> my diff against last closeout rather than a computed record."*

Each closeout from here makes the next one better. **A degradation the player cannot see is
indistinguishable from a full answer** — which is the entire reason this is stated out loud.

## Next

Once the end state is captured and the delta recorded, read fully and follow: {nextStepFile}
