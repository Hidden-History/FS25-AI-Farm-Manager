"""
Fail loudly when a farm's sanctum claims something its own savegame contradicts.

Usage: python3 check_sanctum_freshness.py <savegame_dir> [--sanctum DIR] [--quiet]
Exit 0 = the sanctum agrees with the save. Exit 1 = it has drifted.
Run it at the start of every briefing -- it is fast (no --debug pass).

WHY THIS EXISTS
---------------
The skill had three guards and all were green while the farm's memory described a
farm that no longer existed. The first briefing ever run found FOUR stale claims in
one sanctum (F-028):

    creed.md    "Interest: UNKNOWN... you have never borrowed"
                -> the player had borrowed, and the rate was derived at 4.0000%
    creed.md    "Field 71 -- OAT -- HARVEST_READY"
                -> harvested
    creed.md    "no seeder, no tillage, no sprayer"
                -> two plows and a baler bought that morning
    directives  "Establish the real interest rate -- active (BLOCKING)"
                -> answered

check_skill_honesty.py checks the SKILL: stale claims in SKILL.md, orphaned files,
unwired capabilities, digest size. It never looked at the sanctum. **We guarded the
map and not the territory.**

The worst was the interest rate: creed.md is read FIRST, every session -- it sets the
voice. The 4% went into config.json and never into the creed, so every future briefing
would have opened by announcing it didn't know a rate it had already derived. A stale
creed is worse than a stale parser.

THE DISTINCTION THAT DECIDES EVERYTHING
---------------------------------------
    HISTORICAL facts CANNOT go stale. "At onboarding we owned 18 parcels and held
    $1,000,000" describes a MOMENT. It is true forever, and cash being different today
    does not make it wrong. Never probe these.

    CURRENT-STATE claims ALWAYS go stale. "The fleet has no sprayer", "field 71 is
    ripe", "the rate is unknown" -- each is a claim about a moving target.

So the real fix was architectural, and this guard is the smaller half: the sanctum
should hold what the save CANNOT (decisions, history, doctrine, the anchor) and never
mirror what it already knows. Live state belongs in farm_snapshot.py, read fresh. What
remains here is the handful of current-state claims a sanctum legitimately makes.

RULES THIS FILE FOLLOWS (each one paid for -- see FRICTION-LOG.md)
-----------------------------------------------------------------
  * THE PROBES ARE THE SPEC. Prose is checked against running code, never the reverse.
  * A probe must be able to FAIL. The wiring probes' first draft could only fire when a
    probe SUCCEEDED, so it would have passed happily on an empty digest -- a check that
    cannot fail is absence dressed as data, in the tool built to prevent exactly that.
  * CHECK THE YARDSTICK. A size probe once fired convincingly against a COMPACTED
    output and called a perfectly good digest bloated: a measurement looking like
    evidence. Probe against the right thing, and say what you measured.
  * STALE, UNVERIFIABLE and FRESH are three different answers. "I couldn't check" must
    never read as "it's fine" -- that is F-001 exactly, one level up.
"""
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")


def run_parser(script, args):
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script)] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


# --- Probes. Each returns (verdict, detail).
#     verdict: "fresh" | "stale" | "unverifiable"
#     "unverifiable" is NOT a pass -- it is reported separately and loudly, because a
#     check that quietly downgrades to "fine" when it cannot run is the defect.

def probe_interest_rate(sg, sanctum, farm_id=1):
    """THE ONE THAT ACTUALLY BROKE. The rate is derivable the moment a real loan
    exists: the official manual (p.8) says loan interest is paid "at the end of each
    month" -- once per PERIOD, not accrued per day -- and the finance screen shows
    "the current month and the previous four months". farms.xml's <finances> carries
    that same window as <stats day="N"> blocks: day="N" is the per-MONTH finance-
    column index (0 = current month, 1..4 = previous months), NOT a calendar day. A
    year is always 12 months regardless of daysPerPeriod, so
    rate = one month's charged interest * 12 / loan. Billing frequency (once per
    month) is manual-verified; the FLAT-monthly amount this formula assumes is the
    standard convention and matches all current evidence, but is not yet empirically
    confirmed on a non-default calendar (daysPerPeriod != 1) -- see
    references/game-guide/finances.md for the full derivation and its evidence
    boundary.

    NOTE the trap that hid this for hours: <finances> holds MULTIPLE <stats> blocks.
    findtext('.//loanInterest') returns the FIRST (day 0, which reads 0.00) and looks
    exactly like "no interest charged". That is F-002's first-match trap; iterate to
    the first NONZERO block -- the most recent month that actually charged interest.

    CAVEAT: this pairs the CURRENT loan with a charge that may be up to 4 months old
    (the first nonzero block can be day 1-4, not just day 0). If the loan changed
    since that month, charged*12/loan is wrong. farms.xml exposes no per-month
    historical loan/principal snapshot this skill has found, so that can't be
    cheaply detected here -- this derivation assumes the loan was constant over the
    charged month. Not checked; not silently assumed safe either -- flagged."""
    farms = os.path.join(sg, "farms.xml")
    if not os.path.isfile(farms):
        return "unverifiable", "farms.xml not found"
    try:
        root = ET.parse(farms).getroot()
    except ET.ParseError as e:
        return "unverifiable", f"farms.xml unparseable: {e}"

    farm = None
    for farm_elem in root.iter("farm"):
        try:
            if int(farm_elem.get("farmId", "")) == farm_id:
                farm = farm_elem
                break
        except ValueError:
            continue
    if farm is None:
        return "unverifiable", f"farm_id {farm_id} not found in farms.xml"

    loan = float(farm.get("loan") or 0)
    if not loan:
        return "unverifiable", ("no loan outstanding, so the game charges nothing and the rate "
                                "cannot be derived. NOT evidence of a 0% rate.")

    # Scoped to THIS farm's <stats> only -- a document-wide root.iter("stats") scans
    # every farm on a multi-farm save and can pair this farm's loan with another
    # farm's charged interest (M1).
    charged = 0.0
    for stats in farm.iter("stats"):
        v = stats.findtext("loanInterest")
        if v and float(v):
            charged = abs(float(v))
            break
    if not charged:
        return "unverifiable", (f"loan of ${loan:,.0f} exists but no interest charged yet -- no "
                                f"in-game time has passed. NOT evidence of a 0% rate.")

    derived = charged * 12 / loan

    cfg = os.path.join(sanctum, "config.json")
    claimed = None
    try:
        with open(cfg) as f:
            conf = json.load(f)
        # The rate may live under a notional-budget rule, but a farm can care about the
        # rate WITHOUT running one -- so fall back to top-level. Checking only the nested
        # path made every no-notional-budget farm report a permanent false STALE, which
        # trains sessions to ignore this probe (found at Parzival's Farm onboarding,
        # 2026-07-16). Nested wins when both are set: it's the more specific claim.
        claimed = (((conf.get("notional_budget") or {}).get("debt") or {})
                   .get("interest_rate_annual"))
        if claimed is None:
            claimed = conf.get("interest_rate_annual")
    except (OSError, json.JSONDecodeError):
        pass

    creed = read(os.path.join(sanctum, "identity", "creed.md")) or ""
    creed_denies = bool(re.search(r"interest[^.\n]{0,80}(UNKNOWN|never borrowed|will not invent)",
                                  creed, re.I))

    problems = []
    if claimed is None:
        problems.append(f"config.json records no interest_rate_annual, but the save derives "
                        f"{derived:.4%}")
    elif abs(claimed - derived) > 0.0001:
        problems.append(f"config.json says {claimed:.4%}, the save derives {derived:.4%}")
    if creed_denies:
        problems.append("creed.md still says the rate is UNKNOWN / never borrowed -- and the "
                        "creed is what a session reads FIRST")
    if problems:
        return "stale", "; ".join(problems)
    return "fresh", (f"{derived:.4%} derived from ${charged:,.2f} charged on a ${loan:,.0f} loan "
                     f"(assumes the loan was unchanged over the charged month)")


def probe_owned_land(sg, sanctum, farm_id=1):
    """Owned parcels/hectares are a current-state claim the sanctum legitimately keeps
    (it's the debt's basis and moves only on a land trade). Probe it.

    Threads --farm-id through to read_farmland_areas.py (M8) -- it defaults to farm_id=1
    internally, so leaving this unpassed would silently describe farm 1 even when the
    caller asked about a different farm.

    Also passes --mods-dir explicitly, read from THIS probe's own sanctum/config.json.
    Without it, read_farmland_areas.py falls back to its OWN default lookup: walking up
    from ITS OWN script location for a sanctum/config.json sibling -- which ignores this
    probe's --sanctum override entirely and fails whenever the layout isn't that
    coincidental default (confirmed failing live against a real savegame)."""
    cfg = os.path.join(sanctum, "config.json")
    conf = {}
    try:
        with open(cfg) as f:
            conf = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    mods_dir = (conf.get("paths") or {}).get("mods_dir")
    if not mods_dir or not os.path.isdir(mods_dir):
        return "unverifiable", ("sanctum/config.json has no usable paths.mods_dir -- "
                                "read_farmland_areas.py needs it to decode the map's "
                                "ownership raster")

    d = run_parser("read_farmland_areas.py",
                    [sg, "--farm-id", str(farm_id), "--mods-dir", mods_dir])
    if not d or "error" in d:
        return "unverifiable", f"read_farmland_areas.py: {(d or {}).get('error', 'failed')}"
    owned = d.get("owned") or {}
    count, ha = owned.get("count"), owned.get("total_area_ha")
    if count is None or ha is None:
        return "unverifiable", "decoder returned no owned count/area"

    problems = []
    ids = set((conf.get("owned_fields") or {}).get("field_ids") or [])
    if ids and ids != set(owned.get("field_ids") or []):
        problems.append(f"config.json owned_fields has {len(ids)} ids; the save says "
                        f"{len(owned.get('field_ids') or [])}")

    creed = read(os.path.join(sanctum, "identity", "creed.md")) or ""
    m = re.search(r"\*\*(\d+) parcels\s*[—-]\s*([\d.]+) ha", creed)
    if m:
        c_count, c_ha = int(m.group(1)), float(m.group(2))
        if c_count != count:
            problems.append(f"creed.md says {c_count} parcels, the save says {count}")
        if abs(c_ha - ha) > 0.05:
            problems.append(f"creed.md says {c_ha} ha, the save says {ha}")
    if problems:
        return "stale", "; ".join(problems)
    return "fresh", f"{count} parcels, {ha} ha -- matches the save"


def probe_no_live_state_in_creed(sg, sanctum):
    """creed.md is identity and history. It must not assert CURRENT state -- that is
    the whole of F-028. This probe doesn't check whether such a claim is true; it
    checks that it isn't there at all, because a true one rots by tomorrow.

    Deliberately narrow: only patterns that are unambiguously live state. A creed
    saying "we own 18 parcels" is fine (probe_owned_land checks it). A creed naming a
    ripe field is not."""
    creed = read(os.path.join(sanctum, "identity", "creed.md"))
    if creed is None:
        return "unverifiable", "creed.md not found"
    live = {
        r"HARVEST_READY": "a crop's ripeness",
        r"weedState\s*\d": "a weed level",
        r"\bno (seeder|sprayer|tillage)\b": "a fleet gap",
        r"growthState\s*\d": "a growth stage",
    }
    hits = []
    for pat, what in live.items():
        for m in re.finditer(pat, creed, re.I):
            line = creed[:m.start()].count("\n") + 1
            hits.append(f"creed.md:{line} asserts {what} ({m.group(0)!r})")
    if hits:
        return "stale", ("; ".join(hits) + " -- live state in a 'rarely edited' file rots by "
                         "tomorrow. It belongs in farm_snapshot.py, read fresh.")
    return "fresh", "creed.md asserts no live state -- identity and history only"


def probe_notional_offset(sg, sanctum, farm_id=1):
    """The offset is arithmetic, not an opinion: notional = farms.xml@money - offset.
    Verify it still computes, and surface the balance so a briefing can't quote a
    figure nobody checked. Historical anchors are NOT probed -- they describe a moment.

    Selects the farm by farmId (M8) -- `.find(".//farm")` grabbed the first <farm> in
    document order, the same multi-farm bug M1 fixed in probe_interest_rate. On a
    multi-farm save that could compute the notional balance from the WRONG farm's
    cash."""
    cfg = os.path.join(sanctum, "config.json")
    try:
        with open(cfg) as f:
            nb = json.load(f).get("notional_budget") or {}
    except (OSError, json.JSONDecodeError) as e:
        return "unverifiable", f"config.json unreadable: {e}"
    if not nb.get("enabled"):
        return "fresh", "no notional-budget rule on this farm"
    offset = nb.get("offset")
    if offset is None:
        return "unverifiable", "notional_budget.enabled but no offset recorded"

    farms = os.path.join(sg, "farms.xml")
    try:
        root = ET.parse(farms).getroot()
    except (OSError, ET.ParseError) as e:
        return "unverifiable", f"could not read farms.xml: {e}"

    farm = None
    for farm_elem in root.iter("farm"):
        try:
            if int(farm_elem.get("farmId", "")) == farm_id:
                farm = farm_elem
                break
        except ValueError:
            continue
    if farm is None:
        return "unverifiable", f"farm_id {farm_id} not found in farms.xml"

    try:
        cash = float(farm.get("money"))
    except (TypeError, ValueError) as e:
        return "unverifiable", f"could not read farm_id {farm_id}'s money attribute: {e}"

    notional = cash - offset
    if notional < 0:
        # Not stale -- the arithmetic is fine and the answer is bad. The creed COMMITS
        # to saying so bluntly, so report it rather than let a briefing miss it.
        return "fresh", (f"notional ${notional:,.2f} -- NEGATIVE. Real ${cash:,.2f} - offset "
                         f"${offset:,.2f}. The creed commits to saying this bluntly.")
    return "fresh", f"notional ${notional:,.2f} (real ${cash:,.2f} - offset ${offset:,.2f})"


def probe_directive_premises(sg, sanctum, farm_id=1):
    """A directive is a DECISION, so its status is the player's to change -- not
    something to probe. But a directive whose PREMISE the save contradicts is a real
    rot: 'we own no tillage' stops being a reason once tillage is bought.

    Threads --farm-id through to read_vehicles.py (M8) -- it defaults to farm_id=1
    internally, so leaving this unpassed would silently describe farm 1's fleet even
    when the caller asked about a different farm."""
    d = read(os.path.join(sanctum, "identity", "directives.md"))
    if d is None:
        return "unverifiable", "directives.md not found"
    v = run_parser("read_vehicles.py", [sg, "--farm-id", str(farm_id)])
    if not v or "error" in v:
        return "unverifiable", f"read_vehicles.py: {(v or {}).get('error', 'failed')}"
    specs = set()
    for veh in (v.get("vehicles") or []):
        specs.update(veh.get("specializations") or [])

    problems = []
    # Only claims that are checkable from the fleet's own runtime state (F-026: never
    # infer a machine's role from its name).
    for spec, phrase in (("sower", r"no seeder"), ("cultivator", r"no tillage"),
                         ("plow", r"no tillage"), ("sprayer", r"no sprayer")):
        if spec in specs and re.search(phrase, d, re.I):
            problems.append(f"directives.md says {phrase!r} but the fleet has a {spec}")
    if problems:
        return "stale", "; ".join(sorted(set(problems)))
    return "fresh", "no directive premise contradicted by the fleet"


def main():
    argv = sys.argv[1:]
    quiet = "--quiet" in argv
    sanctum = None
    if "--sanctum" in argv:
        i = argv.index("--sanctum")
        if i + 1 >= len(argv):
            print(json.dumps({"error": "--sanctum requires a path"}))
            sys.exit(1)
        sanctum = argv[i + 1]
        del argv[i:i + 2]
    farm_id = 1
    if "--farm-id" in argv:
        i = argv.index("--farm-id")
        if i + 1 >= len(argv):
            print(json.dumps({"error": "--farm-id requires a value"}))
            sys.exit(1)
        try:
            farm_id = int(argv[i + 1])
        except ValueError:
            print(json.dumps({"error": f"--farm-id must be an integer, got {argv[i + 1]!r}"}))
            sys.exit(1)
        del argv[i:i + 2]
    args = [a for a in argv if a != "--quiet"]
    if not args:
        print(json.dumps({"error": "usage: check_sanctum_freshness.py <savegame_dir> "
                                   "[--sanctum DIR] [--farm-id N] [--quiet]"}))
        sys.exit(1)
    sg = args[0]
    if not os.path.isdir(sg):
        print(json.dumps({"error": f"savegame dir not found: {sg}"}))
        sys.exit(1)
    if sanctum is None:
        sanctum = os.path.join(os.getcwd(), "sanctum")
    if not os.path.isdir(sanctum):
        print(json.dumps({"error": f"sanctum not found: {sanctum}. Pass --sanctum, or run "
                                   f"from the project directory."}))
        sys.exit(1)

    # Built here (not module-level) so the farm-specific probes can close over
    # --farm-id (M1, M8). probe_no_live_state_in_creed reads no farm-specific save
    # data (creed.md only), so it takes no farm_id.
    probes = [
        ("interest rate", lambda sg_, sanctum_: probe_interest_rate(sg_, sanctum_, farm_id)),
        ("owned land", lambda sg_, sanctum_: probe_owned_land(sg_, sanctum_, farm_id)),
        ("creed carries no live state", probe_no_live_state_in_creed),
        ("notional offset", lambda sg_, sanctum_: probe_notional_offset(sg_, sanctum_, farm_id)),
        ("directive premises", lambda sg_, sanctum_: probe_directive_premises(sg_, sanctum_, farm_id)),
    ]

    stale, unverifiable, fresh = [], [], []
    for name, probe in probes:
        try:
            verdict, detail = probe(sg, sanctum)
        except Exception as e:  # a probe that crashes must not read as a pass
            verdict, detail = "unverifiable", f"probe raised {type(e).__name__}: {e}"
        {"stale": stale, "unverifiable": unverifiable, "fresh": fresh}[verdict].append((name, detail))

    print("=" * 74)
    print("SANCTUM FRESHNESS -- does the farm's memory still match its save?")
    print(f"sanctum: {sanctum}")
    print("=" * 74)
    if not quiet:
        for n, d in fresh:
            print(f"  [fresh] {n}: {d}")

    if unverifiable:
        print("\n  COULD NOT CHECK -- this is NOT a pass. An unchecked claim is unknown,")
        print("  not fine. That distinction is the whole point (F-001).")
        for n, d in unverifiable:
            print(f"    [?] {n}: {d}")

    if stale:
        print("\n" + "!" * 74)
        print("STALE -- the sanctum contradicts the save:")
        print("!" * 74)
        for n, d in stale:
            print(f"\n  {n.upper()}\n    {d}")
        print("\n  Fix the SANCTUM, not the probe -- the probe just read the save.")
        print("  And ask whether the claim should live in a permanent file at all: if it")
        print("  could be different tomorrow, it belongs in farm_snapshot.py (F-028).")

    print("\n" + "-" * 74)
    print(f"  {len(fresh)} fresh · {len(stale)} stale · {len(unverifiable)} unverifiable")
    print("-" * 74)
    sys.exit(1 if stale else 0)


if __name__ == "__main__":
    main()
