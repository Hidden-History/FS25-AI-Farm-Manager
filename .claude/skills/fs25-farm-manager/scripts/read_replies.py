#!/usr/bin/env python3
"""
read_replies.py

Ingest the player's replies (clicks on actionable notification cards) from the
mod's replies.xml into the sanctum, then truncate the consumed file -- the
return half of the protocol-4 two-way loop.

    python3 read_replies.py
    python3 read_replies.py --replies /path/to/replies.xml --ledger /path/to/replies-ledger.json

Output is JSON on stdout (the script contract):

    {"new_replies": [...], "already_ingested": N, "truncated": true|false,
     "ledger_path": "..."}                                          (exit 0)
    {"error": "..."}                                                (exit 1)

---------------------------------------------------------------------------
THE CONTRACT WITH THE MOD (FarmManager25.lua writeReply)
---------------------------------------------------------------------------
The mod only ever APPENDS to replies.xml (a read-modify-rewrite, because the
FS25 io sandbox is write-only); the skill only ever truncates-after-read. A
lost race between the two re-reads a reply, and the (id, action) dedup keeps
it from double-counting -- that dedup key is the mod's own idempotency
contract: the same id legitimately carries distinct actions (yes then
dismiss), so id-only dedup would silently drop a real answer.

replies.xml grammar (writeReply saves exactly this):

    <farmManager25Replies>
      <reply id="ctr-field18-0812" action="yes"
             gameTime="..." realTime="2026-07-19 12:00:00">
        <line>text replies carry lines</line>
      </reply>
    </farmManager25Replies>

`realTime` is the string form "%Y-%m-%d %H:%M:%S" (FS25 getDate output; there
is no epoch API in FS25 -- accepted deviation D1). It is ingested VERBATIM,
never converted.

---------------------------------------------------------------------------
WHY THE ORDER IS LEDGER-FIRST, TRUNCATE-LAST, GUARDED
---------------------------------------------------------------------------
The truncate is the destructive step, so it can only ever run after the data
is durable and only if nothing moved underneath us:

1. Read replies.xml (stable-read: two byte-identical reads, xml_utils's
   defense against a torn read -- the engine's save is not atomic).
2. Merge the new (id, action) entries into sanctum/replies-ledger.json and
   ATOMICALLY write it (temp + os.replace, the notify_farm_manager pattern).
3. Truncate replies.xml to the empty <farmManager25Replies/> -- but ONLY if
   its bytes still equal what step 1 read. If the mod appended a reply while
   we ingested, skip the truncate: the next run picks everything up and the
   ledger dedup absorbs the re-read. This narrows the loss window to the
   guard's own check->replace interval -- small, not zero: a lock-free
   two-writer file under the FS25 io sandbox admits no atomic
   check-and-swap, so a reply appended exactly inside that interval is
   still truncated away. Accepted by design; the guard makes it sub-ms
   instead of the whole ingest.

Malformed replies.xml: report the error and touch NOTHING -- the mod itself
replaces a corrupt replies.xml on its next write, so the evidence keeps. A
corrupt ledger likewise fails loud and is never clobbered: it is the durable
record.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from notify_farm_manager import BridgeError, _atomic_write, get_bridge_path, _find_config
from xml_utils import _read_stable_bytes, emit, RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS

REPLIES_NAME = "replies.xml"          # FarmManager25.lua REPLIES_NAME
ROOT_TAG = "farmManager25Replies"
LEDGER_NAME = "replies-ledger.json"
EMPTY_PAYLOAD = '<?xml version="1.0" encoding="utf-8"?>\n<farmManager25Replies/>'


# ---------------------------------------------------------------------------
# path resolution
# ---------------------------------------------------------------------------

def resolve_replies_path(config: Optional[str] = None,
                         bridge: Optional[str] = None,
                         replies: Optional[str] = None) -> str:
    """replies.xml lives beside notify.xml in the mod's modSettings folder
    (the Lua stateFolder) -- derive it from the sender's verified bridge
    resolution rather than re-implementing any path logic."""
    if replies:
        return replies
    return str(Path(get_bridge_path(config=config, bridge=bridge)).parent
               / REPLIES_NAME)


def resolve_ledger_path(config: Optional[str] = None,
                        ledger: Optional[str] = None) -> str:
    """The ledger lives at the sanctum root, beside config.json -- a machine
    file, deliberately not .md, so sanctum_maintain's governed-file check
    (only *.md and config.json are governed) ignores it."""
    if ledger:
        return ledger
    cfg = Path(config) if config else _find_config()
    if cfg is None or not Path(cfg).is_file():
        raise BridgeError(
            "cannot locate sanctum/config.json to place the replies ledger; "
            "pass --ledger /path/to/replies-ledger.json")
    return str(Path(cfg).parent / LEDGER_NAME)


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

def _read_replies_file(path: str):
    """Return (entries, raw_bytes) or raise BridgeError. Stable-read with the
    same bounded retry discipline as xml_utils.load_xml (the mod's save is
    not atomic; a torn read is transient)."""
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        data, stability_error = _read_stable_bytes(path)
        if stability_error:
            last_error = stability_error
        else:
            try:
                root = ET.fromstring(data)
            except ET.ParseError as e:
                last_error = f"malformed XML in {path}: {e}"
            else:
                if root.tag != ROOT_TAG:
                    raise BridgeError(
                        f"{path} root is <{root.tag}>, expected <{ROOT_TAG}> "
                        "-- not a replies file, refusing to touch it")
                entries = []
                for el in root.findall("reply"):
                    entries.append({
                        "id": el.get("id"),
                        "action": el.get("action"),
                        "gameTime": el.get("gameTime"),
                        "realTime": el.get("realTime"),   # D1: verbatim string
                        "lines": [l.text or "" for l in el.findall("line")],
                    })
                return entries, data
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise BridgeError(f"{last_error} (persisted across {RETRY_ATTEMPTS} attempts)")


def _load_ledger(path: str) -> list:
    p = Path(path)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        replies = data["replies"]
        if not isinstance(replies, list):
            raise ValueError("'replies' is not a list")
        if not all(isinstance(item, dict) for item in replies):
            raise ValueError("'replies' contains a non-dict entry")
        return replies
    except (OSError, ValueError, KeyError, TypeError) as e:
        # The ledger is the durable record -- NEVER clobber it on parse
        # failure; fail loud and leave replies.xml untruncated too.
        raise BridgeError(f"cannot read the replies ledger {path}: {e} "
                          "-- fix or move it; refusing to overwrite")


def _truncate_if_unchanged(path: str, original: bytes) -> bool:
    """The guarded destructive step: replace replies.xml with the empty root
    (atomic; NOT a delete -- mirrors the mod's own consume fallback and
    avoids DrvFs delete/sharing flake) ONLY if the file's bytes still equal
    what was ingested. The mod appending mid-ingest skips the truncate; the
    next run re-reads and the ledger dedup absorbs it."""
    if original == EMPTY_PAYLOAD.encode("utf-8"):
        # Already the empty root: rewriting identical bytes would bump the file's
        # mtime for nothing -- and the event watcher keys the replies channel off
        # content precisely so an mtime bump on an empty file can't re-trigger it.
        # Belt-and-suspenders for that loop: an empty file is nothing to consume.
        return False
    try:
        current = Path(path).read_bytes()
    except OSError:
        return False
    if current != original:
        return False
    _atomic_write(Path(path), EMPTY_PAYLOAD)
    return True


def ingest(replies_path: str, ledger_path: str) -> dict:
    """The full loss-proof sequence. Returns the result dict; never raises
    for expected failures (malformed file, unreadable ledger) -- those come
    back as {"error": ...} with nothing touched."""
    if not Path(replies_path).is_file():
        return {"new_replies": [], "already_ingested": 0, "truncated": False,
                "ledger_path": ledger_path,
                "note": f"no {REPLIES_NAME} at {replies_path} -- no replies waiting"}

    try:
        entries, raw = _read_replies_file(replies_path)
        ledger = _load_ledger(ledger_path)

        kept = {(e.get("id"), e.get("action")): e for e in ledger}
        new = []
        for e in entries:
            key = (e["id"], e["action"])
            if key in kept:
                # The (id, action) dedup is the mod's idempotency contract and
                # stands -- but a dropped duplicate whose CONTENT differs from
                # the retained entry deserves a diagnostic: a reply vanishing
                # with different words in it must not vanish silently.
                # Non-fatal; the retained entry wins.
                k = kept[key]
                if any(e.get(f) != k.get(f) for f in ("gameTime", "realTime", "lines")):
                    print(f"warning: dropped duplicate reply (id={e['id']!r}, "
                          f"action={e['action']!r}) whose content differs from "
                          "the retained entry", file=sys.stderr)
                continue
            kept[key] = e
            new.append(dict(e, ingested_at=time.strftime("%Y-%m-%d %H:%M:%S")))

        if new:
            payload = json.dumps({"replies": ledger + new}, indent=2)
            _atomic_write(Path(ledger_path), payload)
    except (BridgeError, OSError) as e:
        return {"error": str(e)}

    result = {
        "new_replies": new,
        "already_ingested": len(entries) - len(new),
        "truncated": False,
        "ledger_path": ledger_path,
    }
    # Past this point the replies ARE durably ledgered -- a truncate failure
    # must not masquerade as "nothing happened". Report the ingest as the
    # success it was; the next run retries the truncate and the dedup
    # absorbs the re-read.
    try:
        result["truncated"] = _truncate_if_unchanged(replies_path, raw)
    except OSError as e:
        result["truncate_error"] = (
            f"replies were ledgered but {REPLIES_NAME} could not be "
            f"truncated (next run retries; the dedup absorbs the re-read): {e}")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Ingest player replies from the FS25 mod's replies.xml "
                    "into the sanctum ledger, then truncate the consumed file.")
    ap.add_argument("--config", help="path to sanctum/config.json")
    ap.add_argument("--bridge", help="path to notify.xml (replies.xml is derived beside it)")
    ap.add_argument("--replies", help="path to replies.xml (overrides all detection)")
    ap.add_argument("--ledger", help="path to replies-ledger.json (default: beside config.json)")
    args = ap.parse_args(argv)

    try:
        replies_path = resolve_replies_path(config=args.config,
                                            bridge=args.bridge,
                                            replies=args.replies)
        ledger_path = resolve_ledger_path(config=args.config, ledger=args.ledger)
    except BridgeError as e:
        emit({"error": str(e)})
        return 1

    result = ingest(replies_path, ledger_path)
    emit(result)
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
