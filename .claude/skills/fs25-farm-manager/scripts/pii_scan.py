"""
pii_scan.py -- invocable CLI scan for the author's private data, vendored from
the PII gate in tools/build_package.py (FORBIDDEN / FORBIDDEN_FLAGS).

WHY THIS EXISTS AS A SEPARATE, VENDORED COPY. tools/ is not shipped -- it is
absent from build_package.py's CONTENTS allowlist and from the live install --
so a closeout step that exports friction reports to a public tracker has
nothing to call for a pre-publish scan on a player's machine. This script IS
the gate, vendored and packaged as scripts/, so it ships.

Parity with the source is enforced at BUILD time, not trusted by inspection:
tests/test_pii_gate_parity.py (repo root, not shipped) asserts FORBIDDEN and
FORBIDDEN_FLAGS below are byte-identical to tools/build_package.py's, and fails
the build if they ever drift. Update both files in the same commit.

This file legitimately CONTAINS the literals the gate exists to catch, so
tools/build_package.py carries one narrow, named skip for exactly this file's
path (PII_SCAN_SKIP) -- otherwise the build would fail against itself.

WHAT THIS SCANS FOR (see FORBIDDEN below for the exact set): the author's
Windows username, the author's email/handle, the author's home directory, the
author's project directory name, and the generic absolute-path shapes that
identify a person or a dev machine -- WSL paths into a drive, Linux home
paths, macOS home paths, Windows user-profile paths, Windows drive paths into
a dev tree, and WSL UNC network paths.

Usage:
    python3 pii_scan.py --file <path>
    python3 pii_scan.py --text "<string>"

Output: one JSON object on stdout (indent=2). "checked_for" always lists the
categories actually scanned -- never a bare verdict like "PII gate passed":
naming what ran is the only way a caller can tell "found nothing" apart from
"checked less than you think" (CLAUDE.md DEC-102).

  ran, clean:    {"ok": true,  "matches": [], "checked_for": [...], ...}
  ran, found:    {"ok": true,  "matches": [{"line", "text", "why"}, ...], ...}
  did not run:   {"error": "...", "ok": false}

Exit codes -- deliberately THREE-WAY, not the two-way (0 / non-zero) some
sibling scripts here use, because "no matches" and "did not run" must never
collapse onto the same signal (CLAUDE.md "Absence must be impossible to
mistake for data"):
    0  ran; no forbidden pattern matched -- safe to publish as far as this
       scan can tell
    1  ran; matched >=1 forbidden pattern(s) -- do NOT publish
    2  did NOT run -- bad usage or an unreadable file; this is a refusal, not
       a clean result, and must not be read as "no matches"
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# Vendored, not imported: tools/build_package.py is not shipped (see module
# docstring). tests/test_pii_gate_parity.py (repo root) asserts this list and
# FORBIDDEN_FLAGS below are byte-identical to tools/build_package.py's own --
# update both in the same commit, or the build fails.
FORBIDDEN = [
    (r"[Uu]sers[/\\]pc\b", "the author's Windows username"),
    (r"hiddenhistory", "the author's email/handle"),
    (r"/home/parzival", "the author's home directory"),
    (r"AI-FS25", "the author's project directory"),
    (r"/mnt/[a-z]/(?!(?:Users|Windows|Program|ProgramData)(?![A-Za-z0-9._'-])|mods[\\/]+(?:FS25_[A-Za-z0-9_]+|(?:\u2026|\.\.\.)(?![A-Za-z0-9._'\\/ -])))[A-Za-z0-9][A-Za-z0-9._'-]*",
     "an absolute WSL path into someone's drive (use a relative path, ~, or an env var)"),
    (r"/home/[A-Za-z0-9][A-Za-z0-9._'-]*", "an absolute Linux home path (use ~ or an env var)"),
    (r"/Users/[A-Za-z0-9][A-Za-z0-9._'-]*", "an absolute home path with a real username (use ~ or <user>)"),
    (r"\b[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9][A-Za-z0-9._'-]*",
     "an absolute Windows user-profile path (use %USERPROFILE% or <user>)"),
    (r"\b[A-Za-z]:[\\/]+(?!(?:Users|Windows|Program|ProgramData)(?![A-Za-z0-9._'-])|mods[\\/]+(?:FS25_[A-Za-z0-9_]+|(?:\u2026|\.\.\.)(?![A-Za-z0-9._'\\/ -])))[A-Za-z0-9][A-Za-z0-9._'-]*",
     "an absolute Windows drive path into a dev tree (use a relative path or an env var)"),
    (r"[\\/]{2}wsl[$.]", r"an absolute WSL UNC network path (\\wsl$\... identifies your machine)"),
]
FORBIDDEN_FLAGS = re.IGNORECASE

CHECKED_FOR = [why for _pattern, why in FORBIDDEN]


def scan_text(text: str) -> list[dict]:
    """Every FORBIDDEN pattern against `text`. Mirrors the four lines at
    tools/build_package.py's _scan() inner loop, scoped to one string instead
    of a DIST.rglob() tree."""
    matches = []
    for pattern, why in FORBIDDEN:
        for m in re.finditer(pattern, text, FORBIDDEN_FLAGS):
            line = text[:m.start()].count("\n") + 1
            matches.append({"line": line, "text": m.group(0), "why": why})
    return matches


class _RefusingArgumentParser(argparse.ArgumentParser):
    """Bad usage is exit 2 here (a refusal -- the scan did not run), never
    exit 1 (which this script reserves for 'ran and found a match'). Collapsing
    those two would make a typo indistinguishable from a real, dangerous
    finding to any caller checking the exit code alone."""

    def error(self, message):
        print(json.dumps({"error": f"{message} ({self.format_usage().strip()})",
                          "ok": False}, indent=2))
        sys.exit(2)


def main(argv: list[str]) -> int:
    parser = _RefusingArgumentParser(
        prog="pii_scan.py",
        description="Scan a string or a file for the author's private data "
                    "before it is published.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", metavar="PATH", help="scan the contents of PATH")
    group.add_argument("--text", metavar="STRING", help="scan STRING directly")
    args = parser.parse_args(argv)

    if args.file is not None:
        try:
            text = open(args.file, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print(json.dumps({"error": f"could not read {args.file}: {e}",
                              "ok": False}, indent=2))
            return 2
        source = {"scanned": "file", "source": args.file}
    else:
        text = args.text
        source = {"scanned": "text", "source": None}

    matches = scan_text(text)
    result = {"ok": True, "checked_for": CHECKED_FOR, "matches": matches, **source}
    print(json.dumps(result, indent=2))
    return 1 if matches else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
