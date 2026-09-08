# Week 1 Proposal — How well do Kalshi's CPI markets forecast inflation?

## Platform and market

We study the **KXCPI** series on **Kalshi**, a CFTC-regulated US prediction
market exchange. Each month Kalshi lists an event on the upcoming headline
CPI release ("CPI in May"), settled against the month-over-month percentage
change (one decimal) published by the Bureau of Labor Statistics.

## Why this market

1. **Unambiguous ground truth.** Every contract settles on a scheduled BLS
   release, so forecast accuracy is exactly measurable — no subjective
   resolution criteria.
2. **A repeated panel, not a one-off.** The series has run monthly since
   June 2021, giving 61 settled events (verified via the API) — enough to
   study calibration and accuracy systematically rather than anecdotally.
3. **A real research question.** CPI has been the most-watched macro number
   of this cycle, and professional benchmarks exist (economist consensus,
   the Cleveland Fed nowcast). Whether a prediction market beats them is a
   genuinely open empirical question.

## Data availability (verified)

- Kalshi's REST API is **public and free**; market data needs no
  authentication. We have already pulled the full inventory: **66 events
  (June 2021 – November 2026), 61 settled**, 528 individual contracts.
- Daily **candlesticks** (bid/ask/trade OHLC, volume, open interest) are
  available for every contract from listing to settlement. Data older than
  ~3 months lives behind separate *historical* endpoints; our pull scripts
  route between the live and historical tiers automatically.
- The settled CPI print is embedded in the market metadata
  (`expiration_value`), which by construction is the first-release BLS
  number the exchange settled on — sidestepping the data-revision problem
  that affects sources like FRED.

## Market structure

Each monthly event contains 5–15 binary **threshold contracts** of the form
"Will CPI rise more than x%?" for thresholds spaced 0.1pp apart (e.g. above
0.1%, above 0.2%, …). Each contract pays $1 if the print exceeds its
threshold. The yes-price of the x-contract therefore estimates
P(CPI > x), and differencing prices across adjacent thresholds yields a
full market-implied **probability distribution** over the upcoming print.
Trading opens one to five months before the release and closes at 8:25am ET
on release day.

## Construction plan (prototype already running)

1. **Pull** all events, contracts, and daily candlesticks via the API,
   storing raw JSON immutably (`src/pull_events.py`, `src/pull_candles.py`).
2. **Clean**: price each contract at the daily bid/ask midpoint (robust to
   stale trades in thin markets); drop quote-free contract-days; record
   spread, volume, and open interest as data-quality covariates.
3. **Construct** (`src/build_series.py`): for every event-day, difference
   the threshold prices into a probability distribution (enforcing
   monotonicity, renormalizing to 1, documented tail assumptions), and
   reduce it to an implied mean, implied SD, and the probability on each
   outcome.
4. **Fix horizons**: freeze the distribution 30/14/7/1 days before each
   release so events are comparable.
5. **Evaluate (Week 3)**: calibration curves, Brier scores against naive
   baselines, implied mean vs. economist consensus and the Cleveland Fed
   nowcast, and accuracy as a function of time-to-release.

All decisions are pre-registered in `DECISIONS.md`; re-running three scripts
reproduces every table.

## Expected challenges (all observed in the data already)

- **Thin early trading**: many contracts show no real quotes (0/100 bid/ask)
  weeks before the release; we flag and filter these by spread.
- **Prices are not exactly probabilities**: threshold prices can violate
  monotonicity or sum inconsistently by a few cents (fees/spreads); we
  record the violation size as a market-coherence measure rather than hide it.
- **Structure drift**: the series was renamed (`CPI-` → `KXCPI-`) in 2024,
  2021 events carry only 1–4 contracts (too few for a distribution), and
  threshold coverage widened during the 2022 inflation spike — tail
  assumptions matter more in some periods.
- **Messy settlement metadata**: the settled-value field changes format over
  the years ("0.5", "0.60", ".9%") and is missing for one event, which we
  reconstruct from the contract resolutions themselves.
- **Small event sample**: 61 monthly observations limit event-level
  statistical power; we pool across thresholds and days where valid.
