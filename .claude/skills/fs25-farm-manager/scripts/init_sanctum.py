"""
Create the sanctum/ folder skeleton inside the current Claude Code project
directory. Idempotent on a fresh dir or an already-tiered sanctum -- safe to
re-run, it skips pieces that already exist. It REFUSES on a pre-D4 flat-layout
sanctum (content .md files at the sanctum root): that is a real farm's memory,
and seeding blank tiered templates alongside it would strand that data. Migrate
such a farm with Lane B's `sanctum_maintain reconcile` first.

Usage: python3 init_sanctum.py <project_dir>

WHY THIS COPIES templates/ INSTEAD OF WRITING STRINGS:
    This script used to inline its own one-line placeholders ("_Populated after
    first session start._"). That duplicated templates/ and then silently rotted
    away from it. The placeholders were not merely thin -- they were WRONG:

      - the finances-ledger placeholder shipped a single "Cash" column, with no
        way to distinguish a derived figure from the game's own and no debt
        column at all;
      - the field-price-watchlist placeholder said prices are "not saved data --
        has to come from you", which is false. Store prices and per-hectare rates
        are readable from the install and mod files. Only parcel AREA genuinely
        has to be asked for.

    So a fresh init wrote a farm's memory pre-loaded with the exact claims this
    skill's references exist to disprove. Two sources of truth is one too many:
    templates/ is now the only one, and a missing template is a loud error rather
    than a quiet fallback to a stale string. That fallback is how the gap reopens.
"""
import os
import sys
import json

# D4 sanctum reorg: load tier is legible from the path. identity/ holds
# creed + decision-making (Tier A, check-only) AND directives (load-tier B,
# mutated and live-probed by check_sanctum_freshness.probe_directive_premises);
# state/ (durable farm facts: registers + dossiers), history/ (append-only +
# all cold archives under history/archive/). config.json stays at the sanctum
# root -- it is the binding every parser resolves, not a tier-scoped content file.
SKELETON_DIRS = [
    "sanctum",
    "sanctum/identity",
    "sanctum/state",
    "sanctum/state/field-dossiers",
    "sanctum/state/husbandry-dossiers",
    "sanctum/state/production-dossiers",
    "sanctum/history",
    "sanctum/history/journal",
    "sanctum/history/archive",
]

# sanctum path -> template filename. Every entry here MUST have a template;
# see TEMPLATES_DIR resolution and the hard error below.
TEMPLATE_FILES = {
    "sanctum/identity/directives.md": "directives.md",
    "sanctum/state/equipment-roster.md": "equipment-roster.md",
    "sanctum/history/closeout-latest.md": "closeout-latest.md",
    "sanctum/state/finances-ledger.md": "finances-ledger.md",
    "sanctum/state/husbandry-roster.md": "husbandry-roster.md",
    "sanctum/state/equipment-shopping-list.md": "equipment-shopping-list.md",
    "sanctum/state/production-roster.md": "production-roster.md",
    "sanctum/state/field-price-watchlist.md": "field-price-watchlist.md",
    # Farm-wide state files (D8, Family 1). Seeded like the rosters -- singular per
    # farm, start empty-but-honest. Per-entity dossiers (field/husbandry/production)
    # stay on-demand and are NOT seeded here.
    "sanctum/state/contracts.md": "contracts.md",
    "sanctum/state/storage-capability.md": "storage-capability.md",
    "sanctum/state/crop-grace-periods.md": "crop-grace-periods.md",
    # The standing defect list, appended every closeout (references/sanctum-upkeep.md).
    # Added 2026-07-16: the skill cited 25 friction IDs (F-001..F-036) across SKILL.md, its
    # references and script docstrings while shipping no log and no template -- every one of
    # those citations was a dead reference, so the bugs they describe were unreadable to the
    # sessions that needed them most. Seeded here so a new farm starts with the file rather
    # than inventing one at its first closeout.
    "sanctum/history/friction-log.md": "friction-log.md",
    # The journal index (F4) -- one row per session, appended each closeout. Seeded
    # empty so the first closeout has an INDEX to append to. The per-session journal
    # files themselves are produced at closeout, not seed-templated.
    "sanctum/history/journal/INDEX.md": "journal/INDEX.md",
}

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: init_sanctum.py <project_dir>"}))
        sys.exit(1)
    project_dir = sys.argv[1]

    templates_dir = os.path.normpath(TEMPLATES_DIR)
    if not os.path.isdir(templates_dir):
        print(json.dumps({
            "error": f"templates directory not found: {templates_dir}",
            "detail": "init_sanctum.py copies sanctum files from the skill's templates/. "
                      "Without it there is nothing to copy -- refusing to fall back to "
                      "inline placeholder strings, which is how this drifted out of sync "
                      "and started shipping false claims.",
        }))
        sys.exit(1)

    # Refuse to seed over a pre-D4 FLAT-layout sanctum. The tiered layout keeps
    # NO .md files at the sanctum root -- every content file lives under
    # identity/ state/ history/. So a .md directly under sanctum/ means a real
    # farm's memory written in the old flat layout. Seeding blank tiered
    # templates alongside it would strand that data (the parsers now read the
    # tiered paths, so the farm would read as empty). Migration is Lane B's job.
    # Guard runs BEFORE any dir/file is created, so a refusal changes nothing.
    sanctum_root = os.path.join(project_dir, "sanctum")
    if os.path.isdir(sanctum_root):
        flat_files = sorted(
            f for f in os.listdir(sanctum_root)
            if f.endswith(".md") and os.path.isfile(os.path.join(sanctum_root, f))
        )
        if flat_files:
            print(json.dumps({
                "error": "flat-layout sanctum detected -- refusing to seed over existing farm data.",
                "flat_files": flat_files,
                "detail": "This sanctum has content files at its root (the pre-D4 flat layout), "
                          "i.e. a real farm's memory. init_sanctum will NOT seed blank tiered "
                          "templates over it -- that would strand the farm's data, since the "
                          "parsers now read identity/ state/ history/. Migrate this farm to the "
                          "tiered layout with Lane B's `sanctum_maintain reconcile` first.",
            }, indent=2))
            sys.exit(1)

    created = []
    for d in SKELETON_DIRS:
        full = os.path.join(project_dir, d)
        if not os.path.isdir(full):
            os.makedirs(full)
            created.append(full)

    missing_templates = []
    for rel_path, template_name in TEMPLATE_FILES.items():
        src = os.path.join(templates_dir, template_name)
        if not os.path.isfile(src):
            # Loud, not silent. A missing template means the skill is incomplete;
            # writing *something* anyway is what created the drift in the first place.
            missing_templates.append({"sanctum_file": rel_path, "expected_template": src})
            continue
        full = os.path.join(project_dir, rel_path)
        if not os.path.isfile(full):
            with open(src, "r", encoding="utf-8") as f:
                content = f.read()
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            created.append(full)

    if missing_templates:
        print(json.dumps({
            "error": f"{len(missing_templates)} sanctum file(s) have no template -- "
                     "the skill is incomplete and the sanctum was only partially created.",
            "missing_templates": missing_templates,
            "created_before_failing": created,
            "detail": "Fix by adding the template(s). This script will NOT invent placeholder "
                      "content to paper over it.",
        }, indent=2))
        sys.exit(1)

    config_path = os.path.join(project_dir, "sanctum", "config.json")
    config_exists = os.path.isfile(config_path)

    print(json.dumps({
        "project_dir": project_dir,
        "created": created,
        "config_exists": config_exists,
        "next_step": "write sanctum/config.json (savegame binding) and sanctum/identity/creed.md if not present"
                      if not config_exists else "sanctum already configured, proceed to session start",
    }, indent=2))


if __name__ == "__main__":
    main()
