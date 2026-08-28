"""
Read used-equipment marketplace listings for this savegame.

Usage: python read_sales.py <savegame_dir>

CONTEXT: Unlike new-equipment prices (static, defined in mod/map files, not
saved), the "Buy Used" listings ARE dynamic and saved per-game -- confirmed by
modding community references to a "sales.xml" file being part of the savegame
and editable to remove/adjust listings. The exact filename was not
independently verified at authoring time, so this script tries several likely
candidates and reports which one (if any) it found, plus a generic dump.

On first real run: if none of the candidates exist, look in the savegame
folder for a file with "sale" in the name and add it to CANDIDATE_FILENAMES.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit

CANDIDATE_FILENAMES = [
    "sales.xml",
    "vehicleSales.xml",
    "usedSales.xml",
    "shopSales.xml",
    "salesItems.xml",
]


def main():
    if len(sys.argv) < 2:
        print('{"error": "usage: read_sales.py <savegame_dir>"}')
        sys.exit(1)
    savegame_dir = sys.argv[1]

    tried = []
    for filename in CANDIDATE_FILENAMES:
        path = os.path.join(savegame_dir, filename)
        exists = os.path.isfile(path)
        tried.append({"filename": filename, "exists": exists})
        if exists:
            root, generic = load_xml(path)
            if root is None:
                emit({"found_file": filename, "error": generic.get("error")})
                return

            listings = []
            for elem in root.iter():
                tag_lower = elem.tag.lower()
                if "sale" in tag_lower or "offer" in tag_lower or "item" in tag_lower:
                    if elem.attrib:
                        listings.append({"tag": elem.tag, "attrs": dict(elem.attrib)})

            emit({
                "found_file": filename,
                "listing_count": len(listings),
                "listings_guess": listings,
                "calibration_needed": len(listings) == 0,
                "generic_dump": generic,
            })
            return

    emit({
        "found_file": None,
        "tried": tried,
        "note": "No known used-equipment sales file found under any candidate name. "
                "Check the savegame folder directly for a file with 'sale' in its name "
                "and add it to CANDIDATE_FILENAMES in this script. If truly absent, "
                "the player may need to check the in-game shop directly for used listings.",
    })


if __name__ == "__main__":
    main()
