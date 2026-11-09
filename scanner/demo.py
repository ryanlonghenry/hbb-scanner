"""Offline sample data so the pipeline and dashboard can be checked without internet. Not real prices."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from scanner.options import choose_expiry, pick_25_delta, bs_delta  # noqa: F401

_rng = np.random.default_rng(7)


def demo_universe() -> pd.DataFrame:
    rows = [("SPY", "SPDR S&P 500 ETF", "ETF"), ("QQQ", "Invesco QQQ (Nasdaq-100)", "ETF"),
            ("IWM", "iShares Russell 2000 ETF", "ETF"), ("DIA", "SPDR Dow Jones ETF", "ETF")]
    rows += [(f"DEMO{i:02d}", f"Sample Company {i}", ["Tech", "Health", "Energy", "Financials"][i % 4]) for i in range(60)]
    return pd.DataFrame(rows, columns=["ticker", "name", "sector"])


def demo_prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=500)
    out = {}
    for t in tickers:
        vol = _rng.uniform(0.012, 0.03)
        drift = _rng.normal(0, 0.0006)
        lr = _rng.normal(drift, vol, len(idx))
        # add a few trend regimes so flips/near-flips appear
        lr += np.repeat(_rng.normal(0, 0.004, len(idx) // 25 + 1), 25)[: len(idx)]
        c = 100 * np.exp(np.cumsum(lr))
        o = c * np.exp(_rng.normal(0, vol / 3, len(idx)))
        h = np.maximum(o, c) * (1 + np.abs(_rng.normal(0, vol / 2, len(idx))))
        lo = np.minimum(o, c) * (1 - np.abs(_rng.normal(0, vol / 2, len(idx))))
        out[t] = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)
    return out


def demo_option(ticker: str, spot: float, kind: str) -> dict | None:
    now = datetime.now(timezone.utc)
    exps = [(pd.Timestamp(now.date()) + pd.Timedelta(days=d)).strftime("%Y-%m-%d") for d in (9, 16, 23, 30, 37, 51, 79)]
    exp, dte = choose_expiry(exps, now)
    strikes = np.round(np.arange(0.7, 1.3, 0.01) * spot, 2)
    base_iv = _rng.uniform(0.18, 0.45)
    mny = np.log(strikes / spot)
    iv = base_iv + 0.15 * mny ** 2 - 0.05 * mny
    from scanner.options import R
    import math
    t = dte / 365

    def price(k, s, kd):
        d1 = (math.log(spot / k) + (R + 0.5 * s * s) * t) / (s * math.sqrt(t)); d2 = d1 - s * math.sqrt(t)
        from scipy.stats import norm
        return spot * norm.cdf(d1) - k * math.exp(-R * t) * norm.cdf(d2) if kd == "call" else k * math.exp(-R * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)

    def chain(kd):
        p = np.array([price(k, s, kd) for k, s in zip(strikes, iv)])
        return pd.DataFrame(dict(contractSymbol=[f"{ticker}{exp.replace('-', '')}{'C' if kd == 'call' else 'P'}{int(k * 1000):08d}" for k in strikes],
                                 strike=strikes, lastPrice=p, bid=np.maximum(p * 0.97, 0.01), ask=p * 1.03 + 0.01,
                                 impliedVolatility=iv, openInterest=_rng.integers(0, 5000, len(strikes)),
                                 volume=_rng.integers(0, 800, len(strikes))))
    return pick_25_delta(chain("call"), chain("put"), spot, exp, now, kind)
