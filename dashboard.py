from pathlib import Path
import html
from io import BytesIO

import pandas as pd
import streamlit as st

from joy_alerts import clean, engine, text

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

st.set_page_config(page_title="Joy QC Alerts", page_icon="JOY", layout="wide")


@st.cache_resource
def load_data():
    raw = clean.load(str(DATA_DIR))
    return raw, engine.Data(raw)


@st.cache_data(ttl=300)
def get_report(asof):
    raw, data = load_data()
    monday = pd.Timestamp(asof)
    alerts = engine.run_asof(data, monday)
    pulse = engine.network_pulse(data, monday)
    messages = text.messages(alerts, pulse)

    extras = {}
    for alert in alerts:
        if alert["type"] == "MARKETING" and alert["status"] != "CLOSED":
            po = data.po[
                (data.po.warehouse_id == alert["warehouse"])
                & (data.po.sku_code == alert["lines"][0]["sku"])
            ].sort_values("po_date")
            before = po[po.po_date < alert["start"]].qty_ordered.tail(4).mean()
            recent = po[po.po_date >= alert["start"]]
            if pd.notna(before) and before > 0 and len(recent):
                after = recent.qty_ordered.iloc[-1]
                if after < 0.7 * before:
                    extras[id(alert)] = (
                        f"{alert['warehouse']} has already cut its orders for this product by "
                        f"{1 - after / before:.0%} (from ~{before:.0f} to {after:.0f} units a week)."
                    )
    return raw, alerts, pulse, messages, extras


def render_alert(alert, extra=None):
    typ = alert["type"]
    closed = alert["status"] == "CLOSED"
    accent = {"SUPPLY": "#b42318", "KAM": "#1d4ed8", "MARKETING": "#b54708", "UNEXPLAINED": "#b42318"}[typ]

    if closed:
        status = "Recovered"
        metrics = f"<div class='metric'><strong>{text.inr(alert['total'])}</strong><span>Sales lost</span></div>"
    else:
        status = "New this week" if alert["status"] == "NEW" else f"Week {alert['weeks']}"
        metrics = (
            f"<div class='metric'><strong>~{text.inr(alert['impact'])}/week</strong><span>Sales at risk now</span></div>"
            f"<div class='metric'><strong>{text.inr(alert['total'])}</strong><span>Lost since {text.d(alert['start'])}</span></div>"
        )

    facts = ""
    action = ""
    if not closed:
        facts = "".join(f"<li>{html.escape(item)}</li>" for item in text.facts(alert, extra=extra))
        action = (
            f"<div class='action'><span>What to do — {html.escape(alert['team'])}</span>"
            f"<p>{html.escape(text.action(alert))}</p></div>"
        )

    table = ""
    if typ == "SUPPLY":
        rows = "".join(
            f"<tr><td>{html.escape(text.short(line['name']))}</td><td class='n'>{line['ordered']}</td>"
            f"<td class='n'>{line['delivered']}</td><td class='n'><strong>{line['short']}</strong></td>"
            f"<td class='n'>{line['fill']:.0%}</td><td class='n'>{line['avail_before']}% → {line['avail_now']}%</td></tr>"
            for line in alert["lines"]
        )
        table = (
            '<div class="table-wrap"><table><thead><tr><th>Product</th><th class="n">Ordered</th>'
            '<th class="n">Delivered</th><th class="n">Short</th><th class="n">Fill</th>'
            '<th class="n">Availability</th></tr></thead><tbody>' + rows + "</tbody></table></div>"
        )

    return f"""
    <article class="alert-card" style="--accent:{accent}">
      <div class="alert-head"><span class="team">{html.escape(alert['team'])}</span><span class="status {'closed' if closed else ''}">{status}</span></div>
      <h3>{html.escape(text.title(alert))}</h3>
      <div class="metrics">{metrics}</div>
      {('<ul class="facts">' + facts + '</ul>') if facts else ''}
      {table}
      {action}
    </article>
    """


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@700&display=swap');
:root{--ink:#243746;--muted:#667783;--line:#d8e3ea;--bg:#f7fafc;--card:#fff;--blue:#0b5a8e;--cyan:#2d89c7}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;color:#bed4e6!important}.stApp,[data-testid="stAppViewContainer"]{background:#f7fafc!important;color:#243746!important}
[data-testid="stHeader"]{background:#fff!important}[data-testid="stSidebar"]{background:#eef5f9!important;border-right:1px solid #d8e3ea}[data-testid="stSidebar"] *{color:#243746!important}
.block-container{max-width:1180px;padding-top:1.5rem;padding-bottom:4rem}h1,h2,h3,p,li,span,strong,td,th,label{color:#243746!important}h1,h2{font-family:'Manrope',sans-serif!important}h1{font-size:34px!important;color:#0b5a8e!important}h2{color:#0b5a8e!important;font-size:20px!important}
.brand{display:flex;align-items:center;gap:12px}.brand-mark{width:48px;height:48px;border-radius:8px;background:#0b5a8e!important;color:#fff!important;display:grid;place-items:center;font-weight:800}.brand strong{color:#0b5a8e!important}.subtle{color:#c5d5e0!important}
.metric-bar{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0 28px}.box{background:#edf5fa!important;border:1px solid #caddea!important;border-radius:4px;padding:18px 20px}.box strong{display:block;font-size:25px;color:#0b5a8e!important}.box span{color:#667783!important;font-size:13px}
.alert-card{background:#fff!important;border:1px solid #d8e3ea!important;border-left:5px solid var(--accent)!important;border-radius:4px;padding:20px 22px;margin:13px 0}.alert-head{display:flex;justify-content:space-between}.team,.status{border-radius:2px;padding:6px 10px;font-size:12px;font-weight:700}.team{background:#edf5fa!important;color:#0b5a8e!important}.status{background:#e5eff7!important;color:#0b5a8e!important}.status.closed{background:#dff1e8!important;color:#24724c!important}.alert-card h3{font-size:20px;margin:12px 0 10px}.metrics{display:flex;gap:36px}.metric strong{display:block;font-size:22px;color:#0b5a8e!important}.metric span{color:#667783!important;font-size:12px}.facts{padding-left:20px}.facts li{margin:5px 0}.action{background:#edf5fa!important;border:1px solid #caddea!important;border-radius:4px;padding:13px 15px}.action span{color:#0b5a8e!important;font-size:11px;text-transform:uppercase;font-weight:700}.action p{margin:5px 0 0}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #d8e3ea;padding:8px;text-align:left}th{background:#edf5fa;color:#0b5a8e!important;font-size:12px}.n{text-align:right;white-space:nowrap}.message{background:#edf5fa!important;border:1px solid #caddea!important;border-radius:4px;padding:14px 16px;white-space:pre-wrap}
[data-testid="stSidebar"] [data-testid="stButton"] button,[data-testid="stDownloadButton"] button{background:#0b5a8e!important;color:#fff!important;border:0!important;border-radius:3px!important;font-weight:700}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"] {
    background: #0b5a8e !important; /* dropdown background */
    color: #fff !important;         /* selected date text */
}
@media print{[data-testid="stSidebar"],header,.stButton,.no-print{display:none!important}.block-container{max-width:none;padding:0}.alert-card{break-inside:avoid}}
</style>
""", unsafe_allow_html=True)

raw, data = load_data()
week_strings = [day.strftime("%Y-%m-%d") for day in pd.date_range("2026-09-14", pd.Timestamp("2026-11-16"), freq="7D")]

st.markdown('<div class="brand"><div class="brand-mark">JOY</div><strong>Quick Commerce Command Center</strong></div>', unsafe_allow_html=True)
st.title("Monday alerts")

with st.sidebar:
    st.header("Report controls")
    selected = st.selectbox("Reporting Monday", week_strings[::-1], index=0)
    st.caption("Only data available before the selected Monday is used.")

raw, alerts, pulse, messages, extras = get_report(selected)
active = [alert for alert in alerts if alert["status"] != "CLOSED"]
closed = [alert for alert in alerts if alert["status"] == "CLOSED"]
week_start = pd.Timestamp(pulse["week_start"])
week_end = week_start + pd.Timedelta(days=6)

st.markdown(f'<p class="subtle">Monday {text.d(pd.Timestamp(selected), True)} · data for {text.d(week_start)}–{text.d(week_end)} · {pulse["stores"]} dark stores</p>', unsafe_allow_html=True)
st.markdown(
    f'<div class="metric-bar"><div class="box"><strong>{len(active)} to act on</strong><span>{sum(a["status"] == "NEW" for a in active)} new this week</span></div>'
    f'<div class="box"><strong>~{text.inr(sum(a["impact"] for a in active))}/week</strong><span>Sales at stake</span></div>'
    f'<div class="box"><strong>{text.inr(pulse["sales"])}</strong><span>Last week · {pulse["like_chg"]:+.0%} like-for-like</span></div></div>',
    unsafe_allow_html=True,
)

st.subheader("1. Act on these, biggest first")
if active:
    for alert in active:
        st.markdown(render_alert(alert, extras.get(id(alert))), unsafe_allow_html=True)
else:
    st.success("Nothing needs action this week.")

if closed:
    st.subheader("2. Recovered recently")
    for alert in closed:
        st.markdown(render_alert(alert), unsafe_allow_html=True)

st.subheader("3. Messages")
for team, message in messages.items():
    cols = st.columns([1.3, 5.2])
    cols[0].markdown(f"<strong>{html.escape(team)}</strong>", unsafe_allow_html=True)
    cols[1].markdown(
        f'<div class="message">{html.escape(message).replace(chr(10), "<br>")}</div>',
        unsafe_allow_html=True,
    )

with st.expander("4. Data checks"):
    st.subheader("Data checks")
    for issue, count, action in raw["log"]:
        cols = st.columns([5, 1, 5])
        cols[0].markdown(issue)
        cols[1].markdown("" if count is None else str(count))
        cols[2].markdown(action)

with st.expander("Download alert data"):
    rows = []
    for alert in alerts:
        row = {key: value for key, value in alert.items() if key != "lines"}
        row["products"] = "; ".join(line["name"] for line in alert["lines"])
        rows.append(row)
    if rows:
        csv = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
        st.download_button("Download alerts.csv", csv, f"alerts-{selected}.csv", "text/csv")

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, KeepTogether
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

def build_pdf(selected, raw, alerts, pulse, messages):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Joy QC Weekly Alerts - {selected}",
    )
    styles = getSampleStyleSheet()
    blue = HexColor("#0B5A8E")
    cyan = HexColor("#2D89C7")
    dark = HexColor("#243746")
    pale = HexColor("#EDF5FA")
    muted = HexColor("#5E6B73")

    title = ParagraphStyle("RSHTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=blue, spaceAfter=4)
    section = ParagraphStyle("RSHSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=blue, spaceBefore=12, spaceAfter=7)
    card_title = ParagraphStyle("CardTitle", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=dark, spaceAfter=4)
    body = ParagraphStyle("RSHBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=dark)
    small = ParagraphStyle("RSHSmall", parent=body, fontSize=8, leading=11, textColor=muted)

    active = [a for a in alerts if a["status"] != "CLOSED"]
    closed = [a for a in alerts if a["status"] == "CLOSED"]
    week_start = pd.Timestamp(pulse["week_start"])
    week_end = week_start + pd.Timedelta(days=6)

    story = [
        Paragraph("RSH GLOBAL", ParagraphStyle("Brand", parent=title, fontSize=10, leading=12, textColor=cyan, alignment=1)),
        Paragraph("Joy Quick Commerce — Monday Alerts", title),
        Paragraph(f"{text.d(pd.Timestamp(selected), True)} &nbsp; | &nbsp; Data: {text.d(week_start)}–{text.d(week_end)} &nbsp; | &nbsp; {pulse['stores']} dark stores", small),
        Spacer(1, 5 * mm),
    ]

    kpis = [[
        Paragraph(f"<b>{len(active)}</b><br/><font size='8'>TO ACT ON</font>", body),
        Paragraph(f"<b>~{text.inr(sum(a['impact'] for a in active))}/week</b><br/><font size='8'>SALES AT RISK</font>", body),
        Paragraph(f"<b>{text.inr(pulse['sales'])}</b><br/><font size='8'>LAST-WEEK SALES ({pulse['like_chg']:+.0%})</font>", body),
    ]]
    kpi_table = Table(kpis, colWidths=[58 * mm, 58 * mm, 58 * mm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale), ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#CADDEB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, HexColor("#CADDEB")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [kpi_table, Paragraph("1. Act on these, biggest first", section)]

    def alert_block(alert):
        closed = alert["status"] == "CLOSED"
        status = "RECOVERED" if closed else ("NEW THIS WEEK" if alert["status"] == "NEW" else f"WEEK {alert['weeks']}")
        if closed:
            metrics = f"<b>{text.inr(alert['total'])}</b> sales lost"
        else:
            metrics = f"<b>~{text.inr(alert['impact'])}/week</b> sales at risk now &nbsp;|&nbsp; <b>{text.inr(alert['total'])}</b> lost so far"
        parts = [
            Paragraph(f"{html.escape(alert['team'])} &nbsp;  <font color='#2D89C7'>{status}</font>", small),
            Paragraph(html.escape(text.title(alert)), card_title),
            Paragraph(metrics, body),
        ]
        if not closed:
            facts = "".join(f"<br/>• {html.escape(item)}" for item in text.facts(alert))
            parts += [Paragraph(facts, body), Paragraph(f"<b>What to do:</b> {html.escape(text.action(alert))}", body)]
        if alert["type"] == "SUPPLY":
            rows = [["Product", "Ordered", "Delivered", "Short", "Fill", "Availability"]]
            for line in alert["lines"]:
                rows.append([text.short(line["name"]), str(line["ordered"]), str(line["delivered"]), str(line["short"]), f"{line['fill']:.0%}", f"{line['avail_before']}% to {line['avail_now']}%"])
            table = Table(rows, colWidths=[50 * mm, 23 * mm, 23 * mm, 20 * mm, 20 * mm, 38 * mm], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), blue), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#CBD9E2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pale]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            parts.append(Spacer(1, 2 * mm)); parts.append(table)
        return parts

    if active:
        for alert in active:
            story += alert_block(alert)
            story.append(Spacer(1, 3 * mm))
    else:
        story.append(Paragraph("Nothing needs action this week.", body))

    if closed:
        story += [Paragraph("2. Recovered recently", section)]
        for alert in closed:
            story += alert_block(alert)
            story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("3. WhatsApp messages — all teams", section))
    for team, message in messages.items():
        story += [Paragraph(html.escape(team), card_title), Paragraph(html.escape(message).replace("\n", "<br/>"), body), Spacer(1, 2 * mm)]

    story.append(Paragraph("4. Data checks", section))
    issue_rows = [["Found", "Count", "What we did"]]
    for issue, count, action in raw["log"]:
        issue_rows.append([issue, "" if count is None else str(count), action])
    issue_table = Table(issue_rows, colWidths=[70 * mm, 18 * mm, 86 * mm], repeatRows=1)
    issue_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), blue), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#CBD9E2")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pale]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(issue_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

raw, alerts, pulse, messages, extras = get_report(selected)
active = [alert for alert in alerts if alert["status"] != "CLOSED"]
closed = [alert for alert in alerts if alert["status"] == "CLOSED"]
week_start = pd.Timestamp(pulse["week_start"])
week_end = week_start + pd.Timedelta(days=6)

pdf = build_pdf(selected, raw, alerts, pulse, messages)

with st.sidebar:
    st.download_button(
        "Download report",
        pdf,
        f"joy-qc-report-{selected}.pdf",
        "application/pdf",
        use_container_width=True,
    )
