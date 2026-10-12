# Field merges: NOT YET ASSESSED

This farm has not been assessed for **merged fields** — two or more savegame
parcels the player works as one field.

While this file is here, `read_field_merges.py` refuses rather than reporting
`count: 0`, because an empty dossier directory is a fact about this sanctum and
not about the savegame. Publishing that zero reports a merged field at the
area of just one of its parcels.

**Do not delete this file by hand.** Ask the player the merged-fields question
(onboarding O3) and record the answer with the script, which clears this marker
only after the answer reads back cleanly — including when the answer is "no
merged fields":

    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_merges.py" sanctum/state/field-dossiers --none
    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_merges.py" sanctum/state/field-dossiers --config sanctum/config.json --merge <CANONICAL> <OTHER_ID> [...]
