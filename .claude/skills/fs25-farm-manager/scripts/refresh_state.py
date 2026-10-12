"""refresh_state.py -- the generator's entry point (plan items 12, 13, 13a, 13c, 14).

⭐⭐ THE DELIVERABLE IS THAT THE MANAGER RUNS NOTHING. DEC-049 (3) and DEC-131:
this fires by itself -- no agent, no turn, no tokens -- and the manager READS
GENERATED ARTIFACTS. That is why SKILL.md no longer carries a script inventory
or a `python3 ...` block for reading state: the inventory moved into
state_inventory.py and is rendered by `--help` below, and the reading is done by
whatever this writes.

THE SYMPTOM THIS EXISTS TO FIX, in the owner's own words: "nothing has changed
in the tabs." Measured the same night -- the FARM tab renders `farm.xml`, which
a script generates, and NOTHING RAN THE SCRIPT. `farm.xml` was stamped
2026-09-03 15:38 while `contracts.xml`, the one file the MOD writes itself, was
current. The data was not wrong; it was simply nobody's job to refresh it.

THREE TRIGGERS, ONE GENERATOR:

  1. `now`  -- the manual trigger, and the ONLY command the manager ever runs.
               "Give me the current position, I have not saved." It bypasses
               the freshness no-op deliberately: the player is asking BECAUSE
               they know the cache's answer is not what they want.
  2. `auto` -- session start, and after the game writes a save. NO-OP when
               nothing changed, so it is safe to fire on a timer or a hook: it
               reads mtimes, finds the cache current, prints that, and writes
               nothing at all.
  3. the same `auto`, fired on save. See "WHERE THE AUTOMATIC FIRING LIVES".

AND ONE READ-ONLY RENDERER, WHICH REFRESHES NOTHING:

  `session-start` -- the session-start documents, under aggregate_render's own
               MAX_INLINE_ITEMS rule, applied recursively. It exists because
               that step's six documents measure 228,616 tokens against a real
               save and three of them are 99.57% of it. See the section headed
               "the pointer rule, applied uniformly" below -- in particular the
               constraint that a signal key is never elided, which is enforced
               by a gate rather than trusted to the summariser.

  `after-save` -- the SAME renderer over the one document workflow-briefing.md
               re-reads after every save the watcher absorbs: read_state.py.
               Measured 95,356 tokens against a real save, paid again on every
               save; see "AFTER-SAVE" below.

⚠ WHERE THE AUTOMATIC FIRING LIVES -- AN OPEN QUESTION, DELIBERATELY NOT
INVENTED HERE. This skill folder ships no hook configuration and cannot: hooks
live in the CONSUMING project's `.claude/settings.json`, which is the player's
farm directory, not ours. So this file makes automatic firing POSSIBLE -- one
argv-only entry point, cheap when nothing changed, safe to call repeatedly --
and stops there. What actually pulls the trigger is a decision for the owner,
and the candidates are written up in the completion report rather than silently
chosen here.

⛔ WHY `auto` MAY NOT SIMPLY READ AND PUBLISH. See the settle check in
cache_provenance.py: a save is 53 files written across ~8.7 seconds, and a
generator firing part-way through publishes a coherent-LOOKING mixture of two
moments, stamped ok. Neither mtime nor the content hash can see it. So every
path through this file settle-checks before it reads.

Usage:
    python3 refresh_state.py now  --config <sanctum>/config.json [--set DOMAIN ...]
    python3 refresh_state.py auto --config <sanctum>/config.json [--set DOMAIN ...]
    python3 refresh_state.py session-start --config <sanctum>/config.json
    python3 refresh_state.py after-save --config <sanctum>/config.json
    python3 refresh_state.py --help

Exit 0 = the cache is current (either it already was, or this run made it so).
Exit 1 = a structured {"error": ...} on stdout and nothing published.
Exit 3 = the save is still being written; nothing was read. Distinct from 1
         because it is not a fault -- it is "ask again in a moment" -- and a
         caller that cannot tell those apart will either alarm or retry wrongly.
"""
import json
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aggregate_render
import cache_layout as layout
import cache_provenance as provenance
import read_field_merges
import record_field_plan
import state_inventory
from generate_state import ENVELOPE_DOMAINS

TOOL = "refresh_state.py"
SUBCOMMANDS = ("now", "auto", "session-start", "after-save")
STATUS_FILE = "REFRESH-STATUS.json"

# The mod's bridge directory, as emit_farm_xml.py already derives it: the
# savegame folder's PARENT holds modSettings/. Copied rather than re-decided so
# the two scripts cannot disagree about where the bridge is.
MOD_NAME = "FS25_AIFarmManager25"
SAVE_MARKER_NAME = "save-marker.xml"

EXIT_OK, EXIT_ERROR, EXIT_STILL_SAVING = 0, 1, 3


def _fail(message, **extra):
    payload = {"error": message}
    payload.update(extra)
    print(json.dumps(payload, indent=2))
    sys.exit(EXIT_ERROR)


def help_text():
    """What `--help` prints: the inventory that used to live in SKILL.md.

    ⚠ GENERATED, NEVER TRANSCRIBED (BP-195). Every name below comes from
    state_inventory.SETS and generate_state.ENVELOPE_DOMAINS at the moment this
    runs, so the listing cannot drift from the code the way the SKILL.md table
    did. The registry can still drift from DISK -- that is what
    state_inventory.reconcile_with_disk() is for, and it is checked by the build
    gate rather than by this text.
    """
    return "\n".join([
        "refresh_state.py -- keep this farm's generated state current.",
        "",
        "  python3 refresh_state.py now  --config <sanctum>/config.json [--set DOMAIN ...]",
        "  python3 refresh_state.py auto --config <sanctum>/config.json [--set DOMAIN ...]",
        "  python3 refresh_state.py session-start --config <sanctum>/config.json",
        "  python3 refresh_state.py after-save --config <sanctum>/config.json",
        "",
        "  now    refresh regardless of the freshness verdict -- the manual",
        "         trigger, for \"give me the position now, I have not saved\".",
        "  auto   refresh only if a source actually moved. NO-OP otherwise:",
        "         nothing is written and nothing is published. Safe to fire on",
        "         session start, on save, or on a timer.",
        "",
        "  session-start   READ-ONLY. Drives the three session-start reads that",
        "         are 99.6% of that step's token cost (read_state.py,",
        "         farm_snapshot.py, read_game_log.py) and renders them under",
        "         aggregate_render's published rule: MAX_INLINE_ITEMS = "
        "%d, POINTER NEVER TRUNCATION, applied recursively at every"
        % aggregate_render.MAX_INLINE_ITEMS,
        "         depth. Writes nothing, refreshes nothing, and does NOT replace",
        "         the step's other three commands -- the document names them.",
        "         Every %s key is preserved and" % ", ".join(SIGNAL_KEYS),
        "         re-resolved in the emitted document before a line is printed;",
        "         one that cannot be re-found is a structured error and NO",
        "         document. LIMIT: this covers each document AS READ. A list a",
        "         reader's own renderer had already summarised lost members "
        "%d+" % (aggregate_render.MAX_INLINE_ITEMS + 1),
        "         before this saw them; a signal there is NOT covered, and that",
        "         envelope's read_the_rest_at is a read_state.py --list command",
        "         that prints the whole list (signal_preservation.limit counts them).",
        "",
        "  after-save   READ-ONLY. The same renderer and the same gate over",
        "         read_state.py alone -- the re-read the session makes after",
        "         every save. Names what it does not re-read.",
        "",
        "  --set DOMAIN   refresh one source set (repeatable). Omit for all sets.",
        "                 Not accepted by session-start or after-save.",
        "",
        "SOURCE SETS -- the per-set entry points, one per cached domain.",
        "A source set is the files ONE domain reads, so weather going stale",
        "never invalidates the ledger:",
        "",
    ] + ["      %s" % d for d in ENVELOPE_DOMAINS] + [
        "",
        "  all sets: omit --set entirely (%d domains)." % len(ENVELOPE_DOMAINS),
        "",
        "SCRIPT SETS -- every script this skill ships, and what each set covers.",
        "The automation calls these; a session does not:",
        "",
        state_inventory.render(),
    ])


# --- Item 13c: the reader AUDITS the save-marker, it never TRUSTS it ---------
#
# ⛔ THE HOOK IS REAL BUT UNDOCUMENTED. Four independent shipping mods use it
# across two hook points, and it has ZERO coverage in either authoritative
# source: `fs25-lookup` returned 0 hits over 1,661 pages across two queries, and
# `gameSource.zip`'s 951 Lua files returned 0 for all four entry points while a
# control query fired. AutoDrive's own source comment records the equivalent
# FS22 hook BREAKING in patch 1.5.
#
# So the failure mode to design for is not "the hook is wrong". It is "the hook
# silently stops firing" -- after a patch, with no error anywhere, leaving a
# marker file that is perfectly valid and simply old. A reader that trusted it
# would conclude "no save since Tuesday" and go quiet, which is the worst shape
# available: confidently current, actually frozen.
#
# THE AUDIT: compare the marker against the savegame's own mtime. The marker
# claims a save happened; the filesystem knows when one did. If the filesystem
# is AHEAD, the hook missed at least one save and the marker is not usable ->
# fall back to mtime for this run and SAY SO in the output. The fallback is not
# a degraded mode to hide; it is the normal mode until the Lua half ships, and
# it must be visible either way.
def audit_save_marker(marker_path, savegame_newest_mtime_ns):
    """Decide whether the mod's save-marker can be believed this run.

    Returns a dict that always carries `usable` (bool) and `reason`. Never
    raises: every way this can go wrong is a reason to fall back, and a
    traceback out of an audit would take down the refresh it was protecting.
    """
    audit = {
        "marker_path": marker_path,
        "savegame_newest_mtime_ns": savegame_newest_mtime_ns,
        "usable": False,
        "fallback": "savegame mtime",
    }
    if not os.path.isfile(marker_path):
        audit["reason"] = (
            "no save-marker present. The mod's save hook is not shipping one "
            "yet, so this run reads the savegame's own mtimes instead. Absent "
            "is not an error -- it is the current expected state.")
        audit["marker_mtime_ns"] = None
        return audit
    try:
        marker_mtime_ns = os.stat(marker_path).st_mtime_ns
    except OSError as exc:
        audit["reason"] = ("save-marker exists but could not be stat'd (%s), so "
                           "it cannot be audited and is not trusted"
                           % (exc.strerror or exc))
        audit["marker_mtime_ns"] = None
        return audit

    audit["marker_mtime_ns"] = marker_mtime_ns
    if savegame_newest_mtime_ns is None:
        audit["reason"] = (
            "the savegame's own mtime could not be read, so there is nothing to "
            "audit the marker AGAINST. An unaudited marker is not a trusted "
            "marker.")
        return audit

    lag_seconds = round((savegame_newest_mtime_ns - marker_mtime_ns) / 1e9, 3)
    audit["marker_lag_seconds"] = lag_seconds
    if marker_mtime_ns < savegame_newest_mtime_ns:
        audit["reason"] = (
            "STALE MARKER: the savegame was written %.3f s AFTER the marker, so "
            "the mod's save hook missed at least one save. This is exactly the "
            "silent-stop the audit exists to catch (AutoDrive's FS22 hook broke "
            "the same way in 1.5). Falling back to savegame mtime."
            % lag_seconds)
        return audit

    audit["usable"] = True
    audit["fallback"] = None
    audit["reason"] = ("marker is at or ahead of the savegame's newest write, so "
                       "the hook fired for the most recent save")
    return audit


# --- Publishing what the player actually SEES --------------------------------
#
# ⭐ THE OWNER'S SYMPTOM WAS "nothing has changed in the tabs", and regenerating
# the cache alone would not have fixed it. The FARM tab renders `farm.xml`, which
# `emit_farm_xml.py` writes; the tab was stale because nothing ran that script.
# So a refresh that stops at the cache would leave the visible half exactly as
# broken as it was found.
#
# ⚠ BEST-EFFORT, AND NEVER SILENT. A failed publish does not fail the refresh --
# the cache is still correct and useful, and emit_farm_xml.py has its own guard
# refusing to let a degraded run overwrite a good document. But its `notes` and
# `refused` are carried out verbatim: a run with notes is a DEGRADED publish and
# must never be reported as a clean one.
def publish_farm_tab(scripts_dir, savegame_dir, farm_id, mods_dir, config_path=None):
    if not mods_dir or "{{" in str(mods_dir):
        return {"published": False,
                "reason": "config.paths.mods_dir is not set, so the FARM tab's "
                          "modded store/land prices cannot be resolved. Said "
                          "plainly rather than publishing a quietly thinner "
                          "document."}
    cmd = [sys.executable, os.path.join(scripts_dir, "emit_farm_xml.py"),
           savegame_dir, "--mods-dir", mods_dir]
    # ⛔ F8 / architect V-3: the low-fuel row resolves vehicle tanks from the game
    # INSTALL, whose path lives in this config. It is passed EXPLICITLY -- the
    # emitter must never find it from the working directory, where a run from
    # the wrong place degrades silently.
    if config_path:
        cmd += ["--config", os.path.abspath(config_path)]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    try:
        report = json.loads(run.stdout)
    except json.JSONDecodeError:
        return {"published": False,
                "reason": "emit_farm_xml.py produced output that is not JSON, so "
                          "this run cannot say whether the tab was updated",
                "exit_code": run.returncode,
                "stderr": run.stderr[:1000]}
    return {"published": bool(report.get("written")),
            "degraded": bool(report.get("notes")) or bool(report.get("refused")),
            "exit_code": run.returncode,
            "report": report}


# ⭐ THE TWO SIBLINGS OF publish_farm_tab, ADDED 2026-09-07 -- THE ACTUAL DEFECT.
#
# FIELDS and PRODUCTIONS were built, committed and deployed, and both tabs still
# rendered "not available yet" -- because NOTHING EVER RAN THEIR EMITTERS. The
# FARM tab worked for exactly one reason: publish_farm_tab existed and had no
# siblings, so `farm.xml` was written on every refresh while `fields.xml` and
# `productions.xml` had never been written ONCE. Measured 2026-09-07 under
# modSettings/FS25_AIFarmManager25/: 9 files present, farm.xml x3, fields.xml 0,
# productions.xml 0. The emitters were correct on disk the whole time and simply
# unreachable -- registering them in state_inventory.SETS fixed the paperwork and
# connected nothing.
#
# ⚠ THE PLACEHOLDER WAS NEVER THE BUG. `fm25_fields_empty` and
# `fm25_productions_unavailable` name OUR GAP and are distinct from
# `fm25_fields_none` / `fm25_productions_none`, which describe the PLAYER'S farm.
# The tabs were correctly reporting an absent document. Do not weaken them.
#
# These follow publish_farm_tab EXACTLY -- same subprocess shape, same JSON
# contract, same best-effort-but-never-silent rule. publish_farm_tab is left
# UNTOUCHED: it works, and the emitters themselves are siblings-by-copy whose
# docstrings say they follow emit_farm_xml.py exactly, so a sibling call site is
# the idiom this codebase already uses.


def _run_emitter(cmd, script_name):
    """Run one emitter and carry its own report out verbatim.

    ⚠ NEVER SILENT. A failed publish does not fail the refresh -- the cache is
    still correct -- but `notes` and `refused` travel out untouched: a run with
    either is a DEGRADED publish and must never be reported as a clean one.
    Shared by the two functions below only; publish_farm_tab keeps its own copy
    so the path that already works is not rewritten to add two that did not.
    """
    run = subprocess.run(cmd, capture_output=True, text=True)
    try:
        report = json.loads(run.stdout)
    except json.JSONDecodeError:
        return {"published": False,
                "reason": "%s produced output that is not JSON, so this run "
                          "cannot say whether the tab was updated" % script_name,
                "exit_code": run.returncode,
                "stderr": run.stderr[:1000]}
    return {"published": bool(report.get("written")),
            "degraded": bool(report.get("notes")) or bool(report.get("refused")),
            "exit_code": run.returncode,
            "report": report}


def tab_publish_problems(publishes):
    """⛔ F11(1) / BUG-036. One line per tab that was NOT published cleanly --
    refused, published degraded, or not published at all -- in the words its
    emitter chose. `result: "refreshed"` stays true of the CACHE; this is what
    says the TABS are not, and the watcher's REFRESH line prints it. It used to
    read `REFRESH auto exit=0 refreshed` while the FIELDS tab was refused."""
    problems = []
    for tab, pub in publishes:
        report = pub.get("report") or {}
        refused = report.get("refused")
        notes = "; ".join(str(n) for n in (report.get("notes") or []))
        if refused:
            # The CAUSE first: `refused` is often generic ("nothing was
            # collected"), and the note names why.
            problems.append("%s tab REFUSED: %s" % (
                tab, (notes[:300] + " -- " + str(refused)[:120]) if notes
                else str(refused)[:300]))
        elif not pub.get("published"):
            # Review L2: an emitter's own {"error": ...} is the cause -- never
            # collapse it into "no reason given".
            why = pub.get("reason") or report.get("error") or notes or "no reason given"
            problems.append("%s tab NOT PUBLISHED: %s" % (tab, str(why)[:300]))
        elif pub.get("degraded"):
            problems.append("%s tab published DEGRADED: %s" % (tab, notes[:300]))
    return problems


def publish_fields_tab(scripts_dir, savegame_dir, farm_id, mods_dir, dossier_dir):
    """Publish fields.xml for THIS savegame, or say plainly why not.

    ⛔ TWO PRECONDITIONS, AND A MISSING ONE IS REPORTED, NEVER DEFAULTED.
    emit_fields_xml.py refuses without --dossier-dir under its guard E1: a caller
    who says nothing about merges has not said there are none, and the difference
    is five fields published at up to a fifth of their true area.
    """
    if not mods_dir or "{{" in str(mods_dir):
        return {"published": False,
                "reason": "config.paths.mods_dir is not set, so "
                          "read_farmland_areas.py cannot resolve the map and no "
                          "field area or ownership can be resolved at all. Said "
                          "plainly rather than publishing a document with every "
                          "area unknown."}
    if not dossier_dir or not os.path.isdir(dossier_dir):
        return {"published": False,
                "reason": "the field-dossier directory %r does not exist, so this "
                          "run cannot tell a save with no merged fields from one "
                          "whose merges it failed to read (guard E1). An "
                          "uncollapsed list is not a smaller correct answer -- it "
                          "is five wrong areas." % dossier_dir}
    # the plan store sits beside the dossier directory: sanctum/state/field-plan.md
    plan_file = os.path.join(os.path.dirname(os.path.abspath(dossier_dir)), "field-plan.md")
    # A sanctum made before the store existed has no plan file. Create it (never overwrite) so
    # the emitter's "missing" answer stays a real fault, not the state of every older sanctum.
    plan_file_status = record_field_plan.ensure_plan_file(plan_file)
    cmd = [sys.executable, os.path.join(scripts_dir, "emit_fields_xml.py"),
           savegame_dir, "--mods-dir", mods_dir, "--dossier-dir", dossier_dir,
           "--plan-file", plan_file]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    result = _run_emitter(cmd, "emit_fields_xml.py")
    result["plan_file"] = plan_file_status
    return result


def publish_productions_tab(scripts_dir, savegame_dir, farm_id, domains_dir, mods_dir):
    """Publish productions.xml for THIS savegame, or say plainly why not.

    ⚠ AN EMPTY DOCUMENT IS A REAL ANSWER HERE and must still be published: a farm
    that owns no production points renders `fm25_productions_none` ("You own no
    production buildings"), which is a statement about the PLAYER'S farm. Suppress
    the write and the tab falls back to `fm25_productions_unavailable`, which
    names OUR gap -- reporting a working manager as a broken one.

    ⛔ `mods_dir` FORWARDED, FIX ROUND 1 (D4/D5): without it every mod-backed
    production point renders `<unnamed>` and D4's resolution never reaches the
    screen -- the exact seam a review found between this lane and the emitter,
    both individually green. best-effort, same as its two siblings above: a
    missing mods_dir degrades names, never fails the publish.

    ⛔ M2 (fix round 3): a fresh install's unfilled `config.paths.mods_dir`
    placeholder is `"{{...}}"`, which the two siblings above REFUSE outright
    (`not mods_dir or "{{" in str(mods_dir)`). This function must not refuse
    the whole publish the same way -- the empty-document case above forbids
    it -- so it reuses that exact guard only to decide whether to FORWARD the
    value, never the sibling's stronger "fail the publish" response. Left
    ungated, `--mods-dir {{...}}` reaches the emitter, every mod-backed point
    fails to read `{{...}}/X.zip`, and (per H1/DEC-212) that renders as a
    derived label with a spurious reason instead of the plain "not set" the
    siblings say.
    """
    if not domains_dir or not os.path.isdir(domains_dir):
        return {"published": False,
                "reason": "the cache domains directory %r does not exist, so "
                          "production_defs.json cannot be read. Guessing another "
                          "one would read another farm's definitions."
                          % domains_dir}
    cmd = [sys.executable, os.path.join(scripts_dir, "emit_productions_xml.py"),
           savegame_dir, "--cache-dir", domains_dir]
    if mods_dir and "{{" not in str(mods_dir):
        cmd += ["--mods-dir", mods_dir]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    return _run_emitter(cmd, "emit_productions_xml.py")


# --- `session-start`: the pointer rule, applied uniformly --------------------
#
# ⭐ THE PROBLEM IS DOCUMENT SIZE, NOT INVOCATION COUNT. Measured against a real
# savegame copy, session-steps/s2-take-delivery.md's six documents total 228,616
# tokens, and THREE of them are 99.57% of it: read_state.py (92,407),
# farm_snapshot.py (103,067), read_game_log.py (32,149). Collapsing the six calls
# into one entry point would save well under 1%. What actually costs is that two
# of those documents are dominated by rows the step EXPLICITLY says not to
# surface -- a mod inventory (83% of read_game_log on the farm measured) and a
# per-vehicle dump (56% of farm_snapshot on that farm).
#
# So this subcommand changes nothing about what is READ and everything about what
# is RENDERED: it drives the three real entry points and applies
# aggregate_render.MAX_INLINE_ITEMS -- the rule that module already publishes --
# recursively, to every list at every depth, instead of only to the one level
# aggregate_render itself reaches.
#
# ⛔ THE CONSTRAINT THAT MAKES THIS SAFE, AND IT IS NOT A COMMENT.
#
# A previous lane held that the fleet's signal keys are safe from elision because
# "they are scalars and dicts, never list members." That is FALSE. Signal keys
# demonstrably DO live inside list members, at sites like --
#
#     aggregate.domains.fields.sections.field_state.data[i]
#         .operations_this_state_calls_for[j].detail.status
#     aggregate.domains.fields.sections.field_work.data[i]
#         .operations[j].detail.status
#
# ⛔ DO NOT TRUST ANY COUNT OF THEM, INCLUDING ONE MEASURED HERE. Four
# instruments have now been pointed at this question and all four disagree:
# two static AST sweeps returned 3 and 4 and both provably under-count (neither
# sees read_fields.py's, which a helper builds); a runtime sweep of the RENDERED
# document returned 7; and the same runtime sweep over the underlying cache
# returned 251, because the renderer had already elided the rest before the
# earlier sweep could see them. Every instrument under-counts, so the true
# population is larger than any figure anyone has quoted.
#
# THAT IS AN ARGUMENT FOR A STRUCTURAL GUARD, NOT A NARROWER ONE. Nothing below
# enumerates a site. collect_signals() walks for a KEY NAME at any depth, so a
# structure a helper builds at runtime is caught exactly like a literal one, and
# a site nobody has found yet is caught the first time it appears.
#
# None is dropped TODAY, and only for one reason: their parent lists are exactly
# 5 long, and the rule elides on len > 5. `operations_this_state_calls_for` is
# EXACTLY at the limit, and in the live save the single non-null `detail.status`
# in each sits at index 2 -- the middle of a list one entry away from being
# summarised. A field that ever calls for a sixth operation loses an operation's
# status from the rendered view.
#
# ⚠ AND THE HARM IS NARROWER THAN "SILENT" -- SAY IT ACCURATELY. summarise()
# emits an `_elided` marker, a true item_count and a pointer, so the OMISSION is
# flagged. `silent` is this project's founding failure mode and must not be used
# loosely. What is NOT flagged is WHAT was omitted: a reader cannot tell an
# elision that dropped 117 routine rows from one that dropped a `blocked_by`.
# The signal is pushed out of the view an agent reads inline, behind a pointer it
# may not follow, and the envelope gives it no reason to follow it. That is the
# real harm, it is real enough to design for, and hoisting is a proportionate
# answer to it -- it puts the signal back in the view and leaves the bulk behind
# the pointer.
#
# THE PROPERTY: a signal key is NEVER elided. Two mechanisms enforce it, and the
# second is why this is construction rather than diligence.
#
#   1. HOIST BEFORE SUMMARISING. Before a list is replaced by its envelope, every
#      signal in every member about to be elided is lifted out -- with its
#      ORIGINAL json_path -- into `elided_signals` on that envelope. And a signal
#      key's own VALUE is never itself summarised: it is copied verbatim, so
#      "preserved" means the same bytes, not a smaller version of them.
#   2. A CONSERVATION GATE THAT RUNS BEFORE A SINGLE LINE IS EMITTED. Every
#      signal found in the UNTRANSFORMED document is re-resolved IN THE EMITTED
#      ONE, through aggregate_render's own resolver, and compared by value AND
#      type. A miss yields {"error": "SIGNAL DROPPED: ..."} and NO document.
#
# That second mechanism is the point. A test proves the transform is correct
# today; the gate is what makes a dropped signal impossible TOMORROW, when
# someone edits the summariser and the suite is not watching. It is deliberately
# the same shape as aggregate_render.validate_claims -- "⚠ THIS RUNS BEFORE A
# SINGLE LINE IS EMITTED. A figure validated after printing is a figure that was
# already believed."

# The keys whose loss is invisible. `error` is the loudest; the other three are
# the ones s2-take-delivery.md's rule ① exists because callers forget:
# `calibration_needed` ("could not confidently parse this source"), per-section
# `status`, and `blocked_by` -- which arrives with NO error key at all and is
# therefore rated clean by any check that looks only for one.
SIGNAL_KEYS = ("blocked_by", "calibration_needed", "error", "status")

# The elision envelope's own keys, so a lookup can tell one of OUR envelopes from
# farm data that happens to look like one. Kept beside the writer that emits them.
ELISION_KEYS = ("_elided", "item_count", "shown", "read_the_rest_at", "note",
                "elided_signals")


def _path_join(prefix, part):
    """Dotted json_path, list indices as bare numeric segments. FOR READING.

    ⛔ DISPLAY ONLY -- NEVER THE THING THE GATE RESOLVES. A dotted string is a
    LOSSY encoding of a path, and this project's own data breaks it: a dict keyed
    by something containing a "." (a map name like `<mod>.<map>`, a filename, a
    version) produces a path that re-resolves to the WRONG place or to nothing.

    Measured, on the shipped gate before this was fixed: a signal under a
    dotted key made the conservation check report SIGNAL DROPPED for a signal
    that was present and correct -- and because a refusal emits no document,
    that FALSE positive would have taken down every session start on a farm
    whose data happened to carry one. A guard that can refuse a healthy briefing
    is worse than the elision it was protecting against.

    So the gate walks SEGMENTS (see _resolve_segments) and this string exists
    for the human reading `elided_signals[].json_path`. Reusing
    aggregate_render.resolve_json_path was the earlier design and is deliberately
    abandoned here: reuse that produces a false refusal is not reuse worth
    having, and a segment list is not a competing opinion about what a path
    names -- it is the encoding that does not lose the answer.
    """
    return part if not prefix else "%s.%s" % (prefix, part)


def _resolve_segments(document, segments):
    """Walk an EXACT path. Returns (value, True) or (None, False).

    Segments are dict keys (str) and list indices (int), kept apart by type, so
    a dict key that looks like a number and a list index can never be confused
    for one another either.
    """
    node = document
    for part in segments:
        if isinstance(part, int):
            if not isinstance(node, list) or part >= len(node):
                return None, False
            node = node[part]
        else:
            if not isinstance(node, dict) or part not in node:
                return None, False
            node = node[part]
    return node, True


def collect_signals(node, path="", segments=()):
    """Every signal key anywhere in `node`, with its json_path, segments, value.

    ⛔ ENUMERATES NOTHING. This walks for a KEY NAME at any depth; it holds no
    list of known sites and cannot be out of date with respect to one. That is
    deliberate and it is the whole design: every static sweep anyone has run at
    this question has UNDER-counted, in both directions, and none of them sees a
    structure a helper builds at runtime. Measured on this farm: a sweep of the
    RENDERED document finds 7, while the same property over the underlying cache
    finds 251 -- because the renderer had already elided the rest before the
    sweep could see them. A guard built against any of those figures would
    protect the sites someone thought of. This one protects the property.

    KEY PRESENCE IS THE SIGNAL, NEVER TRUTHINESS. In the live save four of the
    five `detail.status` entries per operation are None -- a `status` of None is
    still a status that was reported, and a collector that skipped falsy values
    would report the document as carrying one signal where it carries five.
    """
    found = []
    if isinstance(node, dict):
        for key in node:
            value = node[key]
            if key in SIGNAL_KEYS:
                found.append({"json_path": _path_join(path, key),
                              "segments": tuple(segments) + (key,),
                              "key": key, "value": value})
            found.extend(collect_signals(
                value, _path_join(path, key), tuple(segments) + (key,)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(collect_signals(
                value, _path_join(path, str(index)), tuple(segments) + (index,)))
    return found


def summarise_deep(node, pointer_root, orig_path="", out_path="", preserved=None,
                   orig_segments=(), out_segments=()):
    """Apply aggregate_render's published rule to every list at every depth.

    Returns (transformed, preserved) where `preserved` records, for every signal
    in the INPUT, the json_path it had and the path it now occupies in the
    OUTPUT. The gate below re-resolves those output paths against the emitted
    document; this list is the transform's account of itself, and the gate is
    what refuses to take that account on trust.

    ⚠ MAX_INLINE_ITEMS IS IMPORTED, NEVER RE-DECLARED. A second copy of the
    number is a second rule that can drift from the published one, and the whole
    claim of this subcommand is that it applies THAT rule rather than a similar
    one of its own.

    ⚠ A SCALAR IS NEVER TOUCHED. Only lists longer than the limit are replaced,
    and always by an envelope that SAYS how many items it stands for and where to
    read them -- never by a shorter list, which would be a silent truncation
    indistinguishable from a farm that really has five.
    """
    if preserved is None:
        preserved = []
    limit = aggregate_render.MAX_INLINE_ITEMS

    if isinstance(node, dict):
        out = {}
        for key in node:
            value = node[key]
            child_orig = _path_join(orig_path, key)
            child_out = _path_join(out_path, key)
            child_orig_seg = tuple(orig_segments) + (key,)
            child_out_seg = tuple(out_segments) + (key,)
            if key in SIGNAL_KEYS:
                # VERBATIM. Summarising a signal's own value would "preserve" a
                # smaller version of the thing whose loss is the failure mode --
                # a `blocked_by` of twenty entries rendered as five, still called
                # preserved.
                out[key] = value
                preserved.append({"json_path": child_orig, "key": key,
                                  "value": value, "now_at": child_out,
                                  "segments": child_orig_seg,
                                  "now_at_segments": child_out_seg})
                continue
            out[key] = summarise_deep(value, pointer_root, child_orig,
                                      child_out, preserved,
                                      child_orig_seg, child_out_seg)[0]
        return out, preserved

    if isinstance(node, list):
        if len(node) <= limit:
            return [summarise_deep(item, pointer_root,
                                   _path_join(orig_path, str(i)),
                                   _path_join(out_path, str(i)), preserved,
                                   tuple(orig_segments) + (i,),
                                   tuple(out_segments) + (i,))[0]
                    for i, item in enumerate(node)], preserved

        shown = [summarise_deep(item, pointer_root,
                                _path_join(orig_path, str(i)),
                                _path_join(out_path, "shown.%d" % i), preserved,
                                tuple(orig_segments) + (i,),
                                tuple(out_segments) + ("shown", i))[0]
                 for i, item in enumerate(node[:limit])]

        # ⛔ HOIST FIRST. Collected from the ORIGINAL members, before anything is
        # dropped, at any depth inside them -- a status three levels down inside
        # an elided member is exactly as invisible as one at its top.
        hoisted = []
        for index in range(limit, len(node)):
            hoisted.extend(collect_signals(
                node[index], _path_join(orig_path, str(index)),
                tuple(orig_segments) + (index,)))

        envelope = {
            "_elided": True,
            "item_count": len(node),
            "shown": shown,
            # ⛔ THE PATH HALF IS THE SEGMENT LIST, AS JSON -- never the dotted
            # display string, which _path_join's own docstring calls lossy. A
            # reader who parses this pointer must land where the gate would.
            "read_the_rest_at": "%s :: %s" % (pointer_root,
                                              json.dumps(list(orig_segments))),
            "note": "%d items elided, not truncated -- the full list is at the "
                    "path above." % (len(node) - limit),
        }
        if hoisted:
            # The reader gets json_path/key/value; `segments` is the exact
            # encoding and is dropped from the emitted copy to keep the
            # envelope small -- the gate uses it from `preserved`, not from here.
            envelope["elided_signals"] = [
                {"json_path": s["json_path"], "key": s["key"], "value": s["value"]}
                for s in hoisted]
            envelope["elided_signal_count"] = len(hoisted)
            for slot, signal in enumerate(hoisted):
                preserved.append({
                    "json_path": signal["json_path"], "key": signal["key"],
                    "value": signal["value"],
                    "segments": signal["segments"],
                    "now_at": _path_join(out_path, "elided_signals.%d.value" % slot),
                    "now_at_segments": tuple(out_segments) + (
                        "elided_signals", slot, "value"),
                })
        return envelope, preserved

    return node, preserved


def conserve_signals(before, emitted, preserved):
    """Re-find every signal of the untransformed document IN THE EMITTED ONE.

    Returns None, or the text of a structured error. THE CALLER MUST EMIT
    NOTHING when this returns a message.

    TWO INDEPENDENT HALVES, which is what stops this checking its own opinion:

      * the ACCOUNT -- every signal collect_signals() finds in `before` must
        appear in `preserved`. This catches a transform that dropped a member
        without noticing.
      * the ARTIFACT -- each preserved entry's recorded location is resolved
        against the document that is actually about to be printed, and compared
        by value AND type. This catches a transform that recorded a location it
        did not deliver.

    ⛔ BOTH HALVES KEY ON SEGMENTS, NEVER ON THE DOTTED STRING. A dotted path is
    ambiguous the moment a dict key contains a "." -- and this project's own data
    is full of names that do. Keying on it produced a FALSE `SIGNAL DROPPED` for
    a signal that was present and correct, which, because a refusal emits no
    document, would have blocked the briefing entirely. A guard that can refuse a
    healthy session start is worse than the elision it was written to prevent.

    The type comparison is aggregate_render.validate_claims' own: `True` and `1`
    compare equal in Python, and a status that changed type between the read and
    the render is precisely the drift a value-only check waves through.
    """
    accounted = {}
    for entry in preserved:
        accounted.setdefault(
            (entry["segments"], entry["key"]), []).append(entry)

    for signal in collect_signals(before):
        key = (signal["segments"], signal["key"])
        entries = accounted.get(key)
        if not entries:
            return ("SIGNAL DROPPED: %s (%r) is present in the document as read "
                    "and the summariser kept no record of it. A summary that "
                    "loses a signal is the aggregator destroying the evidence "
                    "its components produced, and it is invisible to "
                    "the reader -- so nothing is emitted."
                    % (signal["json_path"], signal["key"]))
        entry = entries[0]
        value, found = _resolve_segments(emitted, entry["now_at_segments"])
        if not found:
            return ("SIGNAL DROPPED: %s (%r) was recorded as preserved at %r, "
                    "which does not resolve in the emitted document. The record "
                    "and the artifact disagree, and the artifact is the one the "
                    "reader gets -- so nothing is emitted."
                    % (signal["json_path"], signal["key"], entry["now_at"]))
        if value != signal["value"] or type(value) is not type(signal["value"]):
            return ("SIGNAL ALTERED: %s (%r) reads %r in the document as read "
                    "and %r at %r in the emitted one. A changed signal is worse "
                    "than a missing one -- so nothing is emitted."
                    % (signal["json_path"], signal["key"], signal["value"],
                       value, entry["now_at"]))
    return None


# The three documents that are 99.57% of the cost. Each entry is
# (document key, script, argv builder). The argv builder takes the resolved
# savegame dir, config path and farm id, so no path is assembled twice.
SESSION_START_READERS = (
    ("read_state",
     "read_state.py",
     lambda sg, cfg, farm_id: ["--config", cfg]),
    ("farm_snapshot",
     "farm_snapshot.py",
     lambda sg, cfg, farm_id: [sg, "--farm-id", str(farm_id)]),
    ("read_game_log",
     "read_game_log.py",
     lambda sg, cfg, farm_id: [sg]),
)

# ⛔ WHAT THIS SUBCOMMAND DOES NOT RUN, AND WHY IT IS NAMED RATHER THAN OMITTED.
# The step's other three documents cost 993 tokens between them -- 0.43% -- so
# there is nothing to win by folding them in, and two of them WRITE
# (sanctum_maintain.py migrate --apply; check_fleet_alerts.py, which updates
# sanctum/fleet-alert-state.json). Pulling a write into a read-and-summarise
# entry point would change its blast radius for no measurable saving. A reader
# who is not told this would reasonably assume one call now covers the step.
SESSION_START_NOT_RUN = (
    {"script": "check_sanctum_freshness.py",
     "why": "it GATES the briefing -- a stale creed must stop the session before "
            "anything is read, which is a decision, not a document to shrink"},
    {"script": "sanctum_maintain.py migrate --apply",
     "why": "it WRITES (migrates the sanctum and backs it up first); a "
            "read-and-summarise entry point must not carry a write"},
    {"script": "check_fleet_alerts.py",
     "why": "it WRITES sanctum/fleet-alert-state.json and pushes in-game cards -- "
            "so it is NOT run here. Run it yourself, separately: it is ON unless "
            "config.json has fleet_alerts_enabled set to false"},
)

# ⭐ AFTER-SAVE: THE SAME RENDERER, ONE DOCUMENT. workflow-briefing.md's "EVENT
# savegame" bullet re-reads read_state.py after every save the watcher absorbs --
# 95,356 tokens on a real save, paid again per save, so it is the largest
# RECURRING cost left. It re-read that one document and no other, and that is
# exactly what this renders: nothing the reader got is dropped, and nothing is
# added. The reader is selected BY KEY from the tuple above, never re-declared,
# so the argv cannot drift between the two subcommands.
#
# ⚠ WHY NOT A DELTA. Measured on the owner's live delta log: 12 of the 13
# records that moved anything after the first moved 6 of the 7 cached domains
# (source files are rewritten on every save whether or not a figure changed),
# so a changed-domains-only view would drop almost nothing. A value-level diff
# is a different product -- it stops re-reading figures -- and is not built.
AFTER_SAVE_READERS = tuple(
    r for r in SESSION_START_READERS if r[0] == "read_state")

AFTER_SAVE_NOT_RUN = (
    {"script": "check_fleet_alerts.py",
     "why": "it WRITES sanctum/fleet-alert-state.json and pushes in-game cards; "
            "workflow-briefing.md runs it next -- run it yourself after every "
            "save, unless config.json has fleet_alerts_enabled set to false"},
    {"script": "farm_snapshot.py",
     "why": "the after-save re-read never ran it -- the live position (cash, "
            "loan, land, fleet, field_state, decisions_needed) is still the one "
            "session start read, so a field it names ready to harvest may "
            "already be cut"},
    {"script": "read_game_log.py",
     "why": "the after-save re-read never ran it"},
)

# subcommand -> (the readers it renders, what it does not run, its coverage note)
RENDERERS = {
    "session-start": (
        SESSION_START_READERS, SESSION_START_NOT_RUN,
        "This document summarises the three session-start reads "
        "that are 99.6% of the step's token cost. It says "
        "NOTHING about the three listed above, which the step "
        "still runs separately. That is an elision, not "
        "completeness."),
    "after-save": (
        AFTER_SAVE_READERS, AFTER_SAVE_NOT_RUN,
        "This document re-reads read_state.py only -- the verified cache view "
        "after a save the watcher absorbed. It says NOTHING about the scripts "
        "listed above. That is an elision, not completeness."),
}


def _read_one_document(scripts_dir, doc_key, script, argv):
    """Run one reader and return (parsed, pointer_command, run) or an error dict.

    ⚠ NEVER THE EXIT CODE. read_state.py exits 1 to REFUSE, with a diagnosis and
    a remedy the caller is meant to read; farm_snapshot.py and read_game_log.py
    report failure in-band with an `error` key. The fleet is not internally
    consistent about exit status -- that is the documented reason s2's rule ①
    forbids trusting it -- so what is parsed here is the STDOUT DOCUMENT, and the
    exit code travels beside it as data rather than as a verdict.
    """
    cmd = [sys.executable, os.path.join(scripts_dir, script)] + list(argv)
    run = subprocess.run(cmd, capture_output=True, text=True)
    # ⚠ SHELL-QUOTED, AND THIS IS NOT PEDANTRY. The pointer IS the promise --
    # "nothing was cut, here is where to read the rest" -- and every real path
    # on this machine looks like `/mnt/c/Users/<user>/Documents/My Games/...`. An
    # unquoted pointer reads as a runnable command, splits at the first space,
    # and sends the reader to a file that does not exist. A pointer that cannot
    # be run is a truncation with a footnote.
    pointer = "python3 %s %s" % (
        shlex.quote(os.path.join(scripts_dir, script)),
        " ".join(shlex.quote(str(a)) for a in argv))
    try:
        parsed = json.loads(run.stdout)
    except json.JSONDecodeError:
        return None, pointer, run, (
            "UNREADABLE DOCUMENT: %s produced output that is not JSON, so this "
            "run cannot say what it holds. An unparseable document is a failure "
            "to report, never an empty one to summarise." % script)
    if not isinstance(parsed, dict) or not parsed:
        return None, pointer, run, (
            "EMPTY DOCUMENT: %s produced %r. That is not a farm with nothing in "
            "it -- it is a read that produced nothing, and the two must never "
            "render the same (the absence rule: an absent value must never be read as data)." % (script, parsed))
    return parsed, pointer, run, None


def _count_envelopes(node):
    """Elision envelopes already present in a document AS READ -- written by the
    reader's own renderer before this transform saw it. Their elided members
    are not in the document, so the conservation gate cannot see into them."""
    if isinstance(node, dict):
        own = 1 if node.get("_elided") is True else 0
        return own + sum(_count_envelopes(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_envelopes(v) for v in node)
    return 0


def run_session_start(scripts_dir, savegame_dir, config_path, farm_id,
                      subcommand="session-start"):
    """Build a render-only document -- `session-start` or `after-save`, whose
    reader sets are in RENDERERS. Returns (document, error).

    NOTHING IS EMITTED WHEN AN ERROR IS RETURNED -- the same contract as
    aggregate_render.render, and for the same reason: a partially-summarised view
    printed alongside a complaint is a view somebody will read.
    """
    documents = {}
    degraded = []
    signals_preserved = 0
    signals_hoisted = 0
    envelopes_upstream = 0
    readers, not_run, coverage_note = RENDERERS[subcommand]

    for doc_key, script, build_argv in readers:
        argv = build_argv(savegame_dir, config_path, farm_id)
        parsed, pointer, run, err = _read_one_document(
            scripts_dir, doc_key, script, argv)
        if err:
            return None, err

        transformed, preserved = summarise_deep(parsed, pointer)
        gate = conserve_signals(parsed, transformed, preserved)
        if gate:
            return None, gate

        upstream_here = _count_envelopes(parsed)
        envelopes_upstream += upstream_here
        hoisted_here = sum(1 for p in preserved if ".elided_signals." in p["now_at"])
        signals_preserved += len(preserved)
        signals_hoisted += hoisted_here

        # ⛔ CARRIED IN-BAND, NEVER SWALLOWED. A refusal (read_state.py's STALE,
        # CACHE ABSENT, CACHE FARM MISMATCH) and an in-band `error` (no log.txt)
        # are different things with different remedies, and BOTH must reach the
        # reader in the words their own author chose.
        entry = {
            "script": script,
            "read_the_full_document_with": pointer,
            "exit_code": run.returncode,
            "document": transformed,
            "signals_preserved": len(preserved),
            "signals_hoisted_out_of_elided_members": hoisted_here,
            "envelopes_elided_upstream": upstream_here,
        }
        if "error" in parsed:
            entry["carries_error"] = True
            degraded.append({"document": doc_key, "error": parsed["error"]})
        documents[doc_key] = entry

    if not documents:
        return None, ("NO DOCUMENTS: the %s reader set is empty, so this run "
                      "would report success over nothing." % subcommand)

    result = {
        "tool": TOOL,
        "subcommand": subcommand,
        "documents": documents,
        "documents_degraded": degraded,
        # The rule, stated with its source, so a reader can check that this
        # applied the published one rather than a similar number of its own.
        "pointer_rule": {
            "max_inline_items": aggregate_render.MAX_INLINE_ITEMS,
            "defined_in": "aggregate_render.MAX_INLINE_ITEMS",
            "behaviour": "pointer, never truncation -- a list longer than the "
                         "limit is replaced by an envelope carrying its true "
                         "item_count, the first %d items, and read_the_rest_at. "
                         "Nothing is cut silently, and read_the_rest_at is "
                         "ALWAYS a command. On an envelope this run made it is "
                         "`<command> :: <JSON path segments>`: run the command, "
                         "then walk the segments. On one read_state.py's own "
                         "renderer made it is a `read_state.py --list "
                         "DOMAIN.SECTION.KEY` command: run it exactly as "
                         "printed and its `items` is the whole list (F10)."
                         % aggregate_render.MAX_INLINE_ITEMS,
            "applied": "recursively, to every list at every depth in every "
                       "document below",
        },
        "signal_preservation": {
            "signal_keys": list(SIGNAL_KEYS),
            "signals_preserved": signals_preserved,
            "signals_hoisted_out_of_elided_members": signals_hoisted,
            "guarantee": "every signal key present in each document as read was "
                         "re-resolved in this document, by value and type, "
                         "before a single line was emitted. A signal that could "
                         "not be re-found is a structured error and NO document.",
            # ⛔ DEC-181 CALL a. The guarantee is literally true and read wider
            # than it is, so its limit travels WITH it, counted.
            "envelopes_elided_upstream": envelopes_upstream,
            "limit": "the guarantee covers each document AS READ. %d list(s) "
                     "in it had already been summarised by the reader's own "
                     "renderer (aggregate_render) before this run saw them: a "
                     "signal in members %d+ of those lists is not in the "
                     "document as read, so it cannot be re-found here and is "
                     "NOT covered. Those envelopes carry no elided_signals; "
                     "their read_the_rest_at is a read_state.py --list "
                     "command that prints the whole list." % (envelopes_upstream,
                                   aggregate_render.MAX_INLINE_ITEMS + 1),
        },
        # ⭐ The step is not finished by this call, and says so itself.
        "this_call_does_not_replace": list(not_run),
        "coverage_note": coverage_note,
    }
    if subcommand == "session-start":
        # ⛔ F11(2) / BUG-036: for a farm onboarded before O3 asked about
        # merges, the marker never clears and the FIELDS tab is never
        # published. Surfaced here -- a script check, not a turn -- so S2
        # asks the question instead of skipping it again.
        marker = os.path.join(os.path.dirname(os.path.abspath(config_path)),
                              "state", "field-dossiers",
                              read_field_merges.UNASSESSED_MARKER)
        result["field_merge_assessment"] = {
            "pending": os.path.exists(marker),
            "marker": marker,
            "why": "while pending, the FIELDS tab is refused and never published "
                   "(guard E1). Ask the player O3's merged-fields question and "
                   "record the answer with record_field_merges.py.",
        }
    # ⛔ F7. A refusal from the cache gate is carried inside the document -- and
    # ALSO at the top, so "read the `error` key" finds it in the same place as
    # every refusal of this tool's own. One place to look, not two.
    gate = documents.get("read_state") or {}
    if gate.get("carries_error"):
        result["error"] = gate["document"]["error"]
        result["error_source"] = "documents.read_state.document.error"
    return result, None


# --- Item 13: is anything actually stale? ------------------------------------
def assess_domains(domains_dir, targets):
    """Per-domain freshness, via the engine that already exists.

    ⭐ NOT REBUILT. cache_provenance.verify_source_set(..., mode=FAST) is git's
    own racy-git shape: compare mtime_ns + size, escalate to the content hash on
    any mismatch. Its invariant -- a false CURRENT is possible, a false STALE is
    not -- is what makes the cheap path safe, and re-deriving it here would have
    been a second implementation to keep in step for no gain.

    Returns (needs_refresh: list, detail: dict). A domain with no cache file, an
    unreadable one, or an envelope that carries no verifiable source set NEEDS
    REFRESH -- absence is never "nothing to do".
    """
    needs, detail = [], {}
    for domain in targets:
        path = os.path.join(domains_dir, domain + ".json")
        if not os.path.isfile(path):
            needs.append(domain)
            detail[domain] = {"verdict": provenance.STALE,
                              "reason": "no cached generation exists yet"}
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            needs.append(domain)
            detail[domain] = {"verdict": provenance.STALE,
                              "reason": "cached generation unreadable: %s" % exc}
            continue
        sources, recorded, err = provenance.extract_source_set(
            record.get("envelope"))
        if err:
            needs.append(domain)
            detail[domain] = {"verdict": provenance.STALE,
                              "reason": "cached envelope cannot be verified: %s" % err}
            continue
        verdict, reason, info = provenance.verify_source_set(
            sources, recorded, mode=provenance.FAST)
        detail[domain] = {"verdict": verdict, "reason": reason,
                          "freshness_check": info.get("freshness_check")}
        if verdict != provenance.CURRENT:
            needs.append(domain)
    return needs, detail


def _newest_mtime_ns(paths):
    newest = None
    for path in paths:
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def main(argv):
    if not argv or argv[0] in ("--help", "-h", "help"):
        print(help_text())
        return EXIT_OK

    sub = argv[0]
    if sub not in SUBCOMMANDS:
        _fail("unknown subcommand %r -- expected one of: %s. Run --help for the "
              "inventory." % (sub, ", ".join(SUBCOMMANDS)))

    rest = list(argv[1:])
    config_path, only = None, []
    quiet = provenance.SETTLE_QUIET_SECONDS
    while rest:
        arg = rest.pop(0)
        if arg == "--config":
            if not rest:
                _fail("--config given with no path")
            config_path = rest.pop(0)
        elif arg == "--set":
            if not rest:
                _fail("--set given with no domain")
            only.append(rest.pop(0))
        elif arg == "--quiet-seconds":
            if not rest:
                _fail("--quiet-seconds given with no value")
            try:
                quiet = float(rest.pop(0))
            except ValueError:
                _fail("--quiet-seconds requires a number")
            if quiet <= 0:
                _fail("--quiet-seconds must be positive: a zero or negative "
                      "quiet window disables the settle check silently, which "
                      "is the defect it exists to prevent")
        else:
            _fail("unexpected argument %r" % arg)

    if not config_path:
        _fail("usage: refresh_state.py %s --config <sanctum>/config.json "
              "[--set DOMAIN ...]" % sub)

    config, err = layout.load_config(config_path)
    if err:
        _fail(err)

    savegame_dir = ((config.get("paths") or {}).get("savegame_dir")
                    or config.get("savegame_path"))
    if not savegame_dir or "{{" in str(savegame_dir):
        _fail("SAVEGAME DIR NOT SET: neither paths.savegame_dir nor "
              "savegame_path in %s names a real folder (got %r)"
              % (config_path, savegame_dir))
    if not os.path.isdir(savegame_dir):
        _fail("SAVEGAME DIR NOT READABLE: %r is not a directory. Nothing was "
              "read and nothing was published." % savegame_dir)

    # ⭐ session-start AND after-save BRANCH HERE, deliberately BEFORE the settle check, the
    # freshness assessment and every publish. It refreshes nothing and writes
    # nothing: it renders documents the fleet already produces. Putting it after
    # the settle check would make a read-only renderer exit 3 while the game is
    # saving -- a briefing blocked by a gate that protects writers.
    if sub in RENDERERS:
        if only:
            _fail("--set is not accepted by %s: it renders every document it "
                  "reads, and a partial render would be a view missing a "
                  "document nobody asked it to drop." % sub)
        farm_id, farm_id_err = layout.resolve_farm_id(config)
        if farm_id_err:
            # F8: the note names the reader THIS subcommand actually runs.
            _fail(farm_id_err, note=(
                "farm_snapshot.py cannot be run without a resolved farm id, "
                "and a substituted default produces a confident, complete "
                "snapshot of the WRONG farm." if sub == "session-start" else
                "read_state.py resolves the farm id from this same config and "
                "refuses without one: the cache is checked against the farm it "
                "was generated for, and a substituted default would check it "
                "against the WRONG farm."))
        document, err = run_session_start(
            os.path.dirname(os.path.abspath(__file__)),
            savegame_dir, os.path.abspath(config_path), farm_id, sub)
        if err:
            _fail(err)
        print(json.dumps(document, indent=2))
        # ⛔ THE EXIT CODE FOLLOWS THE GATE, NOT THE RENDERER. read_state.py is
        # the cache gate: when it refuses, the step must STOP, so this run is a
        # failure even though the rendering succeeded. The other two readers'
        # in-band errors are degradations carried in `documents_degraded` --
        # "no log found" is "nothing to read", never "nothing went wrong", and
        # it must not abort a briefing.
        if document["documents"]["read_state"].get("carries_error"):
            return EXIT_ERROR
        return EXIT_OK

    # An empty or unknown target set is RED, never a green run over nothing.
    unknown = [d for d in only if d not in ENVELOPE_DOMAINS]
    if unknown:
        _fail("UNKNOWN SOURCE SET(S): %s. This generator covers: %s"
              % (", ".join(unknown), ", ".join(ENVELOPE_DOMAINS)))
    targets = [d for d in ENVELOPE_DOMAINS if not only or d in only]
    if not targets:
        _fail("NO SOURCE SETS TO REFRESH: the target set is empty, so this run "
              "would report success over nothing.")

    try:
        save_files = provenance.savegame_files(savegame_dir)
    except OSError as exc:
        _fail("SAVEGAME DIR NOT LISTABLE: %s (%s). An unreadable save is a "
              "failure to report, never an empty file list to proceed on."
              % (savegame_dir, exc.strerror or exc))
    if not save_files:
        _fail("SAVEGAME DIR IS EMPTY: %r holds no files. That is not a farm "
              "with nothing in it -- it is a save that could not be read."
              % savegame_dir)

    newest_ns = _newest_mtime_ns(save_files)
    savegame_key = os.path.basename(os.path.normpath(savegame_dir))
    marker_path = os.path.join(
        os.path.dirname(os.path.normpath(savegame_dir)),
        "modSettings", MOD_NAME, savegame_key, SAVE_MARKER_NAME)
    marker_audit = audit_save_marker(marker_path, newest_ns)

    cache_root = layout.resolve_cache_root(config_path, config)
    paths = layout.cache_paths(cache_root)
    status_path = os.path.join(cache_root, STATUS_FILE)

    # The published promise, re-asserted on every path that can write. This
    # manager writes nothing into the savegame folder -- not once, not ever.
    escapes = layout.paths_escape_savegame(
        dict(paths, refresh_status=status_path), savegame_dir)
    if escapes:
        _fail("REFUSING TO WRITE INSIDE THE SAVEGAME FOLDER. The published "
              "promise is that this manager writes nothing there.",
              offending_paths=escapes)

    needs, freshness = assess_domains(paths["domains"], targets)

    # ⭐ THE NO-OP. `auto` fires on a hook or a timer, so the common case must
    # cost nothing and CHANGE nothing: no write, no rotation, no new stamp. A
    # run that rewrote an identical artifact would churn the mtime the next
    # freshness check reads, and make "when did this last really change?"
    # unanswerable.
    if sub == "auto" and not needs:
        print(json.dumps({
            "tool": TOOL,
            "subcommand": sub,
            "result": "unchanged",
            "note": "every targeted source set still matches what it was "
                    "generated from. Nothing was read and nothing was written.",
            "source_sets_checked": targets,
            "freshness": freshness,
            "save_marker_audit": marker_audit,
        }, indent=2))
        return EXIT_OK

    # ⛔ THE SETTLE CHECK (item 13a). Everything above only READ metadata. This
    # is the last gate before the parsers open the save, and it is the one that
    # neither mtime nor the content hash can stand in for.
    settle_verdict, settle = provenance.settle_scan(save_files, quiet_seconds=quiet)
    if settle_verdict != provenance.SETTLED:
        print(json.dumps({
            "tool": TOOL,
            "subcommand": sub,
            "result": "still_saving",
            "note": "the save is still being written, so nothing was read. This "
                    "is not a failure -- call again after the quiet window. "
                    "Reading now would publish a mixture of two moments that "
                    "no downstream check could detect.",
            "settle": settle,
            "save_marker_audit": marker_audit,
        }, indent=2))
        return EXIT_STILL_SAVING

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, os.path.join(scripts_dir, "generate_state.py"),
           "--config", config_path]
    for domain in (only or []):
        cmd += ["--only", domain]
    run = subprocess.run(cmd, capture_output=True, text=True)
    try:
        generation = json.loads(run.stdout)
    except json.JSONDecodeError:
        _fail("generate_state.py produced output that is not JSON -- the cache "
              "may be untouched, but this run cannot say what happened.",
              exit_code=run.returncode,
              stdout=run.stdout[:2000], stderr=run.stderr[:2000])
    if run.returncode != 0:
        _fail("generate_state.py failed, so nothing was published.",
              exit_code=run.returncode, generation=generation)

    farm_id, farm_id_err = layout.resolve_farm_id(config)
    resolved_farm_id = None if farm_id_err else farm_id
    mods_dir = (config.get("paths") or {}).get("mods_dir")
    publish = publish_farm_tab(
        scripts_dir, savegame_dir, resolved_farm_id, mods_dir, config_path)
    # ⛔ ALL THREE PUBLISHED TABS, NOT ONE. The dossier directory is a sanctum
    # sibling of config.json; the domains directory is the one `paths` already
    # resolved above, so neither is guessed here.
    fields_publish = publish_fields_tab(
        scripts_dir, savegame_dir, resolved_farm_id, mods_dir,
        os.path.join(os.path.dirname(os.path.abspath(config_path)),
                     "state", "field-dossiers"))
    productions_publish = publish_productions_tab(
        scripts_dir, savegame_dir, resolved_farm_id, paths["domains"], mods_dir)
    problems = tab_publish_problems((("FARM", publish), ("FIELDS", fields_publish),
                                     ("PRODUCTIONS", productions_publish)))

    # Item 14: the artifact describes itself. `inputs` and `input_digest` are
    # the save's own files and a set hash over them, so a reader can re-derive
    # whether this is still true without believing anything it says.
    observed = [provenance.file_provenance(p) for p in save_files]
    header = provenance.artifact_header(
        TOOL, sub, [o["path"] for o in observed],
        provenance.source_set_hash(observed))
    status = dict(header)
    status.update({
        "result": "refreshed",
        "trigger": ("manual -- the player asked for the position now"
                    if sub == "now" else
                    "automatic -- a source set moved since the last generation"),
        "source_sets_refreshed": targets,
        "source_sets_that_were_stale": needs,
        "freshness_before": freshness,
        "settle": settle,
        "save_marker_audit": marker_audit,
        "generation": generation,
        "farm_tab_publish": publish,
        "fields_tab_publish": fields_publish,
        "productions_tab_publish": productions_publish,
        "tab_publish_problems": problems,
    })
    ok, write_err = layout.atomic_write_json(status_path, status)
    if not ok:
        _fail(write_err, note="the cache was regenerated; this status artifact "
                              "was not, so a reader would have no as-of line.")

    print(json.dumps({
        "tool": TOOL,
        "subcommand": sub,
        "result": "refreshed",
        "status_artifact": status_path,
        "source_sets_refreshed": targets,
        "source_sets_that_were_stale": needs,
        "generated_at": header["generated_at"],
        "save_marker_audit": marker_audit,
        # ⛔ Surfaced here, not only in the artifact. A degraded publish that a
        # caller has to go and look for is a degradation nobody renders.
        "farm_tab_publish": publish,
        "fields_tab_publish": fields_publish,
        "productions_tab_publish": productions_publish,
        # ⛔ F11(1): the cache refreshed; these tabs did not. Empty = all three
        # published cleanly.
        "tab_publish_problems": problems,
    }, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
