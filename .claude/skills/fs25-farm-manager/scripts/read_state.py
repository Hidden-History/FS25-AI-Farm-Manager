"""read_state.py -- the cache gate (plan item 4).

THE ONE RULE. This is the ONLY way to read the cache, and VERIFICATION IS
INSEPARABLE FROM THE READ. There is no flag that returns farm data without
checking it. Every domain's recorded `source_set_hash` is recomputed from the
files that domain actually declared, on every invocation, before a single figure
is emitted.

IT NEVER SILENTLY REGENERATES. A stale cache is reported, with the remedy
command spelled out, and the caller decides. A gate that quietly refreshed
itself would make "is this current?" unanswerable -- the answer would always be
yes, and it would always be worthless.

THE EXITS.

  exit 0  the verified view. Every domain present, each with its own status,
          reason and provenance.
  exit 1  {"error": "STALE: ..."}            and ZERO farm data.
  exit 1  {"error": "CACHE ABSENT: ..."}     no CACHE-VERSION at all.
  exit 1  {"error": "CACHE EMPTY: ..."}      DEC-073, ruled: a valid CACHE-VERSION
          over an EMPTY domains/ REFUSES RATHER THAN RENDERS.

  ⚠ WHY THE FOURTH EXIT EXISTS, because it is the whole reason this file was
  written before the callers. sec. 6.3.3 rule 0.5 makes an empty SECTION set a
  build failure. The identical hole sits one level up and the spec never closed
  it: a cache with a valid CACHE-VERSION and an empty domains/ is neither absent
  nor stale, so it falls through the three published exits and renders an
  empty-but-exit-0 view -- a clean, successful, blank answer, which is this
  project's top defect class. Precedent is DEC-040: never collapse "no full
  match" into "the docs do not cover this". An empty domains/ must never render
  as "the farm has nothing." Folded in BEFORE build because retrofitting a
  fourth exit after callers depend on three is the expensive path.

  TWO FURTHER REFUSALS, and they are additions to the published contract that
  the owner should see rather than discover:

  exit 1  {"error": "CACHE VERSION MISMATCH: ..."}
  exit 1  {"error": "CACHE FARM MISMATCH: ..."}

  Both are refusals with distinct causes and distinct remedies -- a cache from an
  incompatible layout, and a cache belonging to a DIFFERENT FARM. Each could have
  been folded into "CACHE ABSENT", and that is exactly the collapse DEC-040
  forbids: "regenerate, your format changed", "you are pointed at another farm's
  cache" and "there is no cache" are three different things to tell a player. The
  BEHAVIOUR of all three is identical and non-negotiable -- exit 1, no farm data --
  so only the diagnosis differs.

`--accept-stale` NEVER QUIETLY DEGRADES. It stamps EVERY section -- including the
ones that verified clean -- with status "stale" and a reason, because the
aggregate as a whole is not current and a half-marked view invites exactly the
mistake of trusting the unmarked half.

`--fast` IS AN OPTIMISATION, NEVER A WEAKER ANSWER (sec. 2.3, plan item 5). It
compares `mtime_ns` + `size` and skips hashing only while everything matches;
the moment anything has moved it ESCALATES to the full hash, because a moved
mtime proves only that something moved -- a backup restored with identical bytes
is CURRENT. So the fast path can produce a false CURRENT and never a false
STALE, and `"freshness_check"` records which check was actually performed.

⚠ `"freshness_check"` REPORTS THE WEAKEST CHECK ANY VERIFIED DOMAIN RECEIVED.
`"full"` only when every one of them was re-hashed: a reader asking *is this
fully verified?* must not be told yes because six of seven were. The residual it
exists to make visible is the spec's, carried and NOT resolved here -- a file
whose content changes while `mtime_ns` AND `size` stay byte-identical is
invisible to the fast path (failure mode sec. 11.9, reachability unmeasured).
The mitigation is not cleverness; it is that every run says which check it ran.

`--render-only` AND `--emit-claims` ARE DEBUG AFFORDANCES, AND ONLY THE DUMP IS
EVER OPTIONAL (sec. 9.3). The aggregate and its claims manifest are built and
VALIDATED on every invocation, before a single line is emitted; `--render-only`
changes what is PRINTED and `--emit-claims PATH` additionally writes the
manifest out. Neither can skip the check. An unresolved or mismatched claim
yields `{"error": "CLAIM UNRESOLVED: ..."}` and NO VIEW.

Usage: python3 read_state.py --config <sanctum>/config.json
                             [--accept-stale] [--fast]
                             [--render-only] [--emit-claims PATH]
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aggregate_render
import cache_layout as layout
import cache_provenance as provenance

READER = "read_state.py"
READER_VERSION = "1.0.0"
SUPPORTED_FLAGS = ("--config PATH", "--accept-stale", "--fast",
                   "--render-only", "--emit-claims PATH")


def _fail(message, argv_error=False, **extra):
    """Refuse a run. Every refusal exits 1 with `{"error": ...}` and NO farm
    data (see the module docstring's exit table).

    F-302b: every refusal EXCEPT an argument error also carries
    `coverage_note`, so a caller is told what this response does not cover
    instead of being left to assume -- exactly the moment (a refusal) when the
    caller knows least. The success-path note (:383-385 below) is
    parameterised on `len(sections)`; a refusal has no sections, so this is
    its own wording, not a copy.

    ⚠ ARGUMENT ERRORS ARE EXCLUDED, ON PURPOSE (Parzival, ruled 2026-08-16h).
    Item #13 (tranche 1) carved argument errors out of the delivery-failure
    class specifically so a typo'd flag would not be read as a farm-data
    failure -- a coverage claim on "--config given with no path" would
    re-collapse that distinction. Pass argv_error=True at exactly those call
    sites; every other refusal gets the note by default.
    """
    payload = {"error": message}
    payload.update(extra)
    if not argv_error:
        payload["coverage_note"] = (
            "This is a refusal, not a view: no domain sections are attached, "
            "so nothing here says any of your farm's data is current, stale, "
            "or safe to use. Resolve the error above and rerun read_state.py."
        )
    print(json.dumps(payload, indent=2))
    sys.exit(1)


def _age_of(stamp):
    """Human-readable age of a cache entry. Reported for context only -- it is
    NEVER what decides currency. A save restored from a backup carries an old
    mtime and different content, so only the source hashes can answer that."""
    if not stamp:
        return None
    try:
        then = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    seconds = (datetime.now(timezone.utc) - then).total_seconds()
    if seconds < 90:
        return "%ds" % int(seconds)
    if seconds < 5400:
        return "%dm" % int(seconds // 60)
    return "%.1fh" % (seconds / 3600.0)


def _remedy(config_path):
    return "python3 generate_state.py --config %s" % config_path


def load_domain_records(domains_dir):
    """Every domain file, loaded. Returns (records, error).

    A file that will not parse is an ERROR, not a skipped entry: silently
    dropping it would shrink the farm without saying so.
    """
    records = {}
    for name in sorted(os.listdir(domains_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(domains_dir, name)
        try:
            with open(path, encoding="utf-8") as handle:
                records[name[:-5]] = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            return None, "CACHE CORRUPT: %s could not be read (%s)" % (path, exc)
    return records, None


def verify_domain(record, mode=provenance.FULL):
    """Verify one domain against its own declared sources.

    Returns (status, reason, detail). Statuses: "ok" (verified current),
    "stale", "unavailable" (the parser failed at generation time, so there is
    nothing to verify and nothing to claim).

    `mode` is sec. 2.3's check depth. FULL re-hashes; FAST compares mtime_ns and
    size and escalates to FULL the moment anything has moved.
    """
    entry = record.get("cache_entry") or {}
    if entry.get("status") == "unavailable":
        failure = entry.get("failure") or {}
        return "unavailable", (
            "this domain could not be read when the cache was generated: %s"
            % failure.get("reason", "no reason recorded")), {"failure": failure}

    envelope = record.get("envelope")
    sources, recorded, err = provenance.extract_source_set(envelope)
    if err:
        return "stale", (
            "this domain's provenance cannot be used to verify it: %s" % err), {}

    verdict, reason, detail = provenance.verify_source_set(sources, recorded, mode=mode)
    if verdict == provenance.CURRENT:
        return "ok", None, detail
    return "stale", reason, detail


def main():
    argv = sys.argv[1:]
    config_path = None
    accept_stale = False
    mode = provenance.FULL
    render_only = False
    emit_claims = None
    while argv:
        arg = argv.pop(0)
        if arg == "--config":
            if not argv:
                _fail("--config given with no path", argv_error=True)
            config_path = argv.pop(0)
        elif arg == "--accept-stale":
            accept_stale = True
        elif arg == "--fast":
            mode = provenance.FAST
        elif arg == "--render-only":
            render_only = True
        elif arg == "--emit-claims":
            if not argv:
                _fail("--emit-claims given with no path", argv_error=True)
            emit_claims = argv.pop(0)
        else:
            _fail("unexpected argument %r. Supported: %s"
                  % (arg, ", ".join(SUPPORTED_FLAGS)), argv_error=True)
    if not config_path:
        _fail("usage: read_state.py --config <sanctum>/config.json [--accept-stale]",
              argv_error=True)

    config, err = layout.load_config(config_path)
    if err:
        _fail(err)

    farm_id, err = layout.resolve_farm_id(config)
    if err:
        _fail(err)

    cache_root = layout.resolve_cache_root(config_path, config)
    paths = layout.cache_paths(cache_root)

    # --- exit: CACHE ABSENT --------------------------------------------------
    version, err = layout.read_cache_version(cache_root)
    if err:
        _fail(err if err.startswith("CACHE ABSENT") else "CACHE ABSENT: " + err,
              cache_root=cache_root, remedy=_remedy(config_path))

    # --- exit: CACHE VERSION MISMATCH ---------------------------------------
    if version != layout.CACHE_SCHEMA_VERSION:
        _fail(
            "CACHE VERSION MISMATCH: this cache is format %d and this reader "
            "speaks format %d. The whole cache is invalid -- not partially "
            "usable -- so no farm data is emitted."
            % (version, layout.CACHE_SCHEMA_VERSION),
            cache_root=cache_root, remedy=_remedy(config_path))

    # --- exit: CACHE EMPTY (DEC-073) ----------------------------------------
    if not os.path.isdir(paths["domains"]):
        _fail(
            "CACHE EMPTY: %s is present but there is no domains/ directory -- "
            "0 domain files. Refusing to render: an empty cache is not a farm "
            "with nothing in it." % layout.CACHE_VERSION_FILE,
            cache_root=cache_root, domains_found=0, remedy=_remedy(config_path))

    records, err = load_domain_records(paths["domains"])
    if err:
        _fail(err, cache_root=cache_root, remedy=_remedy(config_path))

    if not records:
        _fail(
            "CACHE EMPTY: %s present, 0 domain files. Refusing to render: a "
            "valid version over an empty domains/ is neither absent nor stale, "
            "and rendering it would answer 'the farm has nothing' to a question "
            "about a cache that was never written."
            % layout.CACHE_VERSION_FILE,
            cache_root=cache_root, domains_found=0, remedy=_remedy(config_path))

    # --- exit: CACHE FARM MISMATCH ------------------------------------------
    # Type-explicit, one direction: config is normalised to int ONCE by
    # resolve_farm_id; an envelope id must already BE an int and is never coerced.
    for domain in sorted(records):
        entry = records[domain].get("cache_entry") or {}
        cached_id = entry.get("farm_id")
        if cached_id is None or isinstance(cached_id, bool) or not isinstance(cached_id, int):
            _fail("CACHE FARM MISMATCH: %s records farm_id %r, which is not an "
                  "integer. sec. 2.1 requires one; not coercing it."
                  % (domain, cached_id),
                  cache_root=cache_root, remedy=_remedy(config_path))
        if cached_id != farm_id:
            _fail(
                "CACHE FARM MISMATCH: config.json resolves to farm %d but %s "
                "was generated for farm %d. This cache belongs to another farm; "
                "rendering it would report that farm's figures as yours."
                % (farm_id, domain, cached_id),
                cache_root=cache_root, config_farm_id=farm_id,
                cached_farm_id=cached_id, domain=domain,
                remedy=_remedy(config_path))

    # --- verify every domain -------------------------------------------------
    sections, stale_domains = {}, []
    for domain in sorted(records):
        status, reason, detail = verify_domain(records[domain], mode=mode)
        entry = records[domain].get("cache_entry") or {}
        sections[domain] = {
            "domain": domain,
            "status": status,
            "reason": reason,
            "provenance": (records[domain].get("envelope") or {}).get("provenance"),
            "cache_entry": entry,
            "verification": detail,
        }
        if status == "stale":
            stale_domains.append(domain)

    # --- exit: STALE ---------------------------------------------------------
    if stale_domains and not accept_stale:
        first = sections[stale_domains[0]]
        detail = first.get("verification") or {}
        _fail(
            "STALE: %d of %d cached domain(s) no longer match the files they "
            "were built from (%s). No farm data is emitted -- a figure from a "
            "stale cache is worse than no figure, because it looks like an answer."
            % (len(stale_domains), len(records), ", ".join(stale_domains)),
            cache_root=cache_root,
            stale_domains=stale_domains,
            recorded_source_set_hash=detail.get("recorded_source_set_hash"),
            observed_source_set_hash=detail.get("observed_source_set_hash"),
            changes=detail.get("changes"),
            cache_age=_age_of((first.get("cache_entry") or {}).get("generated_at")),
            remedy=_remedy(config_path),
            note="This gate never regenerates by itself. Run the remedy above.",
        )

    if accept_stale:
        # NEVER a quiet degrade: every section is stamped, including the ones
        # that verified clean, because the aggregate is not current.
        for domain, section in sections.items():
            was = section["status"]
            section["status"] = "stale"
            section["accepted_stale"] = True
            section["reason"] = (
                "--accept-stale: this view was emitted without a passing currency "
                "check. This domain verified as %r." % was
                + ("" if not section["reason"] else " " + section["reason"]))

    # sec. 2.3 -- ONE value per invocation, and it reports the WEAKEST check any
    # verified domain actually received. "full" only when every one of them was
    # re-hashed: a reader asking "is this fully verified?" must not be told yes
    # because six of seven were. Unavailable domains carry nothing to hash and
    # so cannot weaken it.
    checked = [s["verification"].get("freshness_check")
               for s in sections.values() if s["status"] != "unavailable"]
    freshness_check = (provenance.FAST if provenance.FAST in checked
                       else provenance.FULL)
    escalated = sorted(d for d, s in sections.items()
                       if (s["verification"] or {}).get("escalated_from"))

    degraded = sorted(d for d, s in sections.items() if s["status"] != "ok")
    if not sections:
        _fail("CACHE EMPTY: no sections could be built", cache_root=cache_root)
    top_status = "ok" if not degraded else (
        "stale" if accept_stale else "partial")

    # ------------------------------------------------------------------
    # The aggregate and its claims manifest (item 9). Built in-process, NEVER
    # persisted, and VALIDATED BEFORE A SINGLE LINE IS EMITTED -- a figure
    # validated after printing is a figure that was already believed.
    aggregate, claims, render_err = aggregate_render.render(
        sections, records, config, farm_id, cache_root)
    if render_err:
        _fail(render_err, cache_root=cache_root)

    claim_err = aggregate_render.validate_claims(claims, cache_root)
    if claim_err:
        _fail(claim_err, cache_root=cache_root,
              note="No view was emitted. A rendered figure that does not match "
                   "its own source is the aggregator destroying the evidence "
                   "its components produced (RSK-007).")

    if emit_claims:
        # The DUMP is the optional part; the check above never is (sec. 9.3).
        ok, dump_err = layout.atomic_write(
            emit_claims, json.dumps({"claims": claims}, indent=2) + "\n")
        if not ok:
            _fail(dump_err)

    if render_only:
        print(json.dumps({
            "reader": READER,
            "freshness_check": freshness_check,
            "aggregate": aggregate,
            "claims_validated": len(claims),
        }, indent=2))
        return

    print(json.dumps({
        "reader": READER,
        "reader_version": READER_VERSION,
        "cache_schema_version": version,
        "cache_root": cache_root,
        "farm_id": farm_id,
        "farm_name": config.get("farm_name"),
        "verified_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "status": top_status,
        "accepted_stale": accept_stale,
        "freshness_check": freshness_check,
        "freshness_check_requested": mode,
        "escalated_to_full": escalated,
        "domains_rendered": len(sections),
        "domains_degraded": degraded,
        "coverage_note": (
            "This view covers the %d cached domain(s) and says nothing about any "
            "domain the cache layer does not yet generate." % len(sections)),
        "claims_validated": len(claims),
        "aggregate": aggregate,
        "sections": sections,
    }, indent=2))


if __name__ == "__main__":
    main()
