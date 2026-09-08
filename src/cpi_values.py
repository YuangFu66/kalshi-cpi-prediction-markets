"""Normalize the settled CPI value reported by Kalshi.

Kalshi's expiration_value field is a free-form string whose format drifted
over the years: "0.5", "0.50", "0.5%", ".9%". One event (CPI-23OCT) reports
no usable value at all, so we also infer the print from the market results:
a threshold market "CPI > x" resolving NO means the print was <= x, and YES
means it was > x; with contiguous 0.1-spaced thresholds this pins the value.
"""


def parse_actual(raw):
    """'0.60' -> 0.6, '.9%' -> 0.9, '' -> None."""
    if raw is None:
        return None
    s = str(raw).strip().rstrip("%").strip()
    if not s:
        return None
    try:
        return round(float(s), 1)
    except ValueError:
        return None


def settled_value(markets, thresholds_by_ticker):
    """Best-effort settled CPI print for one event's markets.

    Prefers the (normalized) expiration_value when all markets agree;
    otherwise infers it from yes/no results across thresholds.
    """
    vals = {parse_actual(m.get("expiration_value")) for m in markets}
    vals.discard(None)
    if len(vals) == 1:
        return vals.pop()

    yes = [thresholds_by_ticker[m["ticker"]] for m in markets
           if m.get("result") == "yes" and m["ticker"] in thresholds_by_ticker]
    no = [thresholds_by_ticker[m["ticker"]] for m in markets
          if m.get("result") == "no" and m["ticker"] in thresholds_by_ticker]
    if not no:
        return None
    lo = max(yes) if yes else None
    hi = min(no)
    # contiguous grid: print > lo and <= hi with hi exactly one step above lo
    if lo is not None and abs(hi - lo - 0.1) < 1e-6:
        return round(hi, 1)
    return None
