"""
Build the briefing digest: "what does the manager need to know right now,"
in a few KB -- not a data dump (that's collect_state.py, or run a parser
directly for its full curated output).

Usage: python3 farm_snapshot.py <savegame_dir> [--farm-id N] [--verbose]

--verbose ships every row. The default ships only what THIS farm can act on --
the crops it grows, the inputs whose price actually moves. Nothing is deleted,
and the compact output names what it left out and why.

Composes from the EXISTING parsers (via subprocess, same pattern as
collect_state.py) -- it does NOT re-implement any XML parsing. That's a hard
rule in SKILL.md: parallel implementations of the same parsing logic drift
apart, and this session's whole FRICTION-LOG.md is a record of what drifting
parsers cost. If a fact isn't already surfaced by an existing parser, it
doesn't belong in this script until a parser surfaces it.

DESIGN RULE (the one that matters most, learned expensively this session --
see FRICTION-LOG.md F-001/F-002/F-003): it must be impossible for this
digest to imply something false by omission. Every top-level section below
carries a `status` field ("ok" / "unavailable" / "unknown_by_design") and
is present even when its data isn't -- a missing/errored source becomes a
visible "unavailable" section with the parser's own error message attached,
never a silently absent key. Concretely, two things this digest will NEVER
do:
    1. Print a field/contract/vehicle count as if it were the player's
       without the parser having actually confirmed ownership (see
       `field_state` below -- fields.xml has no farmId, ownership is
       genuinely NOT derivable, and this digest says so explicitly rather
       than printing "122 fields" next to farm data and letting a reader
       assume they're all the player's, which is exactly how F-001/F-002
       happened).
    2. Quote a savegame fact without also quoting how old that fact is --
       and never claim or imply a staleness BOUND that doesn't exist.
       CORRECTED 2026-07-16 (FRICTION-LOG.md F-023): an earlier version of
       this script (and of read_career.py, since fixed) claimed
       autoSaveInterval "bounds staleness while actively playing" and, when
       a 13-minute inode watch (F-021) saw no autosave fire, concluded the
       game must be paused/idle. Both claims were wrong, and the second was
       never observed -- it was inferred from silence and stated as fact,
       the exact same failure shape as F-001/F-002 in a new costume. What
       actually happens: FS25 defers the autosave to the next time the
       player opens the map/menu AFTER the interval has elapsed, so the
       interval only says when a save becomes DUE, not when it's written --
       it bounds nothing, at any time, playing or not. A save can be
       arbitrarily old mid-session with the player actively farming the
       whole time. The ONLY honest freshness signal is the measured mtime
       -- see `save_freshness` below, which reuses read_career.py's
       `source_mtime_iso`/`source_age_seconds` and states an age, never a
       cause (paused, idle, crashed) for that age.

UNITS (this session's other recurring trap -- 5 separate unit bugs found and
fixed today, see FRICTION-LOG.md): every numeric value surfaced here already
comes out of its source parser in human-legible units (minutes-of-day clock
already converted to "HH:MM", playTime already converted from raw minutes,
etc.). This script does no unit conversion of its own except the trivial
ms-of-day arithmetic for forecast/contract deadlines, which reuses the same
absolute-timeline approach read_environment.py documents and verifies.

INVENTORY (added 2026-07-24): the farm's HOLDINGS -- grain in vehicles,
contents of silos -- valued at today's price. This digest previously had
sections for money, land, field_state, fleet and contracts and NO inventory at
all, which meant it tracked what the farm OWNS and what it OWES but not what
it had PRODUCED. On a farm whose whole job is turning crops into money against
a debt, that was the middle of the pipeline missing: 76,772 L of OAT and
46,934 L of CANOLA were sitting in two combines worth ~$63.7k, and the skill
could not see a litre of it -- found only because the player said to look.
Composed from read_vehicles.py (cargo), read_placeables.py (storage) and
read_fill_prices.py (economy.xml's per-period curve), per the no-parallel-
parsers rule above. Two things it deliberately will NOT do:
    1. Price anything from read_prices.py's meanValue -- 0.000000 on every
       node of this never-traded farm, which would value the grain at nothing
       (F-001's exact shape).
    2. Recommend holding on the price spread. It reports the peak and the
       gross gain and stops, because carrying cost dominates that spread here
       and the arithmetic is farm-specific doctrine (sanctum/identity/creed.md), not
       portable skill logic. A spread that looks great is not a decision.

THE BUY SIDE (added 2026-07-16): inventory answers "what have we produced and
what is it worth" -- the SELL side. `input_costs`, `weeds`, `equipment_market`
and `equipment_gaps` answer the other half: what the farm must BUY, what it
cannot currently do, and what either costs.

CROPS ARE A SELL CALENDAR; INPUTS ARE A BUY CALENDAR, and one code path must
never treat them alike -- for a crop a high price is good, for an input a LOW
price is good, and a generic "find the best price" helper would silently
invert the advice and recommend buying seed at its annual peak. So the two
sides never share a code path: inventory reads read_fill_prices.py's `peak`,
and build_input_costs takes an explicit `min`. Which fillTypes are inputs is
resolved from the GAME's own data by read_game_defs.py (sprayTypes + the three
engine-level names), never hardcoded here -- this save's map adds its own
ANHYDROUS spray input and it is picked up with no code change.

Two things deliberately NOT computed, because they would be fabrication:
    1. A weed yield-loss figure. weedState is an ordinal from the map's weed
       info-layer; nothing in the map or the install's loose XML relates it to
       a yield penalty. The level, the herbicide price and whether the farm
       even owns a sprayer are reported; the judgement is the player's.
    2. A farm-wide seed bill. The per-crop rate IS derivable (the game's own
       <seeding litersPerSqm>) and is reported per hectare -- but multiplying
       it by the farm's area needs a cropping plan, which is the player's
       decision and not something a seed rate can reveal.

CAPABILITY CROSS-CHECK (F-026): a list of "12 contracts expire today" is
true and nearly useless if the farm can only act on 2 of them. This script
names actionable contracts concretely -- but ONLY when it can back that
claim with real data:
    1. Equipment: read_vehicles.py's `specializations` field (each owned
       vehicle's own direct-child tag names from vehicles.xml -- e.g. a
       combine harvester's runtime state includes a <combine> element) is
       checked against CAPABILITY_REQUIREMENTS below. Confirmed the naive
       alternative (guessing equipment role from filename/mod name) would
       have been actively wrong in this save: a vehicle named
       "...northStar1230FBEditedByStevie..." reads like a flatbed trailer
       ("FB") but its actual specialization is `cutter` (a header). This
       script never infers role from a name.
    2. For harvestMission specifically, equipment alone isn't enough --
       fields.xml is cross-checked directly for that mission's `field_id`
       having `crop_state == "ready"` before it's called actionable. NOT groundType:
       that is the terrain texture and stays HARVEST_READY after a field is cut.
       A contract existing is not proof the field is ready.
    3. CAPABILITY_REQUIREMENTS is deliberately NOT exhaustive. A mission
       type with no entry gets verdict "unknown", not a guess either way --
       see assess_mission_capability()'s docstring.
This deliberately does NOT resolve `$moddir$` mod zips for exact fruit-type
compatibility, working width, etc. -- that's a separate, unduplicated effort
(F-019/read_store_prices.py). It only answers "does this save's own runtime
data say the farm owns equipment with the specialization this mission type
needs," which is enough to rule capability IN or OUT for what it does check.
"""
import os
import sys
import json
import subprocess

SCRIPT_DIR = os.path.dirname(__file__)

# --verbose ships every row; the default ships what THIS farm can act on.
# The digest once grew to 2.0x the size of the full snapshot it exists to
# condense -- every capability justified, the sum not. A briefing that must be
# skimmed is a dump with better manners. collect_state.py already proved the
# pattern: compact by default, nothing deleted, everything one flag away, and
# the compact output says so.
VERBOSE = False

# Weather types considered "notable" for a briefing lead -- i.e. worth
# surfacing ahead of ordinary SUN/CLOUDY. Not exhaustive by construction;
# anything encountered outside this set still shows up as the plain "next
# forecast change" fallback, never silently dropped.
NOTABLE_WEATHER_TYPES = {"HAIL", "RAIN", "SNOW", "TWISTER"}

# Calendar order, mirroring read_fill_prices.PERIODS. Used only to say "the
# cheapest period is N periods away"; the price data itself always comes from
# that parser, never re-derived here.
PERIOD_ORDER = [
    "EARLY_SPRING", "MID_SPRING", "LATE_SPRING",
    "EARLY_SUMMER", "MID_SUMMER", "LATE_SUMMER",
    "EARLY_AUTUMN", "MID_AUTUMN", "LATE_AUTUMN",
    "EARLY_WINTER", "MID_WINTER", "LATE_WINTER",
]

# The generic seed fillType. NOT a classification of what counts as an input
# (read_game_defs.py resolves that from the game's own data) -- this is only
# the key used to look up seed's price, and it is the fillType the game's own
# <seeding> mechanic consumes for the crops that carry a litersPerSqm rate.
SEED_FILL_TYPE = "SEEDS"
HERBICIDE_FILL_TYPE = "HERBICIDE"

# Mission type -> vehicle specialization tag(s) (from vehicles.xml's own
# runtime state, see read_vehicles.py's `specializations` field, F-026) the
# farm needs ALL of to plausibly perform this contract. Deliberately NOT
# exhaustive -- only mission types where a specialization tag maps cleanly
# and unambiguously to what that contract requires. A mission type absent
# from this map gets an "unknown" capability verdict, never a guess.
CAPABILITY_REQUIREMENTS = {
    "harvestMission": {"combine", "cutter"},
    "baleMission": {"baler"},
    "baleWrapMission": {"baler"},
    "fertilizeMission": {"sprayer"},
    "herbicideMission": {"sprayer"},
    "hoeMission": {"cultivator"},
    # treeTransportMission, deadwoodMission, destructibleRockMission: no
    # verified specialization mapping -- left out on purpose, not guessed.
}


def find_config(explicit):
    """Locate a config.json carrying the 'paths' block that store/def lookups
    need (install_dir, mods_dir).

    Only the sections that price NEW equipment or read the game's own
    definitions need this; everything else works from the savegame alone. If
    it isn't found, those sections report themselves unavailable WITH this
    reason -- they never silently degrade to a partial answer, and the rest of
    the digest is unaffected.

    Searched in order: --config, then the conventional sanctum/config.json
    relative to cwd (this skill's documented convention), then relative to the
    project root two levels above this script -- so the digest still works when
    run from somewhere other than the project directory, which is the common
    case for a subprocess and was a real failure mode (read_store_prices'
    probe reported 'not answerable' purely because of cwd).
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.append(os.path.join("sanctum", "config.json"))
    candidates.append(os.path.abspath(
        os.path.join(SCRIPT_DIR, "..", "..", "..", "..", "sanctum", "config.json")
    ))
    for c in candidates:
        if c and os.path.isfile(c):
            return c, None
    return None, (
        "no config.json with a 'paths' block found (looked in: "
        f"{[c for c in candidates if c]}). Pass --config PATH. Only the sections that "
        "need the game INSTALL (new-equipment prices, the game's own fillType/seed "
        "definitions) are affected; savegame-only sections are unaffected."
    )


def call(script, savegame_dir, farm_id=None, extra_args=None):
    """Run a parser CLI and return (parsed_json_or_None, error_or_None).
    error is set for both "couldn't even get JSON back" and "parser itself
    reported {"error": ...}" -- callers should always check it before
    trusting the first return value."""
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script), savegame_dir]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    if extra_args:
        cmd += extra_args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None, f"{script} timed out after 30s"

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, (
            f"{script} produced non-JSON output (exit {result.returncode}): "
            f"{(result.stderr or result.stdout)[:300]}"
        )

    if isinstance(data, dict) and "error" in data:
        return data, data["error"]
    return data, None


def unavailable(reason):
    return {"status": "unavailable", "reason": reason}


def ms_to_clock(ms_of_day):
    ms_of_day = ms_of_day % 86400000
    total_minutes = ms_of_day // 60000
    return f"{int(total_minutes // 60):02d}:{int(total_minutes % 60):02d}"


def build_when(env):
    data, err = env
    if err:
        return unavailable(f"read_environment.py: {err}")

    current = data.get("current_weather")
    upcoming = data.get("upcoming_forecast") or []

    next_notable = None
    for entry in upcoming:
        if entry.get("type") in NOTABLE_WEATHER_TYPES:
            next_notable = entry
            break
    next_change = upcoming[0] if upcoming else None

    return {
        "status": "ok",
        "in_game_day": data.get("current_day"),
        "clock": data.get("clock"),
        "season": data.get("season"),
        "current_weather": (
            {
                "type": current.get("type"),
                "until_day": current.get("end_day"),
                "until_clock": current.get("end_clock"),
            }
            if current else None
        ),
        "current_weather_note": None if current else data.get("current_weather_note"),
        "next_change": (
            {
                "type": next_change.get("type"),
                "starts_day": next_change.get("start_day"),
                "starts_clock": next_change.get("start_clock"),
            }
            if next_change else None
        ),
        "next_notable_event": (
            {
                "type": next_notable.get("type"),
                "starts_day": next_notable.get("start_day"),
                "starts_clock": next_notable.get("start_clock"),
                "note": "worth leading a briefing with -- disruptive weather type",
            }
            if next_notable else {
                "type": None,
                "note": f"none of {sorted(NOTABLE_WEATHER_TYPES)} found in the "
                        f"{len(upcoming)}-entry forecast window read_environment.py returns "
                        "-- doesn't mean none is coming, just none visible yet",
            }
        ),
        "day_time_unit_confidence": data.get("day_time_unit_confidence"),
    }


def build_save_freshness(career, savegame_dir):
    data, err = career
    if not err:
        return {
            "status": "ok",
            "source": data.get("source"),
            "source_mtime_iso": data.get("source_mtime_iso"),
            "source_age_seconds": data.get("source_age_seconds"),
            "note": (
                "source_age_seconds (measured mtime) is the ONLY honest freshness signal "
                "-- state it as 'as of N minutes ago' and stop there. autoSaveInterval "
                "bounds NOTHING (FRICTION-LOG.md F-023): FS25 defers the actual write to "
                "the next map/menu open after the interval elapses, so a save can be "
                "arbitrarily older than the interval with the player actively playing the "
                "whole time. Do not infer a cause (paused, idle, crashed) for any gap --"
                " that was tried once, stated as fact, and was wrong."
            ),
        }

    # Fallback: read_career.py failed, but we can still get a raw filesystem
    # mtime directly (os.path.getmtime is a stat call, not XML parsing --
    # doesn't violate the "don't re-implement parsers" rule) off any save
    # file that's likely present, so freshness isn't silently lost just
    # because careerSavegame.xml specifically had a problem.
    for fallback_name in ("farms.xml", "environment.xml"):
        fallback_path = os.path.join(savegame_dir, fallback_name)
        if os.path.isfile(fallback_path):
            import datetime
            import time
            mtime_epoch = os.path.getmtime(fallback_path)
            return {
                "status": "partial",
                "source": fallback_path,
                "source_mtime_iso": datetime.datetime.fromtimestamp(mtime_epoch).isoformat(timespec="seconds"),
                "source_age_seconds": round(time.time() - mtime_epoch, 1),
                "note": (
                    f"read_career.py was unavailable ({err}) -- fell back to this file's "
                    "raw filesystem mtime instead of careerSavegame.xml's own reading. "
                    "Same caveat applies: this measured age is the only honest freshness "
                    "signal there is (FRICTION-LOG.md F-023) -- autoSaveInterval bounds "
                    "nothing and no cause (paused/idle/crashed) should be inferred from a gap."
                ),
            }

    return unavailable(f"read_career.py: {err}; no fallback save file found either")


def build_money(economy):
    data, err = economy
    if err:
        return unavailable(f"read_economy.py: {err}")
    return {
        "status": "ok",
        "farm_name": data.get("farm_name"),
        "cash": data.get("cash"),
        "loan": data.get("loan"),
        "source": "farms.xml via read_economy.py",
        "note": "economy.xml is NOT the source (it's fillType price history only, "
                "see FRICTION-LOG.md F-001) -- never substitute it here.",
    }


def build_land(economy):
    data, err = economy
    if err:
        return unavailable(f"read_economy.py: {err}")
    land = data.get("land") or {}
    return {
        "status": "ok",
        "owned_parcel_count": land.get("owned_count"),
        "owned_parcel_ids": land.get("owned_parcel_ids"),
        "total_parcels_on_map": land.get("total_parcels"),
        "source": "farmland.xml via read_economy.py",
    }


def build_field_state(fields):
    """Ownership WAS unknowable from XML (F-004) and read_fields.py now resolves it
    by composing the GRLE decoder. Two honest states remain, and they are NOT the
    same thing: "ok" (resolved) vs "unknown_by_design" (genuinely could not be).
    Never collapse them -- and never let an unresolved state print a map-wide count
    next to farm data where it reads as the player's."""
    data, err = fields
    if err:
        return unavailable(f"read_fields.py: {err}")

    own = data.get("ownership") or {}
    total = data.get("field_count")

    if not own.get("resolved"):
        return {
            "status": "unknown_by_design",
            "total_fields_on_map": total,
            "owned_field_count": None,
            "harvest_ready_on_owned_land": None,
            "why_unresolved": own.get("why_unresolved") or own.get("source"),
            "note": (
                "MAP-WIDE count, NOT the player's. Ownership is not in fields.xml (no "
                "farmId); it is normally derived by decoding the map's GRLE raster, but "
                "that did not resolve this run (see why_unresolved). Attribute NO subset "
                "of these fields to the player. null here means unknown -- it does not "
                "mean the farm owns nothing (F-004)."
            ),
        }

    ready = data.get("harvest_ready_on_owned_land") or []
    harvested = data.get("harvested_on_owned_land") or []
    unknown_state = data.get("unknown_crop_state_on_owned_land") or []
    xc = own.get("field_purchase_cross_check") or {}
    return {
        "status": "ok",
        "total_fields_on_map": total,
        "owned_field_count": data.get("owned_field_count"),
        "owned_field_ids": data.get("owned_field_ids"),
        "owned_area_ha": own.get("owned_area_ha"),
        # The most decision-relevant line in the whole digest: a ripe crop on the
        # player's OWN ground. Empty list = checked, none ready. It is never null
        # here, because status=="ok" means we genuinely know.
        "harvest_ready_on_owned_land": ready,
        # A field that is CUT is the manager's evidence the player harvested it --
        # FS25 records no harvest event, so this state IS the signal. Diff it
        # against the last session to date it.
        "harvested_on_owned_land": harvested,
        "unknown_crop_state_on_owned_land": unknown_state,
        "ownership_source": own.get("source"),
        "ownership_gates_passed": own.get("gates_passed"),
        "ownership_cross_check_matches_fieldPurchase": xc.get("match"),
        "note": (
            "Ownership resolved and gate-checked: the decode's parcel-id set equals "
            "farmland.xml's, its total area equals the map's declared size, and its "
            "computed land cost matches farms.xml's own <fieldPurchase>. "
            "total_fields_on_map is still map-wide -- quote owned_field_count."
        ),
    }


def build_fleet(vehicles):
    data, err = vehicles
    if err:
        return unavailable(f"read_vehicles.py: {err}")

    owned = data.get("vehicles") or []
    WEAR_ATTENTION_THRESHOLD = 0.5  # fraction, i.e. 50% worn
    needs_attention = []
    max_wear = None
    for v in owned:
        dmg = v.get("damage")
        try:
            dmg_f = float(dmg) if dmg is not None else None
        except (TypeError, ValueError):
            dmg_f = None
        if dmg_f is not None and (max_wear is None or dmg_f > max_wear):
            max_wear = dmg_f
        if dmg_f is not None and dmg_f >= WEAR_ATTENTION_THRESHOLD:
            needs_attention.append({
                "filename": v.get("filename"),
                "unique_id": v.get("unique_id"),
                "damage": dmg_f,
                "reason": f"wear >= {WEAR_ATTENTION_THRESHOLD:.0%}",
            })

    return {
        "status": "ok",
        "owned_count": data.get("owned_count"),
        "total_purchase_value": data.get("owned_total_price"),
        "max_wear_fraction": max_wear,
        "needs_attention": needs_attention,
        "note": (
            f"nothing needs attention -- max wear across the fleet is "
            f"{max_wear:.2%}" if (max_wear is not None and not needs_attention) else
            f"{len(needs_attention)} vehicle(s) at or above {WEAR_ATTENTION_THRESHOLD:.0%} wear"
            if needs_attention else "no wear data available"
        ) + (
            ". Fuel is reported by parsers as raw fillLevel (likely liters); tank "
            "capacity isn't present in vehicles.xml, so percent-full can't be computed "
            "-- not evaluated here for that reason, not because it was skipped."
        ),
        "source": "vehicles.xml via read_vehicles.py",
    }


def build_inventory(vehicles, placeables, prices):
    """What the farm is HOLDING, where, and what it's worth at today's price.

    The gap this closes: the manager tracked what the farm OWNS (fleet, land)
    and what it OWES (loan), and not what it had PRODUCED. On a farm whose job
    is turning crops into money against a debt, that was the middle of the
    pipeline missing -- 123,706 L of grain worth ~$63.7k sat in two combines
    and no briefing could see a litre of it.

    VALUED AGAINST economy.xml (via read_fill_prices.py), NOT read_prices.py's
    meanValue -- that reads 0.000000 on every node of this never-traded farm
    and would confidently report this grain as worthless. That is F-001's
    exact shape, and read_prices.py now emits null + a note precisely so
    nobody wires it in here by mistake.

    ON HOLD-VS-SELL, WHICH IS THE ONLY REASON ANYONE ASKS: this section
    reports the peak of the price curve and the gain to it, and REFUSES to
    recommend holding on that basis, because the price spread alone is a trap.
    Worked, with this save's real numbers: holding to peak gains ~+$20,040,
    and on a farm carrying the notional debt this project's creed tracks, the
    interest over those same in-game days runs several times that -- the
    percentage looks great and the decision is still wrong. The carrying cost
    is farm-specific doctrine (it lives in the sanctum, not in this portable
    skill), so this section surfaces the gross spread, states plainly that it
    is gross, and hands the decision to the doctrine rather than pre-empting
    it with a number that flatters itself.
    """
    v_data, v_err = vehicles
    p_data, p_err = placeables
    pr_data, pr_err = prices

    if v_err and p_err:
        return unavailable(
            f"no holdings source available -- read_vehicles.py: {v_err}; read_placeables.py: {p_err}"
        )

    # Merge the two holding locations into one per-fill-type picture. Each
    # source failing is recorded rather than silently contributing nothing --
    # a missing source must never read as "there's nothing there".
    holdings = {}
    sources_ok = []
    sources_failed = []

    # A source that admits its own totals are incomplete must not have them
    # presented here as if they were the whole position.
    incomplete_sources = []
    if not v_err:
        cargo_block = v_data.get("cargo_on_board") or {}
        if cargo_block.get("totals_are_complete") is False:
            incomplete_sources.append({
                "source": "read_vehicles.py",
                "reason": cargo_block.get("totals_are_complete_note"),
                "unreadable": cargo_block.get("unreadable_cargo_units"),
            })

    if not v_err:
        sources_ok.append("vehicles.xml (cargo in fill units)")
        for ft, info in ((v_data.get("cargo_on_board") or {}).get("by_fill_type") or {}).items():
            entry = holdings.setdefault(ft, {"total_litres": 0.0, "locations": []})
            entry["total_litres"] += info["total_litres"]
            for loc in info["locations"]:
                entry["locations"].append({
                    "kind": "vehicle",
                    "what": loc.get("filename"),
                    "litres": loc.get("litres"),
                })
    else:
        sources_failed.append({"source": "read_vehicles.py", "reason": v_err})

    if not p_err:
        sources_ok.append("placeables.xml (silo/storage contents)")
        for ft, info in ((p_data.get("stored_contents") or {}).get("by_fill_type") or {}).items():
            entry = holdings.setdefault(ft, {"total_litres": 0.0, "locations": []})
            entry["total_litres"] += info["total_litres"]
            for loc in info["locations"]:
                entry["locations"].append({
                    "kind": "storage",
                    "what": loc.get("where"),
                    "litres": loc.get("litres"),
                })
    else:
        sources_failed.append({"source": "read_placeables.py", "reason": p_err})

    # Price lookup. If prices are unavailable the litres are still real and
    # still reported -- with value null and a reason, never $0.
    price_by_ft = {}
    if not pr_err:
        for ft in (pr_data.get("fill_types") or []):
            price_by_ft[ft["fill_type"]] = ft

    items = []
    total_value = 0.0
    total_value_at_peak = 0.0
    value_complete = True

    for ft in sorted(holdings):
        litres = holdings[ft]["total_litres"]
        p = price_by_ft.get(ft)
        if p is None or p.get("price_per_1000l") is None:
            value_complete = False
            items.append({
                "fill_type": ft,
                "litres": round(litres, 1),
                "value_now": None,
                "value_note": (
                    f"read_fill_prices.py returned no current-period price for {ft} "
                    f"({pr_err or 'no price history for this fill type in economy.xml'}) "
                    "-- value UNKNOWN, explicitly not $0."
                ),
                "locations": holdings[ft]["locations"],
            })
            continue

        value = litres / 1000.0 * p["price_per_1000l"]
        peak = p.get("peak") or {}
        peak_value = (litres / 1000.0 * peak["price_per_1000l"]) if peak.get("price_per_1000l") else None
        total_value += value
        if peak_value is not None:
            total_value_at_peak += peak_value

        items.append({
            "fill_type": ft,
            "litres": round(litres, 1),
            "price_per_1000l_now": p["price_per_1000l"],
            "value_now": round(value, 2),
            "peak": {
                "period": peak.get("period"),
                "price_per_1000l": peak.get("price_per_1000l"),
                "on_in_game_day": peak.get("on_in_game_day"),
                "periods_until": peak.get("periods_until"),
                "value_at_peak": round(peak_value, 2) if peak_value is not None else None,
                "gain_vs_now": round(peak_value - value, 2) if peak_value is not None else None,
            },
            "locations": holdings[ft]["locations"],
        })

    # Compact the period record for the digest. The full derivation, the
    # contradicting evidence and the one-day tick test that settles it live in
    # read_fill_prices.py's own output -- a digest carries the WARNING and the
    # pointer, not the essay. What must survive the compaction: that this
    # period is derived, that it is unverified, and what the rival reading is.
    # Drop those and every price below silently becomes a fact.
    period = None
    if not pr_err:
        full = pr_data.get("current_period") or {}
        refuted = full.get("refuted_alternative_reading") or {}
        period = {
            "period": full.get("period"),
            "derived": full.get("derived"),
            "period_confidence": full.get("period_confidence"),
            "derived_from": full.get("derived_from"),
            "basis": (
                "No currentPeriod field exists in this save, so the period is DERIVED from "
                "currentDay -- but the derivation was CONFIRMED by observation: economy.xml "
                "fluctuates only the CURRENT period's cell, and the cell it moves is this one "
                f"(checked across 4 fillTypes / 40 cells). The rival reading ({refuted.get('period')}, "
                "from fixedSeasonalVisuals) is REFUTED -- that cell never moves. See "
                "read_fill_prices.py current_period for the evidence and the reusable test."
            ) if refuted.get("period") else full.get("why_not_certain"),
        }

    return {
        "status": "ok",
        "state": "holding" if items else "nothing_held",
        "total_value_now": round(total_value, 2) if (value_complete and items and not incomplete_sources) else None,
        "total_value_now_note": None if (value_complete and items and not incomplete_sources) else (
            "null because a source reported its own holdings totals as INCOMPLETE (an unreadable "
            "fill level on a real crop) -- see sources_incomplete. Any total built on it would be "
            "a floor wearing the costume of a full position."
            if incomplete_sources and items else
            "null because at least one holding could not be priced -- see each item's "
            "value_note. A partial total would read as the farm's whole position and be wrong."
            if items else
            "The farm holds nothing that could be read as cargo or stored contents. This is a "
            "CHECKED result, not a missing one -- but read holdings_caveats before treating it "
            "as proof the silos are bare."
        ),
        "total_value_at_own_peaks": (
            round(total_value_at_peak, 2) if (value_complete and items and not incomplete_sources) else None
        ),
        "gain_if_held_to_peak": (
            round(total_value_at_peak - total_value, 2)
            if (value_complete and items and not incomplete_sources) else None
        ),
        "hold_or_sell": {
            "verdict": "NOT COMPUTED HERE -- BY DESIGN",
            "why": (
                "gain_if_held_to_peak is a GROSS price spread. It ignores carrying cost "
                "entirely, and on this farm the carrying cost dominates it: the interest on "
                "the notional debt over the few in-game days to peak runs several times the "
                "spread, so the trade that looks obviously good on percentage is a large net "
                "loss. A spread is not a recommendation. Weigh it against the debt per "
                "sanctum/identity/creed.md doctrine -- that arithmetic is farm-specific and "
                "deliberately does not live in this portable skill."
            ),
            "also": (
                "Peaks land on DIFFERENT in-game days per crop (see each item's peak) -- "
                "'hold to peak' is not one decision, it is one per crop. And grain sitting in "
                "a combine is a combine that cannot harvest; the opportunity cost of the "
                "machine is real and is not in any of these numbers."
            ),
        },
        "items": items,
        "priced_at_period": period,
        "price_source": (
            "economy.xml per-period price curve via read_fill_prices.py. NOT read_prices.py's "
            "meanValue, which is 0.000000 on every node of this never-traded farm and would "
            "value this grain at nothing (F-001's shape)."
        ) if not pr_err else None,
        "price_error": pr_err,
        "holdings_caveats": [
            "Cargo excludes DIESEL/DEF/AIR -- consumables the machine runs on, not sellable "
            "produce. A combine full of fuel is not a combine full of grain.",
            "Silo contents are a verified read in both directions: a stocked <storage> writes "
            "a <node fillType= fillLevel=/> child (schema directly observed 2026-07-16) and an "
            "empty one writes no children at all, while <bunkerSilo> states an explicit "
            "fillLevel=0. An empty store here means empty, not unreadable.",
            "Litres are raw fillLevel from the save. Tank CAPACITY is not in vehicles.xml "
            "(it lives in the vehicle's own store XML/mod zip), so percent-full is not "
            "computed rather than guessed.",
        ],
        "sources": sources_ok,
        "sources_failed": sources_failed or None,
        "sources_incomplete": incomplete_sources or None,
    }


def build_input_costs(prices, game_defs, placeables, fields):
    """The BUY calendar: what inputs cost, when they're cheapest, and whether
    this farm can actually act on that.

    CROPS ARE A SELL CALENDAR; INPUTS ARE A BUY CALENDAR. For a crop, a high
    price is good. For an input, a LOW price is good. One code path treating
    both the same would silently invert the advice -- telling a player to buy
    seed at its annual PEAK while congratulating itself on finding the best
    number in the row. That inversion is the single most dangerous bug
    available in this section, so `best` is never computed generically here:
    the SELL side (inventory) asks read_fill_prices.py for its `peak`, and the
    BUY side below explicitly takes the MINIMUM and calls it `cheapest`.

    Which fillTypes are inputs is NOT hardcoded -- read_game_defs.py resolves
    it from the game's own SELLINGSTATION_* categories (map package first, per
    F-019). A hand-written list would have missed this map's extra ANHYDROUS
    spray type; the classifier picks it up with no code change.

    STOCKPILING REQUIRES STORAGE, and that dependency is enforced rather than
    assumed. "Seed is cheap today" is advice only if the farm owns somewhere
    to put it; otherwise it is trivia, and printing it next to a price would
    imply an action the farm cannot take.
    """
    pr_data, pr_err = prices
    gd_data, gd_err = game_defs

    if pr_err:
        return unavailable(f"read_fill_prices.py: {pr_err}")
    if gd_err:
        return unavailable(
            f"read_game_defs.py: {gd_err} -- without the game's own fillType classification "
            "there is no way to tell an input from a crop, and guessing would risk inverting "
            "buy-low into buy-high. Refusing to emit a calendar rather than emit a wrong one."
        )

    sellable = set(gd_data.get("sellable_fill_types") or [])
    spray_inputs = set(gd_data.get("spray_input_fill_types") or [])
    # The INPUT set, resolved by read_game_defs.py. Note it is NOT
    # `everything not sellable` -- that complement is also true of AIR,
    # PROPANE, STONE and ~200 intermediate products, and using it here once
    # produced a 74 KB digest with four real buy-signals buried in two hundred
    # rows of noise. See read_game_defs.input_fill_types_rule.
    input_types = set(gd_data.get("input_fill_types") or [])
    if not input_types:
        return unavailable(
            "read_game_defs.py resolved no input fill types -- without them there is no BUY "
            "calendar to report, and falling back to 'everything not sellable' would be noise, "
            "not an answer."
        )

    # Storage gate. Owned storage nodes come from read_placeables.py; their
    # emptiness is a separate question from their existence, and only
    # existence matters for "can we stockpile".
    p_data, p_err = placeables
    if p_err:
        can_stockpile = None
        stockpile_note = (
            f"UNKNOWN whether this farm can stockpile: read_placeables.py failed ({p_err}). "
            "Not assumed either way -- 'buy the annual low and store it' is only actionable "
            "with storage, so this gate is left explicitly unresolved rather than defaulted."
        )
        storage_count = None
    else:
        storage_count = ((p_data.get("storage_nodes") or {}).get("owned_count"))
        bunkers = ((p_data.get("bunker_silos") or {}).get("owned_count")) or 0
        can_stockpile = bool((storage_count or 0) + bunkers)
        stockpile_note = (
            f"The farm owns {storage_count} storage node(s) and {bunkers} bunker silo(s), so it "
            "CAN buy an input at its annual low and hold it for later use. That is what makes "
            "the cheapest_period column below actionable rather than academic."
            if can_stockpile else
            "The farm owns NO storage, so it cannot stockpile: an input must be bought at the "
            "point of use, at whatever that day's price happens to be. The cheapest_period "
            "column below is therefore NOT actionable for this farm today -- it becomes "
            "actionable the moment a silo is owned."
        )

    inputs = []
    for ft in (pr_data.get("fill_types") or []):
        name = ft["fill_type"]
        if name not in input_types:
            continue
        curve = ft.get("curve_per_1000l") or {}
        if not curve:
            continue
        now = ft.get("price_per_1000l")
        # BUY SIDE: minimum, explicitly. Never reuse the sell side's `peak`.
        cheapest_period = min(curve, key=curve.get)
        cheapest = curve[cheapest_period]
        dearest = max(curve.values())
        is_flat = cheapest == dearest

        cur = pr_data.get("current_period") or {}
        current_period = cur.get("period")
        day = (cur.get("derived_from") or {}).get("currentDay")
        dpp = (cur.get("derived_from") or {}).get("daysPerPeriod")
        periods_until = None
        cheapest_on_day = None
        if current_period and current_period in PERIOD_ORDER and cheapest_period in PERIOD_ORDER:
            periods_until = (PERIOD_ORDER.index(cheapest_period) - PERIOD_ORDER.index(current_period)) % 12
            if day is not None and dpp:
                cheapest_on_day = day + periods_until * dpp

        inputs.append({
            "fill_type": name,
            "is_spray_input": name in spray_inputs,
            "price_per_1000l_now": now,
            "cheapest": None if is_flat else {
                "period": cheapest_period,
                "price_per_1000l": cheapest,
                "on_in_game_day": cheapest_on_day,
                "periods_until": periods_until,
                "saving_per_1000l_vs_now": round(now - cheapest, 2) if now is not None else None,
                "pct_below_now": round((1 - cheapest / now) * 100, 1) if now else None,
            },
            "dearest_price_per_1000l": None if is_flat else dearest,
            "price_is_flat_all_year": is_flat,
            "buying_at_annual_low_today": (not is_flat) and now == cheapest,
        })

    inputs.sort(key=lambda x: (not x["buying_at_annual_low_today"], x["fill_type"]))

    # Seed cost per hectare, per crop -- the number that was previously
    # believed underivable. Reported per-hectare only: a farm-wide total would
    # need a cropping plan (which crop on which field), and that is the
    # player's decision, not something to invent from a seed rate.
    own = (fields[0] or {}).get("ownership") or {} if not fields[1] else {}
    owned_area = own.get("owned_area_ha")
    seed_price = next(
        (f.get("price_per_1000l") for f in (pr_data.get("fill_types") or [])
         if f["fill_type"] == SEED_FILL_TYPE), None
    )
    seed_curve = next(
        (f.get("curve_per_1000l") for f in (pr_data.get("fill_types") or [])
         if f["fill_type"] == SEED_FILL_TYPE), None
    )
    seed_low = min(seed_curve.values()) if seed_curve else None

    seed_costs = []
    for c in (gd_data.get("seed_rates") or []):
        rate = c.get("litres_per_hectare")
        if not rate or c.get("is_available_to_sow") == "false":
            continue
        seed_costs.append({
            "crop": c.get("crop"),
            "litres_per_hectare": rate,
            "cost_per_hectare_now": round(rate / 1000.0 * seed_price, 2) if seed_price else None,
            "cost_per_hectare_at_annual_low": round(rate / 1000.0 * seed_low, 2) if seed_low else None,
            "resolved_from": c.get("resolved_from"),
        })
    # Alphabetical, not cost-ranked. Ranking by cost put sugarCane (12,000
    # L/ha) at the top and made it the headline, which implies a relevance
    # this script has no basis for -- what the farm intends to sow is the
    # player's plan, not something a seed rate can reveal.
    seed_costs.sort(key=lambda x: (x["crop"] or ""))

    # Ship the crops THIS farm is actually growing; gate the rest behind --verbose.
    # Every crop's rate is correct and worth having somewhere -- but a briefing that
    # prices sugarCane, rice and poplar for a farm growing none of them is padding,
    # and padding is what turned this digest into something 2x the size of the full
    # snapshot it exists to condense (F-006, in reverse). "Correct" and "worth
    # printing every session" are different tests.
    seed_costs_all = seed_costs
    seed_costs_omitted = 0
    if not VERBOSE:
        planted = set()
        f_data, f_err = fields
        if not f_err and f_data:
            for fld in (f_data.get("fields") or []):
                # Only the farm's OWN fields -- ownership resolved, never assumed.
                if fld.get("owned") is True and fld.get("fruit_type"):
                    planted.add(str(fld["fruit_type"]).lower())
        if planted:
            kept = [s for s in seed_costs if (s["crop"] or "").lower() in planted]
            # If the crop-name spaces don't line up (fields.xml uses UPPER fruitType
            # names, the foliage XML uses camelCase), keep everything rather than
            # silently shipping an empty list -- an empty list would read as "no
            # seed costs", which is this project's oldest bug (F-001).
            if kept:
                seed_costs_omitted = len(seed_costs) - len(kept)
                seed_costs = kept

    return {
        "status": "ok",
        "calendar_type": "BUY -- for these fill types a LOW price is good. Do not read a "
                         "'peak' here; the sell-side peak belongs to inventory.",
        "priced_at_period": (pr_data.get("current_period") or {}).get("period"),
        "period_confidence": (pr_data.get("current_period") or {}).get("period_confidence"),
        "can_stockpile": can_stockpile,
        "can_stockpile_note": stockpile_note,
        "owned_storage_node_count": storage_count,
        "inputs": inputs,
        "price_is_flat_all_year_note": (
            "price_is_flat_all_year=true means the input costs the same in EVERY period: no "
            "timing advantage exists and there is no price reason to stockpile it. Said once "
            "here rather than repeated per row -- a flat price is a real answer, not missing "
            "data, and `cheapest` is null for those rows for that reason and no other."
        ),
        "buying_at_annual_low_today": [i["fill_type"] for i in inputs if i["buying_at_annual_low_today"]],
        "seed_cost_per_hectare": seed_costs,
        "seed_cost_scope": (
            f"Showing the {len(seed_costs)} crop(s) this farm is currently growing. "
            f"{seed_costs_omitted} other sowable crop(s) omitted -- rerun with --verbose for all "
            f"{len(seed_costs_all)}. Omitted, not unknown: every rate is resolved and correct, it is "
            f"just not a briefing's job to price sugarCane for a farm growing none."
            if seed_costs_omitted else
            f"All {len(seed_costs)} sowable crop(s) shown."
        ),
        "seed_cost_note": (
            f"Seed rate is the game's own <seeding litersPerSqm> from each crop's foliage XML "
            f"({gd_data.get('seed_rates_source')}), x10,000 for litres/ha, priced at "
            f"{SEED_FILL_TYPE}'s current-period price. Per-HECTARE only: a farm-wide total needs "
            f"a cropping plan (which crop on which field), which is the player's call and is not "
            f"invented here."
            + (f" The farm owns {owned_area} ha if you want to multiply." if owned_area else "")
        ),
        "classifier_source": gd_data.get("sellable_rule"),
        "sources": ["economy.xml via read_fill_prices.py",
                    f"game definitions via read_game_defs.py ({gd_data.get('map_mod_zip')})"],
    }


def build_weeds(fields, prices, vehicles, game_defs):
    """Weeds on the farm's OWN land, what treating them costs, and whether the
    farm can treat them at all.

    NO YIELD-LOSS MODEL IS INVENTED HERE, and that is a deliberate refusal
    rather than an omission. weedState is an ordinal from the map's own weed
    info-layer; the map's weed.xml carries only the raster wiring (info-layer
    filename, channels, a blocking state) and NOTHING that maps a weed level
    to a yield penalty, and the install's loose XML is equally silent. Any
    "weeds at 9 cost you N% of your crop" would therefore be fabricated. What
    IS derivable is reported: which owned fields are affected, how badly on
    the game's own scale, what herbicide costs, and whether the farm owns
    anything that could apply it. The player judges the rest.
    """
    f_data, f_err = fields
    if f_err:
        return unavailable(f"read_fields.py: {f_err}")

    own = f_data.get("ownership") or {}
    if not own.get("resolved"):
        return {
            "status": "unknown_by_design",
            "note": (
                "Field ownership did not resolve this run, so weeds cannot be attributed to the "
                "player's land. A map-wide weed count would be meaningless next to farm data "
                "(F-004's shape) and is deliberately not printed."
            ),
            "why_unresolved": own.get("why_unresolved"),
        }

    weedy = []
    observed_max = None
    for f in (f_data.get("fields") or []):
        if not f.get("owned"):
            continue
        raw = f.get("weed_state")
        try:
            ws = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            ws = None
        if ws is None:
            continue
        if observed_max is None or ws > observed_max:
            observed_max = ws
        if ws > 0:
            weedy.append({
                "field_id": f.get("id"),
                "weed_state": ws,
                "fruit_type": f.get("fruit_type"),
                "ground_type": f.get("ground_type"),
            })
    weedy.sort(key=lambda x: -x["weed_state"])

    # Can the farm act? Sprayer specialization, read from the save's own
    # runtime state -- never guessed from a filename (F-026).
    v_data, v_err = vehicles
    has_sprayer = None
    if not v_err:
        specs = set()
        for v in (v_data.get("vehicles") or []):
            specs |= set(v.get("specializations") or [])
        has_sprayer = "sprayer" in specs

    pr_data, pr_err = prices
    herbicide_price = None
    if not pr_err:
        herbicide_price = next(
            (f.get("price_per_1000l") for f in (pr_data.get("fill_types") or [])
             if f["fill_type"] == HERBICIDE_FILL_TYPE), None
        )

    return {
        "status": "ok",
        "weedy_owned_field_count": len(weedy),
        "worst": weedy[:5],
        "max_weed_state_observed_on_owned_land": observed_max,
        "herbicide_price_per_1000l": herbicide_price,
        "farm_owns_sprayer": has_sprayer,
        "can_treat": (
            None if has_sprayer is None else has_sprayer
        ),
        "cost_of_treatment": None,
        "cost_of_treatment_note": (
            "NOT COMPUTED. Herbicide's price per 1000 L is known and the game's own sprayType "
            "gives a litres-per-SECOND application rate, but converting that into a per-hectare "
            "cost needs the sprayer's working width and speed -- and this farm owns no sprayer, "
            "so there is no machine to take those from. A number here would be invented."
        ),
        "yield_loss": None,
        "yield_loss_note": (
            "NOT DERIVABLE, and deliberately not estimated. weedState is an ordinal on the map's "
            "own weed info-layer; the map's weed.xml defines only the raster wiring and no "
            "yield relationship, and the install's loose XML is silent too (the economics live "
            "in the packed dataS.gar). Any percentage here would be fabrication dressed as "
            "analysis. Report the level, the cost of herbicide and whether the farm can spray; "
            "let the player judge the rest."
        ),
        "note": (
            f"{len(weedy)} owned field(s) carry weeds"
            + (f", worst at weedState {weedy[0]['weed_state']}" if weedy else "")
            + (
                ". The farm owns NO sprayer, so this is a cost of inaction it currently cannot "
                "address without buying or hiring one -- see equipment_gaps."
                if has_sprayer is False else
                ". The farm owns a sprayer." if has_sprayer else
                ". Whether the farm owns a sprayer could not be determined."
            )
        ),
        "sources": ["fields.xml via read_fields.py (weedState + ownership)",
                    "vehicles.xml via read_vehicles.py (sprayer specialization, F-026)"],
    }


def build_equipment_market(market):
    """Used listings, resolved against their real new price."""
    data, err = market
    if err and not (data or {}).get("listings"):
        return unavailable(f"read_equipment_market.py: {err}")

    listings = (data or {}).get("listings") or []
    resolved = [l for l in listings if l.get("resolved")]
    resolved.sort(key=lambda l: -(l.get("discount_pct") or 0))

    return {
        "status": "ok" if not err else "partial",
        "partial_reason": err,
        "listing_count": (data or {}).get("listing_count"),
        "resolved_count": len(resolved),
        "unresolved_count": (data or {}).get("unresolved_count"),
        "listings": [
            {
                "label": l.get("label"),
                "category": l.get("category"),
                "listed_price": l.get("listed_price"),
                "new_price": l.get("new_price"),
                "discount_pct": l.get("discount_pct"),
                "wear_pct": (l.get("condition") or {}).get("wear_pct"),
                "damage_pct": (l.get("condition") or {}).get("damage_pct"),
                "operating_hours": (l.get("condition") or {}).get("operating_hours"),
                "time_left": l.get("time_left"),
                "from": l.get("resolved_from"),
            }
            for l in resolved
        ],
        "unresolved": [
            {"xml_filename_raw": l.get("xml_filename_raw"),
             "listed_price": l.get("listed_price"),
             "why": l.get("resolve_error")}
            for l in listings if not l.get("resolved")
        ] or None,
        "note": (
            "discount_pct is against the RESOLVED new price (base install or the mod's own zip "
            "-- never a basename guess, F-019). It is NOT a buy signal on its own: wear/damage "
            "are part of what makes a machine cheap, and repair cost is computed by the game at "
            "the workshop and cannot be read from the save. Listings EXPIRE (time_left) -- read "
            "with save_freshness."
        ),
        "source": "sales.xml via read_equipment_market.py, priced via read_store_prices.py",
    }


def build_equipment_gaps(gaps, weeds_section):
    """What the farm cannot do, and what fixing it costs.

    Composed from read_store_prices.py --gaps, which prices real store items
    for the categories this farm has no equipment in.
    """
    data, err = gaps
    if err:
        return unavailable(f"read_store_prices.py --gaps: {err}")

    cats = data.get("categories") or {}
    out = {}
    for name, block in cats.items():
        # read_store_prices.py --gaps reports match_count/priced_count/
        # min_price/max_price plus a truncated `shown` sample. Read those
        # fields, not the sample's length -- `shown` is capped, so counting it
        # would silently under-report how many options exist.
        cheapest = block.get("min_price")
        shown = block.get("shown") or []
        cheapest_item = min(
            (i for i in shown if i.get("price")), key=lambda i: i["price"], default=None
        )
        out[name] = {
            "options_found": block.get("match_count"),
            "priced_count": block.get("priced_count"),
            "cheapest_price": cheapest,
            "dearest_price": block.get("max_price"),
            "cheapest_example": (
                {"label": cheapest_item.get("name_literal") or cheapest_item.get("derived_label"),
                 "price": cheapest_item.get("price")}
                if cheapest_item and cheapest_item.get("price") == cheapest else None
            ),
            "price_note": None if cheapest is not None else (
                f"{block.get('match_count')} option(s) matched but none carried a resolvable "
                "price -- UNKNOWN, not free."
            ),
        }

    return {
        "status": "ok",
        "by_category": out,
        "why_it_matters": (
            "A capability the farm lacks is a cost it pays silently, every period. The weeds "
            "section is the live example: weeds on owned land that the farm cannot treat "
            "because it owns no sprayer."
            if (weeds_section or {}).get("farm_owns_sprayer") is False else
            "Categories where this farm owns no equipment, priced from the store."
        ),
        "note": (
            "Prices are real store prices resolved from the install/mod zips (read_store_prices.py). "
            "This lists what a capability COSTS, not whether to buy it -- that trades against the "
            "debt and is doctrine (creed.md), not arithmetic this script should pre-empt."
        ),
        "source": "read_store_prices.py --gaps",
    }


def build_field_lookup(fields):
    """Returns (field_id_str -> field_record dict, error_or_None). Used only
    to cross-check a specific mission's field_id against real growth state --
    NOT to make any ownership claim (that stays field_state's job, unchanged
    and still "unknown_by_design"). A mission naming a field_id is itself the
    scope-defining fact here, independent of the unresolved farmland-ownership
    mapping question."""
    data, err = fields
    if err:
        return {}, err
    lookup = {}
    for f in (data.get("fields") or []):
        fid = f.get("id")
        if fid is not None:
            lookup[str(fid)] = f
    return lookup, None


def build_fleet_specializations(vehicles):
    """Returns (set_of_specialization_tags_owned, error_or_None)."""
    data, err = vehicles
    if err:
        return set(), err
    specs = set()
    for v in (data.get("vehicles") or []):
        specs |= set(v.get("specializations") or [])
    return specs, None


def assess_mission_capability(m, fleet_specs, fleet_specs_err, field_lookup, fields_err):
    """Returns {"verdict": "actionable"|"not_actionable"|"unknown", "reason": str, ...}.
    Never claims "actionable" past what CAPABILITY_REQUIREMENTS plus this
    save's own vehicles.xml/fields.xml data actually support -- see the
    module docstring's F-026 section for why each check exists."""
    mtype = m.get("type")
    required = CAPABILITY_REQUIREMENTS.get(mtype)

    if fleet_specs_err:
        return {"verdict": "unknown", "reason": f"fleet specialization data unavailable: {fleet_specs_err}"}
    if required is None:
        return {"verdict": "unknown", "reason": f"no verified equipment-specialization mapping for {mtype!r} in this codebase"}

    missing = sorted(required - fleet_specs)
    if missing:
        return {
            "verdict": "not_actionable",
            "reason": f"farm does not own equipment with specialization(s): {missing}",
            "required_specializations": sorted(required),
        }

    result = {
        "verdict": "actionable",
        "reason": f"farm owns equipment with required specialization(s) {sorted(required)} "
                  "(vehicles.xml runtime state via read_vehicles.py, F-026)",
        "required_specializations": sorted(required),
    }

    # Equipment alone isn't proof for a harvest contract -- cross-check the
    # target field is actually ready, per team lead's explicit instruction:
    # "A harvest contract on a field that isn't ready would be a very
    # different message." Don't assume readiness from the contract existing.
    if mtype == "harvestMission":
        field_id = m.get("field_id")
        if not field_id:
            result["verdict"] = "unknown"
            result["reason"] = "harvestMission has no field_id to cross-check readiness against"
            return result
        if fields_err:
            result["verdict"] = "unknown"
            result["reason"] = (
                f"equipment confirmed, but field readiness could not be verified: "
                f"fields.xml unavailable ({fields_err})"
            )
            return result
        field = field_lookup.get(str(field_id))
        if field is None:
            result["verdict"] = "unknown"
            result["reason"] = f"equipment confirmed, but field id {field_id} was not found in fields.xml"
            return result
        # crop_state, not groundType. groundType is the TERRAIN TEXTURE: it still
        # reads HARVEST_READY on a field cut days ago, so it confirmed nothing.
        crop_state = field.get("crop_state")
        result["field_crop_state"] = crop_state
        result["field_ground_type"] = field.get("ground_type")
        result["field_fruit_type"] = field.get("fruit_type")
        if crop_state is None:
            result["verdict"] = "unknown"
            result["reason"] = (
                f"equipment confirmed, but field {field_id}'s crop state could not be "
                f"determined ({field.get('crop_state_reason')}) -- unknown, not ready"
            )
            return result
        if crop_state != "ready":
            result["verdict"] = "unknown"
            result["reason"] = (
                f"equipment confirmed, but field {field_id} is {crop_state!r}, not ready "
                f"({field.get('crop_state_reason')}) -- do not treat as ready without checking in-game"
            )
            return result
        result["reason"] += (f"; fields.xml independently confirms field {field_id} is ready "
                             f"({field.get('crop_state_reason')})")

    return result


def build_contracts(missions, current_day, fleet_specs, fleet_specs_err, field_lookup, fields_err):
    data, err = missions
    if err:
        return unavailable(f"read_missions.py: {err}")

    all_missions = data.get("missions") or []
    by_type = {}
    by_status = {}
    expiring_today = []
    actionable_today = []
    not_actionable_by_type = {}
    not_actionable_today_by_type = {}
    not_actionable_missing = set()
    unknown_capability_by_type = {}
    unknown_capability_today_by_type = {}

    for m in all_missions:
        mtype = m.get("type") or "unknown"
        by_type[mtype] = by_type.get(mtype, 0) + 1
        status = m.get("status") or "unknown"
        by_status[status] = by_status.get(status, 0) + 1

        end_date = m.get("endDate") or {}
        end_day_raw = end_date.get("endDay")
        is_expiring_today = False
        if current_day is not None and end_day_raw is not None:
            try:
                is_expiring_today = int(end_day_raw) == int(current_day)
            except ValueError:
                pass
        if is_expiring_today:
            expiring_today.append(mtype)

        capability = assess_mission_capability(m, fleet_specs, fleet_specs_err, field_lookup, fields_err)

        if capability["verdict"] == "actionable" and is_expiring_today:
            actionable_today.append({
                "type": mtype,
                "field_id": m.get("field_id"),
                "fruit_type": capability.get("field_fruit_type"),
                "end_day": end_date.get("endDay"),
                "end_day_time_ms": end_date.get("endDayTime"),
                "reward": m.get("reward"),
                "reward_note": m.get("reward_note"),
                "capability_reason": capability["reason"],
            })
        elif capability["verdict"] == "not_actionable":
            not_actionable_by_type[mtype] = not_actionable_by_type.get(mtype, 0) + 1
            not_actionable_missing.update(
                s for s in capability.get("required_specializations", []) if s not in fleet_specs
            )
            if is_expiring_today:
                not_actionable_today_by_type[mtype] = not_actionable_today_by_type.get(mtype, 0) + 1
        elif capability["verdict"] == "unknown":
            unknown_capability_by_type[mtype] = unknown_capability_by_type.get(mtype, 0) + 1
            if is_expiring_today:
                unknown_capability_today_by_type[mtype] = unknown_capability_today_by_type.get(mtype, 0) + 1

    return {
        "status": "ok",
        "total_count": data.get("mission_count"),
        "by_type": by_type,
        "by_status": by_status,
        "expiring_today_count": len(expiring_today),
        "expiring_today_types": expiring_today,
        "actionable_today": actionable_today,
        "not_actionable_summary": {
            "count": sum(not_actionable_by_type.values()),
            "by_type": not_actionable_by_type,
            "today_count": sum(not_actionable_today_by_type.values()),
            "today_by_type": not_actionable_today_by_type,
            "missing_specializations": sorted(not_actionable_missing),
            "note": "equipment ownership confirmed absent via vehicles.xml specializations (F-026) "
                    "-- not a guess. count/by_type are ALL such contracts in this save; "
                    "today_count/today_by_type are the subset also expiring today.",
        } if not_actionable_by_type else None,
        "unknown_capability_summary": {
            "count": sum(unknown_capability_by_type.values()),
            "by_type": unknown_capability_by_type,
            "today_count": sum(unknown_capability_today_by_type.values()),
            "today_by_type": unknown_capability_today_by_type,
            "note": "no verified equipment-specialization mapping for these mission types yet, "
                    "or a fleet/field cross-check couldn't be completed -- capability neither "
                    "confirmed nor ruled out, not assumed either way. count/by_type are ALL such "
                    "contracts in this save; today_count/today_by_type are the subset also "
                    "expiring today.",
        } if unknown_capability_by_type else None,
        "capability_check_source": (
            "vehicles.xml 'specializations' (read_vehicles.py, F-026), cross-referenced against "
            "fields.xml groundType for harvestMission field readiness specifically"
        ),
        "note": (
            "offered-vs-accepted is NOT distinguishable from this save's data -- every "
            "named mission here shows status=CREATED with vehicles.spawned=false, and no "
            "other status value has been observed to confirm what 'accepted' looks like. "
            "expiring_today_count is a direct read of endDate.endDay == current in-game "
            "day, independent of that open question. THIS LIST IS NOT STABLE -- contracts "
            "expire and respawn daily (observed 13 -> 15 within one session); always read "
            "this alongside `save_freshness` in the same digest so a stale contract list "
            "can't send the player after an offer that's already gone."
        ),
        "source": "missions.xml via read_missions.py",
    }


def main():
    global VERBOSE
    args = sys.argv[1:]
    if "--verbose" in args:
        VERBOSE = True
        args.remove("--verbose")
    farm_id = 1
    if "--farm-id" in args:
        i = args.index("--farm-id")
        try:
            farm_id = int(args[i + 1])
        except (IndexError, ValueError):
            print(json.dumps({"error": "--farm-id requires an integer"}))
            sys.exit(1)
        del args[i:i + 2]

    explicit_config = None
    if "--config" in args:
        i = args.index("--config")
        try:
            explicit_config = args[i + 1]
        except IndexError:
            print(json.dumps({"error": "--config requires a path"}))
            sys.exit(1)
        del args[i:i + 2]

    if not args:
        print(json.dumps({
            "error": "usage: farm_snapshot.py <savegame_dir> [--farm-id N] [--config PATH]"
        }))
        sys.exit(1)
    savegame_dir = args[0]

    config_path, config_err = find_config(explicit_config)
    path_args = ["--config", config_path] if config_path else None

    env = call("read_environment.py", savegame_dir)
    career = call("read_career.py", savegame_dir)
    economy = call("read_economy.py", savegame_dir, farm_id)
    fields = call("read_fields.py", savegame_dir, farm_id)
    vehicles = call("read_vehicles.py", savegame_dir, farm_id)
    missions = call("read_missions.py", savegame_dir)
    placeables = call("read_placeables.py", savegame_dir, farm_id)
    # read_fill_prices.py takes no --farm-id (prices are map-wide, not owned).
    prices = call("read_fill_prices.py", savegame_dir)

    # These three need the game INSTALL, not just the savegame. When no config
    # is found they fail with find_config's reason attached rather than
    # silently degrading -- the rest of the digest is unaffected.
    no_cfg = (None, config_err)
    game_defs = call("read_game_defs.py", savegame_dir, None, path_args) if path_args else no_cfg
    market = call("read_equipment_market.py", savegame_dir, None, path_args) if path_args else no_cfg
    gaps = call("read_store_prices.py", savegame_dir, farm_id,
                (path_args or []) + ["--gaps"]) if path_args else no_cfg

    when = build_when(env)
    current_day = when.get("in_game_day") if when.get("status") == "ok" else None

    field_lookup, fields_err = build_field_lookup(fields)
    fleet_specs, fleet_specs_err = build_fleet_specializations(vehicles)

    weeds = build_weeds(fields, prices, vehicles, game_defs)

    snapshot = {
        "savegame_dir": savegame_dir,
        "farm_id": farm_id,
        "when": when,
        "save_freshness": build_save_freshness(career, savegame_dir),
        "money": build_money(economy),
        "land": build_land(economy),
        "field_state": build_field_state(fields),
        "fleet": build_fleet(vehicles),
        "inventory": build_inventory(vehicles, placeables, prices),
        "input_costs": build_input_costs(prices, game_defs, placeables, fields),
        "weeds": weeds,
        "equipment_market": build_equipment_market(market),
        "equipment_gaps": build_equipment_gaps(gaps, weeds),
        "contracts": build_contracts(missions, current_day, fleet_specs, fleet_specs_err, field_lookup, fields_err),
    }

    decisions = []

    # A ripe crop on the player's OWN ground leads. It outranks a contract: a
    # contract pays a fixed fee and the grain goes to the contractor, whereas
    # this grain is the player's to store and time against the price calendar.
    # Only possible since ownership became resolvable (F-004); before that this
    # section could not have existed at all.
    fs = snapshot["field_state"]
    if fs.get("status") == "ok":
        for f in (fs.get("harvest_ready_on_owned_land") or []):
            weed = f.get("weed_state")
            weed_bit = ""
            if weed is not None:
                try:
                    if int(weed) >= 7:
                        weed_bit = f" Weeds are heavy here (weedState {weed}) -- expect yield loss."
                except (TypeError, ValueError):
                    pass
            decisions.append(
                f"Field {f['id']} ({f['fruit_type']}) is READY on land the farm "
                f"OWNS -- this crop is the player's to keep, unlike contract work where the "
                f"grain goes to the contractor.{weed_bit} Harvest windows are short when "
                f"daysPerPeriod is low; check references/time-mechanics.md before skipping days."
            )

    # Grain already cut is money already earned that hasn't been banked yet --
    # it outranks a contract offer, and until now no briefing could see it.
    inv = snapshot["inventory"]
    if inv.get("status") == "ok" and inv.get("state") == "holding":
        for item in inv.get("items", []):
            where = ", ".join(sorted({(l.get("what") or "?").split("/")[-1] for l in item["locations"]}))
            if item.get("value_now") is None:
                decisions.append(
                    f"{item['litres']:,.0f} L of {item['fill_type']} is sitting in {where} and "
                    f"could NOT be priced -- {item['value_note']} Do not treat it as worthless."
                )
                continue
            peak = item.get("peak") or {}
            decisions.append(
                f"{item['litres']:,.0f} L of {item['fill_type']} is sitting in {where}, worth "
                f"${item['value_now']:,.2f} at today's price. It is not banked until it is sold, "
                f"and it occupies the machine holding it. Peak is {peak.get('period')} on in-game "
                f"day {peak.get('on_in_game_day')} (+${peak.get('gain_vs_now'):,.2f} gross) -- that "
                f"spread IGNORES carrying cost and is NOT a recommendation to hold; weigh it "
                f"against the debt per creed.md."
            )
        if inv.get("total_value_now") is not None and len(inv.get("items", [])) > 1:
            decisions.append(
                f"Total unsold produce on hand: ${inv['total_value_now']:,.2f} at today's price "
                f"(priced at {(inv.get('priced_at_period') or {}).get('period')})."
            )

    # An input at its annual low is a one-period window. It leads ONLY if the
    # farm can actually store what it buys -- otherwise it is trivia, and
    # saying it would imply an action the farm cannot take.
    ic = snapshot["input_costs"]
    if ic.get("status") == "ok":
        for name in (ic.get("buying_at_annual_low_today") or []):
            row = next((i for i in ic["inputs"] if i["fill_type"] == name), None)
            if not row:
                continue
            dearest = row.get("dearest_price_per_1000l")
            now = row.get("price_per_1000l_now")
            multiple = f" It rises to {dearest:,.0f} at its worst ({dearest / now:.1f}x)." if (
                dearest and now) else ""
            if ic.get("can_stockpile"):
                decisions.append(
                    f"{name} is at its ANNUAL LOW today ({now:,.0f}/1000 L).{multiple} The farm "
                    f"owns storage, so it can buy now and hold. This window is one period wide "
                    f"-- see input_costs."
                )
            else:
                decisions.append(
                    f"{name} is at its annual low today ({now:,.0f}/1000 L){multiple} but the farm "
                    f"owns NO storage to stockpile it in, so this is not actionable -- inputs must "
                    f"be bought at the point of use. It becomes actionable with a silo."
                )
        # A range, not a single crop: naming one implies a cropping plan this
        # script cannot know.
        priced = [s for s in (ic.get("seed_cost_per_hectare") or []) if s.get("cost_per_hectare_now")]
        if priced:
            lo = min(priced, key=lambda s: s["cost_per_hectare_now"])
            hi = max(priced, key=lambda s: s["cost_per_hectare_now"])
            decisions.append(
                f"Seed cost at today's price spans ${lo['cost_per_hectare_now']:,.2f}/ha ({lo['crop']}) "
                f"to ${hi['cost_per_hectare_now']:,.2f}/ha ({hi['crop']}) across {len(priced)} sowable "
                f"crops -- rate is the game's own litersPerSqm per crop. Which crop is the player's "
                f"plan, so no farm total is computed; see input_costs.seed_cost_per_hectare."
            )

    w = snapshot["weeds"]
    if w.get("status") == "ok" and w.get("weedy_owned_field_count"):
        worst = w.get("worst") or []
        ids = ", ".join(str(x["field_id"]) for x in worst[:3])
        if w.get("farm_owns_sprayer") is False:
            decisions.append(
                f"{w['weedy_owned_field_count']} owned field(s) have weeds (worst: {ids} at "
                f"weedState {worst[0]['weed_state']} of {w.get('max_weed_state_observed_on_owned_land')} "
                f"seen). The farm owns NO sprayer, so it cannot treat them. Herbicide is "
                f"{w.get('herbicide_price_per_1000l')}/1000 L. No yield-loss figure is given "
                f"because none is derivable from the save or the install -- see weeds.yield_loss_note."
            )

    em = snapshot["equipment_market"]
    if em.get("status") in ("ok", "partial") and em.get("listings"):
        best = em["listings"][0]
        decisions.append(
            f"Used market: {best['label']} listed ${best['listed_price']:,.0f} vs ${best['new_price']:,.0f} "
            f"new ({best['discount_pct']}% off), wear {best['wear_pct']}%. {em['listing_count']} "
            f"listing(s) live, each expiring -- see equipment_market. A discount is not a buy "
            f"signal; wear is part of why it's cheap."
        )

    contracts = snapshot["contracts"]
    if contracts.get("status") == "ok":
        actionable = contracts.get("actionable_today") or []
        for a in actionable:
            expiry = f"end of in-game day {a['end_day']}"
            if a.get("end_day_time_ms") is not None:
                try:
                    expiry += f" ({ms_to_clock(int(a['end_day_time_ms']))})"
                except (TypeError, ValueError):
                    pass
            field_bit = f"Field {a['field_id']}" + (f" ({a['fruit_type']})" if a.get("fruit_type") else "")
            decisions.append(
                f"{field_bit} -- {a['type']}, expires {expiry}. {a['capability_reason']}. "
                f"Reward: {a['reward'] if a['reward'] is not None else 'UNKNOWN until accepted'} "
                "-- check the in-game contract screen, never assume $0 (FRICTION-LOG.md F-025)."
            )

        leftover_today = contracts.get("expiring_today_count", 0) - len(actionable)
        if leftover_today > 0:
            na = contracts.get("not_actionable_summary") or {}
            uk = contracts.get("unknown_capability_summary") or {}
            na_today = na.get("today_count", 0)
            uk_today = uk.get("today_count", 0)
            bits = []
            if na_today:
                bits.append(f"{na_today} not actionable today (missing: {', '.join(na.get('missing_specializations', []))})")
            if uk_today:
                bits.append(f"{uk_today} capability not machine-verified")
            # These must sum to leftover_today by construction (both are scoped
            # to is_expiring_today in build_contracts) -- if they don't, something
            # drifted between the two functions; say so instead of printing
            # arithmetic that doesn't add up (the exact bug this comment replaced:
            # an earlier version used the ALL-missions counts here, not the
            # today-scoped ones, and 10+4 != 11 silently shipped once).
            if na_today + uk_today != leftover_today:
                bits.append(
                    f"[internal count mismatch: today-scoped breakdown sums to "
                    f"{na_today + uk_today}, expected {leftover_today} -- see contracts section directly]"
                )
            decisions.append(
                f"{leftover_today} other contract(s) also expire today but are not confirmed "
                f"actionable by the owned fleet" + (f" -- {'; '.join(bits)}." if bits else ".")
            )

    fleet = snapshot["fleet"]
    if fleet.get("status") == "ok" and fleet.get("needs_attention"):
        decisions.append(
            f"{len(fleet['needs_attention'])} vehicle(s) at or above 50% wear -- see fleet.needs_attention."
        )
    when_section = snapshot["when"]
    if when_section.get("status") == "ok" and when_section.get("next_notable_event", {}).get("type"):
        nne = when_section["next_notable_event"]
        decisions.append(
            f"{nne['type']} forecast for in-game day {nne['starts_day']} at {nne['starts_clock']}."
        )
    snapshot["decisions_needed"] = decisions or [
        "None identified from the sources this script checks (contract deadlines, fleet "
        "wear, near-term disruptive weather). This is not a guarantee nothing needs "
        "doing -- only that nothing in those specific checks flagged."
    ]

    # Collect every section's failure, if any, into one place so a caller
    # can't miss a degraded source by only skimming individual sections.
    calibration_warnings = []
    for name, section in snapshot.items():
        if isinstance(section, dict) and section.get("status") == "unavailable":
            calibration_warnings.append({"section": name, "reason": section.get("reason")})
    snapshot["calibration_warnings"] = calibration_warnings

    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
