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
| `storage-capability-reads-both-attributes` | The F-102/F-116 "no silo accepts onion" false negative — concluding a silo accepts nothing from `fillTypes` alone, ignoring `fillTypeCategories`. |
| `agent-rotation-is-normal-maintenance` | Treating `sanctum_maintain rotate`'s `agent-rotation` report as a defect/error instead of the normal agent-driven upkeep (move resolved entries to archive per the template's `## Rotation`). |

## Running them

One command runs the whole gate (6 cases × 3 runs = 18 executions):

```bash
./run-evals.sh
```

`run-evals.sh` is the durable harness. It exists because the `bmad-eval-runner` spawns each
case's `claude -p` in a from-scratch clean-room whose `CLAUDE_CONFIG_DIR` points at an empty
per-case dir — so the spawn has **no auth** unless the adapter forwards a config. Two pieces
supply that:

- **`adapter.json`** (auto-discovered beside `cases.json`) is the canonical claude-code adapter
  with `"env_passthrough": ["CLAUDE_CONFIG_DIR"]`, which tells the runner to forward the host
  `CLAUDE_CONFIG_DIR` into each spawn (overriding the clean-room value).
- **`run-evals.sh`** points that forwarded `CLAUDE_CONFIG_DIR` at a dedicated eval-only config
  dir (`~/.claude-eval-only`) that carries real credentials but stays isolated from the live
  `~/.claude` session. Before running it **refreshes** that dir's auth: if
  `~/.claude-eval-only/.credentials.json` is missing or older than `~/.claude/.credentials.json`
  it copies the live `.credentials.json` (and `.claude.json` if the live dir carries one) across
  — live files are copied at runtime, so **no secret is ever hardcoded** in the script. The rest
  of `~/.claude-eval-only` is preserved as-is.

The runner records a transcript per execution and prints an `execution-summary.json`
(`executed` / `skipped` / `failures` counts) to a fresh tmp output dir. Those counts are
process-level (did the spawn run), not the rubric grade.

To run a single case or vary the sample, invoke the runner directly (adapter still
auto-discovered), e.g. `--case-ids storage-capability-reads-both-attributes --runs 1`.

### Grading

The rubrics are written to be **discriminating**: a wrong output cannot pass them (negative
assertions, specific facts, and transcript/order checks — not "the reply is helpful"). Grade the
recorded transcripts with the read-only grader (`bmad-eval-runner/references/grader.md`), which
gives no partial credit.

## Fixtures

`sanctum/` here is a minimal Test Hollow sanctum staged into each case's clean working
directory: `config.json` (so activation skips onboarding), `identity/creed.md`, and
`identity/decision-making.md` (so the manager speaks in-voice). Its `savegame_path`/`paths`
point at non-existent locations on purpose — these cases never read the live save; the
`state_prefix` supplies the parser output instead.
