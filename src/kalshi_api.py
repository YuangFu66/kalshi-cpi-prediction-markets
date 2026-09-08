"""Minimal helper for Kalshi's public trade API (no auth needed for market data).

Kalshi partitions data into a live tier (~last 3 months) and a historical tier.
Every fetcher here tries the live endpoint first and falls back to the
historical one, so callers never need to care which tier a market is in.
"""
import time
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
THROTTLE_SECONDS = 0.12  # stay well under Kalshi's public rate limit

_session = requests.Session()


def get_json(path, **params):
    """GET BASE+path with retries; returns parsed JSON."""
    for attempt in range(5):
        time.sleep(THROTTLE_SECONDS)
        r = _session.get(BASE + path, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def paginate(path, list_key, **params):
    """Follow cursor pagination, concatenating the list under list_key."""
    items, cursor = [], None
    while True:
        d = get_json(path, cursor=cursor, **params)
        items += d.get(list_key, [])
        cursor = d.get("cursor")
        if not cursor:
            return items


def get_all_events(series_ticker):
    return paginate("/events", "events", series_ticker=series_ticker, limit=200)


def get_markets_for_event(event_ticker):
    """Markets for one event; live tier first, then historical tier."""
    ms = paginate("/markets", "markets", event_ticker=event_ticker, limit=100)
    if not ms:
        ms = paginate("/historical/markets", "markets",
                      event_ticker=event_ticker, limit=100)
    return ms


def get_daily_candles(series_ticker, market_ticker, start_ts, end_ts):
    """Daily candlesticks for one market; live tier first, then historical.

    Markets older than the historical cutoff 404 on the live endpoint,
    so a 404 (as well as an empty result) triggers the historical fallback.
    """
    params = dict(start_ts=start_ts, end_ts=end_ts, period_interval=1440)
    candles = []
    try:
        d = get_json(f"/series/{series_ticker}/markets/{market_ticker}/candlesticks",
                     **params)
        candles = d.get("candlesticks", [])
    except requests.HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            raise
    if not candles:
        try:
            d = get_json(f"/historical/markets/{market_ticker}/candlesticks", **params)
            candles = d.get("candlesticks", [])
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 404:
                raise
    return candles
