#!/usr/bin/env python3
"""
wait_for_event.py

The idle-at-zero-cost half of the manager's event loop: poll the two files the
GAME writes -- the bound savegame's careerSavegame.xml and the mod's
replies.xml -- and, on a save, RUN THE GENERATOR ITSELF.

    python3 wait_for_event.py --config /path/to/sanctum/config.json
    python3 wait_for_event.py --replies R.xml --savegame S.xml --marker M.json

Run it under a persistent Monitor: the wait then lives in the shell, never the
model loop, so cost scales with the number of real events, not idle time
(BP-066). Its stdout lines are:

    STARTED wait_for_event pid=<n> interval=<s> refresh=<mode> replies=<path> savegame=<path>
    EVENT replies content:<hash>
    EVENT savegame <mtime>:<size> (startup-backlog)
    REFRESH auto exit=<n> <result> (attempt <n>)
    WARN <message>             (armed, but with a capability switched off)
    ERROR <message>            (a failed arm also exits non-zero -- VISIBLE)

- EVENT replies  -> a player answered a card; run read_replies.py, reconcile,
                    respond. THIS HALF IS STILL THE MANAGER'S -- answering a
                    player takes judgement, which is what an agent is for.
- EVENT savegame -> the game wrote a save. THIS HALF IS NOT THE MANAGER'S ANY
                    MORE: this script fires refresh_state.py auto itself and
                    reports the outcome on a REFRESH line. The session reads
                    generated artifacts; it does not run the generator.

---------------------------------------------------------------------------
WHY THE WATCHER PULLS THE TRIGGER
---------------------------------------------------------------------------
The owner live-tested and reported "nothing has changed in the tabs". The tabs
render files a Python script generates, and NOTHING RAN THE SCRIPT -- the
generator existed and had no home for its on-save trigger. There was nowhere
else to put it: neither .claude/ carries hooks, WSL cannot watch /mnt/c
(WSL#4739), and Claude Code has no hook for "an external file changed". This
process is already awake, already polling at 1 s, and already knows the moment
a save lands. Waking an AGENT to run a script it could run itself costs a turn
and tokens for no judgement (DEC-131).

---------------------------------------------------------------------------
WHY RETRY-UNTIL-0, NOT DEBOUNCE  (the still-saving interaction)
---------------------------------------------------------------------------
A save is 53 files over ~8.7 measured seconds, and refresh_state.py refuses to
read until the newest mtime in the WHOLE save is SETTLE_QUIET_SECONDS (20 s)
old -- so the first fire after a save is expected to return exit 3
(still_saving). That is not a failure; it is "ask again in a moment".

The alternative shape -- debounce, fire once ~20 s after the last event -- was
rejected because THIS WATCHER ONLY WATCHES careerSavegame.xml, one of the 53.
A debounce that assumed "careerSavegame.xml settled, so the save is over"
would be depending on write ORDER, which is exactly the dependency
cache_provenance.py refuses by construction ("no engine documentation promises
it ... a check built on it would silently become a no-op the day a mod or a
patch reordered the writes"). If any other file is written after ours, no
further event ever fires, and a single debounced shot lands inside the quiet
window, gets exit 3, and is DROPPED -- a missed refresh, silently.

So: fire immediately, then re-fire on a bounded backoff until exit 0.
Ordering-independent, and biased the way the cost is -- `auto` is a genuine
no-op when nothing moved, so an extra fire is cheap and a missed one is not.

  exit 0 -> done. Report the result and stop.
  exit 3 -> retry after the next backoff delay. Bounded: when the delays run
            out the state is NOT refreshed and nobody knows, so that exhaustion
            is an ERROR, never a quiet give-up.
  else   -> FAILED, reported as ERROR and NEVER retried. A refresh that
            genuinely errored must be visible, not retried into silence.

Nothing here busy-loops: the retry is a due-time checked once per existing
poll cycle, so the loop keeps its own sleep and never spins.

---------------------------------------------------------------------------
THE TRIGGER IS ARMED ONLY BY AN EXPLICIT --config
---------------------------------------------------------------------------
It never DISCOVERS a config for this. _find_config() walks up from the cwd, and
on this machine that walk finds a real sanctum bound to the owner's live
savegame -- a watcher started in the wrong directory would fire the generator
against a farm nobody asked about. So the trigger takes the path the operator
named, or it stays off and SAYS SO on a WARN line and in the STARTED line.

---------------------------------------------------------------------------
TWO CHANNELS, TWO TRUTHS (the crown-jewel fix)
---------------------------------------------------------------------------
The two files are NOT symmetric, so they are polled differently:

- The SAVEGAME is append-only from our side (nobody truncates it) and re-reading
  it is idempotent, so it keys on mtime+size against a PERSISTED marker and
  reconciles to current state -- a missed intermediate save is harmless.

- replies.xml is TRUNCATED by read_replies.py after ingest, and that mutation
  would make an mtime-keyed watcher (a) self-trigger an unbounded wake loop
  (truncate bumps mtime -> re-fire -> re-ingest -> ...) and (b) silently LOSE a
  reply if the session dies after the marker advanced but before the ingest ran.
  So the replies channel keys on CONTENT, not mtime: it emits iff the settled
  file carries a <reply>, holds the last-emitted fingerprint IN MEMORY (never
  persisted), and treats the empty root as the durable "processed" marker (set
  by read_replies.py's truncate). An empty file therefore never emits
  (loop-proof); a non-empty file that outlived a session death re-emits on the
  next fresh watcher because nothing persisted said it was seen (loss-proof); a
  second reply appended before the first is ingested changes the content and
  re-emits (read_replies.py's (id, action) dedup absorbs the overlap).

---------------------------------------------------------------------------
WHY POLL, NOT WATCH
---------------------------------------------------------------------------
The game writes on the Windows filesystem (/mnt/c); inotify does NOT bridge a
Windows-side write to a WSL watcher (microsoft/WSL#4739 -- architectural, not a
max_user_watches tunable). `stat` DOES return live Windows metadata on each call
across that boundary, so we poll mtime+size at ~1s and never use inotify on
/mnt/c. Polling works; watching does not.

---------------------------------------------------------------------------
WHY RECONCILE-TO-STATE, NOT CONSUME-ONE-EVENT
---------------------------------------------------------------------------
mtime-polling can miss two writes inside one interval and coalesce a burst into
a single detection. So each poll diffs the CURRENT stat against a persisted
marker and emits the delta to current state; a startup backlog drain compares
the stored marker BEFORE entering the wait (the game may have written while the
watcher was down). Queued / lost / coalesced writes are harmless -- the manager
always reconciles to the latest file, and read_replies.py's own (id, action)
ledger dedup makes the reply side idempotent end to end.

---------------------------------------------------------------------------
WHY DEBOUNCE
---------------------------------------------------------------------------
The game's save is not atomic; a poll can catch a half-written file. A detected
change is only emitted once it is SETTLED -- the same mtime:size across one more
short interval. A still-changing file is left for the next cycle, never
signalled mid-write. (read_replies.py's stable-read is the second line of
defence if a half-written replies.xml ever slips past.)

---------------------------------------------------------------------------
SINGLE INSTANCE
---------------------------------------------------------------------------
Two watchers on one sanctum would double every event and race the marker. A
pidfile (sanctum/watch.pid) holds the live watcher's pid: startup refuses
(ERROR + non-zero exit) if it names a process still alive, and removes it on a
clean exit / SIGTERM. That is what makes the briefing's "clear any stale watcher
first" reliable and the closeout's "verify off" deterministic.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Path resolution and the atomic write are REUSED from the sender/ingest scripts
# rather than reimplemented -- the derived paths must agree with the code that
# actually reads and writes those files (read_replies.py derives replies.xml the
# same way; a second implementation would drift). The stable-read is the same
# torn-write defence read_replies.py itself uses for replies.xml.
from notify_farm_manager import BridgeError, _atomic_write, _find_config
from read_replies import resolve_replies_path
from xml_utils import _read_stable_bytes
# The three exit codes are IMPORTED, never re-declared. This file has to tell
# "still saving" apart from "errored", and a second copy of those numbers is a
# thing to keep in step -- the same reasoning that made the paths above reused
# rather than reimplemented. If refresh_state.py renumbers them, this moves with
# it or fails at import; it cannot silently disagree.
from refresh_state import EXIT_ERROR, EXIT_OK, EXIT_STILL_SAVING

SAVEGAME_FILE = "careerSavegame.xml"   # the file the game rewrites on every save
MARKER_NAME = "watch-marker.json"      # machine file at the sanctum root
PIDFILE_NAME = "watch.pid"
REPLY_ELEMENT_MARK = b"<reply"         # a replies.xml carrying at least one reply

POLL_INTERVAL_DEFAULT = 1.0            # BP-066: 0.5-1s for local checks
DEBOUNCE_SECONDS = 0.3                 # require the savegame stat stable across this gap
PIDFILE_ACQUIRE_ATTEMPTS = 3          # bound the stale-pidfile clear+retry (no busy-loop)

REFRESH_SCRIPT = "refresh_state.py"    # the generator this watcher fires
REFRESH_SUBCOMMAND = "auto"            # no-op when nothing moved; safe to re-fire

# The backoff between re-fires while the save is still being written. The first
# attempt is immediate (delay 0 is not in this table); these are the waits
# BEFORE attempts 2..5, so the sequence reaches ~65 s -- comfortably past
# refresh_state's 20 s quiet window even for a save that starts long and runs
# late. Bounded on purpose: an unbounded retry turns "the save never settled"
# into silence, and silence is the failure this whole file exists to prevent.
REFRESH_RETRY_DELAYS = (5.0, 10.0, 20.0, 30.0)
REFRESH_TIMEOUT_SECONDS = 600.0        # a generator that hangs is a fault, not a wait

# What one finished refresh means for the trigger.
REFRESH_DONE = "done"
REFRESH_RETRY = "retry"
REFRESH_EXHAUSTED = "exhausted"
REFRESH_FAILED = "failed"


# ---------------------------------------------------------------------------
# path resolution
# ---------------------------------------------------------------------------

def _sanctum_dir(config: Optional[str] = None) -> Path:
    """The sanctum root (where config.json lives) -- home for the machine-only
    marker and pidfile, beside read_replies.py's ledger."""
    cfg = Path(config) if config else _find_config()
    if cfg is None or not Path(cfg).is_file():
        raise BridgeError(
            "cannot locate sanctum/config.json; pass --config "
            "(or --marker/--pidfile explicitly)")
    return Path(cfg).parent


def resolve_savegame_path(config: Optional[str] = None,
                          savegame: Optional[str] = None) -> str:
    """careerSavegame.xml of the ONE bound save -- the file the game rewrites on
    every save, and the identity file the skill already binds to (locate_save /
    read_career).

    Resolved from the onboarding-captured save FOLDER in config.json, never a
    hardcoded slot (`savegame1`): onboarding asks the player for the savegame
    directory, so that exact path is already recorded. Prefer top-level
    `savegame_path`, fall back to `paths.savegame_dir` (the config template's
    name for the same save folder).

    NOTE: `paths.game_data_dir` (which notify_farm_manager reads) is the PROFILE
    dir -- the PARENT of the savegame folders -- not a save folder, so it is
    deliberately NOT a fallback here: joining careerSavegame.xml onto it would
    point at a file that does not exist, and globbing the profile for a slot
    would be exactly the slot-guessing this resolver refuses. The two configs
    naming the save folder differently (`savegame_path` vs `paths.savegame_dir`)
    is a pre-existing inconsistency, flagged not fixed."""
    if savegame:
        return savegame
    cfg = _sanctum_dir(config) / "config.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise BridgeError(f"cannot read {cfg} to find the savegame: {e}")
    if not isinstance(data, dict):
        # A config whose top level is a list/scalar would blow up on .get() with
        # an uncaught TypeError -- report it as the clean ERROR it is instead.
        raise BridgeError(f"{cfg} is not a JSON object (got {type(data).__name__})")
    paths = data.get("paths") or {}
    save_dir = data.get("savegame_path") or paths.get("savegame_dir")
    if not save_dir:
        raise BridgeError(
            f"{cfg} has no savegame_path or paths.savegame_dir -- cannot locate "
            "the bound save; pass --savegame /path/to/careerSavegame.xml")
    return str(Path(save_dir) / SAVEGAME_FILE)


# ---------------------------------------------------------------------------
# the pure poll/debounce/reconcile core (no I/O side effects except reading)
# ---------------------------------------------------------------------------

def stat_marker(path: str) -> Optional[str]:
    """'mtime_ns:size' for path, or None if absent/unreadable. `stat` reads live
    Windows metadata on /mnt/c each call -- that is why polling sees the write
    inotify never delivers. Combining mtime AND size catches a same-second
    rewrite that mtime alone (coarse on DrvFs/9p under WSL) would miss."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return f"{st.st_mtime_ns}:{st.st_size}"


def settled_marker(path: str, debounce: Optional[float] = None) -> Optional[str]:
    """The marker for path ONLY if it is unchanged across a debounce interval
    (write-complete). None if the file is absent or still changing -- never
    signal a file mid-write."""
    if debounce is None:
        debounce = DEBOUNCE_SECONDS
    first = stat_marker(path)
    if first is None:
        return None
    time.sleep(debounce)
    second = stat_marker(path)
    return second if second == first else None


def reconcile(targets: dict, marker: dict) -> tuple:
    """Diff every target's current settled stat against the persisted marker.

    targets: {name: path}. marker: {name: 'mtime:size'}. Returns
    (events, new_marker) where events is [(name, marker_value)] for each target
    whose settled current stat differs from what was stored. A target that is
    absent, or still mid-write (not settled), is left untouched: its stored
    marker is preserved and no event fires, so it is re-checked next cycle
    rather than lost or double-counted."""
    events = []
    new_marker = dict(marker)
    for name, path in targets.items():
        cur = stat_marker(path)
        if cur is None:
            # absent/unreadable right now: tolerate. Keep the stored marker so a
            # transient unreadable stat does not re-fire when the file returns.
            continue
        if cur == marker.get(name):
            continue                      # unchanged -- no debounce needed
        s = settled_marker(path)
        if s is None or s != cur:
            continue                      # still changing: leave for next cycle
        if s == marker.get(name):
            continue                      # bounced back to the stored value
        events.append((name, s))
        new_marker[name] = s
    return events, new_marker


# ---------------------------------------------------------------------------
# the replies channel -- content-based, in-memory (never persisted)
# ---------------------------------------------------------------------------

def replies_state(path: str) -> tuple:
    """Classify replies.xml by CONTENT, not mtime -- the reply channel's truth is
    "is there an unprocessed reply on disk", and read_replies.py signals
    "processed" by truncating to the empty root. Returns one of:

        ("empty",     None)   -- absent, 0-byte, or no <reply> children
        ("nonempty",  <fp>)   -- carries a reply; fp = sha1 of the settled bytes
        ("unsettled", None)   -- mid-write / unreadable; try again next cycle

    The stable-read (two byte-identical reads, xml_utils's torn-write defence) is
    the debounce for this channel: a file caught mid-write reads as unsettled and
    is never signalled half-written."""
    if not os.path.isfile(path):
        return ("empty", None)
    data, err = _read_stable_bytes(path)
    if err is not None:
        # _read_stable_bytes errors on a 0-byte file too; a 0-byte replies.xml
        # carries no reply, so it is empty. A changing/unreadable file is
        # genuinely unsettled -- leave it for the next poll.
        try:
            if os.path.getsize(path) == 0:
                return ("empty", None)
        except OSError:
            return ("empty", None)
        return ("unsettled", None)
    if REPLY_ELEMENT_MARK not in data:
        return ("empty", None)
    return ("nonempty", hashlib.sha1(data).hexdigest())


def poll_replies(path: str, last_fp: Optional[str]) -> tuple:
    """Content-based emit decision for the replies channel. Returns
    (emit_value_or_None, new_last_fp). `last_fp` is held IN MEMORY by run() and
    NEVER persisted:

    - empty file      -> reset last_fp to None (empty IS the processed marker);
                         never emit (loop-proof against read_replies' truncate).
    - unsettled       -> leave last_fp untouched; retry next cycle.
    - non-empty, new  -> emit; a fresh watcher starts last_fp=None, so a reply
                         that outlived a session death re-emits (loss-proof).
    - non-empty, same -> no re-emit (no per-poll spam while awaiting ingest)."""
    state, fp = replies_state(path)
    if state == "unsettled":
        return None, last_fp
    if state == "empty":
        return None, None
    if fp != last_fp:
        return fp, fp
    return None, last_fp


# ---------------------------------------------------------------------------
# marker persistence  (savegame channel only)
# ---------------------------------------------------------------------------

def load_marker(path: str) -> dict:
    """The persisted last-processed marker. A missing or corrupt marker is not
    durable truth -- return empty and let the startup backlog drain re-emit
    current state; never fatal (unlike read_replies.py's ledger, this file
    records no player answer, only where the poller left off)."""
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_marker(path: str, marker: dict) -> None:
    _atomic_write(Path(path), json.dumps(marker, indent=2))


# ---------------------------------------------------------------------------
# single-instance pidfile
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                       # exists, just not ours to signal
    return True


def _is_our_watcher(pid: int) -> bool:
    """True only if `pid` is alive AND is actually a wait_for_event watcher.

    A bare liveness check false-positives when the OS recycles a dead watcher's
    pid to an unrelated live process -- which would make arm refuse forever with
    no real watcher running. So confirm the process is ours by reading
    /proc/<pid>/cmdline. If cmdline can't be read, fall back to liveness alone:
    better to refuse a maybe-ours pid than to stomp a real watcher (the manual
    escape hatch is deleting sanctum/watch.pid by hand -- see acquire_pidfile)."""
    if not _pid_alive(pid):
        return False
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read()
    except OSError:
        return True
    # cmdline is NUL-separated args; match the basename as a WHOLE path component
    # so an unrelated arg that merely ends in the string (e.g. a test file named
    # test_..._wait_for_event.py) is not mistaken for the watcher.
    args = cmdline.split(b"\x00")
    return any(a.rsplit(b"/", 1)[-1] == b"wait_for_event.py" for a in args)


def acquire_pidfile(path: str) -> None:
    """Claim single-instance ownership ATOMICALLY.

    The create is one syscall (O_CREAT|O_EXCL) so there is no read->check->write
    TOCTOU window. On a pre-existing pidfile: if it names a LIVE wait_for_event
    watcher, refuse (the deterministic 'already running' guard the briefing's
    stale-clear and the closeout's verify-off rely on); otherwise it is stale (a
    dead pid, or a recycled unrelated pid, or unreadable-and-not-us) -- remove it
    and retry, but BOUNDED: a persistent unlink failure (a DrvFs sharing
    violation on /mnt/c -- the flake read_replies.py itself cites) must fail loud,
    never busy-loop at 100% CPU. Manual escape hatch: delete sanctum/watch.pid by
    hand if you are certain no watcher is running."""
    p = Path(path)
    for _ in range(PIDFILE_ACQUIRE_ATTEMPTS):
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                old = int(p.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                old = None
            if old is not None and old != os.getpid() and _is_our_watcher(old):
                raise BridgeError(
                    f"another watcher is live (pid={old}); stop it first "
                    f"(remove {path} only if you are certain it is stale)")
            # stale: clear and retry. A transient DrvFs flake is absorbed by the
            # bounded retries; a PERSISTENT failure exhausts them and raises below
            # instead of spinning forever.
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return
    raise BridgeError(
        f"could not acquire the watcher pidfile {path} after "
        f"{PIDFILE_ACQUIRE_ATTEMPTS} attempts (a stale pidfile that will not "
        "clear, or a racing writer); remove it by hand if no watcher is running")


def release_pidfile(path: str) -> None:
    """Remove the pidfile, but only if it is still OURS -- never delete a
    successor watcher's claim."""
    p = Path(path)
    try:
        if p.is_file() and int(p.read_text(encoding="utf-8").strip()) == os.getpid():
            p.unlink()
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------------------
# the save -> generator trigger
# ---------------------------------------------------------------------------

def classify_refresh(exit_code, attempt, delays=REFRESH_RETRY_DELAYS):
    """What one finished `refresh_state.py auto` run MEANS. The whole decision
    lives here, as one pure function of (exit code, attempt number), because it
    is the answer this trigger exists to get right.

    `attempt` is 1-based and names the run that just finished. Returns
    (action, delay_seconds); delay_seconds is None for every action but RETRY.

      EXIT_OK           -> DONE       the cache is current; stop asking.
      EXIT_STILL_SAVING -> RETRY      not a fault -- "ask again in a moment" --
                                      until the bounded delays run out, then
                                      EXHAUSTED, which is reported as an ERROR.
      anything else     -> FAILED     never retried. Retrying a real error would
                                      convert a visible fault into a quiet loop,
                                      and exit 1 already means "nothing was
                                      published"; asking again cannot fix it.
    """
    if exit_code == EXIT_OK:
        return REFRESH_DONE, None
    if exit_code == EXIT_STILL_SAVING:
        if attempt <= len(delays):
            return REFRESH_RETRY, delays[attempt - 1]
        return REFRESH_EXHAUSTED, None
    return REFRESH_FAILED, None


def _refresh_summary(stdout, stderr):
    """One short human line describing what the generator reported. Prefers its
    own structured output -- `{"error": ...}` on a failure, `result` otherwise
    (DEC-001: absence is never mistaken for data) -- and falls back to the last
    line of whatever it actually printed, so a run that produced no JSON is
    still described rather than reported as nothing."""
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        if payload.get("error"):
            return str(payload["error"])[:400]
        if payload.get("result"):
            # ⛔ F11(1) / BUG-036: a refresh whose TABS failed must not print
            # as a bare "refreshed" -- name each tab problem on the line.
            problems = payload.get("tab_publish_problems") or []
            if problems:
                return ("%s; %s" % (payload["result"], " | ".join(
                    str(p) for p in problems)))[:1500]
            return str(payload["result"])[:400]
    lines = (stderr or stdout or "").strip().splitlines()
    return lines[-1][:400] if lines else "no output"


def fire_refresh(config_path, scripts_dir=None,
                 timeout=REFRESH_TIMEOUT_SECONDS):
    """Run `refresh_state.py auto --config <config_path>` once.

    Returns (exit_code, summary). An outcome we could not observe -- a timeout,
    a failure to launch -- is EXIT_ERROR, never EXIT_STILL_SAVING: "I do not
    know what happened" must not be retried as if it were "not yet"."""
    if scripts_dir is None:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, os.path.join(scripts_dir, REFRESH_SCRIPT),
           REFRESH_SUBCOMMAND, "--config", config_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return EXIT_ERROR, ("%s %s did not finish within %.0fs"
                            % (REFRESH_SCRIPT, REFRESH_SUBCOMMAND, timeout))
    except OSError as exc:
        return EXIT_ERROR, ("could not run %s: %s" % (REFRESH_SCRIPT, exc))
    return proc.returncode, _refresh_summary(proc.stdout, proc.stderr)


class RefreshTrigger:
    """The save -> generator bridge, as a state machine driven once per poll.

    It holds a due time rather than sleeping, so the retry costs nothing and the
    watcher keeps polling replies.xml throughout: there is no second loop here
    and nothing to spin.

    `fire` and `now` are injectable so the DECISIONS can be tested against real
    exit codes without waiting out a 20 s quiet window in every assertion."""

    def __init__(self, config_path, delays=REFRESH_RETRY_DELAYS,
                 fire=None, now=None):
        self.config_path = config_path
        self.delays = tuple(delays)
        self._fire = fire if fire is not None else fire_refresh
        self._now = now if now is not None else time.time
        self.attempt = 0
        self.due_at = None                 # None => nothing pending

    @property
    def pending(self):
        return self.due_at is not None

    def request(self):
        """A save landed. Start (or restart) the attempt sequence immediately.

        A second save arriving mid-sequence restarts it rather than queueing:
        the generator reconciles to CURRENT state, so the newer save subsumes
        the older one -- the same reconcile-to-state reasoning the savegame
        channel already uses."""
        self.attempt = 0
        self.due_at = self._now()

    def tick(self):
        """Run at most one attempt, if one is due. Returns the lines to print
        (it never prints), so the caller owns emission and a test can assert
        what was CONCLUDED rather than that a call happened."""
        if self.due_at is None or self._now() < self.due_at:
            return []
        self.attempt += 1
        exit_code, summary = self._fire(self.config_path)
        action, delay = classify_refresh(exit_code, self.attempt, self.delays)

        if action == REFRESH_RETRY:
            self.due_at = self._now() + delay
            return ["REFRESH %s exit=%s %s; retrying in %.1fs (attempt %d)"
                    % (REFRESH_SUBCOMMAND, exit_code, summary, delay,
                       self.attempt)]

        self.due_at = None
        if action == REFRESH_DONE:
            return ["REFRESH %s exit=%s %s (attempt %d)"
                    % (REFRESH_SUBCOMMAND, exit_code, summary, self.attempt)]
        if action == REFRESH_EXHAUSTED:
            return ["ERROR %s %s still reported still_saving after %d attempts "
                    "-- STATE WAS NOT REFRESHED. The last word was: %s"
                    % (REFRESH_SCRIPT, REFRESH_SUBCOMMAND, self.attempt,
                       summary)]
        return ["ERROR %s %s exited %s and published nothing: %s"
                % (REFRESH_SCRIPT, REFRESH_SUBCOMMAND, exit_code, summary)]


# ---------------------------------------------------------------------------
# emit + run loop
# ---------------------------------------------------------------------------

def emit_event(name: str, mark: str, note: str = "") -> None:
    """One stdout line = one Monitor event. flush so the Monitor sees it the
    instant it is written, not when a buffer fills."""
    suffix = f" ({note})" if note else ""
    print(f"EVENT {name} {mark}{suffix}", flush=True)


def run(replies_path: str, savegame_path: str, marker_path: str, interval: float,
        once: bool = False, max_cycles: Optional[int] = None,
        refresh: Optional["RefreshTrigger"] = None) -> None:
    """Drain the startup backlog, then poll-debounce-emit-and-REFRESH until
    stopped.

    Two channels, two truths (see the module docstring): the SAVEGAME reconciles
    to a PERSISTED mtime marker; the REPLIES channel keys on content with the
    last-emitted fingerprint held IN MEMORY (`last_replies_fp`), never persisted,
    so a reply survives a session death. `max_cycles` bounds the loop for tests;
    None runs until stopped.

    `refresh` is the RefreshTrigger. A SAVEGAME event requests it; a REPLIES
    event does not -- a player answering a card changes nothing the generator
    reads. It is driven once per cycle whether or not an event fired, because a
    pending retry has to come due on its own."""
    marker = load_marker(marker_path)          # savegame channel only
    last_replies_fp = None                     # replies channel, in memory

    def _poll_and_emit(backlog: bool) -> bool:
        nonlocal marker, last_replies_fp
        note = "startup-backlog" if backlog else ""
        sg_events, new_marker = reconcile({"savegame": savegame_path}, marker)
        for _name, mark in sg_events:
            emit_event("savegame", mark, note=note)
        if sg_events and refresh is not None:
            refresh.request()
        r_emit, last_replies_fp = poll_replies(replies_path, last_replies_fp)
        if r_emit is not None:
            emit_event("replies", f"content:{r_emit[:12]}", note=note)
        if sg_events:
            marker = new_marker
            return True
        return False

    def _drive_refresh() -> None:
        if refresh is None:
            return
        for line in refresh.tick():
            print(line, flush=True)

    # Startup backlog handshake: process anything that changed while the watcher
    # was down BEFORE entering the wait.
    _poll_and_emit(backlog=True)
    save_marker(marker_path, marker)
    _drive_refresh()
    if once:
        # --once is the diagnostic arm: one drain, one attempt, no wait loop. If
        # the save was still settling there is nothing left to re-fire, and a
        # trigger that quietly gave up is exactly the silence this file exists
        # to prevent -- so say it.
        if refresh is not None and refresh.pending:
            print("WARN --once is exiting with a refresh still pending "
                  "(the save had not settled); nothing will retry it. Run "
                  "without --once to let the trigger finish.", flush=True)
        return

    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        time.sleep(interval)
        if _poll_and_emit(backlog=False):
            save_marker(marker_path, marker)
        _drive_refresh()
        cycles += 1


def _install_signal_cleanup(pidfile_path: str) -> None:
    """TaskStop/session-end sends SIGTERM; a clean pidfile removal on that is
    what lets the closeout confirm the watcher is actually gone."""
    def handler(signum, frame):
        release_pidfile(pidfile_path)
        sys.exit(0)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, handler)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Poll the bound savegame + the mod's replies.xml and emit "
                    "one line per settled write, for a persistent Monitor.")
    ap.add_argument("--config", help="path to sanctum/config.json")
    ap.add_argument("--replies", help="path to replies.xml (overrides detection)")
    ap.add_argument("--savegame", help="path to careerSavegame.xml (overrides detection)")
    ap.add_argument("--marker", help="path to the marker file (default: sanctum/watch-marker.json)")
    ap.add_argument("--pidfile", help="path to the pidfile (default: sanctum/watch.pid)")
    ap.add_argument("--interval", type=float, default=POLL_INTERVAL_DEFAULT,
                    help="poll cadence in seconds (default: 1.0)")
    ap.add_argument("--once", action="store_true",
                    help="drain the startup backlog once and exit (no wait loop)")
    ap.add_argument("--no-refresh", action="store_true",
                    help="do NOT run refresh_state.py auto on a save; only "
                         "report the event (the pre-generator behaviour)")
    args = ap.parse_args(argv)

    try:
        replies = resolve_replies_path(config=args.config, replies=args.replies)
        savegame = resolve_savegame_path(config=args.config, savegame=args.savegame)
        marker_path = args.marker or str(_sanctum_dir(args.config) / MARKER_NAME)
        pidfile_path = args.pidfile or str(_sanctum_dir(args.config) / PIDFILE_NAME)
    except BridgeError as e:
        print(f"ERROR {e}", flush=True)
        return 1

    try:
        acquire_pidfile(pidfile_path)
    except BridgeError as e:
        print(f"ERROR {e}", flush=True)
        return 1
    atexit.register(release_pidfile, pidfile_path)
    _install_signal_cleanup(pidfile_path)

    # ARMED ONLY BY AN EXPLICIT --config. `args.config` is what the operator
    # typed; it is deliberately NOT backfilled from _find_config(), whose
    # walk-up can land on a sanctum bound to a farm nobody asked about.
    refresh = None
    if args.no_refresh:
        refresh_mode = "off (--no-refresh)"
    elif args.config:
        refresh = RefreshTrigger(args.config)
        refresh_mode = f"{REFRESH_SUBCOMMAND}:{args.config}"
    else:
        refresh_mode = "off (no --config)"

    print(f"STARTED wait_for_event pid={os.getpid()} interval={args.interval} "
          f"refresh={refresh_mode} "
          f"replies={replies} savegame={savegame}", flush=True)
    if refresh is None and not args.no_refresh:
        # Armed with the trigger off by accident is the ONE state that looks
        # like success and ships the original defect -- saves get reported and
        # nothing regenerates. Say it on its own line; do not leave it to
        # whoever reads the far end of the STARTED line.
        print("WARN refresh trigger OFF: no --config was given, so a save will "
              "be reported and NOTHING will regenerate state. Arm it with "
              "--config <sanctum>/config.json.", flush=True)

    try:
        run(replies, savegame, marker_path, args.interval, once=args.once,
            refresh=refresh)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # A watcher that dies must SAY so -- a silent death is indistinguishable
        # from a quiet game (BP-066: silence is not success).
        print(f"ERROR watcher crashed: {type(e).__name__}: {e}", flush=True)
        return 1
    finally:
        release_pidfile(pidfile_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
