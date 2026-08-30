"""Cache layout, CACHE-VERSION, and placement resolution (plan item 2).

WHERE THE CACHE LIVES, and why it is DERIVED rather than configured (Q-2, ruled).
The spec places the cache as a SIBLING of sanctum/, outside it -- but the live
config.json carries no cache key at all: its `paths` block holds exactly
savegame_dir, install_dir, mods_dir and map_config_in_mod. So the root has to
come from somewhere, and the two candidates are not equal:

  * A new REQUIRED config key breaks every existing install on upgrade.
  * A derivation works on every farm and costs nothing.

Derived: `dirname(dirname(<config_path>))/cache`. read_state.py is invoked as
`--config <sanctum>/config.json` (sec. 2.2), so the manager root is exactly one
level above the sanctum. An OPTIONAL `paths.cache_dir` override exists because a
pure derivation strands a player whose manager root is read-only.

⚠ THE DERIVATION CONTAINS NO LITERAL PATH AND NO SANCTUM NAME. This is the item
where a builder copying the spec's worked example would hard-code this machine's
sanctum directory straight out of sec. 2.4 -- which is exactly what the
public-release gate (check_release_conformance.py) exists to catch.

THE READ-ONLY PROMISE. Everything here writes under the MANAGER root, which is a
SIBLING of the savegame folder, never a child. The promise is asserted on the
RESOLVED paths rather than on that layout holding, because the layout is a
measurement of one machine and the promise ships to every player: a config whose
savegame_dir happened to contain the manager root would violate it without a
line of this module changing. See paths_escape_savegame().

WHY `os.replace` AND WHY THE TEMP FILE IS A SIBLING. A half-written domain file
that a reader can see is a cache that lies. `os.replace` is atomic only WITHIN a
filesystem, so the temp file is created in the SAME DIRECTORY as its target --
never in /tmp, which on this machine is a genuinely different device from the
Windows mount (measured: st_dev 2096 vs 71). A cross-device rename raises
OSError(EXDEV); that surfaces as a structured error here, never as a traceback.

THE FARM ID CROSSES THE BOUNDARY EXACTLY ONCE, HERE. Measured trap: the live
config carries `"farm_id": "1"` -- a STRING -- while a parser envelope carries
the INTEGER 1, and `"1" == 1` is False. So a naive comparison rejects a correct
cache, and a careless coercion the other way makes every farm match. resolve_farm_id()
normalises config -> int in ONE direction, once; nothing downstream compares a
raw config value. An envelope's farm id is required to BE an int already
(sec. 2.1) and is never coerced -- a non-int there is a schema violation to
report, not a value to fix up quietly.

⚠ NO DEFAULT, EVER. An absent, placeholder or unparseable farm id is a structured
error. It never falls back to 1. A player whose id is not 1 would otherwise get a
confident, complete, WRONG snapshot -- "fail loud; never substitute a default"
and DEC-001, not a portability nicety.
"""
import json
import os
import tempfile

# The cache format's version. A mismatch invalidates the WHOLE cache: a cache
# written by a different layout is not partially usable, and reading it as if it
# were is how a stale field survives a format change.
CACHE_SCHEMA_VERSION = 1

CACHE_VERSION_FILE = "CACHE-VERSION"
DOMAINS_DIR = "domains"
PREV_DIR = "prev"
# Declared SLOT only. This layer owns the slot and the guarantee that it dies
# with `rm -rf cache/`; the reply layer owns what goes in it.
CARDS_PENDING = "cards-pending.jsonl"


def load_config(config_path):
    """Read a sanctum config.json. Returns (config, None) or (None, error)."""
    if not os.path.isfile(config_path):
        return None, "CONFIG ABSENT: no config.json at %s" % config_path
    try:
        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
    except json.JSONDecodeError as exc:
        return None, "CONFIG UNREADABLE: %s is not valid JSON (%s)" % (config_path, exc)
    except OSError as exc:
        return None, "CONFIG UNREADABLE: %s (%s)" % (config_path, exc.strerror)
    if not isinstance(config, dict):
        return None, "CONFIG UNREADABLE: %s does not contain a JSON object" % config_path
    return config, None


def _is_placeholder(value):
    """A template that was never filled in. The template ships farm_id as
    "{{FARM_ID -- ...}}" and tells the player to write the literal "unknown"
    where something is genuinely not yet known. Both mean NOT ANSWERED, and both
    must fail rather than be parsed."""
    text = str(value).strip()
    return "{{" in text or text.lower() in ("", "unknown", "none", "null")


def resolve_farm_id(config):
    """THE farm-id boundary. Returns (int, None) or (None, error).

    Accepts the int 1 and the string "1" -- the live config carries the string
    form -- and normalises both to int, one direction, once.

    ⚠ NO RANGE RULE IS IMPOSED. It is tempting to reject 0 or negatives as
    "not a real farm", but which ids the game considers valid is an FS25 domain
    claim, and this project does not make those from memory. collect_state.py's
    own comments show ids 0, 1 and 15 occurring in a live save. So the rule here
    is strictly typographic: an integer is accepted, a non-integer is refused.
    """
    if "farm_id" not in config:
        return None, (
            "FARM ID ABSENT: config.json carries no 'farm_id'. Refusing to "
            "assume one -- a substituted default produces a confident, complete "
            "snapshot of the wrong farm.")
    raw = config["farm_id"]
    if isinstance(raw, bool) or raw is None or _is_placeholder(raw):
        return None, (
            "FARM ID NOT SET: config.json's 'farm_id' is %r, which is a "
            "placeholder rather than an answer. Read it from farms.xml and "
            "record it." % (raw,))
    if isinstance(raw, int):
        return raw, None
    try:
        return int(str(raw).strip()), None
    except (TypeError, ValueError):
        return None, (
            "FARM ID UNPARSEABLE: config.json's 'farm_id' is %r, which is not "
            "an integer." % (raw,))


def envelope_farm_id(envelope):
    """A parser envelope's farm id, required to already BE an int (sec. 2.1).

    Never coerced. A string here means the emitting parser broke its own
    contract, and quietly repairing it would hide the drift AND make every farm
    compare equal -- the other half of the measured type trap.
    """
    if not isinstance(envelope, dict) or "farm_id" not in envelope:
        return None, "envelope carries no farm_id"
    value = envelope["farm_id"]
    if isinstance(value, bool) or not isinstance(value, int):
        return None, (
            "envelope farm_id is %r (%s); sec. 2.1 requires an integer. Not "
            "coercing it -- a coerced comparison makes every farm match."
            % (value, type(value).__name__))
    return value, None


def resolve_cache_root(config_path, config):
    """Q-2: derive `dirname(dirname(<config_path>))/cache`, with an optional
    `paths.cache_dir` override. Returns an absolute path."""
    override = (config.get("paths") or {}).get("cache_dir")
    if override and not _is_placeholder(override):
        if os.path.isabs(override):
            return os.path.normpath(override)
        manager_root = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
        return os.path.normpath(os.path.join(manager_root, override))
    manager_root = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
    return os.path.join(manager_root, "cache")


def cache_paths(cache_root):
    """Every path this layer owns, derived from one root."""
    return {
        "root": cache_root,
        "version_file": os.path.join(cache_root, CACHE_VERSION_FILE),
        "domains": os.path.join(cache_root, DOMAINS_DIR),
        "prev": os.path.join(cache_root, PREV_DIR),
        "cards_pending": os.path.join(cache_root, CARDS_PENDING),
    }


def paths_escape_savegame(paths, savegame_dir):
    """Return the paths that would be written INSIDE the savegame folder.

    Empty list = the published promise holds for this config. Asserted on the
    RESOLVED, normalised paths rather than on the sibling-directory convention,
    because the convention is one machine's layout and the promise is shipped to
    every player.
    """
    if not savegame_dir:
        return []
    save = os.path.normpath(os.path.abspath(savegame_dir))
    offenders = []
    for key, path in paths.items():
        candidate = os.path.normpath(os.path.abspath(path))
        if candidate == save or candidate.startswith(save + os.sep):
            offenders.append({"key": key, "path": candidate})
    return offenders


def read_cache_version(cache_root):
    """Returns (int, None) or (None, error).

    ABSENCE FAILS. A missing CACHE-VERSION beside a populated domains/ is an
    error, never a quiet pass -- the version is what makes the rest of the cache
    interpretable, so reading domain files without it is reading bytes of
    unknown format and calling the result a farm.
    """
    path = os.path.join(cache_root, CACHE_VERSION_FILE)
    if not os.path.isfile(path):
        return None, "CACHE ABSENT: no %s at %s" % (CACHE_VERSION_FILE, path)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read().strip()
    except OSError as exc:
        return None, "CACHE UNREADABLE: %s (%s)" % (path, exc.strerror)
    if not raw:
        return None, "CACHE VERSION EMPTY: %s exists but is empty" % path
    try:
        return int(raw), None
    except ValueError:
        return None, "CACHE VERSION UNPARSEABLE: %s contains %r" % (path, raw[:40])


def atomic_write(path, text, temp_dir=None):
    """Write `text` to `path` atomically. Returns (True, None) or (False, error).

    The temp file is created in the TARGET'S OWN DIRECTORY by default, because
    os.replace is atomic only within a filesystem. `temp_dir` exists so the
    cross-device failure can be provoked in a test against a real second
    filesystem rather than by stubbing os.replace -- the boundary under test is
    the rename itself.
    """
    directory = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        return False, "CACHE WRITE FAILED: cannot create %s (%s)" % (directory, exc.strerror)

    handle = None
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=".tmp-", suffix=".part", dir=temp_dir or directory)
        handle = os.fdopen(fd, "w", encoding="utf-8")
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(tmp_name, path)
        return True, None
    except OSError as exc:
        detail = "%s -> %s (%s)" % (tmp_name, path, exc.strerror or exc)
        if handle is not None:
            handle.close()
        if tmp_name and os.path.exists(tmp_name):
            os.remove(tmp_name)
        return False, (
            "CACHE WRITE FAILED: could not atomically replace %s. A rename "
            "across filesystems is not atomic and is refused by the OS; the "
            "temp file must be a sibling of its target." % detail)


def atomic_write_json(path, payload, temp_dir=None):
    return atomic_write(path, json.dumps(payload, indent=2) + "\n", temp_dir=temp_dir)
