"""
Fail loudly when this skill's documentation claims something its own code
contradicts.

Usage: python3 check_skill_honesty.py <savegame_dir> [--quiet] [--skill-md PATH]
Exit 0 = honest. Exit 1 = the docs are lying. Run it after touching a parser
or SKILL.md.

--skill-md lets you check a DIFFERENT copy -- an old revision, a draft, a
proposed rewrite -- without touching the live one. That flag exists because its
absence nearly caused a real accident: proving this checker worked meant testing
it against the stale SKILL.md, and with no way to point it elsewhere the lead
swapped the live file out and back while another agent was actively rewriting
it. Nothing was lost, by luck rather than care. A tool that forces you to mutate
the thing you're inspecting is a badly designed tool. Check an old revision with:
    git show <rev>:path/to/SKILL.md > /tmp/old.md
    python3 check_skill_honesty.py <savegame_dir> --skill-md /tmp/old.md

WHY THIS EXISTS
---------------
Four times in one session, prose drifted from code and nobody noticed:

  - SKILL.md vouched for the most broken parser in the toolkit as
    "community-verified" (F-001/F-009). That misplaced confidence is what stopped
    anyone checking it, and it cost three rewritten sanctum files.
  - SKILL.md kept calling farmland area "the one genuine wall that remains" for
    hours after read_farmland_areas.py decoded it (262 ha, cross-checked to the
    cent against farms.xml's own fieldPurchase). A fresh session would have
    followed the doc and asked the player to count hectares by hand -- the exact
    thing the skill had just been fixed to stop doing.
  - init_sanctum.py wrote its own inline placeholders instead of the templates,
    so a new farm's memory arrived pre-loaded with claims the references exist to
    disprove.
  - FRICTION-LOG.md listed three already-fixed defects as OPEN.

Every one is the same defect this whole skill was repaired to avoid: ABSENCE
LOOKING LIKE DATA. Here the absence is an *update*, and it reads as "still true."
A doc doesn't announce that it has rotted.

DISCIPLINE DOESN'T FIX THIS -- STRUCTURE DOES
---------------------------------------------
The parsers stopped lying when they were made to emit {"error": ...} instead of
[] -- structurally unable to pass absence off as data. Not by anyone promising
to be careful. (The lead wrote "check the artifact, not the command" into
CLAUDE.md and then broke it three times the same afternoon.)

So: the PROBES BELOW ARE THE SPEC. Prose is checked against them, not the other
way round. If a probe can get the data, any doc saying it can't is lying, and
this script says so by name.

ADDING A CAPABILITY
-------------------
When a parser learns to do something the docs call impossible, add a row to
CAPABILITIES with a probe that gets it and the phrases that would then be false.
That is the whole maintenance burden, and it is the point: the claim becomes
executable instead of aspirational.
"""
import json
import os
import re
import subprocess
import sys

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
REFERENCES_DIR = os.path.join(SKILL_DIR, "references")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")


def run_parser(script, args):
    """Run a parser and return its parsed JSON, or None if it failed."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script)] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


# --- The probes. These are the spec. -----------------------------------------
#
# probe(savegame_dir) -> (is_answerable: bool, evidence: str)
# stale_phrases: regexes that are FALSE once the probe succeeds.

def probe_field_ownership(sg):
    d = run_parser("read_fields.py", [sg])
    if not d or "error" in d:
        return False, "read_fields.py failed or errored"
    own = (d.get("ownership") or {})
    if own.get("resolved") is True:
        return True, f"resolved {d.get('owned_field_count')} owned fields via {own.get('source')}"
    return False, f"unresolved: {own.get('why_unresolved')}"


def probe_farmland_area(sg):
    d = run_parser("read_farmland_areas.py", [sg])
    if not d or "error" in d:
        return False, f"read_farmland_areas.py: {(d or {}).get('error', 'failed')}"
    owned = d.get("owned") or {}
    ha = owned.get("total_area_ha")
    if ha:
        xc = (d.get("field_purchase_cross_check") or {}).get("match")
        return True, f"{ha} ha across {owned.get('count')} parcels, cost ${owned.get('total_cost'):,.2f}, fieldPurchase cross-check match={xc}"
    return False, "no area returned"


def probe_land_cost_from_farms_xml(sg):
    """The cost was in farms.xml all along -- F-012. Two independent routes now."""
    path = os.path.join(sg, "farms.xml")
    if not os.path.isfile(path):
        return False, "farms.xml not found"
    m = re.search(r"<fieldPurchase>(-?[\d.]+)</fieldPurchase>", open(path, encoding="utf-8", errors="replace").read())
    if m:
        return True, f"farms.xml <fieldPurchase> = {abs(float(m.group(1))):,.2f} (the game's own record)"
    return False, "no <fieldPurchase> in farms.xml"


def probe_store_prices(sg):
    d = run_parser("read_store_prices.py", [sg, "--fleet"])
    if not d or "error" in d:
        return False, f"read_store_prices.py: {(d or {}).get('error', 'failed')}"
    return True, "resolves owned fleet to real store prices from install + mod zips"


def probe_save_location(sg):
    """locate_save.py must find the save with NO arguments (F-007)."""
    d = run_parser("locate_save.py", [])
    if not d:
        return False, "locate_save.py failed"
    n = d.get("savegame_count", 0)
    if n:
        return True, f"found {n} savegame(s) unaided on this platform (wsl={d.get('platform', {}).get('wsl')})"
    return False, "found none unaided"


# --- WIRING probes ------------------------------------------------------------
#
# The checks above ask "does a doc deny something the code can do?" These ask a
# harder question: "does a capability reach the BRIEFING, or is it merely built?"
#
# That distinction has bitten this project hard. read_farmland_areas.py resolved
# field ownership for HOURS while read_fields.py still returned owned: null and
# farm_snapshot.py still printed "unknown_by_design" -- the digest saying it did
# not know something the toolkit knew for certain (F-004). Separately,
# farm_snapshot.py itself sat built and unmentioned in SKILL.md, so no session
# would ever have run it.
#
# A capability that never reaches the briefing does not exist. BUILT IS NOT
# WIRED. These probes fail when a parser can answer something the digest can't
# say -- the same rule as everywhere else here, applied to ourselves.

def probe_digest_is_a_digest(sg):
    """The briefing digest must stay a small fraction of the real dump.

    HOW THIS PROBE WAS WRONG FIRST, because the story is the lesson:
    the first version compared farm_snapshot.py against collect_state.py's DEFAULT
    output and failed loudly -- "the digest is 2.0x the dump it exists to condense."
    Convincing, quotable, and false. collect_state.py's default is COMPACTED: it
    truncates every list to one example. It is a SAMPLE, not a dump. So the probe
    was measuring a curated briefing against a one-item-per-list sample and calling
    the briefing bloated. Against the REAL dump (--debug, ~1.3MB) the digest is
    under 3% -- exactly what a digest should be.

    The invariant sounded like a law ("a summary must be smaller than its source")
    and was never checked against what it actually measured. That is this project's
    own defect in a new shape: not absence looking like data, but a MEASUREMENT
    LOOKING LIKE EVIDENCE. A probe is only as good as its yardstick -- the same
    lesson as calling 76,772 L impossible using a base-game tank size for a modded
    machine (F-019, by hand).

    So: compare against --debug, the genuine unabridged output. The ceiling is a
    ratio rather than a byte count because a fixed number is a guess that ages,
    while "the briefing is a small fraction of everything there is" stays true as
    both sides grow."""
    import subprocess as _sp

    def size(script, extra=()):
        r = _sp.run([sys.executable, os.path.join(SCRIPTS_DIR, script), sg, *extra],
                    capture_output=True, text=True, timeout=600)
        return len(r.stdout)

    try:
        digest = size("farm_snapshot.py")
        full = size("collect_state.py", ("--debug",))
    except Exception as e:
        return False, f"could not measure: {e}"
    if not digest or not full:
        return False, "one of the scripts produced no output"

    ratio = digest / full
    CEILING = 0.10   # a briefing carrying >10% of everything is not selecting, it's copying
    if ratio <= CEILING:
        return True, (f"digest {digest:,}B is {ratio:.1%} of the unabridged dump "
                      f"({full:,}B) -- still selecting, not copying")
    return False, (f"digest {digest:,}B is {ratio:.1%} of the unabridged dump ({full:,}B), over "
                   f"the {CEILING:.0%} ceiling. A briefing that carries this much of everything "
                   f"has stopped choosing. Trim to what is ACTIONABLE and gate the rest behind "
                   f"--verbose (the pattern collect_state.py proved -- F-006).")


def probe_wired_inventory(sg):
    """The farm's HOLDINGS -- grain in vehicles, contents of silos. The manager
    tracks what the farm owns and owes; without this it cannot see what the farm
    has PRODUCED. 123,706 L of grain once sat in two combines, worth $63,664,
    and nothing in the skill could see it."""
    d = run_parser("farm_snapshot.py", [sg])
    if not d:
        return False, "farm_snapshot.py failed"
    if any(k in d for k in ("inventory", "holdings", "storage")):
        return True, "farm_snapshot.py surfaces an inventory/holdings section"
    return False, ("farm_snapshot.py has NO inventory section -- grain in vehicles and silos "
                   "is invisible to a briefing even if read_vehicles.py can see it")


def probe_wired_input_prices(sg):
    """Inputs are a BUY calendar: seed, fertiliser, lime, herbicide are all priced
    in economy.xml. Observed: SEEDS 277 on one in-game day and 891 the next -- a
    3.2x swing the manager could not see."""
    d = run_parser("farm_snapshot.py", [sg])
    if not d:
        return False, "farm_snapshot.py failed"
    blob = json.dumps(d).upper()
    if "SEEDS" in blob or "FERTILIZER" in blob or "INPUT_PRICE" in blob:
        return True, "farm_snapshot.py surfaces input prices"
    return False, ("farm_snapshot.py never mentions input prices -- economy.xml prices SEEDS/"
                   "FERTILIZER/LIME/HERBICIDE and a briefing cannot see any of it")


def probe_wired_sales(sg):
    """read_sales.py has always parsed the used-equipment market and the briefing
    has never shown it. Listings carry timeLeft; they expire."""
    d = run_parser("farm_snapshot.py", [sg])
    if not d:
        return False, "farm_snapshot.py failed"
    if any("sale" in k or "market" in k or "listing" in k for k in d):
        return True, "farm_snapshot.py surfaces the used-equipment market"
    return False, ("read_sales.py parses listings but farm_snapshot.py never shows them -- "
                   "built, not wired")


def probe_wired_notifications(sg):
    """
    Reachable is not wired. notify_farm_manager.py sat in scripts/ and was named
    in SKILL.md -- so the reachability probe passed -- while ZERO workflows
    mentioned it. A session would know the capability existed and never reach for
    it. "Built, not wired" is the exact failure this guard family exists for, and
    it walked straight past this one because it only checked SKILL.md.

    A notification is the only thing here that INTERRUPTS the player, so the
    during-session rules are where it has to fire, and onboarding is where its
    availability has to be established -- by LOOKING for the mod, never by sending
    a message and misreading exit 2 (F-029/F-030).
    """
    skill_dir = os.path.dirname(SCRIPTS_DIR)
    refs = os.path.join(skill_dir, "references")
    missing = []

    brief = os.path.join(refs, "workflow-briefing.md")
    if os.path.isfile(brief):
        with open(brief, encoding="utf-8") as f:
            t = f.read()
        if "notify_farm_manager.py" not in t:
            missing.append("workflow-briefing.md never names the notifier -- nothing would fire it")
        if "notifications.md" not in t:
            missing.append("workflow-briefing.md doesn't point at references/notifications.md")

    onb = os.path.join(refs, "workflow-onboarding.md")
    if os.path.isfile(onb):
        with open(onb, encoding="utf-8") as f:
            t = f.read()
        if "notifications.available" not in t:
            missing.append("workflow-onboarding.md never establishes notifications.available")

    tmpl = os.path.join(skill_dir, "templates", "config.json")
    if os.path.isfile(tmpl):
        with open(tmpl, encoding="utf-8") as f:
            t = f.read()
        if "notifications" not in t:
            missing.append("templates/config.json has no notifications flag for a workflow to read")

    if missing:
        return False, "; ".join(missing)
    return True, ("the notifier is wired: onboarding establishes availability, the "
                  "during-session rules fire it, notifications.md governs when")


def probe_crop_state(sg):
    """
    Readiness must come from growthState, never groundType.

    groundType is the terrain TEXTURE. It still reads HARVEST_READY on a field cut
    days ago, and it cannot tell HARVEST_READY from HARVEST_READY_OTHER -- which is
    not a readiness distinction at all (the same canola at the same growthState
    appears under both). Reading it listed two already-harvested fields as ready on
    this farm: oat 71 at growthState 7 (cut) and canola 114 at 11 (cut).

    This probe fails if the readiness test regresses to groundType, or if
    crop_state stops reaching the digest, or if an unresolvable crop is reported as
    anything other than unknown.
    """
    d = run_parser("read_fields.py", [sg])
    if not d:
        return False, "read_fields.py failed"

    fields = d.get("fields") or []
    if not fields:
        return False, "read_fields.py returned no fields"
    if "crop_state" not in fields[0]:
        return False, ("read_fields.py no longer reports crop_state per field -- readiness "
                       "has regressed to groundType, which is the terrain texture")

    for key in ("harvested_on_owned_land", "unknown_crop_state_on_owned_land"):
        if key not in d:
            return False, f"read_fields.py no longer reports {key}"

    # A crop with no state table must be UNKNOWN, never silently 'not ready'.
    unknown = d.get("unknown_crop_state_on_owned_land")
    if unknown is None and d.get("harvest_ready_on_owned_land") is not None:
        return False, ("read_fields.py reports readiness but not which fields it could NOT "
                       "classify -- absence would read as 'nothing to do there'")

    src = os.path.join(SCRIPTS_DIR, "read_fields.py")
    with open(src, encoding="utf-8") as f:
        text = f.read()
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if 'startswith("HARVEST_READY")' in line or 'ground_type"] == "HARVEST_READY"' in line:
            return False, (f"read_fields.py:{line_no} tests groundType for readiness again -- "
                           f"that is the terrain texture, not the crop's state")

    ready = d.get("harvest_ready_on_owned_land")
    cut = d.get("harvested_on_owned_land")
    if ready is not None and cut is not None:
        overlap = {f["id"] for f in ready} & {f["id"] for f in cut}
        if overlap:
            return False, f"fields {sorted(overlap)} are reported BOTH ready and harvested"

    n_ready = len(ready) if ready is not None else "null"
    n_cut = len(cut) if cut is not None else "null"
    return True, (f"readiness comes from growthState vs each crop's foliage states: "
                  f"{n_ready} ready, {n_cut} already cut, "
                  f"{len(unknown or [])} honestly unknown")


CAPABILITIES = [
    {
        "id": "digest_is_a_digest",
        "must_be_wired": True,
        "what": "the briefing digest staying smaller than the full snapshot",
        "probe": probe_digest_is_a_digest,
        "stale_phrases": [],
    },
    {
        "id": "wired_inventory",
        "must_be_wired": True,
        "skill_md_must_mention": ["inventory"],
        "what": "the farm's holdings reaching the briefing (grain in vehicles/silos)",
        "probe": probe_wired_inventory,
        "stale_phrases": [],
    },
    {
        "id": "wired_input_prices",
        "must_be_wired": True,
        "skill_md_must_mention": ["seed", "fertilizer"],
        "what": "input prices (seed/fertiliser/lime) reaching the briefing",
        "probe": probe_wired_input_prices,
        "stale_phrases": [],
    },
    {
        "id": "crop_state_not_ground_type",
        "must_be_wired": True,
        "skill_md_must_mention": ["crop_state", "terrain texture"],
        "what": "readiness read from growthState, not from groundType (the terrain texture)",
        "probe": probe_crop_state,
        "stale_phrases": [
            r"groundType[^.\n]{0,40}HARVEST_READY[^.\n]{0,30}(means|=)\s*ready",
        ],
    },
    {
        "id": "wired_notifications",
        "must_be_wired": True,
        "skill_md_must_mention": ["notify_farm_manager.py", "notifications.md"],
        "what": "the on-screen notifier being reachable AND actually fired by a workflow",
        "probe": probe_wired_notifications,
        "stale_phrases": [],
    },
    {
        "id": "wired_sales",
        "must_be_wired": True,
        "skill_md_must_mention": ["sales"],
        "what": "the used-equipment market reaching the briefing",
        "probe": probe_wired_sales,
        "stale_phrases": [],
    },
    {
        "id": "field_ownership",
        "what": "which fields the player owns",
        "probe": probe_field_ownership,
        "stale_phrases": [
            r"which fields are mine[^.\n]{0,60}unanswerable",
            r"field-level ownership is NOT derivable",
            r"not ownership.{0,120}unanswerable from XML alone",
        ],
    },
    {
        "id": "farmland_area",
        "what": "farmland area / land cost",
        "probe": probe_farmland_area,
        "stale_phrases": [
            r"the one genuine wall",
            r"farmland \*?area\*?[^.\n]{0,80}not in any XML",
            r"parcel AREA[^.\n]{0,40}(genuine|only) wall",
        ],
    },
    {
        "id": "land_cost_farms_xml",
        "what": "land cost, straight from farms.xml",
        "probe": probe_land_cost_from_farms_xml,
        "stale_phrases": [r"land cost[^.\n]{0,40}(unobtainable|cannot be read|has to come from you)"],
    },
    {
        "id": "store_prices",
        "what": "new-equipment / store prices",
        "probe": probe_store_prices,
        "stale_phrases": [
            r"No script reads these yet",
            r"prices aren't in the save[^.\n]{0,40}don't guess",
            r"ask the player to tell you prices",
        ],
    },
    {
        "id": "save_location",
        "what": "finding the savegame unaided",
        "probe": probe_save_location,
        "stale_phrases": [
            r"locate_save\.py[^.\n]{0,60}misses entirely",
            r"just ask (the player )?first",
        ],
    },
]

# Genuinely unanswerable from disk -- verified, and NOT probeable by definition.
# Listed so the honest list stays visible next to the executable one.
HUMAN_ONLY = [
    "contract rewards (computed by the game at accept-time; in-game screen only)",
    # NOT the loan interest rate (F-124) -- the manual (p.8) says interest is paid once
    # per month, and a year is always 12 months, so check_sanctum_freshness.py's
    # probe_interest_rate derives it as one month's loanInterest x 12 / loan. Listing
    # it here would contradict that probe.
    "the player's judgment -- goals, risk, what to decide alone",
    "whether the player slept (a discontinuous time jump; ask, never infer from numbers)",
]


def check_honesty(sg, skill_text):
    failures, notes = [], []
    for cap in CAPABILITIES:
        answerable, evidence = cap["probe"](sg)

        # A WIRING probe inverts the usual test. The others ask "does a doc deny
        # something the code can do?" and only fire when the probe SUCCEEDS. A
        # wiring probe fires when it FAILS: the capability exists in a parser but
        # never reaches the briefing. Without this branch these probes could
        # never fail -- a check that cannot fail is itself absence dressed as
        # data, which is the whole thing this file exists to prevent.
        if cap.get("must_be_wired"):
            # Wiring has TWO halves and both must hold. The digest can carry a
            # capability while SKILL.md never mentions it -- and a session reads
            # SKILL.md, so a silent doc makes the capability invisible even with
            # the data flowing. farm_snapshot.py itself sat built and unmentioned
            # for hours; no session would ever have run it. Data reaching the
            # briefing is necessary; the skill knowing it exists is the other half.
            doc_terms = cap.get("skill_md_must_mention") or []
            doc_missing = [t for t in doc_terms if t.lower() not in skill_text.lower()]
            if answerable and doc_missing:
                failures.append({
                    "capability": cap["what"],
                    "evidence_it_works": f"the digest carries it ({evidence})",
                    "stale_claims": [f"but SKILL.md never mentions: {', '.join(doc_missing)} "
                                     f"-- a session reads SKILL.md; if it's silent, the capability is invisible"],
                })
                continue
            if answerable:
                notes.append(f"  [ok]   {cap['what']}: WIRED (digest + SKILL.md) -- {evidence}")
            else:
                failures.append({
                    "capability": cap["what"],
                    "evidence_it_works": "N/A -- this is a WIRING failure, not a stale claim",
                    "stale_claims": [f"NOT WIRED: {evidence}"],
                })
            continue

        if not answerable:
            notes.append(f"  [skip] {cap['what']}: probe says not answerable here ({evidence})")
            continue
        hits = []
        for pat in cap["stale_phrases"]:
            for m in re.finditer(pat, skill_text, re.I):
                line = skill_text[:m.start()].count("\n") + 1
                hits.append(f"SKILL.md:{line}: {m.group(0)[:70]!r}")
        if hits:
            failures.append({
                "capability": cap["what"],
                "evidence_it_works": evidence,
                "stale_claims": hits,
            })
        else:
            notes.append(f"  [ok]   {cap['what']}: answerable, and SKILL.md doesn't deny it")
    return failures, notes


def check_reachability(skill_text):
    """Every script and reference must be reachable from SKILL.md, and every path
    SKILL.md names must exist. Half this skill was orphaned -- reading-the-save.md
    and farm_snapshot.py had ZERO mentions -- so a session would never load them."""
    failures, notes = [], []

    ignore_scripts = {"__init__.py", "xml_utils.py", "check_skill_honesty.py"}
    for f in sorted(os.listdir(SCRIPTS_DIR)):
        if not f.endswith(".py") or f in ignore_scripts:
            continue
        if f not in skill_text:
            failures.append(f"scripts/{f} is never mentioned in SKILL.md -- a session will never run it")
        else:
            notes.append(f"  [ok]   scripts/{f} reachable")

    if os.path.isdir(REFERENCES_DIR):
        for f in sorted(os.listdir(REFERENCES_DIR)):
            if not f.endswith(".md"):
                continue
            if f not in skill_text:
                failures.append(f"references/{f} is never mentioned in SKILL.md -- a session will never load it")
            else:
                notes.append(f"  [ok]   references/{f} reachable")

    for m in re.finditer(r"(?:scripts|references|templates)/[A-Za-z0-9_.\-]+", skill_text):
        rel = m.group(0)
        if not os.path.exists(os.path.join(SKILL_DIR, rel)):
            line = skill_text[:m.start()].count("\n") + 1
            failures.append(f"SKILL.md:{line} names {rel}, which does not exist")

    return failures, notes


def main():
    argv = sys.argv[1:]
    quiet = "--quiet" in argv
    skill_md = SKILL_MD
    if "--skill-md" in argv:
        i = argv.index("--skill-md")
        if i + 1 >= len(argv):
            print(json.dumps({"error": "--skill-md given with no path"}))
            sys.exit(1)
        skill_md = argv[i + 1]
        del argv[i:i + 2]
    args = [a for a in argv if a != "--quiet"]
    if not args:
        print(json.dumps({"error": "usage: check_skill_honesty.py <savegame_dir> [--quiet] [--skill-md PATH]"}))
        sys.exit(1)
    sg = args[0]
    if not os.path.isdir(sg):
        print(json.dumps({"error": f"savegame dir not found: {sg}"}))
        sys.exit(1)
    if not os.path.isfile(skill_md):
        print(json.dumps({"error": f"SKILL.md not found at {skill_md}"}))
        sys.exit(1)

    skill_text = open(skill_md, encoding="utf-8").read()

    honesty_fail, honesty_notes = check_honesty(sg, skill_text)
    reach_fail, reach_notes = check_reachability(skill_text)

    print("=" * 72)
    print("SKILL HONESTY CHECK -- do the docs agree with the code?")
    print(f"checking: {skill_md}")
    print("=" * 72)
    if not quiet:
        print("\nCapabilities (probed by running, not by reading):")
        for n in honesty_notes:
            print(n)
        print("\nReachability:")
        for n in reach_notes:
            print(n)

    if honesty_fail:
        print("\n" + "!" * 72)
        print("FAILURES -- docs denying what the code does, or capabilities never wired in:")
        print("!" * 72)
        for f in honesty_fail:
            print(f"\n  {f['capability'].upper()}")
            print(f"    {f['evidence_it_works']}")
            for c in f["stale_claims"]:
                print(f"      {c}")

    if reach_fail:
        print("\n" + "!" * 72)
        print("UNREACHABLE -- present in the skill, invisible to a session:")
        print("!" * 72)
        for f in reach_fail:
            print(f"    {f}")

    print("\n" + "-" * 72)
    print("What the disk GENUINELY cannot answer (verified, not probeable):")
    for h in HUMAN_ONLY:
        print(f"  - {h}")
    print("-" * 72)

    total = len(honesty_fail) + len(reach_fail)
    if total:
        print(f"\nFAIL: {len(honesty_fail)} stale claim(s), {len(reach_fail)} unreachable file(s).")
        print("Fix the DOC, not the probe -- the probe just ran and got the data.")
        sys.exit(1)
    print("\nPASS: every capability the code has, the docs admit to. Nothing orphaned.")
    sys.exit(0)


if __name__ == "__main__":
    main()
