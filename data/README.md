# Data guide

Every number in this project can be traced from a raw API response to a
row in a results table. Raw files are never edited by hand; every fix is a
rule in `src/` (see `DECISIONS.md`). The snapshot committed here was pulled
from Kalshi on **2026-07-21** and from the Cleveland Fed and BLS on
**2026-08-04**.

```
data/
  raw/                Kalshi API responses, untouched          (src/pull_events.py, src/pull_candles.py)
    events.json       all 66 monthly events in the KXCPI series
    markets/          one file per event: its threshold contracts (528 in total)
    candles/          one file per contract: daily candlesticks from listing to settlement
  external/           benchmark inputs, untouched
    cleveland_nowcast_month.json   Cleveland Fed nowcast archive (chart JSON)   (src/pull_cleveland_nowcast.py)
    cleveland_nowcast_daily.csv    the same, flattened to one row per nowcast day
    bls_cpi_cusr0000sa0.json       BLS CPI-U index, current vintage             (src/pull_bls_cpi.py)
  clean/              derived tables                            (src/pull_events.py, src/build_series.py)
    events_table.csv
    market_day.csv
    distribution_day.csv
    forecast_snapshots.csv
```

Sizes: `data/raw` is about 29 MB, `data/external` 7.5 MB. Everything is
committed so the whole analysis rebuilds offline with `make`.

## Conventions worth knowing

- **Tickers.** `KXCPI-26MAR` is the event on March 2026 CPI; events before
  the 2024 rename use the old `CPI-` prefix (`CPI-22JUL`). A contract ticker
  adds the threshold: `KXCPI-26MAR-T0.8` = "Will March 2026 CPI rise more
  than 0.8%?". Negative thresholds are written `T-0.3` in new events and
  `TN0.3` in 2022-era events.
- **Prices** are in dollars per $1-payout contract (0–1) for the YES side,
  so a price of 0.78 is a 78% market-implied probability that CPI exceeds
  the threshold. **Volumes** are numbers of contracts, not dollars.
- **Two API tiers.** Data older than about three months is served by
  `/historical/*` endpoints whose JSON uses different field names for the
  same quantities (`close` vs `close_dollars`, `volume` vs `volume_fp`).
  The pull scripts route between tiers; the parsers accept both.
- **Quotes of 0.00 bid / 1.00 ask** mean nobody was quoting; those
  contract-days are treated as uninformative (spread filter).
- **Daily candles end at midnight ET** and are labeled with the ET calendar
  day they cover. The release date is the ET date of market close (8:25 am
  ET on the scheduled BLS publication day).

## Raw Kalshi files

`events.json` — one object per event. Key fields: `event_ticker`,
`series_ticker` (`KXCPI`), `title` / `sub_title`, `category`,
`mutually_exclusive` (false: contracts are overlapping thresholds, not
exclusive ranges), `settlement_sources` (Bureau of Labor Statistics).

`markets/<event>.json` — one object per threshold contract.

| field | meaning |
|---|---|
| `ticker`, `event_ticker` | contract ID and the event it belongs to |
| `title`, `yes_sub_title` | the question in words; short label of the YES outcome ("Above 0.8%") |
| `market_type` | `binary`: pays $1 if YES, $0 if NO |
| `strike_type`, `floor_strike` | `greater` and the threshold as a number; blank on historical-tier markets, which is why the threshold is parsed from the ticker |
| `open_time`, `close_time` | trading window (UTC); close is 8:25 am ET on release day |
| `settlement_ts`, `status` | when the exchange settled; `finalized` = paid out |
| `result` | `yes` / `no` settlement; empty if not yet settled |
| `expiration_value` | the CPI print the contract settled on, as a free-form string ("0.5", "0.60", ".9%"); normalized by `src/cpi_values.py` |
| `volume` / `volume_fp`, `open_interest` / `open_interest_fp` | lifetime contracts traded; contracts still open |
| `liquidity_dollars` | resting order-book depth at download time (not meaningful historically) |

`candles/<ticker>.json` — one object per trading day.

| field | meaning |
|---|---|
| `end_period_ts` | end of the daily candle, Unix seconds (midnight ET) |
| `yes_bid.{open,high,low,close}` | best price buyers offered for YES (live tier: `open_dollars`, …) |
| `yes_ask.{open,high,low,close}` | lowest price sellers accepted for YES; always ≥ bid, the gap is the spread |
| `price.{…}` | last-trade OHLC; empty when nothing traded, and can be days stale — the reason the pipeline prices at the bid/ask midpoint |
| `volume` / `volume_fp` | contracts traded that day |
| `open_interest` / `open_interest_fp` | contracts held open at end of day |

## Clean tables

### `events_table.csv` — one row per monthly event (66 rows)

| column | meaning |
|---|---|
| `event_ticker`, `title` | event ID and name |
| `n_markets` | number of threshold contracts (1–4 in 2021, 5–15 later) |
| `first_open_time`, `close_time` | trading window (UTC) |
| `settled` | true once every contract has a yes/no result (61 events) |
| `actual_cpi_mom` | the settled first-release print, normalized; inferred from contract results for CPI-23OCT |
| `total_volume` | lifetime contracts traded across the event |

### `market_day.csv` — one row per contract per day (25,199 rows, 528 contracts)

| column | meaning |
|---|---|
| `event_ticker`, `ticker` | event and contract |
| `threshold` | the contract's x, parsed from the ticker: pays if CPI > x |
| `date` | ET trading day |
| `days_to_release` | days before the CPI release (release day = 0); the alignment variable across months |
| `yes_bid`, `yes_ask` | end-of-day best bid and ask |
| `mid` | (bid + ask) / 2 — the price used throughout |
| `implied_prob_above` | identical to `mid`, named for what it is: the market-implied P(CPI > threshold) |
| `spread` | ask − bid; rows with spread > 0.90 are uninformative |
| `volume`, `open_interest` | that day's trades; open positions at end of day |
| `settled`, `actual_cpi_mom`, `release_date` | event-level fields carried on every row |

Rows are limited to 0–150 days before release.

### `distribution_day.csv` — one row per event per day (3,484 rows)

The market's complete forecast of one month's CPI on one day, obtained by
differencing `implied_prob_above` across the event's thresholds.

| column | meaning |
|---|---|
| `event_ticker`, `date`, `days_to_release`, `release_date` | keys and alignment |
| `settled`, `actual_cpi_mom` | evaluation sample flag and ground truth |
| `implied_mean` | probability-weighted average print: the market's point forecast |
| `implied_sd` | standard deviation of the implied distribution: the market's uncertainty |
| `prob_true_bin` | probability assigned that day to the outcome that actually happened |
| `abs_error_mean` | |implied_mean − actual| in percentage points |
| `prob_sum_raw` | sum of bin probabilities before the safeguard renormalization; exactly 1 on every row (telescoping), kept as a verification column |
| `mono_violation` | size of the worst monotonicity violation repaired that day (a higher threshold priced above a lower one); the market-coherence measure |
| `n_thresholds` | informative contracts (spread ≤ 0.90) in the distribution |
| `avg_spread`, `day_volume` | liquidity gauges for that event-day |

### `forecast_snapshots.csv` — `distribution_day` frozen at fixed horizons (226 rows)

Same columns plus `horizon` ∈ {30, 14, 7, 1}: the row of `distribution_day`
closest to that many days before release (within ±3 days), for each of the
57 settled events with a distribution.

## External benchmark files

`cleveland_nowcast_daily.csv` — `target_month`, `nowcast_date`,
`cpi_mom_nowcast` (the Cleveland Fed model's month-over-month CPI nowcast
published that day), `cpi_mom_actual_clevelandfed` (the print as later
recorded by the Fed). 4,290 rows, target months 2013-08 to 2026-06. This is
a daily archive, so every Kalshi snapshot can be matched to the nowcast
that was actually available on that date.

`bls_cpi_cusr0000sa0.json` — BLS public API response for CPI-U, all items,
seasonally adjusted, 2020–2026, current vintage. Used only to flag months
whose first-release print was later revised (`results/true_cpi.csv`); the
evaluation always grades against the first release. October 2025 is absent
(never published, federal shutdown).

## Results tables (`results/`)

`comparison.csv` — one row per settled event per horizon (226 rows), every
forecaster read on the same `snapshot_date`: `actual_first_release`,
`kalshi_implied_mean`, `cleveland_nowcast` (latest nowcast on or before the
snapshot date), `naive_last_print` and `naive_avg_12m` (built only from
prints already released by the snapshot date), `consensus_survey` (empty:
no free archive of the economist consensus exists), and `abs_err_*` for
each. `accuracy_by_horizon.csv`, `diebold_mariano.csv` and `evaluation.md`
are produced from it by `src/evaluate.py`.
