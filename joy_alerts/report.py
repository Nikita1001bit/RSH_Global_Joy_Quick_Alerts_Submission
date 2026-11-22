import html
import pandas as pd
from .text import inr, d, short, title, facts, action

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1c1b19;--mute:#6b6a65;--line:#e4e2db;--red:#b42318;--redbg:#fdecea;--amb:#b54708;--ambbg:#fef3e2;--grn:#067647;--grnbg:#e6f4ec;--blu:#1d4ed8;--blubg:#e8eefc;--wa:#dcf8c6}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--card:#1f1f1d;--ink:#f1efe8;--mute:#a09e96;--line:#34332f;--red:#ff8a80;--redbg:#3a1d1a;--amb:#ffb865;--ambbg:#3a2a14;--grn:#6ee7a0;--grnbg:#14301f;--blu:#9db8ff;--blubg:#1b2540;--wa:#1f3b2a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:env(safe-area-inset-top,0) 0 env(safe-area-inset-bottom,0)}
.wrap{max-width:920px;margin:0 auto;padding:20px 16px 60px}h1{font-size:24px;margin:0}h2{font-size:17px;margin:32px 0 10px}
.sub{color:var(--mute);margin:2px 0 18px}.pulse{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}.kpi b{display:block;font-size:22px}.kpi span{color:var(--mute);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:12px 0;border-left:5px solid var(--red)}
.card.MARKETING{border-left-color:var(--amb)}.card.KAM{border-left-color:var(--blu)}.card.closed{border-left-color:var(--grn);opacity:.95}
.row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:6px}.tag{font-size:12px;font-weight:600;padding:2px 9px;border-radius:99px;background:var(--redbg);color:var(--red)}
.tag.m{background:var(--ambbg);color:var(--amb)}.tag.k{background:var(--blubg);color:var(--blu)}.tag.n{background:var(--ink);color:var(--bg)}.tag.g{background:var(--grnbg);color:var(--grn)}
.card h3{margin:2px 0 8px;font-size:17px;line-height:1.3}.money{display:flex;gap:22px;flex-wrap:wrap;margin:8px 0}.money div b{font-size:19px;display:block}.money span{font-size:12px;color:var(--mute)}
ul{margin:6px 0 8px;padding-left:20px}li{margin:3px 0}.do{background:var(--bg);border-radius:10px;padding:10px 12px;margin-top:8px}.do b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mute)}
.tbl{overflow-x:auto;margin:8px 0}table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}td.n{white-space:nowrap}th{color:var(--mute);font-weight:600;font-size:12px}td.n,th.n{text-align:right}
.wa{background:var(--wa);border-radius:4px 14px 14px 14px;padding:10px 12px;white-space:pre-wrap;font-size:14px;margin:4px 0 6px;border:1px solid var(--line)}.who{font-weight:600;margin-top:14px}
button{font:inherit;font-size:12px;padding:4px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.note{color:var(--mute);font-size:13px}.ok{padding:14px;background:var(--grnbg);color:var(--grn);border-radius:12px}
"""


def e(x):
    return html.escape(str(x))


def line_table(a):
    if a["type"] == "SUPPLY":
        rows = "".join(f"<tr><td>{e(short(l['name']))}</td><td class=n>{l['ordered']}</td><td class=n>{l['delivered']}</td><td class=n><b>{l['short']}</b></td>"
                       f"<td class=n>{l['fill']:.0%}</td><td class=n>{l['avail_before']}% → {l['avail_now']}%</td></tr>" for l in a["lines"])
        return f"<div class=tbl><table><tr><th>Product<th class=n>Ordered<th class=n>Delivered<th class=n>Short<th class=n>Fill<th class=n>Store availability</tr>{rows}</table></div>"
    return ""


def card(a, extra_fact=None):
    typ = a["type"]
    closed = a["status"] == "CLOSED"
    tcls = {"SUPPLY": "", "KAM": "k", "MARKETING": "m", "UNEXPLAINED": ""}[typ]
    status = (f"<span class='tag g'>Recovered</span>" if closed else
              f"<span class='tag n'>NEW</span>" if a["status"] == "NEW" else f"<span class='tag n'>Week {a['weeks']}</span>")
    h = f"<div class='card {typ} {'closed' if closed else ''}'><div class=row><span class='tag {tcls}'>{e(a['team'])}</span>{status}</div>"
    h += f"<h3>{e(title(a))}</h3>"
    if closed:
        h += (f"<div class=money><div><b>{inr(a['total'])}</b><span>sales lost, {d(a['start'])} to {d(a['end'] + pd.Timedelta(days=6))}</span></div></div>")
        return h + "</div>"
    h += (f"<div class=money><div><b>~{inr(a['impact'])}/week</b><span>sales we're losing now (estimate)</span></div>"
          f"<div><b>{inr(a['total'])}</b><span>lost so far since {d(a['start'])}</span></div></div>")
    h += "<ul>" + "".join(f"<li>{e(f)}</li>" for f in facts(a, extra=extra_fact)) + "</ul>" + line_table(a)
    h += f"<div class=do><b>What to do ({e(a['team'])})</b>{e(action(a))}</div></div>"
    return h


def build(asof, alerts, pulse, msgs, backtest, dq, extras):
    T = pd.Timestamp(asof)
    act = [a for a in alerts if a["status"] != "CLOSED"]
    closed = [a for a in alerts if a["status"] == "CLOSED"]
    dec = "down" if pulse["like_chg"] < 0 else "up"
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>"
         f"<title>Joy QC weekly, {d(T, True)}</title><style>{CSS}</style></head><body><div class=wrap>"]
    h.append(f"<h1>Joy Quick Commerce: what to act on this week</h1><div class=sub>Monday {d(T, True)} · data for {d(pulse['week_start'])} to {d(pulse['week_start'] + pd.Timedelta(days=6))} · Blinkit, Zepto, Instamart · {pulse['stores']} dark stores</div>")
    h.append("<div class=pulse>")
    h.append(f"<div class=kpi><b>{len(act)} to act on</b><span>{sum(a['status'] == 'NEW' for a in act)} new this week</span></div>")
    h.append(f"<div class=kpi><b>~{inr(sum(a['impact'] for a in act))}/week</b><span>sales at stake if nothing changes</span></div>")
    h.append(f"<div class=kpi><b>{inr(pulse['sales'])}</b><span>last week's sales, {pulse['like_chg']:+.0%} vs the week before (like-for-like stores)</span></div></div>")
    h.append(f"<p class=note>Sales {dec} {abs(pulse['like_chg']):.0%} but that is <b>not</b> one of our problems: all {pulse['wh_down']} of {pulse['wh_total']} platform warehouses also ordered less ({pulse['po_chg']:+.0%} units), "
             f"i.e. demand cooling after the festive peak. We compare each product with the same product in other cities, so network-wide swings don't trigger alerts.</p>")
    h.append("<h2>1. Act on these, biggest first</h2>")
    h.append("".join(card(a, extras.get(id(a))) for a in act) if act else "<div class=ok>Nothing needs action this week.</div>")
    if closed:
        h.append("<h2>2. Recovered recently (no action, for your review)</h2>")
        h.append("".join(card(a) for a in closed))
    h.append("<h2>3. Messages ready to send</h2><p class=note>One per team, in the language they use. Tap Copy and paste into WhatsApp.</p>")
    for i, (who, m) in enumerate(msgs.items()):
        h.append(f"<div class=who>{e(who)}</div><div class=wa id=m{i}>{e(m)}</div><button onclick=\"navigator.clipboard.writeText(document.getElementById('m{i}').innerText);this.textContent='Copied'\">Copy</button>")
    if backtest is not None:
        h.append("<h2>4. Would this have caught the last two months' problems?</h2><p class=note>Same code, replayed on each past Monday using only the data available that day.</p>")
        rows = "".join(f"<tr><td>{e(b['name'])}</td><td>{d(b['started'])}</td><td>{e(b['noticed'])}</td><td><b>Mon {d(b['flag'])}</b> ({b['wk']} week after it started)</td><td class=n>{inr(b['saved'])}</td></tr>" for b in backtest)
        h.append(f"<div class=tbl><table><tr><th>Problem<th>Started<th>Noticed by us (per brief)<th>Tool flags it<th class=n>Sales protected</tr>{rows}</table></div>")
        h.append("<p class=note>'Sales protected' = estimated sales lost between our flag date and the date it was noticed. Across all 10 Mondays, the tool never showed more than 3 active alerts.</p>")
    h.append("<h2>5. What was messy in the data</h2><div class=tbl><table><tr><th>Found<th class=n>Count<th>What we did</tr>")
    h += [f"<tr><td style='white-space:normal'>{e(a)}</td><td class=n>{'' if b is None else b}</td><td style='white-space:normal'>{e(c)}</td></tr>" for a, b, c in dq]
    h.append("</table></div><p class=note>Rupee figures are estimates: expected sales (own 4-week baseline, adjusted by the same product in other cities) minus actual sales.</p></div></body></html>")
    return "".join(h)
