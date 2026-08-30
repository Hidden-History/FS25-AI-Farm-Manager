"""
Read economy.xml -> the per-period sale price curve for every fillType, and
resolve which period the farm is in RIGHT NOW.

Usage: python3 read_fill_prices.py <savegame_dir> [--fill-type X [--fill-type Y ...]]
    --fill-type X   Restrict output to these fillTypes (repeatable). Default:
                    all fillTypes that carry a price history.

WHY THIS EXISTS: nothing in this skill parsed economy.xml's price history
until now -- read_economy.py deliberately does NOT read economy.xml (it reads
farms.xml for cash/loan; see F-001, the worst bug this project ever had), and
read_prices.py reads placeables.xml's per-station <stats> meanValue, which is
0.000000 on every node of this never-traded farm and therefore carries NO
price signal at all (it now emits null + a note for exactly that reason).
economy.xml's history is the populated, real signal. This script is the only
thing that reads it.

VERIFIED against this save by running, 2026-07-24 (not by report -- the team
lead supplied the pricing method and asked for it to be checked, and one part
of it did NOT survive the check; see PERIOD, below):

    <economy><fillTypes>
        <fillType fillType="UNKNOWN"/>            <- no <history> at all
        <fillType fillType="OAT">
            <history>
                <period period="EARLY_SPRING">532</period>
                ... 12 periods, always all 12, always in calendar order ...
            </history>
        </fillType>
    237 <fillType> elements; every one that carries a <history> carries all
    12 periods. This is NOT a rolling record of observed past trades -- it is
    the full seasonal price CURVE, present in full on in-game day 7 of a farm
    that has never sold anything. So "today's price" is a lookup of the
    current period in that curve, not an average of anything.

UNITS -- checked by the physical-plausibility test that this codebase's
references name as the only one that reliably catches unit bugs: OAT
EARLY_AUTUMN reads 460. If that were per litre, the 76,772 L sitting in one
of this farm's combines would be worth $35.3 MILLION, which is absurd for one
tank of oats. Read as **price per 1000 litres** it is $35,315 -- an ordinary
number for a combine full of grain. Per-1000-litres it is. Every value from
this script is therefore divided by 1000 before it touches a litre count.

PERIOD -- DERIVED BY FORMULA, THEN CONFIRMED BY OBSERVATION
-----------------------------------------------------------
There is NO currentPeriod field anywhere in this savegame. It was searched
for. The period must be DERIVED, so this script always reports HOW
(`current_period.derived`, never a bare value).

The derivation:
    environment.xml: <currentDay>7</currentDay>, <daysPerPeriod>1</daysPerPeriod>
    period_index = ((currentDay - 1) // daysPerPeriod) % 12
                 = ((7 - 1) // 1) % 12 = 6 -> PERIODS[6] = EARLY_AUTUMN

There WAS a serious rival reading, and it is now dead. Recording both, because
the way it died is reusable:

    THE RIVAL: environment.xml's forecast tags every instance for in-game days
    7 THROUGH 16 with season="SUMMER" -- ten consecutive days. If a period
    advanced once per day, those ten days would run EARLY_AUTUMN -> LATE_WINTER
    and that attribute would have to change. It does not. careerSavegame.xml
    also carries <growthMode>2</growthMode> and <fixedSeasonalVisuals>4</...>,
    and period 4 (1-indexed) is EARLY_SUMMER -- matching the frozen SUMMER
    exactly. So: was the economy pinned to EARLY_SUMMER with the visuals?
    It mattered -- OAT reads 460 at EARLY_AUTUMN and 500 at EARLY_SUMMER, a
    ~9% error on every valuation, and the kind that looks entirely plausible.

    HOW IT WAS SETTLED (2026-07-16, by observation, no player action needed):
    economy.xml is written live while the player plays, and comparing two
    reads of it taken ~40 minutes apart shows WHICH CELL THE GAME TOUCHES.
    Across 4 unrelated fillTypes and 40 cells with known prior values:
        36 cells unchanged
         4 cells changed -- and every one was EARLY_AUTUMN:
            OAT    .EARLY_AUTUMN  460 -> 461
            CANOLA .EARLY_AUTUMN  604 -> 605
            WHEAT  .EARLY_AUTUMN  294 -> 295
            SEEDS  .EARLY_AUTUMN  277 -> 278
    The game fluctuates the CURRENT period's price in place and leaves the
    other 11 frozen. That identifies the live period by OBSERVATION rather
    than by derivation -- and it is EARLY_AUTUMN, exactly what the formula
    predicted. The fixedSeasonalVisuals/EARLY_SUMMER reading is REFUTED: had
    it been right, EARLY_SUMMER would have been the cell moving.
    Conclusion: fixedSeasonalVisuals freezes only the LOOK of the world (the
    setting is, after all, named "...Visuals"), and the weather forecast's
    season attribute is a visual selector with no economic meaning.

    WHAT THIS DOES AND DOESN'T PROVE. It proves the live period is
    EARLY_AUTUMN on this save, and it kills the rival outright. It does not
    independently prove the FORMULA holds at every day -- it confirms the
    formula's prediction at one day (7). The formula and the observation
    agree, and the only competing hypothesis is refuted, so the formula is
    reported with `period_confidence: "derived_formula_confirmed_by_observation"`.
    A future save where they disagree should be believed over this docstring:
    re-run the test below, don't trust this paragraph.

    THE TEST, REUSABLE ON ANY SAVE, COSTS NOTHING: read economy.xml twice
    while the game is running (the writes are deferred, so allow a generous
    window -- F-023) and diff the period cells. Exactly one period will have
    moved. That period is the live one. This is strictly better than the
    "one-day tick test" on this project's task list, which needs the player to
    advance a day; this needs only patience, and works INSIDE a single period.

Output contract:
    - Absence never looks like data. A fillType with no <history> (e.g.
      UNKNOWN, the game's own empty-slot sentinel) is reported with
      price_per_1000l: null and a stated reason -- never 0, which would read
      as "this crop is worthless".
    - current_period is always accompanied by `derived: true`, the inputs it
      was derived from, its confidence, and the competing reading. It is
      never emitted as a bare string.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

# Calendar order. This is the order economy.xml itself writes them in, on
# every one of the 236 fillTypes that carry a history -- confirmed by reading,
# not assumed from a general knowledge of the game.
PERIODS = [
    "EARLY_SPRING", "MID_SPRING", "LATE_SPRING",
    "EARLY_SUMMER", "MID_SUMMER", "LATE_SUMMER",
    "EARLY_AUTUMN", "MID_AUTUMN", "LATE_AUTUMN",
    "EARLY_WINTER", "MID_WINTER", "LATE_WINTER",
]

# economy.xml quotes price for this many litres. See the UNITS note above --
# established by physical plausibility, which is the test that works.
PRICE_QUOTED_PER_LITRES = 1000.0


def parse_fill_type_args(argv):
    """Pull repeatable --fill-type X out of argv. Returns (set_or_None, error)."""
    wanted = set()
    args = argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--fill-type":
            if i + 1 >= len(args):
                return None, "--fill-type given with no value"
            wanted.add(args[i + 1].upper())
            i += 2
        else:
            i += 1
    return (wanted or None), None


def read_current_day(savegame_dir):
    """Returns (current_day, days_per_period, error_or_None) from environment.xml.

    Deliberately reads the two tags by exact name. currentDay is the day
    counter; dayTime is minutes-of-day and is NOT a day (this codebase has
    burned itself on that exact confusion -- see CLAUDE.md's units table).
    """
    path = os.path.join(savegame_dir, "environment.xml")
    root, generic = load_xml(path)
    if root is None:
        return None, None, generic.get("error", "unknown error reading environment.xml")

    day_elem = root.find("currentDay")
    dpp_elem = root.find("daysPerPeriod")
    if day_elem is None or not (day_elem.text or "").strip():
        return None, None, "environment.xml has no <currentDay> -- cannot derive the current period"
    if dpp_elem is None or not (dpp_elem.text or "").strip():
        return None, None, "environment.xml has no <daysPerPeriod> -- cannot derive the current period"
    try:
        return int(day_elem.text.strip()), int(dpp_elem.text.strip()), None
    except ValueError as e:
        return None, None, f"environment.xml <currentDay>/<daysPerPeriod> not integers: {e}"


def read_visual_season_evidence(savegame_dir):
    """Collect the evidence that CONTRADICTS the day-derived period, so it
    travels with every answer instead of being quietly dropped. See the
    module docstring's PERIOD section -- this is not decoration, it is the
    reason period_confidence is not "certain"."""
    ev = {}
    env_path = os.path.join(savegame_dir, "environment.xml")
    root, _ = load_xml(env_path)
    if root is not None:
        seasons = sorted({i.attrib["season"] for i in root.iter("instance") if "season" in i.attrib})
        days = sorted({int(i.attrib["startDay"]) for i in root.iter("instance") if "startDay" in i.attrib})
        if seasons:
            ev["forecast_seasons"] = seasons
            ev["forecast_day_span"] = [min(days), max(days)] if days else None

    career_path = os.path.join(savegame_dir, "careerSavegame.xml")
    croot, _ = load_xml(career_path)
    if croot is not None:
        for tag in ("growthMode", "fixedSeasonalVisuals"):
            el = croot.find(f".//{tag}")
            if el is not None and (el.text or "").strip():
                ev[tag] = el.text.strip()
    return ev


def derive_current_period(savegame_dir):
    """Returns (period_dict, error_or_None).

    NEVER returns a bare period string -- the caller must be unable to quote
    the period without also carrying the fact that it was derived and the
    evidence that disputes it.
    """
    day, dpp, err = read_current_day(savegame_dir)
    if err:
        return None, err
    if dpp <= 0:
        return None, f"daysPerPeriod is {dpp} -- cannot derive a period from a non-positive period length"

    index = ((day - 1) // dpp) % len(PERIODS)
    evidence = read_visual_season_evidence(savegame_dir)

    alt = None
    fsv = evidence.get("fixedSeasonalVisuals")
    if fsv is not None:
        try:
            fsv_i = int(fsv)
            if 1 <= fsv_i <= len(PERIODS):
                alt = PERIODS[fsv_i - 1]
        except ValueError:
            pass

    return {
        "period": PERIODS[index],
        "period_index_0based": index,
        "derived": True,
        "derived_from": {
            "currentDay": day,
            "daysPerPeriod": dpp,
            "formula": "((currentDay - 1) // daysPerPeriod) % 12",
            "source": "environment.xml",
        },
        "period_confidence": "derived_formula_confirmed_by_observation",
        "why_not_certain": (
            "This savegame contains NO currentPeriod field -- it was searched for and does not "
            "exist -- so the period above is DERIVED by formula. The formula's prediction was "
            "CONFIRMED by observation on 2026-07-16: economy.xml is written live, and diffing "
            "two reads ~40 min apart showed the game mutating exactly ONE period's cell across "
            "4 unrelated fillTypes (OAT/CANOLA/WHEAT/SEEDS all moved, 36 other cells frozen) -- "
            "and that cell was the derived period. The game fluctuates the CURRENT period in "
            "place, which identifies it by observation. This confirms the derivation at this "
            "day; it does not independently prove the formula at every day. If a future read "
            "ever disagrees, believe the observation, not this note -- re-run the test in "
            "how_to_verify."
        ),
        "refuted_alternative_reading": (
            {
                "period": alt,
                "status": "REFUTED by observation, 2026-07-16",
                "basis_it_had": f"careerSavegame.xml growthMode={evidence.get('growthMode')}, "
                                f"fixedSeasonalVisuals={fsv} -> period {fsv} (1-indexed) = {alt}, "
                                f"apparently corroborated by season={evidence.get('forecast_seasons')} "
                                f"frozen across the whole forecast window "
                                f"(days {evidence.get('forecast_day_span')}) -- ten days that "
                                "could not all be one season if periods advanced daily.",
                "how_it_died": (
                    f"If the economy sat at {alt}, then {alt} would be the cell economy.xml "
                    f"fluctuates. It is not: only {PERIODS[index]} moves. So "
                    "fixedSeasonalVisuals freezes the LOOK of the world only (it is named "
                    "'...Visuals'), and the forecast's season attribute carries no economic "
                    "meaning. Retained here because a refuted hypothesis with its evidence is "
                    "worth more than a silently deleted one -- it stops the next session "
                    "re-opening the same question."
                ),
            }
            if alt and alt != PERIODS[index] else None
        ),
        "how_to_verify": (
            "Reusable on ANY save, needs no player action: read economy.xml twice while the "
            "game runs and diff the 12 period cells per fillType. FS25 defers its writes, so "
            "allow a generous window (F-023 -- a 2-minute wait was not enough; ~40 min was). "
            "Exactly one period will have moved: that is the live one. Strictly better than "
            "advancing an in-game day, because it works INSIDE a single period."
        ),
        "visual_season_evidence": evidence,
        "visual_season_evidence_note": (
            "Kept visible, but it is a VISUALS signal, not an economic one -- see "
            "refuted_alternative_reading. Do not re-derive a period from it."
        ),
    }, None


def read_price_histories(savegame_dir):
    """Returns (dict fillType -> {period: price}, error_or_None).

    A fillType with no <history> is OMITTED here rather than recorded as an
    empty/zero curve -- callers must be able to tell "no price data for this
    fillType" from "this fillType is worth 0".
    """
    path = os.path.join(savegame_dir, "economy.xml")
    root, generic = load_xml(path)
    if root is None:
        return None, generic.get("error", "unknown error reading economy.xml")

    fill_types = list(root.iter("fillType"))
    if not fill_types:
        return None, "economy.xml parsed but contained no <fillType> elements -- schema may have changed"

    histories = {}
    for ft in fill_types:
        name = ft.attrib.get("fillType")
        if not name:
            continue
        curve = {}
        for p in ft.iter("period"):
            period_name = p.attrib.get("period")
            text = (p.text or "").strip()
            if not period_name or not text:
                continue
            try:
                curve[period_name] = float(text)
            except ValueError:
                continue
        if curve:
            histories[name] = curve

    if not histories:
        return None, (
            "economy.xml has <fillType> elements but not one carries a parsable <history>/"
            "<period> price curve -- schema may have changed. Refusing to report 'no prices' "
            "as if that were a real answer."
        )
    return histories, None


def build_fill_type_report(name, curve, current_period, current_day, days_per_period):
    """Price now + the peak of the curve and when it lands. Never a bare 0."""
    now_price = curve.get(current_period)
    peak_period = max(curve, key=curve.get)
    peak_price = curve[peak_period]

    periods_until_peak = None
    peak_on_day = None
    if current_period in PERIODS:
        gap = (PERIODS.index(peak_period) - PERIODS.index(current_period)) % len(PERIODS)
        periods_until_peak = gap
        if current_day is not None and days_per_period:
            peak_on_day = current_day + gap * days_per_period

    return {
        "fill_type": name,
        "price_per_1000l": now_price,
        "price_per_litre": (now_price / PRICE_QUOTED_PER_LITRES) if now_price is not None else None,
        "price_note": None if now_price is not None else (
            f"economy.xml has a price curve for {name} but no entry for the current period "
            f"({current_period}) -- unknown, NOT zero."
        ),
        "peak": {
            "period": peak_period,
            "price_per_1000l": peak_price,
            "periods_until": periods_until_peak,
            "on_in_game_day": peak_on_day,
            "gain_per_1000l_vs_now": (peak_price - now_price) if now_price is not None else None,
        },
        "trough": {
            "period": min(curve, key=curve.get),
            "price_per_1000l": min(curve.values()),
        },
        "curve_per_1000l": curve,
    }


def main():
    savegame_dir = arg_or_exit("read_fill_prices.py <savegame_dir> [--fill-type X ...]")
    wanted, arg_err = parse_fill_type_args(sys.argv)
    if arg_err:
        emit({"error": arg_err})
        return

    period, period_err = derive_current_period(savegame_dir)
    if period_err:
        emit({
            "error": f"could not resolve the current period: {period_err}. Prices are "
                     "period-indexed, so without a period there is no 'today's price' -- "
                     "refusing to guess one.",
            "calibration_needed": True,
        })
        return

    histories, hist_err = read_price_histories(savegame_dir)
    if hist_err:
        emit({"error": hist_err, "calibration_needed": True})
        return

    current = period["period"]
    names = sorted(histories)
    unknown_requested = sorted(wanted - set(names)) if wanted else []
    if wanted:
        names = [n for n in names if n in wanted]

    reports = [
        build_fill_type_report(n, histories[n], current, period["derived_from"]["currentDay"],
                               period["derived_from"]["daysPerPeriod"])
        for n in names
    ]

    emit({
        "file": os.path.join(savegame_dir, "economy.xml"),
        "current_period": period,
        "price_units": (
            "price_per_1000l is economy.xml's own raw number: it quotes price per 1000 "
            "LITRES, established by physical plausibility (OAT 460 read per-litre would "
            "value one combine's 76,772 L tank at $35 million). Multiply litres/1000 by it."
        ),
        "fill_type_count_with_prices": len(histories),
        "fill_types": reports,
        "requested_but_no_price_history": unknown_requested or None,
        "requested_but_no_price_history_note": (
            f"These fillTypes were requested via --fill-type but carry no <history> in "
            f"economy.xml: {unknown_requested}. That means NO PRICE DATA, not a price of 0. "
            "The game's own empty-slot sentinel 'UNKNOWN' is one of these by design."
        ) if unknown_requested else None,
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
