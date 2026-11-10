"""Forward test + position tracking.

Paper test (data/paper_trades.csv, automatic):
  * every flip on a FINAL (after-the-close) scan opens one paper contract of the 25-delta option at the mid
  * open trades are marked at the mid on every final scan
  * a trade closes at that day's mid when the Hull colour turns back (green -> red for a call,
    red -> green for a put), or at intrinsic value once it reaches expiry

My positions (data/positions.csv, typed in by you): marked the same way, with an EXIT flag when the colour
turns back. They are never closed automatically: set status to "closed" (and exit_price) yourself.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "data" / "paper_trades.csv"
POSITIONS = ROOT / "data" / "positions.csv"
MULT = 100

PAPER_COLS = ["id", "ticker", "side", "signal_date", "contract", "kind", "strike", "expiry", "entry_mid",
              "entry_underlying", "filter", "iv", "skew", "iv_minus_rv", "status", "last_date", "last_mid",
              "last_underlying", "exit_date", "exit_mid", "exit_reason"]
POS_COLS = ["ticker", "contract", "kind", "strike", "expiry", "qty", "entry_date", "entry_price",
            "entry_underlying", "status", "exit_date", "exit_price", "notes"]


def _load(path: Path, cols: list[str]) -> pd.DataFrame:
    if path.exists():
        text = ["id", "ticker", "side", "signal_date", "contract", "kind", "expiry", "filter", "status", "last_date",
                "exit_date", "exit_reason", "entry_date", "notes"]
        df = pd.read_csv(path, dtype={c: object for c in text})
        for c in cols:
            if c not in df.columns:
                df[c] = np.nan
        return df[cols]
    return pd.DataFrame(columns=cols)


def _mark(t: str, contract: str, kind: str, strike: float, expiry: str, spot: float | None,
          scan_date: str, chain_cache: dict, fetch_chain) -> dict:
    """Current value of one contract: chain mid, or intrinsic value on/after expiry."""
    if scan_date >= expiry:
        if spot is None:
            return dict(mid=None, bid=None, ask=None, source="expired, no price")
        intrinsic = max(0.0, (strike - spot) if kind == "put" else (spot - strike))
        return dict(mid=intrinsic, bid=None, ask=None, source="expired (intrinsic)")
    key = (t, expiry)
    if key not in chain_cache:
        chain_cache[key] = fetch_chain(t, expiry)
    ch = chain_cache[key]
    if ch is None:
        return dict(mid=None, bid=None, ask=None, source="no chain")
    df = ch[0] if kind == "call" else ch[1]
    row = df[df.contractSymbol == contract]
    if row.empty:
        return dict(mid=None, bid=None, ask=None, source="contract not listed")
    from scanner.options import quote
    q = quote(row.iloc[0])
    return dict(mid=q["mid"], bid=q["bid"], ask=q["ask"], source="mid" if q["two_sided"] else "last trade")


def _direction(kind: str) -> str:
    return "green" if kind == "call" else "red"


def update(rows: list[dict], scan_date: str, final: bool, fetch_chain, extra_spots: dict | None = None) -> dict:
    by_t = {r["ticker"]: r for r in rows}
    spots = {t: r["close"] for t, r in by_t.items()}
    spots.update(extra_spots or {})
    cache: dict = {}

    # ---------------- paper test ----------------
    paper = _load(PAPER, PAPER_COLS)
    if final:
        have = set(paper.id.astype(str))
        new = []
        for r in rows:
            o = r.get("option")
            if not r["flipped_today"] or not o or not o.get("mid") or o["mid"] <= 0:
                continue
            tid = f"{r['ticker']}-{scan_date}"
            if tid in have:
                continue
            new.append(dict(id=tid, ticker=r["ticker"], side="long" if r["colour"] == "green" else "short",
                            signal_date=scan_date, contract=o["contract"], kind=o["kind"], strike=o["strike"],
                            expiry=o["expiry"], entry_mid=o["mid"], entry_underlying=r["close"],
                            filter=r["filter_today"], iv=o.get("iv"), skew=o.get("skew"),
                            iv_minus_rv=o.get("iv_minus_rv"), status="open", last_date=scan_date,
                            last_mid=o["mid"], last_underlying=r["close"]))
            # seed the cache with nothing: entry is today's pick, so no extra fetch is needed today
        if new:
            paper = pd.concat([paper, pd.DataFrame(new)], ignore_index=True)
    for c in ("status", "last_date", "exit_date", "exit_reason", "filter"):
        paper[c] = paper[c].astype(object)
        print(f"[paper] opened {len(new)} new paper trades")

    closed_now = 0
    for i, p in paper[paper.status == "open"].iterrows():
        if p.signal_date == scan_date:
            continue                                   # opened today: already marked at entry
        spot = spots.get(p.ticker)
        m = _mark(p.ticker, p.contract, p.kind, float(p.strike), str(p.expiry), spot, scan_date, cache, fetch_chain)
        if m["mid"] is not None:
            paper.at[i, "last_mid"] = m["mid"]
            paper.at[i, "last_date"] = scan_date
        if spot is not None:
            paper.at[i, "last_underlying"] = spot
        if not final:
            continue
        r = by_t.get(p.ticker)
        reason = None
        if scan_date >= str(p.expiry):
            reason = "expiry"
        elif r is not None and r["colour"] != _direction(p.kind):
            reason = "colour flipped back"
        if reason:
            paper.at[i, "status"] = "closed"
            paper.at[i, "exit_date"] = scan_date
            paper.at[i, "exit_mid"] = paper.at[i, "last_mid"]
            paper.at[i, "exit_reason"] = reason
            closed_now += 1
    if final:
        print(f"[paper] closed {closed_now} paper trades")
    PAPER.parent.mkdir(parents=True, exist_ok=True)
    paper.to_csv(PAPER, index=False)

    # ---------------- my positions ----------------
    pos = _load(POSITIONS, POS_COLS)
    pos_out = []
    for _, p in pos.iterrows():
        if str(p.status).lower() != "open":
            entry_px, exit_px = float(p.entry_price), p.exit_price
            pnl = (float(exit_px) - entry_px) * MULT * float(p.qty) if pd.notna(exit_px) else None
            pos_out.append(dict(p.to_dict(), mid=exit_px, pnl=pnl, pnl_pct=(float(exit_px) / entry_px - 1) * 100 if pd.notna(exit_px) else None))
            continue
        spot = spots.get(p.ticker)
        m = _mark(p.ticker, p.contract, p.kind, float(p.strike), str(p.expiry), spot, scan_date, cache, fetch_chain)
        r = by_t.get(p.ticker)
        colour = r["colour"] if r else None
        exit_signal = colour is not None and colour != _direction(p.kind)
        trigger = None
        if r and not exit_signal:
            trigger = r["flip_close_tomorrow"]        # close that flips it back against the trade
        dte = (pd.Timestamp(p.expiry) - pd.Timestamp(scan_date)).days
        entry_px = float(p.entry_price)
        pnl = (m["mid"] - entry_px) * MULT * float(p.qty) if m["mid"] is not None else None
        pos_out.append(dict(p.to_dict(), underlying=spot, bid=m["bid"], ask=m["ask"], mid=m["mid"],
                            mark_source=m["source"], pnl=pnl,
                            pnl_pct=(m["mid"] / entry_px - 1) * 100 if m["mid"] is not None else None,
                            colour=colour, exit_signal=exit_signal, trigger=trigger, dte=dte,
                            days_to_flip_flat=r["days_to_flip_flat"] if r else None,
                            breakeven=float(p.strike) - entry_px if p.kind == "put" else float(p.strike) + entry_px))

    # ---------------- summary for the page ----------------
    def stats(df: pd.DataFrame) -> dict:
        if df.empty:
            return dict(n=0)
        val = np.where(df.status == "closed", df.exit_mid, df.last_mid).astype(float)
        pnl = (val - df.entry_mid.astype(float)) * MULT
        closed = df.status == "closed"
        return dict(n=int(len(df)), open=int((~closed).sum()), closed=int(closed.sum()),
                    pnl=float(np.nansum(pnl)), cost=float((df.entry_mid.astype(float) * MULT).sum()),
                    win_closed=float((pnl[closed] > 0).mean() * 100) if closed.any() else None,
                    big=int(((val / df.entry_mid.astype(float)) >= 3).sum()))
    groups = {"All": paper, "Take": paper[paper["filter"] == "take"], "Stretched": paper[paper["filter"] == "stretched"],
              "Calls": paper[paper.kind == "call"], "Puts": paper[paper.kind == "put"]}
    trades = []
    for _, p in paper.iterrows():
        val = p.exit_mid if p.status == "closed" else p.last_mid
        d = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in p.to_dict().items()}
        d["value"] = float(val) if pd.notna(val) else None
        d["pnl"] = (float(val) - float(p.entry_mid)) * MULT if pd.notna(val) else None
        d["pnl_pct"] = (float(val) / float(p.entry_mid) - 1) * 100 if pd.notna(val) else None
        trades.append(d)
    return dict(paper_stats={k: stats(v) for k, v in groups.items()}, paper_trades=trades, positions=pos_out)
