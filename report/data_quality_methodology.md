# Handling data problems: methodology

How this project handles data-quality issues, with the specific problems we
encountered. Companion to `DECISIONS.md` (which records each rule); this
document explains the approach for the report and mentor discussions.

## Principles

1. **Raw data is immutable.** API responses are stored untouched in
   `data/raw/`; every fix happens in code, downstream, and is rerunnable.
2. **Fixes are rules, never hand-edits.** No individual cell was ever
   corrected; each fix is a rule applied uniformly to all observations.
3. **Record, don't discard.** Interventions are stored as columns in the
   dataset (e.g. `mono_violation`, `avg_spread`) so they remain visible.
4. **Decide before looking at results.** Rules are pre-registered in
   `DECISIONS.md` so cleaning choices cannot chase favorable findings.
5. **Validate externally.** Parsed or reconstructed values are cross-checked
   against published BLS figures.

## Problems found, rules applied, examples

### 1. Incoherent prices ("probabilities don't sum to one")

Because KXCPI contracts are thresholds, the distribution built by
differencing adjacent prices telescopes to a sum of exactly 1 — verified on
all 3,484 event-days. The real incoherence: independently-traded contracts
sometimes price P(CPI > 0.2%) above P(CPI > 0.1%), which is logically
impossible and implies a negative bin probability.

**Rule:** enforce monotonicity via running minimum; record the worst
violation per day as `mono_violation`; rerun key results excluding
high-violation days.

**Example:** violations on ~12% of event-days, median < 1¢, max 41¢,
correlation 0.34 with bid–ask spread — a thin-market symptom, reported as a
finding rather than hidden.

### 2. Thin / stale trading

**Rule:** price at the bid/ask midpoint (never the last trade); exclude
contract-days quoted 0/100 (spread > $0.90) as uninformative; carry spread
and volume in every row so analyses can filter by liquidity.

**Example:** median event volume ~1,800 contracts/day 30 days before
release vs ~20,800 the day before; headline results are rerun on liquid
days only as a robustness check.

### 3. Inconsistent settlement-value formats

Kalshi's `expiration_value` is a free-form string: "0.5", "0.60", "0.5%",
".9%".

**Rule:** one normalization function (`src/cpi_values.py`) handles every
observed format, rounding to the one-decimal settlement grid; outputs
spot-checked against BLS releases.

### 4. Missing settlement value (CPI-23OCT)

**Rule:** reconstruct from the contracts' own yes/no resolutions —
"CPI > x" resolving NO means the print was ≤ x; contiguous thresholds pin
the value exactly. Validate externally.

**Example:** resolutions imply 0.0% for October 2023, matching the actual
BLS first release. The observation is kept without guessing.

### 5. Identifier and API regime changes

Series renamed `CPI-` → `KXCPI-` (2024); negative thresholds encoded as
`T-0.3` (new) vs `TN0.3` (2022-era); live vs historical API tiers use
different field names (`close` vs `close_dollars`) and old markets 404 on
live endpoints.

**Rule:** parsers accept every observed convention; unparsed items are
logged loudly, never silently dropped — the log is what reveals unknown
regimes.

**Example:** the build log "7 markets skipped: TN0.1, …" exposed the old
negative-threshold format; handling it recovered every deflation contract
from 2022 (453 → 460 markets).

### 6. Unavoidable assumptions (open-ended tails)

The extreme bins are unbounded but the implied mean needs a value for them.

**Rule:** make the assumption explicit (tails valued one grid step beyond
the outermost threshold), document it, and sensitivity-check conclusions
against alternative tail choices in the evaluation.

### 7. Daylight-saving candle collision (found after the presentation, 2026-09-08)

When the pipeline was published with a continuous-integration check that
rebuilds every table and compares it byte-for-byte with the committed one,
the check failed on Linux while passing on macOS. The diff pointed at twelve
event-days, all the Monday after a spring daylight-saving change, with twice
the usual number of thresholds. Kalshi's daily candles end at midnight ET,
but the boundary moves one day late at the DST change, so one candle a year
ends at 01:00 EDT; labeling candles by their end timestamp put that candle
and the next one on the same day, and the unstable sort then ordered the
duplicates differently on the two platforms.

**Rule:** label each candle by the ET date of its midpoint (12 hours before
its end), which is immune to a one-hour wobble; drop any duplicate
contract-day that still appears, keeping the latest-ending candle, and say
so in the build log.

**Example:** CPI-24FEB, 2024-03-11 (one day before release) had 10 rows for
5 contracts; after the fix it has 5 and 2024-03-10 is no longer empty. The
event-day count rises from 3,484 to 3,497 and the headline numbers move in
the third decimal; no conclusion changes. The
lesson is the reason for the principle above: a reproducibility check is a
data-quality test.

## Summary sentence

Every data problem became a documented rule applied uniformly in code, with
the intervention recorded in the dataset itself — nothing hand-patched,
everything auditable, and several fixes turned into findings.
