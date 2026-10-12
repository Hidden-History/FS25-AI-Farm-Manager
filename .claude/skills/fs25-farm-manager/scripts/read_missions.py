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
from xml_utils import load_xml, emit, arg_or_exit, finite_number

# ---------------------------------------------------------------------------
# THE LIVE REWARD (plan item 5a)
#
# The reward is not merely unparsed here -- it is ABSENT FROM THE SAVEGAME.
# AbstractMission:saveToXMLFile writes `.info#reward` straight from
# `self.reward`, and the game leaves that at 0 while a field-tied contract is
# only OFFERED, computing the real payout at accept-time (F-025). So the mod
# reads it live and writes it beside cards.xml, and this script merges it back.
#
# ==> THE JOIN IS `uniqueId`, NEVER A POSITION. <==
# Grounded, not recalled (FS25-Community-LUADOC @ 24afb18e7cfb,
# Missions/AbstractMission.md): `getUniqueId()` returns `self.uniqueId`, the
# same field `saveToXMLFile` writes to `key#uniqueId` -- i.e. exactly the
# `uniqueId` attribute this script already reads out of missions.xml. One
# origin, so the two halves cannot disagree. A positional merge would credit
# one contract's payout to another, silently and plausibly.
#
# The path is composed the way emit_farm_xml.py:453 composes farm.xml's --
# profile/modSettings/<MOD>/<savegameKey>/ -- so both halves derive the key
# from the same fact, basename(savegame_dir).
MOD_NAME = "FS25_AIFarmManager25"
CONTRACTS_NAME = "contracts.xml"
CONTRACTS_ROOT = "farmManager25Contracts"


def resolve_contracts_path(savegame_dir):
    """(path, savegame_key) for the mod-written live-reward store.

    A SIBLING of the savegame folder, never a child of it: the published
    promise (MODHUB-LISTING.md:48, "not once, not ever. 100% read-only") holds
    by construction because nothing here composes a path under savegame_dir.
    """
    savegame_dir = os.path.abspath(savegame_dir)
    key = os.path.basename(savegame_dir.rstrip("/\\"))
    return (os.path.join(os.path.dirname(savegame_dir), "modSettings",
                         MOD_NAME, key, CONTRACTS_NAME), key)


def load_live_rewards(path, expected_key):
    """Return (rewards, meta, error).

    `rewards` maps uniqueId -> float, and carries ONLY figures that survived
    every check. `error` is None on success AND on a file that simply is not
    there; it is a string for a file that exists but cannot be trusted.

    ⛔ ABSENT AND CORRUPT ARE DIFFERENT FACTS, and collapsing them would break
    this script in one direction or the other. No file is the NORMAL steady
    state -- the mod has not published yet, or is not installed -- and must not
    be an error, or every run of the skill fails. A file that exists and is
    unreadable IS an error: something wrote a document we cannot account for,
    and the caller must hear about it (non-zero exit) rather than receive a
    quietly reward-less answer that looks identical to the healthy case.

    Either way the REWARDS are the same: none. A contract with no trusted live
    figure reports UNKNOWN with its note, exactly as it does today.
    """
    meta = {"path": path}
    if not os.path.isfile(path):
        return {}, dict(meta, source="absent"), None

    root, generic = load_xml(path)
    if root is None:
        return {}, dict(meta, source="unreadable"), (
            "%s exists but could not be read: %s"
            % (path, generic.get("error", "unknown error")))

    if root.tag != CONTRACTS_ROOT:
        return {}, dict(meta, source="unreadable"), (
            "%s root is <%s>, expected <%s> -- that is not this mod's contract "
            "store, and its numbers are not merged." % (path, root.tag, CONTRACTS_ROOT))

    # ⛔ REFUSE ANOTHER SAVEGAME'S FIGURES. One mod install serves every save
    # (BUG-027, found live: savegame1's cards showed up in savegame3). A stale
    # file left under the wrong key would report one farm's payouts as another
    # farm's -- plausible, specific and wrong, which is the worst shape there is.
    # ⛔ AN ABSENT STAMP IS NOT CONSENT (TECH-DEBT-109). The guard below used to
    # read `if stamped is not None and ...`, so a file carrying NO savegame
    # attribute fell straight through and merged as though it had been checked
    # and matched. That is the BUG-027 shape -- rated CRITICAL -- and it is not
    # a hand-edit hypothesis: FarmManager25.lua writes the stamp CONDITIONALLY
    # (`if key ~= nil then`), so our own mod can produce an unstamped file.
    #
    # It is not refused outright, and the reason is that the PATH is a second,
    # independent provenance signal: resolve_contracts_path composes
    # modSettings/<MOD>/<savegameKey>/ from basename(savegame_dir), so an
    # unstamped file was at least found in this savegame's own directory.
    # Refusing would discard a probably-good figure; merging it silently would
    # make it indistinguishable from a verified one. So it is merged and
    # LABELLED, and the label travels with the numbers (see main()) rather
    # than sitting in a meta block a consumer never reads.
    stamped = root.get("savegame")
    stamp_verified = True
    if stamped is None:
        stamp_verified = False
    elif expected_key and stamped != expected_key:
        return {}, dict(meta, source="wrong-savegame"), (
            "%s is stamped savegame=%r but this run is reading %r -- refusing to "
            "merge another savegame's rewards." % (path, stamped, expected_key))

    rewards, rejected = {}, []
    for elem in root.findall("contract"):
        uid = elem.get("uniqueId")
        raw = elem.get("reward")
        if not uid:
            rejected.append({"uniqueId": uid, "reward": raw,
                             "why": "no uniqueId to join on"})
            continue
        # ⛔ FINITENESS BEFORE RANGE (TECH-DEBT-108). `float("nan") <= 0` is
        # False, so the range check below passes nan, inf and -inf and stamps
        # them `reward_source: "live"` -- this file's HIGHEST-confidence label
        # -- after which json.dumps writes a bare `NaN` and a strict consumer
        # fails on the entire snapshot. finite_number is the shared test
        # (xml_utils); the rejection is explicit and reasoned, never a drop.
        value = finite_number(raw)
        if value is None:
            rejected.append({"uniqueId": uid, "reward": raw,
                             "why": "reward is not a finite number"})
            continue
        # 0 is `AbstractMission:getReward()`'s literal return, so it means "this
        # mission type never overrode the base class" just as readily as it
        # means a payout -- and a hand-edited file has no writer to have
        # dropped it.
        # ⚠ A claim was REMOVED here, not annotated (DEC-132). It read "Two
        # independent refusals of the same wrong answer", counting the mod's
        # own `reward > 0` filter (FarmManager25.lua) as a second, independent
        # guard. It is neither: in Lua `inf > 0` is TRUE, so that filter shares
        # this one's exact blind spot. One premise counted twice is not
        # corroboration.
        if value <= 0:
            rejected.append({"uniqueId": uid, "reward": raw,
                             "why": "not a positive payout -- 0 is the engine's "
                                    "base-class constant, not a figure"})
            continue
        rewards[uid] = value

    meta.update(source="live" if stamp_verified else "live-unverified",
                contract_count=len(rewards))
    if not stamp_verified:
        meta["stamp_note"] = (
            "this store carries NO savegame attribute, so its identity could "
            "not be checked against %r -- only its directory ties it to this "
            "save. The figures are merged and every row that took one is "
            "labelled reward_source=\"live-unverified\" so it is never "
            "indistinguishable from a checked-and-matched file."
            % (expected_key,))
    if root.get("generatedAt"):
        meta["generated_at"] = root.get("generatedAt")
    if stamped:
        meta["savegame"] = stamped
    if rejected:
        meta["rejected"] = rejected
    return rewards, meta, None


def main():
    savegame_dir = arg_or_exit("read_missions.py <savegame_dir>")
    path = os.path.join(savegame_dir, "missions.xml")
    root, generic = load_xml(path)

    if root is None:
        emit({"error": generic.get("error", "unknown error reading missions.xml")})
        return 0

    contracts_path, savegame_key = resolve_contracts_path(savegame_dir)
    live_rewards, live_meta, live_error = load_live_rewards(contracts_path,
                                                            savegame_key)

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
            # ⛔ THE MERGE, AND THE HONESTY RULE IT MUST NOT WEAKEN. A live
            # figure is used ONLY for the contract that actually has one, keyed
            # by its own uniqueId. PER CONTRACT, NEVER PER FILE: one contract
            # gaining a number must not give the other thirteen one, and a
            # contract the mod could not read is still emitted, still counted,
            # and still says UNKNOWN. Never a silent 0, never a placeholder
            # that looks like a payout (DEC-001 / RSK-001).
            live = live_rewards.get(m["unique_id"])
            if live is not None:
                m["reward"] = live
                # TECH-DEBT-109: "live" only where the store proved which save
                # it belongs to. A caveat that lives only in a meta block is a
                # caveat a consumer reading this row will never see.
                m["reward_source"] = live_meta.get("source", "live")
                # The <info> dump still carries reward="0"; a reader who reaches
                # for mission["info"]["reward"] would read the placeholder and
                # miss the figure sitting one key away. Point it at the answer.
                if "info" in m and isinstance(m["info"], dict) and "reward" in m["info"]:
                    m["info"]["reward"] = (
                        f"{raw_reward} <- PLACEHOLDER. The real payout is "
                        f"{live}, read live from the game and merged into this "
                        "mission's `reward`. Raw value preserved in reward_raw."
                    )
            else:
                m["reward"] = None
                m["reward_source"] = "unknown"
                m["reward_note"] = (
                    "UNKNOWN, not zero. Field-tied rewards are computed by the game at "
                    "accept-time and are not written to the save while the contract is "
                    "only offered. Check the in-game contract screen for the real figure. "
                    "Never report this as $0."
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
            # A spot contract (tree transport, deadwood, rock clearing) carries
            # a real flat fee in the save. That is the authoritative figure and
            # the live store does not override it.
            # TECH-DEBT-108: guarded for the same reason the live path is,
            # and this label matters MORE -- "savegame" is the authoritative
            # one. An unparseable or non-finite flat fee is UNKNOWN, never a
            # number and never a silent 0 (DEC-001).
            fee = finite_number(raw_reward)
            if fee is None:
                m["reward"] = None
                m["reward_source"] = "unknown"
                m["reward_note"] = (
                    "UNKNOWN, not zero. This spot contract's flat fee is "
                    "%r in the save, which is not a finite number. The raw "
                    "value is preserved verbatim in reward_raw."
                    % (raw_reward,))
            else:
                m["reward"] = fee
                m["reward_source"] = "savegame"

        missions.append(m)

    out = {
        "file": path,
        "mission_count": len(missions),
        "missions": missions,
    }

    # ⚠ IN-BAND REPORT OF A DEGRADED MEASUREMENT. Where the rewards came from is
    # part of the answer, not a footnote: "no live store yet" and "a live store
    # we refused to read" produce identical reward fields, and only these keys
    # tell them apart.
    out["live_reward_source"] = live_meta.get("source")
    out["live_reward_store"] = live_meta
    if live_error:
        out["live_reward_error"] = live_error
    if scheduler_meta:
        out["scheduler_meta"] = scheduler_meta
        out["scheduler_meta_note"] = (
            "From <meta>: spawn-scheduler bookkeeping, deliberately EXCLUDED from "
            "mission_count -- these are not contracts the player can accept. "
            "Useful for planning (e.g. nextDay = when that contract type reappears)."
        )
    emit(out)
    # ⛔ FAIL LOUD, AND STILL EMIT THE DOCUMENT. The missions are good data and
    # throwing them away would punish the caller for a fault in a side channel
    # -- but a store we could not trust must never look like a clean run, so the
    # exit code carries the failure even though stdout carries an answer.
    # (collect_state.py reads stdout and ignores the status, so the snapshot
    # keeps working; a human or a gate running this directly sees the failure.)
    return 1 if live_error else 0


if __name__ == "__main__":
    sys.exit(main())
