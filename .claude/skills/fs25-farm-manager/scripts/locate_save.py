"""
Find Farming Simulator 25 savegame folders on this machine, on any platform.

Usage:
    python3 locate_save.py                 # search every known location
    python3 locate_save.py <base_dir>      # search one specific base directory

Output: JSON. `searched` lists every candidate base and whether it existed, so a
"nothing found" answer can always be checked rather than taken on faith.

WHY THIS IS MORE THAN expanduser("~"):
    The original version hardcoded "~/Documents/My Games/FarmingSimulator2025" and
    offered a Mac path in its error hint. Under WSL -- Claude running in Linux while
    the game runs on Windows -- "~" is /home/<user>, so it looked in a directory that
    cannot ever contain a save, reported "base directory not found", and left the
    operator to hunt by hand. That was F-007.

    It is the same defect as the player's own notify script, which wrote its bridge
    file to /home/<user>/Documents/... while the game watched /mnt/c/Users/<user>/
    Documents/... -- os.makedirs happily created the wrong tree, the write succeeded,
    and no notification ever appeared. A path that resolves is not a path that is
    right.

PATHS (sourced 2026-07-16, not guessed -- see the skill's references):
    Windows (standard) : %USERPROFILE%\\Documents\\My Games\\FarmingSimulator2025
    Windows (MS Store) : %LOCALAPPDATA%\\Packages\\GIANTSSoftware.FarmingSimulator25PC_fa8jxm5fj0esw\\LocalCache\\Local
    macOS (standard)   : ~/Library/Application Support/FarmingSimulator2025
    macOS (App Store)  : ~/Library/Containers/FarmingSimulator2025/Data/Library/Application Support/FarmingSimulator2025
    WSL                : /mnt/<drive>/Users/<user>/Documents/My Games/FarmingSimulator2025
    OneDrive           : Documents is often redirected to .../OneDrive/Documents/...

    Two sources disagreed on the macOS folder name (FarmingSimulator25 vs
    FarmingSimulator2025). Both are probed rather than picking a side -- probing is
    free, and being wrong here means finding nothing and blaming the user.

    There is no native Linux build; a Linux hit means Proton/Wine, so the Steam
    compatdata prefixes are probed too.
"""
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

FS_DIR_NAMES = ["FarmingSimulator2025", "FarmingSimulator25"]
MS_STORE_PKG = "GIANTSSoftware.FarmingSimulator25PC_fa8jxm5fj0esw"


def is_wsl():
    if os.path.exists("/mnt/c/Users"):
        return True
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def candidate_bases():
    """Every place a save could live on this machine. Returns (bases, patterns)
    where bases is [(path, how)] and patterns is [(glob, how, n_matched)].

    Both are returned because a glob that matches nothing must still be REPORTED
    as probed. Otherwise a "nothing found" result lists only the handful of paths
    that happened to exist, and reads as "I barely looked" -- absence looking like
    data, in the one place an operator most needs to trust the search."""
    c, patterns = [], []
    home = os.path.expanduser("~")

    def add_glob(pattern, how):
        hits = sorted(glob.glob(pattern))
        patterns.append({"pattern": pattern, "how": how, "matched": len(hits)})
        for p in hits:
            c.append((p, how))

    if is_wsl():
        # The game is on Windows; we are in Linux. This is the case that was
        # missing entirely and is the whole reason for this rewrite.
        for docs in ("Documents", "OneDrive/Documents"):
            for name in FS_DIR_NAMES:
                add_glob(f"/mnt/*/Users/*/{docs}/My Games/{name}", f"WSL: Windows {docs} via /mnt")
        add_glob(f"/mnt/*/Users/*/AppData/Local/Packages/{MS_STORE_PKG}/LocalCache/Local",
                 "WSL: Windows Microsoft Store package")

    if os.name == "nt":
        userprofile = os.environ.get("USERPROFILE", home)
        localappdata = os.environ.get("LOCALAPPDATA", os.path.join(userprofile, "AppData", "Local"))
        for docs in ("Documents", os.path.join("OneDrive", "Documents")):
            for name in FS_DIR_NAMES:
                c.append((os.path.join(userprofile, docs, "My Games", name), f"Windows {docs}"))
        c.append((os.path.join(localappdata, "Packages", MS_STORE_PKG, "LocalCache", "Local"),
                  "Windows Microsoft Store package"))

    if sys.platform == "darwin":
        for name in FS_DIR_NAMES:
            c.append((os.path.join(home, "Library", "Application Support", name), "macOS standard"))
            c.append((os.path.join(home, "Library", "Containers", name, "Data", "Library",
                                   "Application Support", name), "macOS App Store (sandboxed)"))

    if sys.platform.startswith("linux") and not is_wsl():
        # No native FS25 build exists, so a hit here means Proton/Wine.
        for name in FS_DIR_NAMES:
            add_glob(os.path.join(home, ".steam", "steam", "steamapps", "compatdata", "*", "pfx",
                                  "drive_c", "users", "*", "Documents", "My Games", name),
                     "Linux: Steam Proton prefix")
            add_glob(os.path.join(home, ".wine", "drive_c", "users", "*", "Documents",
                                  "My Games", name), "Linux: Wine prefix")
        # The old default. Kept last so a genuine native/symlinked setup still works,
        # but it is NOT where a WSL user's save lives -- see the docstring.
        for name in FS_DIR_NAMES:
            c.append((os.path.join(home, "Documents", "My Games", name), "home directory (rarely correct)"))

    seen, out = set(), []
    for p, how in c:
        if p not in seen:
            seen.add(p)
            out.append((p, how))
    return out, patterns


def read_names(savegame_dir):
    """Returns (savegame_name, farm_names, error_or_None).

    These are DIFFERENT things and the old version conflated them: <savegameName>
    is what the SAVE is called ("My game save"); the FARM's name lives in farms.xml
    (<farm name="My farm">). The old code also returned the first element carrying
    any `name` attribute at all -- the same first-match trap that made
    read_environment.py report dayTime as the day (F-002).
    """
    savegame_name = None
    career = os.path.join(savegame_dir, "careerSavegame.xml")
    if os.path.isfile(career):
        try:
            root = ET.parse(career).getroot()
            node = root.find("./settings/savegameName")
            if node is None:
                node = root.find(".//savegameName")   # exact tag, not a substring
            if node is not None and node.text:
                savegame_name = node.text.strip()
        except ET.ParseError as e:
            return None, None, f"careerSavegame.xml unparseable: {e}"

    farm_names = None
    farms = os.path.join(savegame_dir, "farms.xml")
    if os.path.isfile(farms):
        try:
            root = ET.parse(farms).getroot()
            found = [{"farm_id": f.get("farmId"), "name": f.get("name")}
                     for f in root.iter("farm") if f.get("farmId")]
            farm_names = found or None
        except ET.ParseError as e:
            return savegame_name, None, f"farms.xml unparseable: {e}"

    return savegame_name, farm_names, None


def scan(base):
    out = []
    for entry in sorted(glob.glob(os.path.join(base, "savegame*"))):
        if not os.path.isdir(entry):
            continue
        savegame_name, farm_names, err = read_names(entry)
        rec = {
            "slot": os.path.basename(entry).replace("savegame", ""),
            "path": entry,
            "last_modified": datetime.fromtimestamp(os.path.getmtime(entry)).isoformat(),
            "savegame_name": savegame_name,
            "farms": farm_names,
        }
        if err:
            rec["warning"] = err
        # savegameBackup is the game's own backup copy, not a save to bind a
        # manager to. Surface it, flagged, rather than hiding or offering it.
        if rec["slot"].lower().startswith("backup"):
            rec["is_backup"] = True
            rec["note"] = "The game's own backup copy -- do not bind a manager to this."
        out.append(rec)
    return out


def main():
    if len(sys.argv) > 1:
        bases, patterns = [(sys.argv[1], "explicit argument")], []
    else:
        bases, patterns = candidate_bases()

    searched, savegames = [], []
    for base, how in bases:
        exists = os.path.isdir(base)
        searched.append({"base": base, "how": how, "exists": exists})
        if exists:
            for s in scan(base):
                s["base_dir"] = base
                savegames.append(s)

    savegames.sort(key=lambda r: r["last_modified"], reverse=True)

    result = {
        "platform": {"os_name": os.name, "sys_platform": sys.platform, "wsl": is_wsl()},
        "searched": searched,
        "patterns_probed": patterns,
        "savegame_count": len(savegames),
        "savegames": savegames,
    }

    if not savegames:
        # Absence must never look like data: say plainly that we found nothing and
        # show every place we looked, so the operator can tell "no saves" from
        # "looked in the wrong places" -- the exact ambiguity that made F-001 cost
        # three rewritten files.
        result["error"] = (
            f"No savegames found. Probed {len(patterns)} search pattern(s) and "
            f"{len(searched)} concrete location(s) -- see `patterns_probed` and `searched`. "
            "This means NOT FOUND, not 'you have no saves'. If the game is installed "
            "elsewhere, pass the base directory explicitly: "
            "locate_save.py '<path to FarmingSimulator2025>'"
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
