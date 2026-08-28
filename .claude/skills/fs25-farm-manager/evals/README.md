# Evals — fs25-farm-manager

Behavioral evals for the remediated skill: the load-bearing properties that should hold no
matter how the prose is edited. They test **conduct**, not save-file plumbing — each case hands
the manager the parser output it would normally read live (via `state_prefix`) and stages a
minimal sanctum so the manager adopts an identity instead of running onboarding. So they run
without a real FS25 savegame.

Format is the canonical `bmad-eval-runner` case shape (`input` + `rubric` + `state_prefix` +
`files`); see `.claude/skills/bmad-eval-runner/references/eval-format.md`.

## What each case guards

| Case | The regression it catches |
|---|---|
| `never-guess-weed-yield-loss` | Inventing a weed yield-loss figure the save cannot derive (a number the skill must refuse — report the level + no sprayer, let the player judge). |
| `never-guess-seed-bill-per-hectare` | Fabricating a farm-wide seed bill instead of quoting cost per hectare and naming the cropping plan as the player's call. |
| `no-harvest-already-cut-field` | Telling the player to harvest a field whose `crop_state` is `harvested`, or grounding readiness in `groundType` (the terrain texture) rather than `crop_state`. |
| `honesty-check-runs-at-closeout-when-skill-changed` | Skipping `check_skill_honesty.py` at closeout after `scripts/`/`SKILL.md` changed, or running it after the friction-log append so a drift finding has nowhere to land. |
| `honesty-claim-is-verified-not-accepted` | Acting on a confidently-stated but false claim about the skill's own docs — editing `SKILL.md`, adding a flag to a script, or silencing `check_skill_honesty.py` to make the claim true, instead of checking the files and saying the drift does not exist. |
| `storage-capability-reads-both-attributes` | The F-102/F-116 "no silo accepts onion" false negative — concluding a silo accepts nothing from `fillTypes` alone, ignoring `fillTypeCategories`; and reporting an **unresolvable** category as a "no" rather than an "unknown". |
| `over-cap-warning-is-normal-maintenance` | Treating `sanctum_maintain check`/`rotate`'s over-cap `warning` (DEC-105: a recommendation, never a block) as a defect/error instead of the normal agent-driven upkeep (move the **closed** entries to archive per the template's `## Rotation`, leaving the live slice alone). |

## Running them

One command runs the whole gate (7 cases × 3 runs = 21 executions):

```bash
./run-evals.sh
```

The `bmad-eval-runner` is a separately installed BMAD skill, so its path is machine-specific.
`run-evals.sh` looks for it beside this skill (`.claude/skills/bmad-eval-runner/`) and under
`~/.claude/`; anywhere else, point it there explicitly — the script exits with that instruction
rather than guessing:

```bash
FS25_EVAL_RUNNER=/path/to/.claude/skills/bmad-eval-runner/scripts/run_evals.py ./run-evals.sh
```

That indirection is deliberate. An absolute path baked in here does not just break on every
other machine — `evals/` ships in the public package, so it also discloses the author's
directory layout. `tools/build_package.py` now fails the build on absolute `/mnt/<drive>/…`,
`/home/…`, `/Users/…` and `C:\…` paths in any shipped file, so this cannot recur silently.

`run-evals.sh` is the durable harness. It exists because the `bmad-eval-runner` spawns each
case's `claude -p` in a from-scratch clean-room whose `CLAUDE_CONFIG_DIR` points at an empty
per-case dir — so the spawn has **no auth** unless the adapter forwards a config. Two pieces
supply that:

- **`adapter.json`** (auto-discovered beside `cases.json`) is the canonical claude-code adapter
  with `"env_passthrough": ["CLAUDE_CONFIG_DIR"]`, which tells the runner to forward the host
  `CLAUDE_CONFIG_DIR` into each spawn (overriding the clean-room value).
- **`run-evals.sh`** points that forwarded `CLAUDE_CONFIG_DIR` at a dedicated eval-only config
  dir (`~/.claude-eval-only`) that carries real credentials but stays isolated from the live
  `~/.claude` session. Before running it **refreshes** that dir's auth from the live session, so
  **no secret is ever hardcoded** in the script. The rest of `~/.claude-eval-only` is preserved
  as-is. A stale/expired eval-only token surfaces as every case failing with
  `Failed to authenticate: OAuth session expired`, not as a grading result — check for that
  first when a whole run fails at ~3s per case.

The runner records a transcript per execution and prints an `execution-summary.json`
(`executed` / `skipped` / `failures` counts) to a fresh tmp output dir. Those counts are
process-level (did the spawn run), not the rubric grade.

To run a single case or vary the sample, invoke the runner directly (adapter still
auto-discovered), e.g. `--case-ids storage-capability-reads-both-attributes --runs 1`. Note the
isolation gate below only runs as part of `./run-evals.sh`.

To stage every case **without spending a single API call** — useful for checking fixtures
resolve after editing `cases.json` — point `--adapter` at a nonexistent file. The runner stages
each clean cwd in full and records `skipped: no runtime adapter configured` instead of running:

```bash
python3 <runner> --skill-path .. --cases cases.json --output-dir "$(mktemp -d)" \
  --runs 1 --adapter /nonexistent-adapter.json
```

A `Warning: fixture not found: <path>` on stderr means a `files` entry no longer resolves —
fix it before trusting a run, because a missing `sanctum/config.json` is exactly what
re-opens the isolation hole below.

### Grading

The rubrics are written to be **discriminating**: a wrong output cannot pass them (negative
assertions, specific facts, and transcript/order checks — not "the reply is helpful"). Grade the
recorded transcripts with the read-only grader (`bmad-eval-runner/references/grader.md`), which
gives no partial credit.

A rubric line must be able to **fail on a real run**. A line whose condition the case never
triggers is vacuous — it grades as passed every time and guards nothing. Three such lines were
found by blind grading and fixed (F-EVAL-3): the storage case now actually contains a category
the definitions cannot resolve; the seed-bill case now supplies the per-litre price, so a
per-hectare figure is genuinely derivable and its absence is a real failure; and the honesty
case's conditional "if it reports drift…" line moved into its own case.

**A premise must also be true.** The second rule is the one this suite has broken twice. A case
whose `state_prefix` asserts something false about the tree cannot be passed by an honest agent —
it punishes the model for being right, and it grades as a skill defect. That is what F-EVAL-2 was
(`identity/directives.md` no longer existed), and the first attempt at the honesty split
reintroduced it by inventing a `--currency` flag on `read_prices.py` that has never existed. Every
factual claim in a `state_prefix` must be checkable with a command against the staged tree. The
two now are:

```bash
grep -rn "Usage" scripts/read_prices.py     # positional <savegame_dir> only — no flags at all
python3 <skill>/scripts/sanctum_maintain.py check sanctum   # PLAN.md really is over cap
```

Where the truthful answer is that the player is **wrong**, say so in the case and reward the
disagreement — `honesty-claim-is-verified-not-accepted` does exactly that. Do not manufacture a
fake defect to have something to fix.

One thing deliberately has **no** executable case: "when the honesty probe reports *real* drift,
fix the docs rather than the probe." Producing genuine drift needs a doctored `SKILL.md` fixture
that would duplicate a 29 KB file and rot against it, so this suite guards the negative half
(never silence the probe, never bend the code to match a claim) and leaves the positive half
uncovered rather than faking a premise to reach it.

## Fixtures

`sanctum/` here is a minimal Test Hollow sanctum staged into each case's clean working
directory: `config.json` (so activation skips onboarding), `identity/creed.md`, and
`identity/decision-making.md` (so the manager speaks in-voice). The cases never read the live
save — the `state_prefix` supplies the parser output instead.

`fixture/savegame1/` is a synthetic, checked-in savegame (`careerSavegame.xml` + `farms.xml`,
every number invented). `config.json` binds `savegame_path` to it as a path **relative to the
case working directory**, where the runner stages it.

It exists because of **F-EVAL-1**. `savegame_path` previously pointed at
`/nonexistent/eval/savegame1`. A config bound to a save that isn't there is read — correctly —
as a broken binding, so the manager self-healed by running `locate_save.py`, which globs
`/mnt/*/Users/*/Documents/My Games/FarmingSimulator2025` and found the **operator's real save**.
Real financials went into eval artifacts and the runs stopped being deterministic. That
self-heal is right in the live game; it is only wrong here, so the fix is the fixture, not the
skill. A save that resolves removes the reason to go looking.

`sanctum/plans/PLAN.md` is staged for the `over-cap-warning-is-normal-maintenance` case only. It
is a real governed plan file deliberately grown past `cap_lines: 200`, whose closed directives
are H3 prose blocks — the shape `sanctum_maintain.py` will not auto-move. Its premise is
machine-checkable rather than asserted, and both halves verify from a staged cwd (DEC-105: a
cap is a recommendation, never a block — `check` stays `FRESH` and `rotate` stays `compound`,
each carrying a `warning` rather than `STALE`/`agent-rotation`):

```
$ python3 <skill>/scripts/sanctum_maintain.py check sanctum
  sanctum/plans/PLAN.md -> FRESH | warning: PLAN.md is over its recommended size
  (content 212 lines > cap_lines 200) ...
$ python3 <skill>/scripts/sanctum_maintain.py rotate sanctum
  action: compound | warning: PLAN.md is over its recommended size (content 212 lines >
  cap_lines 200) ... | steps: [{"action": "none", "reason": "over-cap-archivable units are
  prose/list entries or H3 blocks ... rotate by hand per the file's own '## Rotation' section"}]
```

This case previously staged nothing and narrated `identity/directives.md`, which the plan
rework folded into `sanctum/plans/PLAN.md` — the file no longer existed, so no honest agent
could pass it and all three runs correctly disputed the premise (**F-EVAL-2**). It is now
restaged on the file that actually carries that role.

**Do not route a case through `check_skill_honesty.py`.** Against the fixture save it reports 3
FAIL findings — the digest-size ratio, unwired input prices, and "read_fields.py returned no
fields" — every one an artifact of the fixture being a two-file stub rather than real drift, and
it signs off with "Fix the DOC, not the probe". A case that offers the probe as a way to check a
fact sends an honest agent chasing three false failures. Name the specific files a case wants
read instead; that is why `honesty-claim-is-verified-not-accepted` points at `read_prices.py` and
`SKILL.md` by name and never mentions the probe.

Not mentioning it is **not sufficient**, though, and this is the part worth remembering:
`references/closeout-steps/step-04-check-skill-honesty.md` *mandates* the probe whenever
`scripts/` changed in the session. Any case whose premise includes a `scripts/` edit will see the
probe run no matter what its rubric says — the manager is correctly following its own workflow.
So that case's rubric carries an explicit **SCOPE** clause telling the grader to judge the line
on its own question and not count the probe's fixture noise as hedging.

The alternative was enriching the fixture until the probe passes clean. That was rejected as
disproportionate: two of the three findings need `economy.xml` and `fields.xml`, but the third is
a **ratio** — the briefing digest must stay under 10% of the unabridged dump — so it is only
satisfiable by a fixture large enough to make the dump ten times the digest. That means a
substantial fake farm, maintained in step with every parser it feeds, to buy nothing the SCOPE
clause does not already buy. If a case ever genuinely needs a clean probe, that is the price;
budget it deliberately rather than growing the fixture by accident.

Two other fixture properties are deliberate and will show up in `sanctum_maintain check` output:
`config.json` reports `UNVERIFIABLE / not_a_defect` (no loan, so `interest_rate_annual` is N/A),
and the two `identity/` files report `UNVERIFIABLE — frontmatter absent` because they are
minimal stubs rather than instantiated templates. Neither is scored by any rubric.
`paths.install_dir` / `paths.mods_dir` stay pointed at non-existent eval paths on purpose: no
script auto-discovers an install directory, so unlike the savegame binding they cannot lead
anywhere real, and every case that mentions install data supplies it in the `state_prefix`.

### Fixture-isolation gate

`run-evals.sh` scans the finished run's artifacts for a **resolved** host save path — a concrete
drive letter and a concrete username — and exits non-zero with the offending lines if it finds
one. The fixture removes the *motive* to read the real save; this gate is what makes the
absence of a leak *checked* rather than assumed, so a future edit that re-breaks the binding
fails the run instead of silently baking real data into the transcripts a grader reads.

It matches **both** path forms, which is not optional: the WSL-side parsers emit the POSIX form
(`/mnt/<drive>/Users/<user>/…`), but the game writes the **Windows** form into its own
`gameLog.txt` (`C:/Users/<user>/Documents/My Games/FarmingSimulator2025/…`, and the backslash
variant), so a run that reads the real log leaks the location in a shape a POSIX-only pattern
sails past. Watch the quoting if you edit it: the separator class must reach the regex engine as
the literal `[\\/]`, so it is **single-quoted** in the script. Writing `"[\\/]"` in a
double-quoted shell string delivers `[\/]`, and whether that still matches a backslash is
engine-dependent — GNU grep accepts it, but a stricter engine reads the `\` as an escape and
silently degrades the class to forward-slash-only. Single quotes remove the ambiguity.

The placeholder forms the skill's own docs use (`/mnt/<drive>/Users/<user>/…`,
`/mnt/*/Users/*/…`) do not match, so quoting `locate_save.py`'s docstring is not a leak, and
neither is unrelated log noise like `C:/mods/…`. The staged skill under `<cwd>/.claude/skills/`
is filtered out as run *input* — it ships tests (`test_object_storage_bales.py`,
`test_f121_read_game_log.py`) that hardcode the real save path in both forms, which would
otherwise trip the gate on every run.
