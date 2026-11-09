"""Pick the ~25-delta option from Yahoo's free option chain (via yfinance).

Yahoo gives each contract's implied volatility but not its delta, so delta is computed here with
Black-Scholes (r = 4%, no dividend yield) from that contract's own IV. The 25-delta contract is the
strike whose delta is closest to +0.25 (call) or -0.25 (put) in the expiry closest to 30 days out.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

R = 0.04
TARGET_DAYS = 30
MIN_DAYS = 20
EXPIRY_HOUR_UTC = 21  # 4pm New York (EST); close enough for time-to-expiry


def _ncdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def bs_delta(spot: float, strike: np.ndarray, t: float, iv: np.ndarray, kind: str) -> np.ndarray:
    d1 = (np.log(spot / strike) + (R + 0.5 * iv ** 2) * t) / (iv * math.sqrt(t))
    nd1 = _ncdf(d1)
    return nd1 if kind == "call" else nd1 - 1


def choose_expiry(expiries: list[str], now: datetime) -> tuple[str, int] | None:
    best = None
    for e in expiries:
        exp_dt = datetime.strptime(e, "%Y-%m-%d").replace(hour=EXPIRY_HOUR_UTC, tzinfo=timezone.utc)
        dte = (exp_dt - now).days
        if dte < MIN_DAYS:
            continue
        score = abs(dte - TARGET_DAYS)
        if best is None or score < best[2]:
            best = (e, dte, score)
    return (best[0], best[1]) if best else None


def pick_25_delta(calls: pd.DataFrame, puts: pd.DataFrame, spot: float, expiry: str, now: datetime, kind: str) -> dict | None:
    exp_dt = datetime.strptime(expiry, "%Y-%m-%d").replace(hour=EXPIRY_HOUR_UTC, tzinfo=timezone.utc)
    t = max((exp_dt - now).total_seconds(), 3600) / (365 * 24 * 3600)
    chain = calls if kind == "call" else puts
    c = chain.copy()
    c = c[(c.impliedVolatility > 0.03) & (c.impliedVolatility < 3.0)]
    c = c[(c.bid.fillna(0) > 0) | (c.lastPrice.fillna(0) > 0)]
    if c.empty:
        return None
    c["delta"] = bs_delta(spot, c.strike.to_numpy(float), t, c.impliedVolatility.to_numpy(float), kind)
    target = 0.25 if kind == "call" else -0.25
    row = c.iloc[(c.delta - target).abs().argsort().iloc[0]]
    # ATM vol: average call/put IV at the strike nearest spot (for skew)
    atm_ivs = []
    for ch in (calls, puts):
        v = ch[(ch.impliedVolatility > 0.03) & (ch.impliedVolatility < 3.0)]
        if len(v):
            atm_ivs.append(float(v.iloc[(v.strike - spot).abs().argsort().iloc[0]].impliedVolatility))
    atm_iv = float(np.mean(atm_ivs)) if atm_ivs else None
    bid, ask = float(np.nan_to_num(row.bid)), float(np.nan_to_num(row.ask))
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(np.nan_to_num(row.lastPrice))
    iv = float(row.impliedVolatility)
    return dict(
        kind=kind, contract=str(row.contractSymbol), expiry=expiry, dte=int(round(t * 365)),
        strike=float(row.strike), otm_pct=float(abs(row.strike / spot - 1) * 100),
        bid=bid, ask=ask, mid=mid, cost=mid * 100,
        spread_pct=float((ask - bid) / mid * 100) if mid > 0 and bid > 0 and ask > 0 else None,
        iv=iv * 100, delta=float(row.delta), atm_iv=atm_iv * 100 if atm_iv else None,
        skew=(iv - atm_iv) * 100 if atm_iv else None,
        open_interest=int(row.openInterest) if pd.notna(row.openInterest) else 0,
        volume=int(row.volume) if pd.notna(row.volume) else 0,
    )


def fetch_25_delta(ticker: str, spot: float, kind: str, retries: int = 3, pause: float = 0.6) -> dict | None:
    import yfinance as yf
    now = datetime.now(timezone.utc)
    for attempt in range(retries):
        try:
            tk = yf.Ticker(ticker)
            exp = choose_expiry(list(tk.options), now)
            if not exp:
                return None
            ch = tk.option_chain(exp[0])
            time.sleep(pause)
            if ch.calls is None or ch.puts is None:
                return None
            return pick_25_delta(ch.calls, ch.puts, spot, exp[0], now, kind)
        except Exception as e:  # noqa: BLE001
            print(f"[options] {ticker} attempt {attempt + 1} failed: {e}")
            time.sleep(5 * (attempt + 1))
    return None
