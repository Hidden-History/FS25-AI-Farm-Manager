"""
Read save-wide career settings and stats from careerSavegame.xml.

Usage: python3 read_career.py <savegame_dir> [--verbose]
    --verbose   Include the full ~400-entry installed-mod list and the full
                raw <settings> dump (51 keys). Omitted by default -- see
                "Output size" below.

No --farm-id for the primary data: careerSavegame.xml is save-wide, not
per-farm (contrast with read_economy.py, which is farm-scoped). One field,
`mods.used_by_fleet`, is a best-effort secondary cross-reference against
vehicles.xml filtered to farmId="1" (read_economy.py's own default) -- see
"Secondary source" below.

Primary source: careerSavegame.xml, structured as:
    <careerSavegame revision="2" valid="true">
        <settings>
            <savegameName>My game save</savegameName>
            <mapId>FS25_Montana_4X.MapMontana</mapId>
            <mapTitle>Montana Map 4x</mapTitle>
            <creationDate>2026-07-16</creationDate>
            <saveDate>2026-07-16</saveDate>
            <initialMoney>1000000</initialMoney>
            <initialLoan>0</initialLoan>
            <economicDifficulty>HARD</economicDifficulty>
            <hasInitiallyOwnedFarmlands>false</hasInitiallyOwnedFarmlands>
            <timeScale>1.000000</timeScale>
            <autoSaveInterval>5.000000</autoSaveInterval>
            <plannedDaysPerPeriod>1</plannedDaysPerPeriod>
            ... many more simple <tag>value</tag> settings (helpers, revisions,
            disaster/weed/stone toggles, etc.) ...
        </settings>
        <statistics>
            <money>88575500</money>
            <playTime>101.135475</playTime>
        </statistics>
        <mod modName="..." title="..." version="..." required="true|false" fileHash="..."/>
        ... one <mod> element per installed mod (this save: ~400+) ...
    </careerSavegame>

This file was previously UNREAD by every script in this toolkit
(`FRICTION-LOG.md` F-020). It is the only source for: the map id/title, the
difficulty the save was created at, initial money/loan (the save's
*starting* position, not current), the full installed mod list, and two
operationally important settings -- timeScale and autoSaveInterval (below).

UNIT BUG FIXED HERE, DOCUMENTED SO IT ISN'T RE-LITIGATED: <statistics><playTime>
is NOT hours despite the name reading that way -- it's MINUTES, same clock as
environment.xml's <dayTime>. An earlier version of this script emitted it
raw as "play_time_hours" and was wrong. Evidence (established 2026-07-16,
this is the toolkit's 4th unit error of the session -- see F-002 dayTime,
F-015 grep-counted plural tag, F-018 operatingTime ms-vs-seconds):
    1. Two live reads ~10 real-minutes apart gave IDENTICAL deltas to five
       decimal places on both clocks:
           dayTime:  572.640808 -> 582.049438   delta = +9.408630
           playTime:  91.726852 -> 101.135475   delta = +9.408623
       Same clock, therefore same unit -- and dayTime's unit (minutes-of-day)
       is independently established with high confidence in F-002.
    2. The physical-possibility check that should have caught it immediately:
       <creationDate>2026-07-16</creationDate> -- this save was created TODAY.
       playTime=101.135475 read as HOURS is impossible on a same-day save.
       Read as MINUTES (1.69 hours), it's an ordinary short session.
    Generalizable lesson: convert any surfaced numeric field to a human-scale
    quantity and ask "is this physically possible?" before trusting the label.

SECONDARY SOURCE (best-effort, non-fatal if unavailable): to compute
`mods.used_by_fleet`, this script also reads vehicles.xml and filters
<vehicle farmId="1">'s filename= attributes for a "$moddir$<ModName>/" prefix.
This is cheap (single extra parse, ~24 vehicles this save) and directly
useful for F-011 (store-price lookups must resolve modded vehicles into
their mod zip, not the base install -- see F-019, where a modded X9 was
wrongly compared against the base-game X9 price). If vehicles.xml is
missing or unreadable, `mods.used_by_fleet` is simply omitted with a note --
this never turns into an error or affects calibration_needed, since it's not
this script's primary promise.

Output size (FRICTION-LOG.md F-006 -- oversized parser output eats the
context window before a briefing starts): the full mod list (~400 entries)
and full raw <settings> dump (51 keys, mostly redundant with the curated
fields already returned) are gated behind --verbose. Default output is a
few KB, in line with read_economy.py / read_environment.py.

Output contract (same as read_economy.py):
    - Never returns [] / {} / a guess for missing data. If careerSavegame.xml
      is missing, or <settings>/<statistics> aren't where expected, this
      emits {"error": "..."} explaining exactly what's missing.
    - calibration_needed is true ONLY when the expected structure could not
      be confidently located -- never merely because a value is 0/false/empty.
      A save that genuinely has, say, autoSaveInterval == 0 is a valid,
      non-calibration result.

Why timeScale and autoSaveInterval matter (not just trivia):
    - timeScale is the game's fast-forward speed multiplier (1x/5x/15x/etc,
      player-controlled in-session). Planning advice like "fast-forward to
      harvest" is sound at high timeScale and useless framing at 1x -- every
      time-based recommendation this skill makes depends on knowing it.
    - autoSaveInterval (minutes) does NOT bound how stale a savegame read
      can be -- not "only while playing," not ever. CORRECTED 2026-07-16
      (FRICTION-LOG.md F-023): an earlier version of this docstring claimed
      the interval was a freshness guarantee during active play, and blamed
      an observed 19-minute write gap on the game being "paused/idle." Both
      claims were wrong, and the second was never observed -- it was
      inferred from silence and stated as fact. What actually happens:
      FS25 defers the autosave to the next safe moment (the player opening
      the map/menu), so the interval only says how often a save becomes
      DUE, not when it's written. The player was actively farming the
      entire 19 minutes; the map just hadn't been opened. A save can be
      arbitrarily old mid-session with nothing wrong and nobody idle.
      That's why this script returns `source_mtime_iso` / `source_age_seconds`
      (the actual filesystem mtime of careerSavegame.xml) as the ONLY
      honest freshness signal -- a briefing should quote that measured age
      ("as of N minutes ago") and never infer a cause (paused, idle,
      crashed) from it without independent evidence.

CAVEAT ON LIVE-UPDATE BEHAVIOR (investigated, not assumed): whether
<timeScale> in the XML reflects the player's *current* in-session speed
setting live, or only whatever speed was in effect at the moment of the
last autosave/save, was checked empirically against this save on 2026-07-16
rather than assumed. See FRICTION-LOG.md and SKILL.md's Calibration section
for what was actually observed -- this script does not claim more than what
was verified.
"""
import datetime
import os
import re
import sys
import time
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

# Settings worth surfacing individually, beyond the full settings dump.
# (tag name in XML) -> (output key)
HIGHLIGHTED_SETTINGS = {
    "savegameName": "savegame_name",
    "mapId": "map_id",
    "mapTitle": "map_title",
    "creationDate": "creation_date",
    "saveDate": "save_date",
    "initialMoney": "initial_money",
    "initialLoan": "initial_loan",
    "economicDifficulty": "economic_difficulty",
    "hasInitiallyOwnedFarmlands": "has_initially_owned_farmlands",
    "plannedDaysPerPeriod": "planned_days_per_period",
    "growthMode": "growth_mode",
}

DIFFICULTY_FLAG_SETTINGS = [
    "trafficEnabled", "stopAndGoBraking", "trailerFillLimit",
    "automaticMotorStartEnabled", "fruitDestruction", "plowingRequiredEnabled",
    "stonesEnabled", "weedsEnabled", "limeRequired", "isSnowEnabled",
    "fuelUsage", "helperBuyFuel", "helperBuySeeds", "helperBuyFertilizer",
    "helperSlurrySource", "helperManureSource", "disasterDestructionState",
]

# Filenames under $moddir$<ModName>/... reference a mod by folder name.
MODDIR_RE = re.compile(r"^\$moddir\$([^/]+)/")

# Matches read_economy.py's own default -- this cross-reference is a
# best-effort bonus, not a farm-scoped promise of this script.
FLEET_FARM_ID = "1"


def coerce(text):
    """Best-effort typed coercion of an XML text value: bool > int > float > str."""
    if text is None:
        return None
    t = text.strip()
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def find_mods_used_by_fleet(savegame_dir):
    """Best-effort: which installed mods does the player's own fleet actually use?
    Returns (set_of_mod_names, note_or_None). Never raises -- degrades to
    (set(), note) if vehicles.xml is missing/unreadable."""
    vehicles_path = os.path.join(savegame_dir, "vehicles.xml")
    v_root, v_generic = load_xml(vehicles_path)
    if v_root is None:
        return set(), f"vehicles.xml unavailable ({v_generic.get('error')}) -- fleet cross-reference skipped."

    used = set()
    for v in v_root.iter("vehicle"):
        if v.attrib.get("farmId") != FLEET_FARM_ID:
            continue
        filename = v.attrib.get("filename", "")
        m = MODDIR_RE.match(filename)
        if m:
            used.add(m.group(1))
    return used, None


def main():
    savegame_dir = arg_or_exit("read_career.py <savegame_dir> [--verbose]")
    verbose = "--verbose" in sys.argv[2:]

    path = os.path.join(savegame_dir, "careerSavegame.xml")
    root, generic = load_xml(path)

    if root is None:
        emit({
            "error": f"could not read careerSavegame.xml: {generic.get('error')}",
            "calibration_needed": True,
        })
        return

    settings_elem = root.find("settings")
    if settings_elem is None:
        emit({
            "error": (
                "careerSavegame.xml parsed but has no <settings> element -- "
                "schema may have changed."
            ),
            "calibration_needed": True,
            "generic_dump": generic,
        })
        return

    # Full settings dump: every simple <tag>text</tag> child under <settings>.
    all_settings = {}
    for child in settings_elem:
        all_settings[child.tag] = coerce(child.text)

    if "timeScale" not in all_settings or "autoSaveInterval" not in all_settings:
        emit({
            "error": (
                "<settings> found but missing 'timeScale' and/or 'autoSaveInterval' "
                "-- schema may have changed."
            ),
            "calibration_needed": True,
            "settings_found": sorted(all_settings.keys()),
        })
        return

    statistics_elem = root.find("statistics")
    if statistics_elem is None:
        emit({
            "error": (
                "careerSavegame.xml parsed but has no <statistics> element -- "
                "schema may have changed."
            ),
            "calibration_needed": True,
            "generic_dump": generic,
        })
        return
    statistics = {child.tag: coerce(child.text) for child in statistics_elem}
    if "money" not in statistics or "playTime" not in statistics:
        emit({
            "error": (
                "<statistics> found but missing 'money' and/or 'playTime' -- "
                "schema may have changed."
            ),
            "calibration_needed": True,
            "statistics_found": sorted(statistics.keys()),
        })
        return

    highlighted = {out_key: all_settings.get(xml_key) for xml_key, out_key in HIGHLIGHTED_SETTINGS.items()}
    difficulty_flags = {k: all_settings.get(k) for k in DIFFICULTY_FLAG_SETTINGS if k in all_settings}

    time_scale_raw = all_settings["timeScale"]
    autosave_interval_minutes = all_settings["autoSaveInterval"]

    mods = []
    for mod_elem in root.iter("mod"):
        a = mod_elem.attrib
        mods.append({
            "mod_name": a.get("modName"),
            "title": a.get("title"),
            "version": a.get("version"),
            "required": coerce(a.get("required")),
        })
    mods_by_name = {m["mod_name"]: m for m in mods}

    used_mod_names, fleet_note = find_mods_used_by_fleet(savegame_dir)
    used_by_fleet = [
        {
            "mod_name": name,
            "title": mods_by_name.get(name, {}).get("title"),
        }
        for name in sorted(used_mod_names)
    ]

    play_time_minutes = statistics["playTime"]

    source_mtime_epoch = os.path.getmtime(path)
    source_age_seconds = round(time.time() - source_mtime_epoch, 1)
    source_mtime_iso = datetime.datetime.fromtimestamp(source_mtime_epoch).isoformat(timespec="seconds")

    output = {
        "source": path,
        "source_mtime_iso": source_mtime_iso,
        "source_age_seconds": source_age_seconds,
        **highlighted,
        "time_scale": {
            "raw": time_scale_raw,
            "meaning": (
                "In-session fast-forward speed multiplier the player can change "
                "via the in-game UI (typical FS25 steps: 1x/5x/15x/30x/60x/120x). "
                "Higher values mean less real time per in-game day."
            ),
            "converted_to_real_time_per_in_game_day": None,
            "conversion_note": (
                "Not computed: the real-time length of one in-game day at 1x "
                "(the base 'day length' constant) is not present anywhere in this "
                "save -- checked careerSavegame.xml <settings> and environment.xml "
                "in full, neither has a dayLength/minutesPerDay-style field. "
                "Converting timeScale into a real-minutes-per-in-game-day figure "
                "would require that constant; do not guess at it. If it's ever "
                "needed, derive it empirically: sample environment.xml's <dayTime> "
                "twice with a known real-time gap between reads at a known "
                "timeScale, as was done to investigate this field on 2026-07-16 "
                "(see FRICTION-LOG.md)."
            ),
            "live_update_confirmed": None,
            "live_update_note": (
                "Investigated 2026-07-16, not conclusively confirmed either way: "
                "polled careerSavegame.xml + environment.xml mtimes every 5s for "
                "120s while the game was running and saw NO write at all in that "
                "window; separately, reads taken tens of minutes apart across the "
                "same session showed money/playTime both advancing. CORRECTED "
                "reading of that observation (FRICTION-LOG.md F-023): an earlier "
                "version of this note took the 120s silence as evidence of a fixed "
                "'autoSaveInterval cadence' governing when <settings> gets "
                "rewritten. That's not how it works -- FS25 defers the save to the "
                "next time the player opens the map/menu, not a timer, so 120s of "
                "silence proves nothing about cadence one way or the other; it may "
                "simply mean the map wasn't opened in that window. The only thing "
                "actually established: timeScale stayed at 1.0 throughout every "
                "observation, so no actual speed change was ever caught landing in "
                "the file. Whether timeScale updates the instant it's changed, or "
                "only gets written whenever <settings> next happens to be saved, "
                "remains genuinely unknown -- do not assume 'live' without watching "
                "an actual speed change land in the file."
            ),
        },
        "autosave_interval_minutes": autosave_interval_minutes,
        "freshness_note": (
            f"This file was last written {source_age_seconds:.0f}s ago "
            f"({source_mtime_iso}) -- that measured age is the only honest "
            "freshness signal this script has. autoSaveInterval "
            f"({autosave_interval_minutes} min) does NOT bound staleness: it's "
            "how often a save becomes DUE, not when it's written -- FS25 defers "
            "the actual write to the next time the player opens the map/menu, "
            "so a save can be arbitrarily older than the interval with nothing "
            "wrong and nobody idle (confirmed 2026-07-16, FRICTION-LOG.md F-023, "
            "after an earlier version of this note wrongly inferred 'the game is "
            "paused' from a long gap and stated it as fact -- don't repeat that: "
            "infer a cause for staleness only from independent evidence, never "
            "from the gap alone). Quote source_age_seconds in a briefing "
            "(\"as of N minutes ago\"); never characterize it against "
            "autoSaveInterval as if that were a ceiling."
        ),
        "statistics": {
            "money": statistics["money"],
            "money_note": (
                "This 'money' is careerSavegame.xml's own snapshot, NOT the "
                "authoritative source -- that's farms.xml (read_economy.py). "
                "Observed 2026-07-16: the two differed by a few dollars at the "
                "same moment (both actively drifting downward from ongoing "
                "small expenses while the game ran), consistent with autosave "
                "writing multiple files in the same batch a beat apart rather "
                "than atomically. Use this field only to sanity-check "
                "read_economy.py's number is in the same ballpark, never as "
                "the cash figure itself."
            ),
            "play_time_minutes": play_time_minutes,
            "play_time_hours": round(play_time_minutes / 60, 4),
            "play_time_note": (
                "play_time_hours is DERIVED (play_time_minutes / 60), not a "
                "separate field in the XML -- the raw <playTime> tag is minutes, "
                "not hours, despite its name. See this script's docstring for "
                "the unit evidence (matches environment.xml's <dayTime> clock "
                "delta-for-delta, and creationDate is today's date, making a "
                "100+-hour reading physically impossible)."
            ),
        },
        "difficulty_flags": difficulty_flags,
        "mods": {
            "count": len(mods),
            "required_count": sum(1 for m in mods if m["required"] is True),
            "required": [m for m in mods if m["required"] is True],
            "used_by_fleet": used_by_fleet,
            "used_by_fleet_note": fleet_note or (
                f"Cross-referenced against vehicles.xml, farmId=\"{FLEET_FARM_ID}\" "
                "(matches read_economy.py's default farm). Best-effort, not "
                "farm-id-configurable yet -- if this farm ever needs a different "
                "id, extend this the same way read_economy.py added --farm-id."
            ),
        },
        "calibration_needed": False,
    }

    if verbose:
        output["mods"]["list"] = mods
        output["all_settings"] = all_settings
    else:
        output["_verbose_note"] = (
            "Full mod list (406 entries) and raw <settings> dump (51 keys) "
            "omitted by default to keep output small (FRICTION-LOG.md F-006) "
            "-- rerun with --verbose for both."
        )

    emit(output)


if __name__ == "__main__":
    main()
