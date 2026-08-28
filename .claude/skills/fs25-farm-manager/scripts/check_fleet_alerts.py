"""
Check the fleet's fuel/damage tiers (via farm_snapshot.py) against the last
alerted state and push an individual, actionable in-game card for every NEW
threshold crossing -- never a repeat for a tier that hasn't gotten worse.

Usage: python3 check_fleet_alerts.py <savegame_dir> [--farm-id N] [--config PATH]
    [--state PATH] [--dry-run]

House rule (set 2026-07-24, player asked directly -- see
sanctum/config.json house_rules.fuel_and_repair_alerts and
sanctum/identity/decision-making.md): deterministic thresholds instead of a
judgment call every session --
    fuel remaining  <=50% minor (yellow/warn) / <=25% severe (red/critical)
    damage (worn)   >=50% minor (yellow/warn) / >=75% severe (red/critical)
(tiers computed in farm_snapshot.py's build_fleet -- this script only reacts
to them.)

DEDUP, NOT SPAM -- the whole point of this script. A vehicle stuck below a
threshold for days must alert ONCE, not on every check. sanctum/fleet-alert-
state.json remembers the last tier alerted per vehicle per metric; a card
only fires when the CURRENT tier is WORSE than the last one alerted
(none -> minor -> severe). Recovering (refuel/repair) resets the recorded
tier silently -- no card for good news -- so a later decline can alert again.

KNOWN vs UNKNOWN, not just "not in trouble": a vehicle/metric this run
couldn't confidently read (e.g. fuel capacity unresolved, or the whole
fuel_capacity_status is "unavailable" because no config.json path was given)
must NEVER be treated as "recovered". farm_snapshot.py's per-vehicle
`fuel_known`/`damage_known` flags exist exactly so this script can tell
"confirmed fine" from "don't know this run" -- only the former resets a
recorded tier. Collapsing those two would silently erase real alert history
on a transient data hiccup, the same absence-as-data bug this whole skill is
built to avoid.

ONE CARD PER WARNING, ALWAYS (player's rule, 2026-07-24) -- these are an
in-game todo list, never batched into one combined message. Each gets an
`ack` action (same reply-ledger plumbing this skill already uses for other
cards -- see sanctum/replies-ledger.json) and a card id that includes the
in-game day it was raised. The day suffix matters: without it, a real
recurrence weeks later (refuel/repair, then decline again) would reuse the
exact same id, and read_replies.py's (id, action) dedup would silently
swallow the second real ack as "already seen".

SEQUENTIAL SENDS, LONGER TIMEOUT -- see FRICTION-LOG.md F-210. The bridge
(notify.xml) is SINGLE-SLOT: a second notify_farm_manager.py call overwrites
the first message before the mod's poll cycle can read it. F-210 already
paid for this lesson once (3 rapid cards, all lost). This script sends one
at a time and waits for each outcome (a longer --timeout than the library's
2s default, matching F-210's fix) before sending the next -- while the game
is running that's enough for the mod's ~200ms poll to consume each one in
turn. If the game is CLOSED for multiple crossings in the same run, only the
LAST card written survives on disk; earlier ones are gone. That is a real,
known limitation of the existing bridge protocol, not something this script
can fix -- surfaced in this run's own JSON output (see `note` below), not
hidden.

PRE-SEND IS FINE (player confirmed 2026-07-24): a card written while the
game isn't running just sits on disk and shows when the player next loads
in, per notify_farm_manager.py's own delivery model. This script does not
gate on "is this live play" -- it only gates on "is this a NEW crossing".
It's wired into BR (session start) and the live wait_for_event loop, NOT
ST/PL/PR, which are read-only by design and must not write the state file
(see references/workflow-briefing.md).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import emit, arg_or_exit
from notify_farm_manager import send_notification, BridgeError

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_PATH = os.path.join("sanctum", "fleet-alert-state.json")

# F-210: the mod's poll cadence for a given session is unknown up front, and
# the default library timeout (2s) was proven too short once already. 10s
# matches the timeout that resolved F-210 on retry.
NOTIFY_TIMEOUT = 10.0

SEVERITY_BY_TIER = {"minor": "warn", "severe": "critical"}
TITLE_BY_METRIC = {"fuel": "Fuel", "damage": "Repair"}
ICON_BY_METRIC = {"fuel": "fuel", "damage": "equipment"}
TIER_RANK = {None: 0, "minor": 1, "severe": 2}


def call_snapshot(savegame_dir, farm_id, config_path):
    # --fleet-only (added 2026-07-24 alongside this script): the full digest
    # composes ~11 subprocess calls and measured 55-90s on this install's
    # WSL-mounted drive (dominated by --gaps's base-game XML scan, which this
    # check never needs) -- --fleet-only calls just the 3 parsers `fleet`
    # actually needs, ~10-15s, which matters a lot if this runs on every
    # savegame write during live play.
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "farm_snapshot.py"),
           savegame_dir, "--farm-id", str(farm_id), "--fleet-only"]
    if config_path:
        cmd += ["--config", config_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "farm_snapshot.py --fleet-only timed out after 60s"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        return None, (
            f"farm_snapshot.py produced non-JSON output (exit {result.returncode}): "
            f"{(result.stderr or result.stdout)[:300]}"
        )


def load_state(path):
    if not os.path.isfile(path):
        return {"vehicles": {}}
    try:
        with open(path, "r") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"vehicles": {}}
    state.setdefault("vehicles", {})
    return state


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def format_message(row, metric, day):
    name = row.get("name") or row.get("filename") or row.get("unique_id")
    day_bit = f" (day {day})" if day is not None else ""
    if metric == "fuel":
        pct = row.get("fuel_fraction")
        pct_txt = f"{pct:.0%} remaining" if pct is not None else "low"
        return f"{name}: fuel {pct_txt}{day_bit}."
    pct = row.get("damage_fraction")
    pct_txt = f"{pct:.0%} worn" if pct is not None else "high wear"
    return f"{name}: {pct_txt}{day_bit}."


def parse_args(argv):
    opts = {"farm_id": 1, "config": None, "state": DEFAULT_STATE_PATH, "dry_run": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--farm-id":
            opts["farm_id"] = int(argv[i + 1]); i += 2
        elif a == "--config":
            opts["config"] = argv[i + 1]; i += 2
        elif a == "--state":
            opts["state"] = argv[i + 1]; i += 2
        elif a == "--dry-run":
            opts["dry_run"] = True; i += 1
        else:
            i += 1
    return opts


def main():
    savegame_dir = arg_or_exit(
        "check_fleet_alerts.py <savegame_dir> [--farm-id N] [--config PATH] "
        "[--state PATH] [--dry-run]"
    )
    opts = parse_args(sys.argv[2:])

    snapshot, err = call_snapshot(savegame_dir, opts["farm_id"], opts["config"])
    if err or snapshot is None:
        emit({"error": err or "farm_snapshot.py returned nothing"})
        return

    fleet = snapshot.get("fleet") or {}
    if fleet.get("status") != "ok":
        emit({"error": f"fleet section unavailable: {fleet.get('reason')}", "sent": []})
        return

    day = (snapshot.get("when") or {}).get("in_game_day")
    rows_by_id = {r.get("unique_id"): r for r in (fleet.get("vehicles") or [])}

    state = load_state(opts["state"])
    vehicles_state = state["vehicles"]

    # Every (unique_id, metric) touched either by this check or by prior
    # state, so a full recovery (vehicle no longer even present, or its tier
    # dropped to None) is considered too, not just new/worse crossings.
    all_keys = set()
    for uid, row in rows_by_id.items():
        if row.get("damage_known"):
            all_keys.add((uid, "damage"))
        if row.get("fuel_known"):
            all_keys.add((uid, "fuel"))
    for uid, v in vehicles_state.items():
        if v.get("damage_tier"):
            all_keys.add((uid, "damage"))
        if v.get("fuel_tier"):
            all_keys.add((uid, "fuel"))

    sent = []
    errors = []
    skipped_unknown = []

    for uid, metric in sorted(all_keys):
        row = rows_by_id.get(uid)
        known = bool(row and row.get(f"{metric}_known"))
        entry = vehicles_state.setdefault(uid, {})
        tier_field = f"{metric}_tier"
        last_tier = entry.get(tier_field)

        if not known:
            # Genuinely don't know this run (row missing, or its capacity/
            # damage couldn't be resolved) -- never treat silence as recovery.
            skipped_unknown.append({"unique_id": uid, "metric": metric, "last_tier": last_tier})
            continue

        new_tier = row.get(tier_field)

        if TIER_RANK[new_tier] > TIER_RANK[last_tier]:
            card_id = f"{metric}-{new_tier}-{uid}-d{day if day is not None else 'unknown'}"
            message = format_message(row, metric, day)
            severity = SEVERITY_BY_TIER[new_tier]
            title = TITLE_BY_METRIC[metric]
            icon = ICON_BY_METRIC[metric]
            if opts["dry_run"]:
                sent.append({"card_id": card_id, "message": message, "severity": severity, "dry_run": True})
            else:
                try:
                    outcome, _ = send_notification(
                        message, severity=severity, title=title, icon=icon,
                        timeout=NOTIFY_TIMEOUT, config=opts["config"],
                        card_id=card_id, actions=[{"type": "ack"}], quiet=True,
                    )
                    sent.append({"card_id": card_id, "message": message, "severity": severity, "outcome": outcome})
                except BridgeError as e:
                    errors.append({"card_id": card_id, "error": str(e)})
            entry[tier_field] = new_tier
        elif TIER_RANK[new_tier] < TIER_RANK[last_tier]:
            # Confirmed recovery (refuel/repair) -- reset silently, no card.
            entry[tier_field] = new_tier

    # Prune vehicles with nothing active on either metric to keep the file small.
    for uid in list(vehicles_state.keys()):
        v = vehicles_state[uid]
        if not v.get("fuel_tier") and not v.get("damage_tier"):
            del vehicles_state[uid]

    if not opts["dry_run"]:
        save_state(opts["state"], state)

    emit({
        "checked_day": day,
        "needs_attention_count": len(fleet.get("needs_attention") or []),
        "sent": sent,
        "errors": errors,
        "skipped_unknown": skipped_unknown,
        "state_path": opts["state"],
        "note": (
            "Cards are sent one at a time, each waiting for its own delivery outcome "
            "(F-210) -- but the bridge is single-slot, so if the game was CLOSED for more "
            "than one crossing in this run, only the LAST card in `sent` actually reached "
            "disk; earlier ones were overwritten before anything could read them. This is a "
            "known bridge limitation, not a bug in this script."
        ) if len(sent) > 1 else None,
    })


if __name__ == "__main__":
    main()
