"""
Read per-selling-station price stats from placeables.xml.

Usage: python read_prices.py <savegame_dir>

VERIFIED against this save by running, 2026-07-16. The claim below was previously
sourced to "community reverse-engineering, GIANTS forum" -- it turned out to be
correct, but it was hearsay when written, and identical phrasing on
read_economy.py was flatly wrong and cost this project its worst bug (F-001).
Confidence borrowed from a forum is not confidence. This is now checked.

What was actually checked: 1,525 <stats> nodes in placeables.xml, e.g.
fillType="LIQUIDMANURE" received="0" paid="0" meanValue="0" isInPlateau="true"
plateauDuration="51840000" plateauTime="42276344", each with curveBaseCurve/curve1
children carrying amplitude/period.

CAVEAT worth more than the structure: on a never-traded farm every observed
meanValue is 0.000000 -- not because the crop is worthless, but because no
trade has ever happened at that station for that fill type. The nodes exist
and parse; they carry no price signal yet. That is the F-001/F-018/F-025
failure shape (absence looking like data), and until this fix it was live in
this script's own output: a caller reading price_stats[i]["mean_value"] got a
bare 0, indistinguishable from a genuinely-zero price. FIXED 2026-07-16 --
see main() below: mean_value is now null (with a note) whenever a stats node
shows no recorded trade (received == paid == 0), never a bare 0 standing in
for "unknown". The raw value is preserved in mean_value_raw regardless, so no
fidelity is lost -- only the trap of a reader mistaking placeholder-zero for
real-zero. For actual sell-price guidance, economy.xml's per-period price
history is the real, populated signal -- use that, not this file's meanValue,
for "what does this crop actually sell for."

Structure: selling stations save a <stats> node per fill type with fields like:
    <stats fillType="OAT" received="0.0" paid="0.0" priceVersion="1"
           isInPlateau="false" nextPlateauNumber="1" plateauDuration="..."
           meanValue="0.0" plateauTime="0.0">
        <curveBaseCurve .../> <curve1 .../>
    </stats>
The full sinusoidal pricing curve math is not practically reconstructable
(nobody's fully solved it), but meanValue and isInPlateau give a usable
"is this a good time/place to sell" signal without needing the exact formula.

This script pulls every <stats> node found anywhere in placeables.xml,
along with the filename of its enclosing placeable (the selling station),
so a briefing can compare stations for the same fill type.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit


def main():
    savegame_dir = arg_or_exit("read_prices.py <savegame_dir>")
    path = os.path.join(savegame_dir, "placeables.xml")
    root, generic = load_xml(path)

    if root is None:
        emit({"error": generic.get("error", "unknown error reading placeables.xml")})
        return

    stats_entries = []
    # Walk with a simple parent-tracking pass so we can note which placeable
    # (selling station) each <stats> node belongs to.
    parent_map = {c: p for p in root.iter() for c in p}

    def to_float(raw):
        """Parse an attribute string to float; None if missing/unparseable --
        never silently coerce a bad value to 0.0, that would be the exact
        failure this script is fixing elsewhere."""
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    never_traded_count = 0

    for elem in root.iter("stats"):
        if "fillType" not in elem.attrib:
            continue
        # Walk up to find the nearest ancestor with a "filename" attribute (the placeable)
        station_name = None
        node = elem
        while node in parent_map:
            node = parent_map[node]
            if "filename" in node.attrib:
                station_name = node.attrib["filename"]
                break

        mean_value_raw = elem.attrib.get("meanValue")
        received = to_float(elem.attrib.get("received"))
        paid = to_float(elem.attrib.get("paid"))

        # ever_traded distinguishes "no trade has happened here" from "this
        # crop is genuinely cheap" -- received/paid are real cumulative
        # totals (a true 0 there is a true fact: nothing bought or sold at
        # this station/fill type yet), so they're the signal that tells us
        # whether meanValue's own 0 is a placeholder or a real quote.
        ever_traded = bool((received or 0) != 0 or (paid or 0) != 0)

        entry = {
            "station": station_name,
            "fill_type": elem.attrib.get("fillType"),
            "mean_value_raw": mean_value_raw,
            "is_in_plateau": elem.attrib.get("isInPlateau"),
            "received": received,
            "paid": paid,
            "ever_traded": ever_traded,
        }

        if not ever_traded:
            never_traded_count += 1
            # NEVER surface a bare 0 here -- see FRICTION-LOG.md F-001/F-018/
            # F-025 for what happens when absence is left looking like data.
            # A caller must be unable to read this as "this crop sells for
            # $0" without also seeing why.
            entry["mean_value"] = None
            entry["mean_value_note"] = (
                "UNKNOWN, not zero. No trade has ever been recorded at this station for "
                "this fill type (received and paid are both 0), so meanValue is an "
                "uninitialized placeholder, not a price. Never report this as a $0 "
                "sell price (FRICTION-LOG.md F-001/F-018/F-025 -- absence looking like "
                "data). Use economy.xml's per-period price history for real sell-price "
                "guidance instead."
            )
        else:
            entry["mean_value"] = to_float(mean_value_raw)

        stats_entries.append(entry)

    out = {
        "file": path,
        "price_stat_count": len(stats_entries),
        "price_stats": stats_entries,
        "calibration_needed": len(stats_entries) == 0,
        "note": "meanValue and isInPlateau are directional signals, not exact predicted "
                "sell prices -- treat as 'this station/fill type looks favorable right now' "
                "rather than a precise quote, and only once ever_traded is true.",
    }

    # Loud, top-level statement when the WHOLE file carries no trading
    # signal at all -- this is a fact about the farm (nothing has ever been
    # sold/bought anywhere), not a fact about crop prices, and it must not
    # be left for a caller to infer by noticing 1,525 identical zeroes.
    if stats_entries and never_traded_count == len(stats_entries):
        out["all_stations_untraded"] = True
        out["all_stations_untraded_note"] = (
            f"All {len(stats_entries)} price-stat nodes show no recorded trade. This means "
            "no sale or purchase has happened at ANY selling station yet -- it says nothing "
            "about whether any crop is valuable. Every mean_value in price_stats is null for "
            "exactly this reason. Do not report any crop as cheap or worthless from this "
            "file; use economy.xml's per-period price history for real sell-price guidance."
        )
    elif stats_entries:
        out["all_stations_untraded"] = False
        out["untraded_stat_count"] = never_traded_count

    emit(out)


if __name__ == "__main__":
    main()
