"""
Check the fleet's fuel/damage tiers (via farm_snapshot.py) against the last
alerted state and push an individual, actionable in-game card for every NEW
threshold crossing -- never a repeat for a tier that hasn't gotten worse.

Usage: python3 check_fleet_alerts.py <savegame_dir> [--farm-id N]
    (--config PATH | --state PATH) [--dry-run]

ON BY DEFAULT, FOR EVERY PLAYER. The script reads its own switch from the
sanctum's config.json (top-level key `fleet_alerts_enabled`, see ALERTS_KEY):
a config with NO such key -- every sanctum made before the key existed --
counts as ON; `false` turns the alerts off (no card, no state file written,
exit 0, a structured {"status": "disabled", ...} naming the key); `true` is
the shipped default. Any other value is an error, never a silent ON or OFF.
The step files tell the manager to run this unless the switch is off; the
manager never decides that from prose. Deterministic thresholds instead of a
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
from cache_layout import paths_escape_savegame

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# How long the --fleet-only snapshot may run. It contains the resolver pass
# (`read_store_prices.py --fuel-capacity`, inner timeout
# farm_snapshot.FUEL_CAPACITY_TIMEOUT = 90 s, ~20 s measured live), so this MUST
# stay ABOVE that inner timeout: at 60 s a slow-but-healthy pass timed the alert
# check out first, a bigger failure than the degraded "fuel unavailable" the
# inner timeout is meant to produce.
SNAPSHOT_TIMEOUT = 120
# The state file lives in the CONFIGURED sanctum -- the directory holding the
# --config this run was given (same rule as generate_state.py) -- never in a
# "sanctum/" under the working directory. The old CWD-relative default created
# a stray sanctum/ wherever the script was run from (measured 2026-09-09:
# FS25/sanctum/fleet-alert-state.json), and run from inside a savegame folder
# it would break the published promise that nothing is written there.
STATE_FILENAME = "fleet-alert-state.json"

# F-210: the mod's poll cadence for a given session is unknown up front, and
# the default library timeout (2s) was proven too short once already. 10s
# matches the timeout that resolved F-210 on retry.
NOTIFY_TIMEOUT = 10.0

# The switch. Top level in config.json, boolean. ABSENT == ON (see docstring).
ALERTS_KEY = "fleet_alerts_enabled"

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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SNAPSHOT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, f"farm_snapshot.py --fleet-only timed out after {SNAPSHOT_TIMEOUT}s"
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


def resolve_state_path(state, config, savegame_dir):
    """(absolute path, None) or (None, error). Never falls back to the working
    directory: a --state is honoured as given, otherwise the file sits beside
    --config; with neither, the sanctum is unknown and that is an error."""
    if state:
        path = state
    elif config:
        if not os.path.isfile(config):
            return None, (
                f"--config {config!r} is not a file (relative paths resolve from the "
                f"working directory, {os.getcwd()!r}), so the sanctum that holds "
                f"{STATE_FILENAME} cannot be determined. Pass an absolute --config, "
                f"or --state explicitly.")
        path = os.path.join(os.path.dirname(os.path.abspath(config)), STATE_FILENAME)
    else:
        return None, (
            f"no --config and no --state: the sanctum that holds {STATE_FILENAME} "
            f"cannot be determined. Refusing to fall back to the working directory.")
    path = os.path.abspath(path)
    if paths_escape_savegame({"state": path}, savegame_dir):
        return None, (
            f"state path {path!r} is inside the savegame folder {savegame_dir!r}: "
            f"the manager writes nothing into the savegame folder.")
    return path, None


def read_switch(config_path):
    """(enabled, None) or (None, error). Absent key == ON; only a real boolean
    is accepted. No --config means there is nothing to read: ON. A config that
    is unreadable or not valid JSON, or a non-boolean value, is an error --
    the script never turns alerts on or off on a guess."""
    if not config_path:
        return True, None
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:  # ValueError: invalid JSON and non-UTF-8 bytes alike
        return None, f"cannot read the alert switch from --config {config_path!r}: {e}"
    if not isinstance(cfg, dict):
        return None, f"--config {config_path!r} is not a JSON object"
    if ALERTS_KEY not in cfg:
        return True, None
    value = cfg[ALERTS_KEY]
    if isinstance(value, bool):
        return value, None
    return None, (f"config.json key {ALERTS_KEY!r} must be true or false, got "
                  f"{value!r}; fix it or remove the key (absent means on).")


def parse_args(argv):
    opts = {"farm_id": 1, "config": None, "state": None, "dry_run": False}
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
        "check_fleet_alerts.py <savegame_dir> [--farm-id N] "
        "(--config PATH | --state PATH) [--dry-run]"
    )
    opts = parse_args(sys.argv[2:])

    state_path, err = resolve_state_path(opts["state"], opts["config"], savegame_dir)
    if err:
        emit({"error": err})
        sys.exit(1)

    enabled, err = read_switch(opts["config"])
    if err:
        emit({"error": err})
        sys.exit(1)
    if not enabled:
        emit({
            "status": "disabled",
            "key": ALERTS_KEY,
            "config": os.path.abspath(opts["config"]),
            "sent": [],
            "errors": [],
            "note": (f"Fleet fuel/repair alerts are switched off in config.json "
                     f"({ALERTS_KEY} is false). No card was sent and no state was "
                     f"written. Set it to true, or remove the key, to turn them on."),
        })
        return

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

    state = load_state(state_path)
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
        save_state(state_path, state)

    emit({
        "alerts_switch": ("on: no --config was given, so there is no config.json switch to read"
                          if not opts["config"] else f"on: {ALERTS_KEY} is true or absent"),
        "checked_day": day,
        "needs_attention_count": len(fleet.get("needs_attention") or []),
        "sent": sent,
        "errors": errors,
        "skipped_unknown": skipped_unknown,
        "state_path": state_path,
        "note": (
            "Cards are sent one at a time, each waiting for its own delivery outcome "
            "-- but the bridge is single-slot, so if the game was CLOSED for more "
            "than one crossing in this run, only the LAST card in `sent` actually reached "
            "disk; earlier ones were overwritten before anything could read them. This is a "
            "known bridge limitation, not a bug in this script."
        ) if len(sent) > 1 else None,
    })


if __name__ == "__main__":
    main()
