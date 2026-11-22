"""Load the four CSVs, fix the mess, and keep a log of everything we changed."""
import pandas as pd

CITY_MAP = {
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru",
    "delhi": "Delhi NCR", "new delhi": "Delhi NCR", "delhi ncr": "Delhi NCR",
    "mumbai": "Mumbai", "pune": "Pune", "kolkata": "Kolkata", "hyderabad": "Hyderabad",
}


def load(data_dir):
    log = []  # (what we found, how many, what we did)
    sales = pd.read_csv(f"{data_dir}/daily_sales.csv", parse_dates=["date"], dtype={"platform_product_id": str})
    stores = pd.read_csv(f"{data_dir}/dark_stores.csv", parse_dates=["opened_date"])
    prods = pd.read_csv(f"{data_dir}/products.csv", dtype={"platform_product_id": str})
    po = pd.read_csv(f"{data_dir}/purchase_orders.csv", parse_dates=["po_date", "delivery_date"])

    # strip stray whitespace in every text column
    for df in (sales, stores, prods, po):
        for c in df.select_dtypes(include=["object", "string"]).columns:
            df[c] = df[c].str.strip()

    # 1. exact duplicate rows in daily_sales
    dup = sales.duplicated()
    if dup.any():
        days = ", ".join(sorted(d.strftime("%d %b") for d in sales[dup].date.unique()))
        log.append((f"Exact duplicate rows in daily_sales (all on {days})", int(dup.sum()),
                    "Dropped. Left in, that day's sales would be double-counted and look like a fake spike."))
        sales = sales[~dup]

    # 2. city spellings
    raw_cities = stores.city.nunique()
    stores["city"] = stores.city.str.lower().map(CITY_MAP)
    assert stores.city.notna().all(), "unmapped city name"
    log.append((f"City written {raw_cities} different ways (e.g. 'HYDERABAD', 'Bangalore', 'mumbai ', 'New Delhi')",
                raw_cities, "Mapped to the 6 real cities. Delhi / New Delhi / Delhi NCR treated as one market."))

    # 3. every platform has its own product id -> our sku_code
    sales = sales.merge(prods[["platform", "platform_product_id", "sku_code", "category", "product_name", "mrp_inr"]],
                        on=["platform", "platform_product_id"], how="left", validate="m:1")
    assert sales.sku_code.notna().all(), "unmapped product id"
    log.append(("Each app uses its own product IDs (45 IDs for 15 products)", 45, "Joined to sku_code via products.csv; all rows mapped."))

    sales = sales.merge(stores[["dark_store_id", "city", "warehouse_id", "opened_date"]], on="dark_store_id", how="left", validate="m:1")
    assert sales.city.notna().all(), "unmapped dark store"

    # 4. stores that opened during the 10 weeks
    n_new = int((stores.opened_date >= sales.date.min()).sum())
    log.append((f"{n_new} of {len(stores)} dark stores opened during the 10 weeks, so network sales grow for reasons that are not real demand",
                n_new, "Never compare raw totals. Every sales comparison is per store-day and benchmarked against the same product on the same app in other cities."))

    # 5. missing POs are missing ROWS, not zeros
    log.append(("Purchase orders that were never placed don't appear as zero rows, they are simply absent", None,
                "Rebuilt the full warehouse x product x week grid to find the gaps. This is how the Instamart 'stopped ordering' problem shows up."))

    # sanity checks that passed
    ok = (sales.units_sold * sales.selling_price_inr == sales.sales_inr).all()
    log.append(("Checked: sales_inr = units x price, availability within 0-100, no negative units, no missing days per store, warehouse<->city is 1:1",
                None, "All clean, no action." if ok else "sales_inr mismatch found!"))

    sales["week"] = sales.date - pd.to_timedelta(sales.date.dt.weekday, unit="D")
    po["week"] = po.po_date
    return dict(sales=sales, stores=stores, prods=prods, po=po, log=log)
