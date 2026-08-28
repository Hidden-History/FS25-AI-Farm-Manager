"""lint_append_only.py -- the three teeth that police the delta log (§ 8.4).

The delta log is the one artifact in this system that cannot be regenerated, and
"append-only" is a property nothing enforces by itself: a file opened "w" is
just as valid to the operating system as one opened "a". These are the teeth.

  TOOTH 1 -- STATIC. No shipped script opens a history-class path for writing,
            and no shell line in the tree redirects into one with `>`. Catches
            the defect BEFORE it destroys anything, which is the only useful
            time to catch it.
  TOOTH 2 -- WATERMARK. The log's line count never decreases and its first
            line's digest never changes. Either half alone is blind to one
            direction: a count catches a tail truncation, a first-line digest
            catches a head truncation, and losing one line off each end changes
            neither count nor tail. Both are checked.
  TOOTH 3 -- CHAIN. `seq` is contiguous and every `prev_source_set_hash`
            resolves to its predecessor's `source_set_hash`.

⚠ A LOST WATERMARK DEGRADES TOOTH 2 TO `UNCHECKABLE`, NEVER TO A PASS
(failure mode § 11.8). This is the whole reason the verdict vocabulary has three
values instead of two: "I could not check" and "I checked and it was fine" are
different answers, and a tool that collapses them tells you the log is intact
when it has no idea. `UNCHECKABLE` exits non-zero for the same reason.

⚠ A CHAIN BREAK ACROSS A RECORDED GAP IS NOT A FAILURE. That is exactly what a
gap record exists to say. Tooth 3 fails on an UNEXPLAINED break -- one with no
gap record accounting for it -- because an unexplained break means the loss was
never noticed, while an explained one means it was. Treating both as failures
would train a reader to ignore the tooth, which is how a tooth stops working.

(`UNCHECKABLE` is the post-rename structural word § 8.4 mandates. The word it
replaces is deliberately not written here, so this file adds nothing to that
rename's surface and needs no edit when it lands.)

Usage: python3 lint_append_only.py --config <sanctum>/config.json [--scripts-dir DIR]
Exit 0 = all three teeth pass. Exit 1 = any tooth failed or is UNCHECKABLE.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cache_layout as layout
import delta_log

PASS = "pass"
FAIL = "fail"
UNCHECKABLE = delta_log.UNCHECKABLE

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Writing modes that would destroy an append-only file. "a"/"ab" are the only
# acceptable ones; "r"/"rb" do not write at all.
DESTRUCTIVE_MODE = re.compile(r"""["'](w|w\+|wb|wb\+|x|xb|r\+)["']""")

# How a history-class path is REFERRED TO in code. Both the literal filenames and
# the way this layer actually names them through a variable -- a lint that only
# matched the literal string would have been blind to the one real writer in the
# tree, which opens `paths["log"]`.
HISTORY_TOKENS = (
    "delta-log", "delta_log", "history",
    '["log"]', "['log']", "LOG_NAME", "WATERMARK_NAME",
)

SHELL_REDIRECT = re.compile(r"(?<!>)>\s*[^\s|;&]*(delta[-_]log|history/)[^\s|;&]*")


def _open_calls(text):
    """Yield (start_offset, argument_text) for every `open(` call.

    Balanced-paren scanning rather than a regex, because the arguments routinely
    contain nested calls -- `open(os.path.join(root, "history", "x"), "w")` --
    and a `[^)]*` pattern stops dead at the FIRST close paren, which is the
    inner one. Measured: that naive form missed both a nested os.path.join and
    the layer's own `open(paths["log"], "w")`, so tooth 1 reported PASS over two
    real destructive writes.
    """
    for match in re.finditer(r"\bopen\s*\(", text):
        index = match.end()
        depth, start = 1, index
        while index < len(text) and depth:
            char = text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        yield match.start(), text[start:index - 1]

# This file writes those patterns down as literals, so scanning itself would
# report the lint as the worst offender in the tree. Excluded by exact name, so
# the exclusion cannot silently widen.
SELF = os.path.basename(__file__)


def tooth_1_static(scripts_dir):
    """No shipped script may open a history-class path for writing."""
    violations = []
    for name in sorted(os.listdir(scripts_dir)):
        if not name.endswith(".py") or name == SELF:
            continue
        path = os.path.join(scripts_dir, name)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for offset, args in _open_calls(text):
            targets_history = any(token in args for token in HISTORY_TOKENS)
            if targets_history and DESTRUCTIVE_MODE.search(args):
                violations.append({
                    "file": name,
                    "line": text[:offset].count("\n") + 1,
                    "evidence": ("open(" + args + ")")[:120],
                    "why": "opens a history-class path for writing; append-only "
                           "means mode 'a', and a 'w' here silently destroys a "
                           "history that cannot be reconstructed",
                })
        for match in SHELL_REDIRECT.finditer(text):
            violations.append({
                "file": name,
                "line": text[:match.start()].count("\n") + 1,
                "evidence": match.group(0)[:120],
                "why": "shell redirect into a history-class path truncates it",
            })
    if violations:
        return FAIL, "%d destructive write(s) into a history-class path" % len(violations), violations
    return PASS, None, []


def tooth_2_watermark(paths):
    """Line count never decreases; the first line's digest never changes."""
    watermark, err = delta_log.read_watermark(paths["watermark"])
    if err:
        return FAIL, err, {}
    if watermark is None:
        return UNCHECKABLE, (
            "no watermark on disk, so truncation of the delta log cannot be "
            "ruled out. This is NOT a pass -- it is the absence of a check, and "
            "it exits non-zero for exactly that reason."), {}

    break_reason, detail = delta_log.detect_break(paths["log"], watermark)
    if break_reason:
        return FAIL, break_reason, detail
    return PASS, None, detail


def tooth_3_chain(paths):
    """`seq` contiguous, and every `prev_source_set_hash` resolving.

    A break ACROSS a recorded gap is expected and is not a failure -- that is
    what the gap record says. An UNEXPLAINED break is the failure, because it
    means the loss was never noticed.
    """
    records, err = delta_log.read_log(paths["log"])
    if err:
        return FAIL, err, {}
    if not records:
        return UNCHECKABLE, (
            "no delta log on disk, so the chain cannot be checked. Not a pass: "
            "an absent history and an intact one are different answers."), {}

    problems = []
    previous = None
    for record in records:
        seq = record.get("seq")
        if not isinstance(seq, int):
            problems.append({"seq": seq, "problem": "seq is not an integer"})
            previous = record
            continue
        if previous is not None:
            expected = previous.get("seq", 0) + 1
            if seq != expected:
                problems.append({
                    "seq": seq, "problem": "seq is not contiguous",
                    "expected": expected,
                })
            if record.get("kind") == "delta" and previous.get("kind") == "delta":
                # Only delta-to-delta must chain; a gap record is the explicit
                # statement that the chain could not be continued.
                if record.get("prev_source_set_hash") != previous.get("source_set_hash"):
                    problems.append({
                        "seq": seq,
                        "problem": "prev_source_set_hash does not resolve",
                        "recorded": record.get("prev_source_set_hash"),
                        "predecessor": previous.get("source_set_hash"),
                    })
        previous = record

    detail = {
        "entries": len(records),
        "gaps": sum(1 for r in records if r.get("kind") == "gap"),
        "problems": problems,
    }
    if problems:
        return FAIL, "%d chain problem(s)" % len(problems), detail
    return PASS, None, detail


def main():
    argv = sys.argv[1:]
    config_path, scripts_dir = None, SCRIPT_DIR
    while argv:
        arg = argv.pop(0)
        if arg == "--config":
            if not argv:
                print(json.dumps({"error": "--config given with no path"}))
                sys.exit(1)
            config_path = argv.pop(0)
        elif arg == "--scripts-dir":
            if not argv:
                print(json.dumps({"error": "--scripts-dir given with no path"}))
                sys.exit(1)
            scripts_dir = argv.pop(0)
        else:
            print(json.dumps({"error": "unexpected argument %r" % arg}))
            sys.exit(1)
    if not config_path:
        print(json.dumps({
            "error": "usage: lint_append_only.py --config <sanctum>/config.json "
                     "[--scripts-dir DIR]"}))
        sys.exit(1)

    config, err = layout.load_config(config_path)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    sanctum_dir = os.path.dirname(os.path.abspath(config_path))
    paths = delta_log.history_paths(sanctum_dir)

    teeth = {}
    for name, (verdict, reason, detail) in (
        ("static", tooth_1_static(scripts_dir)),
        ("watermark", tooth_2_watermark(paths)),
        ("chain", tooth_3_chain(paths)),
    ):
        teeth[name] = {"verdict": verdict, "reason": reason, "detail": detail}

    verdicts = [t["verdict"] for t in teeth.values()]
    ok = all(v == PASS for v in verdicts)
    report = {
        "lint": "append-only discipline (spec sec. 8.4)",
        "log": paths["log"],
        "teeth": teeth,
        "ok": ok,
    }
    if not ok:
        failed = sorted(n for n, t in teeth.items() if t["verdict"] != PASS)
        report["error"] = (
            "APPEND-ONLY LINT FAILED: %s. An UNCHECKABLE tooth counts as a "
            "failure, never a pass -- absence of a check is not evidence of "
            "health." % ", ".join("%s=%s" % (n, teeth[n]["verdict"]) for n in failed))
    print(json.dumps(report, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
