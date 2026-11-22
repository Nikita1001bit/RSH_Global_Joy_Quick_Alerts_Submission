"""Detectors + sales-loss estimate. Everything is computed 'as of' a Monday, using only data before it,
so the same code can be replayed on past weeks (backtest) and run for 16 Nov."""
import numpy as np
import pandas as pd

P = dict(
    fill_thresh=0.70,     # PO delivered <70% = supply problem (normal is ~96%; worst random week in 10 weeks was 75%; real problems ran ~50%)
    min_short_units=24,   # ignore tiny POs where a few units short is noise
    rank_jump=3.0,        # search rank >=3 places worse than the product's own recent normal
    rank_hold=1.5,        # ...and the problem stays open until it's back within 1.5 places
    avail_floor=60,       # catch-all: weekly availability under 60% ...
    avail_drop=25,        # ...and 25+ points below the previous two weeks, with no supply/PO alert explaining it
    base_days=28,         # baseline for the loss estimate = up to 4 weeks before the problem started
    min_loss_inr=2000,    # don't show alerts costing less than this per week
)
TEAM = {"SUPPLY": "Supply team", "KAM": "KAM", "MARKETING": "Marketing", "UNEXPLAINED": "Quick Commerce Manager"}
D = pd.Timedelta(days=1)
W7 = pd.Timedelta(days=7)


class Data:
    def __init__(self, raw):
        s = raw["sales"]
        self.sales, self.po, self.stores, self.prods = s, raw["po"], raw["stores"], raw["prods"]
        self.name = raw["prods"].drop_duplicates("sku_code").set_index("sku_code").product_name.to_dict()
        # city-day-sku table (one row per platform x city x sku x day)
        self.cd = (s.groupby(["date", "week", "platform", "city", "warehouse_id", "sku_code"])
                   .agg(sales=("sales_inr", "sum"), units=("units_sold", "sum"), stores=("dark_store_id", "nunique"),
                        avail=("availability_pct", "mean"), rank=("search_rank", "mean")).reset_index())
        self.wh_city = s.drop_duplicates("warehouse_id").set_index("warehouse_id").city.to_dict()
        self.wh_platform = s.drop_duplicates("warehouse_id").set_index("warehouse_id").platform.to_dict()


def runs(weeks):
    """consecutive weeks -> list of (start, end)"""
    out = []
    for w in sorted(set(weeks)):
        if out and w - out[-1][1] == W7:
            out[-1][1] = w
        else:
            out.append([w, w])
    return [tuple(r) for r in out]


# ---------------------------------------------------------------- loss estimate
def loss_series(D_, platform, city, sku, start, end):
    """Rupees lost per day = what the product would normally have sold minus what it sold.
    'Normally' = its own sales per store-day in the 4 weeks before `start`, moved up/down by what the SAME
    product did on the same app in other cities (this strips out festive swings and new-store growth)."""
    cd = D_.cd
    g = cd[(cd.platform == platform) & (cd.sku_code == sku)]
    own = g[g.city == city].set_index("date")
    ctl = g[g.city != city].groupby("date")[["sales", "stores"]].sum()
    b0, b1 = max(cd.date.min(), start - P["base_days"] * D), start - D
    if b1 < b0:
        return pd.Series(dtype=float)
    ob, cb = own.loc[b0:b1], ctl.loc[b0:b1]
    if ob.stores.sum() == 0 or cb.stores.sum() == 0 or cb.sales.sum() == 0:
        return pd.Series(dtype=float)
    base = ob.sales.sum() / ob.stores.sum()
    idx = (ctl.sales / ctl.stores) / (cb.sales.sum() / cb.stores.sum())
    w = own.loc[start:end]
    return base * idx.reindex(w.index).fillna(1) * w.stores - w.sales


def summarise_loss(D_, lines, platform, city, T, closed_until):
    """lines: [(sku, start_date)] -> dict(total, last_week, runrate)"""
    tot = lw = rr = 0.0
    end = min(T - D, closed_until)
    for sku, start in lines:
        ls = loss_series(D_, platform, city, sku, start, end)
        if ls.empty:
            continue
        tot += max(ls.sum(), 0)
        lw += max(ls.loc[T - W7:T - D].sum(), 0) if end >= T - D else 0
        rr += max(ls.loc[T - 3 * D:T - D].sum() * 7 / 3, 0) if end >= T - D else 0
    return dict(total=tot, last_week=lw, runrate=rr)


# ---------------------------------------------------------------- detectors (return one row per product-week flagged)
def detect_fill(D_, T):
    po = D_.po[D_.po.po_date < T].copy()
    po["short"] = po.qty_ordered - po.qty_delivered
    po["fill"] = po.qty_delivered / po.qty_ordered
    f = po[(po.fill < P["fill_thresh"]) & (po.short >= P["min_short_units"])].copy()
    f["type"] = "SUPPLY"
    return f


def detect_missing_po(D_, T):
    po = D_.po[D_.po.po_date < T]
    weeks = sorted(po.po_date.unique())
    rows = []
    seen = {}  # (wh, sku) -> last qty ordered
    byw = {w: po[po.po_date == w] for w in weeks}
    for w in weeks:
        cur = byw[w]
        for wh, g in cur.groupby("warehouse_id"):
            have = set(g.sku_code)
            for sku in set(po[(po.warehouse_id == wh) & (po.po_date < w)].sku_code) - have:
                prev = po[(po.warehouse_id == wh) & (po.sku_code == sku) & (po.po_date < w)].sort_values("po_date")
                rows.append(dict(type="KAM", po_date=w, warehouse_id=wh, sku_code=sku,
                                 platform=D_.wh_platform[wh], last_qty=int(prev.qty_ordered.iloc[-1]),
                                 last_po=prev.po_date.iloc[-1]))
    return pd.DataFrame(rows)


def detect_rank(D_, T):
    cd = D_.cd[D_.cd.date < T]
    wk = cd.groupby(["platform", "city", "sku_code", "week"]).agg(rank=("rank", "mean")).reset_index()
    rows = []
    for (pl, city, sku), g in wk.groupby(["platform", "city", "sku_code"]):
        g = g.sort_values("week")
        base, in_ep, hist = None, False, []
        for _, r in g.iterrows():
            if not in_ep:
                if hist and r["rank"] - np.mean(hist[-4:]) >= P["rank_jump"]:
                    in_ep, base = True, np.mean(hist[-4:])
                else:
                    hist.append(r["rank"])
                    continue
            elif r["rank"] - base < P["rank_hold"]:
                in_ep, hist = False, hist + [r["rank"]]
                continue
            rows.append(dict(type="MARKETING", platform=pl, city=city, sku_code=sku, week=r.week,
                             rank=r["rank"], base_rank=base))
    return pd.DataFrame(rows)


def detect_unexplained(D_, T, covered):
    cd = D_.cd[D_.cd.date < T]
    wk = cd.groupby(["platform", "city", "warehouse_id", "sku_code", "week"]).agg(avail=("avail", "mean")).reset_index().sort_values("week")
    wk["prev"] = wk.groupby(["platform", "city", "sku_code"]).avail.transform(lambda x: x.shift(1).rolling(2, min_periods=1).mean())
    f = wk[(wk.avail < P["avail_floor"]) & (wk.prev - wk.avail >= P["avail_drop"])].copy()
    f = f[[(r.warehouse_id, r.sku_code, r.week) not in covered for r in f.itertuples()]]
    f["type"] = "UNEXPLAINED"
    return f


# ---------------------------------------------------------------- build alerts
def run_asof(D_, T):
    T = pd.Timestamp(T)
    W = T - W7  # last full week
    alerts = []

    fill = detect_fill(D_, T)
    miss = detect_missing_po(D_, T)
    rank = detect_rank(D_, T)
    covered = set()
    for r in fill.itertuples():
        covered |= {(r.warehouse_id, r.sku_code, r.po_date), (r.warehouse_id, r.sku_code, r.po_date + W7)}
    for r in miss.itertuples():
        covered |= {(r.warehouse_id, r.sku_code, r.po_date), (r.warehouse_id, r.sku_code, r.po_date + W7)}
    unex = detect_unexplained(D_, T, covered)

    def avail_stats(wh, sku, week):
        c = D_.cd[(D_.cd.warehouse_id == wh) & (D_.cd.sku_code == sku) & (D_.cd.date < T)]
        a = c[c.week == week].avail.mean()
        b = c[(c.week < week) & (c.week >= week - 2 * W7)].avail.mean()
        return (round(b) if pd.notna(b) else None), (round(a) if pd.notna(a) else None)

    # --- supply + KAM: one alert per warehouse per run of consecutive weeks
    for typ, df, wcol in (("SUPPLY", fill, "po_date"), ("KAM", miss, "po_date")):
        if df is None or df.empty:
            continue
        for wh, g in df.groupby("warehouse_id"):
            for s, e in runs(g[wcol]):
                gg = g[(g[wcol] >= s) & (g[wcol] <= e)]
                pl, city = D_.wh_platform[wh], D_.wh_city[wh]
                closed = e < W
                lines = []
                for sku, h in gg.groupby("sku_code"):
                    first = h[wcol].min()
                    ln = dict(sku=sku, name=D_.name[sku], first_week=first, weeks=len(h))
                    if typ == "SUPPLY":
                        ln.update(ordered=int(h.qty_ordered.sum()), delivered=int(h.qty_delivered.sum()),
                                  short=int(h.short.sum()), fill=h.qty_delivered.sum() / h.qty_ordered.sum(),
                                  latest_fill=float(h.sort_values(wcol).fill.iloc[-1]))
                    else:
                        ln.update(last_qty=int(h.last_qty.iloc[0]), last_po=h.last_po.iloc[0])
                    ln["avail_before"], ln["avail_now"] = avail_stats(wh, sku, e if not closed else s)
                    lines.append(ln)
                loss = summarise_loss(D_, [(l["sku"], l["first_week"]) for l in lines], pl, city, T,
                                      (e + 13 * D) if closed else T)
                alerts.append(dict(type=typ, platform=pl, city=city, warehouse=wh, start=s, end=e,
                                   status="CLOSED" if closed else ("NEW" if s == W else "ONGOING"),
                                   weeks=(e - s).days // 7 + 1, lines=lines, **loss))

    # --- marketing: rank slides
    if not rank.empty:
        for (pl, city, sku), g in rank.groupby(["platform", "city", "sku_code"]):
            for s, e in runs(g.week):
                gg = g[(g.week >= s) & (g.week <= e)]
                closed = e < W
                base = gg.base_rank.iloc[0]
                daily = D_.cd[(D_.cd.platform == pl) & (D_.cd.city == city) & (D_.cd.sku_code == sku) & (D_.cd.date >= s) & (D_.cd.date < T)].sort_values("date")
                hit = daily[daily["rank"] >= base + P["rank_jump"]]
                onset = hit.date.iloc[0] if len(hit) else s
                wh = daily.warehouse_id.iloc[0]
                av = daily[daily.date >= (e if not closed else s)].avail.mean()
                loss = summarise_loss(D_, [(sku, s)], pl, city, T, (e + 6 * D) if closed else T)
                alerts.append(dict(type="MARKETING", platform=pl, city=city, warehouse=wh, start=s, end=e,
                                   status="CLOSED" if closed else ("NEW" if s == W else "ONGOING"),
                                   weeks=(e - s).days // 7 + 1, onset=onset,
                                   lines=[dict(sku=sku, name=D_.name[sku], base_rank=base, rank_now=gg["rank"].iloc[-1],
                                               avail_now=round(av), first_week=s)], **loss))

    # --- unexplained availability crash (catch-all)
    if not unex.empty:
        for (pl, city, wh, sku), g in unex.groupby(["platform", "city", "warehouse_id", "sku_code"]):
            for s, e in runs(g.week):
                closed = e < W
                loss = summarise_loss(D_, [(sku, s)], pl, city, T, (e + 6 * D) if closed else T)
                alerts.append(dict(type="UNEXPLAINED", platform=pl, city=city, warehouse=wh, start=s, end=e,
                                   status="CLOSED" if closed else ("NEW" if s == W else "ONGOING"),
                                   weeks=(e - s).days // 7 + 1,
                                   lines=[dict(sku=sku, name=D_.name[sku], first_week=s,
                                               avail_before=round(g.prev.iloc[0]), avail_now=round(g.avail.iloc[-1]))], **loss))

    for a in alerts:
        a["team"] = TEAM[a["type"]] if a["type"] != "KAM" else f"{a['platform']} KAM"
        a["impact"] = a["runrate"] if a["status"] != "CLOSED" else 0
    # drop trivial active alerts so the list stays short
    # (a missing PO is a hard yes/no signal and costs more every week, so it is never filtered by rupees)
    alerts = [a for a in alerts if a["status"] == "CLOSED" or a["type"] == "KAM"
              or a["runrate"] >= P["min_loss_inr"] or a["last_week"] >= P["min_loss_inr"]]
    alerts.sort(key=lambda a: (a["status"] == "CLOSED", -max(a["runrate"], a["last_week"])))
    return alerts


def network_pulse(D_, T):
    T = pd.Timestamp(T)
    W = T - W7
    s = D_.sales
    cur, prev = s[s.week == W], s[s.week == W - W7]
    po = D_.po
    pc, pp = po[po.po_date == W].groupby("warehouse_id").qty_ordered.sum(), po[po.po_date == W - W7].groupby("warehouse_id").qty_ordered.sum()
    like = s[s.opened_date < W - W7]
    return dict(week_start=W, sales=cur.sales_inr.sum(), prev_sales=prev.sales_inr.sum(),
                like_chg=like[like.week == W].sales_inr.sum() / like[like.week == W - W7].sales_inr.sum() - 1,
                po_chg=pc.sum() / pp.sum() - 1, wh_down=int((pc.reindex(pp.index) < pp).sum()), wh_total=len(pp),
                stores=cur.dark_store_id.nunique())
