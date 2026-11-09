"""Renders the static dashboard page (docs/index.html). All data is embedded, so the page works
on GitHub Pages and when opened straight from disk."""
from __future__ import annotations

import json

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HBB Flip Scanner · __DATE__</title>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#5d6472;--line:#e3e6eb;--green:#0f8a4b;--green-bg:#e3f5ea;
        --red:#c23a2b;--red-bg:#fbe7e4;--amber:#9a6200;--amber-bg:#fdf1d8;--accent:#2457c5}
  @media (prefers-color-scheme: dark){:root{--bg:#111318;--card:#191c22;--ink:#e8eaee;--muted:#9aa1ad;--line:#2b3039;
        --green:#3ecf7f;--green-bg:#123323;--red:#ff7b6b;--red-bg:#3a1a16;--amber:#f0b44c;--amber-bg:#3a2c12;--accent:#7aa2ff}}
  *{box-sizing:border-box} body{margin:0;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
  header{padding:22px 28px 8px} h1{margin:0;font-size:22px;letter-spacing:-.01em} .sub{color:var(--muted);margin-top:4px}
  .demo{margin:12px 28px 0;padding:10px 14px;border-radius:8px;background:var(--amber-bg);color:var(--amber);font-weight:600}
  .stats{display:flex;gap:12px;flex-wrap:wrap;padding:14px 28px}
  .stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:140px}
  .stat b{display:block;font-size:20px} .stat span{color:var(--muted);font-size:12px}
  nav{display:flex;gap:6px;padding:6px 28px 0;flex-wrap:wrap} nav button{border:1px solid var(--line);background:var(--card);color:var(--ink);
       padding:8px 14px;border-radius:999px;cursor:pointer;font:inherit} nav button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
  .tools{display:flex;gap:10px;align-items:center;padding:12px 28px;flex-wrap:wrap}
  .tools input[type=search]{padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);min-width:240px;font:inherit}
  .tools label{color:var(--muted);display:flex;gap:6px;align-items:center;cursor:pointer}
  section{padding:0 28px 28px} .wrap{overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
  table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums} th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
  th{position:sticky;top:0;background:var(--card);color:var(--muted);font-weight:600;font-size:12px;cursor:pointer;user-select:none}
  th[title]{text-decoration:underline dotted;text-underline-offset:3px} th.l,td.l{text-align:left} tr:hover td{background:color-mix(in srgb,var(--accent) 6%,transparent)}
  th.grp{text-align:center;color:var(--ink);cursor:default;border-bottom:none;font-size:11px;letter-spacing:.04em;text-transform:uppercase}
  .pill{display:inline-block;padding:2px 8px;border-radius:999px;font-weight:600;font-size:12px}
  .g{background:var(--green-bg);color:var(--green)} .r{background:var(--red-bg);color:var(--red)} .a{background:var(--amber-bg);color:var(--amber)}
  .tk{font-weight:700} .nm{color:var(--muted);max-width:220px;overflow:hidden;text-overflow:ellipsis} .muted{color:var(--muted)}
  .empty{padding:28px;text-align:center;color:var(--muted)}
  .help{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 22px;max-width:900px}
  .help h3{margin:14px 0 6px;font-size:15px} .help p,.help li{color:var(--ink)} .help code{background:var(--bg);padding:1px 5px;border-radius:4px}
  footer{color:var(--muted);padding:0 28px 28px;font-size:12px}
</style>
</head>
<body>
<header><h1>HBB Flip Scanner</h1><div class="sub" id="sub"></div></header>
<div id="demo"></div>
<div class="stats" id="stats"></div>
<nav id="tabs"></nav>
<div class="tools"><input type="search" id="q" placeholder="Filter by ticker or company…">
  <label><input type="checkbox" id="takeOnly"> Only flips the 50-day rule would take</label></div>
<section id="view"></section>
<footer>Hull Bollinger Bands (HMA 34, 2×σ34) colour = HMA rising (green) or not (red). Data: Yahoo Finance (free, delayed, unofficial) and Wikipedia constituent lists. Options: Yahoo option chains; delta computed with Black-Scholes from each contract's own IV. Research tool, not trading advice.</footer>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const $ = s => document.querySelector(s);
const fmt = (v, d=2) => v==null||isNaN(v) ? '–' : Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const pct = (v, d=1) => v==null ? '–' : (v>0?'+':'')+fmt(v,d)+'%';
const sgn = (v, d=1) => v==null ? '–' : (v>0?'+':'')+fmt(v,d);
const pill = c => `<span class="pill ${c==='green'?'g':'r'}">${c==='green'?'Green':'Red'}</span>`;
const rule = v => v==null ? '–' : `<span class="pill ${v==='take'?'g':'a'}">${v==='take'?'Take':'Stretched'}</span>`;
const trig = r => { const past = r.next_colour==='green' ? r.flip_close_tomorrow < r.close : r.flip_close_tomorrow >= r.close;
  return past ? `<span class="pill a">already past</span> <span class="muted">${pct(r.flip_move_pct)}</span>` : `${pct(r.flip_move_pct)} <span class="muted">${sgn(r.flip_move_atr)} ATR</span>`; };
const days = v => v==null ? `<span class="muted">&gt;30</span>` : v;

$('#sub').textContent = `Daily close ${D.scan_date} · generated ${D.generated_utc}`;
if (D.demo) $('#demo').innerHTML = '<div class="demo">SAMPLE DATA — generated offline to test the page. Not real prices or options.</div>';
const B = D.breadth;
$('#stats').innerHTML = [
  [B.total, 'names scanned'], [Math.round(B.green/B.total*100)+'%', 'green (HMA rising)'],
  [B.green_flips, 'turned green today'], [B.red_flips, 'turned red today'],
  [D.rows.filter(r=>!r.flipped_today && r.days_to_flip_flat!=null && r.days_to_flip_flat<=D.settings.near_days).length, `flip within ${D.settings.near_days} flat days`]
].map(([b,s])=>`<div class="stat"><b>${b}</b><span>${s}</span></div>`).join('');

const optCols = [
  {k:r=>r.option?.expiry, h:'Expiry', t:'Option expiry closest to 30 days out', f:r=>r.option?`${r.option.expiry.slice(5)} <span class="muted">(${r.option.dte}d)</span>`:'<span class="muted">no chain</span>'},
  {k:r=>r.option?.strike, h:'Strike', f:r=>r.option?`${fmt(r.option.strike)} <span class="muted">${r.option.kind==='call'?'C':'P'}</span>`:''},
  {k:r=>r.option?.otm_pct, h:'OTM', t:'How far the strike is from the stock price', f:r=>r.option?fmt(r.option.otm_pct,1)+'%':''},
  {k:r=>r.option?.delta, h:'Delta', f:r=>r.option?fmt(r.option.delta,2):''},
  {k:r=>r.option?.mid, h:'Mid', t:'Midpoint of bid/ask (last trade if no quote)', f:r=>r.option?fmt(r.option.mid):''},
  {k:r=>r.option?.cost, h:'$/contract', f:r=>r.option?'$'+fmt(r.option.cost,0):''},
  {k:r=>r.option?.iv, h:'IV', t:'Implied volatility of this contract (Yahoo)', f:r=>r.option?fmt(r.option.iv,1)+'%':''},
  {k:r=>r.option?.skew, h:'Skew', t:'25Δ IV minus at-the-money IV, vol points. Low/negative = the wing is cheap', f:r=>r.option?sgn(r.option.skew):''},
  {k:r=>r.option?.iv_minus_rv, h:'IV−RV', t:'25Δ IV minus 20-day realised volatility, vol points. Low = cheap vs how the stock has moved', f:r=>r.option?sgn(r.option.iv_minus_rv):''},
  {k:r=>r.option?.iv_rank, h:'IV rank', t:'Percentile of this IV vs the scanner\'s own history (needs ~60 days of runs)', f:r=>r.option?.iv_rank!=null?fmt(r.option.iv_rank,0):'<span class="muted">building</span>'},
  {k:r=>r.option?.open_interest, h:'OI', f:r=>r.option?fmt(r.option.open_interest,0):''},
  {k:r=>r.option?.spread_pct, h:'Spread', t:'Bid/ask spread as % of mid', f:r=>r.option?.spread_pct!=null?fmt(r.option.spread_pct,0)+'%':''},
];
const base = [
  {k:r=>r.ticker, h:'Ticker', c:'l', f:r=>`<span class="tk">${r.ticker}</span>`},
  {k:r=>r.name, h:'Company', c:'l', f:r=>`<div class="nm" title="${r.name}">${r.name}</div>`},
];
const views = {
  flips: {label: r=>`Flipped today (${D.rows.filter(x=>x.flipped_today).length})`,
    rows: ()=>D.rows.filter(r=>r.flipped_today), take: r=>r.filter_today==='take',
    sort: r=>r.colour==='green'?0:1, groups:[['',6],['25-delta option',12]],
    cols: [...base,
      {k:r=>r.colour, h:'Flip', c:'l', f:r=>pill(r.colour)},
      {k:r=>r.stretch_atr, h:'50-day rule', c:'l', t:'Take = price not more than 1 ATR past its 50-day average in the flip direction. Stretched = the move has likely run.', f:r=>`${rule(r.filter_today)} <span class="muted">${sgn(r.stretch_atr)} ATR</span>`},
      {k:r=>r.close, h:'Close', f:r=>fmt(r.close)},
      {k:r=>r.atr_pct, h:'ATR %', t:'14-day average true range as % of price', f:r=>fmt(r.atr_pct,1)+'%'},
      ...optCols]},
  near: {label: r=>`Close to flipping (${D.rows.filter(x=>!x.flipped_today&&x.days_to_flip_flat!=null&&x.days_to_flip_flat<=D.settings.near_days).length})`,
    rows: ()=>D.rows.filter(r=>!r.flipped_today && r.days_to_flip_flat!=null && r.days_to_flip_flat<=D.settings.near_days),
    take: r=>r.filter_if_next_flip_now==='take', sort: r=>r.days_to_flip_flat, groups:[['',9],['25-delta option',12]],
    cols: [...base,
      {k:r=>r.colour, h:'Now', c:'l', f:r=>pill(r.colour)+` <span class="muted">${r.bars_in_colour}d</span>`},
      {k:r=>r.next_colour, h:'Flips to', c:'l', f:r=>pill(r.next_colour)},
      {k:r=>r.days_to_flip_flat, h:'Days if flat', t:'Trading days until the colour changes if price closes unchanged every day', f:r=>days(r.days_to_flip_flat)},
      {k:r=>r.flip_close_tomorrow, h:'Tomorrow\'s trigger', t:'The close that flips the colour on the next bar', f:r=>`${r.next_colour==='green'?'Green if close &gt;':'Red if close ≤'} ${fmt(r.flip_close_tomorrow)}`},
      {k:r=>r.flip_move_pct, h:'Trigger vs today', t:'Where the trigger sits against today\'s close. If today\'s close is already past it, the flip happens on an unchanged close.', f:r=>trig(r)},
      {k:r=>r.stretch_atr, h:'50-day rule', c:'l', t:'Whether the coming flip would pass the 50-day rule at today\'s close', f:r=>`${rule(r.filter_if_next_flip_now)} <span class="muted">${sgn(r.stretch_atr)} ATR</span>`},
      {k:r=>r.close, h:'Close', f:r=>fmt(r.close)},
      ...optCols]},
  all: {label: r=>`All names (${D.rows.length})`, rows: ()=>D.rows, take: r=>true, sort: r=>r.days_to_flip_flat??99, groups:null,
    cols: [...base,
      {k:r=>r.sector, h:'Sector', c:'l', f:r=>`<span class="muted">${r.sector||''}</span>`},
      {k:r=>r.colour, h:'Colour', c:'l', f:r=>pill(r.colour)+(r.flipped_today?' <span class="pill a">new</span>':'')},
      {k:r=>r.bars_in_colour, h:'Days in colour', f:r=>r.bars_in_colour},
      {k:r=>r.days_to_flip_flat??99, h:'Days to flip if flat', f:r=>days(r.days_to_flip_flat)},
      {k:r=>r.flip_close_tomorrow, h:'Tomorrow\'s trigger', f:r=>`${r.next_colour==='green'?'Green if &gt;':'Red if ≤'} ${fmt(r.flip_close_tomorrow)}`},
      {k:r=>r.flip_move_pct, h:'Trigger vs today', f:r=>trig(r)},
      {k:r=>r.stretch_atr, h:'vs 50-day (ATR)', t:'Close minus 50-day average, in ATRs', f:r=>sgn(r.stretch_atr)},
      {k:r=>r.close, h:'Close', f:r=>fmt(r.close)},
      {k:r=>r.hma, h:'Hull line', f:r=>fmt(r.hma)},
    ]},
  help: {label: ()=>'How to read this'},
};
let cur = 'flips', sortKey = null, sortDir = 1;
function tabs(){ $('#tabs').innerHTML = Object.entries(views).map(([k,v])=>`<button data-k="${k}" class="${k===cur?'on':''}">${v.label()}</button>`).join('');
  document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{cur=b.dataset.k; sortKey=null; draw();}); }
function draw(){
  tabs(); const v = views[cur];
  $('.tools').style.display = cur==='help' ? 'none' : 'flex';
  if (cur==='help'){ $('#view').innerHTML = HELP; return; }
  const q = $('#q').value.trim().toLowerCase(); const takeOnly = $('#takeOnly').checked;
  let rows = v.rows().filter(r=>!q || r.ticker.toLowerCase().includes(q) || (r.name||'').toLowerCase().includes(q));
  if (takeOnly) rows = rows.filter(v.take);
  const key = sortKey!=null ? v.cols[sortKey].k : v.sort;
  rows = rows.slice().sort((a,b)=>{const x=key(a), y=key(b); if(x==null) return 1; if(y==null) return -1; return (x>y?1:x<y?-1:0)*(sortKey!=null?sortDir:1);});
  if (!rows.length){ $('#view').innerHTML = '<div class="wrap"><div class="empty">Nothing here today.</div></div>'; return; }
  const grp = v.groups ? '<tr>'+v.groups.map(([t,n])=>`<th class="grp" colspan="${n}">${t}</th>`).join('')+'</tr>' : '';
  const head = '<tr>'+v.cols.map((c,i)=>`<th data-i="${i}" class="${c.c||''}" ${c.t?`title="${c.t}"`:''}>${c.h}${sortKey===i?(sortDir>0?' ▲':' ▼'):''}</th>`).join('')+'</tr>';
  const body = rows.map(r=>'<tr>'+v.cols.map(c=>`<td class="${c.c||''}">${c.f(r)}</td>`).join('')+'</tr>').join('');
  $('#view').innerHTML = `<div class="wrap"><table><thead>${grp}${head}</thead><tbody>${body}</tbody></table></div>`;
  document.querySelectorAll('th[data-i]').forEach(th=>th.onclick=()=>{const i=+th.dataset.i; sortDir = sortKey===i ? -sortDir : 1; sortKey=i; draw();});
}
const HELP = `<div class="help">
<h3>What a flip is</h3><p>The middle line is a 34-day Hull moving average. It is green when it is higher than yesterday and red when it is not. A flip is the first close where that changes. Signals use the closed daily bar; a trade would be entered at the next open.</p>
<h3>Close to flipping</h3><p><b>Days if flat</b> counts the trading days until the colour changes if the stock closes unchanged every day. A falling stock only has to stop falling for the line to turn green. <b>Tomorrow's trigger</b> is the exact close that flips it on the next bar: above it turns green, at or below it turns red. <span class="pill a">already past</span> means today's close is already beyond the trigger, so an unchanged close tomorrow flips it.</p>
<h3>The 50-day rule</h3><p>From the grains study: flips that come when price is already more than 1 ATR past its 50-day average in the flip's direction were mostly late and choppy. <span class="pill g">Take</span> means the flip passes; <span class="pill a">Stretched</span> means it doesn't. The rule has not yet been tested on stocks, so both are listed.</p>
<h3>The 25-delta option</h3><p>For each flip (or coming flip) the scanner picks the call (green) or put (red) whose delta is closest to 0.25, in the expiry nearest 30 days. <b>Skew</b> and <b>IV−RV</b> show whether that option is cheap: in the grains test, buying when the wing was cheap (low skew, low IV rank) carried nearly all the profit. <b>IV rank</b> needs about 60 days of scanner history before it shows.</p>
<h3>Caveats</h3><ul><li>Yahoo data is free and unofficial; quotes after the close can be stale or wide. Check the spread and open interest before trusting a price.</li><li>Delta is computed with Black-Scholes and no dividend yield, so high-dividend stocks are slightly off.</li><li>Nothing here has been backtested on stocks yet.</li></ul></div>`;
$('#q').oninput = draw; $('#takeOnly').onchange = draw; draw();
</script>
</body>
</html>
"""


def render_dashboard(data: dict) -> str:
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", blob).replace("__DATE__", data["scan_date"])
