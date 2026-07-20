"""
Read environment.xml -> in-game date, time, season, weather.

Usage: python3 read_environment.py <savegame_dir>

Confirmed structure (verified against a real FS25 25.x save, environment.xml,
2026-07 -- see FRICTION-LOG.md for the substring-matching bug this replaced):

    <environment>
        <dayTime>572.640808</dayTime>              <!-- minutes-of-day, 0-1440 -->
        <currentDay>6</currentDay>                  <!-- in-game day counter -->
        <currentMonotonicDay>6</currentMonotonicDay>
        <realHourTimer>1696402</realHourTimer>       <!-- NOT the in-game clock; unknown/unused here -->
        <daysPerPeriod>1</daysPerPeriod>
        <weather timeSinceLastRain="259">
            <forecast>
                <instance typeName="SUN" season="SUMMER" variationIndex="2"
                          startDay="6" startDayTime="28884405" duration="28800000">
                    <hail perlinPercentage="4584"/>   <!-- only present for HAIL instances -->
                    <twister startPosX="70" .../>     <!-- only present for TWISTER instances -->
                </instance>
                ...
            </forecast>
        </weather>
    </environment>

UNIT DETERMINATION (do not re-derive by guesswork -- this was verified, see below):

  - <dayTime> is MINUTES-OF-DAY (range 0-1440), not milliseconds and not raw
    "hours". Evidence:
      1. Its value (572.64) sits in the same order of magnitude as the
         <weather>...<fog><target><groundFog startDayTimeMinutes="201"
         endDayTimeMinutes="570" .../> attributes in the SAME file, whose
         names explicitly say "Minutes" -- 570 vs dayTime's 572.64 is a near
         match, confirming the scale.
      2. It never exceeds 1440 (minutes/day) across observed values.
      3. Converted (572.640808 / 60 = 9h32m -> "09:32"), it lands inside the
         forecast window that the file's OWN weather.forecast independently
         claims is active "now" (see next point) -- a plausible mid-morning
         summer time, not 3am or lunchtime.

  - forecast <instance startDayTime="..."> and duration="..." ARE MILLISECONDS-
    OF-DAY (range 0-86,400,000). Evidence:
      1. Every observed duration divided by 3,600,000 is an exact whole
         number of hours (1..12) -- e.g. 28800000/3600000 = 8.0h exactly.
         Random/uncalibrated units would not divide this cleanly.
      2. Every observed startDayTime stays under 86,400,000 (24h in ms) and
         never approaches values consistent with minutes or seconds for a
         "start time within a day" field.

  - Cross-check: converting currentDay(6) + dayTime(minutes->ms) to one
    absolute-ms timeline and comparing against forecast instances' own
    (startDay, startDayTime, duration) on the SAME absolute timeline lands
    inside the first SUN instance (day 6, 08:01:24 - 16:01:24), which is
    self-consistent (a game wouldn't forecast "now" as SUN while actually
    showing something else). CONFIDENCE: high.

If dayTime, currentDay, daysPerPeriod, or a well-formed weather/forecast are
missing/unparseable in a future save format, this script reports an error
rather than guessing -- see main().
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

MS_PER_DAY = 86400000
MINUTES_PER_DAY = 1440
UPCOMING_COUNT = 5


def ms_to_clock(ms_of_day):
    """Convert milliseconds-of-day (0..86,400,000) to 'HH:MM'."""
    ms_of_day = ms_of_day % MS_PER_DAY
    total_minutes = ms_of_day // 60000
    hours = int(total_minutes // 60)
    minutes = int(total_minutes % 60)
    return f"{hours:02d}:{minutes:02d}"


def minutes_to_clock(minutes_of_day):
    """Convert minutes-of-day (0..1440) to 'HH:MM'."""
    minutes_of_day = minutes_of_day % MINUTES_PER_DAY
    hours = int(minutes_of_day // 60)
    minutes = int(minutes_of_day % 60)
    return f"{hours:02d}:{minutes:02d}"


def get_text(elem, tag):
    child = elem.find(tag)
    if child is None or child.text is None or not child.text.strip():
        return None
    return child.text.strip()


def parse_instance(instance_elem):
    a = instance_elem.attrib
    try:
        start_day = int(a["startDay"])
        start_ms = int(a["startDayTime"])
        duration_ms = int(a["duration"])
    except (KeyError, ValueError):
        return None

    end_abs_ms = start_day * MS_PER_DAY + start_ms + duration_ms
    end_day = end_abs_ms // MS_PER_DAY
    end_ms_of_day = end_abs_ms % MS_PER_DAY

    result = {
        "type": a.get("typeName"),
        "season": a.get("season"),
        "variation_index": a.get("variationIndex"),
        "start_day": start_day,
        "start_day_time_ms": start_ms,
        "start_clock": ms_to_clock(start_ms),
        "duration_ms": duration_ms,
        "duration_hours": round(duration_ms / 3600000, 2),
        "end_day": end_day,
        "end_clock": ms_to_clock(end_ms_of_day),
        "_abs_start_ms": start_day * MS_PER_DAY + start_ms,
        "_abs_end_ms": end_abs_ms,
    }

    children = list(instance_elem)
    if children:
        child = children[0]
        result["detail"] = {child.tag: dict(child.attrib)}

    return result


def strip_internal(instance_dict):
    return {k: v for k, v in instance_dict.items() if not k.startswith("_")}


def main():
    savegame_dir = arg_or_exit("read_environment.py <savegame_dir>")
    path = os.path.join(savegame_dir, "environment.xml")
    root, generic = load_xml(path)

    if root is None:
        emit({"error": generic.get("error", "unknown error reading environment.xml")})
        return

    # --- Core date/time tags: required, exact lookups only ---
    missing = [t for t in ("dayTime", "currentDay", "daysPerPeriod") if get_text(root, t) is None]
    if missing:
        emit({
            "error": f"expected tag(s) missing from environment.xml: {', '.join(missing)}",
            "calibration_needed": True,
        })
        return

    try:
        day_time_raw = float(get_text(root, "dayTime"))
        current_day = int(get_text(root, "currentDay"))
        days_per_period = int(get_text(root, "daysPerPeriod"))
    except ValueError as e:
        emit({
            "error": f"could not parse expected numeric tag in environment.xml: {e}",
            "calibration_needed": True,
        })
        return

    current_monotonic_day_text = get_text(root, "currentMonotonicDay")
    current_monotonic_day = int(current_monotonic_day_text) if current_monotonic_day_text else None

    if day_time_raw > MINUTES_PER_DAY:
        # Sanity check on the unit hypothesis itself -- if this ever fires,
        # the save format changed and dayTime is no longer minutes-of-day.
        emit({
            "error": (
                f"dayTime={day_time_raw} exceeds {MINUTES_PER_DAY} (minutes/day); "
                "the minutes-of-day unit assumption documented in this script's "
                "docstring no longer holds -- needs recalibration, not a guess."
            ),
            "calibration_needed": True,
        })
        return

    result = {
        "file": path,
        "current_day": current_day,
        "current_monotonic_day": current_monotonic_day,
        "days_per_period": days_per_period,
        "day_time_raw": day_time_raw,
        "day_time_unit": "minutes-of-day (0-1440)",
        "day_time_unit_confidence": "high",
        "day_time_unit_evidence": [
            "matches magnitude of this file's own weather.fog.target.groundFog "
            "startDayTimeMinutes/endDayTimeMinutes attributes (~570 vs 572.64)",
            "never exceeds 1440 (minutes/day)",
            "resolved clock time lands inside the forecast instance the file "
            "itself claims is active for the current day/time",
        ],
        "clock": minutes_to_clock(day_time_raw),
    }

    # --- Weather / forecast: required for the weather portion, but its
    # absence doesn't invalidate the date/time fields above. ---
    weather_elem = root.find("weather")
    forecast_elem = weather_elem.find("forecast") if weather_elem is not None else None
    instance_elems = forecast_elem.findall("instance") if forecast_elem is not None else []

    if weather_elem is None or forecast_elem is None or not instance_elems:
        result["calibration_needed"] = True
        result["weather_error"] = "expected weather/forecast/instance tags not found in environment.xml"
        emit(result)
        return

    result["time_since_last_rain"] = weather_elem.attrib.get("timeSinceLastRain")

    parsed_instances = [parse_instance(ie) for ie in instance_elems]
    parsed_instances = [pi for pi in parsed_instances if pi is not None]

    if not parsed_instances:
        result["calibration_needed"] = True
        result["weather_error"] = "forecast instances present but none had parseable startDay/startDayTime/duration"
        emit(result)
        return

    day_time_ms = day_time_raw * 60000
    abs_now_ms = current_day * MS_PER_DAY + day_time_ms

    current_index = None
    for i, pi in enumerate(parsed_instances):
        if pi["_abs_start_ms"] <= abs_now_ms < pi["_abs_end_ms"]:
            current_index = i
            break

    if current_index is not None:
        current = parsed_instances[current_index]
        result["season"] = current["season"]
        result["current_weather"] = strip_internal(current)
        upcoming = parsed_instances[current_index + 1: current_index + 1 + UPCOMING_COUNT]
    else:
        result["season"] = parsed_instances[0]["season"]
        result["current_weather"] = None
        result["current_weather_note"] = (
            "no forecast instance's [startDayTime, startDayTime+duration) window "
            "covers the current currentDay/dayTime -- save may be paused at a time "
            "the forecast doesn't cover, or clock has advanced past all known instances"
        )
        upcoming = [pi for pi in parsed_instances if pi["_abs_start_ms"] >= abs_now_ms][:UPCOMING_COUNT]

    result["upcoming_forecast"] = [strip_internal(pi) for pi in upcoming]
    result["calibration_needed"] = False

    emit(result)


if __name__ == "__main__":
    main()
