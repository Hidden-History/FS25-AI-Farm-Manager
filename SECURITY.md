# Security Policy

Thanks for helping keep **FS25 AI Farm Manager** and its users safe.

## Supported versions

Security fixes land against the **latest release**. Older releases are not
patched — please update to the newest version before reporting an issue.

| Version | Supported |
|---|---|
| Latest release | :white_check_mark: |
| Older releases | :x: |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability** (GitHub's private vulnerability reporting).
3. Fill in what you found, the impact, and how to reproduce it.

This routes the report privately to the maintainer. You'll get a response as
soon as possible — this is a solo-maintained project, so please allow some
time for triage.

## What to include

- A clear description of the issue and its impact.
- Steps to reproduce (or a proof of concept).
- The affected component — the Claude Code **skill**, the in-game **Lua mod**,
  or both.
- Any relevant version, save-game, or environment details. **Do not include
  private save data, credentials, or personal information** in the report.

## Scope

This project reads a local Farming Simulator 25 save and renders in-game
notification cards; it does not run a hosted service. Reports about how the
skill or mod handles save data, file paths, or third-party dependencies are in
scope. Please be mindful not to share sensitive local paths or personal data
when reproducing.

## Disclosure

Once a fix is available, the vulnerability may be disclosed in the release
notes. Credit is given to reporters who want it.
