"""
Validate a mod zip's structure: the zip itself, its modDesc.xml, and the
files modDesc.xml promises (icon, extraSourceFiles).

Usage: python3 check_mods.py <mod_zip_or_mods_dir> [--mod NAME]
    <mod_zip_or_mods_dir>  A single .zip -> one report. A directory -> every
                           top-level .zip in it (a mods dir scan).
    --mod NAME             In directory mode, check only the mod(s) whose
                           zip basename contains NAME (case-insensitive).

WHY THIS EXISTS (F-122): a structurally broken mod fails silently from the
player's point of view -- the game logs one line and moves on (the real
install's log shows exactly that: "Error: Failed to open xml file
'.../FS25_Yurg_Custom_Pack/modDesc.xml'" and the mod simply never appears
in-game). This validator answers "is this mod's structure sound?" BEFORE a
3-hour session discovers it wasn't, and pairs with read_game_log.py, which
reports the failures the game has already recorded.

SCOPE -- STRUCTURE ONLY, PURE PYTHON. Checks are stdlib zipfile + ElementTree
existence/well-formedness checks. No Lua is executed or parsed, ever (script
CONTENT validation is a different, heavier concern). A mod can pass every
check here and still be broken in-game. A FAILED check is a real structural
defect, but not always a load failure -- the game's parser is laxer than
strict XML (verified on the real install: a modDesc with a leading blank
line before its XML declaration, and one with no <title>, both still appear
in the game's Available-mod list). Only a missing/unopenable modDesc.xml is
a VERIFIED cannot-load (the game's log says so in as many words). For the
game's actual per-mod verdict, cross-check read_game_log.py. Folder-mods
(unzipped directories in a mods dir) are LISTED but not validated -- only
their modDesc.xml presence is noted.

The checks, per zip:
    zip_opens           the file is a readable zip archive
    moddesc_present     modDesc.xml exists AT THE ZIP ROOT (the game requires
                        the root -- a nested Folder/modDesc.xml is a classic
                        re-zipped-the-folder packaging mistake and is called
                        out by name when detected). Checked case-insensitively
                        at the root: a root-level 'moddesc.xml' passes with a
                        case_mismatch note, like the icon check.
    moddesc_parses      modDesc.xml is well-formed XML with a <modDesc> root
    desc_version        descVersion attribute present and a positive integer
    version             <version> present and dotted-numeric (FS convention
                        is 4-part, e.g. 1.0.0.0; fewer parts is reported as
                        a note, not a failure)
    icon                <iconFilename> declared and RESOLVABLE in the zip the
                        way the ENGINE resolves it: exact match first, then
                        the .png->.dds substitution (GIANTS' packaging
                        pipeline converts icons to .dds while modDesc keeps
                        declaring the .png -- verified against the real mods
                        dir, where ~190 working, in-game-loaded mods declare
                        a .png and ship only the .dds; flagging those would
                        be a plausible-but-wrong "broken mod" verdict), then
                        case-insensitive with a case_mismatch note. A
                        '$'-prefixed value points outside the zip (game data)
                        and is noted, not checked.
    extra_source_files  every <extraSourceFiles><sourceFile filename=...>
                        entry exists in the zip (missing ones listed by name)
    title               <title> present with a non-empty text/<en> (reported;
                        absence is an issue -- the game shows nameless mods
                        as blank entries)

Output contract (toolkit norm):
    - Never a guess, never a silent pass: every check reports ok true/false
      plus the detail it saw; a check that could not run (zip unreadable)
      reports skipped, not ok.
    - status is "ok" only if every runnable check passed; otherwise "issues",
      with each issue named in plain words.
    - Bad input (path missing, no zips found) -> {"error": ...}.
READ-ONLY: never writes to a mod file or the mods dir.
"""
import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import emit

VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


class ToolkitArgumentParser(argparse.ArgumentParser):
    """Failures keep the toolkit's machine contract (structured JSON on
    stdout, exit 1); --help stays argparse-native. Same pattern as
    read_farmland_areas.py / read_game_log.py."""

    def error(self, message):
        emit({
            "error": f"{message} ({self.format_usage().strip()})",
            "calibration_needed": False,
        })
        sys.exit(1)


def parse_args(argv):
    parser = ToolkitArgumentParser(
        prog="check_mods.py",
        description="Validate mod zip structure: zip integrity, modDesc.xml, "
                    "declared icon and extraSourceFiles. Pure structure -- "
                    "no Lua execution.",
    )
    parser.add_argument("target", metavar="mod_zip_or_mods_dir",
                        help="a single mod .zip, or a mods directory to scan")
    parser.add_argument("--mod", default=None, metavar="NAME",
                        help="directory mode: only check zips whose basename "
                             "contains NAME (case-insensitive)")
    return parser.parse_args(argv[1:])


def check_one_zip(zip_path):
    """Run every runnable structural check on one mod zip. Returns the
    per-mod report dict. Never raises for a defective mod -- defects are
    the findings, not exceptions."""
    mod_name = os.path.splitext(os.path.basename(zip_path))[0]
    checks = {}
    issues = []

    def fail(check, detail, issue):
        checks[check] = {"ok": False, **detail}
        issues.append(issue)

    def skip_rest(*names):
        for n in names:
            checks[n] = {"skipped": True,
                         "note": "not checked -- a prerequisite check failed"}

    report = {"mod": mod_name, "zip": zip_path, "checks": checks, "issues": issues}

    try:
        zf = zipfile.ZipFile(zip_path)
        namelist = zf.namelist()
        checks["zip_opens"] = {"ok": True, "entries": len(namelist)}
    except (zipfile.BadZipFile, OSError) as e:
        fail("zip_opens", {"detail": str(e)}, f"not a readable zip archive: {e}")
        skip_rest("moddesc_present", "moddesc_parses", "desc_version",
                  "version", "icon", "extra_source_files", "title")
        report["status"] = "issues"
        return report

    # -- modDesc.xml at the zip root ------------------------------------------
    # Root presence is checked case-insensitively (mirroring the icon check):
    # a root-level 'moddesc.xml' IS at the root -- only its case is off -- and
    # must not be mis-called a nesting mistake.
    moddesc_name = None
    if "modDesc.xml" in namelist:
        moddesc_name = "modDesc.xml"
        checks["moddesc_present"] = {"ok": True}
    else:
        root_case = next((n for n in namelist
                          if "/" not in n and n.lower() == "moddesc.xml"), None)
        if root_case is not None:
            moddesc_name = root_case
            checks["moddesc_present"] = {
                "ok": True, "found": root_case, "case_mismatch": True,
                "note": "present at the zip root but named "
                        f"{root_case!r}, not 'modDesc.xml' -- found only by "
                        "case-insensitive match; tolerated on Windows, may "
                        "fail elsewhere",
            }
    if moddesc_name is None:
        nested = [n for n in namelist if n.lower().endswith("moddesc.xml")]
        if nested:
            fail("moddesc_present", {"nested_at": nested},
                 f"modDesc.xml exists only at {nested} -- FS25 requires it at "
                 "the zip ROOT (classic re-zipped-the-folder packaging mistake)")
        else:
            fail("moddesc_present", {},
                 "no modDesc.xml anywhere in the zip -- the game cannot load this mod")
        skip_rest("moddesc_parses", "desc_version", "version", "icon",
                  "extra_source_files", "title")
        report["status"] = "issues"
        return report

    try:
        moddesc_bytes = zf.read(moddesc_name)
    except Exception as e:
        # A valid central directory can still hold an unreadable member --
        # zf.read() raises where namelist() succeeded, and the exception class
        # varies with the defect: BadZipFile ("Bad CRC-32") for a stored
        # member, zlib.error for corrupt deflated data (verified by corrupting
        # a copy of a real mod), NotImplementedError for a corrupt/unsupported
        # compression method, RuntimeError for an encrypted member. Enumerating
        # those classes proved fragile (two rounds each missed some), so this
        # is a deliberate catch-all backstop: whatever the class, an unreadable
        # modDesc.xml is a defective mod and must be a finding, not an
        # exception (in dir-scan mode one corrupt mod must not kill the scan).
        fail("moddesc_parses", {"detail": str(e)},
             f"modDesc.xml exists in the zip but its data is corrupt and "
             f"cannot be read: {e} -- the game cannot load this mod")
        skip_rest("desc_version", "version", "icon", "extra_source_files", "title")
        report["status"] = "issues"
        return report

    try:
        root = ET.fromstring(moddesc_bytes)
        if root.tag != "modDesc":
            fail("moddesc_parses", {"root_tag": root.tag},
                 f"modDesc.xml root element is <{root.tag}>, expected <modDesc>")
            root = None
        else:
            checks["moddesc_parses"] = {"ok": True}
    except ET.ParseError as e:
        fail("moddesc_parses", {"detail": str(e)},
             f"modDesc.xml is not well-formed XML: {e} -- a real defect, but "
             "the game's laxer parser may still tolerate it; check "
             "read_game_log.py for the game's actual verdict")
        root = None
    if root is None:
        skip_rest("desc_version", "version", "icon", "extra_source_files", "title")
        report["status"] = "issues"
        return report

    # -- descVersion ----------------------------------------------------------
    dv = root.attrib.get("descVersion")
    if dv is None:
        fail("desc_version", {}, "modDesc has no descVersion attribute")
    else:
        try:
            dv_int = int(dv)
            if dv_int >= 1:
                checks["desc_version"] = {"ok": True, "value": dv_int}
            else:
                fail("desc_version", {"value": dv},
                     f"descVersion {dv!r} is not a positive integer")
        except ValueError:
            fail("desc_version", {"value": dv},
                 f"descVersion {dv!r} is not an integer")

    # -- <version> ------------------------------------------------------------
    v_elem = root.find("version")
    version = (v_elem.text or "").strip() if v_elem is not None else None
    if not version:
        fail("version", {}, "modDesc has no <version> (or it is empty)")
    elif not VERSION_RE.match(version):
        fail("version", {"value": version},
             f"<version> {version!r} is not dotted-numeric (expected e.g. 1.0.0.0)")
    else:
        entry = {"ok": True, "value": version}
        if version.count(".") != 3:
            entry["note"] = ("FS convention is a 4-part version (e.g. 1.0.0.0); "
                             f"{version!r} has {version.count('.') + 1} part(s). "
                             "Reported, not failed.")
        checks["version"] = entry

    # -- icon -----------------------------------------------------------------
    icon_elem = root.find("iconFilename")
    icon = (icon_elem.text or "").strip() if icon_elem is not None else None
    if not icon:
        fail("icon", {}, "modDesc has no <iconFilename> (or it is empty)")
    elif icon.startswith("$"):
        checks["icon"] = {"ok": True, "declared": icon,
                          "note": "references game data outside the zip -- "
                                  "existence not checkable here"}
    elif icon in namelist:
        checks["icon"] = {"ok": True, "declared": icon, "found": icon}
    else:
        # Resolution in the documented precedence order (exact was tried
        # above): .png->.dds substitution first -- the GIANTS packaging
        # pipeline converts icons to .dds while modDesc keeps declaring the
        # .png -- then case-insensitive as the last resort.
        lower_map = {n.lower(): n for n in namelist}
        dds_candidate = (icon[:-4] + ".dds"
                         if icon.lower().endswith(".png") else None)
        found = dds_sub = case_mm = None
        if dds_candidate is not None and dds_candidate in namelist:
            found, dds_sub, case_mm = dds_candidate, True, False
        elif icon.lower() in lower_map:
            found, dds_sub, case_mm = lower_map[icon.lower()], False, True
        elif dds_candidate is not None and dds_candidate.lower() in lower_map:
            found, dds_sub, case_mm = lower_map[dds_candidate.lower()], True, True
        if found is None:
            fail("icon", {"declared": icon},
                 f"declared icon {icon!r} does not exist in the zip "
                 "(neither as declared nor as its .dds-converted form)")
        else:
            entry = {"ok": True, "declared": icon, "found": found}
            notes = []
            if dds_sub:
                entry["dds_substitution"] = True
                notes.append("declared as .png, shipped as the .dds the "
                             "GIANTS packaging pipeline produces -- the "
                             "engine resolves this; valid, not a defect")
            if case_mm:
                entry["case_mismatch"] = True
                notes.append("found only by case-insensitive match -- "
                             "tolerated on Windows, may fail elsewhere")
            entry["note"] = "; ".join(notes)
            checks["icon"] = entry

    # -- extraSourceFiles -----------------------------------------------------
    declared = [sf.attrib.get("filename")
                for sf in root.findall("./extraSourceFiles/sourceFile")
                if sf.attrib.get("filename")]
    missing = [f for f in declared if f not in namelist]
    if missing:
        fail("extra_source_files",
             {"declared_count": len(declared), "missing": missing},
             f"declared extraSourceFiles missing from the zip: {missing}")
    else:
        checks["extra_source_files"] = {"ok": True, "declared_count": len(declared)}

    # -- title ----------------------------------------------------------------
    title_elem = root.find("title")
    title = None
    if title_elem is not None:
        en = title_elem.find("en")
        if en is not None and (en.text or "").strip():
            title = en.text.strip()
        elif (title_elem.text or "").strip():
            title = title_elem.text.strip()
    if title:
        checks["title"] = {"ok": True, "value": title}
    else:
        fail("title", {}, "modDesc has no non-empty <title> -- the game would "
                          "show this mod as a blank entry")

    report["status"] = "ok" if not issues else "issues"
    return report


def main():
    ns = parse_args(sys.argv)
    target = ns.target

    if os.path.isfile(target):
        emit(check_one_zip(target))
        return

    if os.path.isdir(target):
        entries = sorted(os.listdir(target))
        zips = [e for e in entries if e.lower().endswith(".zip")]
        unpacked_dirs = [e for e in entries
                         if os.path.isdir(os.path.join(target, e))]
        if ns.mod:
            zips = [z for z in zips if ns.mod.lower() in z.lower()]
        if not zips:
            emit({
                "error": (
                    f"no matching .zip files in {target}"
                    + (f" for --mod {ns.mod!r}" if ns.mod else "")
                    + f" ({len(entries)} directory entries present)"
                ),
                "calibration_needed": False,
            })
            return
        reports = [check_one_zip(os.path.join(target, z)) for z in zips]
        emit({
            "mods_dir": target,
            "checked": len(reports),
            "ok_count": sum(1 for r in reports if r["status"] == "ok"),
            "issues_count": sum(1 for r in reports if r["status"] == "issues"),
            "unpacked_dirs": [
                {
                    "name": d,
                    "has_moddesc": os.path.isfile(os.path.join(target, d, "modDesc.xml")),
                    "note": "folder-mod: listed only, NOT validated (zip scope); "
                            "read_game_log.py reports its actual load failures",
                }
                for d in unpacked_dirs
            ],
            "mods": reports,
            "calibration_needed": False,
        })
        return

    emit({
        "error": f"{target} is neither a file nor a directory",
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
