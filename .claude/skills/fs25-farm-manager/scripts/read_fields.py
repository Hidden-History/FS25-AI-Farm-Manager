"""
Read fields.xml -> per-field crop/growth/ground state, WITH ownership when it
can be resolved.

Usage: python3 read_fields.py <savegame_dir> [--farm-id N]
                             [--owned-fields LIST_OR_PATH] [--mods-dir PATH]
                             [--config PATH] [--no-resolve]
    --farm-id N          Whose fields to mark as owned (default: 1).
    --owned-fields SPEC  Explicit override: a comma-separated list of field ids
                         ("3,7,12"), or a path to a JSON list / {"owned_field_ids":
                         [...]} / plain comma-or-newline text file. HIGHEST
                         precedence -- the player's word beats any derivation.
    --mods-dir PATH      Where the map mod lives, for ownership resolution. If
                         omitted, taken from sanctum/config.json -> paths.mods_dir.
    --config PATH        Where that config.json is. If omitted, this script walks
                         up from its own directory looking for sanctum/config.json
                         (item #12: that walk-up assumes a per-project install and
                         cannot resolve on a personal one -- pass --config there).
    --no-resolve         Skip resolution entirely; every "owned" stays null.

OWNERSHIP: HOW IT IS RESOLVED, AND WHY IT USED TO BE "UNKNOWABLE"
    fields.xml entries carry NO farmId:
        <field id="1" plannedFruit="FALLOW" fruitType="SUNFLOWER" .../>
    Ownership lives one level up on farmland.xml's <farmland id="N" farmId="1"/>,
    and field ids and farmland ids are DIFFERENT id spaces (122 fields vs 149
    farmlands here). The field<->farmland relationship is SPATIAL -- it lives in
    the map's infoLayer_farmlands.grle raster, not in any XML.

    This script long reported `owned: null` for every field and called the mapping
    underivable (F-004). That was true of the XML and false of the save as a whole:
    read_farmland_areas.py now decodes the GRLE raster and resolves it, validated
    against ground truth the decode cannot fake -- its parcel-id set must equal
    farmland.xml's, its total area must equal the map's declared size, and its
    computed land cost must match farms.xml's own <fieldPurchase> to the cent.

    So this script COMPOSES that resolver (it does not reimplement it -- see
    SKILL.md). Precedence, strongest evidence first:
        1. --owned-fields          the player told us. Beats everything.
        2. read_farmland_areas.py  derived + gate-checked. ~0.6s.
        3. null                    honest unknown. NEVER a guess.

    STILL DO NOT assume field id N == farmland id N. That identity holds 122/122
    on Montana 4X and is an empirical finding for THAT MAP, not an FS25 law. It is
    read_farmland_areas.py's job to establish it per-map; if resolution fails, this
    script falls back to null and says so. A wrong ownership claim would tell the
    player they own fields they don't -- exactly the class of silent, plausible
    error this project exists to prevent.

Output contract:
    - "owned" is true/false only when resolved or overridden; otherwise null.
      Never guessed from id, position, or any heuristic.
    - "ownership" reports how it was resolved (source, derivable_from_xml,
      gates), so a caller can always tell knowledge from assumption.
    - Never returns [] when fields.xml is readable; a read failure is {"error"}.
    - calibration_needed means "could not confidently parse fields.xml", never
      "ownership is unknown" -- unknown ownership is an honest state, not a
      calibration failure.
"""
import hashlib
import json
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

SCHEMA_VERSION = 1
DOMAIN = "fields"
SET = "fields"
# a6 field state - a7 soil/treatment state - a9 growth states - a10 crop readiness
CAPABILITY_IDS = ["a6", "a7", "a9", "a10"]


def file_provenance(path):
    """sec. 2.1 source record. Hashes only the files this domain actually reads."""
    stat = os.stat(path)
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return {"path": path, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size,
            "sha256": digest}


def source_set_hash(sources):
    """sec. 2.1: sha256 over the sorted `path\0sha256` lines -- one comparable
    scalar per domain, and the thing that decides currency."""
    lines = sorted("%s\0%s" % (x["path"], x["sha256"]) for x in sources)
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def fail(message, **extra):
    """⛔ A STATED FAILURE EXITS NON-ZERO. This parser used to `emit(); return`
    on every error path, which prints a correct {"error": ...} payload and then
    exits 0 -- a correct artifact with a lying exit code (TECH-DEBT-023).
    generate_state.py defends against exactly that on the consumer side, and
    that defence is right, but a producer must not need defending against:
    "check the artifact, not the exit code" binds a READER, and is not a licence
    for our own scripts to emit a signal that lies."""
    payload = {"error": message, "calibration_needed": False}
    payload.update(extra)
    emit(payload)
    sys.exit(1)


def parse_args(argv):
    """Returns (opts_dict, error_or_None)."""
    o = {"farm_id": 1, "owned_fields_spec": None, "mods_dir": None,
         "config": None, "resolve": True}
    args = argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--farm-id":
            if i + 1 >= len(args):
                return None, "usage: --farm-id given with no value"
            try:
                o["farm_id"] = int(args[i + 1])
            except ValueError:
                return None, f"--farm-id must be an integer, got {args[i + 1]!r}"
            i += 2
        elif args[i] == "--owned-fields":
            if i + 1 >= len(args):
                return None, "usage: --owned-fields given with no value"
            o["owned_fields_spec"] = args[i + 1]
            i += 2
        elif args[i] == "--mods-dir":
            if i + 1 >= len(args):
                return None, "usage: --mods-dir given with no value"
            o["mods_dir"] = args[i + 1]
            i += 2
        elif args[i] == "--config":
            if i + 1 >= len(args):
                return None, "usage: --config given with no value"
            o["config"] = args[i + 1]
            i += 2
        elif args[i] == "--no-resolve":
            o["resolve"] = False
            i += 1
        else:
            i += 1
    return o, None


def find_mods_dir(explicit, config_path=None):
    """Locate the mods dir: the flag, else --config's config.json, else a
    walk-up looking for sanctum/config.json -> paths.mods_dir.

    ⚠ THE --config BRANCH'S WORDING MUST MATCH read_farmland_areas.py's COPY
    OF THIS FUNCTION BYTE FOR BYTE (item #12) -- the two scripts must never
    disagree about where mods live. If you change one, change both.

    Returns (path_or_None, how_or_reason)."""
    if explicit:
        if not os.path.isdir(explicit):
            return None, f"--mods-dir {explicit!r} is not a directory"
        return explicit, "--mods-dir flag"
    if config_path:
        if not os.path.isfile(config_path):
            return None, f"--config {config_path!r} does not exist"
        try:
            with open(config_path) as f:
                paths = (json.load(f).get("paths") or {})
            md = paths.get("mods_dir")
        except (OSError, json.JSONDecodeError) as e:
            return None, f"found {config_path} but could not read paths.mods_dir: {e}"
        if not md:
            return None, f"{config_path} has no paths.mods_dir"
        if not os.path.isdir(md):
            return None, f"paths.mods_dir {md!r} from --config {config_path!r} is not a directory"
        return md, f"--config {config_path!r} -> paths.mods_dir"
    # Walk up from this script looking for a project sanctum. The skill may be
    # installed at project or personal level, so don't assume a fixed depth.
    here = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        cfg = os.path.join(here, "sanctum", "config.json")
        if os.path.isfile(cfg):
            try:
                with open(cfg) as f:
                    paths = (json.load(f).get("paths") or {})
                md = paths.get("mods_dir")
            except (OSError, json.JSONDecodeError) as e:
                return None, f"found {cfg} but could not read paths.mods_dir: {e}"
            if not md:
                return None, f"{cfg} has no paths.mods_dir"
            if not os.path.isdir(md):
                return None, f"paths.mods_dir {md!r} from config.json is not a directory"
            return md, f"sanctum/config.json -> paths.mods_dir"
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None, "no sanctum/config.json found above this script, and --mods-dir not given"


def discover_config_path():
    """The same walk-up find_mods_dir does, but returning the CONFIG PATH itself.

    ⚠ WHY THIS EXISTS RATHER THAN A SECOND RETURN VALUE FROM find_mods_dir: that
    function's --config branch is required to match read_farmland_areas.py's copy
    of it BYTE FOR BYTE (item #12), so the two scripts can never disagree about
    where mods live. Changing its signature to carry one more value would break
    that pairing for a reason unrelated to it. A separate six-line walk is the
    cheaper of the two mistakes.

    Returns a path or None. Never raises.
    """
    here = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        candidate = os.path.join(here, "sanctum", "config.json")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def derive_game_defs(savegame_dir, mods_dir, config_path):
    """Compose read_game_defs.py ONCE for everything this parser needs from the
    game's own definition files: per-crop growth states, the weed replacement
    table, and the stone-picking band.

    Returns (payload_or_None, info). None means the definitions could not be
    built. It does NOT mean "nothing is ready" and it does NOT mean "no field
    work" -- every consumer must treat an absent table as UNKNOWN, which is the
    entire lesson of F-001.

    ⛔ THE --config PASS-THROUGH IS THE WHOLE POINT OF THIS FUNCTION'S SIGNATURE,
    AND OMITTING IT WAS A LIVE, SILENT, TOTAL FAILURE. This function used to
    build its command as:

        cmd = [sys.executable, script, savegame_dir]
        if mods_dir: cmd += ["--mods-dir", mods_dir]

    read_game_defs.py needs install_dir AND mods_dir. Given only --mods-dir it
    resolves NEITHER -- it falls through to looking for "sanctum/config.json"
    relative to the CURRENT WORKING DIRECTORY, which is not where any caller runs
    it from -- and returns {"error": "no --install-dir/--mods-dir given ..."}.

    So on the live save the growth table NEVER built. Measured before the fix:
    crop_state was null for all 122 fields and harvest_ready_on_owned_land was
    null, on every run, on every farm. The parser was honest about it -- it said
    "growth-state table unavailable -- readiness UNKNOWN, not false" 122 times,
    which is why nothing ever flagged it -- but the single most decision-relevant
    thing this script exists to say had never once been said.

    ⚠ mods_dir alone is still passed when there is no config, because
    read_game_defs accepts the pair; but the config path is what actually
    resolves both halves and it is now the primary route.
    """
    script = os.path.join(os.path.dirname(__file__), "read_game_defs.py")
    if not os.path.isfile(script):
        return None, {"error": "read_game_defs.py not found next to this script"}
    # ⛔ WITHOUT A CONFIG read_game_defs.py looks for "sanctum/config.json"
    # RELATIVE TO THE CURRENT WORKING DIRECTORY, which is wherever the caller
    # happened to be -- generate_state.py does not pass --config to any parser,
    # so under the orchestrator that lookup misses and the crop table is empty
    # again. Discovering the config the same way this script discovers the mods
    # dir keeps the two halves resolving from ONE place.
    resolved_config = config_path or discover_config_path()
    cmd = [sys.executable, script, savegame_dir]
    if resolved_config:
        cmd += ["--config", resolved_config]
    if mods_dir:
        cmd += ["--mods-dir", mods_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, {"error": f"read_game_defs.py could not be run: {e}"}
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, {"error": "read_game_defs.py produced unparseable output",
                      "stderr": (r.stderr or "")[:400]}
    # ⛔ CHECK THE ARTIFACT, NOT THE EXIT CODE. read_game_defs.py emits its error
    # payload on EXIT 0 (TECH-DEBT-023). Branching on r.returncode here would read
    # a stated failure as data -- which is exactly how the bug above survived.
    if d.get("error"):
        return None, {"error": f"read_game_defs.py: {d['error']}"}
    return d, {"source": d.get("seed_rates_source"), "map_id": d.get("map_id"),
               "config_used": resolved_config}


def growth_table_from(payload):
    """seed_rates -> {FRUITNAME: growth_states dict}, plus per-crop provenance.

    Carries the WHOLE growth_states block, not just the ready list: the weed
    rungs need allows_weeding / allows_hoeing off the same record, and splitting
    them across two structures is how they drift apart.
    """
    table, sources = {}, {}
    for c in payload.get("seed_rates") or []:
        name = (c.get("crop") or "").upper()
        g = c.get("growth_states") or {}
        if not name or not g.get("state_names"):
            continue
        table[name] = g
        sources[name] = c.get("resolved_from")
    if not table:
        return None, {"error": "read_game_defs.py returned no growth states for any crop"}
    return table, {"crops_with_states": len(table), "resolved_from": sources}


def classify_field(fruit_type, growth_state, table):
    """(crop_state, reason). crop_state is one of ready/harvested/dead/growing, or
    None when it genuinely cannot be determined.

    This reads growthState, NOT groundType. groundType is the TERRAIN TEXTURE: it
    still says HARVEST_READY on a field that was cut days ago, because the texture
    is not repainted when the crop comes off. Reading it as readiness told one farm
    to go harvest two fields it had already harvested.
    """
    if table is None:
        return None, "growth-state table unavailable -- readiness UNKNOWN, not false"
    fruit = (fruit_type or "").upper()
    if not fruit or fruit == "UNKNOWN":
        return None, "field declares no fruit type"
    states = table.get(fruit)
    if states is None:
        return None, (f"no growth states known for {fruit} -- neither the map's fruitType "
                      f"list nor data/foliage/ declares it. UNKNOWN, not 'not ready'. "
                      f"⛔ Not defaulting to base-game data for it either: the "
                      f"fruitType id space is OPEN (453 mods are active on this "
                      f"save) and a confident wrong crop is worse than an "
                      f"acknowledged unknown one.")
    try:
        gs = int(growth_state)
    except (TypeError, ValueError):
        return None, f"growthState {growth_state!r} is not a number"

    if gs in states["cut"]:
        return "harvested", f"growthState {gs} is a harvested/cut state for {fruit}"
    if gs in states["dead"]:
        return "dead", f"growthState {gs} is a dead/withered state for {fruit}"
    if gs in states["ready"]:
        return "ready", f"growthState {gs} is a harvest-ready state for {fruit}"
    return "growing", f"growthState {gs} is a growth stage for {fruit}"


# ---------------------------------------------------------------------------
# THE PER-SAVE MISSION GATES
#
# ⛔ ALL FOUR ARE `true` ON THE SAVE THIS WAS BUILT AGAINST, WHICH IS EXACTLY WHY
# READING THEM MATTERS. A build that hardcoded "ploughing is required" would be
# correct here, correct in every test drawn from here, and WRONG on the farm of
# any player who turned it off -- and it would tell them to plough 23 fields that
# the game will never ask them to plough. This is a public farm manager, not one
# person's save.
#
# A gate that cannot be read is null, and a null gate SUPPRESSES nothing and
# ASSERTS nothing -- the operation is reported with `gate_status: unknown` so the
# reader can see the difference between "the game does not want this" and "we
# could not tell".
MISSION_GATES = {
    "plowingRequiredEnabled": "plough",
    "limeRequired": "lime",
    "weedsEnabled": "weeds",
    "stonesEnabled": "stones",
}


def read_mission_gates(savegame_dir):
    """careerSavegame.xml -> {gate_name: True/False/None}, plus a reason per null.

    Returns (gates_dict, info_dict). Never raises, never guesses: an unreadable
    careerSavegame.xml leaves every gate None WITH the reason attached.
    """
    path = os.path.join(savegame_dir, "careerSavegame.xml")
    gates = {name: None for name in MISSION_GATES}
    info = {"file": path, "unreadable": {}, "source": "careerSavegame.xml"}

    root, generic = load_xml(path)
    if root is None:
        reason = generic.get("error", "unknown error reading careerSavegame.xml")
        info["error"] = reason
        for name in gates:
            info["unreadable"][name] = reason
        return gates, info

    for name in gates:
        el = root.find(".//" + name)
        if el is None or not (el.text or "").strip():
            info["unreadable"][name] = (
                f"careerSavegame.xml declares no <{name}> -- this save's setting for "
                f"it is UNKNOWN. The operation it governs is still reported, marked "
                f"gate_status 'unknown', never silently suppressed and never assumed on."
            )
            continue
        raw = el.text.strip().lower()
        if raw in ("true", "false"):
            gates[name] = (raw == "true")
        else:
            info["unreadable"][name] = (
                f"<{name}> is {el.text.strip()!r}, which is neither 'true' nor 'false'."
            )
    return gates, info


# ---------------------------------------------------------------------------
# THE WEED VERDICT -- a FOUR-way key: (tool, fruitType, weedState, growthState)
#
# ⛔ A MEMBERSHIP TEST ON weedState ALONE IS INSUFFICIENT, and that is not a
# refinement -- it is the difference between an operation the game permits and
# one it does not. Two independent gates must BOTH pass:
#
#   1. THE TOOL GATE, from the game's weed table: does this tool's replacement
#      list send this weedState to 0? Membership, never a threshold (DEC-108) --
#      weederHoe clears {1,2,3,4,6} and the hole at 5 is real.
#   2. THE CROP GATE, from the crop's own foliage definition: does the crop, AT
#      ITS CURRENT GROWTH STATE, permit the operation at all?
#
# ⭐ Gate 2 is grounded in the engine's own parser. FruitTypeDesc (LUADOC
# corpus @ 86f08357, docs/script/Fruits/FruitTypeDesc.md:649-661) reads
# `allowsWeeding` into minWeederState/maxWeederState and `allowsHoeing` into
# minWeederHoeState/maxWeederHoeState -- the flags are named for the tools they
# gate. Weeder.md:434,780 confirms one vehicle spec selects between the two
# replacement tables via `vehicle.weeder#isHoe`. ⚠ The ENFORCEMENT site is not in
# the corpus, so this is grounded in how the engine PARSES the flags, which is
# strong, and not in a line that refuses the operation, which would be stronger.
# Stated at that strength deliberately.
#
# ⭐ Consequence, and it is the finding: a wheat field at weedState 4 carrying a
# crop at greenBig CANNOT BE HOED, even though weederHoe clears state 4. The
# table says the tool works; the crop says the tool is not allowed. Carrot,
# onion, pea, potato and spinach can NEVER be weeded, only hoed. Grape, olive,
# grass and rice permit NEITHER, ever.
#
# ⚠ "NO PERMITTED TOOL" IS A LEGITIMATE, REPORTABLE ANSWER -- the field waits, or
# is mulched at the cost of the crop. It is not an empty result to be hidden.
CROP_GATED_TOOLS = {
    "weeder": "allows_weeding",
    "weederHoe": "allows_hoeing",
}

# herbicide and mulcher carry no per-state crop flag in the foliage definitions.
# They are NOT crop-gated here, and saying so is a claim about what was looked
# for and not found -- not an assertion that the game permits them everywhere.
UNGATED_TOOLS_NOTE = (
    "herbicide and mulcher carry no allowsWeeding/allowsHoeing-style flag in any "
    "resolved crop definition, so no crop gate is applied to them. That is the "
    "absence of a flag, not evidence the game permits them at every growth state."
)


def weed_verdict(fruit_type, weed_state, growth_state, crop_states, weed_model):
    """What can actually be done about this field's weeds, right now.

    Returns a dict, always. Never None-as-data.
    """
    out = {
        "weed_state": weed_state,
        "clearing_tools": [],
        "tools_that_change_without_clearing": [],
        "blocked_by_crop": [],
        "status": "ok",
        "reason": None,
    }
    if weed_model is None:
        out["status"] = "unknown_source"
        out["reason"] = ("the game's weed replacement table could not be resolved, so "
                         "what would clear this field is UNKNOWN -- not 'nothing'.")
        return out
    try:
        state = int(weed_state)
    except (TypeError, ValueError):
        out["status"] = "unreadable_source"
        out["reason"] = f"weedState {weed_state!r} is not a number"
        return out
    if state == 0:
        out["reason"] = "weedState 0 -- this field carries no weeds."
        return out

    fruit = (fruit_type or "").upper()
    try:
        gs = int(growth_state)
    except (TypeError, ValueError):
        gs = None

    # A field with no crop cannot be crop-gated: there is nothing growing for the
    # foliage flags to protect. Bare ground is freely workable.
    has_crop = bool(fruit) and fruit != "UNKNOWN" and gs not in (None, 0)
    states = crop_states.get(fruit) if crop_states else None
    if has_crop and states is None:
        out["status"] = "partial"
        out["reason"] = (
            f"{fruit} has no resolved crop definition, so whether it permits weeding or "
            f"hoeing at growthState {growth_state} is UNKNOWN. Tools are listed by the "
            f"weed table alone and MUST NOT be read as permitted."
        )

    for tool, entry in sorted(weed_model.items()):
        rules = entry.get("by_fruit_type", {}).get(fruit) or entry.get("default") or {}
        clears = rules.get("clears") or []
        changes = rules.get("changes_without_clearing") or {}

        if state in clears:
            gate_attr = CROP_GATED_TOOLS.get(tool)
            if gate_attr and has_crop and states is not None:
                permitted = states.get(gate_attr) or []
                if gs not in permitted:
                    out["blocked_by_crop"].append({
                        "tool": tool,
                        "why": (
                            f"{tool} clears weedState {state}, but {fruit} does not permit "
                            f"it at growthState {gs}: the crop declares {gate_attr} on "
                            f"states {permitted or 'NONE, at any growth state'}."
                        ),
                    })
                    continue
            out["clearing_tools"].append(tool)
        elif str(state) in changes:
            out["tools_that_change_without_clearing"].append({
                "tool": tool,
                "moves_state_to": changes[str(state)],
                "why": (
                    f"{tool} changes weedState {state} to {changes[str(state)]} WITHOUT "
                    f"clearing it. Sending it does not remove the weed."
                ),
            })

    if not out["clearing_tools"] and out["status"] == "ok":
        out["reason"] = (
            f"No tool the game declares can clear weedState {state} on this field"
            + (f" while {fruit} is at growthState {gs}" if has_crop else "")
            + ". That is a real answer: the field waits, or the crop is sacrificed to a "
              "mulcher. It is not an empty result."
        )
    return out


# ---------------------------------------------------------------------------
# THE WORK LIST
#
# ⛔ THIS IS NOT A LADDER, AND CALLING IT ONE WOULD MISDESCRIBE THE GAME. The
# field model has TWO axes:
#
#   Axis 1 -- the crop cycle: tillage -> sowing -> {rolling, harvest} -> tillage.
#             A partial order with ALTERNATIVES inside each lane (CULTIVATED and
#             PLOWED are alternatives, not successive rungs), and GRASS runs a
#             separate perennial cycle that never enters it at all.
#   Axis 2 -- treatments: weeds, lime, stones. These change at ANY cycle position
#             and impose no ordering on it.
#
# ⭐ The axes are ORTHOGONAL IN ORDERING but COUPLED IN FEASIBILITY: axis 2's weed
# operation is gated by axis 1's position (see weed_verdict). A model that treats
# treatments as freely schedulable emits operations the game will not permit.
#
# ⛔ SO A SINGLE RANKED LIST MUST SERIALISE AN ORTHOGONAL AXIS AGAINST A
# SEQUENTIAL ONE, AND ANY ORDER IT PICKS IS ARBITRARY. `rank` below is a
# PRESENTATION ORDER, declared as such in the output, and it is NOT a claim that
# the game requires this sequence. Every applicable operation is emitted; the
# rank only decides which one is shown first.
#
# ==> AND THE PHRASING IS LOAD-BEARING. <==
# This reports THE OPERATION THIS STATE CALLS FOR. It does NOT report "the
# operation that will clear this field": one scalar cannot describe a whole
# field. A field is a raster -- these attributes are the field's summary state,
# and a field can carry weeds on part of its area and none on the rest. Saying
# "this will clear the field" promises an outcome the data cannot support.
PRESENTATION_ORDER = ("harvest", "plough", "weeds", "lime", "stones")


def field_operations(field, crop_states, weed_model, stone_rule, gates):
    """Every operation this field's state calls for. Returns a list of dicts.

    ⛔ NO OPERATION IS OMITTED BECAUSE ITS GATE IS OFF. A gated-off operation is
    reported with `applies: false` and the gate that turned it off, because
    "this save does not require ploughing" and "this field does not need
    ploughing" are different sentences and a player deserves to see which one
    they are being told.
    """
    ops = []

    def gate_of(op_name):
        for gate_name, governed in MISSION_GATES.items():
            if governed == op_name:
                return gate_name, gates.get(gate_name)
        return None, None

    def add(op_name, needed, basis, detail=None):
        gate_name, gate_value = gate_of(op_name)
        entry = {
            "operation": op_name,
            "needed_by_field_state": needed,
            "basis": basis,
            "governing_gate": gate_name,
            "gate_status": ("on" if gate_value is True
                            else "off" if gate_value is False else "unknown"),
            # `applies` is the AND of the two, and it is computed rather than
            # asserted so the two halves stay separately visible above.
            "applies": bool(needed) and gate_value is not False,
            "rank": PRESENTATION_ORDER.index(op_name),
        }
        if detail is not None:
            entry["detail"] = detail
        ops.append(entry)

    # ---- harvest: axis 1, and a MEMBERSHIP TEST on the resolved crop ---------
    # ⛔ NOT groundType. groundType ∈ {HARVEST_READY, HARVEST_READY_OTHER} is
    # 122/122 self-consistent on this save and HALF ITS POSITIVES ARE WRONG: it
    # is sticky after harvest (an already-cut field still shows the marker), it
    # never fires at all for 9 crops including POTATO and GRASS, and it fires
    # three states early on sugarbeet. Self-consistency is not correctness.
    # ⛔ NOT a growthState threshold either: the ready index runs 2..14 across
    # this map's crops, so no single N works.
    add("harvest",
        field["crop_state"] == "ready",
        "growthState is in this crop's own isHarvestReady foliage-state set "
        "(read from the resolved crop definition, map-first). Not groundType, "
        "which is a terrain texture and stays HARVEST_READY after a field is cut.",
        {"crop_state": field["crop_state"], "why": field["crop_state_reason"]})

    # ---- plough: axis 1 and axis 2 both -------------------------------------
    # ⛔ 0 MEANS NEEDS PLOUGHING. Confirmed two independent ways: the engine's own
    # MapOverlayGenerator paints the NEEDS_PLOWING colour on plowLevel state 0,
    # and every plowLevel transition in this save's snapshot window is explained
    # by it -- four 1->0 drops all land on a harvest (harvesting CREATES the
    # debt) and the single 0->1 rise carries groundType -> PLOWED in the same
    # record (ploughing CLEARS it). 5 of 5, no residual.
    plow = _as_int(field.get("plow_level"))
    add("plough",
        plow == 0,
        "plowLevel 0 = needs ploughing. Grounded in MapOverlayGenerator, which "
        "colours NEEDS_PLOWING on state 0, and confirmed by 5 of 5 observed "
        "transitions on this save.",
        {"plow_level": field.get("plow_level")})

    # ---- lime: axis 2 -------------------------------------------------------
    # ⛔ SAME POLARITY AS PLOUGH -- 0 is the deficit end -- AND THAT IS NOT AN
    # INFERENCE FROM PLOUGH. It is grounded separately: the overlay colours
    # NEEDS_LIME on limeLevel 0, and of the five upward moves in the snapshot
    # window four carry sprayType NONE->LIME in the same record, i.e. liming
    # raises the value. ⚠ See the roller note below for why generalising a
    # neighbour's polarity is forbidden here.
    lime = _as_int(field.get("lime_level"))
    add("lime",
        lime == 0,
        "limeLevel 0 = needs lime. Overlay colours NEEDS_LIME on state 0, and 4 "
        "of 5 observed upward moves carry sprayType NONE->LIME in the same record.",
        {"lime_level": field.get("lime_level")})

    # ---- stones: axis 2, membership from the game's own <picking> -----------
    stone = _as_int(field.get("stone_level"))
    if stone_rule is None:
        add("stones", False,
            "the game's stone-picking band could not be resolved -- UNKNOWN, not 'no stones'.",
            {"status": "unknown_source", "stone_level": field.get("stone_level")})
    else:
        pickable = stone_rule.get("pickable_states") or []
        add("stones",
            stone in pickable,
            f"stoneLevel is in the pickable set {pickable}, read from maps_stones.xml "
            f"<picking minValue maxValue>. Membership, not a threshold: a >= rule "
            f"misses the low end and wrongly includes {stone_rule.get('picked_state')}, "
            f"which means ALREADY PICKED.",
            {"stone_level": field.get("stone_level"),
             "picked_state": stone_rule.get("picked_state")})

    # ---- weeds: axis 2, gated by axis 1 -------------------------------------
    verdict = weed_verdict(field.get("fruit_type"), field.get("weed_state"),
                           field.get("growth_state"), crop_states, weed_model)
    add("weeds",
        bool(verdict["clearing_tools"]) or bool(verdict["blocked_by_crop"]),
        "the game's own weed replacement table (which tool sends this weedState "
        "to 0) AND the resolved crop's allowsWeeding/allowsHoeing at this "
        "growthState. Both gates, four-way key: (tool, fruitType, weedState, "
        "growthState).",
        verdict)

    ops.sort(key=lambda o: o["rank"])
    return ops


def _as_int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _ownership_source_note(xc):
    """BUG-012 (second instance, found 2026-08-03): this note used to state
    unconditionally that the decode's "land cost matches farms.xml's own
    <fieldPurchase>" -- and it did so INSIDE the clause naming why the decode is
    trusted. That is worse than the farm_snapshot.py instance it was filed for:
    that one asserted a false fact, this one asserted a false JUSTIFICATION FOR
    TRUST, naming three gates when only two are enforced above.

    The enforced gates are gate1 (parcel-id set) and gate2 (declared area) --
    see the check at the top of derive_owned_field_ids(). The land-cost
    comparison is reported, never gated on. Ownership is trusted without it, so
    the note must not claim otherwise."""
    two_gates = ("Derived by decoding the map's infoLayer_farmlands.grle and matching each "
                 "field's world position to a parcel. Trusted because it passes two gates a "
                 "wrong decode cannot fake: its parcel-id set equals farmland.xml's, and its "
                 "total area equals the map's declared size.")
    match = xc.get("match") if isinstance(xc, dict) else None
    if match is True:
        return two_gates + (" A third, non-gating comparison also agrees: its land cost "
                            "against farms.xml's own <fieldPurchase>.")
    if match is False:
        return two_gates + (" A third, non-gating comparison DISAGREES: its land cost against "
                            "farms.xml's own <fieldPurchase> (see field_purchase_cross_check "
                            "for both figures, and BUG-014 for what that disagreement means). "
                            "Ownership does not depend on it -- the two gates above do.")
    return two_gates + (" The third, non-gating land-cost comparison against farms.xml's "
                        "<fieldPurchase> did NOT run -- neither confirmed nor refuted.")


def derive_owned_field_ids(savegame_dir, farm_id, mods_dir):
    """Compose read_farmland_areas.py -- do NOT reimplement the GRLE decode.
    Returns (set_of_ids_or_None, info_dict)."""
    script = os.path.join(os.path.dirname(__file__), "read_farmland_areas.py")
    if not os.path.isfile(script):
        return None, {"error": "read_farmland_areas.py not found next to this script"}
    cmd = [sys.executable, script, savegame_dir, mods_dir, "--farm-id", str(farm_id)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, {"error": f"read_farmland_areas.py could not be run: {e}"}
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, {"error": "read_farmland_areas.py produced unparseable output",
                      "stderr": (r.stderr or "")[:400]}
    if "error" in d:
        return None, {"error": f"read_farmland_areas.py: {d['error']}"}

    gates = d.get("gates_passed") or {}
    # A decode that fails its own gates must NOT be trusted into an ownership
    # claim -- that is the whole reason the gates exist.
    if not all(gates.get(k) for k in ("gate1_id_set_matches_savegame",
                                      "gate2_area_matches_declared_map_size")):
        return None, {"error": "read_farmland_areas.py did not pass its validation gates",
                      "gates_passed": gates}
    ids = ((d.get("owned") or {}).get("field_ids"))
    if ids is None:
        return None, {"error": "read_farmland_areas.py returned no owned.field_ids"}
    xc = d.get("field_purchase_cross_check") or {}
    return set(int(i) for i in ids), {
        "gates_passed": gates,
        "field_purchase_cross_check": xc,
        "owned_area_ha": (d.get("owned") or {}).get("total_area_ha"),
        "note": _ownership_source_note(xc),
    }


def resolve_owned_field_ids(spec):
    """spec is either a comma-separated id list or a path to a file containing
    one. Returns (set_of_ints, error_or_None)."""
    if spec is None:
        return None, None

    if os.path.isfile(spec):
        try:
            with open(spec, "r") as f:
                raw = f.read()
        except OSError as e:
            return None, f"could not read --owned-fields file {spec}: {e}"

        # Try JSON first (list, or {"owned_field_ids": [...]})
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                ids = data
            elif isinstance(data, dict) and "owned_field_ids" in data:
                ids = data["owned_field_ids"]
            else:
                return None, (
                    f"--owned-fields file {spec} is valid JSON but is neither a list "
                    f"nor an object with 'owned_field_ids'."
                )
            try:
                return set(int(x) for x in ids), None
            except (ValueError, TypeError):
                return None, f"--owned-fields file {spec} contains non-integer field ids."
        except json.JSONDecodeError:
            pass

        # Fall back to comma/newline separated plain text.
        parts = [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
        try:
            return set(int(p) for p in parts), None
        except ValueError:
            return None, f"--owned-fields file {spec} could not be parsed as JSON or a comma/newline id list."

    # Not a file -- treat as inline comma-separated list.
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        return None, f"--owned-fields value {spec!r} did not parse to any field ids."
    try:
        return set(int(p) for p in parts), None
    except ValueError:
        return None, f"--owned-fields must be a comma-separated list of integers or a path to a file, got {spec!r}"


def main():
    savegame_dir = arg_or_exit(
        "read_fields.py <savegame_dir> [--farm-id N] [--owned-fields LIST_OR_PATH] "
        "[--mods-dir PATH] [--no-resolve]"
    )
    opts, arg_err = parse_args(sys.argv)
    if arg_err:
        fail(arg_err)
    farm_id = opts["farm_id"]

    # ⛔ A9 -- BOUND HERE, BEFORE ANY BRANCH. mods_dir used to be assigned ONLY
    # inside the final `else:` below and was then read unconditionally further
    # down, so `--owned-fields` or `--no-resolve` crashed with a bare
    # UnboundLocalError traceback and an EMPTY stdout. Reproduced on the live
    # save before this fix. A parser that dies with no JSON at all is the worst
    # possible failure shape for a machine consumer: there is no error payload
    # to read, only an exit code and a traceback on stderr.
    mods_dir, how = None, "not resolved -- ownership resolution did not run"

    # Ownership precedence, strongest evidence first: the player's word, then a
    # gate-checked derivation, then an honest null. Never a guess.
    ownership = {"derivable_from_xml": False}
    owned_field_ids, owned_err = resolve_owned_field_ids(opts["owned_fields_spec"])
    if owned_err:
        fail(owned_err)

    if owned_field_ids is not None:
        ownership.update({
            "resolved": True,
            "source": "player override (--owned-fields)",
            "note": "The player stated these directly. That outranks any derivation.",
        })
    elif not opts["resolve"]:
        ownership.update({
            "resolved": False,
            "source": "--no-resolve",
            "note": "Resolution skipped by request; every field's owned is null.",
        })
    else:
        mods_dir, how = find_mods_dir(opts["mods_dir"], opts["config"])
        if mods_dir is None:
            ownership.update({
                "resolved": False,
                "source": None,
                "why_unresolved": how,
                "note": ("Ownership is NOT in fields.xml (no farmId). It is derivable by "
                         "decoding the map's GRLE raster, but the mods dir could not be "
                         "located. Pass --mods-dir or set paths.mods_dir in "
                         "sanctum/config.json. Every field's owned stays null -- unknown, "
                         "not guessed."),
            })
        else:
            derived, info = derive_owned_field_ids(savegame_dir, farm_id, mods_dir)
            if derived is None:
                ownership.update({
                    "resolved": False,
                    "source": None,
                    "why_unresolved": info.get("error"),
                    "note": ("Derivation was attempted and FAILED. Every field's owned stays "
                             "null. A failed decode must never be rounded up into an "
                             "ownership claim -- that is what the gates are for."),
                })
                ownership.update({k: v for k, v in info.items() if k != "error"})
            else:
                owned_field_ids = derived
                ownership.update({
                    "resolved": True,
                    "source": f"read_farmland_areas.py (mods dir via {how})",
                })
                ownership.update(info)

    path = os.path.join(savegame_dir, "fields.xml")
    root, generic = load_xml(path)

    if root is None:
        fail(generic.get("error", "unknown error reading fields.xml"))

    field_elems = list(root.iter("field"))
    if not field_elems:
        fail("fields.xml parsed but contained no <field> elements -- schema may "
             "have changed. ⛔ An empty field set is reported as an ERROR, never "
             "as a farm with no fields: absence must be impossible to mistake "
             "for data (DEC-001).", calibration_needed=True)

    # ⚠ mods_dir may legitimately be None here (--no-resolve, or a player
    # override). read_game_defs still resolves from --config in that case, so
    # the crop table survives a skipped ownership resolution -- which is the
    # whole point of binding mods_dir above rather than crashing.
    defs_payload, defs_info = derive_game_defs(savegame_dir, mods_dir, opts["config"])
    if defs_payload is None:
        growth_table, growth_info = None, defs_info
        weed_model, stone_rule = None, None
        weed_source = stone_source = {"error": defs_info.get("error")}
    else:
        growth_table, growth_info = growth_table_from(defs_payload)
        if growth_info.get("error"):
            growth_info = dict(growth_info, **{k: v for k, v in defs_info.items() if k != "error"})
        else:
            growth_info.update({k: v for k, v in defs_info.items() if k != "error"})
        weed_model = defs_payload.get("weed_model")
        weed_source = defs_payload.get("weed_model_source")
        stone_rule = defs_payload.get("stone_picking")
        stone_source = defs_payload.get("stone_picking_source")

    gates, gates_info = read_mission_gates(savegame_dir)

    fields = []
    # Rows fields.xml declared that this parser could NOT key. They are counted,
    # never silently dropped: a dropped row makes the field count wrong and
    # nothing says so. This is what calibration_needed is derived from.
    unparsed_rows = []
    unresolved_override_ids = set(owned_field_ids) if owned_field_ids is not None else None

    for field_elem in field_elems:
        a = field_elem.attrib
        fid_raw = a.get("id")
        if fid_raw is None:
            unparsed_rows.append({"attrs": dict(a),
                                  "why": "<field> carries no id attribute"})
            continue
        owned = None
        if owned_field_ids is not None and fid_raw is not None:
            try:
                fid_int = int(fid_raw)
                owned = fid_int in owned_field_ids
                unresolved_override_ids.discard(fid_int)
            except ValueError:
                owned = None

        crop_state, crop_state_reason = classify_field(
            a.get("fruitType"), a.get("growthState"), growth_table)

        fields.append({
            "id": fid_raw,
            "owned": owned,
            "planned_fruit": a.get("plannedFruit"),
            "fruit_type": a.get("fruitType"),
            "growth_state": a.get("growthState"),
            "last_growth_state": a.get("lastGrowthState"),
            "weed_state": a.get("weedState"),
            "stone_level": a.get("stoneLevel"),
            "ground_type": a.get("groundType"),
            "spray_type": a.get("sprayType"),
            "spray_level": a.get("sprayLevel"),
            "lime_level": a.get("limeLevel"),
            "roller_level": a.get("rollerLevel"),
            "plow_level": a.get("plowLevel"),
            "stubble_shred_level": a.get("stubbleShredLevel"),
            "water_level": a.get("waterLevel"),
            # THE field to read. ground_type above is the terrain texture and does
            # not reset when a crop is cut -- see classify_field().
            "crop_state": crop_state,
            "crop_state_reason": crop_state_reason,
        })
        fields[-1]["operations_this_state_calls_for"] = field_operations(
            fields[-1], growth_table or {}, weed_model, stone_rule, gates)

    owned_fields = [f for f in fields if f["owned"] is True]

    # Was: `f["ground_type"].startswith("HARVEST_READY")`. That is the TERRAIN
    # TEXTURE, and it is still HARVEST_READY on a field cut days ago -- it listed
    # two already-harvested fields as ready on this very farm (oat 71 at
    # growthState 7 = cut, canola 114 at 11 = cut). It also could not tell
    # HARVEST_READY from HARVEST_READY_OTHER, which is not a readiness
    # distinction at all: the same canola at the same growthState appears under
    # both. growthState is the fact; groundType is decoration.
    ready_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "ground_type": f["ground_type"],
         "growth_state": f["growth_state"], "weed_state": f["weed_state"]}
        for f in owned_fields if f["crop_state"] == "ready"
    ]
    harvested_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "growth_state": f["growth_state"]}
        for f in owned_fields if f["crop_state"] == "harvested"
    ]
    dead_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "growth_state": f["growth_state"]}
        for f in owned_fields if f["crop_state"] == "dead"
    ]
    unknown_state_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "growth_state": f["growth_state"],
         "why": f["crop_state_reason"]}
        for f in owned_fields if f["crop_state"] is None
    ]

    sources = [file_provenance(path)]
    career = os.path.join(savegame_dir, "careerSavegame.xml")
    if os.path.isfile(career):
        sources.append(file_provenance(career))
    provenance = {
        "generator": "read_fields.py",
        "generator_version": "1.1.0",
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
    }
    provenance["source_set_hash"] = source_set_hash(sources)

    # ------------------------------------------------------------------ the work list
    # ⛔ OWNED LAND ONLY. The mod this ordering was adapted from does the exact
    # opposite -- MissionInfo.lua returns nil when field.farmland.isOwned,
    # because it exists to give a CONTRACTOR work on land the player does NOT
    # own. We want the precise inverse, and taking its scope with its ordering
    # would silently produce a list of other people's fields.
    #
    # ⛔ AND IT ENUMERATES. That mod samples ONE RANDOM FIELD and retries ten
    # times -- fine for "give a worker something to do", useless for "tell me
    # every field that needs attention".
    work_list = []
    for f in owned_fields:
        due = [o for o in f["operations_this_state_calls_for"] if o["applies"]]
        unknown_gate = [o for o in f["operations_this_state_calls_for"]
                        if o["needed_by_field_state"] and o["gate_status"] == "unknown"]
        if not due and not unknown_gate:
            continue
        work_list.append({
            "field_id": f["id"],
            "fruit_type": f["fruit_type"],
            "growth_state": f["growth_state"],
            "operations": due,
            # The FIRST operation in presentation order, named so no reader
            # mistakes a display choice for a game-imposed sequence.
            "first_in_presentation_order": due[0]["operation"] if due else None,
            "operations_with_unknown_gate": [o["operation"] for o in unknown_gate],
        })
    # Fields with more outstanding operations first; ties broken by the numeric
    # field id so the order is stable between runs and diffable.
    work_list.sort(key=lambda w: (-len(w["operations"]), _as_int(w["field_id"]) or 0))

    work_list_available = ownership.get("resolved") is True

    # ------------------------------------------------------------------ sec. 6.2 envelope
    def section(status, reason, shape, typing, identity, empty_means, source_elements,
                data, extra=None):
        block = {
            "status": status,
            "reason": reason,
            "shape": shape,
            "capability_ids": list(CAPABILITY_IDS),
            "typing": dict(typing),
            "typing_guarantee": {},
            "identity_fields": list(identity),
            "empty_means": empty_means,
            "absence_guarantee": None,
            "source_elements": list(source_elements),
            "blocked_by": None,
            "count": len(data),
            "data": data,
        }
        if extra:
            block.update(extra)
        return block

    if not ownership.get("resolved"):
        wl_status, wl_reason = "unavailable", (
            "Ownership could not be resolved, so which fields are THIS FARM'S is "
            "unknown and a work list would be a list of somebody else's fields. "
            "⛔ This is NOT 'no work outstanding'.")
    elif not owned_fields:
        wl_status, wl_reason = "unknown_by_design", (
            "Ownership resolved and this farm owns no fields, so there is no field "
            "work by construction.")
    elif growth_table is None:
        wl_status, wl_reason = "partial", (
            "The crop definitions could not be resolved, so every harvest verdict is "
            "UNKNOWN. The non-crop operations (plough, lime, stones) are still "
            "grounded and are reported; harvest is absent from this list rather than "
            "reported as 'not ready'. Reason: %s" % (defs_info.get("error"),))
    elif not work_list:
        wl_status, wl_reason = "ok", (
            "Every owned field was examined and none has an outstanding operation "
            "under this save's mission gates.")
    else:
        wl_status, wl_reason = "ok", None

    sections = {
        "field_state": section(
            "ok" if fields else "unavailable",
            None if fields else "fields.xml declared no <field> rows",
            "record_list",
            {"id": "raw", "owned": "raw", "fruit_type": "raw", "growth_state": "int",
             "weed_state": "int", "stone_level": "int", "lime_level": "int",
             "plow_level": "int", "spray_level": "int", "crop_state": "raw"},
            ["id"],
            "farm_has_none",
            ["fields.xml:field"],
            fields),
        "field_work": section(
            wl_status, wl_reason, "record_list",
            {"field_id": "raw", "fruit_type": "raw", "growth_state": "int"},
            ["field_id"],
            "no_field_work_outstanding",
            ["fields.xml:field", "careerSavegame.xml:plowingRequiredEnabled",
             "careerSavegame.xml:limeRequired", "careerSavegame.xml:weedsEnabled",
             "careerSavegame.xml:stonesEnabled"],
            work_list if work_list_available else [],
            {"interpretation_guarantee": [{
                "kind": "design_ruling",
                "ruling": "DEC-108",
                "text": (
                    "Weed and stone capability are MEMBERSHIP TESTS against the "
                    "game's own tables, never thresholds. The weed relation is "
                    "non-monotonic and the stone rule is a bounded band with an "
                    "above-band 'already picked' marker, so no >= rule expresses "
                    "either. The weed verdict additionally consults the resolved "
                    "crop's allowsWeeding/allowsHoeing at the field's current "
                    "growthState -- a four-way key."),
            }],
             "ordering_note": (
                 "`rank` and the list order are a PRESENTATION ORDER, not a "
                 "sequence the game requires. The field model is two orthogonal "
                 "axes -- a crop cycle and a set of independent treatments -- so "
                 "any single ranked list serialises one against the other and the "
                 "choice is arbitrary. Every applicable operation is emitted; only "
                 "which is shown first depends on the rank."),
             "scalar_note": (
                 "Each row reports THE OPERATION THIS STATE CALLS FOR. It does not "
                 "report the operation that will clear the field: a field is a "
                 "raster and these attributes are its summary state, so one scalar "
                 "cannot describe the whole field."),
             "cost_note": (
                 "No cost figure is emitted. D-04's `cost` field is governed by the "
                 "four-constants hard stop (DEC-107): time and area are sayable, a "
                 "precise money figure is not."),
             "ungated_tools_note": UNGATED_TOOLS_NOTE}),
        "mission_gates": section(
            "ok" if all(v is not None for v in gates.values()) else "partial",
            None if all(v is not None for v in gates.values())
            else "one or more per-save mission gates could not be read; see data[].reason",
            "record_list",
            {"gate": "raw", "enabled": "raw", "governs": "raw"},
            ["gate"],
            "unknown_by_design",
            ["careerSavegame.xml:" + g for g in sorted(MISSION_GATES)],
            [{"gate": g, "enabled": gates[g], "governs": MISSION_GATES[g],
              "reason": gates_info["unreadable"].get(g)} for g in sorted(MISSION_GATES)]),
    }

    top_status = ("partial" if any(x["status"] in ("unavailable", "partial")
                                   for x in sections.values())
                  else "unknown_by_design" if all(x["status"] == "unknown_by_design"
                                                  for x in sections.values())
                  else "ok")

    result = {
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN,
        "set": SET,
        "capability_ids": list(CAPABILITY_IDS),
        "provenance": provenance,
        "status": top_status,
        "reason": "; ".join(
            "%s (%s): %s" % (n, x["status"], x["reason"])
            for n, x in sorted(sections.items())
            if x["status"] in ("unavailable", "partial") and x["reason"]) or None,
        "sections": sections,
        "file": path,
        "farm_id": farm_id,
        "field_count": len(fields),
        "field_count_note": "Fields on the MAP. See owned_field_count for the farm's own.",
        "owned_field_count": len(owned_fields) if ownership.get("resolved") else None,
        "owned_field_ids": sorted(int(f["id"]) for f in owned_fields) if ownership.get("resolved") else None,
        # The single most decision-relevant thing this parser can say: a ripe crop
        # on ground the player actually owns. Empty list = checked and none ready.
        # null = ownership unresolved, so we genuinely do not know -- do not read
        # an absent list as "nothing to harvest".
        "harvest_ready_on_owned_land": (
            ready_owned if (ownership.get("resolved") and growth_table is not None) else None),
        "harvest_ready_note": (
            "From growthState vs the crop's own foliage states -- NOT groundType, which is "
            "the terrain texture and stays HARVEST_READY after a field is cut. Empty list "
            "means resolved and none are ready. null means ownership or the growth-state "
            "table is unresolved -- unknown, NOT 'nothing to harvest'."
        ),
        "harvested_on_owned_land": (
            harvested_owned if (ownership.get("resolved") and growth_table is not None) else None),
        "harvested_note": (
            "Fields whose crop is CUT. FS25 records no harvest timestamp anywhere, so this "
            "is a state, not an event: to date it, diff against the previous session."
        ),
        "dead_on_owned_land": (
            dead_owned if (ownership.get("resolved") and growth_table is not None) else None),
        "unknown_crop_state_on_owned_land": (
            unknown_state_owned if ownership.get("resolved") else None),
        "unknown_crop_state_note": (
            "Fields whose readiness could NOT be determined, each with a reason. These are "
            "not 'not ready' -- they are unknown, and saying so is the point."
        ),
        "growth_states": growth_info,
        "fields": fields,
        "ownership": ownership,
        # ⛔ A5 -- DERIVED, NOT A LITERAL. This was written as a bare `False`,
        # which is a self-describing quality label pinned to a constant: it
        # claimed "this parser read fields.xml confidently" on every run, and it
        # would have gone on claiming it if the parse had degraded. It means
        # exactly one thing -- "could not confidently parse fields.xml" -- and it
        # is now computed from whether that actually happened. It does NOT mean
        # "ownership is unknown": unknown ownership is an honest state, not a
        # calibration failure, so it is deliberately not part of this expression.
        "calibration_needed": bool(unparsed_rows) or not fields,
        "calibration_reason": (
            "%d of %d <field> rows carry no id attribute, so they cannot be keyed."
            % (len(unparsed_rows), len(fields) + len(unparsed_rows))
        ) if unparsed_rows else None,
    }

    if owned_field_ids is not None:
        result["ownership"]["override_applied"] = True
        result["ownership"]["override_owned_field_ids"] = sorted(owned_field_ids)
        result["ownership"]["override_owned_count"] = len(owned_field_ids)
        if unresolved_override_ids:
            result["ownership"]["override_ids_not_found_in_fields_xml"] = sorted(unresolved_override_ids)
    else:
        result["ownership"]["override_applied"] = False

    emit(result)


if __name__ == "__main__":
    main()
