"""
read_storage_capability.py -- resolve what a storage node can ACCEPT.

The F-102/F-116 fix. "No silo accepts onion" was a FALSE negative: it came from
reading only a storage node's `fillTypes` attribute. A real base-game silo declares
its capability the OTHER way -- via `fillTypeCategories` (e.g. `farmSilo`, `BULK`) --
so a fillTypes-only read sees an empty list and concludes the silo accepts nothing.

This script reads BOTH attributes on every `<storage>` node of a placeable TYPE
definition, then expands each category against the game's fillType definitions
(`data/maps/maps_fillTypes.xml`, where `<fillTypeCategory name="FARMSILO">WHEAT
BARLEY ...</fillTypeCategory>` lists a category's members). Category names are matched
CASE-INSENSITIVELY -- storage nodes reference `fillTypeCategories="farmSilo"` while the
definition is `name="FARMSILO"`; a case-sensitive match is itself an F-102-class bug.

A category the definitions don't declare is reported as UNRESOLVED (unknown) -- never
silently treated as "accepts nothing," matching storage-capability.md's invariant
("unresolved categories are 'unknown', never 'no'").

Usage:
    python3 read_storage_capability.py --placeable <placeable-def.xml> \\
        [--fill-types-xml <maps_fillTypes.xml>] [--config <config.json>]

If --fill-types-xml is omitted, it is resolved from config.json's
paths.install_dir + /data/maps/maps_fillTypes.xml.
"""
import argparse
import json
import os
import sys

import xml_utils


def load_fill_type_categories(fill_types_xml):
    """Return {CATEGORY_NAME_UPPER: [member fillType names]} from a fillTypes xml."""
    root, meta = xml_utils.load_xml(fill_types_xml)
    if root is None:
        return None, meta.get("error", "could not parse fillTypes xml")
    categories = {}
    for cat in root.iter("fillTypeCategory"):
        name = cat.get("name")
        if not name:
            continue
        members = (cat.text or "").split()
        categories[name.strip().upper()] = members
    return categories, None


def resolve_storage(placeable_xml, categories):
    """Read every <storage> node's fillTypes AND fillTypeCategories, expand categories,
    and return the accepted-fill-type resolution with full provenance."""
    root, meta = xml_utils.load_xml(placeable_xml)
    if root is None:
        return {"error": meta.get("error", "could not parse placeable xml")}

    # Authoritative capability lives on <storage> nodes. If a definition carries the
    # attributes on a differently-named element, fall back to any element that has one.
    nodes = [e for e in root.iter() if e.tag == "storage"
             and (e.get("fillTypes") or e.get("fillTypeCategories"))]
    fallback = False
    if not nodes:
        nodes = [e for e in root.iter() if e.get("fillTypes") or e.get("fillTypeCategories")]
        fallback = bool(nodes)

    explicit = []            # from fillTypes= (the attribute F-102 read alone)
    from_categories = {}     # CATEGORY -> [members], the attribute F-102 MISSED
    unresolved = []          # categories the definitions don't declare -> unknown
    for node in nodes:
        for ft in (node.get("fillTypes") or "").split():
            explicit.append(ft.strip().upper())
        for cat in (node.get("fillTypeCategories") or "").split():
            key = cat.strip().upper()
            if key in categories:
                from_categories.setdefault(key, [])
                for m in categories[key]:
                    if m not in from_categories[key]:
                        from_categories[key].append(m)
            elif key not in unresolved:
                unresolved.append(key)

    accepted = set(explicit)
    for members in from_categories.values():
        accepted.update(members)

    return {
        "placeable": placeable_xml,
        "storage_nodes": len(nodes),
        "resolved_via_fallback_element": fallback,
        "accepted_fill_types": sorted(accepted),
        "from_fill_types": sorted(set(explicit)),
        "from_categories": {k: sorted(v) for k, v in from_categories.items()},
        "unresolved_categories": sorted(unresolved),
        "note": "accepted_fill_types is the UNION of explicit fillTypes and expanded "
                "fillTypeCategories -- reading only fillTypes is the F-102 'no silo "
                "accepts onion' false negative. Unresolved categories are 'unknown', not 'no'.",
    }


def _default_fill_types_xml(config_path):
    if not config_path or not os.path.isfile(config_path):
        return None
    try:
        cfg = json.loads(open(config_path, encoding="utf-8").read())
    except (ValueError, OSError):
        return None
    install = (cfg.get("paths") or {}).get("install_dir")
    if not install:
        return None
    return os.path.join(install, "data", "maps", "maps_fillTypes.xml")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resolve a storage node's accepted fill types.")
    ap.add_argument("--placeable", required=True, help="placeable TYPE definition xml")
    ap.add_argument("--fill-types-xml", default=None, help="maps_fillTypes.xml (category defs)")
    ap.add_argument("--config", default=None, help="config.json (to locate the install)")
    args = ap.parse_args(argv)

    fill_types_xml = args.fill_types_xml or _default_fill_types_xml(args.config)
    if not fill_types_xml:
        xml_utils.emit({"error": "no fillTypes xml: pass --fill-types-xml or a --config "
                                 "whose paths.install_dir resolves maps_fillTypes.xml"})
        sys.exit(1)
    if not os.path.isfile(fill_types_xml):
        xml_utils.emit({"error": f"fillTypes xml not found: {fill_types_xml}"})
        sys.exit(1)

    categories, err = load_fill_type_categories(fill_types_xml)
    if err:
        xml_utils.emit({"error": err})
        sys.exit(1)

    result = resolve_storage(args.placeable, categories)
    result["fill_types_xml"] = fill_types_xml
    xml_utils.emit(result)


if __name__ == "__main__":
    main()
