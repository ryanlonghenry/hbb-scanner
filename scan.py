"""Daily HBB flip scan: S&P 500 + Nasdaq-100 (+ SPY/QQQ/IWM/DIA).

  python scan.py            # live run (needs internet: Wikipedia + Yahoo Finance)
  python scan.py --demo     # offline run on generated sample data, to check the pipeline/page

Writes docs/index.html (the dashboard), docs/data/latest.json, docs/data/scans/<date>.json,
and appends option vols to data/iv_history.csv.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import pandas as pd

from scanner import hbb
from scanner.render import render_dashboard

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
IV_HISTORY = ROOT / "data" / "iv_history.csv"
NEAR_DAYS = 3            # "close to flipping" = flips within this many flat days
MAX_OPTION_PULLS = 160   # keep the free API polite


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (o is None or math.isnan(o) or math.isinf(o)) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def iv_rank(hist: pd.DataFrame, ticker: str, kind: str, iv: float, min_obs: int = 60):
    h = hist[(hist.ticker == ticker) & (hist.kind == kind)].iv.dropna()
    if len(h) < min_obs:
        return None
    return float((h < iv).mean() * 100)


def is_final(scan_date: str) -> bool:
    """True once the US market has closed for the scan's bar (16:05 New York time or a later day)."""
    ny = datetime.now(ZoneInfo("America/New_York"))
    return ny.date().isoformat() > scan_date or ny.time() >= dtime(16, 5)


def tracked_tickers() -> list[str]:
    from scanner import tracker
    ts = []
    for path, cols in ((tracker.POSITIONS, tracker.POS_COLS), (tracker.PAPER, tracker.PAPER_COLS)):
        df = tracker._load(path, cols)
        if len(df):
            ts += df[df.status.astype(str).str.lower() == "open"].ticker.astype(str).tolist()
    return sorted(set(ts))


def run(demo: bool = False) -> dict:
    if demo:
        from scanner.demo import demo_universe, demo_prices, demo_option
        universe = demo_universe()
        prices = demo_prices(universe.ticker.tolist())
        fetch_option = demo_option
    else:
        from scanner.data import refresh_universe, download_prices
        from scanner.options import fetch_25_delta as fetch_option
        universe = refresh_universe()
        tickers = universe.ticker.tolist()
        tickers += [t for t in tracked_tickers() if t not in set(tickers)]   # positions/paper trades outside the index lists
        prices = download_prices(tickers)
    print(f"[scan] prices for {len(prices)} of {len(universe)} tickers")

    meta = universe.set_index("ticker")
    rows = []
    for t, df in prices.items():
        res = hbb.analyse(df)
        if res is None:
            continue
        res.update(ticker=t, name=str(meta.name.get(t, "")) if t in meta.index else "",
                   sector=str(meta.sector.get(t, "")) if t in meta.index else "",
                   is_etf=t in {"SPY", "QQQ", "IWM", "DIA"})
        rows.append(res)
    if not rows:
        raise SystemExit("no tickers analysed")
    scan_date = max(r["date"] for r in rows)
    rows = [r for r in rows if r["date"] == scan_date]   # drop stale/halted names
    final = is_final(scan_date)
    print(f"[scan] {scan_date} {'FINAL (after the close)' if final else 'INTRADAY (market still open)'}")

    # option pulls: today's flips first, then names closest to flipping, then the index ETFs
    def want(r):
        if r["flipped_today"]:
            return 0, r["ticker"]
        d = r["days_to_flip_flat"]
        if d is not None and d <= NEAR_DAYS:
            return 1, d
        if r["is_etf"]:
            return 2, 0
        return None
    queue = sorted([r for r in rows if want(r) is not None], key=want)[:MAX_OPTION_PULLS]
    hist = pd.read_csv(IV_HISTORY) if IV_HISTORY.exists() else pd.DataFrame(columns=["date", "ticker", "kind", "iv", "atm_iv", "skew"])
    new_hist = []
    for r in queue:
        direction = r["colour"] if r["flipped_today"] else r["next_colour"]
        kind = "call" if direction == "green" else "put"
        opt = fetch_option(r["ticker"], r["close"], kind)
        if opt:
            opt["iv_minus_rv"] = (opt["iv"] - r["rv20"]) if r.get("rv20") else None
            opt["iv_rank"] = iv_rank(hist, r["ticker"], kind, opt["iv"])
            new_hist.append(dict(date=scan_date, ticker=r["ticker"], kind=kind, iv=opt["iv"],
                                 atm_iv=opt.get("atm_iv"), skew=opt.get("skew")))
        r["option"] = opt
    print(f"[scan] option chains pulled: {sum(1 for r in queue if r.get('option'))} of {len(queue)}")

    if new_hist and not demo:
        hist = pd.concat([hist, pd.DataFrame(new_hist)], ignore_index=True)
        hist = hist.drop_duplicates(["date", "ticker", "kind"], keep="last")
        IV_HISTORY.parent.mkdir(parents=True, exist_ok=True)
        hist.to_csv(IV_HISTORY, index=False)

    from scanner import tracker
    if demo:
        track = dict(paper_stats={}, paper_trades=[], positions=[])
    else:
        from scanner.options import fetch_chain
        track = tracker.update(rows, scan_date, final, fetch_chain)

    index_rows = [r for r in rows if r["ticker"] in set(universe.ticker)]
    green = sum(r["colour"] == "green" for r in index_rows)
    out = _clean(dict(
        scan_date=scan_date,
        final=final,
        **track,
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        demo=demo,
        settings=dict(hma=hbb.HMA_LEN, bands=f"{hbb.BB_MULT} x stdev({hbb.BB_LEN})", ma=hbb.MA_LEN,
                      max_stretch_atr=hbb.MAX_STRETCH, near_days=NEAR_DAYS, option_target_days=30),
        breadth=dict(total=len(index_rows), green=green, red=len(index_rows) - green,
                     green_flips=sum(r["flipped_today"] and r["colour"] == "green" for r in index_rows),
                     red_flips=sum(r["flipped_today"] and r["colour"] == "red" for r in index_rows)),
        rows=sorted(index_rows, key=lambda r: r["ticker"]),
    ))
    (DOCS / "data" / "scans").mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out, separators=(",", ":"))
    (DOCS / "data" / "latest.json").write_text(payload)
    if not demo and final:
        (DOCS / "data" / "scans" / f"{scan_date}.json").write_text(payload)
    (DOCS / "index.html").write_text(render_dashboard(out), encoding="utf-8")
    print(f"[scan] {scan_date}: {out['breadth']} -> docs/index.html")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="offline sample data")
    run(ap.parse_args().demo)
