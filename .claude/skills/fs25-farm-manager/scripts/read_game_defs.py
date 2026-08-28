"""
Resolve the GAME'S OWN definitions: which fillTypes are sellable OUTPUTS vs
buyable INPUTS, and how much seed each crop needs per hectare.

Usage: python3 read_game_defs.py <savegame_dir>
        [--config PATH] [--install-dir DIR] [--mods-dir DIR]

WHY THIS EXISTS: economy.xml prices 236 fillTypes and does not say which of
them the farm SELLS and which it BUYS. That distinction is the whole ballgame
for a price calendar -- for a crop a HIGH price is good, for an input a LOW
price is good -- and getting it backwards would invert the advice silently,
which is the most dangerous kind of wrong. Rather than hardcode a list of
"things that are seed", this reads the game's own classification.

THE CLASSIFIER IS POSITIVE-ONLY, AND THAT IS DELIBERATE (corrected 2026-08-16g
after F-311: reading it as a complete SELL/BUY split cost ~$1.1M/month of
mis-advice on a real farm). A fillType is CONFIRMED SELLABLE if EITHER holds:
    (a) it appears in any SELLINGSTATION_* <fillTypeCategory> -- the game's
        own price-table grouping, checked against this install and map
        (WHEAT/OAT/CANOLA/COTTON confirmed this way); or
    (b) a placeables.xml selling station in THIS SAVE has traded it -- a
        <stats fillType=.../> node under a placeable, the same station data
        read_prices.py already parses.
Both sources are POSITIVE evidence only. NEITHER is a complete inventory of
what the farm can sell, and the union of both is STILL INCOMPLETE: on the
farm that surfaced F-311, MANURE and WOOL are base-game outputs recovered by
source (b), but MILK never appears in either source though the game sells it.
ABSENCE FROM sellable_confirmed MEANS "NOT YET CONFIRMED SELLABLE" -- NEVER
"the farm buys this" and never "this is unsellable". There is no reliable way
to name what the farm buys from this data, so this module does not attempt
it; SEEDS/FERTILIZER/HERBICIDE/DIESEL/LIQUIDFERTILIZER/DIGESTATE/
LIQUIDMANURE/ANHYDROUS are confirmed inputs via the game's <sprayType> list
below, an independent, positive source -- not by process of elimination
against sellable_confirmed.

MAP-FIRST RESOLUTION IS MANDATORY -- THIS IS F-019's RULE, NOT A NICETY.
A mod map ships its OWN fillTypes/fruitTypes/sprayTypes, and they win over
the base install. Concretely, on this save: the map adds 24 fillTypes the base
install has never heard of and an extra ANHYDROUS spray type; its fruitTypes
list has 29 entries against the base's 25, four of which (alfalfa, clover,
meadow, meadowWeed) exist ONLY in the map.

Its per-crop seed rates happen to be IDENTICAL to the base install's for all
15 crops that appear in both -- which is exactly why this must not shortcut to
the base install. "They agree today" is the precondition for the F-019 trap,
not an argument against it: a base-install lookup would return a real,
plausible, correct-looking number for as long as the two happen to agree, and
start lying silently the day a map rebalances a seed rate. Resolve where the
game resolves, or report unresolved.

The map mod is derived from the SAVE, not from config: careerSavegame.xml's
<mapId> reads "<ModName>.<MapClass>", so the part before the first dot is the
mod whose zip holds the map. A mapId with no dot is a base-game map and there
is no mod to consult.

SEED RATE -- ANSWERED, WITH ITS SOURCE, AND WORTH STATING PLAINLY BECAUSE IT
WAS PREVIOUSLY BELIEVED UNDERIVABLE:
    Each fruitType's own foliage XML carries
        <fruitType name="wheat"> <seeding litersPerSqm="0.0308"/> ...
    litersPerSqm * 10000 = litres per hectare. Wheat -> 308 L/ha.
    PLAUSIBILITY-CHECKED, because this codebase's own rule is that unit bugs
    are caught by physical sense and not by reading code harder: SEEDS has
    massPerLiter 0.35 in maps_fillTypes.xml, so 308 L/ha is ~108 kg/ha of
    wheat seed. Real-world wheat drills at roughly 100-200 kg/ha. The number
    survives the test. Read as litres-per-HECTARE instead of per-sqm it would
    be 0.0308 L/ha -- a teaspoon of seed for a whole hectare, which is
    absurd, and that absurdity is what identifies the unit.

Output contract:
    - Absence never looks like data. If the install/mods dirs aren't
      resolvable, or the map zip is missing, this emits {"error": ...} naming
      what's missing -- it never returns an empty classification that would
      read as "nothing is sellable" or "no crop needs seed".
    - Every resolved fact carries `resolved_from` ("map" / "base") so a
      caller can see which package answered.
"""
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit
from read_store_prices import load_paths, parse_args as _sp_parse_args

SELLING_CATEGORY_PREFIX = "SELLINGSTATION"
SQM_PER_HECTARE = 10000.0

# Inputs the farm BUYS that carry no declarative marker anywhere in the game's
# XML -- the engine knows them by name, so nothing can be resolved from data.
#
# This list is deliberately TINY and everything else is resolved: the
# sprayable inputs (fertiliser, lime, herbicide, manure, digestate, and any
# the map adds) come from the game's own <sprayType> list, so a map that
# invents a new one is picked up with no code change here. These three are the
# residue that genuinely cannot be:
#   SEEDS  -- consumed by <seeding litersPerSqm>, which names a RATE but no
#             fillType; the engine supplies the generic seed type.
#   DIESEL -- fuel. Appears in vehicles.xml fill units; no category marks it
#   DEF      as "a thing the farm buys".
#
# NOTE the failed alternative, because it is instructive: "not sellable at a
# selling station" is NOT a usable definition of an input. It is true of every
# input, but it is also true of AIR (a brake reservoir), PROPANE, STONE,
# FORAGE_MIXING and ~200 intermediate/product fillTypes -- so using it would
# bury four real buy-signals in two hundred rows of noise. Sellability is a
# sound test for what the farm SELLS; it is not the complement of it.
ENGINE_LEVEL_INPUT_FILL_TYPES = {
    "SEEDS": "consumed by the <seeding> mechanic, which declares a rate but no fillType",
    "DIESEL": "fuel; carried in vehicle fill units, marked by no category",
    "DEF": "diesel exhaust fluid; same",
}

# "$data/..." inside a map's own XML points back at the BASE install, not at
# the map zip -- the map is explicitly deferring to the base game for that
# file. Honouring this prefix is what makes map-first resolution correct
# rather than merely map-only.
DATA_PREFIX_RE = re.compile(r"^\$data/(.+)$")


def parse_path_args(argv):
    """Reuse read_store_prices' own path resolution rather than reinventing
    it -- same sanctum/config.json 'paths' block, same explicit overrides."""
    config = install_dir = mods_dir = None
    args = argv[2:]
    i = 0
    while i < len(args):
        if args[i] in ("--config", "--install-dir", "--mods-dir") and i + 1 < len(args):
            val = args[i + 1]
            if args[i] == "--config":
                config = val
            elif args[i] == "--install-dir":
                install_dir = val
            else:
                mods_dir = val
            i += 2
        else:
            i += 1
    return load_paths(config, install_dir, mods_dir)


def read_map_id(savegame_dir):
    """Returns (mod_name_or_None, map_id_or_None, error_or_None).

    mod_name None with no error means "base-game map, no mod zip to consult"
    -- a real answer, distinct from "couldn't tell"."""
    path = os.path.join(savegame_dir, "careerSavegame.xml")
    root, generic = load_xml(path)
    if root is None:
        return None, None, generic.get("error", "unknown error reading careerSavegame.xml")
    el = root.find(".//mapId")
    if el is None or not (el.text or "").strip():
        return None, None, "careerSavegame.xml has no <mapId> -- cannot tell which map this save uses"
    map_id = el.text.strip()
    if "." not in map_id:
        return None, map_id, None
    return map_id.split(".", 1)[0], map_id, None


class PackageResolver:
    """Reads XML out of the map's zip first, falling back to the base install
    only where the map itself defers via a '$data/' path. Never falls back by
    basename -- see F-019 and this module's docstring."""

    def __init__(self, install_dir, mods_dir, map_mod_name):
        self.install_dir = install_dir
        self.mods_dir = mods_dir
        self.map_mod_name = map_mod_name
        self.zip_path = (
            os.path.join(mods_dir, map_mod_name + ".zip") if map_mod_name else None
        )
        self._zip = None
        self._names = []

    def open_map_zip(self):
        """Returns error_or_None. A missing map zip is reported, not ignored:
        silently continuing with base-only data would produce exactly the
        plausible-but-wrong output this class exists to prevent."""
        if not self.zip_path:
            return None
        if not os.path.isfile(self.zip_path):
            return f"map mod zip not found: {self.zip_path}"
        try:
            self._zip = zipfile.ZipFile(self.zip_path)
            self._names = self._zip.namelist()
        except (zipfile.BadZipFile, OSError) as e:
            return f"could not open map mod zip {self.zip_path}: {e}"
        return None

    def find_in_map(self, *needles):
        """First zip entry under a config/ path matching all needles."""
        for n in self._names:
            low = n.lower()
            if all(x.lower() in low for x in needles):
                return n
        return None

    def read_map_xml(self, inner_path):
        try:
            return ET.fromstring(self._zip.read(inner_path).decode("utf-8", "replace")), None
        except (KeyError, ET.ParseError, OSError) as e:
            return None, f"could not read {inner_path} from map zip: {e}"

    def read_base_xml(self, rel_under_data):
        full = os.path.join(self.install_dir, "data", rel_under_data)
        if not os.path.isfile(full):
            return None, f"base install file not found: {full}"
        root, generic = load_xml(full)
        if root is None:
            return None, generic.get("error", f"could not parse {full}")
        return root, None

    def read_referenced(self, filename):
        """Resolve a fruitType's filename, which may be '$data/foliage/x/x.xml'
        (base install -- the map deferring) or 'mapUS/foliage/x/x.xml' (inside
        the map zip). Returns (root, resolved_from, error)."""
        m = DATA_PREFIX_RE.match(filename)
        if m:
            root, err = self.read_base_xml(m.group(1))
            return root, "base", err
        if self._zip is not None and filename in self._names:
            root, err = self.read_map_xml(filename)
            return root, "map", err
        root, err = self.read_base_xml(filename)
        return root, "base", err


def collect_fill_type_categories(resolver):
    """Union base + map categories. The map's fillTypes file is ADDITIVE on
    this map (it adds 24 fillTypes and extends BULK/LIQUID/SPRAYER rather than
    replacing them), so a union -- not a replace -- is the faithful merge.
    Returns (categories dict, sources list, error_or_None)."""
    categories = {}
    sources = []

    base_root, err = resolver.read_base_xml(os.path.join("maps", "maps_fillTypes.xml"))
    if base_root is None:
        return None, None, f"could not read the base install's fillType definitions: {err}"
    for cat in base_root.iter("fillTypeCategory"):
        name = cat.attrib.get("name")
        if name:
            categories.setdefault(name, set()).update((cat.text or "").split())
    sources.append("base:data/maps/maps_fillTypes.xml")

    if resolver._zip is not None:
        inner = resolver.find_in_map("config/", "filltypes")
        if inner:
            root, ferr = resolver.read_map_xml(inner)
            if root is not None:
                for cat in root.iter("fillTypeCategory"):
                    name = cat.attrib.get("name")
                    if name:
                        categories.setdefault(name, set()).update((cat.text or "").split())
                sources.append(f"map:{inner}")
    return categories, sources, None


def collect_placeables_sellable(savegame_dir):
    """fillTypes a selling station in THIS SAVE has actually traded --
    adapted from read_prices.py's station walk (that script already parses
    every <stats fillType=.../> node in placeables.xml; this reuses the same
    walk to collect just the set of fillType names, not the price stats).

    A SECOND, INDEPENDENT positive source for 'confirmed sellable', additive
    to the SELLINGSTATION_* category test. Verified against a real farm
    (F-311): this source is a STRICT SUPERSET of the category test alone (144
    vs 112 fillTypes, 32 gained, 0 lost) -- it recovers MANURE and WOOL,
    which are base-game outputs the category test alone misses -- but it is
    STILL INCOMPLETE (MILK never appears here either on that farm). That
    incompleteness is exactly why the caller must never treat absence from
    the union as 'unsellable'; see the module docstring.

    Returns (set_of_fill_types, source_label, error_or_None). An error here
    is NOT fatal to the caller -- it degrades to the category-only source
    rather than blocking a classification that source (a) already supports.
    """
    path = os.path.join(savegame_dir, "placeables.xml")
    root, generic = load_xml(path)
    if root is None:
        return set(), None, generic.get("error", "unknown error reading placeables.xml")
    fill_types = {
        elem.attrib["fillType"] for elem in root.iter("stats") if "fillType" in elem.attrib
    }
    return fill_types, f"save:{path}", None


def collect_spray_types(resolver):
    """fillTypes the game itself treats as sprayable inputs. Map file wins
    outright here (it is a full sprayTypes list, not an additive fragment),
    with the base install as the fallback."""
    inner = resolver.find_in_map("config/", "spraytypes") if resolver._zip is not None else None
    if inner:
        root, err = resolver.read_map_xml(inner)
        if root is not None:
            return {s.attrib["name"] for s in root.iter("sprayType") if "name" in s.attrib}, f"map:{inner}"
    root, err = resolver.read_base_xml(os.path.join("maps", "maps_sprayTypes.xml"))
    if root is None:
        return set(), f"unresolved: {err}"
    return {s.attrib["name"] for s in root.iter("sprayType") if "name" in s.attrib}, \
        "base:data/maps/maps_sprayTypes.xml"


# A fruit's <foliageState> elements ARE its growth states, in document order:
# the Nth element is growthState N. That indexing is confirmed against this save
# (RESEARCH-field-operations-model-2026-08-23.md sec. 12: for every ground-marked
# field, growthState never lands BELOW the marker index -- 0 counter-examples out
# of 122 fields; if the index were wrong they would land on both sides).
#
# ==> READ THE DECLARED ATTRIBUTE, NEVER THE STATE'S NAME. <==
#
# This function used to classify by NAME PREFIX -- "harvestready..." meant ready,
# "harvested..." meant cut. That was measured against the declared
# `isHarvestReady` attribute on this save's own resolved crops and IT DISAGREES
# FOR 8 OF 29 CROPS. The name is a label; the attribute is what the engine reads.
#
#   crop        name-prefix says   isHarvestReady says   live fields affected
#   maize       ready @ 5,6,7      ready @ 7             8    <- over-claims 2 states
#   potato      ready @ 6          ready @ 9             7    <- wrong in BOTH directions
#   sugarbeet   ready @ 8          ready @ 11            10   <- 3 states EARLY
#   sugarcane   ready @ 8          ready @ 11            0
#   spinach     ready @ 6          ready @ 6,7           2    <- misses a ready state
#   grass       ready @ 4          ready @ 3,4           11   <- misses a ready state
#   alfalfa     ready @ 4          ready @ 3,4           7
#   clover/meadow  ready @ 4       ready @ 3,4           7
#
# That is 50+ of this farm's 122 fields told the wrong thing about harvest, and
# EVERY ONE OF THEM WOULD HAVE LOOKED RIGHT: sugarbeet's state 8 really is named
# "harvestReady", it just is not harvest-ready. The name tracks the ground
# marker, which is a texture; the attribute tracks readiness, which is the fact.
# Same defect shape as reading groundType -- one layer further in, and it
# survived because the growth table never actually built on the live save (see
# derive_growth_states in read_fields.py), so nobody ever saw the wrong answer.
#
# ⚠ THE NAME-DERIVED ANSWER IS STILL COMPUTED AND STILL REPORTED, under
# `name_derived_cross_check`, precisely so this disagreement stays VISIBLE rather
# than being quietly replaced. A future map whose foliage drops the attributes
# would otherwise degrade to silence.
READY_PREFIX = "harvestready"
CUT_PREFIX = "harvested"
DEAD_NAMES = ("dead", "withered")

# The declared flags, as they appear on <foliageState>. Measured across all 29
# resolved crops on this save: isHarvestReady is declared by ALL of them, isCut
# by all but the 2-state cover crop oilseedRadish. So absence is rare and real,
# never the common case -- and it is reported as absence, not as "none".
READY_ATTR = "isHarvestReady"
CUT_ATTR = "isCut"
WITHERED_ATTR = "isWithered"
WEEDING_ATTR = "allowsWeeding"
HOEING_ATTR = "allowsHoeing"


def _flagged(states, attr):
    """1-based indices of the <foliageState> elements carrying attr="true"."""
    return [i for i, fs in enumerate(states, start=1)
            if (fs.attrib.get(attr) or "").strip().lower() == "true"]


def classify_growth_states(states):
    """<foliageState> elements in document order -> what each growthState means.

    `states` is the list of ELEMENTS, not their names -- the attributes are the
    answer and the names are only a cross-check (see the block comment above).

    Returns a dict. Empty lists mean the fruit DECLARES no such state, which is a
    real answer for e.g. grass (no weeding ever) and must not be confused with
    "could not read it" -- an unreadable crop never reaches here, it is reported
    as an unresolved fruitType instead.
    """
    names = [fs.attrib.get("name") for fs in states]

    # The name-prefix reading, kept only to expose drift. Never used as the answer.
    n_ready, n_cut, n_dead = [], [], []
    for i, n in enumerate(names, start=1):
        k = (n or "").lower()
        if k.startswith(READY_PREFIX):
            n_ready.append(i)
        elif k.startswith(CUT_PREFIX):
            n_cut.append(i)
        elif k in DEAD_NAMES:
            n_dead.append(i)

    ready = _flagged(states, READY_ATTR)
    cut = _flagged(states, CUT_ATTR)
    dead = _flagged(states, WITHERED_ATTR)
    # A few crops mark witheredness by NAME only. Falling back is safe here in a
    # way it is not for readiness: `dead` is advisory, and the name "dead" is
    # unambiguous where the attribute is simply absent. Labelled either way.
    dead_basis = "isWithered attribute"
    if not dead and n_dead:
        dead = n_dead
        dead_basis = "state name ('dead'/'withered') -- no isWithered attribute declared"

    return {
        "state_names": names,
        "ready": ready,
        "cut": cut,
        "dead": dead,
        "allows_weeding": _flagged(states, WEEDING_ATTR),
        "allows_hoeing": _flagged(states, HOEING_ATTR),
        "basis": (
            "1-based index into this crop's own <foliageState> list, read from "
            "the declared isHarvestReady/isCut attributes -- NOT from the state's "
            "name, which disagrees for 8 of this map's 29 crops."
        ),
        "dead_basis": dead_basis,
        "name_derived_cross_check": {
            "ready": n_ready,
            "cut": n_cut,
            "agrees": n_ready == ready and n_cut == cut,
            "note": (
                "The superseded name-prefix reading, compared on BOTH ready and "
                "cut. `agrees: false` is EXPECTED on this map for a substantial "
                "minority of crops and is not a fault -- it is reported so the "
                "divergence stays visible, and it is never the answer. No count "
                "is stated here on purpose: it moves with the map's fruitType "
                "list, and a figure that drifts inside a caveat reads as a "
                "checkable fact. Count it from this output if you need it."
            ),
        },
    }


# --------------------------------------------------------------------------
# THE WEED MODEL AND THE STONE RULE -- both read from the game, never constants.
#
# ⛔ DEC-108: WEED CAPABILITY IS A MEMBERSHIP TEST, NEVER A THRESHOLD. The
# relation is non-monotonic, so `weed_state <= N` is wrong by construction for
# every N. On the base table `weederHoe` clears {1,2,3,4,6} -- the hole at 5 is
# real -- while `mulcher` clears {3..9} and cannot touch 1 or 2. No single
# number separates "handled" from "not handled" for any tool.
#
# ⭐ THREE OUTCOMES, NOT TWO: a tool CLEARS a state (-> 0), TRANSFORMS it
# (herbicide moves 3,4,5,6 to 7,8,9 -- states only a mulcher clears), or does
# NOTHING AT ALL (no row). A model with only handles/doesn't-handle cannot say
# that a weeder sent to a state-5 field achieves literally nothing, and a manager
# built on one will report work done that was not done. `handles != clears`.
MAP_CONFIG_SECTION_WEED = "weed"


def _map_config_root(resolver, map_id):
    """The map's own config XML, located the way the GAME locates it.

    modDesc.xml declares <map id=... configFilename=...>; that reference is READ,
    not guessed from a naming convention, because a mod is free to name its
    config anything. Returns (root, inner_path, error_or_None). A base-game map
    (no zip) returns (None, None, None) -- a real answer, not a failure.
    """
    if resolver._zip is None:
        return None, None, None
    try:
        desc = ET.fromstring(resolver._zip.read("modDesc.xml"))
    except (KeyError, ET.ParseError, OSError) as e:
        return None, None, f"could not read modDesc.xml from the map zip: {e}"
    short_id = map_id.split(".", 1)[1] if map_id and "." in map_id else None
    chosen = None
    for node in desc.iter("map"):
        cfg = node.attrib.get("configFilename")
        if not cfg:
            continue
        if short_id is None or node.attrib.get("id") == short_id:
            chosen = cfg
            break
    if chosen is None:
        return None, None, (
            f"modDesc.xml in the map zip declares no <map configFilename=> for "
            f"map id {short_id!r}; the map's own config could not be located."
        )
    root, err = resolver.read_map_xml(chosen)
    if root is None:
        return None, chosen, err
    return root, chosen, None


def _parse_replacements(root):
    """<replacements><tool><replacements [fruitType=]><replacement .../>.

    Returns {tool: {"default": {src: tgt}, "by_fruit_type": {FRUIT: {src: tgt}}}}.
    A target of 0 means CLEARED; any other target means transformed, not cleared.
    """
    tools = {}
    container = root.find("replacements")
    if container is None:
        return tools
    for tool_node in container:
        entry = {"default": {}, "by_fruit_type": {}}
        for group in tool_node.findall("replacements"):
            fruit = group.attrib.get("fruitType")
            target = entry["default"] if fruit is None else \
                entry["by_fruit_type"].setdefault(fruit.upper(), {})
            for rep in group.findall("replacement"):
                try:
                    src = int(rep.attrib["sourceState"])
                    tgt = int(rep.attrib["targetState"])
                except (KeyError, ValueError):
                    continue
                target[src] = tgt
        tools[tool_node.tag] = entry
    return tools


def _summarise_tools(tools):
    """Per tool: which states it CLEARS, which it merely CHANGES. Sorted lists,
    not sets, so the payload is JSON and a reader can diff two runs."""
    out = {}
    for tool, entry in sorted(tools.items()):
        def split(mapping):
            return {
                "clears": sorted(s for s, t in mapping.items() if t == 0),
                "changes_without_clearing": {str(s): t for s, t in sorted(mapping.items()) if t != 0},
            }
        out[tool] = {
            "default": split(entry["default"]),
            "by_fruit_type": {f: split(m) for f, m in sorted(entry["by_fruit_type"].items())},
        }
    return out


def collect_weed_model(resolver, map_id):
    """The resolved weed replacement table -- MAP FIRST, BASE SECOND, and the
    map is CHECKED rather than assumed to contribute nothing.

    ⚠ On this save the map's own weed.xml declares an <infoLayer> and no
    <replacements> at all, so the BASE table is in force. That is a MEASUREMENT,
    not an assumption, and this function re-makes it every run: a map update that
    adds replacements must change the answer, not be silently ignored.
    """
    info = {
        "map_config": None,
        "map_weed_file": None,
        "map_contributes_replacements": None,
        "base_file": None,
        "resolution_rule": (
            "The map's own weed config is read first via modDesc.xml's declared "
            "<map configFilename=>. If it declares <replacements> those are the "
            "table. If it declares none -- the common case -- the base install's "
            "data/maps/maps_weed.xml is in force, and this says so explicitly "
            "rather than leaving base-in-force as an unstated default."
        ),
        "error": None,
    }

    map_root, cfg_path, err = _map_config_root(resolver, map_id)
    info["map_config"] = cfg_path
    if err:
        info["error"] = err
    if map_root is not None:
        node = map_root.find(MAP_CONFIG_SECTION_WEED)
        inner = node.attrib.get("filename") if node is not None else None
        info["map_weed_file"] = inner
        if inner:
            weed_root, werr = resolver.read_map_xml(inner)
            if weed_root is None:
                info["error"] = werr
            else:
                map_tools = _parse_replacements(weed_root)
                info["map_contributes_replacements"] = bool(map_tools)
                if map_tools:
                    info["source"] = f"map:{inner}"
                    return _summarise_tools(map_tools), info

    base_rel = os.path.join("maps", "maps_weed.xml")
    base_root, berr = resolver.read_base_xml(base_rel)
    info["base_file"] = "base:data/" + base_rel.replace(os.sep, "/")
    if base_root is None:
        info["error"] = berr
        return None, info
    info["source"] = info["base_file"]
    return _summarise_tools(_parse_replacements(base_root)), info


def collect_stone_picking(resolver):
    """<picking minValue= maxValue= pickedValue=> -> the pickable MEMBERSHIP set.

    ⛔ The working mod this project studied uses `stoneLevel >= 3`, and that is
    wrong in BOTH directions against the game's own declaration: it misses state
    2 (pickable) and wrongly includes state 5 (pickedValue -- already picked).
    A threshold cannot express a bounded band with an above-band "done" marker.
    """
    info = {"source": None, "error": None}
    base_rel = os.path.join("maps", "maps_stones.xml")
    root, err = resolver.read_base_xml(base_rel)
    info["source"] = "base:data/" + base_rel.replace(os.sep, "/")
    if root is None:
        info["error"] = err
        return None, info
    node = root.find(".//picking")
    if node is None:
        info["error"] = "maps_stones.xml declares no <picking> element"
        return None, info
    try:
        low = int(node.attrib["minValue"])
        high = int(node.attrib["maxValue"])
        picked = int(node.attrib["pickedValue"])
    except (KeyError, ValueError) as e:
        info["error"] = f"<picking> is missing or malformed: {e}"
        return None, info
    return {
        "pickable_states": list(range(low, high + 1)),
        "picked_state": picked,
        "min_value": low,
        "max_value": high,
        "rule": (
            "Membership, not a threshold: a field needs stone picking when its "
            "stoneLevel is IN pickable_states. picked_state means it has already "
            "been picked and needs nothing."
        ),
    }, info


def scan_foliage_dir(resolver, already_declared):
    """Fruits present in data/foliage/ that no fruitType list mentions.

    Returns (crops, error_or_None). Each carries resolved_from='base:foliage-scan'
    so a consumer can see this came from a filename convention rather than a
    declaration -- a weaker claim, and one worth labelling."""
    base = os.path.join(resolver.install_dir, "data", "foliage")
    if not os.path.isdir(base):
        return [], f"no foliage directory at {base}"
    found = []
    try:
        entries = sorted(os.listdir(base))
    except OSError as e:
        return [], f"could not list {base}: {e}"
    for d in entries:
        xml_path = os.path.join(base, d, d + ".xml")
        if not os.path.isfile(xml_path):
            continue
        root, generic = load_xml(xml_path)
        if root is None:
            continue
        node = root.find("fruitType")
        if node is None:
            continue
        name = node.attrib.get("name")
        # Trust the file's OWN declared name, not the folder it sits in. If they
        # disagree the folder is the guess and the declaration is the fact.
        if not name or name.lower() in already_declared:
            continue
        growth = classify_growth_states(list(root.iter("foliageState")))
        seeding = node.find("seeding")
        per_sqm = None
        if seeding is not None and "litersPerSqm" in seeding.attrib:
            try:
                per_sqm = float(seeding.attrib["litersPerSqm"])
            except ValueError:
                per_sqm = None
        found.append({
            "crop": name,
            "source_file": os.path.relpath(xml_path, resolver.install_dir),
            "resolved_from": "base:foliage-scan",
            "litres_per_sqm": per_sqm,
            "litres_per_hectare": round(per_sqm * SQM_PER_HECTARE, 2) if per_sqm else None,
            "growth_states": growth,
            "note": "Found by scanning data/foliage/ -- NOT declared by the map's or the "
                    "base map's fruitType list, yet present in the install. Onion is the "
                    "known case. Weaker provenance than a declared fruit; the states "
                    "themselves are read from the file, not inferred.",
        })
    return found, None


def collect_seed_rates(resolver):
    """Per-crop seed usage, from each fruitType's own foliage XML.
    Returns (list, source_label, error_or_None)."""
    inner = resolver.find_in_map("config/", "fruittypes") if resolver._zip is not None else None
    if inner:
        root, err = resolver.read_map_xml(inner)
        source = f"map:{inner}"
        if root is None:
            return None, source, err
    else:
        root, err = resolver.read_base_xml(os.path.join("maps", "maps_fruitTypes.xml"))
        source = "base:data/maps/maps_fruitTypes.xml"
        if root is None:
            return None, source, err

    crops = []
    for ft in root.iter("fruitType"):
        filename = ft.attrib.get("filename")
        if not filename:
            continue
        froot, resolved_from, ferr = resolver.read_referenced(filename)
        if froot is None:
            crops.append({
                "crop": None,
                "source_file": filename,
                "litres_per_hectare": None,
                "error": ferr,
                "note": "This fruitType could not be resolved -- its seed rate is UNKNOWN, "
                        "not zero, and it is not silently dropped from the list.",
            })
            continue
        node = froot.find("fruitType")
        if node is None:
            continue
        name = node.attrib.get("name")

        # Growth states come from the SAME file we already have open. A crop with
        # no seed rate (trees, meadow) can still be harvestable, so this is read
        # before the seeding early-outs below -- attaching it only to the happy
        # path would silently strip states from exactly the odd crops that need
        # explaining.
        growth = classify_growth_states(list(froot.iter("foliageState")))
        if not growth["state_names"]:
            growth["error"] = ("this fruit's foliage XML declares no <foliageState> -- its "
                               "growth states are UNKNOWN. Do not infer readiness for it.")

        seeding = node.find("seeding")
        if seeding is None or "litersPerSqm" not in seeding.attrib:
            crops.append({
                "crop": name,
                "source_file": filename,
                "resolved_from": resolved_from,
                "litres_per_hectare": None,
                "growth_states": growth,
                "note": "This crop's foliage XML has no <seeding litersPerSqm> -- it is not "
                        "sown from generic seed (tree/meadow types typically aren't). UNKNOWN, "
                        "not zero.",
            })
            continue
        try:
            per_sqm = float(seeding.attrib["litersPerSqm"])
        except ValueError:
            continue
        crops.append({
            "crop": name,
            "source_file": filename,
            "resolved_from": resolved_from,
            "litres_per_sqm": per_sqm,
            "litres_per_hectare": round(per_sqm * SQM_PER_HECTARE, 2),
            "is_available_to_sow": seeding.attrib.get("isAvailable"),
            "growth_states": growth,
        })
    # The map's fruitType list is NOT the whole truth. This farm's save contains
    # ONION fields, and onion appears in NEITHER the map's list (29 fruits) nor
    # the base map's list (43) -- yet $data/foliage/onion/onion.xml exists and
    # declares its states. Something pulls it in that neither list mentions.
    #
    # So: sweep data/foliage/ for anything the lists missed. Without this, a fruit
    # the player is actually growing has no state table, and every consumer has to
    # answer "is field 61 ready?" with null. Provenance is recorded, because a
    # fruit found by convention is a weaker claim than one the map declared.
    declared = {(c.get("crop") or "").lower() for c in crops}
    extra, scan_err = scan_foliage_dir(resolver, declared)
    crops.extend(extra)
    if scan_err:
        source = source + f" (+foliage scan: {scan_err})"
    elif extra:
        source = source + f" (+{len(extra)} from base:foliage-scan)"
    return crops, source, None


def main():
    savegame_dir = arg_or_exit("read_game_defs.py <savegame_dir> [--config PATH] "
                               "[--install-dir DIR] [--mods-dir DIR]")
    install_dir, mods_dir, path_err = parse_path_args(sys.argv)
    if path_err:
        emit({"error": path_err, "calibration_needed": True})
        return

    map_mod, map_id, err = read_map_id(savegame_dir)
    if err:
        emit({"error": err, "calibration_needed": True})
        return

    resolver = PackageResolver(install_dir, mods_dir, map_mod)
    zip_err = resolver.open_map_zip()
    if zip_err:
        emit({
            "error": (
                f"{zip_err}. This save's map is a MOD ({map_id}), so the base install's "
                "definitions are NOT authoritative for it -- reporting them anyway would be "
                "the F-019 trap (a plausible, wrong answer). Refusing to guess."
            ),
            "map_id": map_id,
            "calibration_needed": True,
        })
        return

    categories, cat_sources, cat_err = collect_fill_type_categories(resolver)
    if cat_err:
        emit({"error": cat_err, "calibration_needed": True})
        return

    sellable = set()
    for name, members in categories.items():
        if name.upper().startswith(SELLING_CATEGORY_PREFIX):
            sellable |= members

    if not sellable:
        emit({
            "error": (
                "no fillType appears in any SELLINGSTATION_* category -- the primary "
                "confirmed-sellable source found nothing, which almost certainly means the "
                "game's own price-table schema has changed rather than that the farm sells "
                "nothing. Refusing to emit a classification built on that."
            ),
            "calibration_needed": True,
        })
        return

    spray_types, spray_source = collect_spray_types(resolver)
    crops, crop_source, crop_err = collect_seed_rates(resolver)

    # The two field-work rule sources. Neither is fatal: a farm can still be told
    # what is ready to harvest without them, and a null table must read as
    # "unknown" downstream, never as "nothing to do" (DEC-001).
    weed_model, weed_info = collect_weed_model(resolver, map_id)
    stone_picking, stone_info = collect_stone_picking(resolver)

    # Second, independent positive source (F-311 fix, step (2)): a
    # placeables.xml selling station this save has actually traded with. A
    # failure here is NOT fatal -- it degrades to the category-only source,
    # which already passed the emptiness guard above -- but it is recorded
    # in sellable_source either way, never silently dropped.
    placeables_sellable, placeables_source, placeables_err = collect_placeables_sellable(savegame_dir)
    sellable_confirmed = sellable | placeables_sellable
    sellable_source = list(cat_sources) + [
        placeables_source if placeables_source else f"save:placeables.xml unreadable: {placeables_err}"
    ]

    # Cross-check: every sprayType should be non-sellable. Checked against the
    # FULL confirmed-sellable union (categories + placeables), not just the
    # category source alone, so a fillType placeables.xml recovers (e.g.
    # MANURE, both a sprayable input and a station-traded output on the F-311
    # farm) is correctly flagged as ambiguous rather than missed.
    contradictions = sorted(s for s in spray_types if s in sellable_confirmed)

    emit({
        "map_id": map_id,
        "map_mod": map_mod,
        "map_mod_zip": resolver.zip_path,
        "resolution_rule": (
            "Map package first, base install ONLY where the map's own XML defers via a "
            "'$data/' path. Never a basename fallback (F-019). On this map the per-crop seed "
            "rates happen to match the base install exactly -- which is precisely why the "
            "shortcut is forbidden: agreement today is what makes a base-only lookup look "
            "correct right up until a map rebalances something."
        ),
        "sellable_confirmed": sorted(sellable_confirmed),
        "sellable_source": sellable_source,
        "sellable_rule": (
            "A fillType is CONFIRMED SELLABLE if it appears in a SELLINGSTATION_* "
            "fillTypeCategory (the game's own price-table grouping) OR in a placeables.xml "
            "selling-station <stats> node for this save. Both sources are POSITIVE evidence "
            "only -- neither is a complete inventory of what the farm can sell, and their "
            "union is confirmed STILL INCOMPLETE (F-311: MILK sells in-game but appears in "
            "neither source on the farm that surfaced this). Absence from sellable_confirmed "
            "means 'not yet confirmed sellable' -- NEVER 'the farm buys this' and never 'this "
            "is unsellable'. There is no reliable way to name what the farm buys from this "
            "data; input_fill_types below is a SEPARATE, independently-sourced positive list, "
            "not the complement of this one."
        ),
        # ⛔ MEMBERSHIP TABLES, NOT THRESHOLDS (DEC-108). Read every run from the
        # game's own files so a map that rebalances them changes the answer.
        # null means the table could not be resolved -- UNKNOWN, never "no work".
        "weed_model": weed_model,
        "weed_model_source": weed_info,
        "weed_model_rule": (
            "Per tool: `clears` are the weedStates that go to 0, "
            "`changes_without_clearing` are states the tool alters WITHOUT "
            "removing the weed. A state in neither list is untouched by that "
            "tool. Test MEMBERSHIP -- the relation is non-monotonic and no "
            "threshold expresses it. ⚠ This table says what a TOOL can do; it "
            "does NOT say whether the CROP permits the operation. That gate is "
            "each crop's own allows_weeding / allows_hoeing state list under "
            "seed_rates[].growth_states. Both must be consulted."
        ),
        "stone_picking": stone_picking,
        "stone_picking_source": stone_info,
        "spray_input_fill_types": sorted(spray_types),
        "spray_input_source": spray_source,
        "input_fill_types": sorted(spray_types | set(ENGINE_LEVEL_INPUT_FILL_TYPES)),
        "input_fill_types_basis": {
            **{s: f"declared by the game's own <sprayType> list ({spray_source})" for s in sorted(spray_types)},
            **ENGINE_LEVEL_INPUT_FILL_TYPES,
        },
        "input_fill_types_rule": (
            "What the farm BUYS. Sprayable inputs are resolved from the game's own sprayTypes "
            "(so a map adding one -- this map adds ANHYDROUS -- is picked up with no code "
            "change); SEEDS/DIESEL/DEF are named explicitly because the engine knows them by "
            "name and no XML marks them. This is NOT the complement of sellable_confirmed: "
            "'absent from sellable_confirmed' is also true of AIR, PROPANE, STONE and ~200 "
            "intermediate products (and, on some farms, of real outputs sellable_confirmed "
            "simply hasn't seen traded yet), so using absence as the input test would bury "
            "the real buy-signals in noise and misclassify untraded outputs as inputs."
        ),
        "classifier_cross_check": {
            "every_spray_type_is_non_sellable": not contradictions,
            "contradictions": contradictions or None,
            "note": (
                "Independent confirmation: the sprayTypes list and sellable_confirmed are "
                "unrelated structures, and every sprayType lands outside sellable_confirmed. "
                "Two structures agreeing is why this classifier is trusted over a hand-written "
                "list of names."
                if not contradictions else
                "WARNING: these fillTypes are BOTH sprayable inputs AND confirmed sellable, "
                "so 'buy low' and 'sell high' both apply and the calendar for them is "
                "genuinely ambiguous. Reported rather than silently forced to one side."
            ),
        },
        "seed_rates": crops,
        "seed_rates_source": crop_source,
        "seed_rates_error": crop_err,
        "seed_rate_units": (
            "litres_per_hectare = <seeding litersPerSqm> * 10000, from each fruitType's own "
            "foliage XML. Plausibility-checked: wheat 308 L/ha * SEEDS massPerLiter 0.35 = "
            "~108 kg/ha, which matches real-world wheat drilling rates (~100-200 kg/ha). A "
            "null rate means the crop is not sown from generic seed, NOT that seed is free."
        ),
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
