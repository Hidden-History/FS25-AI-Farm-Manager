"""
sanctum_maintain.py -- parity, migration, and rotation for a farm's sanctum files.

Three subcommands, built to the CP0-locked contract
(rebuild/FRONTMATTER-PARITY-SCHEMA.md + CANONICAL-TEMPLATE-LIST.md):

  check      Read each governed file's OWN frontmatter and answer FRESH / STALE /
             UNVERIFIABLE. Caps are measured CONTENT-only (the leading YAML
             frontmatter block is stripped first, per schema Section 1). config.json is
             special-cased against its required-keys list (schema Section 2) instead of
             frontmatter.

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
CONFIG_REQUIRED_KEYS = ["savegame_path", "farm_id", "paths"]
CONFIG_CONDITIONAL_KEY = "interest_rate_annual"

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


def _check_config_json(path):
    try:
        data = json.loads(_read(path).decode("utf-8"))
    except (ValueError, OSError) as e:
        return {"file": path, "verdict": UNVERIFIABLE, "reason": f"unreadable JSON: {e}"}
    missing = [k for k in CONFIG_REQUIRED_KEYS if k not in data]
    if missing:
        return {"file": path, "verdict": STALE,
                "reason": f"missing always-required key(s): {', '.join(missing)}"}
    # config.json cap_kb 8 (schema Section 2) -- JSON, measured whole (L-A).
    nbytes = len(_read(path))
    if nbytes > 8 * KB:
        return {"file": path, "verdict": STALE,
                "reason": f"over cap: {nbytes} B > cap_kb 8 ({8 * KB} B)"}
    if CONFIG_CONDITIONAL_KEY not in data:
        # No-loan farm (or rate unknown): cannot verify the conditional key -> not FRESH,
        # but explicitly NOT a defect. UNVERIFIABLE / N-A per schema Section 2.
        return {"file": path, "verdict": UNVERIFIABLE,
                "reason": f"{CONFIG_CONDITIONAL_KEY} absent -- N/A for a no-loan farm "
                          "(conditionally required only once a loan's rate is known)",
                "not_a_defect": True}
    return {"file": path, "verdict": FRESH, "reason": "all required keys present"}


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

    # Content-only cap measurement: frontmatter stripped, remainder measured.
    content_lines = _content_line_count(body)
    content_bytes = len(body.encode("utf-8"))
    cap_lines = meta.get("cap_lines")
    cap_kb = meta.get("cap_kb")
    over_cap = False
    cap_notes = []
    if isinstance(cap_lines, int) and content_lines > cap_lines:
        over_cap = True
        cap_notes.append(f"content {content_lines} lines > cap_lines {cap_lines}")
    if isinstance(cap_kb, int) and content_bytes > cap_kb * KB:
        over_cap = True
        cap_notes.append(f"content {content_bytes} B > cap_kb {cap_kb} ({cap_kb * KB} B)")

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
    if missing:
        result["verdict"] = STALE
        result["reason"] = f"missing required section(s): {', '.join(missing)}"
    elif over_cap:
        result["verdict"] = STALE
        result["reason"] = "over cap -- needs rotation: " + "; ".join(cap_notes)
    else:
        result["verdict"] = FRESH
        result["reason"] = "frontmatter present, all required sections present, within cap"
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
# archive a LIVE machine. Covers the domain's resolved states.
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


def _cell_has_marker(cell):
    up = cell.upper()
    return any(re.search(rf"\b{m}\b", up) for m in RESOLVED_MARKERS)


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


def _over_cap(meta, body):
    lines = _content_line_count(body)
    nbytes = len(body.encode("utf-8"))
    cl, ck = meta.get("cap_lines"), meta.get("cap_kb")
    return (isinstance(cl, int) and lines > cl) or (isinstance(ck, int) and nbytes > ck * KB)


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


# H-HONEST: a size/age trigger IMPLIES rotation should be possible; if the file is over cap
# but nothing is auto-rotatable (prose/list entries, H3 blocks, or an excluded-only table),
# `rotate` must NOT report a bare success -- it reports agent-rotation so unbounded
# growth is surfaced, not hidden. NB: building parsers for those prose/list/H3 shapes is a
# DEFERRED Lane-A/plan design decision (out of scope here) -- this signal is the correct
# Lane-B behavior until then.


def _manual(path, meta, reason):
    return {"file": path, "class": meta.get("class"), "rotation_trigger": meta.get("rotation_trigger"),
            "action": "agent-rotation", "reason": reason}


def rotate_file(path, sanctum_dir, apply):
    text = _read(path).decode("utf-8")
    fm_block, inner, body = _split_frontmatter(text)
    if fm_block is None:
        return {"file": path, "action": "skip", "reason": "no frontmatter -- not a governed capped file"}
    meta = _parse_frontmatter(inner)
    cls = meta.get("class")
    trig = meta.get("rotation_trigger")

    if trig == "none":
        return {"file": path, "class": cls, "rotation_trigger": trig,
                "action": "none", "reason": "write-once / mutated-in-place / overwritten -- no relocation"}

    tokens = _base_tokens(os.path.basename(path))

    # on-resolve: MOVE resolved rows, matched ONLY in a designated status column (H-D). A
    # register with no status column has no resolution signal -> report agent-rotation
    # (H-HONEST), never a silent no-op that hides unbounded growth.
    def _resolved(idx, cells, header):
        ci = _status_col(header)
        return ci is not None and ci < len(cells) and _cell_has_marker(cells[ci])

    def _has_status_column(data_idx, row_header):
        return any(_status_col(row_header.get(i)) is not None for i in data_idx)

    if trig == "on-resolve":
        _l, data_idx, row_header = _parse_tables(body)
        if data_idx and not _has_status_column(data_idx, row_header):
            # populated register with no resolution signal -> honest manual signal (H-HONEST)
            return _manual(path, meta,
                           "on-resolve needs a status/resolution column; none present "
                           "(status-less register or list/prose entries) -- Lane-A signal gap")
        if not data_idx and _over_cap(meta, body):
            return _manual(path, meta,
                           "on-resolve over cap but no auto-rotatable table rows (list/prose "
                           "entries or status-less) -- Lane-A template shape / agent rotation "
                           "(per template's `## Rotation` section)")
        # has a status column (move resolved / honest none) OR empty & within cap (honest none)
        return _move_rows(path, sanctum_dir, meta, _resolved, apply, tokens=tokens)

    if trig == "segment-and-retain":
        _lines, data_idx, _rh = _parse_tables(body)
        if len(data_idx) > 25:
            oldest = set(sorted(data_idx)[:15])
            return _move_rows(path, sanctum_dir, meta, lambda i, c, h: i in oldest, apply,
                              tokens=tokens, archive_header=_ledger_index_header, ledger_index=True)
        if _over_cap(meta, body):  # over cap but <=25 parseable ledger rows -> honest signal
            return _manual(path, meta,
                           "over cap but <=25 auto-segmentable ledger rows -- Lane-A template shape / "
                           "agent rotation (per template's `## Rotation` section)")
        return {"file": path, "class": cls, "rotation_trigger": trig, "action": "none",
                "data_rows": len(data_idx), "reason": "at or under 25 rows -- no segmentation"}

    if trig == "on-age":
        _lines, data_idx, _rh = _parse_tables(body)
        if len(data_idx) > 30:
            # L-B: archive only the OLDEST rows exceeding the ~30 threshold (contract F1 §10).
            excess = len(data_idx) - 30
            oldest = set(sorted(data_idx)[:excess])
            return _move_rows(path, sanctum_dir, meta, lambda i, c, h: i in oldest, apply, tokens=tokens)
        if _over_cap(meta, body):
            return _manual(path, meta,
                           "over cap but <=30 auto-archivable rows -- Lane-A template shape / "
                           "agent rotation (per template's `## Rotation` section)")
        return {"file": path, "class": cls, "rotation_trigger": trig, "action": "none",
                "data_rows": len(data_idx), "reason": "at or under ~30 rows -- no archival"}

    if trig in ("on-close-over-cap", "on-resolve+on-close-over-cap", "age-or-cap"):
        # The CP0 templates using these compound triggers keep their over-cap-archivable units
        # as PROSE/LIST entries (directives) or H3 blocks (friction-log FIXED/NOTED), NOT as
        # table rows -- and parsing those shapes is a DEFERRED Lane-A/plan design decision
        # (scope guard). So Lane B does NOT attempt generic table-row over-cap archival here
        # (that wrongly grabbed incidental legend/documentation tables); the live OPEN backlog
        # never rotates (M-A) and an over-cap file honestly reports agent-rotation.
        reports = []
        if trig in ("on-resolve+on-close-over-cap", "age-or-cap"):
            reports.append(_move_rows(path, sanctum_dir, meta, _resolved, apply, tokens=tokens))
        body_now = _split_frontmatter(_read(path).decode("utf-8"))[2]
        if _over_cap(meta, body_now):
            # H-HONEST: over cap and no auto-rotatable table units -> honest manual signal,
            # never a silent no-op / bare compound that implies the growth is handled. Carry
            # `steps` so an on-resolve move that DID happen (real archive + source rewrite) is
            # still visible alongside the over-cap overflow that needs manual/Lane-A rotation.
            return {**_manual(path, meta,
                              "over cap but over-cap-archivable units are prose/list entries or "
                              "H3 blocks (only excluded OPEN / legend tables present) -- deferred "
                              "Lane-A template shape / agent rotation (per template's "
                              "`## Rotation` section)"),
                    "steps": reports}
        reports.append({"action": "none", "reason": "within cap -- no over-cap rotation"})
        return {"file": path, "class": cls, "rotation_trigger": trig, "action": "compound",
                "steps": reports}

    if trig == "on-cap-relocate":
        if not _over_cap(meta, body):
            return {"file": path, "class": cls, "rotation_trigger": trig, "action": "none",
                    "reason": "within cap -- durable facts stay hot, no History relocation"}
        # M-B: relocate only the OLDEST '## History' rows needed to get back under cap.
        lines, data_idx, _rh = _parse_tables(body)
        hist = _rows_under_heading(lines, data_idx, "history")
        chosen = set()
        for i in sorted(hist):  # oldest (topmost) History rows first
            remaining = "\n".join(ln for j, ln in enumerate(lines) if j not in chosen)
            if not _over_cap(meta, remaining):
                break
            chosen.add(i)
        if not chosen:  # over cap but no History table rows to relocate (H-HONEST)
            return _manual(path, meta,
                           "over cap but no relocatable '## History' table rows found "
                           "(prose/no History table) -- Lane-A template shape / agent rotation "
                           "(per template's `## Rotation` section)")
        return _move_rows(path, sanctum_dir, meta, lambda i, c, h: i in chosen, apply, tokens=tokens)

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
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except (StaleManifestError, ConservationError, ArchivePathError) as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2))
        sys.exit(2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
