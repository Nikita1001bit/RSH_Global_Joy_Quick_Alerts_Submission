from pathlib import Path
import html

import pandas as pd
import streamlit as st

from joy_alerts import clean, engine, text


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

st.set_page_config(
    page_title="Joy QC Weekly Alerts",
    page_icon="JOY",
    layout="wide",
)


@st.cache_resource
def load_data():
    raw = clean.load(str(DATA_DIR))
    return raw, engine.Data(raw)


@st.cache_data(ttl=300)
def get_report(asof: str):
    raw, data = load_data()
    monday = pd.Timestamp(asof)

    alerts = engine.run_asof(data, monday)
    pulse = engine.network_pulse(data, monday)
    msgs = text.messages(alerts, pulse)

    extras = {}
    for alert in alerts:
        if alert["type"] == "MARKETING" and alert["status"] != "CLOSED":
            po = data.po[
                (data.po.warehouse_id == alert["warehouse"])
                & (data.po.sku_code == alert["lines"][0]["sku"])
            ].sort_values("po_date")
            if len(po):
                before = po[po.po_date < alert["start"]].qty_ordered.tail(4).mean()
                recent = po[po.po_date >= alert["start"]]
                if pd.notna(before) and len(recent):
                    after = recent.qty_ordered.iloc[-1]
                    if before > 0 and after < 0.7 * before:
                        extras[id(alert)] = (
                            f"{alert['warehouse']} has already cut orders for this product by "
                            f"{1 - after / before:.0%} (from ~{before:.0f} to {after:.0f} units a week)."
                        )

    return raw, data, alerts, pulse, msgs, extras


def rupee(value):
    return text.inr(value)


def alert_facts(alert, extra=None):
    facts = text.facts(alert, extra=extra)
    return "".join(f"<li>{html.escape(fact)}</li>" for fact in facts)


def render_supply_table(alert):
    if alert["type"] != "SUPPLY":
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(text.short(line['name']))}</td>"
        f"<td class='number'>{line['ordered']}</td>"
        f"<td class='number'>{line['delivered']}</td>"
        f"<td class='number'><strong>{line['short']}</strong></td>"
        f"<td class='number'>{line['fill']:.0%}</td>"
        f"<td class='number'>{line['avail_before']}% → {line['avail_now']}%</td>"
        "</tr>"
        for line in alert["lines"]
    )
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Product</th><th class='number'>Ordered</th><th class='number'>Delivered</th>"
        "<th class='number'>Short</th><th class='number'>Fill</th><th class='number'>Availability</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )


def render_alert_card(alert, extra=None):
    status = alert["status"]
    closed = status == "CLOSED"
    typ = alert["type"]
    color = {"SUPPLY": "#b42318", "KAM": "#1d4ed8", "MARKETING": "#b54708", "UNEXPLAINED": "#b42318"}[typ]
    status_label = "Recovered" if closed else "New this week" if status == "NEW" else f"Week {alert['weeks']}"

    title = text.title(alert)
    if closed:
        impact = (
            f"<div class='metric'><strong>{rupee(alert['total'])}</strong>"
            f"<span>estimated sales lost, {text.d(alert['start'])}–{text.d(alert['end'])}</span></div>"
        )
    else:
        impact = (
            f"<div class='metric'><strong>~{rupee(alert['impact'])}/week</strong><span>Sales at risk now</span></div>"
            f"<div class='metric'><strong>{rupee(alert['total'])}</strong>"
            f"<span>Lost so far since {text.d(alert['start'])}</span></div>"
        )

    facts = "" if closed else alert_facts(alert, extra)
    action = "" if closed else (
        f"<div class='action'><span>What to do — {html.escape(alert['team'])}</span>"
        f"<p>{html.escape(text.action(alert))}</p></div>"
    )

    return f"""
    <article class="alert-card" style="--accent:{color}">
      <div class="alert-head">
        <div><span class="team">{html.escape(alert['team'])}</span></div>
        <span class="status {'closed' if closed else ''}">{status_label}</span>
      </div>
      <h3>{html.escape(title)}</h3>
      <div class="metrics">{impact}</div>
      {('<ul class="facts">' + facts + '</ul>') if facts else ''}
      {render_supply_table(alert)}
      {action}
    </article>
    """


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@700&display=swap');
:root { --ink:#1d1d1a; --muted:#6f716b; --line:#e5e7df; --bg:#f5f6f2; --card:#ffffff; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:var(--bg); }
.block-container { max-width:1180px; padding-top:2rem; padding-bottom:4rem; }
.brand-row { display:flex; align-items:center; gap:12px; margin-bottom:4px; }
.brand-mark { width:38px; height:38px; border-radius:11px; background:#111; color:#fff; display:grid; place-items:center; font-weight:800; }
h1 { font-family:'Manrope',sans-serif !important; letter-spacing:-.04em; }
.subtle { color:var(--muted); }
.metric-bar { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:18px 0 24px; }
.metric-bar .box { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px 18px; }
.metric-bar strong { display:block; font-size:24px; margin-bottom:3px; }
.metric-bar span { color:var(--muted); font-size:13px; }
.alert-card { background:var(--card); border:1px solid var(--line); border-left:5px solid var(--accent); border-radius:16px; padding:18px 20px; margin:12px 0; }
.alert-head { display:flex; justify-content:space-between; align-items:center; }
.team { background:#f0f2ed; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:700; }
.status { background:#edeff8; color:#3045a5; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:700; }
.status.closed { background:#e9f5ed; color:#207348; }
.alert-card h3 { font-size:19px; margin:10px 0 8px; }
.metrics { display:flex; gap:32px; flex-wrap:wrap; margin-bottom:8px; }
.metric strong { display:block; font-size:21px; }
.metric span { color:var(--muted); font-size:12px; }
.facts { margin:8px 0 10px; padding-left:20px; }
.facts li { margin:4px 0; }
.action { background:#f5f6f2; border-radius:12px; padding:12px 14px; }
.action span { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; font-weight:700; }
.action p { margin:4px 0 0; }
.table-wrap { overflow-x:auto; margin:10px 0; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { border-bottom:1px solid var(--line); padding:7px 8px; text-align:left; }
th { color:var(--muted); font-size:12px; }
.number { text-align:right; white-space:nowrap; }
.message-box { background:#eaf7e7; border:1px solid #d5ebd1; border-radius:14px 14px 14px 4px; padding:14px 16px; white-space:pre-wrap; font-size:14px; }
.data-box { background:#fff; border:1px solid var(--line); border-radius:12px; padding:10px 14px; }
@media print {
  .stApp > header, [data-testid="stSidebar"], .no-print, .stButton, .stTextArea { display:none !important; }
  .block-container { max-width:none; padding:0; }
  .alert-card { break-inside:avoid; }
}
</style>
""", unsafe_allow_html=True)


raw, data, alerts, pulse, msgs, extras = load_data()
active = [a for a in alerts if a["status"] != "CLOSED"]
closed = [a for a in alerts if a["status"] == "CLOSED"]

week_start = pd.Timestamp(pulse["week_start"])
week_end = week_start + pd.Timedelta(days=6)
st.markdown(
    f'<p class="subtle">Monday {text.d(pd.Timestamp(selected), True)} · data for '
    f'{text.d(week_start)}–{text.d(week_end)} · {pulse["stores"]} dark stores</p>',
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <section class="metric-bar">
      <div class="box"><strong>{len(active)} to act on</strong><span>{sum(a['status']=='NEW' for a in active)} new this week</span></div>
      <div class="box"><strong>~{rupee(sum(a['impact'] for a in active))}/week</strong><span>Sales at stake</span></div>
      <div class="box"><strong>{rupee(pulse['sales'])}</strong><span>Last week's sales · {pulse['like_chg']:+.0%} like-for-like</span></div>
    </section>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Act on these, biggest first")
if active:
    for alert in active:
        st.markdown(render_alert_card(alert, extras.get(id(alert))), unsafe_allow_html=True)
else:
    st.success("Nothing needs action this week.")

if closed:
    st.subheader("2. Recovered recently")
    for alert in closed:
        st.markdown(render_alert_card(alert), unsafe_allow_html=True)

st.subheader("3. Messages ready to copy")
for team, message in msgs.items():
    with st.expander(team, expanded=team == "Quick Commerce Manager"):
        st.markdown(f'<div class="message-box">{html.escape(message)}</div>', unsafe_allow_html=True)
        st.code(message, language=None)

st.subheader("4. Data checks")
for issue, count, action in raw["log"]:
    cols = st.columns([5, 1, 5])
    cols[0].markdown(issue)
    cols[1].markdown("" if count is None else str(count))
    cols[2].markdown(action)

with st.expander("Download alert data"):
    rows = []
    for alert in alerts:
        row = {k: v for k, v in alert.items() if k != "lines"}
        row["products"] = "; ".join(line["name"] for line in alert["lines"])
        rows.append(row)
    if rows:
        csv = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
        st.download_button("Download alerts.csv", csv, f"alerts-{selected}.csv", "text/csv")
