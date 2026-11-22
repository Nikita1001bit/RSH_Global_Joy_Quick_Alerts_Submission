"""python run.py --data data --asof 2026-11-16 --out output   (add --backtest to replay past Mondays)"""
import argparse, os
import pandas as pd
from joy_alerts import clean, engine, report, text

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data"); ap.add_argument("--asof", default="2026-11-16"); ap.add_argument("--out", default="output")
ap.add_argument("--backtest", action="store_true", help="replay every past Monday and check the 3 known problems")
a = ap.parse_args()

raw = clean.load(a.data)
D = engine.Data(raw)
T = pd.Timestamp(a.asof)
alerts = engine.run_asof(D, T)
pulse = engine.network_pulse(D, T)

# extra evidence for ranking alerts: did the platform warehouse cut its orders for this product?
extras = {}
for al in alerts:
    if al["type"] == "MARKETING" and al["status"] != "CLOSED":
        po = D.po[(D.po.warehouse_id == al["warehouse"]) & (D.po.sku_code == al["lines"][0]["sku"])].sort_values("po_date")
        before, after = po[po.po_date < al["start"]].qty_ordered.tail(4).mean(), po[po.po_date >= al["start"]].qty_ordered.iloc[-1]
        if after < 0.7 * before:
            extras[id(al)] = f"{al['warehouse']} has already cut its orders for this product by {1 - after / before:.0%} (from ~{before:.0f} to {after:.0f} units a week), a knock-on effect of the lost visibility."

backtest = None
if a.backtest or True:
    known = [
        dict(name="Blinkit Bengaluru: only ~50% of PO delivered for 6 products", type="SUPPLY", wh="BLK-WH-01", started="2026-09-21", noticed="~5 weeks later (≈26 Oct)", n_asof="2026-10-26"),
        dict(name="Zepto Bengaluru: best-selling face wash fell #3 → #13 in search", type="MARKETING", wh="ZEP-WH-07", started="2026-10-12", noticed="~1 month later (≈9 Nov)", n_asof="2026-11-09"),
        dict(name="Instamart Hyderabad: stopped ordering sunscreen for 2 weeks", type="KAM", wh="IM-WH-16", started="2026-09-14", noticed="~3 weeks later (≈5 Oct)", n_asof="2026-10-05"),
    ]
    backtest = []
    mondays = list(pd.date_range("2026-09-14", T, freq="7D"))
    cache = {m: engine.run_asof(D, m) for m in mondays}
    for k in known:
        match = lambda x: x["type"] == k["type"] and x["warehouse"] == k["wh"]
        flag = next(m for m in mondays if any(match(x) for x in cache[m]))
        tot = lambda m: sum(x["total"] for x in cache[m] if match(x))
        n_asof = pd.Timestamp(k["n_asof"])
        wk = (flag - pd.Timestamp(k["started"])).days // 7
        backtest.append(dict(name=k["name"], started=k["started"], noticed=k["noticed"], flag=flag, wk=wk, saved=max(tot(n_asof) - tot(flag), 0)))
    if a.backtest:
        print("Active alerts per Monday:", {m.strftime("%d %b"): sum(x["status"] != "CLOSED" for x in cache[m]) for m in mondays})
        for b in backtest: print(b)

msgs = text.messages(alerts, pulse)
out = os.path.join(a.out, T.strftime("%Y-%m-%d")); os.makedirs(out, exist_ok=True)
open(f"{out}/report.html", "w", encoding="utf-8").write(report.build(a.asof, alerts, pulse, msgs, backtest, raw["log"], extras))
open(f"{out}/whatsapp_messages.txt", "w", encoding="utf-8").write("\n\n".join(f"===== {w} =====\n{m}" for w, m in msgs.items()))
pd.DataFrame([{k: v for k, v in x.items() if k != "lines"} | {"products": "; ".join(l["name"] for l in x["lines"])} for x in alerts]).to_csv(f"{out}/alerts.csv", index=False)
print(f"{len([x for x in alerts if x['status'] != 'CLOSED'])} active alerts -> {out}/report.html")
