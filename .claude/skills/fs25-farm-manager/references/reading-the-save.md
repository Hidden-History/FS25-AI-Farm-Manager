# Reading the save honestly

A savegame is a file format, not a witness. It will not tell you when you've
misread it — a wrong parse and a right one both return valid JSON, both look
like an answer. This is how to tell the difference, learned the expensive way
across a full onboarding session against a real FS25 save. Everything below
was earned by running a parser and finding it wrong, not by reading the code
harder.

## The rule that subsumes the rest

**Absence must never be allowed to look like data.** An empty list, a `None`,
a zero, a silence — every one of these is ambiguous between "I checked, and
there is nothing" and "I could not find it." A reader cannot tell those apart
from the output alone, so the parser must: it emits `{"error": "..."}` (or an
explicit `null` with a stated reason) and never a bare `[]`, `{}`, or `None`
standing in for "unknown."

This single discipline would have prevented most of the mistakes below. Every
one of them is the same defect wearing a different costume:

| Shape of the absence | Read as | Should have been |
|---|---|---|
| An empty list from the wrong file | "this farm owns no land" | "I read the wrong file" |
| A matched-but-wrong XML tag | a confident, wrong number | "the right tag wasn't found" |
| `None` on an attribute that doesn't exist at that path | "zero wear, never driven" | "I looked in the wrong place" |
| No file writes in an observation window | "the player is paused" | "I don't know what the player is doing" |
| A shell pipeline's exit code | "the merge succeeded" | check the artifact the merge should have produced |
| A reward field that's genuinely `0` at offer-time | "this contract pays nothing" | "reward is unknown until accepted" |
| A `<stats>` node with no fill children | "zero storage capacity" | "no fill data present on this node" |

Before writing any of these into a briefing, ask: *could this be a hole in my
reading rather than a hole in the farm?* If there's any doubt, that doubt is
the thing to report — not the zero.

## Units are the trap, and there's one test that catches all of them

FS25's savegame XML does not name its units consistently, and tag names
actively mislead (`playTime` sounds like hours; it isn't). Guessing from a
tag's name, or from what "seems reasonable," produces a plausible number that
happens to be wrong by an order of magnitude — the most dangerous kind of
error because nothing about the output looks broken.

**The test that works, and the only one that's caught every instance so far:
convert the number to a human scale and ask whether it could be true of a
real farm.**

Worked examples:
- *A save created today shows 101 "hours" of play time.* Impossible — nobody
  played four days straight on day one. Reinterpreted as minutes (1.7 hours),
  it's an ordinary session. The field was minutes, not hours.
- *A vehicle burns 5 litres of diesel over what a raw field reads as "30
  hours."* That's 0.17 L/h — no tractor idles that efficiently. Reinterpreted
  as seconds (30 minutes), it's 10 L/h — correct for a tractor under load.
  The field was seconds, not the unit its name implied.
- *A farm's own land-ownership field reads as an empty list.* Not a unit
  error, but the same test in spirit: does a real farm plausibly own nothing
  at all, ever? Worth a second look before it's reported as fact.

Reading the code harder does not catch these — the code is internally
consistent either way. Only checking the number against physical plausibility
does.

### The test is only as good as what you measure against

The plausibility test has one failure mode, and it is worth as much attention
as the test itself: **it is only as good as the yardstick.** Ask "could this be
true of a real farm?" against the wrong reference and the test fires
confidently on a number that was correct all along — a false alarm that reads
exactly like a catch.

The worked example, and note who made it: a combine reported ~76,000 litres of
grain on board. That is absurd against a base-game harvester, whose tank is
around 14,000 L, so it was flagged as suspicious and quoted as a fact that
needed testing. The number was real. The machine was not a base-game
harvester — it was a `$moddir$` mod whose own XML declares selectable tank
configurations of 16,200 / 120,000 / **240,000** L, and the save recorded the
240,000 L configuration as the active one. The tank was a third full. The
physical-possibility test worked perfectly; the yardstick was wrong.

**This is the same defect as the basename-fallback rule, committed by a human
instead of a resolver.** The rule says: never resolve a `$moddir$` item against
a same-named base-game file, because it returns a real, plausible, wrong
answer. Sanity-checking a modded machine against base-game specs is that
mistake performed by hand — and it was made by the same person who had written
the rule that morning.

So, before doubting a number:
- **Check what the thing actually is.** A `$moddir$` prefix means the base game
  is not the reference for anything about it — not price, not capacity, not
  role. Mods routinely rebalance by 10x and more.
- **Resolve the yardstick in the item's own package**, exactly as you would the
  item. The mod's XML declares its own capacities; the save records which
  configuration is live.
- **A number that survives investigation is a finding, not a false alarm.**
  Report what made it plausible, so the next reader doesn't re-litigate it.

The test stays. Point it at the right reference.

Units worth stating outright, so nobody re-derives them from scratch:
- an in-day clock field expressed as **minutes-of-day** (range 0–1440)
- a weather/forecast start-time or duration expressed in **milliseconds-of-day**
- a vehicle's accumulated operating time expressed in **seconds**
- a career/session play-time field expressed in **minutes**

Don't assume any of these transfer to a field you haven't checked — the
lesson is the test, not the specific table. Apply it to every new numeric
field before it's surfaced, not after someone else catches it.

## "Verified by running" is the only kind of confidence worth writing down

A docstring or comment that asserts a structure is "confirmed" or
"community-verified" is a claim, not evidence — and it is exactly the kind of
claim that gets believed *because* it sounds confident, which makes it more
dangerous than an honest "untested." The worst mis-parse in this class of
project came from a docstring asserting a structure that simply does not
exist in the format being read; the same confident phrasing on two other
parsers happened to be true, which only means a claim like that is a coin
flip, not a guarantee.

The only trustworthy form is a claim that names its own evidence: "confirmed
against a real save, run on \<date\>, output was X" — something a reader can
check by re-running it, not just believe. If you can't point to a run that
verified it, say "untested" or "assumed," not "confirmed."

And a success flag that just counts matches is not the same as a correctness
check. A calibration/health flag that reports "OK" because *some* candidate
values were found — rather than the *right* ones — will confidently pass over
three wrong numbers at once. Treat any such flag as necessary, not
sufficient: it tells you parsing didn't crash, not that the values are true.
Sanity-check the values themselves — does the farm own zero land? does the
in-game day equal the raw time-of-day field? does a count look suspiciously
like the size of the whole map rather than one farm's share of it?

## Ownership: filter, or you're describing the map

Most FS25 save data is map-wide, not farm-specific — vehicles, buildings, and
scenery on a shared map are not partitioned by owner unless you explicitly
filter for it. Every entity table that carries an owner id must be filtered
by that id, or the count you report describes the whole map, not the player's
farm.

Concretely, on one save: a vehicle table listed 50 entries; only 24 belonged
to the player, the rest were unowned map props (a locomotive, cargo wagons).
Buildings/production placeables are frequently map-wide scenery, sometimes
under an owner id that doesn't even correspond to a registered farm in the
save's own farm list — infrastructure baked into the map by its author, using
an internal id nothing else recognizes. Reporting the unfiltered count as "you
own N vehicles / N production buildings" is false and it's the specific kind
of false that sounds plausible, which is worse than a number that looks
obviously wrong.

Always filter by the owning id, always report owned-vs-total-seen side by
side (never silently drop the total — a caller should be able to see that
the inflation is even possible), and if an id shows up that doesn't match any
known owner, say so explicitly rather than folding it into either bucket.

## mtime is the only honest freshness signal

A game like this can defer writing its save until some later trigger (e.g.
the player next opening a menu), not on a fixed timer — so an "autosave
interval" setting bounds *nothing*. It only marks when a write becomes due,
not when it happens. A save can sit unchanged for arbitrarily long mid-session
with the player still actively playing.

Never infer what the player is doing from the absence of writes. "No file
changes in N minutes" is not evidence of anything except "no file changes in
N minutes" — not a pause, not idling, not disconnection. If you need to know
what the player is doing, that's a question for the player, not an inference
from silence (see the rule at the top: silence is an absence, and absence is
not data).

The one freshness fact worth trusting is the file's own modification time —
report it plainly ("as of N minutes ago") whenever a number from the save
might be stale enough to matter, and let the reader judge.

## A live file will answer questions its contents won't: watch what moves

The flip side of "the game writes while you read" is that **the writes are
themselves data.** When a value you need isn't stated anywhere, two reads taken
apart in time will often identify it — because the game keeps exactly the live
one up to date and leaves the rest frozen.

The worked example, which settled a question two files' worth of static reading
could not. The market file holds a 12-cell price table per commodity, one cell
per seasonal period. Nothing in the savegame states which period is *current* —
there is no such field; it was searched for. The obvious derivation (from the
day counter and the days-per-period setting) had a serious rival: the forecast
tagged ten consecutive days with a single unchanging season, and a career
setting named a different period outright. The two readings disagreed by ~9% on
every price — the exact size of error that looks entirely plausible and is
simply false.

Diffing two reads of that file, taken about forty minutes apart while the
player played, decided it in one step. Of 40 cells with known prior values, 36
were byte-identical and 4 had moved — and all 4 were the same period, across
four unrelated commodities. **The game fluctuates the current period's cell in
place and freezes the other eleven. The live period is whichever cell moves.**
That is an observation, not a derivation, and it refuted the rival outright:
had the rival been right, its cell would have been the one moving.

The generalisation is worth more than the instance:

- **When a value isn't stated, look for what the game keeps updating.** A live
  field is self-identifying. Sample twice, diff, and the moving part tells you
  where you are.
- **Prefer a test that needs no one's cooperation.** The alternative here was
  asking the player to advance a day — costing them a day of farming to answer
  a question the file was already answering for free, to anyone patient enough
  to look twice.
- **Budget for the deferred write.** The same behaviour that makes mtime the
  only honest freshness signal applies: a two-minute window caught nothing; a
  much longer one did. A null result from a short window is not evidence of
  anything (see the rule at the top — that silence is an absence, not data).
- **A settings name is a hypothesis, not a fact.** The rival reading came from
  a setting whose name contained "Visuals" and which turned out to do exactly
  that — freeze the *look* of the world while the economy carried on
  underneath. Its name was the strongest clue available and still had to be
  tested rather than believed.

Record which reading won *and how it died*, not just the winner. A refuted
hypothesis with its evidence attached stops the next session reopening a
settled question; a silently deleted one guarantees they will.

## Where the data actually lives

The single most expensive mistake available here is reading the wrong file
confidently — it doesn't crash, it just quietly answers a different question.
Established by direct inspection, worth treating as a map rather than
re-deriving per session:

| Data | Lives in | Not in |
|---|---|---|
| Cash, loan, and finance running totals (new-vehicle spend, field-purchase spend, construction spend, loan interest) | the farm's own save record (a `farms.xml`-equivalent, keyed by farm id) | the fill-type/price-history file — that file is market price history only, it has no cash or ownership concept at all |
| Land ownership (which parcels belong to which farm) | the farmland ownership file, matched by farm id | — |
| In-game day counter | the environment/world-state file's explicit day-counter tag | the same file's raw time-of-day tag, which is a different field on a different scale (see Units, above) |
| Session/difficulty settings, timeScale, mod list | the career-save file | — |
| Buildings/silos/production placeables | the placeables file | the vehicles file — a vehicle listing and a buildings listing are different files with different ownership rules |
| Field crop/growth state | the fields file | — carries no owner id at all; ownership for fields has to come from the farmland file plus a spatial join, not from anything in the fields file itself |

If a doc, a comment, or a prior session's notes assert one of these
mappings, verify it against the actual file before trusting it — the
docstring making the strongest claim in this codebase's history was also the
one describing a structure that didn't exist.

## Prices are usually on disk, but resolve them inside their own package

Store/catalog prices for equipment and land are frequently *not* in the save
file itself, which tempts a parser into declaring them unobtainable and
punting to the player. Check the install and any mod directories before
concluding that — a base game install typically ships plain price tags per
item, and mod packages carry their own equivalent files inside their own
archives.

The trap: a modded item's filename must resolve *inside its own package*
never by falling back to a same-named file in the base install. Mods
frequently reuse a base game's filename for a re-skinned or lightly-edited
item, so a basename fallback can return a real, plausible-looking price that
is nevertheless wrong the moment the mod's own price diverges from the
base's — and it will look correct for as long as the two happen to agree,
which is exactly what makes the shortcut dangerous rather than merely lazy.
Resolve inside the item's own declared package, or report it unresolved.

## A filename is marketing; runtime state is the fact

Don't infer what something *is* — its role, capability, or type — from its
name. Mod and asset filenames are chosen for marketing appeal and are not a
reliable schema: a name suggesting one kind of implement can belong to an
entirely different one. One save's fleet included a vehicle named like a
flatbed trailer whose actual in-save specialization tag identified it as a
header attachment — four of them, all named the same misleading way.

The fix is to read what the save's own runtime state says the thing is —
its own child tags/attributes at the moment it's saved — rather than parsing
significance out of a name a modder or the base game happened to pick. If you
want to know whether the fleet has balers, look for the tag that means
"baler," not for the substring "bale" in a filename.

## Read the file you already have open

Before declaring a number unobtainable — "locked in a proprietary format,"
"not tracked anywhere," "the player has to tell us" — check whether it's
already sitting in a file you're reading for something else. One session
declared a land-cost figure permanently locked in an opaque raster format and
escalated it as a blocking question for the player, while the exact number
was present as plain text in the same finance file already being read for
cash and loan. The habit that would have caught it: before writing "this
can't be derived," grep the files already open for the term itself.

## Check the artifact, not the command

A command's exit status, a pipeline's "success" message, or a green
checkmark is not the same claim as "the operation had the effect I intended."
A shell pipeline can report success at a stage that always succeeds (e.g. a
formatting/paging command at the end of a pipe) regardless of what the actual
operation upstream did. The concrete case: a merge command's output was piped
into a formatter, and the formatter's own exit code — not the merge's — was
what got treated as "it worked." Nothing was actually merged.

Verify against the thing the operation was supposed to produce — the file
that should now exist, the count that should have changed, the diff that
should be non-empty — not against the process substitute for that evidence.
This is the same discipline as "sanity-check the values, not the success
flag," applied to shell commands instead of parsers.
