# Finances & Making Money

**Sources:** `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — **primary**, p.8
("Finances & Making Money"). Cross-checked against `FS25-manual_EN.pdf` (base edition, 24pp),
same p.8: **programmatically confirmed byte-identical** (only a page-number formatting
difference, "8" vs "08"). Verification: text extracted with PyMuPDF and cross-checked visually
against the page's own finance-screen/contracts/generators screenshots (no numeric data in those
screenshots beyond what the body text states). This file never used Academy sourcing, so the
corrected sourcing policy (Academy no longer primary) doesn't change anything here.

**This file is a distillation, not the live source of truth** — see the in-game Help for the
live version of this content.

## Financials & Loans

*(Manual p.8)*

- The finance screen shows all income and expenditures for the current month and the
  previous four months (a 5-month rolling view).
- Any loan taken from the bank is displayed on the finance screen.
- You can take on additional loans from the bank if you need money urgently.
- "At the end of each month, you will have to pay any excess interest on the loans."
  Pay loans back as fast as possible to save on interest.

**Interest billing frequency (resolved, F-124):** the manual states interest is settled
"at the end of each month" — i.e. once per calendar month, not per day. The
finance-screen screenshot on this page has no separate "Interest" line item, consistent
with interest being folded into the month-end settlement rather than accrued/shown as a
running daily charge. Since there are always 12 months per year regardless of
`daysPerPeriod`, the annualized rate is `one month's loanInterest × 12 / loan`. **Billing
frequency (once per month) is manual-verified; the FLAT-monthly amount this formula
assumes is not.** The manual doesn't state whether that monthly charge scales with
`daysPerPeriod` (e.g. a daily-accrual sum) or stays flat regardless — flat-monthly is the
standard convention and matches all current evidence, but it hasn't been empirically
confirmed on a save with `daysPerPeriod != 1`. This does not come from a single explicit
sentence on p.8 beyond "at the end of each month"; the per-day-vs-per-period question was
cross-verified against game behavior by the `fs25-investigate-interest` teammate and
folded in here per that resolved verdict. A future `daysPerPeriod ≥ 2` save would make
this definitive.

## Contracts

*(Manual p.8)*

- Other farms on the map are owned by other (NPC) farmers unless you buy their fields.
- The contract screen (in the menu) lists available jobs; you can also ask neighbors
  directly whether they need help.
- Contracts are a way to earn money, gain familiarity with machinery/processes, and try
  equipment or crops/activities not yet available on your own farm.
- Contracts can be done with your own machines, or with equipment borrowed for the job.

## Passive Income

*(Manual p.8)*

- Passive income sources include wind turbines, solar collectors, and other generator
  types.
- These can have high initial (purchase) costs but are described as "often worth the
  investment."
- They produce steady income without requiring further attention once placed.
- Generators are purchased and placed on your land via the build menu.

## Not covered on this page

The manual's Finances page does not mention: a numeric interest rate, a loan cap/limit,
selling-price fluctuation mechanics (covered in `crops.md`, Storing), or contract-reward
formulas beyond what's shown in the contract-screen screenshot (a per-contract flat
reward, e.g. "€3,221" — a single example value, not a general formula). None of these
are asserted here since the source doesn't state them generally.
