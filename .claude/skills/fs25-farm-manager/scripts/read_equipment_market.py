"""
The used-equipment market, RESOLVED: what each listing actually is, what it
costs new, and therefore whether it is a bargain.

Usage: python3 read_equipment_market.py <savegame_dir>
        [--config PATH] [--install-dir DIR] [--mods-dir DIR]

WHY THIS EXISTS: read_sales.py parses sales.xml into `listings_guess` -- a raw
attribute dump whose most useful field is an `xmlFilename` like
"data/vehicles/newHolland/t8/t8.xml". That is not an answer to the only
question anyone asks of a used-equipment list: *is this worth buying?* A
listing without a new-price comparison is noise. This composes read_sales.py's
find with read_store_prices.py's resolver (which already handles base-install
and mod-zip paths correctly, and refuses basename fallbacks -- F-019) to turn
each listing into something decidable.

THE FILENAME FORM sales.xml USES IS NOT THE ONE vehicles.xml USES. This is the
whole reason a naive resolve fails, and it is worth stating exactly, because
the difference is invisible until you try it (verified against this save,
2026-07-24):
    vehicles.xml : "$moddir$FS25_Edison_BDE/xml/bde.xml"
    sales.xml    : "<FS25 profile>/mods/
                    FS25_tiger6S_premium/rrXL9_premium.xml"
Three things are different and each one breaks something:
    1. It is an ABSOLUTE HOST path (a Windows path, while this may run under
       WSL where that path does not exist).
    2. It has no "$moddir$" marker, so read_store_prices.resolve_filename
       rejects it as an unrecognized pattern.
    3. It points INSIDE A DIRECTORY that does not exist: the game writes
       "mods/FS25_tiger6S_premium/rrXL9_premium.xml", but on disk the mod is
       "mods/FS25_tiger6S_premium.zip" with "rrXL9_premium.xml" at its root.
       The game is naming the mod's logical contents, not a real filesystem
       path.
normalize_sales_filename() below rewrites that form into the "$moddir$" form
the existing resolver already handles correctly, rather than adding a second
resolver that would drift from the first. Base-game paths ("data/...") are
already in a form the resolver accepts and are passed through untouched.

WHY NORMALIZE INSTEAD OF RESOLVE DIRECTLY: the temptation is to strip to the
basename ("rrXL9_premium.xml") and search. That is precisely F-019 -- several
of this install's mods share a basename with an unrelated base-game file, so a
basename search returns a real, plausible, WRONG price and looks right until
the two diverge. The mod name is present in the path; use it.

BARGAIN ASSESSMENT IS A COMPARISON, NOT A VERDICT. This reports the listed
price beside the resolved new price and the machine's condition, and computes
the discount. It does NOT declare "buy this": a heavily-worn machine at 40%
off may be a worse deal than a clean one at 20% off, and repair cost is not
derivable from the save (it is a function the game computes at the workshop).
Condition is surfaced so the discount can be read against it.

UNITS (this codebase's standing trap):
    - operatingTime on a sales <item> is SECONDS, same as vehicles.xml.
      Plausibility-checked: this save's listed New Holland T8 reads
      87,355 -> 24.3 hours for a machine of age 31 with 46% wear. Read as
      hours it would be ~10 years of continuous running on a used tractor,
      which is absurd. Reported as hours, converted, never raw.
    - damage and wear are 0..1 fractions, reported as percentages.
    - age is left RAW and unconverted: its unit could not be established from
      the save or the install, and guessing between days/months/years would be
      exactly the kind of plausible-looking error this project keeps paying
      for. Stated as unknown rather than dressed up.

Output contract:
    - A listing that cannot be resolved is REPORTED, with the reason, and
      keeps its raw attributes. It is never dropped and never given a guessed
      price -- an unresolvable listing is unknown, not free and not worthless.
    - listing_count always reflects sales.xml's real count, so a resolution
      failure can never quietly shrink the market.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit
from read_store_prices import load_paths, resolve_filename

# Matches ".../mods/<ModName>/<inner/path.xml>" in a host-absolute path,
# tolerating either separator. Anchored on the "/mods/" segment because that
# is the one stable landmark: the drive, the user and the game-data root all
# vary by machine, but the game always writes the mod under a "mods" folder.
MODS_SEGMENT_RE = re.compile(r"[/\\]mods[/\\]([^/\\]+)[/\\](.+)$", re.IGNORECASE)


def parse_path_args(argv):
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


def normalize_sales_filename(filename):
    """Rewrite sales.xml's filename form into one resolve_filename understands.

    Returns (normalized, how) where `how` records what was done, so the
    transformation is visible in the output instead of happening invisibly.
    Never strips to a basename -- see the module docstring (F-019).
    """
    if not filename:
        return None, "empty"

    # Already the savegame/mod form, or a base-install relative path.
    if filename.startswith("$moddir$") or filename.startswith("data/") or filename.startswith("$data/"):
        return filename, "already_resolvable"

    m = MODS_SEGMENT_RE.search(filename.replace("\\", "/"))
    if m:
        mod_name, inner = m.group(1), m.group(2)
        return f"$moddir${mod_name}/{inner}", (
            f"host-absolute mod path rewritten to $moddir$ form (mod {mod_name!r}); "
            "the game names the mod's logical contents, but on disk it is a .zip"
        )

    # A host-absolute path into the base install, e.g. ".../data/vehicles/...".
    m2 = re.search(r"[/\\](data[/\\]vehicles[/\\].+)$", filename.replace("\\", "/"), re.IGNORECASE)
    if m2:
        return m2.group(1).replace("\\", "/"), "host-absolute base-install path trimmed to its data/ root"

    return None, (
        f"unrecognized filename form {filename!r} -- matches neither '$moddir$...', 'data/...', "
        "nor a host-absolute path containing a '/mods/<ModName>/' or '/data/vehicles/' segment. "
        "NOT falling back to a basename search: several mods here share a basename with an "
        "unrelated base-game file, so that would return a plausible, wrong price (F-019)."
    )


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_listings(savegame_dir):
    """Returns (list_of_raw_attr_dicts, error_or_None)."""
    path = os.path.join(savegame_dir, "sales.xml")
    root, generic = load_xml(path)
    if root is None:
        return None, generic.get("error", "unknown error reading sales.xml")
    items = list(root.iter("item"))
    if not items:
        return [], None
    return [dict(i.attrib) for i in items], None


def build_listing(attrs, install_dir, mods_dir):
    raw_name = attrs.get("xmlFilename")
    normalized, how = normalize_sales_filename(raw_name)

    listing = {
        "xml_filename_raw": raw_name,
        "xml_filename_normalized": normalized,
        "normalization": how,
        "time_left": attrs.get("timeLeft"),
        "time_left_note": (
            "Raw timeLeft from sales.xml. Its unit is NOT established -- it is not converted "
            "here, because guessing between in-game hours/days would be a plausible-looking "
            "invention. Treat it only as an ordinal: smaller means expiring sooner."
        ),
        "listed_price": to_float(attrs.get("price")),
        "condition": {
            "damage_pct": (lambda d: round(d * 100, 1) if d is not None else None)(to_float(attrs.get("damage"))),
            "wear_pct": (lambda w: round(w * 100, 1) if w is not None else None)(to_float(attrs.get("wear"))),
            "operating_hours": (
                lambda o: round(o / 3600.0, 1) if o is not None else None
            )(to_float(attrs.get("operatingTime"))),
            "operating_hours_note": "operatingTime is SECONDS (converted). Verified by plausibility: "
                                    "read as hours these listings would be decades old.",
            "age_raw": attrs.get("age"),
            "age_note": "age is left RAW: its unit (days/months/years) could not be established "
                        "from the save or the install. Unknown, not assumed.",
        },
    }

    if normalized is None:
        listing["resolved"] = False
        listing["resolve_error"] = how
        listing["new_price"] = None
        listing["value_note"] = (
            "This listing could not be resolved to a store item, so its new price is UNKNOWN "
            "and no discount can be computed. Unknown -- not a bargain, not a rip-off."
        )
        return listing

    item, err, kind = resolve_filename(normalized, install_dir, mods_dir)
    if item is None:
        listing["resolved"] = False
        listing["resolve_error"] = err
        listing["resolution_kind"] = kind
        listing["new_price"] = None
        listing["value_note"] = (
            f"Resolution failed ({err}). New price UNKNOWN -- explicitly not treated as 0, and "
            "the listing is kept in the market list rather than dropped."
        )
        return listing

    new_price = to_float(item.get("price"))
    listed = listing["listed_price"]
    listing["resolved"] = True
    listing["resolution_kind"] = kind
    # Name honesty: base-game items carry an l10n KEY, not English text, and
    # the translations live in the install's packed dataS.gar which nothing
    # here can read. read_store_prices.py already models this correctly, so
    # its fields are carried through as-is rather than flattened into a single
    # "name" that would silently present a brand+filename guess as the
    # official product name.
    listing["name_literal"] = item.get("name_literal")
    listing["name_l10n_key"] = item.get("name_l10n_key")
    listing["label"] = item.get("name_literal") or item.get("derived_label")
    listing["label_note"] = None if item.get("name_literal") else (
        "label is derived from brand + filename, NOT the game's official name -- base-game "
        "items name themselves with an l10n key whose translation is in the packed dataS.gar. "
        "Good enough to identify the machine; do not quote it as the product's real name."
    )
    listing["brand"] = item.get("brand")
    listing["category"] = item.get("category")
    listing["resolved_from"] = item.get("resolved_from")
    listing["mod_name"] = item.get("mod_name")
    listing["new_price"] = new_price

    if new_price and listed is not None:
        listing["discount_vs_new"] = round(new_price - listed, 2)
        listing["discount_pct"] = round((1 - listed / new_price) * 100, 1)
        listing["value_note"] = (
            "discount_pct is listed price against NEW price only. It is NOT a buy signal: "
            "condition above is part of the price, and repair cost is computed by the game at "
            "the workshop and is not derivable from the save. Read the discount against the "
            "wear/damage, not on its own."
        )
    else:
        listing["discount_vs_new"] = None
        listing["discount_pct"] = None
        listing["value_note"] = (
            "Resolved the item but it carries no usable store price, so no discount can be "
            "computed. UNKNOWN, not zero."
        )
    return listing


def main():
    savegame_dir = arg_or_exit("read_equipment_market.py <savegame_dir> [--config PATH] "
                               "[--install-dir DIR] [--mods-dir DIR]")
    install_dir, mods_dir, path_err = parse_path_args(sys.argv)

    raw, err = read_listings(savegame_dir)
    if err:
        emit({"error": err, "calibration_needed": True})
        return

    if path_err:
        # The listings themselves are still real and still expiring -- report
        # them unresolved rather than reporting nothing. A market we can see
        # but not price is far better than a silent empty list.
        emit({
            "file": os.path.join(savegame_dir, "sales.xml"),
            "listing_count": len(raw),
            "listings": [
                {
                    "xml_filename_raw": a.get("xmlFilename"),
                    "listed_price": to_float(a.get("price")),
                    "time_left": a.get("timeLeft"),
                    "resolved": False,
                    "resolve_error": path_err,
                }
                for a in raw
            ],
            "resolved_count": 0,
            "error": (
                f"listings were read from sales.xml but NONE could be priced: {path_err} "
                "The listings above are real; only the new-price comparison is missing."
            ),
            "calibration_needed": True,
        })
        return

    listings = [build_listing(a, install_dir, mods_dir) for a in raw]
    resolved = [l for l in listings if l.get("resolved")]

    emit({
        "file": os.path.join(savegame_dir, "sales.xml"),
        "listing_count": len(listings),
        "resolved_count": len(resolved),
        "unresolved_count": len(listings) - len(resolved),
        "unresolved_note": (
            f"{len(listings) - len(resolved)} listing(s) could not be resolved to a store item "
            "-- each carries its own resolve_error and a null new_price. They are listed, not "
            "dropped: an unpriced listing is unknown, not absent."
        ) if len(resolved) != len(listings) else None,
        "listings": listings,
        "market_note": (
            "Listings EXPIRE (each carries a timeLeft) and the set changes over time -- read "
            "this alongside save_freshness so a stale list can't send the player after a "
            "machine that is already gone."
        ),
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
