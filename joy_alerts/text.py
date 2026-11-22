"""Plain-English wording for each alert type: what we see, what to do, and the WhatsApp messages."""
import pandas as pd


def inr(x):
    x = float(x)
    if x >= 1e5:
        return f"₹{x / 1e5:.1f}L"
    if x >= 1e4:
        return f"₹{round(x / 1e3):.0f}k"
    if x >= 1e3:
        return f"₹{x / 1e3:.1f}k"
    return f"₹{round(x, -1):.0f}"


def d(ts, year=False):
    timestamp = pd.Timestamp(ts)
    month_year = timestamp.strftime("%b" + (" %Y" if year else ""))
    return f"{timestamp.day} {month_year}"


def short(name):
    return name.replace("Joy ", "")


def title(a):
    if a["type"] == "SUPPLY":
        o = sum(l["ordered"] for l in a["lines"]); dl = sum(l["delivered"] for l in a["lines"])
        return f"{a['platform']} {a['city']}: we delivered only {dl / o:.0%} of what {a['warehouse']} ordered"
    if a["type"] == "KAM":
        n = len(a["lines"])
        what = short(a["lines"][0]["name"]) if n == 1 else f"{n} products ({', '.join(short(l['name']) for l in a['lines'])})"
        return f"{a['platform']} {a['city']}: {a['warehouse']} has stopped ordering {what}"
    if a["type"] == "MARKETING":
        l = a["lines"][0]
        return f"{a['platform']} {a['city']}: {short(l['name'])} slid from #{l['base_rank']:.0f} to #{l['rank_now']:.0f} in search"
    l = a["lines"][0]
    return f"{a['platform']} {a['city']}: {short(l['name'])} availability crashed to {l['avail_now']}%"


def facts(a, D_=None, extra=None):
    """bullets: what the data shows"""
    out = []
    ln = a["lines"]
    if a["type"] == "SUPPLY":
        tot_short = sum(l["short"] for l in ln)
        out.append(f"{len(ln)} product{'s' if len(ln) > 1 else ''} short, {tot_short:,} units missing in total. Normal fill rate for this warehouse is ~96%.")
        av = [(l["avail_before"], l["avail_now"]) for l in ln if l["avail_before"] is not None and l["avail_now"] is not None]
        if av:
            b = sum(x for x, _ in av) / len(av); n = sum(y for _, y in av) / len(av)
            out.append(f"Dark-store availability for these products fell from ~{b:.0f}% to ~{n:.0f}%, so stores are already running out.")
        if a["weeks"] > 1:
            out.append(f"Short on {a['weeks']} POs in a row (since the {d(a['start'])} PO).")
        else:
            out.append(f"First seen on the {d(a['start'])} PO (delivered {d(a['start'] + pd.Timedelta(days=3))}-{d(a['start'] + pd.Timedelta(days=4))}).")
    elif a["type"] == "KAM":
        l0 = ln[0]
        out.append(f"No PO line at all for {'these products' if len(ln) > 1 else 'this product'} on the {', '.join(d(w) for w in sorted({l['first_week'] + pd.Timedelta(days=7 * i) for l in ln for i in range(l['weeks'])}))} PO{'s' if a['weeks'] > 1 else ''}, while the same warehouse placed orders for its other products.")
        out.append(f"It ordered every week before (last order: {l0['last_qty']} units on {d(l0['last_po'])}).")
        av = [(l["avail_before"], l["avail_now"]) for l in ln if l["avail_before"] is not None and l["avail_now"] is not None]
        if av:
            out.append(f"Dark-store availability: ~{sum(x for x, _ in av) / len(av):.0f}% -> ~{sum(y for _, y in av) / len(av):.0f}%. Stores are running dry.")
        out.append("The data can't tell us why (delisted? blocked in their system? a one-off miss?). That's the question for the KAM.")
    elif a["type"] == "MARKETING":
        l = ln[0]
        out.append(f"Average search rank in {a['city']} moved from #{l['base_rank']:.1f} (usual) to #{l['rank_now']:.1f} since ~{d(a['onset'])}. Other products and other cities are unchanged.")
        out.append(f"Stock is fine (availability {l['avail_now']}%), so the sales loss is a visibility problem, not a supply problem.")
        if extra:
            out.append(extra)
    else:
        l = ln[0]
        out.append(f"Availability fell from ~{l['avail_before']}% to {l['avail_now']}%, and no supply shortfall or missing PO explains it.")
    return out


def action(a):
    plat, city = a["platform"], a["city"]
    if a["type"] == "SUPPLY":
        u = sum(l["short"] for l in a["lines"])
        return (f"Dispatch the {u:,} missing units to {a['warehouse']} now (table above). Find out why the PO was only part-filled (factory stock, transport, packing?). "
                f"Make sure this Monday's PO is delivered in full, and warn {plat} early if it won't be.")
    if a["type"] == "KAM":
        return (f"Ask the {plat} KAM today: is the listing paused, delisted or blocked at {a['warehouse']}? Get a PO raised this week and ask for an expedited delivery. "
                f"Every week without an order is stock-outs in {city}.")
    if a["type"] == "MARKETING":
        return (f"Turn on / raise sponsored ads on the category keyword for this product on {plat} {city}. Check the listing (price vs competitors, images, rating, delivery tag) "
                f"and ask the {plat} KAM whether the ranking algorithm or the listing changed around {d(a['onset'])}.")
    return f"Ask Supply and the {plat} KAM whether this product is blocked or out of stock at {a['warehouse']}."


def messages(alerts, pulse):
    act = [a for a in alerts if a["status"] != "CLOSED"]
    M = {}
    sup = [a for a in act if a["type"] == "SUPPLY"]
    if sup:
        t = ["*Joy QC: Supply action, week of 9 Nov*"]
        for a in sup:
            t.append(f"\n*{a['platform']} {a['city']} ({a['warehouse']})*: delivered {sum(l['delivered'] for l in a['lines']) / sum(l['ordered'] for l in a['lines']):.0%} of PO dated {d(a['end'])}")
            for l in a["lines"]:
                t.append(f"• {short(l['name'])}: ordered {l['ordered']}, delivered {l['delivered']} (short {l['short']})")
            t.append(f"Please: send the missing units this week, tell us the reason, and fill Monday's PO in full. Stores already at ~{min(l['avail_now'] for l in a['lines'] if l['avail_now'] is not None)}% availability.")
        M["Supply team"] = "\n".join(t)
    for plat in ("Blinkit", "Zepto", "Instamart"):
        kam = [a for a in act if a["type"] in ("KAM", "UNEXPLAINED") and a["platform"] == plat]
        if kam:
            t = [f"*Joy x {plat}: please check this week*"]
            for a in kam:
                for l in a["lines"]:
                    t.append(f"• {a['city']} warehouse {a['warehouse']} has not raised a PO for {l['name']} for {a['weeks']} week{'s' if a['weeks'] > 1 else ''}"
                             f" (its last order was {l.get('last_qty', '~')} units). Our stores there are at ~{l['avail_now']}% availability.")
            t.append("Can you confirm whether the listing is live / not blocked, and get a PO raised this week? Thanks!")
            M[f"{plat} KAM"] = "\n".join(t)
    mk = [a for a in act if a["type"] == "MARKETING"]
    if mk:
        t = ["*Joy QC: Marketing, visibility drop*"]
        for a in mk:
            l = a["lines"][0]
            t.append(f"• {a['platform']} {a['city']}: {l['name']} fell from #{l['base_rank']:.0f} to #{l['rank_now']:.0f} in search since ~{d(a['onset'])}. "
                     f"Stock is fine. Costing ~{inr(a['runrate'])}/week ({inr(a['total'])} so far).")
        t.append("Please boost ads on the category keyword and check the listing. Update us by Wednesday.")
        M["Marketing"] = "\n".join(t)
    t = [f"*Joy QC weekly, {d(pulse['week_start'])} to {d(pulse['week_start'] + pd.Timedelta(days=6))}*",
         f"Sales {inr(pulse['sales'])} ({pulse['like_chg']:+.0%} vs last week, in line with every warehouse ordering less after the festive peak: no action)."]
    if act:
        t.append(f"\n{len(act)} things need action, ~{inr(sum(a['impact'] for a in act))}/week of sales at stake:")
        for i, a in enumerate(act, 1):
            t.append(f"{i}. {a['platform']} {a['city']}: {title(a).split(': ', 1)[1]}. ~{inr(a['impact'])}/wk → {a['team']}")
    else:
        t.append("\nNothing needs action this week.")
    M["Quick Commerce Manager"] = "\n".join(t)
    return M
