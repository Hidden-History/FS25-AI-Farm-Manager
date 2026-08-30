"""generate_state.py -- write the per-domain cache (plan item 3).

WHAT IT IS. The cache's only writer. It fans out over the domains that emit the
sec. 6.2 envelope, captures each one's output verbatim, writes
`cache/domains/<domain>.json` atomically, rotates the previous generation into
`cache/prev/`, and stamps `CACHE-VERSION`. read_state.py is then the only way to
read any of it back.

WHY IT IS IN SCOPE AT ALL, since the brief could have shipped only the gate:
sec. 2.4's mandated acceptance test invokes this script BY NAME, so the
Done-Condition is unrunnable without it; and read_state.py verifies domain files
against their sources, so with no writer there is nothing to verify and the gate
ships untestable.

SEVEN DOMAINS, AND THE NUMBER THAT DECIDES IT IS 7 OF 16, NOT 7 OF 24. All seven
envelope-emitting parsers are ALREADY registered in collect_state.PARSERS, so
the cache can be generated today without one legacy parser being touched. The
other nine registered domains are skipped -- and skipped LOUDLY, with a named
reason recorded in this run's own output, never silently. A coverage gap that
does not appear in the output is indistinguishable from completeness.

THE SOURCE SET IS THE PARSER'S OWN (Q-1, ruled PARSER-SIDE). Every one of the
seven already declares `provenance.sources[]` and its own `source_set_hash`,
computed where the read actually happens. This orchestrator therefore NEVER
declares a source set: it stores the parser's envelope VERBATIM under "envelope"
and records its own metadata separately under "cache_entry". Two consequences,
both deliberate: the declaration cannot drift from the read, and not one parser
file is edited by this item.

FAILURE ISOLATION -- and the line between two things that look alike:

  * A parser that FAILS (non-zero exit, unparseable output, timeout) is
    ISOLATED. Its domain is written with status "unavailable" AND THE EXIT TEXT
    CARRIED, and the other six are still written. A failed domain must never be
    indistinguishable from a domain that ran and found nothing -- that is DEC-001
    at the orchestration layer.
  * A parser that SUCCEEDS while emitting ZERO SECTIONS is NOT isolated: it
    fails the whole run. sec. 6.3.3 rule 0.5 makes an empty section set a build
    failure, added precisely because a domain emitting nothing was claiming
    "unknown_by_design" vacuously. Recording it as merely "degraded" would let
    the vacuous claim through the exact door rule 0.5 closed.

  ⚠ The distinction is deliberate: a parser that fails is expected and survivable;
  a parser that reports FALSE SUCCESS is not, because everything downstream
  trusts a successful envelope.

Usage: python3 generate_state.py --config <sanctum>/config.json [--only DOMAIN ...]
Exit 0 = cache written. Exit 1 = structured error, and no partial cache is left
claiming to be complete.
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cache_layout as layout
import delta_log
from collect_state import PARSERS

GENERATOR = "generate_state.py"
GENERATOR_VERSION = "1.0.0"

# The domains that emit the sec. 6.2 "sections" envelope. Declared explicitly
# rather than sniffed, and then CHECKED against the registry below: a declared
# domain that is not registered is an error, not a silent skip.
ENVELOPE_DOMAINS = (
    "bales_pallets",
    "farm_ledger",
    # `fields` was registered in collect_state.PARSERS but absent here, so the
    # domain that answers "what needs doing today" never reached the cache at
    # all. read_fields.py now emits the sec. 6.2 envelope, so it belongs here.
    "fields",
    "fleet",
    "livestock",
    "production_defs",
    "productions",
    "weather",
)

# read_production_defs.py walks the install tree and every mod zip; it is the
# slow one by a wide margin. A timeout is a failure like any other and is
# isolated as one, never silently retried.
PARSER_TIMEOUT_SECONDS = 900

# BUG-024. THE ORCHESTRATOR MUST FORWARD THE PATH CONFIG, AND IT MUST NOT
# FORWARD IT TO EVERYONE.
#
# Three envelope parsers need `install_dir`/`mods_dir` -- facts the savegame
# directory cannot supply. Given no `--config` they fall back to resolving
# `sanctum/config.json` RELATIVE TO THE CURRENT WORKING DIRECTORY, so from any
# other cwd `read_production_defs.py` exits 1 and its domain is written
# "unavailable". Measured from /tmp at exactly the argv shape below:
#   {"error": "no --install-dir/--mods-dir given and no config at
#              'sanctum/config.json'. ... Refusing to guess an install location."}
# The parser is RIGHT to refuse; the caller was wrong to make it guess.
#
# ⛔ AND THE OBVIOUS FIX -- forward `--config` to every parser -- IS WRONG, and
# wrong in the direction that makes things worse. BUG-024's own suggested
# direction says "parsers that do not take it already ignore unknown args".
# MEASURED, ALL FIVE, at this argv shape: read_bales_pallets, read_farm_ledger,
# read_fleet, read_livestock and read_productions each exit 1 with
# "unrecognised argument '--config' -- refusing to ignore it". Unconditional
# forwarding therefore turns a ONE-domain failure into a SIX-domain failure.
# Those parsers are also right: silently ignoring an argument you do not
# understand is how a caller's intent gets lost.
#
# So the set is DECLARED here, never sniffed -- and
# tests/test_datalayer_wave3_config_forwarding.py re-measures the declaration
# against what the parsers actually accept, by RUNNING them, so this tuple
# cannot drift from reality in either direction.
CONFIG_AWARE_DOMAINS = (
    "fields",
    "production_defs",
    "weather",
)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def run_parser(scripts_dir, script, savegame_dir, farm_id, config_path=None):
    """Run one parser. Returns (envelope, None) or (None, failure_dict).

    The failure dict carries the parser's own words -- exit code, stderr tail,
    stdout head. A domain that fails must say why in terms a player can act on.

    `config_path` is forwarded as `--config` ONLY when the caller passes it, and
    the caller passes it only for CONFIG_AWARE_DOMAINS (BUG-024). Every other
    parser rejects the flag outright, so "forward it to everyone" is not a
    harmless superset -- see the note on that tuple.
    """
    cmd = [sys.executable, os.path.join(scripts_dir, script), savegame_dir]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    if config_path is not None:
        cmd += ["--config", config_path]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=PARSER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return None, {
            "reason": "parser timed out after %ds" % PARSER_TIMEOUT_SECONDS,
            "cmd": " ".join(cmd[1:]),
        }
    except OSError as exc:
        return None, {"reason": "parser could not be run: %s" % exc, "cmd": " ".join(cmd[1:])}

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, {
            "reason": "parser exited %d and its output is not JSON" % result.returncode,
            "cmd": " ".join(cmd[1:]),
            "exit_code": result.returncode,
            "stderr": result.stderr[-2000:],
            "stdout": result.stdout[:2000],
        }
    if result.returncode != 0:
        return None, {
            "reason": "parser exited %d" % result.returncode,
            "cmd": " ".join(cmd[1:]),
            "exit_code": result.returncode,
            "parser_error": envelope.get("error") if isinstance(envelope, dict) else None,
            "stderr": result.stderr[-2000:],
        }

    # ⛔ A ZERO EXIT IS NOT A SUCCESS SIGNAL ON ITS OWN. Measured in this tree:
    # eleven parsers emit a top-level {"error": ...} AND EXIT 0 -- e.g.
    # `read_environment.py <dir-with-no-environment.xml>` prints
    # {"error": "file not found: .../environment.xml"} and returns 0. Branching
    # on returncode alone therefore reads a stated failure as a valid payload
    # and caches it, or hands it to a caller as data.
    #
    # THOSE PARSERS ARE LATENT TODAY ONLY BECAUSE A HUMAN READS THE OUTPUT, and
    # this architecture removes the human by design -- that is the whole point
    # of it. So the CONSUMER stops trusting the exit code here. ⚠ The eleven
    # producers are NOT touched from here: fixing them is another round's work,
    # and a consumer that defends itself is correct whether or not they are ever
    # fixed. This is "check the artifact, not the exit code" applied in the
    # direction it binds a reader.
    #
    # Only a NON-NULL top-level `error` trips this. The sec. 6.2 envelope has no
    # `error` key at all on success -- all seven envelope parsers emit one only
    # as their hard-failure payload, alongside exit 1 -- so `error: null` and an
    # absent key both stay clean.
    if isinstance(envelope, dict) and envelope.get("error") is not None:
        return None, {
            "reason": "parser exited 0 but its output is an error payload, not "
                      "data. A stated failure must never be cached or read as a "
                      "result because the exit code disagreed with it.",
            "cmd": " ".join(cmd[1:]),
            "exit_code": result.returncode,
            "parser_error": envelope["error"],
            "stderr": result.stderr[-2000:],
        }
    return envelope, None


# The domain whose parser answers "what in-game day is it?". Taken from the
# registry rather than written as a literal, so the script name has exactly one
# source of truth (collect_state.PARSERS) and cannot drift from it here.
DAY_DOMAIN = "environment"


def resolve_game_day(scripts_dir, savegame_dir):
    """Read the in-game day for this run. Returns a resolved-day dict, always.

    ⛔ ONE SUBPROCESS, NO ENVELOPE CONVERSION, NO DERIVATION. `read_environment.py`
    already emits `current_day` and `current_monotonic_day` (:184-185), and
    `run_parser` above validates no envelope -- it runs a script, parses stdout
    and checks the outcome. So the two integers are one call away through
    machinery this script already uses seven times a run. Making `environment`
    an envelope domain is a parser rewrite that buys nothing this needs, and the
    delta log does not read the cache anyway (delta_log.py:4-7).

    ⛔ AND NOTHING IS DERIVED. The owner's ruling, 2026-08-22: the day counter is
    established by the map from savegame start -- absolute and monotonic. There
    is no timescale to apply and no conversion layer to build. An implementer
    who reads "get the in-game day" as "compute the in-game day" builds
    something unnecessary and probably wrong.

    ⚠ A FAILURE HERE IS NEVER FATAL TO THE RUN. The cache is the deliverable and
    seven domains may be perfectly readable while environment.xml is not. So
    this returns the typed-absence form and the run continues with a record that
    states it has no day -- never a record that silently has none.
    """
    script, takes_farm_id, _ = PARSERS[DAY_DOMAIN]
    # `takes_farm_id` is False for this domain -- the day belongs to the save,
    # not to a farm -- but it is read from the registry rather than assumed, so
    # a registry change cannot leave a hardcoded argument shape behind.
    payload, failure = run_parser(
        scripts_dir, script, savegame_dir, None if not takes_farm_id else 0)

    if failure is not None:
        # duty-register.md's axis 2, verbatim: `status: unavailable` plus the
        # reader's own error string, surfaced, never swallowed.
        return delta_log.game_day_unavailable(
            "%s could not supply the in-game day: %s"
            % (script, failure.get("parser_error") or failure.get("reason")))

    if not isinstance(payload, dict):
        return delta_log.game_day_unavailable(
            "%s emitted JSON that is not an object, so it carries no day." % script)

    current = payload.get("current_day")
    monotonic = payload.get("current_monotonic_day")
    if current is None and monotonic is None:
        return delta_log.game_day_unavailable(
            "%s ran and emitted neither current_day nor current_monotonic_day."
            % script)

    return {
        "current_day": current,
        "current_monotonic_day": monotonic,
        # `ok` claims only that the read happened. delta_log downgrades this to
        # `partial` itself if the authoritative counter is the missing one --
        # the decision about which field is authoritative lives there, in one
        # place, and is not re-made here.
        "status": "ok",
        "reason": None,
        "source": script,
    }


# Numeric typings, per the parsers' own `typing` blocks. Anything else in a row
# is descriptive, not a quantity, and a delta log full of names retains nothing
# a rate could ever be built from.
NUMERIC_TYPINGS = ("int", "float")


def extract_measurements(collected):
    """The VALUES each domain reported this run, for later rate work.

    ⛔ THIS INVENTS NO SCHEMA, and refusing to was the design decision. The
    obvious alternative -- copy duty-register.md's output keys in here and map
    each parser onto them -- would plant a SECOND SOURCE OF TRUTH for what a
    domain reports, which is the failure SKILL.md:129-131 names by name:
    "Prose that duplicates runtime state is a second source of truth, and it
    will drift. Ask the script, not the doc."

    So every key comes from the ENVELOPE ITSELF. Each section already declares
    `identity_fields` (which columns name a row) and `typing` (which columns are
    numbers), because sec. 6.2 makes it. This reads those declarations and keeps
    the identity plus the numbers. A parser that gains a quantity is retained
    automatically; a parser that renames one renames it here too, in step,
    because there is only ever the one declaration.

    What is taken verbatim FROM duty-register.md is its CONTRACT, not its column
    names: "Every row's output carries a `status` field", and every row states
    what an empty result means -- so `status`, `reason` and `empty_means` are
    carried through per section, unaltered, and a section that reports nothing
    still appears with the reason it reported nothing.

    ⛔ NOTHING HERE DIVIDES. See delta_log's module docstring: two snapshots are
    a net change, not a rate.
    """
    measurements = {}
    for domain, envelope, failure in collected:
        if envelope is None:
            # duty-register axis 2 again: a reader that could not run is
            # `unavailable` WITH its own words, never an absent domain. An
            # omitted domain would read as "this farm has none of that".
            measurements[domain] = {
                "status": "unavailable",
                "reason": (failure or {}).get("reason", "the parser did not run"),
                "sections": {},
            }
            continue

        sections = envelope.get("sections")
        if not isinstance(sections, dict):
            measurements[domain] = {
                "status": "unavailable",
                "reason": "the parser emitted no 'sections' object to measure",
                "sections": {},
            }
            continue

        per_section = {}
        for name in sorted(sections):
            section = sections[name]
            if not isinstance(section, dict):
                per_section[name] = {
                    "status": "unavailable",
                    "reason": "this section is not an object",
                    "rows": [],
                    "count": 0,
                }
                continue

            typing = section.get("typing")
            typing = typing if isinstance(typing, dict) else {}
            identity = section.get("identity_fields")
            identity = identity if isinstance(identity, list) else []
            data = section.get("data")
            data = data if isinstance(data, list) else []

            # ⚠ `"*"` IS A WILDCARD TYPING, NOT A COLUMN NAMED "*".
            # read_farm_ledger.py:321 declares `typing={"*": "float"}`, meaning
            # EVERY column of that row is a float. Reading it literally stored
            # `{"*": null}` and threw the actual numbers away -- on the 5-day x
            # 33-category finance ledger, the single most rate-relevant block in
            # the save. That is DEC-001 inverted: a fabricated null standing
            # where real data was. Found by running this against the live save,
            # not by reading the code.
            wildcard = typing.get("*")
            if wildcard in NUMERIC_TYPINGS:
                numeric = sorted({k for row in data if isinstance(row, dict)
                                  for k in row} - set(identity))
            else:
                numeric = sorted(k for k, t in typing.items()
                                 if t in NUMERIC_TYPINGS and k != "*")

            # ⛔ A SECTION DECLARING NO NUMBER HAS NO QUANTITY TO RETAIN, and
            # keeping its rows anyway is not caution -- it is 71% of this
            # payload's bytes (measured live: 126,349 of 176,691) spent on rows
            # that cannot contribute to any rate, in the ONE artifact here that
            # is never rotated and cannot be regenerated. `fleet` alone offered
            # 1,507 identity-only rows.
            #
            # ⚠ THE SECTION STILL APPEARS, with its status, its reason, its real
            # row count and an explicit `rows_omitted_reason`. Dropping the rows
            # is not the same as dropping the section, and only the second would
            # be the DEC-001 failure -- a reader can see exactly what was left
            # out and why, and can go to the cache for the rows themselves.
            rows = []
            omitted_reason = None
            if numeric:
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    kept = {k: row.get(k) for k in identity}
                    kept.update({k: row.get(k) for k in numeric})
                    if kept:
                        rows.append(kept)
            elif data:
                omitted_reason = (
                    "this section's envelope declares no int or float column, "
                    "so it reports no quantity this log could retain. Its %d "
                    "row(s) are identity and descriptive fields only and stay "
                    "in the cache rather than being copied into history."
                    % len(data))

            per_section[name] = {
                # Carried through unaltered. A section that says
                # `unknown_by_design` with a reason must still say exactly that
                # here -- restating it in this layer's own words would be the
                # second source of truth again, one layer down.
                "status": section.get("status"),
                "reason": section.get("reason"),
                "empty_means": section.get("empty_means"),
                "identity_fields": identity,
                "measured_fields": numeric,
                # The rows the SECTION reported, never the rows this log chose
                # to keep -- those are `rows_retained`. Collapsing the two would
                # make an omission read as an empty domain.
                "count": len(data),
                "rows_retained": len(rows),
                "rows_omitted_reason": omitted_reason,
                "rows": rows,
            }

        measurements[domain] = {
            "status": envelope.get("status"),
            "reason": envelope.get("reason"),
            "sections": per_section,
        }
    return measurements


# sec. 6.2's two licence kinds, per entry.
GUARANTEE_KINDS = ("schema_cited", "design_ruling")


def validate_interpretation_guarantees(domain, sections):
    """DEC-077 / sec. 6.2.1 -- `interpretation_guarantee` is a LIST.

    ONE FORM, because two accepted shapes is how a consumer ends up handling
    only the one it saw first:

        no ruled reading  -> []            NEVER null
        one               -> [ { ... } ]   NEVER a bare object
        two or more       -> [ {...}, {...} ]

    THREE RULES, added because a list can launder where a single object could
    not. The object shape gave two of them for free by construction.

      1. EVERY ENTRY IS VALIDATED, NOT JUST THE FIRST. A checker that validates
         [0] and stops lets every later entry launder freely -- the one
         genuinely new hole a list opens. The loop below has no early exit and
         MUTATION M77-4 exists to prove it: a structurally invalid entry in
         position [1] must go red.
      2. RULING IDS ARE UNIQUE WITHIN A LIST. Impossible under an object;
         possible AND ambiguous under a list -- which of the two is the licence?
      3. ONE ENTRY PER RULING, never split, never merged. Each entry carries its
         own `kind`, because two rulings under one id cannot be refuted
         separately and refuting either would appear to refute both.

    ⚠ PRESENCE IS NOT REQUIRED HERE, AND THAT IS A DELIBERATE SCOPE LINE.
    sec. 6.2 makes a missing key a build failure -- for the DOMAIN build gate.
    Measured in this tree: ALL SEVEN envelope parsers emit the 13-key rev-4
    shape and ZERO emit this key, so requiring presence would make this
    orchestrator refuse every domain on its first run. That 13-vs-14 drift is
    another item's dispatch (plan sec. 4 item 2); closing it from here by making
    the cache unusable is not this layer's call. So: PRESENT means it must be
    the list form; ABSENT means this layer says nothing.

    ⚠ AND ONE CHECK IS DELIBERATELY NOT MADE: whether a `design_ruling`'s id is
    a ruling THE SPEC DEFINES. That needs the spec's ruling registry, and a copy
    of it here would be a second trust root that drifts from the first -- the
    sec. 11.14 weakness by name. That check belongs to the domain build gate.

    Returns an error string, or None.
    """
    for name in sorted(sections):
        section = sections[name]
        if not isinstance(section, dict) or "interpretation_guarantee" not in section:
            continue
        value = section["interpretation_guarantee"]
        where = "%s.sections.%s.interpretation_guarantee" % (domain, name)

        if value is None:
            return ("%s is null. sec. 6.2.1 forbids null: absence must not be "
                    "how a field is expressed, and [] keeps the field uniformly "
                    "iterable so no consumer branches on type." % where)
        if isinstance(value, dict):
            return ("%s is a bare object. sec. 6.2.1 requires a ONE-ELEMENT "
                    "LIST -- a second shape doing the same job is how a consumer "
                    "ends up handling only the form it saw first." % where)
        if not isinstance(value, list):
            return "%s is %s; sec. 6.2.1 requires a list." % (where, type(value).__name__)

        seen = {}
        for index, entry in enumerate(value):
            # No early exit: rule 1. Every entry, every time.
            if not isinstance(entry, dict):
                return "%s[%d] is not an object." % (where, index)
            kind = entry.get("kind")
            if kind not in GUARANTEE_KINDS:
                return ("%s[%d] has kind %r; sec. 6.2 allows only %s. A decision "
                        "must never be readable as a fact."
                        % (where, index, kind, " or ".join(GUARANTEE_KINDS)))
            ruling = entry.get("ruling")
            if not isinstance(ruling, str) or not ruling.strip():
                return ("%s[%d] names no ruling. A %s licence that names nothing "
                        "licenses nothing." % (where, index, kind))
            if ruling in seen:
                return ("%s names ruling %r twice, at [%d] and [%d]. sec. 6.2.1 "
                        "rule 2: ids are unique within a list, because two "
                        "entries under one id are ambiguous -- which is the "
                        "licence?" % (where, ruling, seen[ruling], index))
            seen[ruling] = index
    return None


def validate_envelope(domain, envelope):
    """sec. 6.3.3 rule 0.5, applied at the orchestration layer. Returns an error
    string, or None when the envelope may be cached."""
    if not isinstance(envelope, dict):
        return "%s emitted JSON that is not an object" % domain
    if "sections" not in envelope:
        return (
            "%s exited 0 but emitted no 'sections' key -- it is registered as an "
            "envelope domain and did not emit an envelope" % domain)
    sections = envelope["sections"]
    if not isinstance(sections, dict):
        return "%s emitted a 'sections' value that is not an object" % domain
    if not sections:
        return (
            "%s exited 0 with ZERO sections. sec. 6.3.3 rule 0.5 makes an empty "
            "section set a build failure: a domain that emits nothing cannot be "
            "cached as though it had reported something." % domain)
    return validate_interpretation_guarantees(domain, sections)


def rotate(domains_dir, prev_dir, domain):
    """Move the prior generation aside before the new one lands. Best-effort by
    design: a missing prior generation is the FIRST run, not an error."""
    current = os.path.join(domains_dir, domain + ".json")
    if not os.path.isfile(current):
        return
    os.makedirs(prev_dir, exist_ok=True)
    shutil.copy2(current, os.path.join(prev_dir, domain + ".json"))


def main():
    argv = sys.argv[1:]
    config_path = None
    only = []
    while argv:
        arg = argv.pop(0)
        if arg == "--config":
            if not argv:
                print(json.dumps({"error": "--config given with no path"}))
                sys.exit(1)
            config_path = argv.pop(0)
        elif arg == "--only":
            if not argv:
                print(json.dumps({"error": "--only given with no domain"}))
                sys.exit(1)
            only.append(argv.pop(0))
        else:
            print(json.dumps({"error": "unexpected argument %r" % arg}))
            sys.exit(1)
    if not config_path:
        print(json.dumps({
            "error": "usage: generate_state.py --config <sanctum>/config.json "
                     "[--only DOMAIN ...]"}))
        sys.exit(1)

    config, err = layout.load_config(config_path)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    farm_id, err = layout.resolve_farm_id(config)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    savegame_dir = (config.get("paths") or {}).get("savegame_dir")
    if not savegame_dir or "{{" in str(savegame_dir):
        print(json.dumps({
            "error": "SAVEGAME DIR NOT SET: config.paths.savegame_dir is %r"
                     % (savegame_dir,)}))
        sys.exit(1)

    # BUG-024. A config-aware domain that is not an envelope domain would be a
    # declaration nothing ever reads -- silent, and exactly how the missing
    # forward went unnoticed for the life of the file. Checked, never assumed.
    stray = [d for d in CONFIG_AWARE_DOMAINS if d not in ENVELOPE_DOMAINS]
    if stray:
        print(json.dumps({
            "error": "CONFIG_AWARE_DOMAINS names %s, which %s not envelope "
                     "domain(s), so the --config forward would never fire for "
                     "them. Fix the declaration."
                     % (", ".join(stray), "is" if len(stray) == 1 else "are")}))
        sys.exit(1)

    # An empty target set must be RED, never a green run over nothing.
    targets = [d for d in ENVELOPE_DOMAINS if not only or d in only]
    unknown = [d for d in only if d not in ENVELOPE_DOMAINS]
    if unknown:
        print(json.dumps({
            "error": "UNKNOWN DOMAIN(S): %s. This layer covers: %s"
                     % (", ".join(unknown), ", ".join(ENVELOPE_DOMAINS))}))
        sys.exit(1)
    if not targets:
        print(json.dumps({
            "error": "NO DOMAINS TO GENERATE: the envelope-domain set is empty, "
                     "so this run would write a cache over nothing."}))
        sys.exit(1)

    missing_from_registry = [d for d in targets if d not in PARSERS]
    if missing_from_registry:
        print(json.dumps({
            "error": "REGISTRY MISMATCH: %s declared as envelope domain(s) but "
                     "absent from collect_state.PARSERS"
                     % ", ".join(missing_from_registry)}))
        sys.exit(1)

    cache_root = layout.resolve_cache_root(config_path, config)
    paths = layout.cache_paths(cache_root)

    sanctum_dir = os.path.dirname(os.path.abspath(config_path))
    history = delta_log.history_paths(sanctum_dir)

    # The delta log lives under the SANCTUM, not the cache, so it needs the same
    # published-promise check -- every path this run may write, without exception.
    escapes = layout.paths_escape_savegame(dict(paths, **history), savegame_dir)
    if escapes:
        print(json.dumps({
            "error": "REFUSING TO WRITE INSIDE THE SAVEGAME FOLDER. The published "
                     "promise is that this manager writes nothing there, not once, "
                     "not ever.",
            "offending_paths": escapes}))
        sys.exit(1)

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    written, failures = [], []

    # ⚠ COLLECT AND VALIDATE EVERYTHING BEFORE WRITING ANYTHING, so a build
    # failure leaves the cache exactly as it found it.
    #
    # This was NOT the first shape. Run-and-write in one pass meant a domain
    # failing validation aborted AFTER its predecessors had already landed --
    # so the run exited 1 while claiming "No cache was written for this run",
    # which was false, and left a cache half from this generation and half from
    # the last one with the previous CACHE-VERSION still valid beside it. The
    # exit code was right and the artifact lied, which is the wrong half to get
    # right. Caught by test_a_null_guarantee_fails_the_whole_run_and_writes_no_cache.
    collected = []
    for domain in targets:
        script, takes_farm_id, _ = PARSERS[domain]
        envelope, failure = run_parser(
            scripts_dir, script, savegame_dir, farm_id if takes_farm_id else None,
            config_path=config_path if domain in CONFIG_AWARE_DOMAINS else None)

        if envelope is not None:
            invalid = validate_envelope(domain, envelope)
            if invalid:
                # NOT isolated. A false success poisons everything downstream.
                print(json.dumps({
                    "error": "BUILD FAILURE: " + invalid,
                    "domain": domain,
                    "note": "No cache was written for this run -- nothing had "
                            "been written when this was found. Fix the parser; "
                            "an invalid envelope must never be cached.",
                }, indent=2))
                sys.exit(1)
        collected.append((domain, envelope, failure))

    # Read the OUTGOING generation's hashes before a byte of it is overwritten.
    # After the write loop they are gone, and the delta log's whole job is to say
    # what changed between the two.
    previous_hashes = {}
    for domain in targets:
        prior = os.path.join(paths["domains"], domain + ".json")
        if not os.path.isfile(prior):
            continue
        try:
            with open(prior, encoding="utf-8") as handle:
                prior_record = json.load(handle)
        except (json.JSONDecodeError, OSError):
            continue   # an unreadable prior generation is a change, not a crash
        prior_hash = ((prior_record.get("envelope") or {})
                      .get("provenance", {}) or {}).get("source_set_hash")
        if prior_hash:
            previous_hashes[domain] = prior_hash

    current_hashes = {}
    for domain, envelope, _failure in collected:
        domain_hash = ((envelope or {}).get("provenance", {}) or {}).get("source_set_hash")
        if domain_hash:
            current_hashes[domain] = domain_hash

    for domain, envelope, failure in collected:
        script = PARSERS[domain][0]
        record = {
            "domain": domain,
            "cache_entry": {
                "generated_at": _now(),
                "generator": GENERATOR,
                "generator_version": GENERATOR_VERSION,
                "cache_schema_version": layout.CACHE_SCHEMA_VERSION,
                "farm_id": farm_id,
                "parser": script,
                "status": "ok" if envelope is not None else "unavailable",
            },
            "envelope": envelope,
        }
        if failure:
            record["cache_entry"]["failure"] = failure
            failures.append({"domain": domain, **failure})

        rotate(paths["domains"], paths["prev"], domain)
        ok, write_err = layout.atomic_write_json(
            os.path.join(paths["domains"], domain + ".json"), record)
        if not ok:
            print(json.dumps({"error": write_err, "domain": domain}, indent=2))
            sys.exit(1)
        written.append(domain)

    ok, write_err = layout.atomic_write(
        paths["version_file"], str(layout.CACHE_SCHEMA_VERSION) + "\n")
    if not ok:
        print(json.dumps({"error": write_err}, indent=2))
        sys.exit(1)

    # One delta entry per run, appended AFTER the cache is complete: a delta
    # describing a generation that failed halfway would be a lie about history,
    # and history is the one thing here that cannot be regenerated.
    #
    # ⭐ THE DAY IS READ HERE, NOT EARLIER, and the ordering is deliberate: it is
    # read as close as possible to the moment it is stamped, so the number in
    # the record is the day the generation actually happened on rather than the
    # day the run started on. A run over the slow parsers can straddle an
    # in-game midnight.
    game_day = resolve_game_day(scripts_dir, savegame_dir)
    measurements = extract_measurements(collected)

    delta, delta_err = delta_log.append(
        sanctum_dir,
        farm_id,
        current_hashes,
        delta_log.diff_domains(previous_hashes, current_hashes),
        GENERATOR,
        game_day=game_day,
        measurements=measurements,
    )
    if delta_err and delta is None:
        print(json.dumps({
            "error": delta_err,
            "note": "The cache was written. The delta log was NOT, so this "
                    "generation is absent from a history that cannot be "
                    "reconstructed -- said plainly rather than exiting 0.",
        }, indent=2))
        sys.exit(1)

    # The nine registered domains this layer does not cover. Named, with the
    # reason, in the run's own output -- a coverage gap that is not rendered is
    # indistinguishable from completeness.
    skipped = [
        {"domain": d,
         "reason": "registered in collect_state.PARSERS but does not emit the "
                   "sec. 6.2 'sections' envelope; bringing the legacy parsers to "
                   "the envelope is a separate, out-of-scope dispatch"}
        for d in PARSERS if d not in ENVELOPE_DOMAINS
    ]

    print(json.dumps({
        "generated_at": _now(),
        "generator": GENERATOR,
        "cache_root": cache_root,
        "farm_id": farm_id,
        "cache_schema_version": layout.CACHE_SCHEMA_VERSION,
        "domains_written": written,
        "domains_written_count": len(written),
        "domains_unavailable": failures,
        "domains_skipped": skipped,
        "domains_skipped_count": len(skipped),
        "delta_log_seq": delta.get("seq"),
        "delta_log_changes": delta.get("changes"),
        "delta_log_warning": delta_err,
        # ⚠ SURFACED IN THIS RUN'S OWN OUTPUT, not only buried in the log. A day
        # that could not be read is a sample that can never carry a rate, and a
        # degradation nobody renders is indistinguishable from success -- the
        # same rule that makes `domains_skipped` appear above.
        "game_day": delta.get("game_day"),
        "game_day_status": delta.get("game_day_status"),
        "game_day_reason": delta.get("game_day_reason"),
        "coverage_note": (
            "This cache covers %d of %d registered domains. It is complete over "
            "those %d and says nothing about the rest."
            % (len(written), len(PARSERS), len(written))),
    }, indent=2))


if __name__ == "__main__":
    main()
