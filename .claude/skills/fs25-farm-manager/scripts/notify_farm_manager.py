#!/usr/bin/env python3
"""
notify_farm_manager.py

Send an on-screen notification into Farming Simulator 25 via the "AI Farm
Manager 25" mod's bridge file.

    python3 notify_farm_manager.py "Silo 3 is almost full"
    python3 notify_farm_manager.py --severity warn --title Market \
        "Oat is at its annual low: $431/1000L, peaks $644 on day 11."

    from notify_farm_manager import send_notification
    send_notification("Field 61 is ripe", severity="warn", title="Harvest")

---------------------------------------------------------------------------
HOW DELIVERY IS PROVEN
---------------------------------------------------------------------------
The mod consumes a message by deleting the bridge file (or, if the engine sandbox
refuses the delete, by emptying it to <farmManager25/>). Either way the message is
gone from disk because the game read it -- a real receipt. So this script waits
for it and reports one of three OUTCOMES, never a bare success:

    delivered      the file went empty -- the mod has the message   (exit 0)
    not consumed   we wrote it; nothing picked it up                (exit 2)
    error          we could not even find where to write            (exit 1)

"not consumed" is never explained away. The previous version printed
"game may not be running to display it" for EVERY unconsumed write -- a
confident, plausible, unverified cause. It was wrong: the game was running and
the message had been written to a directory the game cannot see. A guessed cause
is worse than no cause, because it stops you looking. We report what we OBSERVED
(the mod is/isn't installed; the save's mtime) and let the reader conclude.

---------------------------------------------------------------------------
WHY THE BRIDGE IS XML (protocol 2)
---------------------------------------------------------------------------
Protocol 1 wrote plain text to notify.txt. The mod could never read it: FS25
sandboxes io to write-only, so io.open(path, "r") returns a table with no read
method AND opens the file for writing, which then blocks the next open with a
sharing violation. The engine XML API is the only sanctioned way for a mod to
read a file, so the bridge is XML.

Body lines are separate <line> elements rather than one newline-joined string,
so nothing depends on whether the engine's XML reader preserves newlines inside
element text.

---------------------------------------------------------------------------
WHY THE PATH IS DERIVED AND NEVER GUESSED
---------------------------------------------------------------------------
Under WSL, os.name == "posix", so the old expanduser("~")/Documents fallback
resolved to /home/<user>/Documents/My Games/... -- a Linux path FS25 has never
heard of. It then os.makedirs()'d that path, so every write "succeeded" into a
directory nothing reads. Silent, permanent, invisible.

So: resolve from sanctum/config.json (paths.game_data_dir), which the farm-manager
skill already verifies. Fall back to WSL/Windows detection only if that is
absent. And REFUSE to create the folder tree at a location that doesn't already
look like an FS25 profile -- if we can't find the real one, that is an error to
report, not a directory to invent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

PROTOCOL = 4
# FS25 sandboxes a mod to modSettings/<MOD NAME>/ -- the mod name being the zip's
# filename stem. The mod derives it from g_currentModName; we must arrive at the
# same string or we write somewhere the game refuses to touch. test_bridge_folder_
# matches_the_mod_name asserts these agree with the actual built zip.
MOD_NAME = "FS25_AIFarmManager25"
BRIDGE_SUBPATH = ("modSettings", MOD_NAME, "notify.xml")
MOD_ZIP_NAME = MOD_NAME + ".zip"

SEVERITIES = ("ok", "info", "warn", "critical")
DEFAULT_SEVERITY = "info"
DEFAULT_TITLE = "Farm Manager"

# Protocol-4 actionable cards. Types and the cap MIRROR the mod's parser
# (FarmManager25.lua parseActions, MAX_ACTIONS) -- but where the mod is
# SILENT (drops actions without an id, truncates past the cap), the sender
# fails LOUD: a card that would lose its affordances in-game is a bug worth
# an error at send time, not a mystery in the game log.
ACTION_TYPES = ("yesno", "ack", "text", "choice")
MAX_ACTIONS = 6                      # per card; also bounds options per action

# Glyphs in the mod's atlas. MIRRORS build_atlas.py's ICON_ORDER and the ICONS
# table in FarmManager25.lua -- test_icon_names_agree_across_all_three asserts all
# three still match. Omitting it uses the severity's default, so an icon is
# decoration and never a reason for a message not to show.
ICONS = (
    "leaf",
    "alert",
    "check",
    "briefing",
    "contract",
    "silo",
    "fleet",
    "finances",
    "crop",
    "weather",
    "harvest",
    "field",
    "report",
    "equipment",
    "fuel",
    "building",
    "supply",
    "schedule",
    "profit",
    "worker",
    "dealer",
    "soil",
    "season",
    # Interaction affordances (TASK-101 P1) -- appended after every pre-existing
    # glyph, matching build_atlas.py's append-only ICON_ORDER.
    "thumb_up",
    "thumb_down",
    "chat",
    "send",
    "gear",
    "close",
    # TASK-101 P2 (owner icon sheet 4) -- same append-only rule, slots 29/30.
    "snooze",
    "critical",
)


# Exit codes
EXIT_DELIVERED = 0
EXIT_ERROR = 1
EXIT_NOT_CONSUMED = 2


class BridgeError(RuntimeError):
    """We could not determine where to write. Never silently invented."""


# ---------------------------------------------------------------------------
# path resolution
# ---------------------------------------------------------------------------

def _find_config(start: Optional[Path] = None) -> Optional[Path]:
    """Walk up from `start` looking for sanctum/config.json."""
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        candidate = d / "sanctum" / "config.json"
        if candidate.is_file():
            return candidate
    return None


def _profile_dir_from_config(config_path: Path) -> Optional[Path]:
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    # Preferred: the explicit, already-verified profile dir.
    p = (cfg.get("paths") or {}).get("game_data_dir")
    if p and Path(p).is_dir():
        return Path(p)

    # Fallback: the savegame's parent IS the profile dir.
    sg = cfg.get("savegame_path")
    if sg and Path(sg).parent.is_dir():
        return Path(sg).parent
    return None


def _profile_dir_by_detection() -> Optional[Path]:
    """Only used when there's no config. Every candidate must ALREADY exist."""
    candidates = []

    if os.name == "nt":
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            candidates.append(Path(userprofile) / "Documents" / "My Games" / "FarmingSimulator2025")
    else:
        # WSL: the Windows profile lives under /mnt/<drive>/Users/<name>.
        # NOT expanduser("~") -- that is the Linux home, which FS25 cannot see.
        for drive in ("c", "d", "e"):
            users = Path(f"/mnt/{drive}/Users")
            if not users.is_dir():
                continue
            try:
                for user in users.iterdir():
                    candidates.append(user / "Documents" / "My Games" / "FarmingSimulator2025")
            except OSError:
                continue
        # Native Linux / Proton prefixes
        candidates.append(Path.home() / "Documents" / "My Games" / "FarmingSimulator2025")

    for c in candidates:
        if c.is_dir():
            return c
    return None


def resolve_profile_dir(config: Optional[str] = None) -> Path:
    if config:
        cfg_path = Path(config)
        if not cfg_path.is_file():
            raise BridgeError(f"--config given but not found: {cfg_path}")
        p = _profile_dir_from_config(cfg_path)
        if p is None:
            raise BridgeError(f"{cfg_path} has no usable paths.game_data_dir / savegame_path")
        return p

    found = _find_config()
    if found is not None:
        p = _profile_dir_from_config(found)
        if p is not None:
            return p

    p = _profile_dir_by_detection()
    if p is not None:
        return p

    raise BridgeError(
        "cannot locate the FS25 profile folder (the one containing modSettings/ and savegame1/).\n"
        "  Looked for: sanctum/config.json -> paths.game_data_dir, then /mnt/*/Users/*/Documents/My Games/FarmingSimulator2025.\n"
        "  Pass --bridge /path/to/notify.xml or --config /path/to/config.json.\n"
        "  Refusing to create a guessed folder: that is exactly how the old version wrote\n"
        "  every notification into a directory the game cannot see, and reported success."
    )


def get_bridge_path(config: Optional[str] = None, bridge: Optional[str] = None) -> Path:
    if bridge:
        return Path(bridge)
    env = os.environ.get("FS25_BRIDGE")
    if env:
        return Path(env)

    profile = resolve_profile_dir(config)
    if not (profile / "modSettings").is_dir() and not (profile / "savegame1").is_dir():
        raise BridgeError(
            f"{profile} does not look like an FS25 profile folder "
            f"(no modSettings/ and no savegame1/). Refusing to write there."
        )

    path = profile.joinpath(*BRIDGE_SUBPATH)
    # Creating modSettings/FarmManager25/ under a VERIFIED profile dir is safe;
    # the mod creates it too. We only ever makedirs somewhere already proven real.
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# sending
# ---------------------------------------------------------------------------

def _validate_actions(actions, card_id) -> None:
    """Fail-loud gate for the <actions> block. Everything refused here would
    be SILENTLY lost or truncated by the mod (MUST-carry-id drop; the
    MAX_ACTIONS bound on both loops) -- surface it at send instead."""
    if not card_id:
        raise BridgeError("actions require an id: the mod drops <actions> on a "
                          "card without one (MUST-carry-id rule); pass card_id/--id")
    if len(actions) > MAX_ACTIONS:
        raise BridgeError(f"{len(actions)} actions exceed the mod's cap of "
                          f"{MAX_ACTIONS}; the excess would be silently truncated")
    for a in actions:
        a_type = a.get("type")
        if a_type not in ACTION_TYPES:
            raise BridgeError(f"unknown action type {a_type!r}; expected one of "
                              f"{', '.join(ACTION_TYPES)}")
        options = a.get("options")
        if a_type == "choice":
            if not options:
                raise BridgeError("a choice action needs options: [(value, label), ...]")
            if len(options) > MAX_ACTIONS:
                raise BridgeError(f"{len(options)} options exceed the mod's cap of "
                                  f"{MAX_ACTIONS}; the excess would be silently truncated")
            for opt in options:
                if (not isinstance(opt, (tuple, list)) or len(opt) != 2
                        or not all(isinstance(x, str) for x in opt)):
                    raise BridgeError(f"malformed option {opt!r}: expected a "
                                      "(value, label) pair of strings")
        elif options:
            raise BridgeError(f"options are only valid on a choice action, not {a_type!r} "
                              "(the encoder would silently drop them)")


def _encode(message: str, severity: str, title: str, ttl_ms: int, icon: str = "",
            card_id: str = None, actions: list = None) -> str:
    """
    Build the XML payload. See FarmManager25.lua for the grammar. Protocol 4
    is ADDITIVE: card_id/actions default to None, and a call without them
    produces byte-identical protocol-3 output.

    Uses ElementTree rather than string formatting so escaping is the stdlib's
    problem, not mine: a farm message legitimately contains & and $ and quotes
    ("Oat & wheat", 'the "cheap" seeder'), and hand-rolled XML would corrupt the
    first one of those it met. Protocol 1's pipe-delimited header had to strip
    pipes from titles for the same reason; XML just carries them.
    """
    severity = (severity or DEFAULT_SEVERITY).lower()
    if severity not in SEVERITIES:
        raise BridgeError(f"unknown severity {severity!r}; expected one of {', '.join(SEVERITIES)}")
    # Checked here rather than in _validate_actions so an id-only card (legal
    # protocol 4, no actions) gets the same clean refusal instead of a
    # TypeError inside ElementTree.
    if card_id is not None and not isinstance(card_id, str):
        raise BridgeError(f"card_id must be a string, got {type(card_id).__name__}")
    if actions:
        _validate_actions(actions, card_id)

    body = message.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not body:
        raise BridgeError("refusing to send an empty notification")

    root = ET.Element("farmManager25")
    note = ET.SubElement(root, "notification")
    if card_id:
        note.set("id", card_id)
    note.set("severity", severity)
    note.set("title", (title or DEFAULT_TITLE).strip() or DEFAULT_TITLE)
    if ttl_ms:
        note.set("ttl", str(int(ttl_ms)))
    if icon:
        if icon not in ICONS:
            raise BridgeError(f"unknown icon {icon!r}; expected one of {', '.join(ICONS)}")
        note.set("icon", icon)

    for line in body.split("\n"):
        # Blank lines are written too. The mod distinguishes "no such element"
        # from "element with no text" via hasProperty, so a blank line in the
        # middle of a message survives instead of truncating it.
        ET.SubElement(note, "line").text = line

    if actions:
        block = ET.SubElement(note, "actions")
        for a in actions:
            el = ET.SubElement(block, "action")
            el.set("type", a["type"])
            for value, label in a.get("options") or ():
                opt = ET.SubElement(el, "option")
                opt.set("value", value)
                opt.text = label

    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode")


def _atomic_write(path: Path, payload: str) -> None:
    """
    Write via temp file + os.replace, in the SAME directory so the rename is
    atomic. The mod polls every 200ms; a plain open(w) truncates and then
    writes, so a poll landing in that gap reads an empty or half-written file.
    os.replace makes the message appear whole or not at all.
    """
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".notify-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_consumed(path: Path) -> bool:
    """
    The delivery receipt. The mod consumes a message by deleting the bridge --
    but deleteFile is refused by the engine sandbox on some setups, so it falls
    back to overwriting the file with an empty <farmManager25/>. BOTH mean
    consumed, so the receipt must accept both: the file is gone, OR it no longer
    carries a <notification>.

    Checking only for absence would report "not consumed" for a message the
    player had already read -- a false negative that would have us re-send.
    """
    if not path.exists():
        return True
    try:
        return "<notification" not in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _observe_environment(path: Path) -> list[str]:
    """
    Facts, not a diagnosis. We report what we can SEE and let the reader
    conclude. Guessing the cause is how the old version claimed the game
    wasn't running while it was.
    """
    notes = []
    profile = path.parent.parent.parent  # .../FarmingSimulator2025
    mods = profile / "mods"
    mod_present = False
    if mods.is_dir():
        mod_present = (mods / MOD_ZIP_NAME).is_file() or any(
            p.name.lower().startswith("fs25_aifarmmanager") or p.name.lower().startswith("fs25_farmmanager")
            for p in mods.iterdir()
        )
    notes.append(
        f"the mod IS present in {mods}" if mod_present
        else f"the mod is NOT in {mods} -- it cannot consume anything until installed and enabled"
    )

    # careerSavegame.xml, NOT savegame.xml -- there is no such file. The first
    # version of this globbed for savegame.xml, matched nothing, and the mtime
    # note silently disappeared from the report. An empty glob that removes a
    # line is indistinguishable from "no saves exist": F-001's exact shape,
    # inside the function whose whole job is to report facts honestly. So an
    # empty result now SAYS it found nothing rather than going quiet.
    saves = sorted(profile.glob("savegame*/careerSavegame.xml"))
    if saves:
        newest = max(saves, key=lambda p: p.stat().st_mtime)
        age = (time.time() - newest.stat().st_mtime) / 60.0
        notes.append(f"newest save wrote {age:.0f} min ago ({newest.parent.name})")
        notes.append(
            "  (save mtime does NOT prove the game is closed: FS25 defers the write "
            "until the player next opens the map -- see FRICTION-LOG F-023)"
        )
    else:
        notes.append(f"found no savegame*/careerSavegame.xml under {profile} -- unexpected; not inferring anything from it")
    return notes


def send_notification(
    message: str,
    severity: str = DEFAULT_SEVERITY,
    title: str = DEFAULT_TITLE,
    ttl_ms: int = 0,
    icon: str = "",
    timeout: float = 2.0,
    config: Optional[str] = None,
    bridge: Optional[str] = None,
    quiet: bool = False,
    card_id: Optional[str] = None,
    actions: Optional[list] = None,
) -> Tuple[str, Path]:
    """
    Returns (outcome, path) where outcome is "delivered" or "not_consumed".
    Raises BridgeError if the destination cannot be resolved.

    Protocol 4: pass card_id (a stable correlation id) and actions -- a list
    of {"type": "yesno"|"ack"|"text"} or {"type": "choice", "options":
    [(value, label), ...]} -- to send an actionable card the player can
    answer in-game; the answer lands in replies.xml (read_replies.py ingests
    it). Actions require card_id: the reply carries the id back.

    NOTE: "delivered" means the mod READ the message. It does not prove the
    player saw it -- nothing on disk can prove that.
    """
    path = get_bridge_path(config=config, bridge=bridge)
    _atomic_write(path, _encode(message, severity, title, ttl_ms, icon,
                                card_id=card_id, actions=actions))

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.05)
        if _is_consumed(path):
            if not quiet:
                print(f"delivered: the mod consumed the message ({severity}) -- {message!r}")
            return "delivered", path

    if not quiet:
        print(f"NOT CONSUMED after {timeout:.1f}s: {message!r}")
        print(f"  written to: {path}")
        print("  the bridge file still carries the message, so nothing in the game has read it.")
        for note in _observe_environment(path):
            print(f"  - {note}")
        print("  Not guessing a cause -- those are the facts.")
    return "not_consumed", path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Send an on-screen notification into FS25.")
    ap.add_argument("message", nargs="+", help="the notification text")
    ap.add_argument("--severity", "-s", default=DEFAULT_SEVERITY, choices=SEVERITIES,
                    help="accent colour + native fallback type (default: info)")
    ap.add_argument("--title", "-t", default=DEFAULT_TITLE, help="panel header (default: Farm Manager)")
    ap.add_argument("--ttl", type=int, default=0, metavar="MS",
                    help="how long to show it; 0 = auto from text length")
    ap.add_argument("--icon", "-i", default="", choices=("",) + ICONS, metavar="NAME",
                    help="glyph on the card; omit to use the severity's default")
    ap.add_argument("--timeout", type=float, default=2.0, help="seconds to wait for the delivery receipt")
    ap.add_argument("--config", help="path to sanctum/config.json")
    ap.add_argument("--bridge", help="path to notify.xml (overrides all detection)")
    ap.add_argument("--path-only", action="store_true", help="print the resolved bridge path and exit")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.add_argument("--id", dest="card_id", metavar="ID",
                    help="stable correlation id (protocol 4); required with --action/--choice")
    ap.add_argument("--action", action="append", default=[], metavar="TYPE",
                    choices=("yesno", "ack", "text"),
                    help="add an affordance to the card (yesno, ack, text); repeatable")
    ap.add_argument("--choice", action="append", default=[], metavar="VALUE:LABEL",
                    help="add one option to a choice action (repeatable; all "
                         "--choice flags form a single choice action)")
    args = ap.parse_args(argv)

    actions = [{"type": t} for t in args.action]
    if args.choice:
        options = []
        for spec in args.choice:
            value, sep, label = spec.partition(":")
            if not sep or not value or not label:
                print(f"error: --choice expects VALUE:LABEL, got {spec!r}", file=sys.stderr)
                return EXIT_ERROR
            options.append((value, label))
        actions.append({"type": "choice", "options": options})

    try:
        if args.path_only:
            print(get_bridge_path(config=args.config, bridge=args.bridge))
            return EXIT_DELIVERED
        outcome, _ = send_notification(
            " ".join(args.message),
            severity=args.severity,
            title=args.title,
            ttl_ms=args.ttl,
            icon=args.icon,
            timeout=args.timeout,
            config=args.config,
            bridge=args.bridge,
            quiet=args.quiet,
            card_id=args.card_id,
            actions=actions or None,
        )
    except BridgeError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as e:
        # e.g. --bridge pointing at a directory that doesn't exist. Report it
        # as an error, not as a raw traceback: a stack dump reads like a crash
        # in the notifier when it's really a bad path we were handed.
        print(f"error: cannot write the bridge file: {e}", file=sys.stderr)
        return EXIT_ERROR

    return EXIT_DELIVERED if outcome == "delivered" else EXIT_NOT_CONSUMED


if __name__ == "__main__":
    sys.exit(main())
