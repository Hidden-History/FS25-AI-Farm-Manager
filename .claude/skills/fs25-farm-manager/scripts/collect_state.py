"""
Run all parsers against one savegame directory and return a single combined
JSON snapshot. This is the one script the SKILL.md workflow calls at the
start of every session.

Usage: python3 collect_state.py <savegame_dir> [--farm-id N] [--debug]

--farm-id defaults to 1 and is passed to every parser that understands ownership.
Without it, parsers describe the whole MAP rather than the player's FARM: 50 vehicles
instead of 24, map-wide placeables, etc. Ownership is the whole point - see
sanctum/config.json -> known_parser_bugs and FRICTION-LOG.md (F-003).

OUTPUT SIZE (FRICTION-LOG.md F-006): this used to emit 3.87 MB -- almost
entirely each parser's `generic_dump` safety-net field, plus a couple of
genuinely long lists (this save: 1525 price_stats entries, 122 fields).
Piped into context as SKILL.md documents, that ate the window before a
briefing could start. Some of the drop already happened as a side effect of
other fixes (read_economy.py alone went 172KB -> 653B once it stopped
reading the wrong file) but the rest is handled here, generically, so it
doesn't require re-tuning every time a parser's output shape changes:

    - By default, `compact()` below walks every parser's returned JSON and
      (a) blanks out any key literally named "generic_dump" or "all_settings"
          (the known safety-net/reflection fields -- see xml_utils.py's own
          docstring on why they exist) with a short pointer instead of the
          full content, and
      (b) truncates any list longer than MAX_LIST_ITEMS to its first few
          entries + a "N more, rerun with --debug" marker, keeping whatever
          summary counts (field_count, price_stat_count, owned_count, ...)
          the parser already computed untouched -- nothing is silently
          dropped, it's just not inlined by default.
    - `--debug` skips all of that AND passes `--verbose` through to
      read_career.py (the one parser that already has its own verbose gate),
      so a full, unabridged run is always one flag away.

This is deliberately schema-agnostic (no per-parser special-casing beyond
the two known padding-field names) so a parser added later doesn't need this
script edited to stay compact -- see farm_snapshot.py for the actual curated,
human-facing digest; this script's only job is "don't blow the context
window," not "be the briefing."
"""
import os
import sys
import json
import subprocess

SCRIPT_DIR = os.path.dirname(__file__)

# Keys whose *content* is always a safety-net/reflection dump, never load-
# bearing for a briefing, regardless of size. Blanked by default even when
# small, for predictability (a different save could make either one huge).
PADDING_KEYS = {"generic_dump", "all_settings"}

# Lists longer than this get truncated to their first N entries by default.
# Kept small on purpose: collect_state.py's job is "confirm the data's there
# and shaped as expected," not "enumerate it" -- that's farm_snapshot.py's
# job, built from the same parsers without this truncation.
MAX_LIST_ITEMS = 1

# Long prose strings (evidence/investigation notes, not the caveat itself --
# these scripts consistently write the load-bearing warning as the FIRST
# sentence and follow with supporting evidence, see e.g. read_career.py's
# money_note/freshness_note) get capped to their opening by default. Never
# applied to keys that look like error messages -- those must stay whole.
# 130 was chosen empirically: it's enough room for every load-bearing lead
# sentence in this codebase's notes to survive intact (e.g. read_career.py's
# money_note: "This 'money' is careerSavegame.xml's own snapshot, NOT the
# authoritative source -- that's farms.xml (read_economy.py)." is 118 chars)
# while still meaningfully shrinking the multi-paragraph evidence that
# typically follows.
MAX_STRING_CHARS = 110

# Parsers that accept --farm-id. The rest have no ownership concept by nature
# (weather is weather; the sales list is the same for everyone).
# Fourth element: extra args to append only when --debug is set (currently
# just read_career.py's own --verbose gate for its ~400-entry mod list).
PARSERS = {
    "environment": ("read_environment.py", False, []),
    "economy": ("read_economy.py", True, []),
    "fields": ("read_fields.py", True, []),
    "vehicles": ("read_vehicles.py", True, []),
    "missions": ("read_missions.py", False, []),
    "placeables": ("read_placeables.py", True, []),
    "sales": ("read_sales.py", False, []),
    "prices": ("read_prices.py", False, []),
    "career": ("read_career.py", False, ["--verbose"]),
}


def compact(obj, key=None):
    """Recursively blank known padding keys, truncate long lists, and cap
    long prose strings to their opening sentence(s). Never touches summary
    scalars (counts, ids) or error messages -- those are what a caller
    reading the compacted output is meant to trust as complete."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in PADDING_KEYS and v:
                out[k] = {
                    "_omitted": True,
                    "note": f"{k} omitted to keep collect_state.py's output small "
                            "(FRICTION-LOG.md F-006) -- rerun with --debug for the full value.",
                }
            else:
                out[k] = compact(v, key=k)
        return out
    if isinstance(obj, list):
        full = [compact(v) for v in obj]
        if len(obj) > MAX_LIST_ITEMS:
            shown = full[:MAX_LIST_ITEMS] + [
                f"... {len(obj) - MAX_LIST_ITEMS} more item(s) omitted "
                "(rerun with --debug for the full list)"
            ]
            # For short lists of small scalars (e.g. farm_ids_seen: [0, 1,
            # 15]) the marker string can cost more bytes than the data it's
            # replacing -- only truncate when it actually shrinks output.
            if len(json.dumps(shown)) < len(json.dumps(full)):
                return shown
        return full
    if isinstance(obj, str):
        is_error_ish = key is not None and "error" in key.lower()
        if not is_error_ish and len(obj) > MAX_STRING_CHARS:
            return obj[:MAX_STRING_CHARS].rstrip() + (
                f"... [{len(obj) - MAX_STRING_CHARS} more chars truncated, "
                "rerun with --debug for the full note]"
            )
        return obj
    return obj


def run(script, savegame_dir, farm_id=None, extra_args=None):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script), savegame_dir]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    if extra_args:
        cmd += extra_args
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "error": f"failed to parse output of {script}",
            "cmd": " ".join(cmd[1:]),
            "stderr": result.stderr[:2000],
            "stdout": result.stdout[:2000],
        }


def main():
    args = [a for a in sys.argv[1:]]
    farm_id = 1
    if "--farm-id" in args:
        i = args.index("--farm-id")
        try:
            farm_id = int(args[i + 1])
        except (IndexError, ValueError):
            print(json.dumps({"error": "--farm-id requires an integer"}))
            sys.exit(1)
        del args[i:i + 2]

    debug = "--debug" in args
    if debug:
        args.remove("--debug")

    if not args:
        print(json.dumps({"error": "usage: collect_state.py <savegame_dir> [--farm-id N] [--debug]"}))
        sys.exit(1)
    savegame_dir = args[0]

    snapshot = {"savegame_dir": savegame_dir, "farm_id": farm_id}
    for key, (script, takes_farm_id, debug_args) in PARSERS.items():
        raw = run(
            script,
            savegame_dir,
            farm_id if takes_farm_id else None,
            debug_args if debug else None,
        )
        snapshot[key] = raw if debug else compact(raw)

    if not debug:
        snapshot["_debug_note"] = (
            "This output is compacted (FRICTION-LOG.md F-006): generic_dump/"
            "all_settings fields and list entries beyond the first "
            f"{MAX_LIST_ITEMS} are omitted with a note, not silently dropped -- "
            "summary counts (field_count, owned_count, price_stat_count, ...) "
            "are always the real, untruncated totals. Rerun with --debug for "
            "unabridged per-parser output. For a curated, human-facing "
            "briefing digest instead of raw parser output, use farm_snapshot.py."
        )

    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
