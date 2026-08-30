"""Provenance and source-set hashing for the cache layer (plan item 1).

WHAT DECIDES CURRENCY. Not `generated_at` -- a save restored from a backup
carries an OLD mtime and DIFFERENT content, so a timestamp comparison would call
it fresh. The `source_set_hash` decides, because it is computed from what the
files actually contain.

A DOMAIN HASHES ONLY THE FILES IT READS (sec. 2.1), never the 133 MB savegame.
Freshness is then honestly relative to a domain's OWN sources: weather going
stale must not invalidate the ledger.

⚠ THIS MODULE IS AN EXTRACTION, NOT AN INVENTION -- and that is the whole reason
it can be trusted. Measured in this tree: all SEVEN envelope-emitting parsers
already compute this hash, and they agree exactly --

    "sha256:" + sha256("\\n".join(sorted("<path>\\0<sha256>" for each source)))

Six define `source_set_hash()`; read_farm_ledger.py inlines the identical
formula in `build_provenance()` (:261-262); read_production_defs.py hashes one
record per ROOT rather than per file, deliberately and documented, but uses the
same set formula over those records. `file_provenance()` agrees six ways too --
read_farm_ledger.py reads in 1 MB chunks rather than whole-file, which changes
the memory profile and not one byte of the digest.

So this module does NOT re-decide the formula. It is the single implementation
the cache layer reads through, and tests/test_item1_cache_provenance.py holds it
to PARITY with all seven shipped copies. If a parser's formula ever drifts from
this one, that parity test goes red -- which is the point, because the gate
compares a hash THIS module recomputes against a hash A PARSER recorded, and if
those two formulas disagree the gate reports every cache as stale forever.

⚠ NO PARSER IS EDITED BY THIS ITEM. Q-1 was ruled PARSER-SIDE: the source-set
declaration stays where the read happens, so it cannot drift from the truth.
Every parser already declares its own `provenance.sources[]`, so the ruling is
satisfied by the shipped envelope and the orchestrator never declares a source
set of its own -- it consumes the parser's. That also keeps this item's hands off
the seven files another lane is editing.

WHY THE `path\\0sha256` PAIRING IS THE FORMULA. Concatenating all the paths and
then all the hashes would let two sources SWAP their digests without changing
the set hash -- a cache that reports itself current while every domain's data
belongs to the other file. Pairing each path WITH its own digest before sorting
makes that swap change the answer. The mutation set exercises exactly that.

`farm_id` arrives here ALREADY RESOLVED, by cache_layout.resolve_farm_id(). This
module never reads config and never defaults: it takes the int it is handed.
"""
import hashlib
import os

# Verdicts, in the temporal vocabulary sec. 2.2 assigns to the cache gate.
# CURRENT is deliberately NOT called "fresh": "fresh" belongs to the structural
# health vocabulary, which a separate, still-open item renames. Keeping the two
# apart here costs nothing and keeps this file off that item's surface entirely.
CURRENT = "current"
STALE = "stale"

# sec. 2.3 -- what check an invocation ACTUALLY performed. Recorded in the run's
# own output, never inferred by the caller.
#
# ⚠ THIS IS THE FIELD'S WHOLE JOB. The fast path carries a residual the spec
# names and this plan does NOT resolve: a file whose content changes while its
# mtime_ns AND size stay byte-identical is invisible to it (failure mode
# sec. 11.9; a backup restored mid-session is the plausible route, and its
# reachability is unmeasured). The mitigation is not cleverness -- it is that
# every run SAYS which check it ran, so a reader can tell a full verification
# from a cheap one instead of assuming.
FULL = "full"
FAST = "fast"

# Vocabulary note: "freshness_check" is sec. 2.3's mandated field name, and
# CURRENT/STALE here are the cache-TEMPORAL words. They are NOT the
# sanctum-structural health vocabulary, which a separate, still-open item
# renames -- and that item's three words are deliberately not written anywhere
# in this file, so nothing here lands on its rename surface. (Naming them "just
# to be clear" is exactly what this comment originally did, and the suite's own
# guard caught it.)

READ_CHUNK = 1024 * 1024


def file_provenance(path):
    """One sec. 2.1 source record: {path, mtime_ns, size, sha256}.

    Opened "rb" -- a read mode, never a write. Chunked, following
    read_farm_ledger.py: a savegame file is not guaranteed small, and the digest
    is identical either way.
    """
    stat = os.stat(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK), b""):
            digest.update(chunk)
    return {
        "path": path,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": digest.hexdigest(),
    }


def source_set_hash(sources):
    """sec. 2.1: sha256 over the sorted `path\\0sha256` lines, one comparable
    scalar per domain. SORTED, so reordering sources[] is not a change; PAIRED,
    so swapping two files' digests is."""
    lines = sorted("%s\0%s" % (s["path"], s["sha256"]) for s in sources)
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def extract_source_set(envelope):
    """Pull (sources, recorded_set_hash) out of a parser envelope.

    Returns (sources, set_hash, None) or (None, None, error_string).

    ABSENCE FAILS. A domain with no `provenance`, no `sources[]`, an EMPTY
    sources list, or no recorded `source_set_hash` is an error -- never an empty
    list quietly treated as "nothing to verify", which would make the gate pass
    by verifying nothing. That is DEC-001 at the verification layer and it is the
    single most likely way this gate could be made toothless without anyone
    noticing.
    """
    if not isinstance(envelope, dict):
        return None, None, "envelope is not a JSON object"
    prov = envelope.get("provenance")
    if not isinstance(prov, dict):
        return None, None, "envelope carries no provenance object"
    sources = prov.get("sources")
    if not isinstance(sources, list):
        return None, None, "provenance.sources is missing or not a list"
    if not sources:
        return None, None, (
            "provenance.sources is EMPTY -- a domain that declares no sources "
            "cannot be verified against anything, and treating that as current "
            "would make the gate pass over nothing")
    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            return None, None, "provenance.sources[%d] is not an object" % i
        for key in ("path", "sha256"):
            if not src.get(key):
                return None, None, "provenance.sources[%d] has no %r" % (i, key)
    recorded = prov.get("source_set_hash")
    if not recorded:
        return None, None, "provenance carries no source_set_hash"
    return sources, recorded, None


def _cheap_stat(path):
    """(mtime_ns, size) without reading a byte of content."""
    stat = os.stat(path)
    return stat.st_mtime_ns, stat.st_size


def _directory_provenance(path, kind):
    """Recompute a directory-rooted source record (F-301).

    read_production_defs.py records ONE source per ROOT -- the install tree,
    the mod zips -- via its own root_provenance() over its own
    collect_install_files()/collect_mod_files(). Those are the ONLY collectors
    used here, reused rather than reimplemented: a naive re-hash of the
    directory (every file, no filter) would apply a different filter than the
    parser used to build the recorded digest and would never agree with it --
    reporting the gate STALE forever instead of fixing it. Nothing else in the
    fleet emits a directory-rooted source, so `kind` is always "install" or
    "mods" in practice; an unrecognized kind fails loud rather than guessing.
    """
    import read_production_defs as rpd
    if kind == "install":
        files = rpd.collect_install_files(path)
    elif kind == "mods":
        files = rpd.collect_mod_files(path)
    else:
        raise ValueError("unrecognized directory source kind: %r" % (kind,))
    return rpd.root_provenance(kind, path, files)


def fast_scan(sources):
    """sec. 2.3's cheap check: mtime_ns + size only, no hashing.

    Returns (looks_unchanged, notes). `looks_unchanged` is True only when EVERY
    source still carries the recorded mtime_ns and size.

    ⚠ THE ASYMMETRY IS THE WHOLE DESIGN, and it is what makes this safe to use
    at all. A mismatch here proves only that something MOVED -- not that content
    changed, because a backup restored with identical bytes carries a new mtime.
    So a mismatch never decides anything: it escalates to the full hash, which
    is definitive. That means the fast path can produce a FALSE CURRENT (the
    sec. 11.9 residual) but never a FALSE STALE. A cheap check that could
    wrongly condemn a good cache would be worse than no cheap check.

    ⚠ DIRECTORY SOURCES (F-301) ALWAYS ESCALATE. root_provenance() records no
    mtime_ns/size for a directory-rooted source (see module docstring), so
    there is nothing cheap to compare -- comparing the directory's own stat
    against a recorded `None` would be a meaningless mismatch dressed up as a
    real one. Say so honestly and let the full recompute settle it.
    """
    notes = []
    for src in sources:
        path = src["path"]
        if os.path.isdir(path):
            notes.append({
                "path": path,
                "change": "directory source: no cheap check recorded, "
                          "escalating to full",
            })
            continue
        try:
            mtime_ns, size = _cheap_stat(path)
        except OSError as exc:
            notes.append({"path": path,
                          "change": "source unreadable: %s" % (exc.strerror or exc)})
            continue
        if src.get("mtime_ns") != mtime_ns or src.get("size") != size:
            notes.append({
                "path": path,
                "change": "mtime or size moved",
                "recorded_mtime_ns": src.get("mtime_ns"), "observed_mtime_ns": mtime_ns,
                "recorded_size": src.get("size"), "observed_size": size,
            })
    return (not notes), notes


def verify_source_set(sources, recorded_set_hash, mode=FULL):
    """Re-read every declared source and decide CURRENT vs STALE.

    `mode=FAST` (sec. 2.3) checks mtime_ns + size only and SKIPS hashing while
    everything matches; ANY mismatch escalates to the full hash, and the returned
    detail then reports `freshness_check: "full"` with `escalated_from: "fast"`,
    because what is reported must be the check that was actually performed.

    Returns (verdict, reason, detail). `detail` carries both triples and the
    per-source comparison, because sec. 2.2 requires a stale report to name the
    mismatch, both hashes and the remedy rather than just saying "stale".

    ⚠ A SOURCE THAT CANNOT BE READ IS STALE, NOT AN ERROR, AND THE REASON SAYS
    WHY. Deleting a file a domain hashed genuinely changes that domain's source
    set, so "stale" is the honest answer rather than a collapse -- but "gone",
    "unreadable" and "edited" are different facts with different remedies, so the
    reason distinguishes them even though the verdict does not. Never report a
    cache as current because a source vanished.
    """
    escalated = False
    if mode == FAST:
        looks_unchanged, _cheap_notes = fast_scan(sources)
        if looks_unchanged:
            return CURRENT, None, {
                "freshness_check": FAST,
                "recorded_source_set_hash": recorded_set_hash,
                "observed_source_set_hash": None,
                "sources_checked": len(sources),
                "note": "mtime_ns and size only -- no content was hashed. A "
                        "change that preserved BOTH would be invisible here "
                        "(failure mode sec. 11.9); that is why this field says "
                        "which check ran.",
            }
        escalated = True   # something moved; only the full hash can settle it

    observed, notes = [], []
    for src in sources:
        path = src["path"]
        if os.path.isdir(path):
            try:
                current = _directory_provenance(path, src.get("kind"))
            except (OSError, ValueError, ImportError) as exc:
                # ImportError: the lazy `import read_production_defs` inside
                # _directory_provenance is new code this item added, so it is
                # a new failure mode -- caught here rather than left to crash
                # the caller with a bare traceback (DEC-001).
                change = ("could not import read_production_defs.py: %s" % exc
                          if isinstance(exc, ImportError) else
                          "source unreadable: %s" % exc)
                notes.append({"path": path, "change": change})
                observed.append({"path": path, "sha256": "<unreadable>"})
                continue
            observed.append({"path": path, "sha256": current["sha256"]})
            if current["sha256"] != src["sha256"]:
                notes.append({
                    "path": path,
                    "change": "content changed",
                    "recorded_sha256": src["sha256"],
                    "observed_sha256": current["sha256"],
                    "recorded_file_count": src.get("file_count"),
                    "observed_file_count": current["file_count"],
                })
            continue
        try:
            current = file_provenance(path)
        except FileNotFoundError:
            notes.append({"path": path, "change": "source no longer exists"})
            observed.append({"path": path, "sha256": "<missing>"})
            continue
        except OSError as exc:
            notes.append({"path": path, "change": "source unreadable: %s" % exc.strerror})
            observed.append({"path": path, "sha256": "<unreadable>"})
            continue
        observed.append({"path": path, "sha256": current["sha256"]})
        if current["sha256"] != src["sha256"]:
            notes.append({
                "path": path,
                "change": "content changed",
                "recorded_sha256": src["sha256"],
                "observed_sha256": current["sha256"],
                "recorded_size": src.get("size"),
                "observed_size": current["size"],
            })

    observed_hash = source_set_hash(observed)
    performed = {"freshness_check": FULL}
    if escalated:
        performed["escalated_from"] = FAST
    if observed_hash == recorded_set_hash and not notes:
        performed.update({
            "recorded_source_set_hash": recorded_set_hash,
            "observed_source_set_hash": observed_hash,
            "sources_checked": len(sources),
        })
        return CURRENT, None, performed
    performed.update({
        "recorded_source_set_hash": recorded_set_hash,
        "observed_source_set_hash": observed_hash,
        "sources_checked": len(sources),
        "changes": notes,
    })
    return STALE, (
        "%d of %d source file(s) no longer match what this domain hashed"
        % (len(notes) or 1, len(sources))
    ), performed
