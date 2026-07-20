"""
Resolve real store prices for equipment/buildings from the base game install and
mod zips -- kills the "new-equipment prices aren't in the savegame, ask the
player" limitation (FRICTION-LOG.md F-011). Prices ARE on disk, just not in
the savegame: one <price> (or <storeData><price>) tag per item, in loose XML
under the install's data/ folder for base content, and inside each mod's zip
for modded content.

Usage:
    python3 read_store_prices.py <savegame_dir> [--farm-id N]
        [--config PATH] [--install-dir DIR] [--mods-dir DIR]
        (--fleet | --lookup FILENAME | --search KEYWORD | --gaps)
        [--category vehicles|placeables|objects] [--include-mods] [--limit N] [--verbose]

Modes (exactly one; default is --fleet if none given):
    --fleet                Resolve and price-check every one of the player's
                            OWNED vehicles (vehicles.xml, filtered --farm-id,
                            same as read_vehicles.py). THE validation gate for
                            this whole script -- see "Validation" below.
    --lookup FILENAME       Resolve one savegame-style filename (exactly as it
                            appears in vehicles.xml/placeables.xml, e.g.
                            "$moddir$FS25_Edison_BDE/xml/bde.xml" or
                            "data/vehicles/johnDeere/series8R/series8R.xml")
                            to its store data.
    --search KEYWORD        Case-insensitive substring search over base-game
                            store data (name text, l10n key, filename, brand)
                            in the chosen --category (default: vehicles). Add
                            --include-mods to also scan installed mod zips
                            (slower: ~400 zips).
    --gaps                  Convenience preset: price the categories a farm needs
                            to complete its crop cycle -- seeders, tillage,
                            sprayers -- in one call. A fleet that can take a crop
                            off but not put one in is a common and expensive
                            shape, and this costs the difference.
                            WHICH gaps a given farm has is NOT decided here: read
                            it from read_vehicles.py's `specializations`, the
                            save's own runtime state. This script prices
                            categories; it does not know your fleet.
                            --include-mods works here too.

PORTABLE CODE MUST NOT CARRY ONE FARM'S BOOKS -- the bug that earned the rule,
kept here (where maintainers read it) rather than in the runtime output (where
every session would):
    This preset's `why` text used to assert, to every user of this skill, that
    "this farm owns four complete harvest crews" and that "every purchase adds
    to a $7.3M debt at 5%/yr". Three things were wrong with that, and only the
    first is obvious:
      1. It described ONE farm, shipped to everyone. A reader of another save
         got confident prose about a fleet and a debt that were never theirs.
      2. Both numbers were false even for that farm. The debt was off by ~3x
         once farms.xml's own finances block was actually read, and the rate
         had been invented outright -- it was never derived from anything.
      3. It rotted on contact. A farm's debt changes every in-game day; any
         figure baked into portable code is stale before the next session.
    The first fix for this replaced the numbers with a paragraph explaining the
    numbers -- which still shipped one farm's debt and rate in every --gaps
    payload, and still rotted. Naming a farm's books to explain why you don't
    name a farm's books is the same defect wearing an apology.
    The rule that survives: a skill's scripts describe the SAVE; a farm's own
    sanctum/ describes the farm. If a figure would go stale when the player
    plays, it does not belong in this folder at all.

WHERE PRICES ACTUALLY LIVE (verified 2026-07-16 against this install):
    - Base game: <install_dir>/data/vehicles/**/*.xml (758 files),
      data/placeables/**/*.xml (503 files) -- each carries a plain
      <storeData><price>NNNNN</price></storeData>.
    - Mods: <mods_dir>/<ModName>.zip -- same <storeData><price>> tag, inside
      the zip at the path implied by the savegame's "$moddir$<ModName>/..."
      filename (the part after the mod name maps directly to a path inside
      the zip -- verified against all 7 mods this fleet uses).
    Paths are read from sanctum/config.json's "paths" block (install_dir,
    mods_dir) by default -- see --config/--install-dir/--mods-dir below.
    Never hardcoded (FRICTION-LOG.md F-007 was exactly this mistake for the
    savegame path; not repeating it here for the install path).

THE CRITICAL SUBTLETY (F-019, a real error this script exists partly to
prevent): filenames with a "$moddir$<ModName>/" prefix are NOT in the base
install -- they live ONLY inside that mod's zip, and MUST be resolved there.
A resolver that ignores the $moddir$ prefix and falls back to searching the
base install by basename produces a PLAUSIBLE, WRONG number, because several
of this fleet's mods happen to share an exact basename with an unrelated
base-game file:
    seriesX9.xml        -- base: data/vehicles/johnDeere/seriesX9/seriesX9.xml
                            AND inside FS25_JohnDeereX91100EditedByStevie.zip
    northStar1230FB.xml -- base: data/vehicles/geringhoff/northStar1230FB/...
                            AND inside FS25_northStar1230FBEditedByStevie.zip
    vnx300.xml           -- base: data/vehicles/volvo/vnx300/vnx300.xml
                            AND inside FS25_vnx300BoxTruck.zip
In THIS save the mod and base copies of those three happen to carry the same
price (they're light reskins), which is exactly what makes the failure mode
dangerous: a basename-fallback resolver would have been "right" here by luck
and wrong the moment a mod actually changes the economics. This script NEVER
falls back to a basename search -- a "$moddir$" filename resolves inside that
mod's zip or it is reported unresolved, full stop.

CONFIGURATION SURCHARGES (why saved price != store list price, and that's
correct): the savegame's <vehicle price="..."> is the price AFTER the
player's chosen configuration (motor, wheels, etc.), not the store's base
list price. Verified exactly on one of this fleet's own machines: a series8R
lists at $312,500 base; this fleet's copies show configuration name="motor"
id="5" (the store file's motorConfiguration index 5 = "8R 410", +$56,500) and
a "BROAD_WEIGHTS" wheel option (+$7,000) active. 312500 + 56500 + 7000 =
376000 -- the EXACT saved price. So a moderate positive delta between
resolved store price and saved price is expected and correct, not a bug.
This script does NOT attempt to reconstruct the exact configuration surcharge
in general (the store schema for it is not uniform across vehicle types --
e.g. wheel configuration ids in the savegame combine a base config name with
a brand/tread suffix, "BROAD_WEIGHTS_TRELLEBORG_TM900", that isn't a direct
lookup key -- guessing at that mapping is exactly the kind of unverified
structure this project's rules say not to assume). Instead, --fleet reports
the delta and a plausibility verdict (see below) so a human/lead can sanity
check it, and documents the one case that WAS verified exactly, above.

Output contract (same as the other read_*.py scripts in this toolkit):
    - Never returns [] / {} / a guess for missing data. A filename that can't
      be resolved is reported per-item as unresolved with a reason -- NEVER
      silently substituted with a near-match. That substitution IS the F-019
      bug.
    - calibration_needed means "the expected structure (storeData/price)
      wasn't found where expected", never "search found zero results" or
      "price legitimately looks unusual".
    - Compact by default (search/gaps result lists are capped by --limit,
      default 25, with the true match count always reported alongside so a
      cap is never mistaken for "that's everything" -- see FRICTION-LOG.md
      F-006 on oversized output). --verbose includes full <storeData> specs.
"""
import glob
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit, xml_to_dict

MODDIR_RE = re.compile(r"^\$moddir\$([^/]+)/(.+)$")
DATA_PREFIX_RE = re.compile(r"^\$?data/(.+)$")

# type= attribute values (root <vehicle type="...">) observed in this
# install's base game data, grouped into the categories this farm is
# actually missing. Verified by scanning all 758 base vehicle XMLs
# 2026-07-16 and tabulating every distinct `type` seen -- not guessed.
GAP_CATEGORIES = {
    "seeder": ["sowingMachine", "fertilizingSowingMachine"],
    "tillage": ["plow", "cultivator", "turnOnCultivator", "plowPacker", "weeder", "roller"],
    "sprayer": ["sprayer", "selfPropelledSprayer"],
}

STORE_SUBDIRS = {
    "vehicles": "data/vehicles",
    "placeables": "data/placeables",
    "objects": "data/objects",
}


# --------------------------------------------------------------------------
# Path / config resolution
# --------------------------------------------------------------------------

def load_paths(args_config, args_install_dir, args_mods_dir):
    """Resolve (install_dir, mods_dir, error_or_None).
    Explicit --install-dir/--mods-dir win outright. Otherwise read them from
    a config.json's "paths" block (default: sanctum/config.json relative to
    cwd, matching this skill's convention that scripts run with cwd = the
    project directory -- see SKILL.md). Never falls back to a hardcoded
    Windows/WSL path guess (that mistake is FRICTION-LOG.md F-007)."""
    if args_install_dir and args_mods_dir:
        return args_install_dir, args_mods_dir, None

    config_path = args_config or os.path.join("sanctum", "config.json")
    if not os.path.isfile(config_path):
        return None, None, (
            f"no --install-dir/--mods-dir given and config file not found at "
            f"{config_path!r}. Pass --install-dir/--mods-dir explicitly, or "
            f"--config pointing at a config.json with a 'paths' block "
            f"containing 'install_dir' and 'mods_dir' (see sanctum/config.json "
            f"in this project)."
        )
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, None, f"could not read/parse config file {config_path}: {e}"

    paths = cfg.get("paths", {})
    install_dir = args_install_dir or paths.get("install_dir")
    mods_dir = args_mods_dir or paths.get("mods_dir")
    if not install_dir or not mods_dir:
        return None, None, (
            f"config file {config_path} has no paths.install_dir and/or "
            f"paths.mods_dir. Found paths keys: {sorted(paths.keys())}."
        )
    return install_dir, mods_dir, None


# --------------------------------------------------------------------------
# Store-item parsing
# --------------------------------------------------------------------------

def extract_store_item(root, source_label, verbose=False):
    """Parse a <vehicle>/<placeable> root's <storeData> into a plain dict.
    Returns None if there's no <storeData> at all (not every root has one --
    e.g. bale objects). When verbose=True, includes the full <storeData>
    subtree as storeData_raw (specs, combinations, functions, etc. beyond
    the curated fields) -- omitted by default to keep output compact
    (FRICTION-LOG.md F-006)."""
    sd = root.find("storeData")
    if sd is None:
        return None

    price_elem = sd.find("price")
    price = None
    if price_elem is not None and price_elem.text is not None:
        try:
            price = float(price_elem.text.strip())
        except ValueError:
            price = None

    name_elem = sd.find("name")
    name_literal = None
    name_l10n_key = None
    name_params = None
    if name_elem is not None:
        en = name_elem.find("en")
        if en is not None and en.text and en.text.strip():
            name_literal = en.text.strip()
        elif name_elem.text and name_elem.text.strip():
            name_literal = name_elem.text.strip()
        else:
            name_l10n_key = None
        # l10n-keyed names (base game) look like "$l10n_shopItem_seriesX"
        # regardless of whether text/en resolved -- capture it either way if present.
        raw_text = (name_elem.text or "").strip()
        if raw_text.startswith("$l10n_"):
            name_l10n_key = raw_text
            name_literal = None
        name_params = name_elem.attrib.get("params")

    brand_elem = sd.find("brand")
    category_elem = sd.find("category")
    functions_elem = sd.find("functions")
    functions = [f.text for f in functions_elem] if functions_elem is not None else []

    basename = os.path.splitext(os.path.basename(source_label))[0]
    brand_text = brand_elem.text.strip() if brand_elem is not None and brand_elem.text else None
    derived_label = " ".join(x for x in [
        brand_text.title() if brand_text else None,
        basename,
    ] if x)

    return {
        "source": source_label,
        "type": root.attrib.get("type"),
        "price": price,
        "name_literal": name_literal,
        "name_l10n_key": name_l10n_key,
        "name_params": name_params,
        "name_note": None if name_literal else (
            "no literal English name in this file -- base-game items reference a "
            "l10n translation key (name_l10n_key) resolved elsewhere in the game's "
            "packed data, not available to this script (see store_data.packed note "
            "in config.json: dataS.gar/dataS2.gar are packed, not readable here). "
            "derived_label is a best-effort brand+filename label, NOT the official name."
        ),
        "derived_label": derived_label,
        "brand": brand_text,
        "category": category_elem.text.strip() if category_elem is not None and category_elem.text else None,
        "functions": functions,
        **({"storeData_raw": xml_to_dict(sd)} if verbose else {}),
    }


def resolve_filename(filename, install_dir, mods_dir, verbose=False):
    """Resolve a savegame-style filename to its store item.
    Returns (item_dict_or_None, error_or_None, resolution_kind).
    resolution_kind is one of "base", "mod", "unresolved" -- always set, even
    on error, so callers can tally without re-deriving it."""
    if not filename:
        return None, "empty filename", "unresolved"

    mod_match = MODDIR_RE.match(filename)
    if mod_match:
        mod_name, inner_path = mod_match.group(1), mod_match.group(2)
        zip_path = os.path.join(mods_dir, mod_name + ".zip")
        if not os.path.isfile(zip_path):
            return None, f"mod zip not found: {zip_path}", "mod"
        try:
            with zipfile.ZipFile(zip_path) as z:
                names = z.namelist()
                # Exact match only -- no basename fallback (see F-019 in the
                # module docstring: that fallback is the bug this exists to avoid).
                match = inner_path if inner_path in names else None
                if match is None:
                    # Try case-insensitive exact match on the full path only.
                    lower_map = {n.lower(): n for n in names}
                    match = lower_map.get(inner_path.lower())
                if match is None:
                    return None, (
                        f"{inner_path!r} not found inside {zip_path} "
                        f"(zip has {len(names)} entries; not falling back to a "
                        f"basename search inside the zip)."
                    ), "mod"
                data = z.read(match)
        except (zipfile.BadZipFile, KeyError, OSError) as e:
            return None, f"could not read {inner_path!r} from {zip_path}: {e}", "mod"

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            return None, f"XML parse error in {zip_path}!{inner_path}: {e}", "mod"

        item = extract_store_item(root, f"{mod_name}.zip!{inner_path}", verbose=verbose)
        if item is None:
            return None, f"{zip_path}!{inner_path} parsed but has no <storeData>", "mod"
        item["resolved_from"] = "mod"
        item["mod_name"] = mod_name
        return item, None, "mod"

    data_match = DATA_PREFIX_RE.match(filename)
    if data_match or filename.startswith("data/"):
        rel = data_match.group(1) if data_match else filename[len("data/"):]
        full_path = os.path.join(install_dir, "data", rel)
        if not os.path.isfile(full_path):
            return None, f"base install file not found: {full_path}", "base"
        root, generic = load_xml(full_path)
        if root is None:
            return None, f"could not parse {full_path}: {generic.get('error')}", "base"
        item = extract_store_item(root, full_path, verbose=verbose)
        if item is None:
            return None, f"{full_path} parsed but has no <storeData>", "base"
        item["resolved_from"] = "base"
        return item, None, "base"

    return None, (
        f"filename {filename!r} matches neither '$moddir$<ModName>/...' nor "
        f"'data/...'/'$data/...' -- unrecognized pattern, not resolved."
    ), "unresolved"


# --------------------------------------------------------------------------
# --fleet mode
# --------------------------------------------------------------------------

def plausibility_verdict(saved_price, store_price):
    if store_price is None or saved_price is None:
        return "UNKNOWN (missing price)"
    if store_price <= 0:
        return "UNKNOWN (store price is 0/invalid)"
    delta = saved_price - store_price
    delta_pct = delta / store_price
    if delta < 0:
        return f"SUSPICIOUS (saved price is LOWER than store price by {abs(delta):,.0f} -- unexpected, verify)"
    if delta_pct <= 0.35:
        return f"plausible (+{delta:,.0f}, +{delta_pct:.1%} -- consistent with configuration surcharges)"
    return f"SUSPICIOUS (+{delta:,.0f}, +{delta_pct:.1%} -- larger than any configuration delta observed on this fleet; verify resolution)"


def run_fleet(savegame_dir, farm_id, install_dir, mods_dir, verbose):
    vehicles_path = os.path.join(savegame_dir, "vehicles.xml")
    root, generic = load_xml(vehicles_path)
    if root is None:
        emit({"error": f"could not read vehicles.xml: {generic.get('error')}"})
        return

    owned = [v for v in root.iter("vehicle") if v.attrib.get("farmId") == str(farm_id)]
    if not owned:
        emit({
            "error": f"no <vehicle farmId=\"{farm_id}\"> found in vehicles.xml -- verify --farm-id.",
            "calibration_needed": False,
        })
        return

    rows = []
    resolved_count = 0
    unresolved_count = 0
    for v in owned:
        a = v.attrib
        filename = a.get("filename")
        saved_price = float(a["price"]) if a.get("price") is not None else None
        item, err, kind = resolve_filename(filename, install_dir, mods_dir, verbose=verbose)
        row = {
            "unique_id": a.get("uniqueId"),
            "filename": filename,
            "saved_price": saved_price,
            "resolution_kind": kind,
        }
        if item is None:
            row["resolved"] = False
            row["error"] = err
            unresolved_count += 1
        else:
            row["resolved"] = True
            row["store_price"] = item["price"]
            row["name"] = item["name_literal"] or item["name_l10n_key"] or item["derived_label"]
            row["brand"] = item["brand"]
            row["mod_name"] = item.get("mod_name")
            row["verdict"] = plausibility_verdict(saved_price, item["price"])
            resolved_count += 1
            if verbose:
                row["storeData_raw"] = item.get("storeData_raw")
        rows.append(row)

    total_saved = sum(r["saved_price"] for r in rows if r.get("saved_price") is not None)
    total_resolved_store = sum(r["store_price"] for r in rows if r.get("resolved") and r.get("store_price") is not None)
    suspicious = [r for r in rows if r.get("verdict", "").startswith("SUSPICIOUS")]

    output = {
        "mode": "fleet",
        "farm_id": farm_id,
        "owned_count": len(owned),
        "resolved_count": resolved_count,
        "unresolved_count": unresolved_count,
        "total_saved_price": total_saved,
        "total_resolved_store_price": total_resolved_store,
        "suspicious_count": len(suspicious),
        "suspicious": suspicious,
        "vehicles": rows,
        "validation_note": (
            "Every owned vehicle's saved `price` is ground truth for the same machine -- "
            "resolved store_price should be at or below saved_price, with the gap explained "
            "by configuration surcharges (verified exactly on this fleet's own series8R: "
            "312500 base + 56500 motor + 7000 wheel = 376000 saved, to the dollar). A large "
            "gap, a negative gap, or a base-game hit for a $moddir$ vehicle means the resolver "
            "picked the wrong file, not that the fleet is oddly priced -- see suspicious[] above."
        ),
        "calibration_needed": False,
    }
    emit(output)


# --------------------------------------------------------------------------
# --lookup mode
# --------------------------------------------------------------------------

def run_lookup(filename, install_dir, mods_dir, verbose=False):
    item, err, kind = resolve_filename(filename, install_dir, mods_dir, verbose=verbose)
    if item is None:
        emit({
            "mode": "lookup",
            "filename": filename,
            "resolved": False,
            "resolution_kind": kind,
            "error": err,
        })
        return
    emit({
        "mode": "lookup",
        "filename": filename,
        "resolved": True,
        "resolution_kind": kind,
        "item": item,
    })


# --------------------------------------------------------------------------
# --search / --gaps modes
# --------------------------------------------------------------------------

def iter_base_store_items(install_dir, category):
    subdir = STORE_SUBDIRS[category]
    pattern = os.path.join(install_dir, subdir, "**", "*.xml")
    for path in glob.glob(pattern, recursive=True):
        if os.sep + "sounds" + os.sep in path or "/sounds/" in path:
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        item = extract_store_item(root, os.path.relpath(path, install_dir))
        if item is None:
            continue
        yield item


def iter_mod_store_items(mods_dir, category):
    subdir_hint = STORE_SUBDIRS[category].split("/")[-1]  # "vehicles"/"placeables"/"objects"
    for zip_path in glob.glob(os.path.join(mods_dir, "*.zip")):
        mod_name = os.path.splitext(os.path.basename(zip_path))[0]
        try:
            with zipfile.ZipFile(zip_path) as z:
                for name in z.namelist():
                    if not name.lower().endswith(".xml") or "sound" in name.lower():
                        continue
                    try:
                        data = z.read(name)
                        root = ET.fromstring(data)
                    except (KeyError, ET.ParseError, zipfile.BadZipFile):
                        continue
                    if root.tag not in ("vehicle", "placeable"):
                        continue
                    item = extract_store_item(root, f"{mod_name}.zip!{name}")
                    if item is None:
                        continue
                    item["mod_name"] = mod_name
                    yield item
        except (zipfile.BadZipFile, OSError):
            continue


def attach_verbose_specs(item, install_dir, mods_dir):
    """Re-resolve one already-found item to attach its full storeData_raw.
    Called only on the (small, --limit-bounded) `shown` list after
    truncation, NOT during the full directory/zip scan -- computing the full
    dump for every scanned item (up to ~750 base + ~400 mod files) before
    truncating would be pure waste when only a handful are ever shown."""
    source = item.get("source", "")
    try:
        if item.get("mod_name") and "!" in source:
            zip_path = os.path.join(mods_dir, item["mod_name"] + ".zip")
            inner = source.split("!", 1)[1]
            with zipfile.ZipFile(zip_path) as z:
                root = ET.fromstring(z.read(inner))
        else:
            full_path = os.path.join(install_dir, source)
            root = ET.parse(full_path).getroot()
    except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile):
        return item
    verbose_item = extract_store_item(root, source, verbose=True)
    if verbose_item:
        item["storeData_raw"] = verbose_item.get("storeData_raw")
    return item


def item_matches_keyword(item, keyword_lower):
    haystacks = [
        item.get("name_literal"), item.get("name_l10n_key"), item.get("derived_label"),
        item.get("brand"), item.get("category"), item.get("source"),
    ]
    return any(h and keyword_lower in h.lower() for h in haystacks)


def summarize_items(items, limit):
    items_sorted = sorted((i for i in items if i.get("price") is not None), key=lambda i: i["price"])
    priceless = [i for i in items if i.get("price") is None]
    return {
        "match_count": len(items_sorted) + len(priceless),
        "priced_count": len(items_sorted),
        "shown": items_sorted[:limit],
        "shown_count": min(limit, len(items_sorted)),
        "truncated": len(items_sorted) > limit,
        "priceless_count": len(priceless),
        "min_price": items_sorted[0]["price"] if items_sorted else None,
        "max_price": items_sorted[-1]["price"] if items_sorted else None,
    }


def run_search(keyword, category, install_dir, mods_dir, include_mods, limit, verbose=False):
    items = list(iter_base_store_items(install_dir, category))
    base_scanned = len(items)
    mods_scanned = 0
    if include_mods:
        mod_items = list(iter_mod_store_items(mods_dir, category))
        mods_scanned = len(mod_items)
        items += mod_items

    matched = [i for i in items if item_matches_keyword(i, keyword.lower())]
    summary = summarize_items(matched, limit)
    if verbose:
        summary["shown"] = [attach_verbose_specs(i, install_dir, mods_dir) for i in summary["shown"]]

    emit({
        "mode": "search",
        "keyword": keyword,
        "category": category,
        "include_mods": include_mods,
        "base_items_scanned": base_scanned,
        "mod_items_scanned": mods_scanned if include_mods else None,
        **summary,
        "calibration_needed": False,
    })


def run_gaps(install_dir, mods_dir, include_mods, limit, verbose=False):
    # Scan the base vehicle store data (and, optionally, mod zips) exactly
    # once and reuse the in-memory pool for all three categories -- avoids
    # re-parsing 758 base XML files (and up to ~400 mod zips) three times over.
    base_items = list(iter_base_store_items(install_dir, "vehicles"))
    mods_scanned = 0
    pool = list(base_items)
    if include_mods:
        mod_items = list(iter_mod_store_items(mods_dir, "vehicles"))
        mods_scanned = len(mod_items)
        pool += mod_items

    results = {}
    for gap_name, types in GAP_CATEGORIES.items():
        matched = [i for i in pool if i.get("type") in types]
        summary = summarize_items(matched, limit)
        if verbose:
            summary["shown"] = [attach_verbose_specs(i, install_dir, mods_dir) for i in summary["shown"]]
        results[gap_name] = {
            "types_searched": types,
            "mod_items_scanned": mods_scanned if include_mods else None,
            **summary,
        }

    emit({
        "mode": "gaps",
        "why": (
            "Prices the equipment categories a farm needs to complete its crop cycle -- "
            "sowing, tillage, spraying -- so a gap between what the farm CAN do and what it "
            "NEEDS to do can be costed rather than guessed at. Which gaps this farm actually "
            "has comes from read_vehicles.py's `specializations` (the save's own runtime "
            "state), not from this script and not from any assumption baked in here."
        ),
        "why_not_here": (
            "This states no farm's fleet, debt or interest rate, by design: a skill's scripts "
            "describe the SAVE, and a farm's own sanctum/ describes the farm. For which gaps "
            "THIS farm has, read read_vehicles.py's `specializations`; for its books, read "
            "read_economy.py. See this script's --gaps docstring for the bug that earned the "
            "rule."
        ),
        "categories": results,
        "include_mods": include_mods,
        "calibration_needed": False,
    })


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv):
    args = argv[2:]
    opts = {
        "farm_id": 1, "config": None, "install_dir": None, "mods_dir": None,
        "mode": None, "lookup": None, "search": None, "category": "vehicles",
        "include_mods": False, "limit": 25, "verbose": False,
    }
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--farm-id":
            opts["farm_id"] = int(args[i + 1]); i += 2
        elif a == "--config":
            opts["config"] = args[i + 1]; i += 2
        elif a == "--install-dir":
            opts["install_dir"] = args[i + 1]; i += 2
        elif a == "--mods-dir":
            opts["mods_dir"] = args[i + 1]; i += 2
        elif a == "--fleet":
            opts["mode"] = "fleet"; i += 1
        elif a == "--lookup":
            opts["mode"] = "lookup"; opts["lookup"] = args[i + 1]; i += 2
        elif a == "--search":
            opts["mode"] = "search"; opts["search"] = args[i + 1]; i += 2
        elif a == "--gaps":
            opts["mode"] = "gaps"; i += 1
        elif a == "--category":
            opts["category"] = args[i + 1]; i += 2
        elif a == "--include-mods":
            opts["include_mods"] = True; i += 1
        elif a == "--limit":
            opts["limit"] = int(args[i + 1]); i += 2
        elif a == "--verbose":
            opts["verbose"] = True; i += 1
        else:
            i += 1
    if opts["mode"] is None:
        opts["mode"] = "fleet"
    return opts


def main():
    savegame_dir = arg_or_exit(
        "read_store_prices.py <savegame_dir> [--farm-id N] [--config PATH] "
        "[--install-dir DIR] [--mods-dir DIR] (--fleet | --lookup FILENAME | "
        "--search KEYWORD | --gaps) [--category vehicles|placeables|objects] "
        "[--include-mods] [--limit N] [--verbose]"
    )
    try:
        opts = parse_args(sys.argv)
    except (ValueError, IndexError) as e:
        emit({"error": f"argument error: {e}"})
        return

    if opts["category"] not in STORE_SUBDIRS:
        emit({"error": f"--category must be one of {sorted(STORE_SUBDIRS)}, got {opts['category']!r}"})
        return

    install_dir, mods_dir, path_err = load_paths(opts["config"], opts["install_dir"], opts["mods_dir"])
    if path_err:
        emit({"error": path_err})
        return
    if not os.path.isdir(install_dir):
        emit({"error": f"install_dir does not exist: {install_dir}"})
        return
    if not os.path.isdir(mods_dir):
        emit({"error": f"mods_dir does not exist: {mods_dir}"})
        return

    if opts["mode"] == "fleet":
        run_fleet(savegame_dir, opts["farm_id"], install_dir, mods_dir, opts["verbose"])
    elif opts["mode"] == "lookup":
        run_lookup(opts["lookup"], install_dir, mods_dir, opts["verbose"])
    elif opts["mode"] == "search":
        run_search(opts["search"], opts["category"], install_dir, mods_dir, opts["include_mods"], opts["limit"], opts["verbose"])
    elif opts["mode"] == "gaps":
        run_gaps(install_dir, mods_dir, opts["include_mods"], opts["limit"], opts["verbose"])


if __name__ == "__main__":
    main()
