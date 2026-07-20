# Pushing a notification to the player's screen

You can put a message on the player's screen **while they're playing**, via the AI Farm
Manager 25 mod. This file is about *when that's justified*.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/notify_farm_manager.py" \
    -s warn -t Market -i finances "Oat is at its annual low: \$431/1000L, peaks \$644 on day 11."
```

`-s` `ok`|`info`|`warn`|`critical` sets the accent colour · `-t` the card title · `-i` the
glyph (`--help` lists all 31) · exit `0` delivered, `2` not consumed, `1` error.

**Requires the mod.** If it is not installed and enabled you get exit `2` every time. The
script prints what it observed; pass that on rather than guessing.

## This is the one thing in this skill that INTERRUPTS

Every other capability answers a question the player asked. This one speaks without being
spoken to, into a game they're concentrating on. That inverts the usual bar: the question
is not *"is this true?"* but **"is this worth taking their hands off the wheel for?"**

A notification the player didn't need teaches them to ignore the next one — including the
one that mattered. **The cost of a bad notification is not zero; it is the credibility of
every future one.** Under-send.

Silence is the default. Send when **all** of these hold:

1. **It's time-critical.** It changes what they should do in the next few minutes. At
   `daysPerPeriod = 1`, a harvest window can be as narrow as ~1 in-game day
   (`references/time-mechanics.md`) — that is worth a notification. This is **not** a
   portable constant: read the bound farm's actual `daysPerPeriod` (from `environment.xml`)
   before judging urgency — a higher setting widens the window and can turn "spoiling
   today" into a false alarm. "Wheat is up 4%" is not time-critical; it'll keep until the
   next briefing.
2. **They can act on it now**, from where they are.
3. **They'd want the interruption.** Ask honestly. If the answer is "they'd sigh," don't.

If it can wait for the briefing, **let it wait for the briefing.** That is what the
briefing is for.

## Severity means something — don't inflate it

The accent colour is the whole design. It only carries information if it's used honestly:

| | |
|---|---|
| `critical` | money or an asset is being lost **right now**. Notional cash negative; a crop spoiling today. |
| `warn` | a closing window. An input at its annual low for one period; a contract deadline. |
| `info` | worth knowing, no action implied. |
| `ok` | a thing they asked for finished. |

Everything-is-`critical` is the same failure as everything-is-green: the colour stops
being a signal and becomes decoration.

## The rules that don't relax

**Never notify a number you haven't read.** Everything in `references/reading-the-save.md`
applies harder here: a briefing figure gets scrutinised, a popup gets believed and acted on
in the moment. Same for the creed's notional-debt rule — a notification quoting real save
cash instead of notional cash is exactly the number the creed forbids reporting.

**Exit code 2 means NOT DELIVERED.** The mod truncates the bridge file to consume a
message; the script waits for that and reports honestly. `2` means nothing read it — the
mod isn't installed, or isn't enabled, or the game is closed. **Do not report a `2` as
sent.** And do not guess which cause it was; the script prints what it observed, so pass
that on. The v1.0 sender guessed "game may not be running" for every failure and was wrong
every time — see FRICTION-LOG F-029.

**Delivered ≠ seen.** Exit `0` proves the mod read the bytes. Nothing on disk can prove the
player looked at the screen. Never tell them "I notified you" as though it were received.

**VERIFIED end-to-end 2026-07-16** — a real game returned a real `0`: message consumed via
`getfenv(0).deleteFile`, shown once, zero log lines. Mod v1.4.0.0.

**RE-VERIFIED on mod v2.0.1.0, 2026-07-16** — and the gap between those two lines is the
lesson. A farm was found running v2.0.1.0 while this file only claimed v1.4.0.0, so by this
file's own rule the bridge was *unverified* — but nothing surfaced that at send time, and
two messages went out on it before anyone checked the installed version. Both landed
(`critical` + `warn`, exit `0`), and the player confirmed **both cards appeared on screen** —
which is the only evidence that ever closes "delivered ≠ seen", since no exit code can.
**Read the installed `modDesc.xml` version before trusting this section**, rather than
assuming the version named here is the one running.

That took four real-game runs, and every failure was invisible to a passing test suite:
protocol 1 could never have worked at all (FS25 sandboxes `io` to write-only — 60 tests
green, F-035); `deleteFile` was refused from a mod's own environment (450 log errors, F-036);
and the bridge folder must be `modSettings/<mod name>/`, which the game itself spelled out
in an `Info:` line next to the error. **Tested logic is not a working feature** — this bridge
is the standing proof. If the mod changes, it is unverified again until a game says otherwise.

## The return half — ingesting the player's replies

An actionable card (`--id` + `--action`/`--choice`, see `notify_farm_manager.py --help`) can be
*answered* in-game: the player clicks, and the mod appends their choice to `replies.xml` beside
the bridge. Reading that back is the return half of the loop, and **the manager does it
automatically** — you do not poll by hand.

- **`scripts/read_replies.py`** ingests `replies.xml` into a durable sanctum ledger
  (`replies-ledger.json`), dedups on `(id, action)` — the mod's own idempotency contract, so the
  same id can legitimately carry `yes` then `dismiss` — and truncates the consumed file
  *loss-proof*: the ledger is written before the guarded truncate, and a reply that arrives
  mid-ingest is re-read next run rather than dropped. Malformed `replies.xml` or a corrupt ledger
  fail loud and touch nothing.
- **`scripts/wait_for_event.py`** is what fires it. Armed at briefing under a persistent Monitor
  (`references/workflow-briefing.md`), it idles at ~zero token cost and emits one line when the
  game writes `replies.xml`; on that event you run `read_replies.py`, reconcile the new entries
  against what you asked, and respond — often a follow-up card back through this same notifier.
  It is disarmed and verified off at closeout (`references/workflow-closeout.md`).

So a notification is not a one-way announcement: send an actionable card, and be ready to read
and answer what comes back — the same under-send discipline applies to the follow-up.
