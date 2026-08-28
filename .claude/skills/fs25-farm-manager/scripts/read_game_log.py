"""
Parse the FS25 engine log (log.txt) into structured events: errors (including
mod-load failures), warnings (with their source file), the available-mod
inventory, session lifecycle, and a clean-shutdown verdict.

Usage: python3 read_game_log.py <savegame_dir> [--log PATH]
    --log PATH   Explicit path to a log.txt. If omitted, resolved as
                 <parent-of-savegame_dir>/log.txt -- savegame dirs live
                 directly in the FS25 game data root, next to log.txt
                 (verified layout on the real install).

WHY THIS EXISTS (F-121): the log is where the game confesses what the
savegame XML never will -- a mod whose modDesc.xml failed to open, a
duplicate l10n entry, a density-height-type registry overflow. Until now
answering "did any of my mods fail to load?" meant hand-grepping ~6,000
lines. This makes those events structured and honest.

LOG SHAPE (grounded in the real log, read 2026-07-18):
    - A preamble with NO timestamps: engine version/build line first, then
      hardware/driver info. Early load-phase Warning:/Error: lines can also
      appear untimestamped.
    - Then timestamped lines: `YYYY-MM-DD HH:MM:SS.mmm  <message>`.
    - Message spellings observed:
        Error: <text>                          (incl. "Failed to open xml file
                                                '<path>/modDesc.xml'." -- a mod
                                                that did NOT load)
        Warning: <text>
        Warning (<source>): <text>             (source = a file path, or a
                                                category like "performance")
        Available mod: (Hash: <h>) (Version: <v>) <name>
        ... Map loaded: <map>, Savegame name: <name>   (session start)
        quit savegame / Application quit / #End.
      Lifecycle matching is deliberately EXACT (whole-message or the literal
      'Map loaded:' marker) -- a substring match on "savegame" drowned the
      bucket in file-path noise ('.../savegame1/densityMap_fruits.gdm')
      when run against the real log. Unrecognized lifecycle spellings land
      in `other`, counted and sampled, which is the honest failure mode.
    - A run that shut down cleanly ends with `#End.`; a crash/kill leaves the
      log without it. That difference is reported (log_complete), not guessed
      away.

Output contract (toolkit norm):
    - Never a guess. Missing/unreadable/empty log -> {"error": ...} naming the
      tried path; a parsed log with zero errors is a VERIFIED "0 errors", which
      is a different claim entirely.
    - Nothing dropped silently: every line lands in exactly one bucket
      (preamble / errors / warnings / mods_available / lifecycle / other /
      blank), and the buckets' counts sum to the line count. `other` keeps a
      capped sample and an explicit count, and any dedup-list truncation is
      reported with the number dropped -- a cap that doesn't announce itself
      reads as "covered everything" when it didn't.
    - The game appends to log.txt while running: if the file doesn't end in a
      newline, the final line may be mid-write and is reported via
      last_line_partial rather than silently parsed as complete.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import emit

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+(.*)$")
MOD_RE = re.compile(r"^Available mod: \(Hash: ([0-9a-fA-F]+)\) \(Version: ([^)]*)\)\s+(.+)$")
# Lazy to the FIRST '):' in the line. The source -- a file path or a category
# word like 'performance' -- never contains '):': a path's ')' (as in
# '(x86)/') is followed by '/' or '\\', and ':' only follows a drive letter,
# never a ')'. So the FIRST '):' is always the source/message separator. This
# handles BOTH a parenthesized path ('C:/Program Files (x86)/...', which a
# [^)]+ matcher cut short) AND a message body containing '): ' (which a
# greedy .+ matcher swallowed into the source).
WARN_SRC_RE = re.compile(r"^Warning \((.+?)\):\s*(.*)$")
QUOTED_PATH_RE = re.compile(r"'([^']*[/\\][^']*)'")

# Dedup lists are capped so a pathological log can't produce a megabyte of
# JSON -- but never silently: the number of unique entries dropped is
# reported, and occurrence counting keeps running past the cap.
MAX_UNIQUE = 200
MAX_OTHER_SAMPLE = 20


class ToolkitArgumentParser(argparse.ArgumentParser):
    """Failures keep the toolkit's machine contract (structured JSON on
    stdout, exit 1) instead of argparse's usage-to-stderr + exit 2; --help
    stays argparse-native (stdout, exit 0). Same pattern as
    read_farmland_areas.py -- duplicated, not imported, per this toolkit's
    no-cross-script-imports convention."""

    def error(self, message):
        emit({
            "error": f"{message} ({self.format_usage().strip()})",
            "calibration_needed": False,
        })
        sys.exit(1)


def parse_args(argv):
    parser = ToolkitArgumentParser(
        prog="read_game_log.py",
        description="Parse the FS25 log.txt into structured events "
                    "(errors, warnings, mod inventory, lifecycle).",
    )
    parser.add_argument("savegame_dir", help="the savegame directory; log.txt "
                        "is resolved from its parent (the game data root)")
    parser.add_argument("--log", default=None, metavar="PATH",
                        help="explicit path to a log.txt (overrides the "
                             "parent-of-savegame_dir resolution)")
    return parser.parse_args(argv[1:])


def _dedup_add(bucket, key, message, source_file, timestamp):
    """Count an occurrence into an insertion-ordered dedup bucket."""
    entry = bucket.get(key)
    if entry is None:
        bucket[key] = {
            "message": message,
            "source_file": source_file,
            "count": 1,
            "first_timestamp": timestamp,
            "last_timestamp": timestamp,
        }
    else:
        entry["count"] += 1
        if timestamp is not None:
            entry["last_timestamp"] = timestamp
            if entry["first_timestamp"] is None:
                entry["first_timestamp"] = timestamp


def classify(message):
    """Route one (timestamp-stripped) message to its bucket.
    Returns (kind, payload) -- kind in {error, warning, mod, lifecycle, other}."""
    m = MOD_RE.match(message)
    if m:
        return "mod", {"hash": m.group(1), "version": m.group(2), "name": m.group(3).strip()}
    if message.startswith("Error:"):
        text = message[len("Error:"):].strip()
        pm = QUOTED_PATH_RE.search(text)
        return "error", {"message": text, "source_file": pm.group(1) if pm else None}
    m = WARN_SRC_RE.match(message)
    if m:
        return "warning", {"message": m.group(2), "source_file": m.group(1)}
    if message.startswith("Warning:"):
        return "warning", {"message": message[len("Warning:"):].strip(), "source_file": None}
    if message in ("quit savegame", "Application quit", "#End.") or "Map loaded:" in message:
        return "lifecycle", {"message": message}
    return "other", {"message": message}


def _finish_bucket(bucket, occurrences):
    """Materialize a dedup bucket into the output shape, announcing any cap."""
    unique = list(bucket.values())
    dropped = max(0, len(unique) - MAX_UNIQUE)
    return {
        "occurrences": occurrences,
        "unique_count": len(unique),
        "unique": unique[:MAX_UNIQUE],
        "unique_dropped_over_cap": dropped,
    }


def main():
    ns = parse_args(sys.argv)

    if ns.log:
        log_path, resolved_from = ns.log, "--log"
    else:
        log_path = os.path.join(
            os.path.dirname(os.path.abspath(ns.savegame_dir)), "log.txt")
        resolved_from = "parent of savegame_dir"

    if not os.path.isfile(log_path):
        emit({
            "error": f"log file not found: {log_path} (resolved from "
                     f"{resolved_from}). Pass --log with the explicit path.",
            "calibration_needed": False,
        })
        return
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        emit({"error": f"could not read {log_path}: {e}", "calibration_needed": False})
        return
    if not raw:
        emit({
            "error": f"log file is empty (0 bytes): {log_path} -- nothing to "
                     "report, which is NOT the same as 'no errors occurred'.",
            "calibration_needed": False,
        })
        return

    last_line_partial = not raw.endswith("\n")
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    errors = {}
    warnings = {}
    error_occurrences = 0
    warning_occurrences = 0
    mods = {}
    mod_occurrences = 0
    lifecycle = []
    other_count = 0
    other_sample = []
    preamble_count = 0
    blank_count = 0

    engine_runtime = None
    application = None
    first_timestamp = None
    last_timestamp = None
    seen_timestamp = False
    last_message = None

    for line in lines:
        if not line.strip():
            blank_count += 1
            continue
        m = TS_RE.match(line)
        if m:
            timestamp, message = m.group(1), m.group(2)
            seen_timestamp = True
            if first_timestamp is None:
                first_timestamp = timestamp
            last_timestamp = timestamp
        else:
            timestamp, message = None, line.rstrip()

        kind, payload = classify(message)
        if kind == "error":
            error_occurrences += 1
            _dedup_add(errors, (payload["source_file"], payload["message"]),
                       payload["message"], payload["source_file"], timestamp)
        elif kind == "warning":
            warning_occurrences += 1
            _dedup_add(warnings, (payload["source_file"], payload["message"]),
                       payload["message"], payload["source_file"], timestamp)
        elif kind == "mod":
            mod_occurrences += 1
            mods[payload["name"]] = {"name": payload["name"],
                                     "version": payload["version"],
                                     "hash": payload["hash"]}
        elif kind == "lifecycle":
            lifecycle.append({"timestamp": timestamp, "message": message})
        elif timestamp is None and not seen_timestamp:
            # Untimestamped, unclassified, before the first timestamped line:
            # the engine/hardware preamble. Counted, with the two
            # identity-bearing lines captured.
            preamble_count += 1
            if engine_runtime is None:
                engine_runtime = message
            if application is None and message.startswith("Application:"):
                application = message[len("Application:"):].strip()
        else:
            other_count += 1
            if len(other_sample) < MAX_OTHER_SAMPLE:
                other_sample.append({"timestamp": timestamp, "message": message})
        last_message = message

    log_complete = last_message == "#End."

    emit({
        "log_file": log_path,
        "log_resolved_from": resolved_from,
        "line_count": len(lines),
        "log_complete": log_complete,
        "log_complete_note": (
            "the log's final line is '#End.' -- the engine shut down cleanly."
            if log_complete else
            "the log does NOT end with '#End.' -- the session crashed, was "
            "killed, or is STILL RUNNING. Treat the tail as possibly mid-write."
        ),
        "last_line_partial": last_line_partial,
        "engine": {"runtime": engine_runtime, "application": application},
        "timespan": {"first_timestamp": first_timestamp, "last_timestamp": last_timestamp},
        "errors": _finish_bucket(errors, error_occurrences),
        "warnings": _finish_bucket(warnings, warning_occurrences),
        "mods_available": {
            "unique_count": len(mods),
            "occurrences": mod_occurrences,
            "mods": list(mods.values()),
        },
        "lifecycle": {"count": len(lifecycle), "events": lifecycle},
        "other": {
            "count": other_count,
            "sample": other_sample,
            "note": "timestamped lines matching no known event shape -- counted "
                    "and sampled, never silently dropped.",
        },
        "preamble_line_count": preamble_count,
        "blank_line_count": blank_count,
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
