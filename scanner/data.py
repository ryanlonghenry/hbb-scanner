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
# Daily-updated constituent lists published on GitHub (github.com/yfiua/index-constituents)
GH_LISTS = {
    "sp500": "https://raw.githubusercontent.com/yfiua/index-constituents/main/docs/constituents-sp500.csv",
    "ndx": "https://raw.githubusercontent.com/yfiua/index-constituents/main/docs/constituents-nasdaq100.csv",
}
UA = {"User-Agent": "hbb-scanner/1.0 (+https://github.com/ryanlonghenry/hbb-scanner)"}


def _yahoo_symbol(sym: str) -> str:
    return str(sym).strip().replace(".", "-")   # BRK.B -> BRK-B


def _read_wiki_tables(url: str) -> list[pd.DataFrame]:
    import requests
    html = requests.get(url, headers=UA, timeout=30).text
    return pd.read_html(io.StringIO(html))


def _from_github() -> pd.DataFrame:
    import requests
    frames = []
    for url in GH_LISTS.values():
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        frames.append(pd.read_csv(io.StringIO(r.content.decode("utf-8"))))
    u = pd.concat(frames).rename(columns={"Symbol": "ticker", "Name": "name"})
    u["ticker"] = u.ticker.map(_yahoo_symbol)
    return u.drop_duplicates("ticker")[["ticker", "name"]]


def refresh_universe() -> pd.DataFrame:
    """Current S&P 500 + Nasdaq-100 members.
    Order: GitHub daily lists -> Wikipedia -> the list saved in data/universe.csv."""
    cached = pd.read_csv(UNIVERSE_CACHE) if UNIVERSE_CACHE.exists() else None
    etfs = pd.DataFrame(ETFS, columns=["ticker", "name", "sector"])
    try:
        u = _from_github()
        if len(u) > 400:
            if cached is not None:   # keep sectors from the saved list
                u = u.merge(cached[["ticker", "sector"]], on="ticker", how="left")
            u = pd.concat([etfs, u]).drop_duplicates("ticker").fillna({"sector": ""})
            UNIVERSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            u.to_csv(UNIVERSE_CACHE, index=False)
            print(f"[universe] {len(u)} tickers from GitHub lists")
            return u.reset_index(drop=True)
    except Exception as e:  # noqa: BLE001
        print(f"[universe] GitHub lists failed ({e}); trying Wikipedia")
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
            print(f"[universe] {len(u)} tickers from Wikipedia")
            return u.reset_index(drop=True)
    except Exception as e:  # noqa: BLE001
        print(f"[universe] Wikipedia failed ({e}); using the saved list")
    if cached is not None and len(cached) > 400:
        print(f"[universe] {len(cached)} tickers from data/universe.csv")
        return cached
    print("[universe] WARNING: no member list available, scanning index ETFs only")
    return etfs


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
