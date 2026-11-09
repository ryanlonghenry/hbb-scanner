"""Hull Bollinger Bands (HBB) math, matching the TradingView Pine v5 script
"Hull Bollinger Bands" by BeanThereBoughtThat (MPL-2.0), plus flip forecasting.

Colour rule (Pine): lime if hma > hma[1], else red (a flat bar counts as red).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HMA_LEN = 34
BB_LEN = 34
BB_MULT = 2.0
MA_LEN = 50          # 50-day stretch filter
ATR_LEN = 14
MAX_STRETCH = 1.0    # ATRs past the 50-day in the trade's direction before a flip is "stretched"
MAX_FLAT_DAYS = 30   # cap for the "days to flip if price stays flat" countdown


def pine_round(x: float) -> int:
    """Pine math.round: half away from zero (inputs here are positive)."""
    return int(np.floor(x + 0.5))


def wma(x: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.wma: linear weights, newest bar weighted n. NaN until n bars exist."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    k = np.arange(n, 0, -1, dtype=float)  # convolution kernel: newest gets weight n
    out[n - 1:] = np.convolve(x, k, mode="valid") / k.sum()
    return out


def hma(close: np.ndarray, length: int = HMA_LEN) -> np.ndarray:
    half = wma(close, pine_round(length / 2))
    full = wma(close, length)
    return wma(2 * half - full, pine_round(np.sqrt(length)))


def rma(x: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.rma: seeded with the SMA of the first n values, then alpha = 1/n."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    valid = np.where(~np.isnan(x))[0]
    if len(valid) < n:
        return out
    s = valid[0]
    out[s + n - 1] = np.mean(x[s:s + n])
    for i in range(s + n, len(x)):
        out[i] = out[i - 1] + (x[i] - out[i - 1]) / n
    return out


def atr(high, low, close, n: int = ATR_LEN) -> np.ndarray:
    high, low, close = (np.asarray(a, dtype=float) for a in (high, low, close))
    prev = np.r_[np.nan, close[:-1]]
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev), np.abs(low - prev)]), axis=0)
    tr[0] = high[0] - low[0]
    return rma(tr, n)


def bands(close: np.ndarray, h: np.ndarray, length: int = BB_LEN, mult: float = BB_MULT):
    dev = mult * pd.Series(close).rolling(length).std(ddof=0).to_numpy()  # ta.stdev = population
    return h + dev, h - dev


def colour(h: np.ndarray) -> np.ndarray:
    """+1 green, -1 red, 0 not enough data."""
    prev = np.r_[np.nan, h[:-1]]
    c = np.where(h > prev, 1, -1)
    c[np.isnan(h) | np.isnan(prev)] = 0
    return c


def _hma_last(close: np.ndarray, length: int = HMA_LEN) -> float:
    """HMA value on the last bar only (fast path for forecasting)."""
    n_half, n_sq = pine_round(length / 2), pine_round(np.sqrt(length))
    need = length + n_sq - 1
    c = np.asarray(close[-need:], dtype=float)
    return float(hma(c, length)[-1])


def flip_price_tomorrow(close: np.ndarray, length: int = HMA_LEN) -> float:
    """Close needed on the next bar to change colour.
    HMA tomorrow is linear in tomorrow's close: hma1 = a + b * c.
    Green now -> turns red if hma1 <= hma0, i.e. close <= this price.
    Red now   -> turns green if hma1 > hma0, i.e. close > this price."""
    close = np.asarray(close, dtype=float)
    h0 = _hma_last(close, length)
    a = _hma_last(np.r_[close, 0.0], length)
    b = _hma_last(np.r_[close, 1.0], length) - a
    return (h0 - a) / b


def days_to_flip_if_flat(close: np.ndarray, length: int = HMA_LEN, cap: int = MAX_FLAT_DAYS):
    """Trading days until the colour changes if every future close equals today's close.
    1 = it flips on tomorrow's close even if price doesn't move. None = not within the cap."""
    close = np.asarray(close, dtype=float)
    hs = [_hma_last(close, length)]
    prev_h = _hma_last(close[:-1], length)
    now_green = hs[0] > prev_h
    c = close.copy()
    for k in range(1, cap + 1):
        c = np.r_[c, close[-1]]
        h = _hma_last(c, length)
        green = h > hs[-1]
        if green != now_green:
            return k
        hs.append(h)
    return None


def analyse(df: pd.DataFrame) -> dict | None:
    """df: daily bars with columns open, high, low, close (oldest first), last row = latest completed bar."""
    df = df.dropna(subset=["close"])
    if len(df) < max(HMA_LEN + 6, MA_LEN) + 5:
        return None
    o, hi, lo, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    hi = np.where(np.isnan(hi), c, hi)
    lo = np.where(np.isnan(lo), c, lo)
    h = hma(c)
    up, dn = bands(c, h)
    col = colour(h)
    a = atr(hi, lo, c)
    sma = pd.Series(c).rolling(MA_LEN).mean().to_numpy()
    if col[-1] == 0 or np.isnan(a[-1]) or np.isnan(sma[-1]):
        return None
    flipped = col[-1] != col[-2] and col[-2] != 0
    # bars in current colour (including today)
    run = 1
    while run < len(col) and col[-1 - run] == col[-1]:
        run += 1
    stretch = (c[-1] - sma[-1]) / a[-1]
    green = col[-1] == 1
    fp = flip_price_tomorrow(c)
    move = fp - c[-1]
    lr = np.diff(np.log(c[-21:]))
    rv20 = float(np.std(lr, ddof=1) * np.sqrt(252) * 100) if len(lr) >= 20 else None
    # filter status for a flip in direction d (+1 green/long, -1 red/short) at today's close
    take_long = stretch <= MAX_STRETCH
    take_short = stretch >= -MAX_STRETCH
    return dict(
        date=str(pd.Timestamp(df.index[-1]).date()),
        close=float(c[-1]),
        colour="green" if green else "red",
        flipped_today=bool(flipped),
        bars_in_colour=int(run),
        hma=float(h[-1]),
        upper=float(up[-1]),
        lower=float(dn[-1]),
        atr=float(a[-1]),
        atr_pct=float(a[-1] / c[-1] * 100),
        sma50=float(sma[-1]),
        stretch_atr=float(stretch),
        # today's flip (if any) judged by the 50-day rule
        filter_today=(("take" if (take_long if green else take_short) else "stretched") if flipped else None),
        # next flip would be the opposite colour
        next_colour="red" if green else "green",
        flip_close_tomorrow=float(fp),
        flip_move_pct=float(move / c[-1] * 100),
        flip_move_atr=float(move / a[-1]),
        days_to_flip_flat=days_to_flip_if_flat(c),
        filter_if_next_flip_now=("take" if (take_short if green else take_long) else "stretched"),
        rv20=rv20,
    )
