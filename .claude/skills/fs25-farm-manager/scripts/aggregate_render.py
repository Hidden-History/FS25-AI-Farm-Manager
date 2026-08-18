"""The aggregate renderer and its in-process claims manifest (plan item 9, § 9).

⚠ BY DEC-048 ⑤ THIS IS THE HIGHEST-RISK COMPONENT IN THE DESIGN, NOT THE
SIMPLEST. RSK-007: *an aggregator destroys the evidence its own components
produced.* BUG-012 is the live instance -- `farm_snapshot.py` emitted, in one
dict literal, `ownership_cross_check_matches_fieldPurchase: false` and, beside
it, an unconditional note saying the land cost "matches". The parsers underneath
were honest; the summary layer overwrote them. And the consumer is a language
model, for which PROSE OUTRANKS A BOOLEAN: a manager agent acts on the sentence
and never notices the adjacent snake_case flag.

THREE MECHANISMS, and the first is the one that makes the other two possible.

  1. NO AUTHORED PROSE AT ALL. This module writes no sentences about the farm.
     Every string it emits is either a structural label or a value copied from
     the cache. That is not a style preference -- it is what makes BUG-012
     structurally impossible here rather than merely fixed: there is no sentence
     available to contradict a field. A renderer that "explains" a figure is a
     renderer that can explain it wrongly.
  2. A CLAIMS MANIFEST BUILT IN-PROCESS, NEVER PERSISTED, AND VALIDATED BEFORE A
     SINGLE LINE IS EMITTED. Every figure rendered is registered as a claim
     naming the cache file and the json_path it came from, and each claim is
     re-resolved against the file on disk and compared. A mismatch yields
     `{"error": "CLAIM UNRESOLVED: ..."}` and NO VIEW. Validation happens first
     precisely so a bad figure is never emitted and then corrected.
  3. THE BUG-012 REGRESSION, named for its id, in
     tests/test_item9_aggregate_render.py.

NEVER PERSISTED, GENERATED WHOLESALE, FLAT AND ONE LEVEL (§ 9.5, ruled by
William 2026-08-01d and independently required by DEC-048 ①). A persisted
aggregate is a second copy of the truth that can drift from the first; this one
lives exactly as long as the process that printed it.

PER-DOMAIN STATUS IS THE ENVELOPE'S OWN (§ 6.3.3), NOT RE-DERIVED HERE. A
renderer that recomputed a domain's status would be a second opinion competing
with the parser's, and the parser is the one that read the file.

A FAILED SECTION RENDERS MORE PROMINENTLY, NOT LESS. Degraded domains are listed
first, at the top, before any healthy figure -- the opposite of the instinct to
tuck a problem under a summary.

SIZE: SUMMARISE WITH AN EXPLICIT POINTER, NEVER TRUNCATE SILENTLY (§ 9.4). A
long list is replaced by a count and the path to read it at, so the reader knows
something was elided and where to find it.

⚠ G-2 -- THE HEADER'S SOURCE IS SPECIFIED HERE BECAUSE THE SPEC DID NOT. § 9.1's
worked example renders a name that, measured against the live config, matches
NEITHER `farm_name` NOR `map`: it is the SANCTUM DIRECTORY NAME -- the one
candidate of the three that is a filesystem accident rather than a datum. A
builder copying that line ships a header derived from a directory. Here the
header is `farm_name` + the resolved `farm_id`, both from config, and a
placeholder `farm_name` is a structured error rather than a string to render.

(The example's actual text is deliberately NOT quoted here. Check (b) of the
public-release gate scans raw text, comments included, precisely because a
machine-local name in a comment still ships to every player -- and this file
would otherwise be the first thing that gate catches. It was. The gate is right:
one player's farm and map names have no business in a shipped artifact, not even
as an illustration of why they should not be.)

`farm_id` arrives here ALREADY RESOLVED, by cache_layout.resolve_farm_id(). This
module never reads it from config and never defaults it.
"""
import json
import os

# A list longer than this is summarised with a pointer, never silently cut.
MAX_INLINE_ITEMS = 5

# Values a config may carry meaning "not answered". Rendering one would put a
# template placeholder in front of a player as though it were their farm's name.
PLACEHOLDER_MARKERS = ("{{", "}}")


def _is_placeholder(value):
    text = str(value or "").strip()
    if not text or text.lower() in ("unknown", "none", "null"):
        return True
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


def resolve_json_path(document, path):
    """Resolve a dotted path. Returns (value, True) or (None, False).

    Deliberately tiny and dependency-free: the claims manifest's whole value is
    that its paths are re-resolved against the file on disk, so the resolver
    must not be able to "helpfully" find something the path did not name.
    """
    node = document
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None, False
    return node, True


def _claimable(value):
    """Only scalars are claims. A container's identity is not a figure, and
    claiming one would let a whole subtree change while the claim still
    'resolved'."""
    return isinstance(value, (str, int, float, bool)) or value is None


def build_header(config, farm_id):
    """G-2. Returns (header, None) or (None, error)."""
    farm_name = config.get("farm_name")
    if _is_placeholder(farm_name):
        return None, (
            "FARM NAME NOT SET: config.json's farm_name is %r. Refusing to "
            "render a header from a placeholder -- and refusing to fall back to "
            "the sanctum directory name, which is a filesystem accident rather "
            "than a datum (gap G-2)." % (farm_name,))
    return {"farm_name": farm_name, "farm_id": farm_id}, None


def summarise(value, pointer):
    """§ 9.4. A long list becomes a count plus where to read it. Never a silent
    truncation: the reader must be able to tell that something was elided."""
    if isinstance(value, list) and len(value) > MAX_INLINE_ITEMS:
        return {
            "_elided": True,
            "item_count": len(value),
            "shown": value[:MAX_INLINE_ITEMS],
            "read_the_rest_at": pointer,
            "note": "%d items elided, not truncated -- the full list is at the "
                    "path above." % (len(value) - MAX_INLINE_ITEMS),
        }
    return value


def render(view_sections, records, config, farm_id, cache_root):
    """Build the aggregate and its claims manifest.

    Returns (rendered, claims, None) or (None, None, error). NOTHING is emitted
    when an error is returned -- the caller must not print a partial view.
    """
    header, err = build_header(config, farm_id)
    if err:
        return None, None, err

    claims = []
    domains = {}

    for domain in sorted(view_sections):
        entry = view_sections[domain]
        record = records.get(domain) or {}
        envelope = record.get("envelope") or {}
        source = os.path.join(cache_root, "domains", domain + ".json")

        declared = envelope.get("sections")
        rendered_sections = {}
        if isinstance(declared, dict):
            for name in sorted(declared):
                section = declared[name] or {}
                if not isinstance(section, dict):
                    return None, None, (
                        "RENDER ERROR: %s.sections.%s is not an object" % (domain, name))
                fields = {}
                for key in sorted(section):
                    value = section[key]
                    path = "envelope.sections.%s.%s" % (name, key)
                    if _claimable(value):
                        claims.append({
                            "claim_id": "%s.%s.%s" % (domain, name, key),
                            "value": value,
                            "source": source,
                            "json_path": path,
                        })
                        fields[key] = value
                    else:
                        fields[key] = summarise(value, "%s :: %s" % (source, path))
                rendered_sections[name] = fields

        domains[domain] = {
            "domain": domain,
            # § 6.3.3 -- the envelope's own status, never re-derived here.
            "status": entry.get("status"),
            "reason": entry.get("reason"),
            "envelope_status": envelope.get("status"),
            "provenance": entry.get("provenance"),
            "verification": entry.get("verification"),
            "sections": rendered_sections,
            "declared_section_count": len(declared) if isinstance(declared, dict) else 0,
        }

        # A missing DECLARED section is a hard render error (§ 9).
        if isinstance(declared, dict) and set(rendered_sections) != set(declared):
            missing = sorted(set(declared) - set(rendered_sections))
            return None, None, (
                "RENDER ERROR: %s declared section(s) %s and the render dropped "
                "them. A section that vanishes between the cache and the view is "
                "the aggregator destroying its components' evidence."
                % (domain, ", ".join(missing)))

    degraded = sorted(d for d, e in domains.items() if e["status"] != "ok")
    rendered = {
        "header": header,
        # Degraded FIRST, before any healthy figure. A failed section renders
        # more prominently, not less.
        "degraded_domains": [domains[d] for d in degraded],
        "domains": domains,
        "domains_rendered": len(domains),
        "coverage": {
            "domains_in_this_view": len(domains),
            "note": "This view is complete over the %d cached domain(s) and says "
                    "NOTHING about any domain the cache layer does not yet "
                    "generate. That is an elision, not completeness."
                    % len(domains),
        },
    }
    return rendered, claims, None


def validate_claims(claims, cache_root):
    """Re-resolve every claim against the file on disk. Returns None or an error.

    ⚠ THIS RUNS BEFORE A SINGLE LINE IS EMITTED. A figure validated after
    printing is a figure that was already believed.

    EVERY claim is checked, not a sample -- the same hole DEC-077's rule 1
    closes one layer up. A validator that stopped at the first claim would let
    every later figure drift freely.
    """
    cache = {}
    for claim in claims:
        source = claim["source"]
        if source not in cache:
            if not os.path.isfile(source):
                return ("CLAIM UNRESOLVED: %s cites %s, which does not exist."
                        % (claim["claim_id"], source))
            try:
                with open(source, encoding="utf-8") as handle:
                    cache[source] = json.load(handle)
            except (json.JSONDecodeError, OSError) as exc:
                return ("CLAIM UNRESOLVED: %s cites %s, which could not be read "
                        "(%s)." % (claim["claim_id"], source, exc))

        value, found = resolve_json_path(cache[source], claim["json_path"])
        if not found:
            return ("CLAIM UNRESOLVED: %s cites json_path %r in %s, which does "
                    "not resolve." % (claim["claim_id"], claim["json_path"], source))
        if value != claim["value"] or type(value) is not type(claim["value"]):
            return ("CLAIM UNRESOLVED: %s renders %r but %s :: %s holds %r. The "
                    "rendered figure does not match its own source."
                    % (claim["claim_id"], claim["value"], source,
                       claim["json_path"], value))
    return None
