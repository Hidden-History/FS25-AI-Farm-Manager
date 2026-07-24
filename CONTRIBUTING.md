# Contributing to FS25 AI Farm Manager

Thanks for your interest in improving **FS25 AI Farm Manager** — a Claude Code
**skill** that reads a Farming Simulator 25 save and advises the player, paired
with an in-game **Lua mod** that shows on-screen notification cards.

This is a solo-maintained project. Contributions are welcome; the notes below
keep the process smooth for everyone.

> This project ships as a mod + a Claude Code skill. It is **not** published to
> PyPI — there is no `pip install`. You run it from the repo.

## Filing issues

Please use the issue forms — they make sure the important details are captured:

- **🐛 Bug report** — something isn't working.
- **✨ Feature request** — an idea or improvement.
- **❓ Question** — usage or setup help.

When filing, tell us which part is involved so it can be labelled correctly:

- `area: mod` — the in-game Lua mod (notification cards).
- `area: skill` — the Claude Code skill (save reading, advice).
- `area: docs` — documentation.

Before opening a new issue, please search existing issues to avoid duplicates.
For security problems, **do not open an issue** — see
[`SECURITY.md`](SECURITY.md).

## Pull request flow

1. **Fork** the repository and create a topic branch from `main`
   (e.g. `fix/notification-timing` or `feat/crop-price-advice`).
2. Make your change. Keep it focused — one logical change per PR.
3. Update docs if your change affects behaviour or usage.
4. Open a **pull request** against `main` and fill in the PR template.
5. **CI must pass** before review — see below.
6. The **maintainer merges** once CI is green and the change is approved.

Please keep PRs small and reviewable. If you're planning a large change, open an
issue first so we can align on the approach before you invest the time.

## CI and testing

Every PR and push to `main` runs CI:

- **lint** — style and static checks.
- **public smoke** — a lightweight smoke test that runs on public infrastructure
  and does not depend on private save data.

The **full test suite is dev-side** — it exercises paths that need local save
games and environment setup that can't run in public CI. The maintainer runs it
before releases. You don't need it to pass CI, but if your change touches
tested behaviour, describe how you verified it in the PR.

## Style

Match the existing style of the code you're editing — Lua for the mod, Python
for the skill. Keep changes surgical: touch only what your change requires, and
don't reformat unrelated code.

## Reporting anything sensitive

Never include private save data, credentials, personal information, or local
machine paths in issues, PRs, or commits.

## Code of conduct

By participating, you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).
