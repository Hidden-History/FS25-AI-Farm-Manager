"""The append-only delta log (plan item 7, spec §§ 8.1-8.3, 8.5).

⚠ THIS IS THE ONE IRREPLACEABLE ARTIFACT IN THE SYSTEM. Everything else the
cache layer writes dies with `rm -rf cache/` BY DESIGN and is regenerated in one
command. The delta log cannot be: it is the record of what CHANGED between
generations, and nothing on disk can reconstruct a history that was not kept.
That is why it lives in `sanctum/history/` rather than in the cache, why it
carries the strictest write discipline here, and why this is the only module in
the layer that opens a file in "a" mode.

NEWEST-LAST, and it is not a style choice. Append-only is the binding
constraint; newest-first would require rewriting the file on every entry, which
is precisely the operation the whole design forbids.

ONE ENTRY PER RUN, not per domain. § 3.3 says the generator appends ONE entry,
and a single chain is what makes "seq contiguous" checkable at all -- seven
interleaved per-domain chains would have to be de-interleaved before anyone
could tell a gap from a domain that simply was not generated. The entry's own
`source_set_hash` is a composite over the run's per-domain hashes, computed with
the SAME formula the domains use (sorted `key\\0hash` lines), so one comparable
scalar answers "did anything at all move since the last generation?" while
`changes[]` says what. ⚠ This is an INTERPRETATION -- § 8.1 states the fields in
the singular and does not say which -- and it is recorded here rather than
absorbed.

GAPS ARE NEVER FILLED, NEVER INTERPOLATED, NEVER SMOOTHED (§ 8.3). A break in
the chain emits an explicit `gap` record saying what is missing and refuses to
guess at it. A rate computed ACROSS a gap is a fabrication, and returning a
number there is the defect this discipline exists to prevent.

THE WATERMARK is what makes a break detectable at all. `delta-log.watermark.json`
carries the line count and the first line's digest; the log itself cannot report
its own truncation, because a truncated file is perfectly well-formed. The
watermark is `retention_class: register` -- NEVER ROTATED. Rotating the thing
that detects loss is how loss stops being detectable.

`farm_id` arrives here ALREADY RESOLVED, by cache_layout.resolve_farm_id(). This
module never reads config and never defaults: it records the int it is handed.

⚠ A LOST WATERMARK IS NOT A PASS. It degrades the check to UNCHECKABLE and says
so. (`UNCHECKABLE` is the post-rename structural word § 8.4 mandates. The word it
replaces is deliberately not written here, so this file adds nothing to that
rename's surface and needs no edit when it lands.)
"""
import hashlib
import json
import os
from datetime import datetime, timezone

LOG_NAME = "delta-log.jsonl"
WATERMARK_NAME = "delta-log.watermark.json"
HISTORY_DIR = "history"

RETENTION_LOG = "history"      # rotated on its own schedule, never truncated
RETENTION_WATERMARK = "register"   # NEVER rotated -- see the module docstring

UNCHECKABLE = "UNCHECKABLE"


def history_paths(sanctum_dir):
    """Every path this item owns, derived from the sanctum."""
    history = os.path.join(sanctum_dir, HISTORY_DIR)
    return {
        "history": history,
        "log": os.path.join(history, LOG_NAME),
        "watermark": os.path.join(history, WATERMARK_NAME),
    }


def composite_hash(per_domain):
    """One comparable scalar over a run's per-domain source-set hashes.

    Same construction as a domain's own source_set_hash -- sorted, and each key
    PAIRED with its own digest, so swapping two domains' hashes changes the
    answer. A concatenation would not.
    """
    lines = sorted("%s\0%s" % (k, v) for k, v in sorted(per_domain.items()))
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def read_log(log_path):
    """Every record, in file order (oldest first). Returns (records, error).

    A line that will not parse is an ERROR, never a skipped line: silently
    dropping one would shorten the history without saying so, which is the same
    defect as a gap nobody recorded.
    """
    if not os.path.isfile(log_path):
        return [], None
    records = []
    with open(log_path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                return None, ("DELTA LOG CORRUPT: %s line %d is not JSON (%s). "
                              "Refusing to read past it -- a history with an "
                              "unreadable line is not a shorter history."
                              % (log_path, number, exc))
    return records, None


def read_watermark(watermark_path):
    """Returns (watermark, None), (None, None) when absent, or (None, error)."""
    if not os.path.isfile(watermark_path):
        return None, None
    try:
        with open(watermark_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        return None, "WATERMARK UNREADABLE: %s (%s)" % (watermark_path, exc)
    if not isinstance(data, dict):
        return None, "WATERMARK UNREADABLE: %s is not an object" % watermark_path
    return data, None


def _first_line_sha256(log_path):
    if not os.path.isfile(log_path):
        return None
    with open(log_path, "rb") as handle:
        first = handle.readline()
    return hashlib.sha256(first).hexdigest() if first else None


def line_count(log_path):
    if not os.path.isfile(log_path):
        return 0
    with open(log_path, encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def detect_break(log_path, watermark):
    """Compare the log against its watermark. Returns (break_reason, detail).

    (None, detail) when the log is intact or there is nothing to compare
    against. The watermark exists because a truncated JSONL file is perfectly
    well-formed and cannot report its own loss.
    """
    observed_lines = line_count(log_path)
    observed_first = _first_line_sha256(log_path)
    detail = {"observed_line_count": observed_lines,
              "observed_first_line_sha256": observed_first}

    if watermark is None:
        detail["watermark"] = UNCHECKABLE
        detail["note"] = (
            "no watermark on disk, so truncation cannot be ruled out. This is "
            "UNCHECKABLE, which is NOT a pass -- it is the absence of a check.")
        return None, detail

    detail["recorded_line_count"] = watermark.get("line_count")
    detail["recorded_first_line_sha256"] = watermark.get("first_line_sha256")

    recorded_lines = watermark.get("line_count")
    if isinstance(recorded_lines, int) and observed_lines < recorded_lines:
        return ("TRUNCATED AT THE TAIL: the watermark recorded %d lines and the "
                "log now holds %d. %d entries are missing and cannot be "
                "reconstructed." % (recorded_lines, observed_lines,
                                    recorded_lines - observed_lines)), detail

    recorded_first = watermark.get("first_line_sha256")
    if recorded_first and observed_first and recorded_first != observed_first:
        return ("TRUNCATED AT THE HEAD: the first line's digest changed, so the "
                "oldest entries were removed. The count alone would not have "
                "caught this."), detail

    return None, detail


def append(sanctum_dir, farm_id, per_domain_hashes, changes, generator):
    """Append one run's delta record. Returns (record, error).

    THE ONLY WRITE PATH, and the only "a"-mode open in this layer. The sequence:

      1. Read the log and its watermark.
      2. If the chain is broken, append an explicit GAP record FIRST. It is not
         a repair -- it is the permanent statement that something is missing.
      3. Append this run's record, chained to its predecessor.
      4. Rewrite the watermark to match what is now on disk.

    ⚠ THE WATERMARK IS WRITTEN LAST, ON PURPOSE. If the process dies between
    steps 3 and 4 the watermark under-counts, which the next run reads as
    "more lines than recorded" -- benign, and it self-corrects. Writing it FIRST
    would over-count, and the next run would report a truncation that never
    happened. Given a choice of which way an interrupted write should be wrong,
    it must be the way that does not manufacture a loss.
    """
    paths = history_paths(sanctum_dir)
    try:
        os.makedirs(paths["history"], exist_ok=True)
    except OSError as exc:
        return None, "DELTA LOG UNWRITABLE: cannot create %s (%s)" % (
            paths["history"], exc.strerror)

    records, err = read_log(paths["log"])
    if err:
        return None, err
    watermark, err = read_watermark(paths["watermark"])
    if err:
        return None, err

    break_reason, break_detail = detect_break(paths["log"], watermark)

    tail = records[-1] if records else None
    next_seq = (tail.get("seq", 0) + 1) if tail else 1

    pending = []
    if break_reason:
        pending.append({
            "kind": "gap",
            "seq": next_seq,
            "prev_seq": tail.get("seq") if tail else None,
            "recorded_at": _now(),
            "farm_id": farm_id,
            "reason": break_reason,
            "detail": break_detail,
            "note": "This gap is permanent and is NEVER filled, interpolated or "
                    "smoothed. Any rate or trend computed ACROSS it is a "
                    "fabrication and must be refused, not estimated.",
        })
        next_seq += 1

    record = {
        "kind": "delta",
        "seq": next_seq,
        "prev_seq": tail.get("seq") if tail else None,
        "recorded_at": _now(),
        "farm_id": farm_id,
        "generator": generator,
        "source_set_hash": composite_hash(per_domain_hashes),
        "prev_source_set_hash": (tail or {}).get("source_set_hash"),
        "domains": dict(sorted(per_domain_hashes.items())),
        "changes": changes,
        "retention_class": RETENTION_LOG,
    }
    pending.append(record)

    try:
        with open(paths["log"], "a", encoding="utf-8") as handle:
            for entry in pending:
                handle.write(json.dumps(entry) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        return None, "DELTA LOG UNWRITABLE: %s (%s)" % (paths["log"], exc.strerror)

    watermark_err = write_watermark(paths)
    if watermark_err:
        return record, watermark_err
    return record, None


def write_watermark(paths):
    """Update the watermark. HIGH-WATER, never a mirror.

    ⚠ `line_count` IS MONOTONICALLY NON-DECREASING (§ 8.4) AND THAT IS THE WHOLE
    MECHANISM. The first version of this function rewrote both fields wholesale
    to match whatever was on disk, which quietly destroyed the tooth it exists
    to serve: flip the writer's "a" to "w" and it truncates the log, then
    immediately records the SHORTER count as the new truth. Tooth 1 caught the
    bad mode; tooth 2 stayed green, because the destructive writer had laundered
    its own truncation. Measured by § 3.8's mandated both-teeth-red proof
    failing on its second half.

    A watermark that can go DOWN is not a watermark, it is a mirror. So the
    count only ever rises, and `first_line_sha256` is recorded ONCE and never
    overwritten -- in an append-only log the first line never legitimately
    changes, so a change there is exactly the head truncation the digest exists
    to catch, and letting it be re-recorded would erase the evidence.

    ⚠ LIMIT, stated rather than discovered: a legitimate ROTATION of the log
    would shorten it and this watermark would then report a permanent loss.
    Rotation is not built in this plan; whoever builds it owns re-anchoring the
    watermark deliberately, which is the correct place for that decision because
    it is the one moment a shrink is known to be intentional.
    """
    existing, _err = read_watermark(paths["watermark"])
    observed_count = line_count(paths["log"])
    observed_first = _first_line_sha256(paths["log"])

    recorded_count = (existing or {}).get("line_count")
    recorded_first = (existing or {}).get("first_line_sha256")

    payload = {
        "line_count": (max(observed_count, recorded_count)
                       if isinstance(recorded_count, int) else observed_count),
        "first_line_sha256": recorded_first or observed_first,
        "observed_line_count_at_last_write": observed_count,
        "updated_at": _now(),
        "retention_class": RETENTION_WATERMARK,
        "note": "NEVER ROTATE THIS FILE, and never lower line_count. It is what "
                "makes truncation of delta-log.jsonl detectable; a truncated "
                "JSONL file is itself perfectly well-formed and cannot report "
                "its own loss.",
    }
    tmp = paths["watermark"] + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, paths["watermark"])
    except OSError as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        return "WATERMARK UNWRITABLE: %s (%s)" % (paths["watermark"], exc.strerror)
    return None


def diff_domains(previous, current):
    """Structured changes between two {domain: source_set_hash} maps.

    Every difference is named with its kind. A domain that vanished is NOT the
    same as one that never existed, and neither is a domain whose hash moved --
    collapsing them would make the log unable to answer what actually happened.
    """
    changes = []
    for domain in sorted(set(previous) | set(current)):
        before, after = previous.get(domain), current.get(domain)
        if before is None:
            changes.append({"domain": domain, "change": "added", "to": after})
        elif after is None:
            changes.append({"domain": domain, "change": "removed", "from": before})
        elif before != after:
            changes.append({"domain": domain, "change": "sources_moved",
                            "from": before, "to": after})
    return changes


def spans_a_gap(records, from_seq, to_seq):
    """True when any gap record sits between two sequence numbers.

    The question a trend consumer must ask BEFORE computing a rate. § 8.3: a
    number returned across a gap is red.
    """
    low, high = min(from_seq, to_seq), max(from_seq, to_seq)
    return any(r.get("kind") == "gap" and low <= r.get("seq", -1) <= high
               for r in records)
