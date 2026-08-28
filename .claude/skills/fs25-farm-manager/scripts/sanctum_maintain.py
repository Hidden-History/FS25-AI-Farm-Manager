"""
sanctum_maintain.py -- parity, migration, and rotation for a farm's sanctum files.

Three subcommands, built to the CP0-locked contract
(rebuild/FRONTMATTER-PARITY-SCHEMA.md + CANONICAL-TEMPLATE-LIST.md):

  check      Read each governed file's OWN frontmatter and answer FRESH / STALE /
             UNVERIFIABLE. Caps are measured CONTENT-only (the leading YAML
             frontmatter block is stripped first, per schema Section 1). config.json is
             special-cased against its required-keys list (schema Section 2) instead of
             frontmatter. A cap is a RECOMMENDATION, not a limit (DEC-105): an over-cap
             file stays FRESH/UNVERIFIABLE and carries a `warning` instead of STALE. The
             farm's own config.json `"cap_overrides"` replaces the shipped number.

  reconcile  Migrate an old-version farm to the current templates: relocate the
             pre-D4 FLAT layout (content .md at the sanctum root) into the tiered
             identity/ state/ history/ layout via this script's OWN migration list
             (NOT init_sanctum.TEMPLATE_FILES -- that list deliberately omits
             creed/decision-making/config, so it is not a migration map), and add
             any required_sections a stale-version file lacks. Content-preserving:
             every heading that carries farm content is kept.

  rotate     Dispatch on (class, rotation_trigger) using the CLOSED 9-token enum
             (schema Section 6). Never blind row-shed: register `on-resolve` MOVES resolved
             entries whole to a `<name>-archive.md`; ledger `segment-and-retain`
             conservation-checks the row count before any deletion.

Every write goes through _safe_write / a safe move: backup-before-write, crash-atomic
(temp + os.replace), and a staleness check that raises StaleManifestError if the file
changed on disk since it was read (the reconcile_helper.py contract, implemented locally
-- reconcile_helper.py does not exist in this tree; the contract names it only as the model).

Frontmatter is parsed by a small stdlib-only reader (see _split_frontmatter /
_parse_frontmatter). This skill ships stdlib-only, so this script does NOT depend on
PyYAML; the reader handles exactly the CP0 frontmatter schema (scalars + the
parity_spec.required_sections list, block or flow form, escaped quotes included).

Output contract: JSON on stdout (indent=2), matching the other scripts here.

Usage:
    python3 sanctum_maintain.py check     <file-or-sanctum-dir>
    python3 sanctum_maintain.py reconcile <sanctum-dir> [--templates-dir DIR] [--apply]
    python3 sanctum_maintain.py rotate    <file-or-journal-dir> [--sanctum-dir DIR] [--apply]

Without --apply, reconcile/rotate are a DRY RUN: they report the plan and change nothing.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

TEMPLATES_DIR_DEFAULT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
)

# KB is measured as KiB (1024 bytes) -- caps are small (4..20) and content-derived.
KB = 1024

# Verdicts (exactly three, per schema Section 1's three-answer discipline).
FRESH = "FRESH"
STALE = "STALE"
UNVERIFIABLE = "UNVERIFIABLE"

# Sanctum structural-schema marker (DEC-268): the highest migration to_version this build
# ships. Stored per-sanctum in config.json as `sanctum_schema_version` and advanced by the
# `migrate` subcommand. Deliberately SEPARATE from config.json's notifications.mod_version
# (the AI Farm Manager notification MOD's release -- a different axis). Bump this by one
# whenever a new MANIFEST entry is appended.
SANCTUM_SCHEMA_VERSION = 1


class StaleManifestError(Exception):
    """Raised when a file changed on disk between read and write. Defined LOCALLY:
    reconcile_helper.py (its origin in AI-Memory's aim-tracking-rotate) does not exist
    in the FS25 tree -- the contract cites it only as the model to implement here."""


class ConservationError(Exception):
    """Raised when a rotation's row/file conservation invariant fails -- archived plus
    retained must equal the pre-rotation total, re-derived from the rewritten output
    (not a same-variable tautology). Raised BEFORE any deletion, so a failed check
    aborts with the source untouched (never blind row-shed -- TD-655)."""


class ArchivePathError(Exception):
    """Raised when an archive_target still contains an unresolved {token} after
    substitution -- writing a literal-brace path would collide every entity's history
    into one file (schema Section 4)."""


class SchemaVersionError(Exception):
    """Raised when the sanctum's version marker cannot be trusted forward-only: it is AHEAD
    of the newest migration this build knows (sanctum written by a NEWER skill), OR the
    sanctum's config.json is present-but-unparseable (a corrupt marker must never be guessed
    as 'pre-migration'). migrate fails loud: applies nothing, wipes nothing, keeps any
    backup (BP-069 pitfall 3 -- never a silent destructive fallback on an unrecognized
    version, never a silent re-migration off a corrupt marker)."""


class MigrationError(Exception):
    """Raised when a migration hits an unexpected-but-clean-exit error (missing template,
    non-UTF8 content, ENOSPC/EACCES, a FileExists race) so it is routed through this
    script's clean-JSON / exit-nonzero contract instead of escaping as a raw traceback. The
    pre-migration backup is already taken, so this is a clean-exit-vs-traceback correctness
    gap, not data loss. Scoped to migrate -- other commands keep their own handling."""


# --------------------------------------------------------------------------- #
# Frontmatter reader (stdlib-only, scoped to the CP0 schema)
# --------------------------------------------------------------------------- #

def _split_frontmatter(text):
    """Return (fm_block, fm_inner, body).

    fm_block is the leading `---\\n ... \\n---\\n` verbatim (delimiters included), or
    None if the file does not open with a frontmatter block. fm_inner is the text
    between the delimiters; body is everything after.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None, None, text
    lines = text.splitlines(keepends=True)
    # lines[0] is the opening '---'. Find the next line that is exactly '---'.
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            fm_block = "".join(lines[: i + 1])
            fm_inner = "".join(lines[1:i])
            body = "".join(lines[i + 1:])
            return fm_block, fm_inner, body
    return None, None, text  # no closing delimiter -> treat as no frontmatter


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        inner = s[1:-1]
        if s[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return s


def _parse_list_value(inline, following_lines):
    """Parse a YAML list in either flow form (["a", "b"]) or block form (- a / - b).

    `inline` is the text after the key's colon on the same line; `following_lines`
    are the subsequent raw lines (used only for the block form).
    """
    inline = inline.strip()
    if inline.startswith("["):
        # Flow form. Pull quoted strings first (handles escaped quotes and commas
        # inside a heading); fall back to comma-split for any bare tokens.
        body = inline
        # gather across lines until the closing ']' in case it wrapped
        idx = 0
        for ln in following_lines:
            if "]" in body:
                break
            body += ln
            idx += 1
        body = body[body.index("[") + 1: body.rindex("]")] if "]" in body else body[body.index("[") + 1:]
        quoted = re.findall(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'', body)
        if quoted:
            return [(_a or _b).replace('\\"', '"').replace("\\\\", "\\") for _a, _b in quoted]
        return [t.strip() for t in body.split(",") if t.strip()]
    # Block form: consecutive `  - item` lines.
    items = []
    for ln in following_lines:
        stripped = ln.strip()
        if stripped.startswith("- "):
            items.append(_unquote(stripped[2:]))
        elif stripped == "" or stripped.startswith("#"):
            continue
        else:
            break
    return items


def _parse_frontmatter(fm_inner):
    """Parse the CP0 frontmatter into a dict. Returns top-level scalars plus
    parity_spec.required_sections / required_placeholders as lists."""
    meta = {}
    lines = fm_inner.splitlines(keepends=True)
    i = 0
    in_parity = False
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip("\r\n")
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^(\s*)([A-Za-z0-9_]+):\s?(.*)$", line)
        if not m:
            continue
        key, val = m.group(2), m.group(3)
        if indent == 0:
            in_parity = (key == "parity_spec")
            if key == "parity_spec":
                continue
            if key == "resolved_markers":
                meta[key] = [mk.upper() for mk in _parse_list_value(val, lines[i:])]
            else:
                meta[key] = _unquote(val)
        elif in_parity and key in ("required_sections", "required_placeholders"):
            meta[key] = _parse_list_value(val, lines[i:])
    # numeric coercions where meaningful
    for k in ("cap_lines", "cap_kb", "format_version"):
        if k in meta and re.fullmatch(r"-?\d+", meta[k].strip() or ""):
            meta[k] = int(meta[k])
    return meta


# --------------------------------------------------------------------------- #
# Heading helpers
# --------------------------------------------------------------------------- #

_PLACEHOLDER_SPAN = re.compile(r"\{\{.*?\}\}")


def _normalize_heading(h):
    """Strip every {{...}} span and re-trim (schema Section 1 match semantics), so an
    instantiated placeholder heading still matches its required_sections entry."""
    return _PLACEHOLDER_SPAN.sub("", h).strip()


def _body_h2_headings(body):
    """Return the set of normalized H2 headings (## ...) present in the body,
    each as its exact trimmed line with {{...}} spans removed."""
    out = set()
    for line in body.splitlines():
        s = line.strip()
        if re.match(r"^##\s+\S", s) and not s.startswith("###"):
            out.add(_normalize_heading(s))
    return out


# --------------------------------------------------------------------------- #
# Safe I/O (the reconcile_helper contract, implemented locally)
# --------------------------------------------------------------------------- #

def _digest(data_bytes):
    return hashlib.sha256(data_bytes).hexdigest()


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _atomic_write(path, content_bytes):
    """Crash-atomic write: temp file in the same dir + os.replace (atomic rename)."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(content_bytes)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _safe_write(path, new_text, expected_digest):
    """backup-before-write + crash-atomic + staleness-checked overwrite of an
    EXISTING file. expected_digest is the sha256 captured when the file was read;
    if the file changed since, raise StaleManifestError and touch nothing."""
    current = _read(path)
    if _digest(current) != expected_digest:
        raise StaleManifestError(path)
    _atomic_write(path + ".bak", current)          # backup the pre-write content
    _atomic_write(path, new_text.encode("utf-8"))


def _safe_move(src, dst, new_text, src_digest):
    """Relocate src -> dst, writing new_text at dst. Staleness-checked against
    src_digest; backs the source content up (src.bak) before removing it; crash-atomic
    at the destination. Refuses to clobber an existing, different destination."""
    current = _read(src)
    if _digest(current) != src_digest:
        raise StaleManifestError(src)
    if os.path.exists(dst) and _read(dst) != new_text.encode("utf-8"):
        raise FileExistsError(dst)
    _atomic_write(dst, new_text.encode("utf-8"))
    _atomic_write(src + ".bak", current)
    os.remove(src)


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #

# config.json's out-of-band contract (schema Section 2). always-required top-level keys;
# interest_rate_annual is conditionally required (only once a loan with a known rate
# exists) -- its absence is UNVERIFIABLE/N-A, never STALE.
CONFIG_REQUIRED_KEYS = ["savegame_path", "farm_id", "paths",
                        "player_name", "language"]
CONFIG_CONDITIONAL_KEY = "interest_rate_annual"

# BUG-025 / DEC-117. A presence test alone cannot separate "asked and answered" from
# "never asked": onboarding writes config.json by hand from templates/config.json
# (o5:12-19), so the failure that actually happens is a key left holding the template's
# own placeholder. Measured before this was added: "{{PLAYER_NAME}}", "", "unknown" and a
# real answer all returned the IDENTICAL verdict -- DEC-001's own shape inside the check
# meant to prevent it.
#
# NOT a new key's problem. templates/config.json ships savegame_path as
# "{{ABSOLUTE_PATH_TO_SAVEGAME_FOLDER}}" and savegame_path is ALREADY in
# CONFIG_REQUIRED_KEYS -- so this hole is live today on a currently-required key, and the
# guard closes that one too. Hence: GENERAL over CONFIG_REQUIRED_KEYS, never a special
# case for the two keys that prompted it.
#
# The judgement itself is aggregate_render._is_placeholder -- the SHIPPED gate build_header
# already applies to farm_name (:75-79, :110). Imported, never restated: a second copy of
# a refusal rule is a copy that can drift, and this module is the one that would drift
# silently. sys.path insert matches the convention every sibling script here uses.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aggregate_render import _is_placeholder  # noqa: E402


def _is_unanswered(value):
    """True when a required config value reads as 'never filled in'.

    Containers are exempt: a dict/list is not itself an answer, and judging one by its
    repr would flag `paths` for any nested placeholder -- a different check with a
    different owner. Mirrors aggregate_render._claimable: only scalars are claims.
    """
    if isinstance(value, (dict, list)):
        return False
    return _is_placeholder(value)
# config.json carries no frontmatter (it's JSON, not a templated .md), so its size
# recommendation is this constant rather than a `cap_kb:` frontmatter field -- overridable
# the same way every other file's cap is, via config.json's own "cap_overrides" (DEC-105).
CONFIG_CAP_KB = 8

# Files that legitimately carry NO frontmatter (schema Section 3) -- excluded from the gate.
NO_FRONTMATTER_FILES = {
    "directive-entry.md",
    "session-start-briefing.md",
}
# Directory-marker READMEs (schema Section 3): a README.md directly under one of these
# dirs is a dir-marker, not a governed capped file. Scoped by PARENT dir so an unrelated
# README.md elsewhere is not silently waved through (L-E).
DIR_MARKER_PARENTS = {"field-dossiers", "husbandry-dossiers", "production-dossiers", "journal"}


def _content_line_count(body):
    """Line count aligned to literal `wc -l` (newline count) -- NOT +1 for a body with
    no trailing newline (L-D)."""
    return body.count("\n")


def _is_dir_marker_readme(path):
    return os.path.basename(path) == "README.md" and \
        os.path.basename(os.path.dirname(path)) in DIR_MARKER_PARENTS


# ---- DEC-105: caps are a RECOMMENDATION, not a limit --------------------------------- #
# ① no cap ever blocks (a STALE verdict) or forces manual rotation (an "agent-rotation"
#   action) by itself -- being over cap changes NEITHER. ② an over-cap file ALWAYS carries a
#   `warning` naming the real cost (token/context budget) and what to do about it -- every
#   run it stays over, not once on crossing. ③ the farm's own number, recorded in
#   config.json's "cap_overrides", replaces the shipped recommendation everywhere a cap is
#   read from (both the warning threshold and any auto-rotation trigger keyed on it).

def _validate_override_int(basename, field, raw, shipped):
    """Validate ONE cap_overrides.<basename>.<field> value the player wrote. Returns
    (usable_value_or_None, issue_or_None). A value that is not a whole number (bool is
    REJECTED too -- `isinstance(True, int)` is True in Python, so `cap_lines: true` would
    otherwise silently become 1) or that is zero/negative (a cap of zero or less is not a
    cap) is UNUSABLE: fall back to `shipped`, but the issue string names the file, the
    field, what was written, why it couldn't be used, and the value used instead -- an
    override that silently vanishes reproduces AI-060 / RSK-001 (absence rendered as data)
    inside the very mechanism DEC-105 part 3 built to replace hard caps."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None, (f'cap_overrides."{basename}".{field} was {raw!r}; expected a whole '
                      f'number. Using the shipped {shipped}.')
    if raw <= 0:
        return None, (f'cap_overrides."{basename}".{field} was {raw}; a cap of zero or '
                      f'less is not a cap. Using the shipped {shipped}.')
    return raw, None


def _parse_cap_overrides(data):
    """(overrides_dict, whole_key_issue) from an already-parsed config.json `data`.
    `overrides_dict` is config.json's "cap_overrides" map when it IS one; `whole_key_issue`
    is a player-facing reason string when "cap_overrides" is PRESENT but not an object at
    all (every file's override is unusable in that case, not just one -- still never
    silent). Absent key or a `data` that isn't even a dict -> ({}, None): no override was
    attempted, which is not malformed."""
    overrides = data.get("cap_overrides") if isinstance(data, dict) else None
    if overrides is None:
        return {}, None
    if not isinstance(overrides, dict):
        return {}, (f'"cap_overrides" was {overrides!r}; expected an object mapping '
                    f'filenames to their own cap_lines/cap_kb. No overrides applied -- '
                    f'using shipped defaults.')
    return overrides, None


def _cap_overrides(sanctum_dir):
    """(overrides_dict, whole_key_issue) read fresh from the sanctum's config.json. See
    _parse_cap_overrides. Unreadable/unparseable config.json -> ({}, None) -- never an
    error here; config.json's OWN validity is _check_config_json's job, not this helper's."""
    try:
        data = json.loads(_read(_sanctum_config_path(sanctum_dir)).decode("utf-8"))
    except (OSError, ValueError):
        return {}, None
    return _parse_cap_overrides(data)


def _cap_override_for(basename, overrides, shipped_values):
    """Apply one file's entry (if any) from an already-resolved `overrides` dict.
    `shipped_values` is {field: shipped_value} for exactly the fields relevant to this file
    (e.g. {"cap_lines": .., "cap_kb": ..} for a template; {"cap_kb": ..} only for
    config.json, which has no cap_lines concept). Returns (applied: dict of field->value
    actually adopted, issues: list[str]) -- `applied` omits any field that was absent or
    unusable, so the caller's shipped default stays in force for it."""
    entry = overrides.get(basename)
    if entry is None:
        return {}, []
    if not isinstance(entry, dict):
        fields = "/".join(f'"{f}"' for f in shipped_values)
        return {}, [f'cap_overrides."{basename}" was {entry!r}; expected an object with '
                    f'{fields}. Using the shipped default(s).']
    applied, issues = {}, []
    for field, shipped in shipped_values.items():
        if field not in entry:
            continue
        value, issue = _validate_override_int(basename, field, entry[field], shipped)
        if issue:
            issues.append(issue)
        else:
            applied[field] = value
    return applied, issues


def _effective_caps(meta, sanctum_dir, basename):
    """(cap_lines, cap_kb, override_issues) after applying the farm's own config.json
    override, if any and if usable, over the shipped template recommendation (DEC-105 part
    3). `override_issues` is non-empty whenever the farm's config.json declared SOMETHING
    for this file that could not be used -- the caller must surface it, not drop it."""
    cap_lines, cap_kb = meta.get("cap_lines"), meta.get("cap_kb")
    overrides, whole_issue = _cap_overrides(sanctum_dir)
    applied, entry_issues = _cap_override_for(
        basename, overrides, {"cap_lines": cap_lines, "cap_kb": cap_kb})
    issues = ([whole_issue] if whole_issue else []) + entry_issues
    cap_lines = applied.get("cap_lines", cap_lines)
    cap_kb = applied.get("cap_kb", cap_kb)
    return cap_lines, cap_kb, issues


def _over_cap_detail(cap_lines, cap_kb, body):
    """(over_cap: bool, notes: list[str]) against explicit (already-overridden) cap
    values -- content-only (frontmatter stripped), per schema Section 1."""
    lines = _content_line_count(body)
    nbytes = len(body.encode("utf-8"))
    notes = []
    if isinstance(cap_lines, int) and lines > cap_lines:
        notes.append(f"content {lines} lines > cap_lines {cap_lines}")
    if isinstance(cap_kb, int) and nbytes > cap_kb * KB:
        notes.append(f"content {nbytes} B > cap_kb {cap_kb} ({cap_kb * KB} B)")
    return bool(notes), notes


def _cap_warning(basename, notes):
    """DEC-105 part 2: ALWAYS warn while over -- never once-on-crossing. Names the real
    cost and what the player can do about it."""
    return (
        f"{basename} is over its recommended size ({'; '.join(notes)}). This is a "
        "recommendation, not a limit -- nothing is blocked. Cost: this file is read in "
        "full every session, so being oversized spends more of that session's "
        "token/context budget before real work starts. To stop this warning: rotate the "
        "file (its own '## Rotation' section, where it has one), or if this size genuinely "
        f"suits this farm, set config.json's \"cap_overrides\".\"{basename}\" to the size "
        "you want."
    )


def _check_config_json(path):
    try:
        data = json.loads(_read(path).decode("utf-8"))
    except (ValueError, OSError) as e:
        return {"file": path, "verdict": UNVERIFIABLE, "reason": f"unreadable JSON: {e}"}
    missing = [k for k in CONFIG_REQUIRED_KEYS if k not in data]
    if missing:
        return {"file": path, "verdict": STALE,
                "reason": f"missing always-required key(s): {', '.join(missing)}"}
    # BUG-025: present-but-never-answered is the failure that actually reaches a player,
    # because onboarding hand-writes this file from the template. Reported as its own
    # reason, not folded into "missing" -- a key copied verbatim and a key deleted are
    # different mistakes and the player is told which one they made.
    unanswered = [k for k in CONFIG_REQUIRED_KEYS if _is_unanswered(data.get(k))]
    # Deliberately NOT an early return, unlike `missing` above. An unanswered key and a
    # malformed cap_overrides are independent defects, and returning here would hide the
    # second behind the first -- a farm would fix its config and only THEN discover the
    # cap problem. Everything below still runs; only the verdict is overridden, at the end.
    # config.json cap_kb (schema Section 2) -- JSON, measured whole (L-A). DEC-105: a
    # recommendation that warns, never blocks; the farm's own "cap_overrides" (if any and
    # if usable) replaces the shipped default -- a malformed one falls back but is never
    # silent (see _validate_override_int).
    overrides, whole_issue = _parse_cap_overrides(data)
    applied, entry_issues = _cap_override_for("config.json", overrides, {"cap_kb": CONFIG_CAP_KB})
    override_issues = ([whole_issue] if whole_issue else []) + entry_issues
    cap_kb = applied.get("cap_kb", CONFIG_CAP_KB)
    nbytes = len(_read(path))
    over_cap = nbytes > cap_kb * KB
    if CONFIG_CONDITIONAL_KEY not in data:
        # No-loan farm (or rate unknown): cannot verify the conditional key -> not FRESH,
        # but explicitly NOT a defect. UNVERIFIABLE / N-A per schema Section 2.
        result = {"file": path, "verdict": UNVERIFIABLE,
                  "reason": f"{CONFIG_CONDITIONAL_KEY} absent -- N/A for a no-loan farm "
                            "(conditionally required only once a loan's rate is known)",
                  "not_a_defect": True}
    else:
        result = {"file": path, "verdict": FRESH, "reason": "all required keys present"}
    if unanswered:
        # BUG-025. Overrides FRESH *and* the no-loan UNVERIFIABLE: a config whose required
        # keys were never answered is stale regardless of whether it carries a loan rate,
        # and it is emphatically not "not_a_defect".
        result = {"file": path, "verdict": STALE,
                  "reason": f"always-required key(s) present but never answered: "
                            f"{', '.join(unanswered)}. A template placeholder, \"\", or "
                            "\"unknown\" means onboarding did not ask -- which must not "
                            "read the same as an answer (DEC-001).",
                  "unanswered_keys": unanswered}
    result["over_cap"] = over_cap
    if over_cap:
        result["warning"] = _cap_warning(
            "config.json", [f"{nbytes} B > cap_kb {cap_kb} ({cap_kb * KB} B)"])
    if override_issues:
        result["cap_override_issue"] = "; ".join(override_issues)
    return result


def check_file(path):
    name = os.path.basename(path)
    if name == "config.json":
        return _check_config_json(path)

    text = _read(path).decode("utf-8")
    fm_block, fm_inner, body = _split_frontmatter(text)

    if fm_block is None:
        if name in NO_FRONTMATTER_FILES or _is_dir_marker_readme(path):
            return {"file": path, "verdict": UNVERIFIABLE,
                    "reason": "no frontmatter by design (schema Section 3) -- not gated",
                    "not_a_defect": True}
        # A file that SHOULD carry frontmatter but doesn't: UNVERIFIABLE, never FRESH.
        return {"file": path, "verdict": UNVERIFIABLE,
                "reason": "frontmatter absent on a file that should carry it"}

    meta = _parse_frontmatter(fm_inner)

    # Content-only cap measurement: frontmatter stripped, remainder measured, against the
    # EFFECTIVE cap (the farm's own config.json override, if any, else the shipped
    # recommendation -- DEC-105 part 3).
    content_lines = _content_line_count(body)
    content_bytes = len(body.encode("utf-8"))
    cap_lines, cap_kb, override_issues = _effective_caps(meta, _find_sanctum_root(path), name)
    over_cap, cap_notes = _over_cap_detail(cap_lines, cap_kb, body)

    required = meta.get("required_sections", []) or []
    present = _body_h2_headings(body)
    missing = [h for h in required if _normalize_heading(h) not in present]

    result = {
        "file": path,
        "class": meta.get("class"),
        "content_lines": content_lines,
        "content_bytes": content_bytes,
        "cap_lines": cap_lines,
        "cap_kb": cap_kb,
        "over_cap": over_cap,
        "missing_sections": missing,
    }
    # DEC-105 part 1: over cap NEVER blocks (no STALE for this alone) -- only a missing
    # required section does. DEC-105 part 2: over cap ALWAYS carries a warning, every run.
    if missing:
        result["verdict"] = STALE
        result["reason"] = f"missing required section(s): {', '.join(missing)}"
    else:
        result["verdict"] = FRESH
        result["reason"] = ("frontmatter present, all required sections present, over its "
                            "recommended size (see warning)" if over_cap else
                            "frontmatter present, all required sections present, within cap")
    if over_cap:
        result["warning"] = _cap_warning(name, cap_notes)
    if override_issues:
        result["cap_override_issue"] = "; ".join(override_issues)
    return result


# Rotation OUTPUT and other non-template files are NOT part of the 23-template governed
# set (M-C) -- checking them as if they should carry template frontmatter inflates the
# UNVERIFIABLE count with false "defects". Excluded from `check <sanctum>`.
_JOURNAL_SESSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-session-\d+\.md$")


def _is_governed_file(path):
    name = os.path.basename(path)
    if name in (".DS_Store",) or name.endswith((".bak", ".tmp")):
        return False
    if name.endswith("-archive.md") or name.endswith("-history.md"):
        return False           # rotation output / dossier sidecars
    if name in ("friction-INDEX.md",) or _JOURNAL_SESSION_RE.match(name):
        return False           # rotation index / per-session journal files (not templated)
    parts = path.replace("\\", "/").split("/")
    if "archive" in parts:
        return False           # anything under history/archive/...
    return name.endswith(".md") or name == "config.json"


def _governed_md_files(sanctum_dir):
    out = []
    for root, _dirs, files in os.walk(sanctum_dir):
        for f in sorted(files):
            full = os.path.join(root, f)
            if _is_governed_file(full):
                out.append(full)
    return sorted(out)


def cmd_check(args):
    target = args.path
    if os.path.isdir(target):
        results = [check_file(p) for p in _governed_md_files(target)]
    else:
        results = [check_file(target)]
    summary = {v: 0 for v in (FRESH, STALE, UNVERIFIABLE)}
    for r in results:
        summary[r["verdict"]] += 1
    return {"command": "check", "target": target, "summary": summary, "results": results}


# --------------------------------------------------------------------------- #
# reconcile
# --------------------------------------------------------------------------- #

# This script's OWN flat->tiered migration list. NOT init_sanctum.TEMPLATE_FILES:
# that list seeds a fresh farm and deliberately omits creed/decision-making/config, so
# it is not a complete "every governed file's tiered home" map. This one is -- including
# creed.md and decision-making.md, for which there is otherwise ZERO code path to migrate
# a real farm out of the flat layout (schema Section 1 MED-gap note).
FLAT_TO_TIERED = {
    "creed.md": "identity/creed.md",
    "decision-making.md": "identity/decision-making.md",
    "directives.md": "identity/directives.md",
    "equipment-roster.md": "state/equipment-roster.md",
    "equipment-shopping-list.md": "state/equipment-shopping-list.md",
    "field-price-watchlist.md": "state/field-price-watchlist.md",
    "husbandry-roster.md": "state/husbandry-roster.md",
    "production-roster.md": "state/production-roster.md",
    "contracts.md": "state/contracts.md",
    "storage-capability.md": "state/storage-capability.md",
    "crop-grace-periods.md": "state/crop-grace-periods.md",
    "finances-ledger.md": "state/finances-ledger.md",
    "closeout-latest.md": "history/closeout-latest.md",
    "friction-log.md": "history/friction-log.md",
    # session-closeout.md is intentionally OMITTED (L-C): it is the transient closeout
    # working draft, overwritten in place each session and NOT seeded by init_sanctum, so a
    # real farm has no durable flat copy of it to migrate.
}
# Flat subdirectories that relocate wholesale (per-entity dossiers + the journal).
FLAT_DIR_TO_TIERED = {
    "field-dossiers": "state/field-dossiers",
    "husbandry-dossiers": "state/husbandry-dossiers",
    "production-dossiers": "state/production-dossiers",
    "journal": "history/journal",
}


def _template_for(basename, templates_dir):
    """Resolve the current template file for a governed sanctum file basename.
    Per-entity dossier instances (field-1.md, husbandry-2.md, ...) map to their
    family's *-dossier.md template."""
    direct = os.path.join(templates_dir, basename)
    if os.path.isfile(direct):
        return direct
    if basename == "INDEX.md":
        return os.path.join(templates_dir, "journal", "INDEX.md")
    for fam in ("field", "husbandry", "production"):
        if re.match(rf"^{fam}-.+\.md$", basename):
            cand = os.path.join(templates_dir, f"{fam}-dossier.md")
            if os.path.isfile(cand):
                return cand
    return None


# Frontmatter fields authored PER FILE by Lane A (schema Section 1) -- these survive a
# migration. Every other field (class/load/cap_lines/cap_kb/rotation_trigger/archive_target/
# parity_spec/format_version) is CONTRACT-sourced and is re-stamped from the current template
# so a migrated file tracks the contract, not its frozen old values (M-E2).
PER_FILE_FRONTMATTER_KEYS = ("owns", "reconciliation")


def _merge_frontmatter(old_block, tmpl_block):
    """Migrate frontmatter: take the current TEMPLATE's frontmatter wholesale (all
    contract fields + parity_spec + format_version), then override ONLY the per-file-authored
    fields (owns, reconciliation) with the old file's values where present (M-E2). If the old
    file has no frontmatter, the template's is used as-is (nothing per-file to preserve)."""
    _tb, tmpl_inner, _ = _split_frontmatter(tmpl_block)
    if old_block is None:
        return tmpl_block

    _ob, old_inner, _ = _split_frontmatter(old_block)
    old_per_file = {}
    for line in old_inner.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):", line)
        if m and m.group(1) in PER_FILE_FRONTMATTER_KEYS:
            old_per_file[m.group(1)] = line   # keep the raw line (value verbatim)

    out = []
    for line in tmpl_inner.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):", line)
        if m and m.group(1) in old_per_file:
            out.append(old_per_file[m.group(1)])   # per-file authored value survives
        else:
            out.append(line)                       # contract field re-stamped from template
    return "---\n" + "\n".join(out) + "\n---\n"


def _migrate_structure(old_text, template_text):
    """Content-preserving, structure-only migration to the current template.

    Keeps ALL of the old body verbatim (never drops a heading that carries farm content),
    migrates the frontmatter via _merge_frontmatter (format_version + parity_spec updated,
    per-file owns/reconciliation preserved -- M-E), and appends any required_sections the
    old body lacks. Returns the new file text."""
    old_block, _oldinner, old_body = _split_frontmatter(old_text)
    tmpl_block, tmpl_inner, _tmpl_body = _split_frontmatter(template_text)
    if tmpl_block is None:
        # Template has no frontmatter (Section 3 files) -- nothing structural to stamp.
        return old_text
    meta = _parse_frontmatter(tmpl_inner)
    required = meta.get("required_sections", []) or []
    present = _body_h2_headings(old_body)
    additions = []
    for h in required:
        if _normalize_heading(h) not in present:
            additions.append(f"\n{h}\n\n_(section added by reconcile migration; populate at next touch)_\n")
    new_body = old_body
    if additions:
        if not new_body.endswith("\n"):
            new_body += "\n"
        new_body += "".join(additions)
    return _merge_frontmatter(old_block, tmpl_block) + new_body


def _current_format_version(text, templates_dir, basename):
    tmpl_path = _template_for(basename, templates_dir)
    if not tmpl_path:
        return None, None
    _b, inner, _body = _split_frontmatter(_read(tmpl_path).decode("utf-8"))
    tmpl_meta = _parse_frontmatter(inner) if inner is not None else {}
    return tmpl_meta.get("format_version"), tmpl_path


def cmd_reconcile(args):
    sanctum = args.path
    templates_dir = args.templates_dir
    apply = args.apply
    plan = []
    handled = set()  # source paths handled by relocation -- excluded from step 3 (L-F)

    # 1. Flat -> tiered .md relocations (with structure migration to current template).
    for flat_name, tiered_rel in FLAT_TO_TIERED.items():
        src = os.path.join(sanctum, flat_name)
        if not os.path.isfile(src):
            continue
        handled.add(os.path.abspath(src))
        dst = os.path.join(sanctum, tiered_rel)
        old_bytes = _read(src)
        old_text = old_bytes.decode("utf-8")
        tmpl_path = _template_for(flat_name, templates_dir)
        if tmpl_path:
            new_text = _migrate_structure(old_text, _read(tmpl_path).decode("utf-8"))
        else:
            new_text = old_text
        entry = {"action": "relocate", "from": src, "to": dst,
                 "structure_migrated": tmpl_path is not None}
        if apply:
            try:
                _safe_move(src, dst, new_text, _digest(old_bytes))
                entry["applied"] = True
            except (StaleManifestError, FileExistsError) as e:
                entry["applied"] = False
                entry["error"] = f"{type(e).__name__}: {e}"
        plan.append(entry)

    # 2. Flat subdirectory relocations (per-entity dossiers + journal), file by file.
    for flat_dir, tiered_dir in FLAT_DIR_TO_TIERED.items():
        src_dir = os.path.join(sanctum, flat_dir)
        if not os.path.isdir(src_dir):
            continue
        for fname in sorted(os.listdir(src_dir)):
            src = os.path.join(src_dir, fname)
            if not os.path.isfile(src):
                continue
            handled.add(os.path.abspath(src))
            dst = os.path.join(sanctum, tiered_dir, fname)
            old_bytes = _read(src)
            entry = {"action": "relocate", "from": src, "to": dst, "structure_migrated": False}
            if apply:
                try:
                    _safe_move(src, dst, old_bytes.decode("utf-8"), _digest(old_bytes))
                    entry["applied"] = True
                except (StaleManifestError, FileExistsError) as e:
                    entry["applied"] = False
                    entry["error"] = f"{type(e).__name__}: {e}"
            plan.append(entry)

    # 3. Already-tiered files whose format_version is behind the current template.
    if os.path.isdir(sanctum):
        for path in _governed_md_files(sanctum):
            # A flat file relocated in step 1/2 must not be re-planned here (L-F de-dupe).
            if os.path.abspath(path) in handled:
                continue
            basename = os.path.basename(path)
            if basename in NO_FRONTMATTER_FILES:
                continue
            text = _read(path).decode("utf-8")
            fm_block, inner, _body = _split_frontmatter(text)
            if fm_block is None:
                continue
            meta = _parse_frontmatter(inner)
            cur_fv, tmpl_path = _current_format_version(text, templates_dir, basename)
            file_fv = meta.get("format_version")
            if cur_fv is None or tmpl_path is None:
                continue
            if isinstance(file_fv, int) and file_fv >= cur_fv:
                continue
            new_text = _migrate_structure(text, _read(tmpl_path).decode("utf-8"))
            entry = {"action": "migrate_version", "file": path,
                     "from_version": file_fv, "to_version": cur_fv}
            if apply and new_text != text:
                try:
                    _safe_write(path, new_text, _digest(text.encode("utf-8")))
                    entry["applied"] = True
                except StaleManifestError as e:
                    entry["applied"] = False
                    entry["error"] = f"StaleManifestError: {e}"
            plan.append(entry)

    return {"command": "reconcile", "sanctum": sanctum, "apply": apply,
            "changes": len(plan), "plan": plan}


# --------------------------------------------------------------------------- #
# rotate
# --------------------------------------------------------------------------- #

# A register's "resolved" markers, matched ONLY inside a designated status/resolution
# column (H-D) -- never against Role/Notes/prose cells, where "closed cab combine" would
# archive a LIVE machine. Covers the domain's resolved states. This is the DEFAULT set,
# used when a file's template declares no `resolved_markers` contract field; a register
# whose "resolved" states differ (e.g. a roster where BOUGHT means STILL-OWNED, not done)
# declares its own set in the template and it is re-stamped on migration (M-E2).
RESOLVED_MARKERS = ("SOLD", "REMOVED", "RESOLVED", "CLOSED", "STOPPED", "ARCHIVED", "DONE", "BOUGHT")
STATUS_HEADERS = {"status", "resolution", "state"}
_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def _is_table_row(line):
    return line.strip().startswith("|") and line.strip().endswith("|")


def _is_separator(line):
    s = line.strip()
    return bool(_SEP_RE.match(s)) and "-" in s


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _parse_tables(body):
    """Return (lines, data_idx, row_header). data_idx = indices of real data rows (table
    rows that are neither a header nor a separator nor a {{...}} placeholder scaffold).
    row_header maps each data-row index to its table's header cells (for status-column
    scoping). A blank/prose line ends a table region."""
    lines = body.splitlines(keepends=False)
    header_idx = set()
    for i, line in enumerate(lines):
        if _is_separator(line) and i > 0 and _is_table_row(lines[i - 1]):
            header_idx.add(i - 1)
    data_idx, row_header, cur_header = set(), {}, None
    for i, line in enumerate(lines):
        if i in header_idx:
            cur_header = _cells(line)
            continue
        if _is_separator(line):
            continue                      # part of the table -- keep the header
        if not _is_table_row(line):
            cur_header = None             # prose/blank ends the table region
            continue
        if "{{" in line:                  # placeholder scaffold row, not real farm data
            continue
        data_idx.add(i)
        row_header[i] = cur_header
    return lines, data_idx, row_header


def _status_col(header_cells):
    for idx, h in enumerate(header_cells or []):
        if h.strip().lower() in STATUS_HEADERS:
            return idx
    return None


def _cell_has_marker(cell, markers):
    up = cell.upper()
    return any(re.search(rf"\b{m}\b", up) for m in markers)


def _rows_under_heading(lines, data_idx, keyword):
    """Data-row indices whose governing H2 heading (nearest preceding `## `), normalized
    and lower-cased, contains `keyword` (e.g. 'open', 'history')."""
    cur, out = None, set()
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r"^##\s+", s):
            cur = _normalize_heading(s).lower()
        if i in data_idx and cur and keyword in cur:
            out.add(i)
    return out


def _assert_row_conservation(retained_rows, moved_rows, original_rows, where):
    """Re-derived conservation (H-A): the retained rows + the archived rows must equal the
    original rows as a multiset (row-exact). Compares INDEPENDENT inputs -- retained is
    re-parsed from the rewritten body, not `total - len(moved)` -- so a drop or double-count
    fails. Raises ConservationError; never a same-variable tautology."""
    if sorted(retained_rows + moved_rows) != sorted(original_rows):
        raise ConservationError(
            f"{where}: retained({len(retained_rows)})+archived({len(moved_rows)}) != "
            f"original({len(original_rows)}) rows")


def _block_marker(orig_digest, moved):
    """Idempotency key for an archive append, keyed on OPERATION IDENTITY: the source state
    at read (orig_digest) plus the moved rows (H-B2). A true retry re-reads the unchanged
    source -> same key -> idempotent skip. A DISTINCT op moving byte-identical rows to the
    same fixed archive has a different source state -> different key -> appends (no collision,
    no data loss). A content-only key silently dropped rows from both files when two ops
    coincided."""
    return hashlib.sha256((orig_digest + "".join(moved)).encode("utf-8")).hexdigest()[:16]


def _assert_partition(moved, retained, universe, where):
    """Conservation for a file-set move (H-A, journal): moved and retained must be disjoint
    and together exactly the original set -- no item in both or neither."""
    moved, retained, universe = set(moved), set(retained), set(universe)
    if (moved & retained) or (moved | retained) != universe:
        raise ConservationError(f"{where}: move/retain sets do not partition {len(universe)} items")


def _resolve_archive_path(sanctum_dir, archive_target, tokens):
    """Resolve archive_target (relative to the sanctum root), substituting EVERY legal
    schema-Section-1 token supplied in `tokens` ({YYYY} {date} {first} {last} {id} {n}).
    Any {…} left after substitution -> ArchivePathError (never write a literal-brace path
    that collides every entity's history into one file -- H-C / schema Section 4)."""
    at = archive_target
    for k, v in (tokens or {}).items():
        at = at.replace("{" + k + "}", str(v)).replace("{{" + k + "}}", str(v))
    leftover = re.search(r"\{\{?[A-Za-z0-9_]+\}?\}", at)
    if leftover:
        raise ArchivePathError(
            f"unresolved token {leftover.group()!r} in archive_target {archive_target!r}")
    return os.path.join(sanctum_dir, at)


def _base_tokens(basename):
    """Tokens derivable from the file itself: {id} from a dossier instance filename
    (field-3.md -> 3), plus the current {YYYY}/{date} for yearly/dated shards."""
    today = datetime.date.today()
    tokens = {"YYYY": f"{today.year:04d}", "date": today.isoformat()}
    # {id} comes only from a per-entity dossier INSTANCE filename (field-3.md -> 3), matched
    # explicitly by dossier family (not "any hyphenated name that isn't a template").
    m = re.match(r"^(?:field|husbandry|production)-(.+)\.md$", basename)
    if m:
        tokens["id"] = m.group(1)
    return tokens


def _find_sanctum_root(path):
    """Nearest ancestor directory named 'sanctum'; falls back to the file's parent."""
    p = os.path.abspath(path)
    cur = p if os.path.isdir(p) else os.path.dirname(p)
    while cur and os.path.basename(cur) != "sanctum" and os.path.dirname(cur) != cur:
        cur = os.path.dirname(cur)
    return cur if os.path.basename(cur) == "sanctum" else os.path.dirname(p)


def _move_rows(path, sanctum_dir, meta, selector, apply, tokens=None,
               archive_header=None, ledger_index=False):
    """Shared MOVE primitive. `selector(idx, cells, header_cells) -> bool` picks rows.

    Conservation (H-A) is RE-DERIVED from the rewritten body -- re-parse it, and require
    the retained data rows plus the archived rows to equal the original data rows as a
    multiset (row-exact). A drop or double-count raises ConservationError BEFORE any write.

    Atomicity (H-B): the SOURCE is staleness-checked before the archive is touched, and the
    archive append is idempotent (a per-block marker), so a failed/retried source write can
    never leave a row in both files. Archive path tokens are fully substituted (H-C)."""
    text = _read(path).decode("utf-8")
    orig_digest = _digest(text.encode("utf-8"))
    fm_block, _inner, body = _split_frontmatter(text)
    lines, data_idx, row_header = _parse_tables(body)
    original_rows = [lines[i] for i in sorted(data_idx)]
    move_idx = sorted(i for i in data_idx
                      if selector(i, _cells(lines[i]), row_header.get(i)))
    moved = [lines[i] for i in move_idx]

    report = {"file": path, "class": meta.get("class"),
              "rotation_trigger": meta.get("rotation_trigger"),
              "data_rows": len(data_idx), "moved_rows": len(moved)}
    if not moved:
        report["action"] = "none"
        report["reason"] = "no rows matched the rotation condition"
        return report

    kept_lines = [ln for i, ln in enumerate(lines) if i not in set(move_idx)]
    new_body = "\n".join(kept_lines)
    if body.endswith("\n"):
        new_body += "\n"
    new_text = (fm_block or "") + new_body

    # H-A: re-derive conservation from the ACTUALLY-rewritten body (independent source of
    # truth), not from `total - len(moved)`. Retained + archived must equal the original.
    _kl, kept_idx, _rh = _parse_tables(new_body)
    retained_rows = [_kl[i] for i in sorted(kept_idx)]
    _assert_row_conservation(retained_rows, moved, original_rows, path)
    report["conservation_ok"] = True

    tokens = dict(tokens or {})
    if ledger_index and moved:
        sessions = [_cells(m)[0] for m in moved]
        tokens["first"], tokens["last"] = _session_num(sessions[0]), _session_num(sessions[-1])
    archive_path = _resolve_archive_path(sanctum_dir, meta.get("archive_target", "") or "", tokens)
    report["archive"] = archive_path

    header = archive_header(moved) if archive_header else ""
    block_id = _block_marker(orig_digest, moved)
    marker = f"<!-- rotation-block {block_id} -->"
    report["archive_block_id"] = block_id

    if apply:
        # ACCEPTED residual (R3-PA-1, duplication-only, never loss): if the process dies in
        # the sub-ms window between the archive append below and the source rewrite, AND the
        # eligible set changes before a retry, the orphaned rows re-archive under a fresh
        # marker -> duplicate rows in the COLD archive. That is human-visible over-conservation
        # (the .bak is present, live farm state is never lost); a true fix needs a write-ahead
        # log, disproportionate here. Not a bug -- do not "fix" by weakening the source-first
        # staleness check or the idempotency marker.
        # H-B: confirm the source is unchanged since read BEFORE writing the archive.
        if _digest(_read(path)) != orig_digest:
            raise StaleManifestError(path)
        os.makedirs(os.path.dirname(archive_path) or ".", exist_ok=True)
        existing = _read(archive_path).decode("utf-8") if os.path.isfile(archive_path) else ""
        if marker in existing:
            # Already appended by a prior (partial) run -- honest report: this call did NOT
            # write the archive (do not imply the rows were freshly archived here).
            report["archive_written"] = False
            report["archive_skipped"] = True
        else:
            _atomic_write(archive_path,
                          (existing + marker + "\n" + header + "\n".join(moved) + "\n").encode("utf-8"))
            report["archive_written"] = True
        _safe_write(path, new_text, orig_digest)   # commit: remove moved rows from source
        report["applied"] = True
    report["action"] = "move"
    return report


def _session_num(cell):
    m = re.search(r"-?\d+", cell)
    return int(m.group()) if m else cell


def _ledger_index_header(moved):
    cash, loan, sess = [], [], []
    for m in moved:
        c = _cells(m)
        if len(c) >= 4:
            sess.append(_session_num(c[0]))
            cash.append(_num(c[2]))
            loan.append(_num(c[3]))
    sess = [s for s in sess if isinstance(s, int)]
    cash = [x for x in cash if x is not None]
    loan = [x for x in loan if x is not None]
    parts = ["<!-- archive index (segment-and-retain):"]
    if sess:
        parts.append(f" sessions {min(sess)}..{max(sess)};")
    if cash:
        parts.append(f" cash {min(cash)}..{max(cash)};")
    if loan:
        parts.append(f" loan {min(loan)}..{max(loan)}")
    parts.append(" -->\n")
    return "".join(parts)


def _num(cell):
    digits = re.sub(r"[^\d.-]", "", cell)
    try:
        return int(float(digits)) if digits not in ("", "-", ".") else None
    except ValueError:
        return None


# H-HONEST: a size/age trigger IMPLIES rotation should be possible; if a register has no
# resolution signal at all (no status column -- a Lane-A CAPABILITY gap, not a size one),
# `rotate` must NOT report a bare success -- it reports agent-rotation so the gap is
# surfaced, not hidden. NB: building parsers for those prose/list/H3 shapes is a DEFERRED
# Lane-A/plan design decision (out of scope here) -- this signal is the correct Lane-B
# behavior until then.
#
# DEC-105: being OVER CAP, by itself, is never one of these signals -- a cap is a
# recommendation (see `_cap_warning` / `_over_cap_detail` above), not a capability gap, so
# it never forces "agent-rotation" on its own. An over-cap file that has nothing
# auto-rotatable still reports whatever its normal (no-op) action would have been, plus a
# `warning`.


def _manual(path, meta, reason):
    return {"file": path, "class": meta.get("class"), "rotation_trigger": meta.get("rotation_trigger"),
            "action": "agent-rotation", "reason": reason}


def _attach_cap_signals(result, over, notes, override_issues, basename):
    """Attach the DEC-105 `warning` (over-cap, part 2) and `cap_override_issue` (a
    malformed/unusable config.json override for THIS file, part 3 -- must never be
    dropped silently) to a rotate_file result dict. Shared by every branch that consults
    cap_lines/cap_kb, so an override issue reaches the player regardless of which action
    the file's rotation_trigger takes."""
    if over:
        result["warning"] = _cap_warning(basename, notes)
    if override_issues:
        result["cap_override_issue"] = "; ".join(override_issues)
    return result


def rotate_file(path, sanctum_dir, apply):
    text = _read(path).decode("utf-8")
    fm_block, inner, body = _split_frontmatter(text)
    if fm_block is None:
        return {"file": path, "action": "skip", "reason": "no frontmatter -- not a governed capped file"}
    meta = _parse_frontmatter(inner)
    cls = meta.get("class")
    trig = meta.get("rotation_trigger")
    basename = os.path.basename(path)
    cap_lines, cap_kb, override_issues = _effective_caps(meta, sanctum_dir, basename)   # DEC-105 part 3

    if trig == "none":
        return {"file": path, "class": cls, "rotation_trigger": trig,
                "action": "none", "reason": "write-once / mutated-in-place / overwritten -- no relocation"}

    tokens = _base_tokens(basename)

    # on-resolve: MOVE resolved rows, matched ONLY in a designated status column (H-D). A
    # register with no status column has no resolution signal -> report agent-rotation
    # (H-HONEST), never a silent no-op that hides unbounded growth. The resolved-marker set
    # is per-file: a template may declare `resolved_markers` (contract field, re-stamped on
    # migration) so a register whose "resolved" states differ from the default uses its own
    # set; absent that field, the global RESOLVED_MARKERS default applies.
    markers = meta.get("resolved_markers")
    if markers is None:
        markers = RESOLVED_MARKERS       # absent -> global default (unchanged)
    elif not markers:
        # PRESENT but empty/unparseable (e.g. `resolved_markers: []` or a scalar): a contract
        # violation. Do NOT fall back to the global default (would re-introduce BOUGHT on a
        # roster and false-archive owned rows) and do NOT silently no-op (an over-cap file with
        # resolved rows would report a bare `none`, breaking its own H-HONEST invariant). Surface
        # a clear per-file error naming the file, matching the result-dict idiom.
        return {"file": path, "class": cls, "rotation_trigger": trig, "action": "error",
                "reason": f"resolved_markers present but empty/unparseable in "
                          f"{os.path.basename(path)} -- declare a non-empty list of marker "
                          "words (contract violation); refusing to fall back or silently no-op"}

    def _resolved(idx, cells, header):
        ci = _status_col(header)
        return ci is not None and ci < len(cells) and _cell_has_marker(cells[ci], markers)

    def _has_status_column(data_idx, row_header):
        return any(_status_col(row_header.get(i)) is not None for i in data_idx)

    if trig == "on-resolve":
        _l, data_idx, row_header = _parse_tables(body)
        if data_idx and not _has_status_column(data_idx, row_header):
            # populated register with no resolution signal -> honest manual signal (H-HONEST).
            # A capability gap, not a size one -- DEC-105 does not touch this.
            return _manual(path, meta,
                           "on-resolve needs a status/resolution column; none present "
                           "(status-less register or list/prose entries) -- Lane-A signal gap")
        # has a status column (move resolved / honest none) OR no table rows at all
        # (_move_rows degrades to "none" cleanly when there's nothing to move).
        result = _move_rows(path, sanctum_dir, meta, _resolved, apply, tokens=tokens)
        body_now = _split_frontmatter(_read(path).decode("utf-8"))[2]
        over, notes = _over_cap_detail(cap_lines, cap_kb, body_now)
        return _attach_cap_signals(result, over, notes, override_issues, basename)

    if trig == "segment-and-retain":
        _lines, data_idx, _rh = _parse_tables(body)
        if len(data_idx) > 25:
            oldest = set(sorted(data_idx)[:15])
            result = _move_rows(path, sanctum_dir, meta, lambda i, c, h: i in oldest, apply,
                                tokens=tokens, archive_header=_ledger_index_header, ledger_index=True)
        else:
            # <=25 parseable ledger rows -- no auto-segmentation (row-count threshold, not the
            # size cap; unrelated to DEC-105).
            result = {"file": path, "class": cls, "rotation_trigger": trig, "action": "none",
                      "data_rows": len(data_idx), "reason": "at or under 25 rows -- no segmentation"}
        body_now = _split_frontmatter(_read(path).decode("utf-8"))[2]
        over, notes = _over_cap_detail(cap_lines, cap_kb, body_now)
        return _attach_cap_signals(result, over, notes, override_issues, basename)

    if trig == "on-age":
        _lines, data_idx, _rh = _parse_tables(body)
        if len(data_idx) > 30:
            # L-B: archive only the OLDEST rows exceeding the ~30 threshold (contract F1 §10).
            excess = len(data_idx) - 30
            oldest = set(sorted(data_idx)[:excess])
            result = _move_rows(path, sanctum_dir, meta, lambda i, c, h: i in oldest, apply, tokens=tokens)
        else:
            result = {"file": path, "class": cls, "rotation_trigger": trig, "action": "none",
                      "data_rows": len(data_idx), "reason": "at or under ~30 rows -- no archival"}
        body_now = _split_frontmatter(_read(path).decode("utf-8"))[2]
        over, notes = _over_cap_detail(cap_lines, cap_kb, body_now)
        return _attach_cap_signals(result, over, notes, override_issues, basename)

    if trig in ("on-close-over-cap", "on-resolve+on-close-over-cap", "age-or-cap"):
        # The CP0 templates using these compound triggers keep their over-cap-archivable units
        # as PROSE/LIST entries (directives) or H3 blocks (friction-log FIXED/NOTED), NOT as
        # table rows -- and parsing those shapes is a DEFERRED Lane-A/plan design decision
        # (scope guard). So Lane B does NOT attempt generic table-row over-cap archival here
        # (that wrongly grabbed incidental legend/documentation tables); the live OPEN backlog
        # never rotates (M-A). DEC-105: being over cap with nothing auto-rotatable is no
        # longer a forced agent-rotation signal -- it is a `warning` alongside the compound
        # action, naming what's over and what to do (rotate by hand, or raise the cap).
        reports = []
        if trig in ("on-resolve+on-close-over-cap", "age-or-cap"):
            reports.append(_move_rows(path, sanctum_dir, meta, _resolved, apply, tokens=tokens))
        body_now = _split_frontmatter(_read(path).decode("utf-8"))[2]
        over, notes = _over_cap_detail(cap_lines, cap_kb, body_now)
        reports.append(
            {"action": "none",
             "reason": ("over-cap-archivable units are prose/list entries or H3 blocks "
                        "(only excluded OPEN / legend tables present) -- rotate by hand "
                        "per the file's own '## Rotation' section" if over else
                        "within cap -- no over-cap rotation")})
        result = {"file": path, "class": cls, "rotation_trigger": trig, "action": "compound",
                  "steps": reports}
        return _attach_cap_signals(result, over, notes, override_issues, basename)

    if trig == "on-cap-relocate":
        over, notes = _over_cap_detail(cap_lines, cap_kb, body)
        if not over:
            return _attach_cap_signals(
                {"file": path, "class": cls, "rotation_trigger": trig, "action": "none",
                 "reason": "within cap -- durable facts stay hot, no History relocation"},
                False, notes, override_issues, basename)
        # M-B: relocate only the OLDEST '## History' rows needed to get back under cap. This
        # automatic housekeeping is unaffected by DEC-105 (it never blocks or interrupts
        # anyone) -- it now runs against the farm's own EFFECTIVE cap (part 3), same as the
        # warning below.
        lines, data_idx, _rh = _parse_tables(body)
        hist = _rows_under_heading(lines, data_idx, "history")
        chosen = set()
        for i in sorted(hist):  # oldest (topmost) History rows first
            remaining = "\n".join(ln for j, ln in enumerate(lines) if j not in chosen)
            if not _over_cap_detail(cap_lines, cap_kb, remaining)[0]:
                break
            chosen.add(i)
        if not chosen:
            # over cap but no History table rows to relocate (prose/no History table) --
            # DEC-105: no longer a forced agent-rotation signal, just the warning.
            return _attach_cap_signals(
                {"file": path, "class": cls, "rotation_trigger": trig, "action": "none",
                 "reason": "no relocatable '## History' table rows found (prose/no "
                           "History table) -- rotate by hand per the file's own "
                           "'## Rotation' section"},
                True, notes, override_issues, basename)
        result = _move_rows(path, sanctum_dir, meta, lambda i, c, h: i in chosen, apply, tokens=tokens)
        body_now = _split_frontmatter(_read(path).decode("utf-8"))[2]
        over_now, notes_now = _over_cap_detail(cap_lines, cap_kb, body_now)
        return _attach_cap_signals(result, over_now, notes_now, override_issues, basename)

    if trig == "rolling-window":
        return _rotate_journal(path, sanctum_dir, apply)

    return {"file": path, "class": cls, "rotation_trigger": trig, "action": "skip",
            "reason": f"unrecognized rotation_trigger token: {trig!r}"}


def _rotate_journal(journal_dir, sanctum_dir, apply, window=12):
    """rolling-window: keep the last `window` session files hot; move older ones to
    history/archive/journal/{YYYY}/. Operates on the journal directory."""
    if not os.path.isdir(journal_dir):
        return {"dir": journal_dir, "action": "skip", "reason": "journal dir not found"}
    sessions = []
    for f in os.listdir(journal_dir):
        m = re.match(r"^(\d{4})-\d{2}-\d{2}-session-(\d+)\.md$", f)
        if m:
            sessions.append((int(m.group(2)), m.group(1), f))
    sessions.sort()
    total = len(sessions)
    all_files = {fname for _s, _y, fname in sessions}
    to_move = sessions[:-window] if total > window else []
    retained = {fname for _s, _y, fname in (sessions[-window:] if total > window else sessions)}
    moved_names = {fname for _s, _y, fname in to_move}

    # H-A: the moved set and retained set must PARTITION the original files -- disjoint,
    # and together exactly the original (no file in both or neither). Re-derived from the
    # sets, not from `len(to_move)+window` (which is true by construction).
    _assert_partition(moved_names, retained, all_files, journal_dir)

    report = {"dir": journal_dir, "action": "rolling-window", "window": window,
              "session_files": total, "moved": len(to_move), "conservation_ok": True}
    moved_files = []
    for _snum, year, fname in to_move:
        src = os.path.join(journal_dir, fname)
        dst = os.path.join(sanctum_dir, "history", "archive", "journal", year, fname)
        moved_files.append({"from": src, "to": dst})
        if apply:
            data = _read(src)
            _safe_move(src, dst, data.decode("utf-8"), _digest(data))
    report["moves"] = moved_files
    return report


def cmd_rotate(args):
    path = args.path
    sanctum_dir = args.sanctum_dir or _find_sanctum_root(path)
    if os.path.isdir(path):
        # M-D: ONLY the journal directory dispatches to the rolling-window rotator. Any
        # other directory dispatches per-file (e.g. state/field-dossiers/ -> on-cap-relocate
        # per dossier); a directory with no governed files is an explicit error, never a
        # silent no-op.
        if os.path.basename(os.path.normpath(path)) == "journal":
            return {"command": "rotate", "result": _rotate_journal(path, sanctum_dir, args.apply)}
        files = _governed_md_files(path)
        if not files:
            return {"command": "rotate", "result": {
                "dir": path, "action": "error",
                "reason": "unsupported directory target: not the journal dir and no governed files to rotate"}}
        results = [rotate_file(p, sanctum_dir, args.apply) for p in files]
        return {"command": "rotate", "result": {"dir": path, "action": "per-file", "results": results}}
    return {"command": "rotate", "result": rotate_file(path, sanctum_dir, args.apply)}


# --------------------------------------------------------------------------- #
# migrate -- versioned, ordered, idempotent STRUCTURAL migrations (BP-069)
# --------------------------------------------------------------------------- #

def _sanctum_config_path(sanctum_dir):
    return os.path.join(sanctum_dir, "config.json")


def _read_schema_version(sanctum_dir):
    """The applied-migration marker from the sanctum's config.json. This distinguishes THREE
    states (never conflating them -- C3):
      - config.json ABSENT              -> 0 (legit pre-migration: nothing bound yet).
      - config.json parses, key MISSING -> 0 (legit pre-migration: an old sanctum).
      - config.json PRESENT but corrupt -> SchemaVersionError (fail loud; guessing 'pre-
        migration' off a corrupt marker could silently RE-migrate an already-migrated farm).
    A non-int marker is likewise refused rather than coerced. This marker is the keystone
    that makes migrate idempotent + resumable (BP-069)."""
    path = _sanctum_config_path(sanctum_dir)
    if not os.path.isfile(path):
        return 0
    try:
        raw = _read(path)
    except OSError as e:
        raise SchemaVersionError(
            f"config.json is unreadable ({path}): {e}. Nothing was migrated or touched.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise SchemaVersionError(
            f"config.json is present but unparseable ({path}): {e}. Refusing to guess the "
            "sanctum schema version -- nothing was migrated or touched. Fix or restore "
            "config.json (a pre-migration backup, if any, is under history/archive/).")
    if not isinstance(data, dict):
        raise SchemaVersionError(
            f"config.json ({path}) is valid JSON but not an object ({type(data).__name__}). "
            "Refusing to guess the sanctum schema version -- nothing was migrated or touched.")
    v = data.get("sanctum_schema_version")
    if v is None:
        return 0
    if not isinstance(v, int):
        raise SchemaVersionError(
            f"sanctum_schema_version in config.json ({path}) is not an integer: {v!r}. "
            "Refusing to guess -- nothing was migrated or touched.")
    return v


def _write_schema_version(sanctum_dir, version):
    """Advance the applied marker to `version` in config.json. JSON in / JSON out at
    indent=2, key order preserved (an existing key keeps its position; a new key on an old
    sanctum appends at the end). Backup-before-write + crash-atomic via _safe_write. Fails
    loud (never a raw traceback) if config.json turned unparseable since the read (C3)."""
    path = _sanctum_config_path(sanctum_dir)
    current = _read(path)
    try:
        data = json.loads(current.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise SchemaVersionError(
            f"config.json became unparseable before the marker could be advanced ({path}): "
            f"{e}. Re-run migrate once config.json is valid.")
    if not isinstance(data, dict):
        raise SchemaVersionError(
            f"config.json ({path}) is valid JSON but not an object ({type(data).__name__}); "
            "cannot record the schema marker. Re-run migrate once config.json is a valid object.")
    data["sanctum_schema_version"] = version
    _safe_write(path, json.dumps(data, indent=2) + "\n", _digest(current))


def _tree_digest(root):
    """Digest of every regular file under root, keyed by its path relative to root --
    order-independent, so files/directories walked in either order still compare equal.
    Exists to let _backup_subtree prove a copied directory is byte-identical to its source,
    the same way _digest already lets it prove that for a single file."""
    parts = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            parts.append(rel + ":" + _digest(_read(full)))
    return _digest("\n".join(sorted(parts)).encode("utf-8"))


def _backup_subtree(sanctum_dir, paths, to_version):
    """Copy the touched paths to a dated pre-migration backup dir BEFORE any write -- the
    single restore point for the design's 'roll back = restore from the backup' model (there
    are no down-migrations). Each entry in `paths` may be a DIRECTORY (copied whole) or a
    FILE (copied individually) -- BUG-020: an isdir-only guard silently skipped a root-level
    file like config.json while still returning a plausible backup path, so the caller
    recorded a successful-looking backup that captured nothing. A path that does not exist
    yet is skipped -- there is nothing there to protect.

    Every copy is READ BACK and compared to its source (_digest for a file, _tree_digest for
    a directory) before this function returns. shutil.copytree/copy2 raise NOTHING if the
    process is killed mid-copy -- OOM, a WSL VM stop, the game being closed -- so a truncated
    file can be left on disk, named exactly like a good backup, with no exception anywhere to
    catch. Measured: a copy loop killed with SIGKILL partway through leaves the destination
    file present, readable, and short, on this project's own worktree filesystem (ext4) --
    silent truncation is not a theoretical edge case, it is what an interrupted buffered copy
    does by default. A mismatch here raises ConservationError -- deliberately NOT one of the
    (OSError, ValueError) this function's callers already catch and downgrade to a clean
    MigrationError, so an unverifiable backup aborts the migration loud (main()'s top-level
    handler) rather than being reported as a successful step. Fails loud on purpose: item #17's
    warn-never-block rule governs file SIZE, which a player can judge for themselves; this
    governs whether their data is RECOVERABLE, which they cannot.

    Returns the backup dir, which the player report names as the restore location. Lives under
    history/archive/ so it is not itself a governed file."""
    stamp = datetime.date.today().isoformat()
    base = os.path.join(sanctum_dir, "history", "archive",
                        f"pre-migration-backup-{stamp}-v{to_version}")
    backup_dir, n = base, 2
    while os.path.exists(backup_dir):
        backup_dir = f"{base}-{n}"
        n += 1
    os.makedirs(backup_dir)
    for rel in paths:
        src = os.path.join(sanctum_dir, rel)
        dst = os.path.join(backup_dir, rel)
        if os.path.isdir(src):
            src_digest = _tree_digest(src)
            shutil.copytree(src, dst)
            if _tree_digest(dst) != src_digest:
                raise ConservationError(
                    f"pre-migration backup of {rel!r} ({dst}) does not match its source "
                    f"({src}) after copy -- the copy was interrupted or corrupted. Migration "
                    "aborted; the live sanctum is untouched. Delete the incomplete backup "
                    "directory and retry.")
        elif os.path.isfile(src):
            src_digest = _digest(_read(src))
            dst_parent = os.path.dirname(dst)
            if dst_parent:
                os.makedirs(dst_parent, exist_ok=True)
            shutil.copy2(src, dst)
            if _digest(_read(dst)) != src_digest:
                raise ConservationError(
                    f"pre-migration backup of {rel!r} ({dst}) does not match its source "
                    f"({src}) after copy -- the copy was interrupted or corrupted. Migration "
                    "aborted; the live sanctum is untouched. Delete the incomplete backup "
                    "directory and retry.")
    return backup_dir


# ---- Entry #1: fold identity/directives.md -> plans/PLAN.md (item 7 / DEC-259) ------- #

# A directive TITLE is an H3-or-deeper heading, tolerant of a missing space (`###Title`)
# and extra hashes -- so a hand-edited heading is captured, not silently dropped (C2).
# A structural section is a `## ` (exactly two-hash) heading, matched separately.
_DIRECTIVE_HEADING_RE = re.compile(r"^#{3,}\s*\S")
# A directive FIELD bullet, matched as a `key: value` bullet: `- **Status:** ...`,
# `- Status: active`, `* Goal: ...`. Bold is optional so a hand-edited non-bold bullet is
# still captured (R2-C2); the required `key:` anchor keeps ordinary prose bullets
# (`- buy the barn`) from becoming signals. Used to raw-anchor conservation independently
# of block extraction.
_DIRECTIVE_FIELD_RE = re.compile(r"^[-*]\s+\*{0,2}[A-Za-z][^:]*:")


def _iter_directive_region(directives_body):
    """Yield each line OUTSIDE a structural `## ` section, so the extractor and the
    signal-line anchor stay in lockstep (R2-P1). CONTRACT: in a directives.md the directive
    entries come FIRST and the structural sections (`## How entries accumulate` / `## Closing
    a directive honestly` / `## Rotation ...`) come LAST; this latches `in_structural` at the
    first structural `## ` heading and skips everything after it. Content after that first
    structural heading -- including any illustrative `### ` example nested in a structural
    section -- is NOT carried into the live plan; it is superseded by plan-main and preserved
    byte-identical in the archive. A convention-violating layout (a directive placed AFTER a
    structural section) fails safe: that directive is not carried live, but the whole file is
    archived byte-identical, so it is never lost."""
    in_structural = False
    for ln in directives_body.splitlines():
        s = ln.strip()
        if s.startswith("## ") and not s.startswith("###"):
            in_structural = True
        if in_structural:
            continue
        yield ln


def _extract_directive_entries(directives_body):
    """The directive entries from an old identity/directives.md body: each directive-heading
    block (title + its bullet fields, INCLUDING multi-line wrapped continuation lines) up to
    the next directive heading. Structural sections are excluded via _iter_directive_region
    (R2-P1). The whole directives.md is archived byte-identical, so nothing is lost. Returns
    the entry blocks, trimmed. Robust to `###Title` (no space) / deeper (C2)."""
    entries, cur = [], None
    for ln in _iter_directive_region(directives_body):
        s = ln.strip()
        if _DIRECTIVE_HEADING_RE.match(s):
            if cur is not None:
                entries.append(cur)
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        entries.append(cur)
    return [("\n".join(e)).rstrip() for e in entries if any(x.strip() for x in e)]


def _directive_signal_lines(directives_body):
    """The raw source lines that MUST land in the folded plan, derived INDEPENDENTLY of
    _extract_directive_entries so an extraction bug cannot hide a drop (C2 raw anchor): every
    directive title (###-family heading) + every field bullet (`key: value` bullet, bold or
    bare) OUTSIDE a structural `## ` section (shared _iter_directive_region -- R2-P1).
    Boilerplate (the `# ` H1, intro prose, and the structural sections with any illustrative
    `### ` / `- **...**` examples inside them) is not a signal: plan-main supersedes it and
    the archive preserves it byte-identical."""
    out = []
    for ln in _iter_directive_region(directives_body):
        s = ln.strip()
        if _DIRECTIVE_HEADING_RE.match(s) or _DIRECTIVE_FIELD_RE.match(s):
            out.append(ln.rstrip())
    return out


def _template_section_body(tmpl_body, heading):
    """The body lines under `heading` in a template body, up to the next `## ` heading."""
    collecting, buf = False, []
    for ln in tmpl_body.splitlines():
        s = ln.strip()
        if s == heading:
            collecting = True
            continue
        if collecting and s.startswith("## ") and not s.startswith("### "):
            break
        if collecting:
            buf.append(ln)
    return "\n".join(buf).strip("\n")


def _fold_into_plan(template_text, current_focus_body, standing_directives_body):
    """Build the new plans/PLAN.md from the plan-main.md template, replacing the bodies of
    `## Current focus` and `## Standing directives` (heading kept, template guide prose
    swapped for the folded content) and keeping every other section + the frontmatter +
    intro verbatim."""
    fm, _inner, body = _split_frontmatter(template_text)
    replacements = {
        "## Current focus": current_focus_body.rstrip("\n"),
        "## Standing directives": standing_directives_body.rstrip("\n"),
    }
    lines = body.splitlines()
    out, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if s in replacements:
            out.extend([lines[i], "", replacements[s], ""])
            i += 1
            while i < len(lines):
                s2 = lines[i].strip()
                if s2.startswith("## ") and not s2.startswith("### "):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    new_body = "\n".join(out).rstrip("\n") + "\n"
    return (fm or "") + new_body


def _migration_1_guard(sanctum_dir, templates_dir=None):
    """Entry #1 is applied once the old identity/directives.md is gone (folded + archived).
    A fresh farm (never had directives.md) also reads as applied -> harmless no-op advance.
    NB: this is the coarse 'done?' gate; the fine-grained RESUME of a partial run (PLAN.md
    folded but directives.md not yet removed) is handled inside _migration_1_apply, which
    never re-consumes its own output (C1)."""
    return not os.path.isfile(os.path.join(sanctum_dir, "identity", "directives.md"))


def _plan_required_sections(templates_dir):
    """The required H2 sections of the plan-main.md template (its structural signature)."""
    _b, inner, _body = _split_frontmatter(_read(os.path.join(templates_dir, "plan-main.md"))
                                          .decode("utf-8"))
    meta = _parse_frontmatter(inner) if inner is not None else {}
    return meta.get("required_sections", []) or []


def _is_resumable_fold(plan_text, signal_lines):
    """True iff plans/PLAN.md is ALREADY the folded output from a prior partial run: it
    already contains EVERY directive signal line. Then a retry must RESUME (finish
    archive+remove only), never re-fold its own output (C1). This is the sole reliable
    discriminator AND it is independent of plan-main's `required_sections` (R2-N1): a folded
    plan contains the directive signal lines; a fresh ad-hoc plan and a fresh empty-template
    plan do NOT -> neither is a false resume. Keying on structure would let a template that
    drops `required_sections` silently disable this guard -- so it does not. Sound because
    _safe_write is crash-atomic (os.replace): PLAN.md is always fully-old or fully-folded,
    never a partial write. (The directive-FREE partial-retry hole -- no signal lines to key
    on -- is closed by the frontmatter backstop in _migration_1_apply.)"""
    return bool(signal_lines) and all(s in plan_text for s in signal_lines)


def _directives_already_archived(archive_dir, orig_bytes):
    """A byte-identical directives-*.md archive already present? Returns its path or None.
    Lets a re-entry (same-day OR cross-day retry) reuse the existing archive instead of
    writing a duplicate copy (idempotent)."""
    if not os.path.isdir(archive_dir):
        return None
    for f in sorted(os.listdir(archive_dir)):
        if f.startswith("directives-") and f.endswith(".md"):
            p = os.path.join(archive_dir, f)
            if os.path.isfile(p) and _read(p) == orig_bytes:
                return p
    return None


def _archive_and_remove_directives(directives_path, sanctum_dir, orig_bytes, where):
    """Idempotent, prove-first archive+remove of directives.md: archive byte-identical (reuse
    an existing identical copy if present), VERIFY the archive equals the original, THEN
    staleness-checked-remove the source (a `.bak` first). Safe to re-enter after a partial
    run -- an absent source is a no-op remove. Returns the archive path."""
    archive_dir = os.path.join(sanctum_dir, "history", "archive")
    archive_path = _directives_already_archived(archive_dir, orig_bytes)
    if archive_path is None:
        stamp = datetime.date.today().isoformat()
        archive_path = os.path.join(archive_dir, f"directives-{stamp}.md")
        if os.path.exists(archive_path) and _read(archive_path) != orig_bytes:
            raise FileExistsError(archive_path)
        _atomic_write(archive_path, orig_bytes)
    if _read(archive_path) != orig_bytes:
        raise ConservationError(f"{where}: archived directives.md differs from the original")
    if os.path.isfile(directives_path):
        if _digest(_read(directives_path)) != _digest(orig_bytes):
            raise StaleManifestError(directives_path)
        _atomic_write(directives_path + ".bak", orig_bytes)
        os.remove(directives_path)
    return archive_path


def _migration_1_apply(sanctum_dir, templates_dir):
    """Fold identity/directives.md into plans/PLAN.md: directive entries -> ## Standing
    directives (verbatim); the ad-hoc plans/PLAN.md body -> ## Current focus (verbatim);
    plan-main.md supplies frontmatter + structural sections. RESUMABLE + idempotent (C1):
    a partial run (PLAN.md folded, directives.md still present) is detected and completed,
    never re-folded. Conservation is three independent layers (C1/C2): whole-block, raw
    source signal lines, and ad-hoc-body-exactly-once. Reuses _safe_write / _atomic_write /
    ConservationError. The Cyrus-voice narrative polish of ## Current focus is a deliberate
    later owner step -- this fold guarantees loss-free, not prose-rewritten (DEC-268)."""
    directives_path = os.path.join(sanctum_dir, "identity", "directives.md")
    plan_path = os.path.join(sanctum_dir, "plans", "PLAN.md")
    tmpl_path = os.path.join(templates_dir, "plan-main.md")
    where = "migrate:1 directives->plan"

    orig_directives_bytes = _read(directives_path)
    _dfm, _di, directives_body = _split_frontmatter(orig_directives_bytes.decode("utf-8"))
    directive_entries = _extract_directive_entries(directives_body)
    signal_lines = _directive_signal_lines(directives_body)

    plan_exists = os.path.isfile(plan_path)
    plan_bytes = _read(plan_path) if plan_exists else b""
    plan_text = plan_bytes.decode("utf-8") if plan_exists else ""

    # C1 RESUME: a prior partial run already folded PLAN.md but did not finish archive+remove.
    # Detect it and RESUME (finish only) -- never re-read the folded plan as an 'ad-hoc body'.
    if plan_exists and _is_resumable_fold(plan_text, signal_lines):
        archive_path = _archive_and_remove_directives(
            directives_path, sanctum_dir, orig_directives_bytes, where)
        return {"action": "resume-complete", "from": directives_path, "plan": plan_path,
                "archived": archive_path, "directive_entries": len(directive_entries),
                "conservation_ok": True,
                "changed": "completed a previously-interrupted fold "
                           "(archived + removed identity/directives.md)"}

    # R2-N1 directive-free backstop: signal-line resume can't fire when the source has NO
    # signals, so a directive-FREE partial retry could re-consume its own ad-hoc body. An
    # ad-hoc OLD plan carries NO frontmatter; a folded/template plan DOES. If we're about to
    # treat a frontmatter-bearing plan as the 'ad-hoc body' with no signals to confirm a safe
    # resume -> refuse (fail loud, backup intact), never risk a double-fold. Template-agnostic
    # (keys on frontmatter PRESENCE, not its content) so it can't be disabled by template drift.
    if plan_exists and not signal_lines and _split_frontmatter(plan_text)[0] is not None:
        raise ConservationError(
            f"{where}: plans/PLAN.md is already in the plan-lifecycle structure (has "
            "frontmatter) but identity/directives.md is directive-free, so a safe resume "
            "cannot be confirmed -- refusing to fold (would risk doubling the plan body). "
            "Resolve by hand; nothing was touched.")

    # C2 fail-loud: the source has directive content but NONE parsed into entries -> refuse
    # (never silently replace real directives with template boilerplate).
    if not directive_entries and signal_lines:
        raise ConservationError(
            f"{where}: identity/directives.md has directive content ({len(signal_lines)} "
            "signal line(s)) but none parsed into entries -- refusing to fold (would silently "
            "drop them). Fix the heading format or migrate by hand; nothing was touched.")

    old_plan_body = ""
    if plan_exists:
        _pfm, _pi, old_plan_body = _split_frontmatter(plan_text)

    template_text = _read(tmpl_path).decode("utf-8")
    _tfm, _ti, tmpl_body = _split_frontmatter(template_text)

    current_focus_body = old_plan_body.rstrip("\n") if old_plan_body.strip() \
        else _template_section_body(tmpl_body, "## Current focus")
    standing_directives_body = "\n\n".join(directive_entries) if directive_entries \
        else _template_section_body(tmpl_body, "## Standing directives")

    new_plan_text = _fold_into_plan(template_text, current_focus_body, standing_directives_body)

    # ---- conservation-prove (three independent layers) BEFORE any source removal ----
    # (1) whole-block: every recognized directive entry lands verbatim, INCLUDING multi-line
    #     wrapped continuation lines (they ride with their block).
    for e in directive_entries:
        if e not in new_plan_text:
            raise ConservationError(f"{where}: ## Standing directives dropped a directive entry")
    # (2) raw-source signal lines: every source directive title + field bullet lands -- even
    #     one whose block extraction FAILED to recognize (independent of extraction) (C2).
    for s in signal_lines:
        if s and s not in new_plan_text:
            raise ConservationError(
                f"{where}: ## Standing directives dropped a source directive line: {s.strip()!r}")
    # (3) ad-hoc body conserved EXACTLY ONCE -- present, and not DOUBLED (double-fold) (C1).
    if old_plan_body.strip():
        block = old_plan_body.rstrip("\n")
        n = new_plan_text.count(block)
        if n == 0:
            raise ConservationError(f"{where}: ## Current focus lost the ad-hoc plan body")
        if n > 1:
            raise ConservationError(
                f"{where}: ## Current focus holds the ad-hoc plan body {n}x -- double-fold aborted")

    # write the new plan (backup-before-write + crash-atomic + staleness-checked)
    if plan_exists:
        _safe_write(plan_path, new_plan_text, _digest(plan_bytes))
    else:
        _atomic_write(plan_path, new_plan_text.encode("utf-8"))

    # archive byte-identical + remove the source (idempotent, prove-first, inside the helper)
    archive_path = _archive_and_remove_directives(
        directives_path, sanctum_dir, orig_directives_bytes, where)

    return {"action": "fold", "from": directives_path, "plan": plan_path,
            "archived": archive_path, "directive_entries": len(directive_entries),
            "current_focus_source": plan_path if old_plan_body.strip() else "template-default",
            "conservation_ok": True,
            "changed": f"folded {len(directive_entries)} directive(s) from "
                       "identity/directives.md into plans/PLAN.md and archived the original"}


MANIFEST = [
    {
        "to_version": 1,
        "description": "Fold identity/directives.md into plans/PLAN.md (## Standing "
                       "directives) + the ad-hoc plan body into ## Current focus; archive "
                       "the old directives.md whole (item 7 / DEC-259).",
        "guard": _migration_1_guard,
        "apply": _migration_1_apply,
    },
]


def cmd_migrate(args):
    sanctum = args.path
    templates_dir = args.templates_dir
    apply = args.apply
    marker = _read_schema_version(sanctum)
    latest = max((e["to_version"] for e in MANIFEST), default=0)

    # Forward-only: a marker AHEAD of the newest migration this build knows means the sanctum
    # was written by a newer skill. Fail loud, wipe nothing, keep any backup (BP-069).
    if marker > latest:
        raise SchemaVersionError(
            f"sanctum_schema_version {marker} is ahead of the newest migration this skill "
            f"knows ({latest}) -- this sanctum was written by a newer farm-manager. "
            "Applying nothing; update the skill.")

    pending = sorted((e for e in MANIFEST if e["to_version"] > marker),
                     key=lambda e: e["to_version"])
    if not pending:
        return {"command": "migrate", "sanctum": sanctum, "apply": apply,
                "from_version": marker, "to_version": marker,
                "pending": 0, "up_to_date": True, "steps": []}

    steps, cur = [], marker
    for entry in pending:
        step = {"to_version": entry["to_version"], "description": entry["description"]}
        if entry["guard"](sanctum, templates_dir):
            # Already applied (e.g. a crash-and-rerun, or a fresh farm that never had the old
            # file) -> no source subtree changes, but the marker still gets recorded in
            # config.json (BUG-020: that write was previously unbacked -- "backup": None
            # while a restore point was destroyed). Back up config.json first, same as the
            # fold path below, so this is never the unprotected write.
            step["action"] = "already-applied"
            step["backup"] = None
            if apply:
                try:
                    step["backup"] = _backup_subtree(sanctum, ("config.json",),
                                                      entry["to_version"])
                    _write_schema_version(sanctum, entry["to_version"])
                except (OSError, ValueError) as e:
                    raise MigrationError(
                        f"migration to v{entry['to_version']} (already-applied) failed "
                        f"cleanly ({type(e).__name__}: {e}); nothing further applied. "
                        f"Pre-migration backup: {step.get('backup')}")
                step["marker_advanced"] = True
            cur = entry["to_version"]
            steps.append(step)
            continue
        if not apply:
            step["action"] = "pending"
            step["backup"] = None
            steps.append(step)
            continue
        # Backup AFTER the guard, so an idempotent rerun writes nothing at all. config.json
        # is included because _write_schema_version below writes it unconditionally on
        # success -- BUG-020: it was the one write this restore point did not cover.
        try:
            step["backup"] = _backup_subtree(sanctum, ("identity", "plans", "config.json"),
                                              entry["to_version"])
            step.update(entry["apply"](sanctum, templates_dir))   # raises ConservationError on loss
            _write_schema_version(sanctum, entry["to_version"])   # advance ONLY after conservation
        except (OSError, ValueError) as e:
            # Unexpected-but-clean-exit (missing template, non-UTF8, ENOSPC, FileExists race):
            # route through the clean-JSON/exit-nonzero contract instead of a raw traceback.
            # The pre-migration backup is already taken; nothing further is applied. The
            # meaningful data-safety classes (Conservation/Stale/Schema/ArchivePath) are NOT
            # in this tuple, so they propagate unchanged.
            raise MigrationError(
                f"migration to v{entry['to_version']} failed cleanly "
                f"({type(e).__name__}: {e}); nothing further applied. "
                f"Pre-migration backup: {step.get('backup')}")
        step["marker_advanced"] = True
        cur = entry["to_version"]
        steps.append(step)

    return {"command": "migrate", "sanctum": sanctum, "apply": apply,
            "from_version": marker, "to_version": cur if apply else marker,
            "pending": len(pending), "up_to_date": False, "steps": steps}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(description="Parity / migration / rotation for a farm's sanctum.")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="FRESH/STALE/UNVERIFIABLE per governed file")
    c.add_argument("path", help="a sanctum file or a sanctum directory")
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("reconcile", help="migrate a farm to the current templates")
    r.add_argument("path", help="the sanctum directory to migrate")
    r.add_argument("--templates-dir", default=TEMPLATES_DIR_DEFAULT)
    r.add_argument("--apply", action="store_true", help="apply changes (default: dry run)")
    r.set_defaults(func=cmd_reconcile)

    o = sub.add_parser("rotate", help="dispatch on (class, rotation_trigger)")
    o.add_argument("path", help="a governed file, or the journal directory")
    o.add_argument("--sanctum-dir", default=None, help="sanctum root (for resolving archive_target)")
    o.add_argument("--apply", action="store_true", help="apply changes (default: dry run)")
    o.set_defaults(func=cmd_rotate)

    mg = sub.add_parser("migrate", help="apply pending versioned structural migrations")
    mg.add_argument("path", help="the sanctum directory to migrate")
    mg.add_argument("--templates-dir", default=TEMPLATES_DIR_DEFAULT)
    mg.add_argument("--apply", action="store_true", help="apply changes (default: dry run)")
    mg.set_defaults(func=cmd_migrate)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except (StaleManifestError, ConservationError, ArchivePathError, SchemaVersionError,
            MigrationError) as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2))
        sys.exit(2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
