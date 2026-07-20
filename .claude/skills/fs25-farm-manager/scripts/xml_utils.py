"""
Shared helpers for reading Farming Simulator 25 savegame XML files.

Design principle: FS25's exact XML schema can vary slightly by file and by
map mods, and hasn't been independently verified byte-for-byte here. So every
parser in this skill does two things:

1. Best-effort extraction of the fields we expect (based on documented/
   community-confirmed structures for fields.xml, economy.xml, missions.xml).
2. A full generic dump of the XML as nested JSON, included alongside, so nothing
   is silently lost if a tag name is slightly different than expected.

If you (Claude, running this skill for real) see the generic dump contain data
that the "expected fields" section missed, prefer the generic dump and note in
the briefing that the parser should be calibrated -- see SKILL.md "Calibration".
"""
import xml.etree.ElementTree as ET
import json
import sys
import os
import time

# FS25 autosaves while the game is running -- the savegame is NOT frozen
# until the player manually saves (confirmed live: environment.xml mtime
# was 76s old with the game open; farm cash moved 88,575,568 -> 88,575,504
# mid-session with no sale to explain it). See FRICTION-LOG.md F-016.
#
# That means a parser can catch a save file mid-write. Two distinct hazards
# follow from that, and load_xml() below defends against both:
#
#   1. A torn read that breaks XML syntax (unclosed tag, truncated element).
#      This is the common case and is self-announcing: ET raises ParseError.
#      Bounded retries turn this transient failure into a clean success once
#      the writer finishes, or a clean error if it doesn't.
#
#   2. A torn read that DOESN'T break XML syntax -- e.g. an in-place,
#      non-atomic overwrite where the reader's read straddles old and new
#      bytes, and the old bytes happen to close out the document validly.
#      This is the dangerous one: syntactically valid XML with silently
#      wrong data (a stale attribute value, a hybrid old/new record, a
#      wrong record count). Verified reproducible offline: simulating an
#      in-place overwrite of a 3-record farmland.xml, 199/234 (85%) of
#      possible truncation points still parsed as valid XML, including a
#      corrupted hybrid record blending a new attribute with a stale one.
#      ET's own well-formedness check does NOT catch this -- so load_xml
#      reads the file TWICE with a short pause and requires the bytes to be
#      byte-identical before trusting them at all. A write in progress will
#      not produce identical bytes on both reads.
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.2
STABILITY_CHECK_DELAY_SECONDS = 0.08


def xml_to_dict(elem):
    """Recursively convert an ElementTree element into a plain dict/list structure."""
    node = {}
    if elem.attrib:
        node["@attrs"] = dict(elem.attrib)
    children = list(elem)
    if children:
        child_groups = {}
        for child in children:
            child_groups.setdefault(child.tag, []).append(xml_to_dict(child))
        for tag, group in child_groups.items():
            node[tag] = group if len(group) > 1 else group[0]
    text = (elem.text or "").strip()
    if text:
        node["#text"] = text
    return node


def _read_stable_bytes(path):
    """Read a file's bytes twice with a short pause and require them to match.

    A single read (even one that parses as well-formed XML) is not proof the
    file wasn't caught mid-write -- see the module docstring note above on
    non-atomic in-place overwrites. Two reads that agree byte-for-byte is a
    much stronger guarantee than "it parsed" or "mtime looks stable" (mtime
    resolution/caching on this project's 9p/DrvFs mount under WSL is not
    trustworthy for sub-second writes).

    Returns (bytes, None) on a stable read, or (None, error_message) if the
    file is actively changing, unreadable, or empty.
    """
    try:
        with open(path, "rb") as f:
            first = f.read()
        time.sleep(STABILITY_CHECK_DELAY_SECONDS)
        with open(path, "rb") as f:
            second = f.read()
    except OSError as e:
        return None, f"could not read {path}: {e}"

    if first != second:
        return None, f"file changed while being read (mid-write): {path}"
    if len(first) == 0:
        return None, f"file is empty (0 bytes): {path}"
    return first, None


def load_xml(path):
    """Parse an XML file and return (root_element, generic_dict) or (None, {'error': ...}).

    Bounded-retries a torn/concurrent read (see RETRY_ATTEMPTS): FS25
    autosaves while running, so a parser can catch a save file mid-write. A
    torn read is transient -- the file is complete again milliseconds later
    -- so a short bounded retry turns what would otherwise be a hard failure
    into a clean success, without risking an infinite spin: a persistently
    malformed file simply exhausts its retries (~3 attempts, well under a
    second total) and returns the same clean error shape as before.
    """
    if not os.path.isfile(path):
        return None, {"error": f"file not found: {path}"}

    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        data, stability_error = _read_stable_bytes(path)
        if stability_error:
            last_error = stability_error
        else:
            try:
                root = ET.fromstring(data)
                return root, {root.tag: xml_to_dict(root)}
            except ET.ParseError as e:
                last_error = f"XML parse error in {path}: {e}"
            except Exception as e:
                # Must not let a genuinely unexpected condition crash the
                # caller with a bare traceback -- always hand back a clean,
                # unambiguous error instead.
                last_error = f"unexpected error parsing {path}: {type(e).__name__}: {e}"

        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS)

    return None, {
        "error": f"{last_error} (persisted across {RETRY_ATTEMPTS} attempts)",
    }


def emit(result):
    """Print a result dict as JSON to stdout (the standard output contract for these scripts)."""
    print(json.dumps(result, indent=2))


def arg_or_exit(usage):
    if len(sys.argv) < 2:
        print(json.dumps({"error": f"usage: {usage}"}))
        sys.exit(1)
    return sys.argv[1]
