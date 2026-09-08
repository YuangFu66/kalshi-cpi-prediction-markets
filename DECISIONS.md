# Methodology decisions

Every judgment call in the pipeline, recorded before running the evaluation.
Anyone re-running the scripts with these rules should reproduce our numbers
exactly.

## Scope

- **Series**: Kalshi KXCPI — headline CPI, month-over-month, one decimal,
  as published by the BLS. Events from CPI-21JUN (June 2021) onward; the
  pre-2024 events use the legacy `CPI-` ticker prefix but are returned under
  the KXCPI series by the API.
- **Sample**: settled events only (61 as of 2026-07-21). Open events are
  downloaded but excluded from evaluation tables.
- 2021 events have only 1–4 threshold markets; event-days with fewer than
  2 informative thresholds are dropped from the distribution table (a full
  distribution cannot be built from one contract).

## Market structure

KXCPI markets are **threshold contracts**: "Will CPI rise more than x%?"
(ticker suffix `T<x>`, e.g. `KXCPI-26MAY-T-0.3` = "more than −0.3%").
The yes-price of the x-threshold estimates the survival probability
S(x) = P(CPI > x). They are not mutually exclusive brackets; the
distribution is obtained by differencing S across adjacent thresholds.

Ticker-format quirks handled by the parser: negative thresholds appear as
`T-0.3` in new events but `TN0.3` in 2022-era events, and the live vs.
historical candlestick endpoints use different field names for the same
quantities (`close` vs `close_dollars`, `volume` vs `volume_fp`).

## Prices

- **Price = bid/ask midpoint** of the daily candlestick close, not the last
  trade (thin markets have stale trades).
- Contracts with spread > $0.90 on a given day (in practice: quoted 0/100,
  i.e. no real quotes) are treated as uninformative and excluded that day.
- Daily candles end at midnight ET; a candle is labeled with the ET calendar
  day it covers, read from the candle's midpoint (12 hours before its end).
  *Added 2026-09-08:* Kalshi shifts the candle boundary one day late at the
  spring daylight-saving change, so one candle a year ends at 01:00 EDT;
  labeling from the end timestamp had put two candles on the same day
  (12 event-days over 2022–2026, including two 1-day and two 30-day
  snapshots) and left the previous day empty. The midpoint rule fixes it;
  the pipeline also drops any remaining duplicate contract-day, keeping the
  latest-ending candle, and reports doing so.

## Distribution construction (per event-day)

1. Sort informative thresholds x₁ < … < xₙ, take mids as S(xᵢ).
2. Enforce monotonicity (S must be non-increasing): running minimum from the
   lowest threshold up. The maximum violation before fixing is recorded as
   `mono_violation`.
3. Bin probabilities: P(−∞, x₁] = 1 − S(x₁); P(xᵢ, xᵢ₊₁] = S(xᵢ) − S(xᵢ₊₁);
   P(xₙ, ∞) = S(xₙ). Because the bins are built by differencing, they
   telescope to a sum of exactly 1 — threshold markets have no
   bracket-style normalization problem (verified: `prob_sum_raw` = 1.0 on
   all event-days; the clip-and-renormalize step in the code is a
   safeguard only). Market incoherence instead appears as monotonicity
   violations (step 2), so **`mono_violation` is the coherence measure**:
   nonzero on ~12% of event-days, median violation < 1¢, and correlated
   with spreads (thin-market symptom).
4. Representative value of interior bin (a, b]: (a + b + 0.1)/2 — for
   contiguous 0.1-spaced thresholds this is exactly the grid value the bin
   contains. **Tail assumption**: bottom tail valued at x₁, top tail at
   xₙ + 0.1 (one grid step beyond the outermost threshold). Tail
   probabilities are usually small, but this is an assumption and results
   involving the implied mean should be robustness-checked against it.
5. Implied mean and SD are the moments of this discrete distribution.

## Ground truth

- The settled print is taken from Kalshi's own `expiration_value` field —
  this is by construction the first-release BLS number the exchange settled
  on (later BLS revisions are irrelevant).
- The field is a free-form string with drifting formats ("0.5", "0.60",
  ".9%"); it is normalized by `cpi_values.parse_actual`.
- One event (CPI-23OCT) has no usable value; it is inferred from the yes/no
  results of the threshold contracts (print > every YES threshold and
  ≤ every NO threshold), giving 0.0 — consistent with the actual
  October 2023 release.

## Fixed horizons

Snapshots at 30, 14, 7, and 1 day(s) before the release date (release date =
ET date of market close, which is the scheduled 8:30 ET publication day).
If the exact day is missing, the nearest available day within ±3 days is
used; otherwise the event is missing at that horizon.

## Known limitations (flagged for the report)

- ~61 monthly events: small for event-level statistical tests; pool across
  brackets/days where possible and mind autocorrelation.
- Early-life and 2021-era markets are thin; `avg_spread`, `day_volume` and
  `n_thresholds` are carried in every row so liquidity filters can be applied
  at analysis time.
- Prices embed fees and spreads, so "price = probability" is an
  approximation; the calibration analysis in Week 3 tests it directly.
- Threshold coverage changed over time (5–15 contracts per event, wider
  ranges in high-inflation 2022), so tail assumptions matter more in some
  periods than others.

## Evaluation sample (added 2026-09-08, as applied in the final presentation)

- The evaluation covers every settled event with a full implied distribution
  at the fixed horizons: 57 events, CPI-21DEC through KXCPI-26JUN (the four
  2021 events with 1–4 contracts have no distribution, see Scope).
- **KXCPI-25OCT is excluded from the headline sample.** The BLS never
  published October 2025 CPI (federal government shutdown), so no
  first-release print exists to grade against; Kalshi settled the market on
  its own rule. The event stays in every data table and the evaluation is
  also reported with it included ("all" sample, 57 events) — conclusions are
  unchanged.
- Accuracy is measured on the implied mean (MAE, RMSE, bias) against the
  first-release print; equal-accuracy tests use Diebold–Mariano on the
  absolute-error loss with a plain sample variance (one-step-ahead monthly
  forecasts do not overlap), with a Newey–West variance reported as a
  robustness check. Benchmarks are read on the same snapshot date as the
  market, never later.
