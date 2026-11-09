"""Free data: S&P 500 + Nasdaq-100 constituents (Wikipedia) and daily prices (Yahoo Finance via yfinance)."""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_CACHE = ROOT / "data" / "universe.csv"
ETFS = [("SPY", "SPDR S&P 500 ETF", "ETF"), ("QQQ", "Invesco QQQ (Nasdaq-100)", "ETF"),
        ("IWM", "iShares Russell 2000 ETF", "ETF"), ("DIA", "SPDR Dow Jones ETF", "ETF")]
WIKI = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "ndx": "https://en.wikipedia.org/wiki/Nasdaq-100",
}
UA = {"User-Agent": "hbb-scanner/1.0 (research script)"}


def _yahoo_symbol(sym: str) -> str:
    return str(sym).strip().replace(".", "-")   # BRK.B -> BRK-B


def _read_wiki_tables(url: str) -> list[pd.DataFrame]:
    import requests
    html = requests.get(url, headers=UA, timeout=30).text
    return pd.read_html(io.StringIO(html))


def refresh_universe() -> pd.DataFrame:
    """Pull current constituents; fall back to the cached list if Wikipedia is unreachable."""
    rows = []
    try:
        sp = _read_wiki_tables(WIKI["sp500"])[0]
        for _, r in sp.iterrows():
            rows.append((_yahoo_symbol(r["Symbol"]), r["Security"], r.get("GICS Sector", "")))
        ndx_tables = _read_wiki_tables(WIKI["ndx"])
        ndx = next(t for t in ndx_tables if any(str(c).lower() in ("ticker", "symbol") for c in t.columns))
        tcol = next(c for c in ndx.columns if str(c).lower() in ("ticker", "symbol"))
        ncol = next((c for c in ndx.columns if str(c).lower() in ("company", "security")), tcol)
        scol = next((c for c in ndx.columns if "sector" in str(c).lower()), None)
        for _, r in ndx.iterrows():
            rows.append((_yahoo_symbol(r[tcol]), r[ncol], r[scol] if scol else ""))
        u = pd.DataFrame(rows, columns=["ticker", "name", "sector"]).drop_duplicates("ticker")
        u = pd.concat([pd.DataFrame(ETFS, columns=["ticker", "name", "sector"]), u]).drop_duplicates("ticker")
        if len(u) > 400:
            UNIVERSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            u.to_csv(UNIVERSE_CACHE, index=False)
            return u.reset_index(drop=True)
    except Exception as e:  # noqa: BLE001
        print(f"[universe] Wikipedia refresh failed ({e}); using cached list")
    if UNIVERSE_CACHE.exists():
        return pd.read_csv(UNIVERSE_CACHE)
    return pd.DataFrame(ETFS, columns=["ticker", "name", "sector"])


def download_prices(tickers: list[str], period: str = "2y", chunk: int = 100, retries: int = 3) -> dict[str, pd.DataFrame]:
    """Daily OHLC, split-adjusted, not dividend-adjusted (same as TradingView's default stock chart)."""
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i + chunk]
        for attempt in range(retries):
            try:
                raw = yf.download(batch, period=period, interval="1d", group_by="ticker",
                                  auto_adjust=False, actions=False, threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                print(f"[prices] batch {i} attempt {attempt + 1} failed: {e}")
                time.sleep(10 * (attempt + 1))
        else:
            continue
        for t in batch:
            try:
                sub = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                sub = sub.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna(subset=["close"])
                if len(sub):
                    out[t] = sub
            except (KeyError, ValueError):
                pass
        time.sleep(1)
    return out
