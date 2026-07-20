"""
Read missions.xml -> active contracts (harvest/transport/etc missions).

Usage: python read_missions.py <savegame_dir>

VERIFIED against this save by running, 2026-07-16 (not "community-verified" --
that phrasing, borrowed from a forum rather than earned by a run, is exactly what
caused F-001: read_economy.py claimed a "community-verified" structure that does
not exist in FS25, and the resulting silent wrong answer cost three rewritten
sanctum files and one reversed player decision. Trust a run, not a claim.)

What was actually checked here: 15 real contracts, each a direct child of
<missions> with status="CREATED"; the <meta> block excluded (see below); field ids
and endDate/endDay read back against the raw XML by hand.

Structure:
    <harvestMission uniqueId="..." status="CREATED" finishState="NONE">
        <harvest fruitType="PARSNIP" expectedLiters="0" depositedLiters="0" .../>
        <info reward="0" reimbursement="0" completion="0"/>
        <endDate endDay="182" endDayTime="86399999"/>
        <field id="88"/>
    </harvestMission>
Other mission types (transport, cultivation, etc.) likely follow a similar
pattern with a different root tag ending in "Mission" -- this script grabs
any tag ending in "Mission" generically.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit


def main():
    savegame_dir = arg_or_exit("read_missions.py <savegame_dir>")
    path = os.path.join(savegame_dir, "missions.xml")
    root, generic = load_xml(path)

    if root is None:
        emit({"error": generic.get("error", "unknown error reading missions.xml")})
        return

    # Iterate DIRECT CHILDREN only, never root.iter() -- the tree contains a
    # <meta> block holding a scheduler note that looks exactly like a mission:
    #     <meta><destructibleRockMission nextDay="14"/></meta>
    # That is "when does the next rock contract spawn", NOT an offer the player
    # can accept. root.iter() swept it in and inflated the count 15 -> 16.
    # See FRICTION-LOG.md F-025. The tell was its missing status attribute.
    missions = []
    scheduler_meta = {}

    for elem in root:
        if elem.tag == "meta":
            for note in elem:
                scheduler_meta[note.tag] = dict(note.attrib)
            continue
        if not elem.tag.endswith("Mission"):
            continue

        m = {"type": elem.tag, "unique_id": elem.attrib.get("uniqueId"),
             "status": elem.attrib.get("status"), "finish_state": elem.attrib.get("finishState")}
        for child in elem:
            m[child.tag] = dict(child.attrib)

        field_elem = elem.find("field")
        m["field_id"] = field_elem.get("id") if field_elem is not None else None

        info = elem.find("info")
        raw_reward = info.get("reward") if info is not None else None
        m["reward_raw"] = raw_reward
        # A field-tied contract reads reward="0" because the game computes the
        # payout at accept-time and never writes it while the offer is merely
        # posted. That is UNKNOWN, not zero. Spot contracts (tree transport,
        # deadwood, rock clearing) DO carry real flat fees -- which is how we
        # know 0 is a placeholder and not missing data. Reporting "$0" would
        # talk the player out of the only work their fleet can do. F-025.
        if raw_reward in (None, "0", "0.000000"):
            m["reward"] = None
            m["reward_note"] = (
                "UNKNOWN, not zero. Field-tied rewards are computed by the game at "
                "accept-time and are not written to the save while the contract is "
                "only offered. Check the in-game contract screen for the real figure. "
                "Never report this as $0 (FRICTION-LOG.md F-025)."
            )
            # The raw <info> child dump above carries reward="0" too. A reader who
            # reaches for mission["info"]["reward"] instead of mission["reward"]
            # would see a bare "0" and report it as a payout -- the correction
            # sitting in a sibling key doesn't help someone who never looks at it.
            # Overwrite that one value in place with something unmistakable. The
            # original is preserved verbatim in reward_raw above, so no fidelity is
            # lost; only the trap is removed. A fix you have to NOTICE isn't a fix.
            if "info" in m and isinstance(m["info"], dict) and "reward" in m["info"]:
                m["info"]["reward"] = (
                    f"{raw_reward} <- PLACEHOLDER, NOT A PAYOUT. See this mission's "
                    "reward_note. Raw value preserved in reward_raw."
                )
        else:
            m["reward"] = float(raw_reward)

        missions.append(m)

    out = {
        "file": path,
        "mission_count": len(missions),
        "missions": missions,
    }
    if scheduler_meta:
        out["scheduler_meta"] = scheduler_meta
        out["scheduler_meta_note"] = (
            "From <meta>: spawn-scheduler bookkeeping, deliberately EXCLUDED from "
            "mission_count -- these are not contracts the player can accept. "
            "Useful for planning (e.g. nextDay = when that contract type reappears)."
        )
    emit(out)


if __name__ == "__main__":
    main()
