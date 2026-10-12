"""state_inventory.py -- the script inventory, as CODE (plan item 12).

WHY THIS FILE EXISTS. SKILL.md used to carry a seven-set table naming 44 of the
45 shipped scripts, plus `python3 ...` blocks telling the agent to run them.
DEC-049 (3) and DEC-131 removed that on purpose: the generator fires
automatically -- no agent, no turn, no tokens -- and the manager READS GENERATED
ARTIFACTS. He is not a script-runner with a better index; he is not a
script-runner at all. So the inventory had to leave SKILL.md, and the removal is
the deliverable rather than a side effect of one.

⚠ IT HAD TO LAND SOMEWHERE CHECKABLE. `tools/build_package.py` runs
`tests/test_skill_doc_parity.py`, which asserts every shipped script is
reachable from a doc -- the gate that exists because half this skill was once
orphaned (`reading-the-save.md` and `farm_snapshot.py` had ZERO mentions, so no
session would ever have loaded them). Stripping the table breaks that gate BY
DESIGN. Re-pointing it at hand-maintained prose (`references/data-sources.md`,
say) would have re-created exactly the drift the gate exists to catch. So the
inventory lives here, in code, and `refresh_state.py --help` RENDERS it: the
human-readable listing cannot drift from the registry, because it is generated
from it (BP-195).

⛔ AND THE REGISTRY ITSELF CAN STILL DRIFT FROM DISK -- WHICH IS THE POINT.
A registry derived by globbing `scripts/*.py` could never disagree with the
filesystem, and a gate that cannot disagree cannot fail: adding a script nothing
documents would sail through. So SETS is written out by hand and
`reconcile_with_disk()` compares it against the real directory in BOTH
directions. That comparison is the gate; this docstring is not.

TWO SENSES OF "SET", KEPT APART DELIBERATELY:
  * a SCRIPT SET (here) groups shipped scripts for the inventory that left
    SKILL.md -- what a reader would have found in that table;
  * a SOURCE SET (cache_provenance.py) is the files one domain actually reads,
    and is what the freshness and settle checks operate on.
`refresh_state.py --help` renders both, labelled, because the brief for this
item used the one word for both and a reader deserves to see which is which.
"""
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Permanent exclusions, mirroring check_skill_honesty.check_reachability's own
# ignore set. `xml_utils.py` is a shared helper no session ever invokes; a
# session runs the scripts that import it. Declared here so the two halves of
# the parity gate cannot disagree about what is in scope.
IGNORED_SCRIPTS = frozenset({"__init__.py", "xml_utils.py"})

# The inventory. Group name -> (what the group covers, scripts in it).
# Transcribed from SKILL.md's seven-set table as it stood at 256 lines, plus the
# three scripts that sat outside it (emit_farm_xml.py, sanctum_maintain.py,
# pii_scan.py) -- which is why there are eight groups here and seven there: the
# table never covered the publishing and operator tools at all.
SETS = (
    ("Position & land",
     "cash, loan, the finance ledger, land ownership/value",
     ("read_economy.py", "read_farm_ledger.py", "read_farmland_areas.py")),
    ("Fields, crops & weather",
     "crop state, growth/seed data, input/output prices, forecast",
     ("read_fields.py", "read_game_defs.py", "read_fill_prices.py",
      "read_environment.py", "read_weather.py", "project_crop_calendar.py")),
    ("Fleet & equipment",
     "owned machines, condition, resale, used market, store prices",
     ("read_vehicles.py", "read_fleet.py", "read_equipment_market.py",
      "read_sales.py", "read_store_prices.py")),
    ("Livestock & production",
     "husbandry, factories, storage contents & capacity, bales/pallets",
     ("read_livestock.py", "read_placeables.py", "read_productions.py",
      "read_production_defs.py", "read_bales_pallets.py",
      "read_storage_capability.py", "read_building_capacity.py")),
    ("Contracts & career",
     "contracts, save-wide settings, market trade signals",
     ("read_missions.py", "read_career.py", "read_prices.py")),
    ("Cache & state pipeline",
     "composing, caching, verifying and rendering the state a session reads",
     ("farm_snapshot.py", "collect_state.py", "generate_state.py",
      "read_state.py", "refresh_state.py", "state_inventory.py",
      "cache_provenance.py", "cache_layout.py", "lint_append_only.py",
      "delta_log.py", "aggregate_render.py")),
    ("Session mechanics & self-checks",
     "the bridge, onboarding, and the skill checking itself",
     ("wait_for_event.py", "notify_farm_manager.py", "read_replies.py",
      "locate_save.py", "init_sanctum.py", "check_mods.py",
      "check_sanctum_freshness.py", "check_skill_honesty.py",
      "check_fleet_alerts.py", "read_game_log.py")),
    ("Publishing & operator tools",
     "publishing figures the mod renders, the dossier reads and writes that feed "
     "them, sanctum upkeep, and the pre-publication privacy gate a HUMAN runs",
     ("emit_farm_xml.py", "emit_fields_xml.py", "emit_productions_xml.py",
      "read_field_merges.py", "record_field_merges.py", "read_field_plan.py",
      "record_field_plan.py", "sanctum_maintain.py",
      "pii_scan.py")),
)


def inventoried_scripts():
    """Every script name the registry claims, flattened. A name appearing in two
    groups is a registry defect, not a convenience -- reconcile_with_disk()
    reports it rather than silently de-duplicating it away."""
    names = []
    for _group, _covers, scripts in SETS:
        names.extend(scripts)
    return names


def _disk_scripts():
    return sorted(
        f for f in os.listdir(SCRIPTS_DIR)
        if f.endswith(".py") and f not in IGNORED_SCRIPTS
    )


def undocumented_scripts():
    """Scripts on disk that no group claims -- the orphaning defect itself.

    This is the property the build gate enforces now that SKILL.md no longer
    names the scripts. It was not hypothetical: `reading-the-save.md` and
    `farm_snapshot.py` both sat shipped with ZERO mentions, so no session would
    ever have loaded either one.

    ⚠ THE REGISTRY IS AUTHORITATIVE FOR SCRIPTS, and a SKILL.md mention no
    longer rescues one. Accepting either source would mean the gate could be
    satisfied by prose again -- and prose is what item 12 removed, precisely
    because it drifts. One place, checked against disk.
    """
    return sorted(set(_disk_scripts()) - set(inventoried_scripts()))


def registry_defects():
    """Ways the registry can be wrong that DO NOT show up as an orphan.

      * a name claimed twice -> the rendered listing prints it twice and every
        count derived from it stops meaning anything;
      * a name no file backs -> the inventory advertises something that cannot
        run, which is worse than not listing it: a caller trusts the listing.

    Kept separate from undocumented_scripts() so the two never double-count the
    same script and leave the gate reporting a total that does not reconcile.
    """
    defects = []
    seen = set()
    for name in inventoried_scripts():
        if name in seen:
            defects.append(
                "state_inventory.SETS names %s in more than one group" % name)
        seen.add(name)
    on_disk = set(_disk_scripts())
    for name in sorted(seen - on_disk):
        defects.append(
            "state_inventory.SETS names scripts/%s, which does not exist"
            % name)
    return defects


def render(width=None):
    """The inventory as text -- what `refresh_state.py --help` prints.

    Generated from SETS on every call, so the listing and the registry cannot
    disagree. Never hand-edit the output of this function into a doc: that is
    the second source of truth this whole item exists to delete.
    """
    lines = []
    total = 0
    for group, covers, scripts in SETS:
        lines.append("  %s -- %s" % (group, covers))
        for name in scripts:
            lines.append("      %s" % name)
            total += 1
        lines.append("")
    lines.append("  %d scripts in %d sets. Generated from "
                 "state_inventory.SETS; do not hand-maintain a copy."
                 % (total, len(SETS)))
    return "\n".join(lines)
