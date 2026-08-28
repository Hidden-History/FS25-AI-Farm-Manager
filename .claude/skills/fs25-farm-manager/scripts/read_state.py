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
import math
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

# ⛔ WAVE 3C REMEDIATION (M1). `verify_domain`'s detail says, on every path,
# whether this run actually COMPARED the domain against its recorded sources.
# "stale" is returned for six distinct conditions and only some of them are a
# comparison; a sentence that says "no longer match the files they were built
# from" is FALSE about the others. This is the fact that keeps that sentence
# honest, and it is carried BY the verdict -- never inferred from whether some
# neighbouring field happens to be populated.
PERFORMED = "performed"
NOT_PERFORMED = "not_performed"


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

    ⛔ WAVE 3C REMEDIATION (H1 + M1). EVERY RETURN PATH NOW STATES WHETHER A
    COMPARISON WAS ACTUALLY PERFORMED, as a fact carried BY the verdict rather
    than inferred from a neighbouring field. Two callers need it and neither can
    re-derive it honestly:

      * H1 -- `detail["freshness_check"]` already said whether bytes were hashed
        ("full") or only mtime_ns and size compared ("fast"). The layer above
        DISCARDED it and rendered both as `verified_current`, so `--fast`
        published a full-verification word about content it never read.
      * M1 -- "stale" is this function's answer for SIX distinct conditions,
        only some of which involve a comparison at all. A domain whose
        provenance could not be READ is not a domain whose files were compared
        and found to differ. Prose that says otherwise asserts a fact this
        function never established. `comparison` is what tells the two apart.

    ⚠ The verdict SET IS UNCHANGED -- still exactly "ok", "stale",
    "unavailable". A fourth verdict is deferred (L-class); this adds a fact to
    the detail, not a rung to the ladder, so the STALE gate in `main()` and
    everything downstream of it behave exactly as before.
    """
    entry = record.get("cache_entry") or {}
    if entry.get("status") == "unavailable":
        failure = entry.get("failure") or {}
        return "unavailable", (
            "this domain could not be read when the cache was generated: %s"
            % failure.get("reason", "no reason recorded")), {
                "failure": failure, "comparison": NOT_PERFORMED}

    envelope = record.get("envelope")
    sources, recorded, err = provenance.extract_source_set(envelope)
    if err:
        return "stale", (
            "this domain's provenance cannot be used to verify it: %s" % err), {
                "comparison": NOT_PERFORMED}

    verdict, reason, detail = provenance.verify_source_set(sources, recorded, mode=mode)
    detail = dict(detail, comparison=PERFORMED)
    if verdict == provenance.CURRENT:
        return "ok", None, detail
    return "stale", reason, detail



# ---------------------------------------------------------------------------
# ITEM ③a-EXTENDED + ③b + BUG-026 -- the production input-demand join.
#
# WHY IT LIVES IN THE GATE. `production_recipes` (what a line burns per cycle)
# and `storage_fill_levels` (what the line is holding) are produced by two
# different parsers reading two different worlds -- the mod/install tree and the
# savegame. Neither can see the other, and both say so in their own `reason`
# fields: "the join belongs to whatever consumes both." This module is the only
# thing in the tree that holds both, and it refuses to emit anything at all
# against a stale cache -- so a figure derived here is derived from data whose
# currency was proved seconds earlier.
#
# ⛔ IT IS NOT IN aggregate_render.py AND THAT IS DELIBERATE. Every figure that
# module emits is a CLAIM carrying a source file and a json_path, re-resolved
# against disk before a line is printed. A DERIVED number has no json_path. Put
# one there and the claims manifest starts carrying figures it cannot check,
# which is precisely the mechanism that file exists to guarantee.
#
# ⛔ BUG-026 -- WHAT THIS REFUSES TO DO. A `production_id` DOES NOT IDENTIFY ONE
# RECIPE. Measured on the owner's live cache: 289 distinct ids over 752 rows,
# 184 of them carrying more than one definition, 71 disagreeing on
# `cycles_per_hour`. `clothes` carries FOUR definitions at 150/100/10/100 cycles
# per hour -- so its FABRIC burn is one of {600, 400, 40} L/h and its
# hours-to-empty anywhere across a 15x spread. A consumer that takes the first
# match produces a COMPLETE, PLAUSIBLE, CORRECTLY-ORDERED table in which some
# rows are wrong by 100x, and nothing about it looks wrong.
#
#   So: when the surviving definitions disagree ON THE ANSWER, this emits
#   `rate_status: "ambiguous"`, a NULL rate, and the candidate count -- never a
#   number. When they agree, the number is emitted and the candidate count is
#   still carried, so a reader can always see how many definitions stood behind
#   it. Agreement is judged on the COMPUTED per-hour burn, not on the recipe
#   text: two definitions that differ in wording but produce the same number are
#   not an ambiguity, and calling them one would bury real answers in noise.
#
# ⛔ AND IT KEYS ON THE FULL `source_path`, NEVER THE BASENAME. `clothes`'s four
# definitions live at four distinct paths, and TWO OF THEM ARE BOTH NAMED
# `tailorShop.xml` -- one under productionPointsGeneric (100/h), one under
# productionPointsSmall (10/h). Collapsing them by basename is a silent 10x
# error. `read_production_defs.py:696` already declares the section's identity
# as ["source_path", "production_id"]; this honours that declaration rather than
# re-deriving a weaker one.
#
# ⛔ PLACEABLE-LEVEL RESOLUTION IS NOT ATTEMPTED, AND THAT IS A MEASUREMENT, NOT
# A SHRUG. `placeables.xml` carries `filename=` on 37 of 44 production-bearing
# placeables (24 of the owner's 27 on farm 1) -- so the route BUG-026 calls "the
# likely route, NOT measured" is REAL BUT PARTIAL, and would need a $moddir$
# path mapping this layer has no verified way to perform. Building a tiebreak on
# top of that would be inventing one (DEC-080). Ambiguity is reported instead.
#
# ⛔ ③b -- A PASS-THROUGH FILL TYPE IS NOT CONSUMED, AND IT IS NOT DELETED
# EITHER. A fill type that is both an input and an output of the same recipe
# passes through the building; counting it as demand reads as a permanent
# shortage. It is EXCLUDED FROM DEMAND AND STILL EMITTED, carrying its reason.
# ⚠ The trap, live on this farm: `soupCansPotato` lists its own production_id as
# an input fill type. Three genuine cases here.
#
# ⭐ ORDER IS LOAD-BEARING: pass-through exclusion runs BEFORE the stock-absence
# report. Measured -- 11 input-lines have no stock row, one of which
# (`soupCansPotato`) is also a pass-through. Report absence first and you tell
# the player about an input the building never consumes.
#
# ⛔ AN INPUT WITH NO STOCK ROW IS REPORTED, NEVER DROPPED. Ten of the owner's
# input-lines have no `storage_fill_levels` row at all. A dropped line renders a
# production the manager CANNOT SEE as a production with nothing wrong -- DEC-001
# exactly, absence rendered as data.
# ---------------------------------------------------------------------------

DEMAND_SECTION = "production_input_demand"
HOURS_PER_DAY = 24


def _number(value):
    """Coerce a cache scalar to float. Returns (value, None) or (None, reason).

    `cycles_per_hour` and input `amount` are emitted by read_production_defs.py
    as RAW UNCOERCED STRINGS ("160"). Coercing silently to 0.0 on a bad value
    would turn an unreadable recipe into an infinite runway.
    """
    if value is None:
        return None, "absent"
    if isinstance(value, bool):
        return None, "not a number: %r" % (value,)
    if isinstance(value, (int, float)):
        coerced = float(value)
    else:
        try:
            coerced = float(str(value).strip())
        except (TypeError, ValueError):
            return None, "not a number: %r" % (value,)
    # ⛔ FINDING 5 (wave 3b). float() ACCEPTS "nan", "inf" and "-inf" without
    # raising, so only ValueError being caught let all three through as a
    # `rate_status: "resolved"` number. Neither is a JSON number: a strict
    # reader rejects the whole document and `jq` rewrites NaN to **null**,
    # turning a computed burn rate into absence-as-data (DEC-001) in the one
    # section built to make absence impossible to mistake for data. This is
    # the identical guard build_finance_ledger already carries for money
    # (read_farm_ledger.py, "Finding H4"); the two arrived by the same route.
    if not math.isfinite(coerced):
        return None, "not a finite number: %r" % (value,)
    return coerced, None


def _derived_label(raw, fallback):
    """A player-facing label that is NEVER a raw l10n key or format template.

    ⚠ ADAPTED FROM read_store_prices.py's `derived_label` (its `name_note`
    records the same finding): base-game display strings live inside
    dataS.gar/dataS2.gar, which are PACKED AND NOT READABLE from disk -- checked
    here, `<install>/data/l10n/` does not exist at all. 678 of 748 recipe names
    are `$l10n_*` keys or `%s (%s)` runtime templates, so "resolve the name"
    has no lookup to resolve against.
    WHAT CHANGED FROM THE ORIGINAL: read_store_prices builds its label from
    brand + filename; there is no brand here, so the label is derived from the
    l10n key's own trailing segment, and from the production_id when the name is
    a bare format template. Returns (label, source) and the source is always
    stated -- a derived label must never be mistaken for the official name.
    """
    text = (raw or "").strip()
    if text and "$l10n_" not in text and "%s" not in text:
        return text, "literal"
    if text.startswith("$l10n_"):
        tail = text[len("$l10n_"):]
        for prefix in ("fillType_", "shopItem_"):
            if tail.startswith(prefix):
                tail = tail[len(prefix):]
                break
        if tail:
            return _spaced(tail), "derived_from_l10n_key"
    return _spaced(fallback or ""), "derived_from_production_id"


def _spaced(token):
    """`pigFood` -> `Pig Food`. Presentation only; never used as a key."""
    out = []
    for i, ch in enumerate(str(token)):
        if ch in "_-":
            out.append(" ")
            continue
        if i and ch.isupper() and not str(token)[i - 1].isupper():
            out.append(" ")
        out.append(ch)
    return " ".join("".join(out).split()).title() or str(token)


# A section this join may READ. Anything else -- "unavailable", "partial", or a
# status this layer has never heard of -- is a failure to report, not a dataset.
#
# ⛔ WHY THIS LIST EXISTS AT ALL, and it is DEC-001's exact shape one layer up.
# An earlier version of `_section_rows` read `data` and NEVER LOOKED AT `status`.
# read_production_defs.status_for() returns "unavailable" for an EMPTY section --
# "the definition trees are present and enumerable, so an empty result means the
# layout moved" -- and it carries `data: []` alongside it. So an unavailable
# recipe section arrived here as an empty list and the join reported
# `status: "ok"` with a per-line sentence reading "no recipe in
# production_recipes carries production_id 'clothes'". Every word of that is
# false: the recipes were not absent, they were UNREADABLE. Found by the
# DEC-113 verification lane, which reached it with three injected probes.
#
# ⚠ "unknown_by_design" IS readable and IS a claim: it means the producer looked
# and the farm genuinely has none. That is the one empty this layer may believe.
READABLE_SECTION_STATUS = ("ok", "unknown_by_design")


def _section_rows(records, domain, section):
    """(rows, None) or (None, reason). An unavailable domain or SECTION is a
    REASON, never an empty list -- the two are the whole of DEC-001."""
    record = records.get(domain)
    if not isinstance(record, dict):
        return None, ("the %r domain is not in this cache, so the join cannot "
                      "run. This is not a report that the farm has none."
                      % domain)
    envelope = record.get("envelope") or {}
    sections = envelope.get("sections")
    if not isinstance(sections, dict) or section not in sections:
        return None, ("%s.%s is absent from the cached envelope (domain status "
                      "%r), so the join cannot run."
                      % (domain, section, envelope.get("status")))
    block = sections[section] or {}
    status = block.get("status")
    if status not in READABLE_SECTION_STATUS:
        return None, ("%s.%s reports status %r, so its rows cannot be believed. "
                      "The producer's own reason: %r. Reading its `data` anyway "
                      "would turn a section that FAILED TO BE READ into a "
                      "confident statement about the farm -- an unreadable "
                      "recipe tree would render as 'no recipe carries this "
                      "production_id', which is a different and false claim."
                      % (domain, section, status, block.get("reason")))
    rows = block.get("data")
    if not isinstance(rows, list):
        return None, ("%s.%s carries no `data` list (section status %r, reason "
                      "%r)." % (domain, section, status, block.get("reason")))
    # ⚠ G4 (DEC-113 lane, LOW -- producer-bug-only, closed because it is cheap).
    # A section declaring `count: 752` while carrying 0 rows is the last route by
    # which an unreadable recipe tree becomes 45 confident per-line sentences
    # reading "no recipe carries this production_id". Nothing else in the chain
    # reconciles the two: validate_envelope does not either. Refusing costs one
    # comparison; believing it costs a page of false claims.
    declared = block.get("count")
    if declared is not None:
        # ⚠ N6 (third DEC-113 lane): the first version gated this on
        # `isinstance(declared, int)`, so a producer emitting `count` as "752"
        # or 752.0 skipped the check SILENTLY -- a guard that opts itself out on
        # the malformed input it exists to catch.
        if isinstance(declared, bool) or not isinstance(declared, (int, float)):
            return None, ("%s.%s declares count %r, which is not a number, so it "
                          "cannot be reconciled with the %d row(s) it carries."
                          % (domain, section, declared, len(rows)))
        if declared != len(rows):
            return None, ("%s.%s declares count %s but carries %d row(s). The two "
                          "disagree, so neither can be trusted -- reading the rows "
                          "anyway would turn a producer fault into confident "
                          "per-row claims about the farm."
                          % (domain, section, declared, len(rows)))
    return rows, None


def _index_recipes(sources):
    """[(section_name, rows), ...] -> (by_id, without_id, plant_slots).

    ⚠ Four of the 752 `production_recipes` rows carry NO `production_id` --
    read_production_defs.py reports them honestly via `absent_attributes`. They
    are counted and stated, never dropped into silence and never merged under a
    fake key.

    ⛔ WAVE 3B / FINDING 1 -- `greenhouse_recipes` IS A MIXED SECTION AND MUST
    NOT BE COUNTED AS ONE KIND. Measured on the live cache: 304 rows = 201
    recipe rows (identical shape to production_recipes) + 103 PLANT-SLOT rows
    carrying only `source_path`, `fill_type` and `plant_xml`. The producer says
    so itself: "A greenhouse carries TWO blocks -- a <greenhouse><plants> block
    (the slots) and a normal <productionPoint> (the economics)". Folding all 304
    into `without_id` would report 107 "recipes with no production_id" where
    there are 4, turning a correct parse into a false defect report. The
    discriminator is measured, not guessed: a recipe-shaped row carries an
    `inputs` key and a plant slot does not.
    """
    by_id, without_id, plant_slots = {}, 0, 0
    for section_name, rows in sources:
        for row in rows:
            pid = row.get("production_id")
            if not pid:
                if "inputs" in row:
                    without_id += 1
                else:
                    plant_slots += 1
                continue
            by_id.setdefault(pid, []).append((section_name, row))
    return by_id, without_id, plant_slots


def _candidate_view(candidate, source_section=None):
    """One recipe definition, reduced to what the answer depends on."""
    cph, cph_err = _number(candidate.get("cycles_per_hour"))
    inputs, outputs = {}, set()
    for item in candidate.get("outputs") or []:
        if item.get("fill_type"):
            outputs.add(item["fill_type"])
    for item in candidate.get("inputs") or []:
        ft = item.get("fill_type")
        if not ft:
            continue
        amount, amt_err = _number(item.get("amount"))
        inputs[ft] = {
            "per_cycle": amount,
            "per_cycle_error": amt_err,
            "pass_through": ft in outputs,
        }
    return {
        "source_path": candidate.get("source_path"),
        "source_section": source_section,
        "cycles_per_hour": cph,
        "cycles_per_hour_error": cph_err,
        "name": candidate.get("name"),
        "inputs": inputs,
        "outputs": sorted(outputs),
    }


def _per_hour(view, fill_type):
    """(litres_per_hour, None) or (None, reason). Never a silent 0.0."""
    spec = view["inputs"].get(fill_type)
    if spec is None:
        return None, "this definition does not list %s as an input" % fill_type
    if spec["per_cycle_error"]:
        return None, "per-cycle amount unreadable (%s)" % spec["per_cycle_error"]
    if view["cycles_per_hour_error"]:
        return None, "cycles_per_hour unreadable (%s)" % view["cycles_per_hour_error"]
    return spec["per_cycle"] * view["cycles_per_hour"], None


def _round(value, places=4):
    return None if value is None else round(value, places)


def _section_present(records, domain, section):
    """Is this section carried by the envelope AT ALL?

    ⛔ WAVE 3B / FINDING 1. This distinguishes the two absences that
    `_section_rows` collapses into one reason string, and they need opposite
    handling. A cache written before `greenhouse_recipes` existed simply does
    not carry the key -- that is a KNOWN, STATED limit and the join proceeds
    while saying so. A cache that carries the section but cannot read it is the
    F-class defect `_section_rows` was hardened for: proceeding would emit
    confident "no recipe carries this production_id" sentences that may be
    false, which is exactly the claim Finding 1 was filed about.
    """
    record = records.get(domain)
    if not isinstance(record, dict):
        return False
    sections = (record.get("envelope") or {}).get("sections")
    return isinstance(sections, dict) and section in sections


DEMAND_SOURCE_DOMAINS = ("productions", "production_defs")

# verify_domain's three verdicts, rendered for the `source_domains` map. THE
# TABLE IS THE WHOLE GUARD: a lookup miss returns "unknown", where the old
# `if d in stale else "verified_current"` returned a positive claim.
_SOURCE_DOMAIN_RENDER = {
    "stale": "stale",
    "unavailable": "unavailable",
}

# ⛔ WAVE 3C REMEDIATION (H1) -- "ok" IS NOT ONE ANSWER, IT IS TWO, AND THE
# TABLE ABOVE COULD NOT SAY WHICH.
#
# `verify_domain(mode=FAST)` returns "ok" from a comparison of mtime_ns and size
# that HASHES NO BYTES. cache_provenance says so in the note it emits with that
# very verdict: "mtime_ns and size only -- no content was hashed. A change that
# preserved BOTH would be invisible here." The information was recorded
# correctly and DISCARDED HERE: this table had no mode axis, so a `--fast` run
# published `verified_current` -- the identical word a full re-hash earns --
# about content it had never read. REPRODUCED: 18 bytes rewritten to 18
# different bytes with mtime_ns restored (what `cp -p` from a backup does, and
# this project backs saves up) rendered `verified_current` and an
# `hours_to_empty` of 10.0.
#
# ⭐ THE WEAKER WORD IS STILL A POSITIVE ONE. `unchanged_since_cache` is a real
# claim honestly made: nothing about these files has moved since the cache was
# built. It is NOT an alarm, and pinning it to one would be RSK-017's second
# shape -- a fix that passes every failure-path test while destroying the
# signal. A `--fast` run of a clean cache must still read as good news; what it
# must never do is borrow the word that a re-hash earns.
_OK_RENDER_BY_CHECK = {
    provenance.FULL: "verified_current",
    provenance.FAST: "unchanged_since_cache",
}

# The two renderings that are POSITIVE claims about a source's currency. Every
# other rendering names a failure and joins a group. ⛔ A NEW POSITIVE WORD MUST
# BE ADDED HERE DELIBERATELY -- membership is what keeps a domain out of the
# failure groups and out of the downgrade ladder, so an omission fails CLOSED
# (the domain is treated as failing) rather than open.
POSITIVE_SOURCE_RENDERS = ("verified_current", "unchanged_since_cache")


def _render_source_domain(status, freshness_check):
    """Render ONE domain's verdict, closed-set on BOTH axes.

    ⭐ ABSENCE IS NOT A VERDICT, ON EITHER AXIS. An unrecognised status renders
    "unknown" (wave 3c's original guard) and so does an "ok" carrying a check
    depth this layer does not recognise -- including a MISSING one. Neither may
    manufacture a positive claim out of an absence (DEC-001). That is what makes
    both a future fourth verdict AND a future third check depth safe here: each
    degrades to "unknown" instead of silently joining the verified pile.
    """
    if status == "ok":
        return _OK_RENDER_BY_CHECK.get(freshness_check, "unknown")
    return _SOURCE_DOMAIN_RENDER.get(status, "unknown")


def _source_domain_status(domain_status, domain_checks, accepted_stale):
    """⛔ WAVE 3C -- A THREE-STATE QUESTION, ANSWERED WITH THREE STATES.

    THE DEFECT THIS CLOSES. This function used to receive `stale_domains`: a
    LIST of the domains `main()` had found stale. But `verify_domain` returns
    THREE verdicts -- "ok", "stale" and "unavailable" -- and `main()` collected
    only the stale ones. An UNAVAILABLE domain therefore arrived here
    indistinguishable from a verified one and fell to the else branch of

        {d: ("stale" if d in stale else "verified_current") ...}

    so a domain that COULD NOT BE READ AT ALL was published as
    `verified_current`. That is a POSITIVE FALSE CLAIM, made in the very field
    wave 3b added to carry provenance, and it is worse than an omission: it
    ships beside a correctly-marked neighbour, which is exactly what makes it
    read as deliberate and therefore trustworthy.

    MEASURED PRE-FIX against the REAL `verify_domain`, with productions
    unavailable, production_defs stale and `--accept-stale`:

        source_domains = {"productions": "verified_current",   <- UNAVAILABLE
                          "production_defs": "stale"}

    ⛔ AND IT NEEDED NO FLAG. With productions unavailable and production_defs
    clean, a plain `read_state.py` with no arguments emitted
    `{"productions": "verified_current", "production_defs": "verified_current"}`
    -- the false claim was on the default path, not behind a debug affordance.

    ⭐ ABSENCE IS NOT A VERDICT. Any status this layer has never heard of, and
    any domain missing from the map entirely, renders "unknown" -- NEVER
    "verified_current". A provenance field must not be able to manufacture a
    positive claim out of an absence (DEC-001). That is the property that makes
    a future FOURTH verify_domain status safe here: it degrades to "unknown"
    instead of silently joining the verified pile.

    ⛔ WAVE 3C REMEDIATION. `domain_checks` carries, per domain, WHICH check
    produced that status -- `freshness_check` ("full" / "fast") and `comparison`
    ("performed" / "not_performed"). Both come straight from `verify_domain`'s
    detail, which already returned them; nothing new is computed here and
    nothing is inferred from a neighbouring field. They answer the two questions
    the status alone could not:

      * H1 -- an "ok" earned by a full re-hash and an "ok" earned by comparing
        mtime_ns and size are DIFFERENT CLAIMS and must not share a word.
      * M1 -- a "stale" reached by comparing files and a "stale" reached because
        the provenance could not be read are DIFFERENT FACTS, and only the first
        one licenses the sentence "no longer match the files they were built
        from".

    Returns (groups, per_domain, unverifiable, reason). `unverifiable` is the
    subset of the stale group for which NO comparison happened -- reported as a
    fact in the document, not left to prose alone.
    """
    statuses = domain_status if isinstance(domain_status, dict) else {}
    checks = domain_checks if isinstance(domain_checks, dict) else {}
    per_domain, groups = {}, {"stale": [], "unavailable": [], "unknown": []}
    unverifiable = []
    for domain in DEMAND_SOURCE_DOMAINS:
        check = checks.get(domain)
        check = check if isinstance(check, dict) else {}
        rendered = _render_source_domain(
            statuses.get(domain), check.get("freshness_check"))
        per_domain[domain] = rendered
        if rendered not in POSITIVE_SOURCE_RENDERS:
            groups[rendered].append(domain)
        # ⚠ ONLY the stale group can be "unverifiable": "unavailable" already
        # says a stronger thing about the same domain, and "unknown" says this
        # layer never received a verdict to characterise at all. Widening this
        # would double-report one domain under two headings.
        if rendered == "stale" and check.get("comparison") == NOT_PERFORMED:
            unverifiable.append(domain)
    for bucket in groups.values():
        bucket.sort()
    unverifiable.sort()
    return (groups, per_domain, unverifiable,
            _source_domain_reason(groups, unverifiable))


def _source_domain_reason(groups, unverifiable=()):
    """The prose half of the mark. One sentence per failing GROUP, strongest
    first, so a reader meets the unreadable sources before the stale ones.

    ⛔ WAVE 3C REMEDIATION (M1). THE STALE GROUP SPLITS IN TWO, BECAUSE ONE
    SENTENCE WAS ASSERTING A COMPARISON THAT NEVER HAPPENED. `verify_domain`
    answers "stale" for six distinct conditions, only some of which compare
    anything; `unverifiable` names the ones where nothing was compared, so each
    domain gets the sentence that is TRUE of it.
    """
    parts = []
    compared_stale = [d for d in groups["stale"] if d not in unverifiable]
    if groups["unavailable"]:
        parts.append(
            "A SOURCE OF THIS SECTION COULD NOT BE READ AT ALL. %s failed when "
            "this cache was generated, so there is no verification result for "
            "it and this run has NO BASIS on which to call anything derived "
            "from it current. An absent domain is not an empty one."
            % (" and ".join(groups["unavailable"]),))
    if groups["unknown"]:
        # ⛔ WAVE 3C REMEDIATION (M2). THIS SENTENCE BLAMED THE WRONG PARTY. It
        # read "This is a caller defect, surfaced here rather than absorbed."
        # Through `main()` the status map is built from `sorted(records)` and
        # `verify_domain` can only return the three table keys, so the SOLE
        # REACHABLE route to "unknown" is a source domain that is absent from
        # the cache entirely -- a cache that does not carry what this section
        # needs, which is not a caller defect at all. Naming a cause the reader
        # cannot act on is worse than naming none: it sends them to debug the
        # wrong layer. The unrecognised-status route is real but is defence in
        # depth against a FUTURE fourth verdict, so it is named second and as a
        # possibility rather than as the diagnosis.
        parts.append(
            "THE CURRENCY OF A SOURCE IS UNKNOWN. %s reached this section with "
            "no verification status this layer can recognise, so it is reported "
            "as unknown rather than assumed current. The reachable cause is a "
            "source domain this cache does not carry at all: it was never "
            "verified because it was never there. A status newer than this "
            "layer would land here too, by design, rather than being enrolled "
            "in the verified pile."
            % (" and ".join(groups["unknown"]),))
    if unverifiable:
        # ⛔ WAVE 3C REMEDIATION (M1). THE SENTENCE THIS REPLACES WAS FALSE.
        # "%s no longer match the files they were built from" asserts that a
        # comparison ran and came back different. For these domains NO
        # COMPARISON RAN -- the provenance could not be read, so there was
        # nothing to compare against. REPRODUCED with `provenance: {}`: verdict
        # "stale", reason "provenance cannot be used to verify it", and prose
        # claiming the files had changed. Nothing established that.
        #
        # ⚠ AND THE CONSENT IS WRONG TOO, WHICH IS THE HALF THAT COSTS THE USER
        # SOMETHING. Because the verdict is "stale", `--accept-stale` waves
        # these through -- but the user consented to "my cache is out of date",
        # a thing they can reason about, NOT to "this domain's provenance is
        # unreadable", which they cannot. The verdict set is unchanged here (a
        # fourth verdict is deferred), so the honest move available now is to
        # SAY SO, in the document, where --accept-stale cannot hide it.
        parts.append(
            "THE CURRENCY OF A SOURCE COULD NOT BE CHECKED AT ALL. %s carries "
            "provenance this run could not use, so NO COMPARISON against the "
            "files it was built from was ever performed. It is reported as "
            "stale because a domain that cannot be verified must never be "
            "reported as current -- but nothing here establishes that it "
            "actually changed, and nothing here establishes that it did not. "
            "⚠ --accept-stale does NOT cover this: consenting to an out-of-date "
            "cache is not consenting to one whose provenance is unreadable."
            % (" and ".join(unverifiable),))
    if compared_stale:
        parts.append(
            "EVERY FIGURE IN THIS SECTION IS DERIVED FROM A STALE CACHE. %s no "
            "longer match the files they were built from, and this run proceeded "
            "only because --accept-stale was passed. A burn rate, a stock level and "
            "an hours-to-empty computed from them describe the cache, NOT the farm "
            "as it is now. Nothing here is a current answer."
            % (" and ".join(compared_stale),))
    return " ".join(parts) or None


def _section_freshness_check(per_domain, domain_checks):
    """The WEAKEST check any POSITIVELY-VERIFIED source of this section received.

    Mirrors sec. 2.3's top-level rule -- "full" only when every one of them was
    re-hashed, because a reader asking "is this fully verified?" must not be
    told yes because one of two was -- but scoped to THIS SECTION's sources
    instead of to every domain in the run. Returns None when no source of this
    section was positively verified at all; there is then no check to report,
    and reporting "full" would be the exact false affirmation H1 is about.
    """
    checks = domain_checks if isinstance(domain_checks, dict) else {}
    seen = []
    for domain, rendered in per_domain.items():
        if rendered not in POSITIVE_SOURCE_RENDERS:
            continue
        entry = checks.get(domain)
        seen.append((entry if isinstance(entry, dict) else {}).get("freshness_check"))
    if not seen:
        return None
    return provenance.FAST if provenance.FAST in seen else provenance.FULL


def _demand_envelope(body, domain_status, domain_checks, accepted_stale):
    """Stamp any derived section -- including a refusal -- with its sources'
    currency, so no shape of this section can ship unmarked.

    ⛔ WAVE 3C REMEDIATION (H1). THE MARK IS CARRIED ON THIS SECTION, NOT
    INFERRED FROM A NEIGHBOUR. `freshness_check` was emitted at TOP LEVEL only,
    collapsed across every domain in the run -- so a reader of this section had
    to leave the subtree, find a sibling field and reason about which domains it
    covered in order to learn whether these figures rested on a re-hash or on a
    timestamp comparison. That cross-reference is exactly what wave 3b forbade:
    "the mark is carried on the SECTION ITSELF, not inferred from its
    neighbours." The per-domain words in `source_domains` now say it outright,
    and `source_freshness_check` states the weakest check THIS SECTION's own
    sources received.
    """
    (groups, per_domain, unverifiable,
     reason) = _source_domain_status(domain_status, domain_checks, accepted_stale)
    body["source_domains"] = per_domain
    body["accepted_stale"] = bool(accepted_stale)
    # ⚠ ALWAYS EMITTED, null included. A field that is present only sometimes
    # forces a reader to interpret its ABSENCE, and an absence is exactly what
    # this wave keeps proving must never carry meaning (DEC-001). null here says
    # one thing only: not one source of this section was positively verified.
    body["source_freshness_check"] = _section_freshness_check(
        per_domain, domain_checks)
    if groups["stale"]:
        body["stale_source_domains"] = groups["stale"]
    if unverifiable:
        # The stale domains for which NO comparison ran, as a FACT in the
        # document rather than a claim buried in prose. A consumer that must not
        # treat "stale" as "confirmed changed" can read this key; one that reads
        # only the sentence would have to parse English to find out (M1).
        body["unverifiable_source_domains"] = unverifiable
    if groups["unavailable"]:
        body["unavailable_source_domains"] = groups["unavailable"]
    if groups["unknown"]:
        body["unknown_source_domains"] = groups["unknown"]
    if reason:
        body["staleness_warning"] = reason
    # ⚠ "unavailable" IS NOT OVERWRITTEN. It is the stronger statement -- the
    # join did not run and there are no figures to distrust -- and replacing it
    # with a weaker mark would trade a specific refusal for a vaguer one. The
    # source fields are still attached, so no shape of this section ships
    # without the mark; only the happy paths change status.
    #
    # ⛔ WAVE 3C: the DOWNGRADE LADDER, strongest first. Pre-fix the only rung
    # was "stale", so an unreadable source could leave the body at "ok".
    if groups["unavailable"]:
        downgrade = "unavailable"
    elif groups["unknown"]:
        downgrade = "unverified"
    elif groups["stale"]:
        downgrade = "stale"
    else:
        downgrade = None
    if downgrade and body.get("status") != "unavailable":
        body["status_before_staleness_mark"] = body.get("status")
        body["status"] = downgrade
    return body


def derive_production_demand(records, *, domain_status, domain_checks, accepted_stale):
    """③a-extended + ③b + BUG-026. Returns ONE section dict, always.

    Never returns [], {} or None. An input it cannot compute is a row that says
    so; a domain it cannot read is a section that says so.

    ⛔ `domain_status` / `domain_checks` / `accepted_stale` ARE NOT A DATA SOURCE
    (wave 3b, Finding 2). They carry the caller's own freshness VERDICT -- the
    one this function previously had no way to learn and therefore could not
    mark. No farm figure is read from them; they decide only what this section
    says about the currency of the figures it computed from `records`.

    ⛔ ALL THREE ARE REQUIRED AND CARRY NO DEFAULT. A caller that forgets one
    gets a TypeError, not a section that calls every source `verified_current`
    on no evidence at all. `domain_checks` says WHICH check produced each
    verdict -- `{domain: {"freshness_check": ..., "comparison": ...}}`, straight
    from `verify_domain`'s detail -- and it is required for the same reason the
    other two are: an absent check depth renders "unknown", so omitting it fails
    CLOSED, but a caller who omits it by accident should be told, not quietly
    downgraded.
    """
    lines, err = _section_rows(records, "productions", "production_lines")
    if err:
        return _demand_envelope(
            {"status": "unavailable", "reason": err, "shape": "input_demand"},
            domain_status, domain_checks, accepted_stale)
    stock_rows, err = _section_rows(records, "productions", "storage_fill_levels")
    if err:
        return _demand_envelope(
            {"status": "unavailable", "reason": err, "shape": "input_demand"},
            domain_status, domain_checks, accepted_stale)
    recipe_rows, err = _section_rows(records, "production_defs", "production_recipes")
    if err:
        return _demand_envelope(
            {"status": "unavailable", "reason": err, "shape": "input_demand"},
            domain_status, domain_checks, accepted_stale)

    # ⛔ FINDING 1 (wave 3b) -- GREENHOUSE RECIPES LIVE IN A SIBLING SECTION AND
    # WERE NEVER READ. read_production_defs.py states in its own words that
    # `production_recipes` "deliberately excludes" greenhouse productions -- they
    # "carry their own <greenhouse> block and are reported separately, so the
    # same <production> element is never counted twice". But read_productions.py
    # walks EVERY <productionPoint> with no greenhouse filter, so a greenhouse
    # DOES produce a production_lines row. Reading only production_recipes made
    # every greenhouse line resolve zero candidates and report "no recipe in
    # production_recipes carries production_id X, so nothing is known about what
    # this line burns" -- literally true of the one section consulted, and
    # substantively FALSE about the farm, whose recipe sits in the section next
    # door in the same verified cache. MEASURED on the live cache: 7 lines
    # reported unmatched, 4 of them (strawberry, lettuce, enoki, oyster) fully
    # resolvable from greenhouse_recipes.
    sources = [("production_recipes", recipe_rows)]
    if _section_present(records, "production_defs", "greenhouse_recipes"):
        gh_rows, gh_err = _section_rows(records, "production_defs", "greenhouse_recipes")
        if gh_err:
            # Refusing, NOT falling back to production_recipes alone. An
            # unreadable greenhouse section cannot be distinguished from an
            # empty one, and proceeding would republish Finding 1's false
            # sentence with no way for a reader to tell.
            return _demand_envelope(
                {"status": "unavailable", "shape": "input_demand",
                 "reason": "production_defs.greenhouse_recipes is present but "
                           "unreadable, so a line with no match in "
                           "production_recipes cannot be called unmatched -- its "
                           "recipe may be in the section that failed. The "
                           "producer's own reason: %s" % gh_err},
                domain_status, domain_checks, accepted_stale)
        sources.append(("greenhouse_recipes", gh_rows))
        greenhouse_note = None
    else:
        greenhouse_note = (
            "production_defs.greenhouse_recipes is NOT carried by this cache, so "
            "greenhouse production lines cannot be matched and will be reported "
            "unmatched. This is a limit of the cache that was read, stated here "
            "rather than left to look like a farm with no greenhouse recipes. "
            "Regenerate the cache to consult it.")

    if not lines:
        return _demand_envelope({
            "status": "unknown_by_design",
            "shape": "input_demand",
            "count": 0,
            "data": [],
            "empty_means": "you own no production points",
            "reason": "production_lines is present and empty. That is a farm "
                      "with no productions, NOT an unreadable recipe graph.",
        }, domain_status, domain_checks, accepted_stale)

    by_id, recipes_without_id, plant_slot_rows = _index_recipes(sources)
    consulted = [name for name, _ in sources]

    # ⛔ FINDING 11 (wave 3b) -- reported, NOT silently last-one-wins. A plain
    # `stock[key] = row` discarded an earlier row with no count mismatch, no
    # warning and no code path that could ever surface it. Measured on the live
    # cache: 92 rows, 92 distinct keys, ZERO duplicates -- so this is an
    # unguarded pattern rather than a live occurrence, and it is guarded the way
    # read_farm_ledger.py guards its own siblings ("EVERY SIBLING IS ACCOUNTED
    # FOR, NOT JUST THE FIRST") rather than left to chance.
    stock, stock_duplicates = {}, {}
    for row in stock_rows:
        key = (row.get("placeable_id"), row.get("fill_type"))
        if key in stock:
            seen = stock_duplicates.setdefault(
                "%s / %s" % (key[0], key[1]),
                {"placeable_id": key[0], "fill_type": key[1], "rows": 1,
                 "fill_levels": [stock[key].get("fill_level")]})
            seen["rows"] += 1
            seen["fill_levels"].append(row.get("fill_level"))
            continue
        stock[key] = row

    data = []
    tally = {
        "lines_total": len(lines),
        "lines_recipe_matched": 0,
        "lines_unmatched": 0,
        "lines_with_an_ambiguous_input_rate": 0,
        "input_rows_total": 0,
        "input_rows_rate_resolved": 0,
        "input_rows_rate_ambiguous": 0,
        "input_rows_rate_unreadable": 0,
        "input_rows_excluded_pass_through": 0,
        "input_rows_stock_absent": 0,
        "input_rows_with_hours_to_empty": 0,
        "input_rows_sharing_stock_with_another_line": 0,
        "input_rows_rate_from_greenhouse_recipes": 0,
    }

    # ----------------------------------------------------------------- pass 1
    # Rates only. The stock join is DEFERRED to pass 2 because hours-to-empty is
    # not a property of one line (Finding 4): it depends on every line drawing
    # on the same tank, and that set is not known until every line is read.
    for line in lines:
        pid = line.get("production_id")
        placeable_id = line.get("placeable_id")
        candidates = [_candidate_view(row, section)
                      for section, row in by_id.get(pid, [])]
        label, label_source = _derived_label(
            candidates[0]["name"] if candidates else None, pid)
        row = {
            "placeable_id": placeable_id,
            "placeable_name": line.get("placeable_name"),
            "production_id": pid,
            "display_name": label,
            "display_name_source": label_source,
            "is_enabled": line.get("is_enabled"),
            "recipe_candidate_count": len(candidates),
            "inputs": [],
        }
        if not candidates:
            row["resolution"] = "unmatched"
            row["reason"] = (
                "no recipe in %s carries production_id %r, so nothing is known "
                "about what this line burns. Reported, not dropped: an unmatched "
                "line is not a line with no demand."
                % (" or ".join(consulted), pid))
            if greenhouse_note:
                row["unmatched_caveat"] = greenhouse_note
            tally["lines_unmatched"] += 1
            data.append(row)
            continue

        tally["lines_recipe_matched"] += 1
        row["resolution"] = "recipe_matched"
        row["recipe_source_paths"] = sorted(
            c["source_path"] for c in candidates if c["source_path"])
        row["recipe_source_sections"] = sorted(
            {c["source_section"] for c in candidates if c["source_section"]})

        fill_types = sorted({ft for c in candidates for ft in c["inputs"]})
        line_has_ambiguity = False
        for fill_type in fill_types:
            tally["input_rows_total"] += 1
            listing = [c for c in candidates if fill_type in c["inputs"]]
            pass_through = [c for c in listing if c["inputs"][fill_type]["pass_through"]]

            entry = {
                "fill_type": fill_type,
                "fill_type_label": _spaced(fill_type),
                "definitions_listing_this_input": len(listing),
            }

            # ③b FIRST -- see the ordering note at the top of this block.
            if pass_through and len(pass_through) == len(listing):
                entry.update({
                    "excluded": True,
                    "exclusion_reason": "pass_through",
                    "per_hour": None,
                    "per_day": None,
                    "rate_status": "excluded",
                    "stock_status": "not_applicable",
                    "hours_to_empty": None,
                    "note": "%s is BOTH an input and an output of every "
                            "definition of this recipe, so it passes through "
                            "the building rather than being consumed. Excluded "
                            "from demand and kept visible: counted as demand it "
                            "would read as a permanent shortage." % fill_type,
                })
                tally["input_rows_excluded_pass_through"] += 1
                row["inputs"].append(entry)
                continue

            # ⛔ FINDING 3 (wave 3b) -- A PASS-THROUGH CANDIDATE IS NOT A BURN
            # RATE AND MUST NOT BE AVERAGED IN. The disagreement was already
            # DETECTED and named here, and then `listing` was used UNFILTERED to
            # compute the rates -- so a definition that does not consume this
            # fill type at all contributed a per_cycle x cycles_per_hour figure
            # to the pool that decides "resolved" vs "ambiguous". It either
            # manufactured a spurious ambiguity between genuinely-consuming
            # definitions that agreed, or -- if its number happened to coincide
            # -- passed silently into a "resolved" rate one of whose sources
            # does not consume the input. The live case the docstring already
            # names, `soupCansPotato`, is exactly this branch.
            consuming = [c for c in listing
                         if not c["inputs"][fill_type]["pass_through"]]
            entry["definitions_consuming_this_input"] = len(consuming)
            if pass_through:
                entry["pass_through_disagreement"] = {
                    "pass_through_in": len(pass_through),
                    "of_definitions_listing_it": len(listing),
                    "rate_computed_over": len(consuming),
                    "note": "some definitions consume this fill type and others "
                            "pass it through. Not excluded, and flagged rather "
                            "than resolved by majority. The rate below is "
                            "computed over the CONSUMING definitions only -- a "
                            "pass-through definition is not a draw on this "
                            "input and averaging it in would understate or "
                            "fabricate the burn.",
                }

            rates, unreadable = [], []
            for cand in consuming:
                value, why = _per_hour(cand, fill_type)
                if why:
                    unreadable.append({"source_path": cand["source_path"],
                                       "source_section": cand["source_section"],
                                       "reason": why})
                else:
                    rates.append({
                        "source_path": cand["source_path"],
                        "source_section": cand["source_section"],
                        "cycles_per_hour": cand["cycles_per_hour"],
                        "per_cycle": cand["inputs"][fill_type]["per_cycle"],
                        "per_hour": value,
                    })

            distinct = sorted({_round(r["per_hour"]) for r in rates})
            if not rates:
                entry.update({
                    "excluded": False, "per_hour": None, "per_day": None,
                    "rate_status": "unreadable",
                    "candidates": unreadable,
                    "reason": "every definition consuming this input has an "
                              "unreadable rate; no number is emitted.",
                })
                tally["input_rows_rate_unreadable"] += 1
            elif len(distinct) > 1:
                # ⛔ BUG-026. The candidates disagree ON THE ANSWER. No number.
                line_has_ambiguity = True
                entry.update({
                    "excluded": False, "per_hour": None, "per_day": None,
                    "rate_status": "ambiguous",
                    "candidate_count": len(rates),
                    "distinct_per_hour_values": distinct,
                    "candidates": rates,
                    "unreadable_candidates": unreadable,
                    "reason": "production_id %r resolves to %d definitions that "
                              "DISAGREE on this input's burn rate (%s L/h). "
                              "A production_id does not identify one recipe, and "
                              "nothing in the savegame layer says which "
                              "definition this placeable uses, so no rate and no "
                              "hours-to-empty are emitted for this input. "
                              "Picking one would produce a plausible number that "
                              "could be wrong by the full spread (BUG-026)."
                              % (pid, len(rates),
                                 ", ".join("%g" % v for v in distinct)),
                })
                tally["input_rows_rate_ambiguous"] += 1
            else:
                # ⚠ FINDING 12 (wave 3b): the EXACT rate is kept alongside the
                # rounded display value. hours_to_empty divides by the exact one
                # -- rounding a denominator before dividing by it is the precise
                # ordering mistake this wave's own sibling suite guards against
                # for per_play_hour.
                exact = rates[0]["per_hour"]
                per_hour = distinct[0]
                entry.update({
                    "excluded": False,
                    "per_hour": per_hour,
                    "per_day": _round(exact * HOURS_PER_DAY),
                    "rate_status": "resolved",
                    "candidate_count": len(rates),
                    "cycles_per_hour": rates[0]["cycles_per_hour"],
                    "per_cycle": rates[0]["per_cycle"],
                    "agreeing_source_paths": sorted(
                        r["source_path"] for r in rates if r["source_path"]),
                    "unreadable_candidates": unreadable,
                })
                entry["_per_hour_exact"] = exact
                if all(r["source_section"] == "greenhouse_recipes" for r in rates):
                    tally["input_rows_rate_from_greenhouse_recipes"] += 1
                tally["input_rows_rate_resolved"] += 1

            row["inputs"].append(entry)

        if line_has_ambiguity:
            tally["lines_with_an_ambiguous_input_rate"] += 1
        data.append(row)

    # ------------------------------------------------- the shared-draw index
    # ⛔ FINDING 4 (wave 3b). storage_fill_levels is keyed PER PLACEABLE, not per
    # production line, because in FS25 one <productionPoint> holds several
    # <production> lines that share one physical tank. The consuming side
    # ignored that: each line divided the WHOLE shared stock by its OWN burn
    # rate, so a 1000 L tank feeding a 100 L/h line and a 50 L/h line reported
    # 10 h and 20 h when the true combined runway is 6.7 h -- every figure wrong
    # in the OPTIMISTIC direction, which is the worst direction for a "you are
    # about to run dry" warning. MEASURED on the live cache: 6 (placeable,
    # fill_type) tanks are drawn by 2-3 lines each AND carry a stock row, so six
    # overstated runways ship today -- montanaDairy's MILK feeds butter_milk,
    # cheese and milkBottled from one silo.
    draws = {}
    for row in data:
        for entry in row["inputs"]:
            if entry.get("excluded"):
                continue
            draws.setdefault((row["placeable_id"], entry["fill_type"]), []).append(
                {"production_id": row["production_id"],
                 "rate_status": entry.get("rate_status"),
                 "per_hour": entry.get("_per_hour_exact")})

    # ----------------------------------------------------------------- pass 2
    for row in data:
        placeable_id = row["placeable_id"]
        for entry in row["inputs"]:
            exact = entry.pop("_per_hour_exact", None)
            if entry.get("excluded"):
                continue
            fill_type = entry["fill_type"]
            drawers = draws.get((placeable_id, fill_type), [])
            shared = [d for d in drawers if d["production_id"] != row["production_id"]]
            if shared:
                tally["input_rows_sharing_stock_with_another_line"] += 1
                entry["shared_stock"] = {
                    "drawn_by_production_ids": sorted(d["production_id"] for d in drawers),
                    "line_count": len(drawers),
                    "note": "this stock is a SINGLE tank in the placeable, drawn "
                            "by more than one production line. A runway computed "
                            "from this line's own rate alone would overstate it.",
                }

            held = stock.get((placeable_id, fill_type))
            if held is None:
                entry.update({
                    "stock_status": "absent",
                    "fill_level": None,
                    "hours_to_empty": None,
                    "stock_reason":
                        "no storage_fill_levels row exists for (%r, %s), so the "
                        "manager cannot see this input's stock. This is NOT a "
                        "report that the stock is zero, and the input is NOT "
                        "dropped -- an invisible input renders as a production "
                        "with nothing wrong (DEC-001)."
                        % (placeable_id, fill_type),
                })
                tally["input_rows_stock_absent"] += 1
                continue

            level, level_err = _number(held.get("fill_level"))
            entry["fill_level"] = level
            if level_err:
                entry.update({
                    "stock_status": "unreadable",
                    "hours_to_empty": None,
                    "stock_reason": "fill_level %s" % level_err,
                })
                continue

            entry["stock_status"] = "ok"

            # The rate that actually empties this tank is the SUM over every
            # line drawing on it -- and if any one of those lines has no
            # resolved rate, the sum is unknown. Emitting this line's own
            # figure anyway would be a plausible number that is wrong by
            # however much the unresolved lines burn (BUG-026's rule, applied
            # to the denominator instead of the recipe).
            unresolved = [d["production_id"] for d in drawers
                          if d["rate_status"] != "resolved"]
            combined = None
            if not unresolved:
                combined = sum(d["per_hour"] for d in drawers
                               if d["per_hour"] is not None)
            if shared:
                entry["shared_stock"]["this_line_per_hour"] = _round(exact)
                entry["shared_stock"]["combined_per_hour"] = _round(combined)
                if unresolved:
                    entry["shared_stock"]["unresolved_lines"] = sorted(unresolved)

            if entry.get("rate_status") != "resolved":
                entry["hours_to_empty"] = None
                entry.setdefault(
                    "hours_to_empty_reason",
                    "no usable burn rate for this input, so a stock level "
                    "cannot be turned into a runway.")
                continue
            if unresolved:
                entry["hours_to_empty"] = None
                entry["hours_to_empty_reason"] = (
                    "this stock is shared with %s, whose burn rate for %s could "
                    "not be resolved, so the COMBINED rate that actually empties "
                    "the tank is unknown. This line's own rate would overstate "
                    "the runway; no number is emitted."
                    % (", ".join(sorted(unresolved)), fill_type))
                continue
            # ⛔ FINDING 6 (wave 3b). `if rate:` is False for a computed,
            # correct 0.0 -- so a row carrying rate_status "resolved" and
            # per_hour 0.0 was reported with "no usable burn rate for this
            # input", contradicting its own adjacent field. A known zero is an
            # ANSWER ("it will never run dry"), not an absence, and this file's
            # own _number docstring warns against exactly that conflation one
            # function away.
            if combined is None or combined < 0:
                entry["hours_to_empty"] = None
                entry["hours_to_empty_reason"] = (
                    "the combined burn rate for this input is %r, which cannot "
                    "produce a runway." % (combined,))
                continue
            if combined == 0:
                entry["hours_to_empty"] = None
                entry["hours_to_empty_reason"] = (
                    "this input's burn rate is a COMPUTED, RESOLVED ZERO, so the "
                    "stock will never run dry. This is an answer, not a missing "
                    "rate -- the recipe consumes none of it per hour.")
                continue
            entry["hours_to_empty"] = _round(level / combined, 2)
            tally["input_rows_with_hours_to_empty"] += 1

    body = {
        "status": "ok",
        "shape": "input_demand",
        "count": len(data),
        "data": data,
        "identity_fields": ["placeable_id", "production_id", "fill_type"],
        "recipe_identity_fields": ["source_path", "production_id"],
        "tally": tally,
        "recipe_sections_consulted": consulted,
        "recipes_without_production_id": recipes_without_id,
        "greenhouse_plant_slot_rows": plant_slot_rows,
        "derivation": (
            "per_hour = per_cycle x cycles_per_hour; per_day = per_hour x 24; "
            "hours_to_empty = fill_level / COMBINED per_hour, summed over every "
            "production line drawing on the same (placeable_id, fill_type) tank. "
            "Three static values from ONE snapshot -- no second sample and no "
            "elapsed time is involved, so nothing here is a measured rate over "
            "time."
        ),
        "empty_means": "you own no production points",
        "absence_guarantee": (
            "Every production line is emitted, including the ones with no "
            "matching recipe. Every input fill type is emitted, including the "
            "ones with no stock row and the ones excluded as pass-through. No "
            "row is ever dropped for being unresolvable -- it is emitted with "
            "the reason it could not be resolved."
        ),
        "reason": (
            "Derived in-process from two cached domains whose currency was "
            "verified by this same run. NEVER a substitute for the domains "
            "themselves; it computes nothing they do not already contain."
        ),
    }
    if greenhouse_note:
        body["greenhouse_recipes_note"] = greenhouse_note
    if stock_duplicates:
        body["storage_fill_level_duplicate_keys"] = sorted(
            stock_duplicates.values(), key=lambda d: (str(d["placeable_id"]), str(d["fill_type"])))
        body["storage_fill_level_duplicate_note"] = (
            "more than one storage_fill_levels row carries the same "
            "(placeable_id, fill_type). The FIRST was used and the others are "
            "reported here rather than silently overwriting it -- two rows for "
            "one tank means the stock this section divided by may not be the "
            "whole of it."
        )
    return _demand_envelope(body, domain_status, domain_checks, accepted_stale)


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
    # ⛔ WAVE 3C. `domain_status` carries verify_domain's ACTUAL verdict for
    # every domain. `stale_domains` is kept for the STALE gate below, which asks
    # a genuinely binary question ("must this run refuse?") -- but it is NOT a
    # freshness report and must never again be passed off as one. Deriving the
    # derived section's provenance from it published an UNAVAILABLE domain as
    # `verified_current`, because "not stale" was read as "verified".
    #
    # ⛔ WAVE 3C REMEDIATION (H1 + M1). `domain_checks` carries WHICH CHECK
    # produced each verdict. It is read from the SAME `detail` this loop already
    # receives and already emits under `sections[domain]["verification"]` --
    # nothing is recomputed and `cache_provenance.py` is untouched, because
    # `verify_source_set` has always returned `freshness_check` in its detail.
    # The information existed at this line the whole time; the layer below just
    # never got it. That is the shape of this entire defect chain, and it is why
    # both facts are now PASSED rather than left to be inferred downstream.
    sections, stale_domains, domain_status, domain_checks = {}, [], {}, {}
    for domain in sorted(records):
        status, reason, detail = verify_domain(records[domain], mode=mode)
        domain_status[domain] = status
        domain_checks[domain] = {
            "freshness_check": (detail or {}).get("freshness_check"),
            "comparison": (detail or {}).get("comparison"),
        }
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

    # ITEM ③a-extended / ③b / BUG-026. Derived HERE and never cached: a
    # persisted derivation is a second copy of the truth that can drift from the
    # first, and this one lives exactly as long as the process that printed it
    # (the same rule the aggregate follows). It sits OUTSIDE `aggregate` so the
    # claims manifest keeps carrying only figures it can re-resolve on disk.
    # ⛔ WAVE 3B / FINDING 2 -- THE VERDICT TRAVELS WITH THE DATA. This call
    # passed the RAW `records` and nothing else, so the derived section had no
    # parameter and no code path by which it could learn that the domains it
    # was about to read had just been verified STALE and were being read only
    # because --accept-stale was passed. It therefore emitted `status: "ok"`
    # with real-looking hours-to-empty figures beside a `sections` block that
    # correctly said "stale" throughout -- the exact "half-marked view invites
    # trusting the unmarked half" failure this module's own docstring forbids.
    # ⛔ WAVE 3C. Both freshness arguments are REQUIRED and named here. The
    # parameters carry no defaults, so a caller that forgets them raises
    # TypeError rather than being handed a section that calls every source
    # `verified_current` on no evidence at all.
    derived = {DEMAND_SECTION: derive_production_demand(
        records, domain_status=domain_status, domain_checks=domain_checks,
        accepted_stale=accept_stale)}

    if render_only:
        # ⛔ WAVE 3B / FINDING 2(c). `accepted_stale` was absent from this
        # payload ENTIRELY -- it is added only to the full document below -- so
        # `--accept-stale --render-only` produced a JSON document with no field
        # anywhere saying the run had accepted stale data. The coarse top-level
        # flag that exists in full mode was not merely unset here; it did not
        # exist. A debug affordance may print less, never claim more.
        print(json.dumps({
            "reader": READER,
            "freshness_check": freshness_check,
            "status": top_status,
            "accepted_stale": accept_stale,
            "stale_domains": stale_domains,
            "domains_degraded": degraded,
            "aggregate": aggregate,
            "derived": derived,
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
        "derived": derived,
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
