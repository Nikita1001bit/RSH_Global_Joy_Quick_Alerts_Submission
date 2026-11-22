# Joy QC Alerts: Technical Documentation

Version 1.0 · Reference date of the shipped output: Monday 16 November 2026 · Language: Python 3.10+

## 1. Purpose and scope

Joy sells face wash, creams, lotions, sunscreens and serums on Blinkit, Zepto and Swiggy Instamart across six cities. Every week the Quick Commerce Manager used to spend half a day building pivot tables from about 20,000 rows of sales and stock data, then send WhatsApp messages to Supply, platform Key Account Managers (KAMs) and Marketing.

This project automates that Monday routine. Given the four CSV exports, it:

1. Cleans the data and logs every fix it makes.
2. Runs four detection rules to find problems that are costing sales.
3. Estimates the rupees each problem is costing.
4. Produces a ranked list of actions, each with an owner, evidence, a recommended action and a ready-to-send WhatsApp message.
5. Can be replayed on any past Monday to prove it would have caught earlier problems in week 1.

**Design goals:** few alerts (the shipped data never produces more than 3 active alerts in a week), plain language per team, rupee-ranked priority, and an "as-of" model that never peeks at the future.

**Out of scope:** live data connections, authentication, sending WhatsApp messages automatically, forecasting, and root-cause diagnosis (the tool tells you *where* and *how much*, not *why*).

## 2. Quick start

### 2.1 Requirements

| Package | Used for |
| --- | --- |
| pandas >= 2.0, numpy | all data work |
| streamlit >= 1.40 | the interactive dashboard (`dashboard.py`) |
| reportlab | the PDF download inside the dashboard (**missing from requirements.txt, see section 12**) |
| playwright (optional) | `make_pdf.py` only, to print `report.html` to PDF/PNG |

```bash
python -m pip install -r requirements.txt
python -m pip install reportlab        # needed by dashboard.py
```

### 2.2 Run the dashboard

```bash
python -m streamlit run dashboard.py
# Windows, if port 8501 is blocked:
python -m streamlit run dashboard.py --server.port 8501
```

Choose a **Reporting Monday** in the sidebar (14 Sep to 16 Nov 2026). The alerts, messages and PDF update for that Monday.

### 2.3 Run the command-line report

```bash
python run.py --data data --asof 2026-11-16 --out output --backtest
```

Creates `output/2026-11-16/` containing `report.html`, `whatsapp_messages.txt` and `alerts.csv`. With `--backtest` it also prints the number of active alerts for each past Monday and the detection lag for the three known problems.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--data` | `data` | folder holding the four CSVs |
| `--asof` | `2026-11-16` | the reporting Monday; only data before this date is used |
| `--out` | `output` | output folder |
| `--backtest` | off | print the replay summary (the HTML always includes the backtest table) |

## 3. Repository layout

| Path | Role |
| --- | --- |
| `data/` | the four input CSVs |
| `joy_alerts/clean.py` | load, de-duplicate, standardise, join, log data issues |
| `joy_alerts/engine.py` | parameters, detectors, loss estimate, alert assembly, network pulse |
| `joy_alerts/text.py` | plain-English titles, facts, actions, WhatsApp messages, number formatting |
| `joy_alerts/report.py` | self-contained HTML report builder |
| `run.py` | command-line entry point and backtest |
| `dashboard.py` | Streamlit web app with sidebar date picker and PDF export (current UI) |
| `app.py` | an earlier Streamlit draft, **stale and not runnable** (section 12) |
| `make_pdf.py` | prints an HTML report to PDF and PNG using Playwright |
| `NOTE.md` | the half-page submission note |
| `README.md` | short run instructions |

## 4. Architecture and data flow

```
 4 CSVs --> clean.load() --> raw dict {sales, stores, prods, po, log}
                                   |
                          engine.Data(raw)   (builds city-day-SKU table `cd`)
                                   |
        engine.run_asof(D, Monday) --> list of alert dicts (sorted)
        engine.network_pulse(D, Monday) --> headline numbers
                                   |
                text.messages(alerts, pulse) --> WhatsApp text per team
                                   |
        +--------------------------+---------------------------+
   report.build() -> HTML     dashboard.py -> Streamlit     alerts.csv
```

Everything downstream of `run_asof` is presentation. All business logic lives in `engine.py`.

## 5. Input data

Period: Monday 7 Sep to Sunday 15 Nov 2026 (10 Monday-to-Sunday weeks).

### 5.1 daily\_sales.csv (186,285 raw rows; one row per dark store, product, day)

| Column | Meaning |
| --- | --- |
| date, platform, dark\_store\_id | day, app, dark store |
| platform\_product\_id | the app's own product ID (differs per app) |
| availability\_pct | share of the day the product was orderable, 0 to 100 |
| units\_sold, selling\_price\_inr, sales\_inr | `sales_inr` = units x price paid |
| search\_rank | position in the category search (1 is best) |

### 5.2 dark\_stores.csv (202 rows)

`dark_store_id, platform, city, pincode, warehouse_id, opened_date`. `warehouse_id` is the platform warehouse that supplies the store. Each warehouse serves exactly one city.

### 5.3 products.csv (45 rows = 15 products x 3 apps)

`platform, platform_product_id, sku_code, product_name, category, pack_size, mrp_inr`. `sku_code` is Joy's internal key.

### 5.4 purchase\_orders.csv (2,694 rows)

`po_id, po_date, platform, warehouse_id, sku_code, qty_ordered, qty_delivered, delivery_date`. One row per warehouse, SKU and Monday. Delivery happens 2 to 4 days after the PO. A PO that was never placed has **no row** (it is not a zero).

## 6. Data cleaning (`clean.py`)

`clean.load(data_dir)` returns a dict: `sales` (enriched daily table), `stores`, `prods`, `po`, and `log` (a list of `(finding, count, action)` tuples that is shown in the report).

Steps, in order:

1. **Read** the CSVs. `platform_product_id` is read as a string so IDs are never mangled.
2. **Strip whitespace** in every text column (for example `'mumbai '`).
3. **Drop exact duplicate rows** in sales. In this data there are 765, all on 2 Oct. Left in, that day would be double-counted and look like a spike.
4. **Normalise cities.** 11 raw spellings (`HYDERABAD`, `Bangalore`, `New Delhi`, `Delhi`, `Delhi NCR`, and so on) are mapped through `CITY_MAP` to the six real cities. Delhi, New Delhi and Delhi NCR are treated as one market. An `assert` fails loudly if a new, unmapped city appears.
5. **Map product IDs** to `sku_code`, `category`, `product_name` and `mrp_inr` with a many-to-one merge on `(platform, platform_product_id)`. An `assert` fails if any row is unmapped.
6. **Attach store attributes** (`city`, `warehouse_id`, `opened_date`) to each sales row.
7. **Log context:** 51 of 202 stores opened inside the 10 weeks; missing POs are absent rows; and checks that passed (sales = units x price, availability in 0 to 100, no negative units, no missing store-days, warehouse to city is 1:1).
8. **Add `week`** (the Monday of each date) to sales, and `week = po_date` to POs.

Columns of the returned `sales` table: the nine original columns, plus `sku_code, category, product_name, mrp_inr, city, warehouse_id, opened_date, week`.

## 7. The engine (`engine.py`)

### 7.1 Parameters (`P`)

| Key | Value | Meaning and rationale |
| --- | --- | --- |
| `fill_thresh` | 0.70 | a PO delivered under 70% is a supply problem. Normal is about 96%; the worst random week in the data was 75%; real problems ran about 50% |
| `min_short_units` | 24 | ignore tiny POs where a few units short is noise |
| `rank_jump` | 3.0 | rank at least 3 places worse than the product's own recent normal |
| `rank_hold` | 1.5 | a rank problem stays open until rank is back within 1.5 places |
| `avail_floor` | 60 | catch-all: weekly availability under 60% |
| `avail_drop` | 25 | ...and at least 25 points below the previous two weeks |
| `base_days` | 28 | loss baseline = up to 4 weeks before the problem started |
| `min_loss_inr` | 2000 | hide active alerts below this many rupees per week (missing POs are exempt) |

These were chosen after looking at the 10 weeks provided, so they should be re-tuned on real, longer history.

### 7.2 The `Data` class

Built once per run. It holds the raw tables plus:

- `cd`: the **city-day-SKU table**, one row per `(date, week, platform, city, warehouse_id, sku_code)` with `sales`, `units`, `stores` (distinct dark stores), `avail` (mean) and `rank` (mean). Almost all detection and loss maths runs on this table.
- `name`: SKU to product name; `wh_city` and `wh_platform`: warehouse lookups.

### 7.3 The as-of model

`run_asof(D, T)` takes a Monday `T` and defines `W = T - 7 days`, the **last full week**. It uses only sales dated before `T` and POs with `po_date < T`. A PO dated on `T` itself is excluded because its delivery is not yet known. This is what makes the backtest honest: the 28 Sep run sees exactly what a manager would have seen on 28 Sep.

Helper `runs(weeks)` merges consecutive Mondays (7 days apart) into `(start, end)` episodes.

### 7.4 Detector 1: supply shortfall (`detect_fill`, team: Supply)

For each PO row, `short = qty_ordered - qty_delivered` and `fill = qty_delivered / qty_ordered`. A row is flagged when `fill < 0.70` **and** `short >= 24`.

### 7.5 Detector 2: stopped ordering (`detect_missing_po`, team: platform KAM)

For each PO week and each warehouse that placed any order that week, find SKUs that warehouse had ordered in an earlier week but that have no row now. Records `last_qty` and `last_po` for the message. Because the check is relative to the same warehouse's other orders, a warehouse that simply did not order anything is not flagged.

### 7.6 Detector 3: search rank slide (`detect_rank`, team: Marketing)

Per `(platform, city, SKU)` it computes the weekly mean rank and walks the weeks as a small state machine:

- **Start** an episode when the week's rank is at least `rank_jump` worse than the mean of the last 4 *non-flagged* weeks. That mean is **frozen** as the episode baseline.
- **Continue** while rank minus the frozen baseline is at least `rank_hold`.
- **Close** when rank returns within `rank_hold` of baseline.

Freezing the baseline matters: a rolling baseline would absorb the drop and silently "heal" the alert. The onset date shown to users is the first day the daily rank is at least `base + 3`.

### 7.7 Detector 4: unexplained availability crash (`detect_unexplained`, team: Quick Commerce Manager)

A safety net for problems outside the first three types. Per `(warehouse, SKU, week)`, flag when weekly availability is under 60% and at least 25 points below the mean of the previous two weeks. Weeks already explained by a supply or missing-PO flag (same week or the following week, to allow for delivery lag) are excluded. It produced no alerts on the supplied data.

### 7.8 The loss estimate (`loss_series`, `summarise_loss`)

Goal: estimate rupees lost to a problem without being fooled by festive demand swings or new stores.

For one product in one city, starting on date `start`:

1. **Baseline** = the product's own sales per store-day over the up-to-28 days before `start` (`b0` to `b1`).
2. **Control index (per day)** = sales per store-day of the *same product on the same app in all other cities*, divided by that control group's own baseline sales per store-day.
3. **Expected sales (day)** = baseline x control index x number of stores that day.
4. **Loss (day)** = expected minus actual.

`summarise_loss` sums over a product list and returns three numbers:

| Output | Definition |
| --- | --- |
| `total` | sum of daily loss from the start date to the end of the window, floored at zero per product |
| `last_week` | loss over the last 7 days before `T` (active alerts only) |
| `runrate` | loss over the last 3 days x 7/3 (active alerts only) |

The run-rate exists because a late-week delivery shortfall only partly hits the last full week. Closed alerts have `last_week = runrate = 0`. The loss window for a closed alert ends 13 days after its last flagged week for supply and PO problems (to allow for stock lag) and 6 days for rank problems. If there is no baseline (the problem starts on the first day of data) or the control group has no sales, the product contributes nothing.

### 7.9 Alert assembly (`run_asof`)

- **Supply and KAM alerts** are grouped **per warehouse per run of consecutive weeks**, so six short products become one alert with six lines. Each line carries ordered, delivered, short, fill, and availability before and now.
- **Marketing and Unexplained alerts** are one per `(platform, city, SKU)` run.
- **Status:** `CLOSED` if the run ended before `W`; `NEW` if it started in `W`; otherwise `ONGOING`. `weeks` is the run length.
- **Team:** Supply team, `<Platform> KAM`, Marketing, or Quick Commerce Manager.
- **Impact** = `runrate` for active alerts, 0 for closed.
- **Noise filter:** keep closed alerts, all KAM alerts, and active alerts whose run-rate or last-week loss is at least `min_loss_inr`.
- **Sort:** active before closed, then by rupees per week, largest first.

### 7.10 Alert record

| Key | Type | Notes |
| --- | --- | --- |
| `type` | str | `SUPPLY`, `KAM`, `MARKETING`, `UNEXPLAINED` |
| `team` | str | owner shown in the UI |
| `platform`, `city`, `warehouse` | str | location |
| `start`, `end` | Timestamp | first and last flagged Monday |
| `status`, `weeks` | str, int | `NEW` / `ONGOING` / `CLOSED`, run length |
| `lines` | list of dict | per-product detail (varies by type) |
| `total`, `last_week`, `runrate`, `impact` | float | rupees |
| `onset` | Timestamp | marketing only: first bad day |

### 7.11 Network pulse (`network_pulse`)

Headline numbers for the latest full week: total sales, prior-week sales, **like-for-like change** (only stores opened before the prior week), total PO quantity change, how many warehouses ordered less than the week before, and the active store count. It exists so the report can explain a network-wide dip (for example post-festive) as *not a problem*, instead of alerting on it.

## 8. Text layer (`text.py`)

| Function | Purpose |
| --- | --- |
| `inr(x)` | rupee formatting: `₹3.2L`, `₹44k`, `₹7.5k`, `₹850` |
| `d(ts, year=False)` | day-month date such as `9 Nov` (see section 12 on Windows) |
| `short(name)` | drops the "Joy " prefix |
| `title(alert)` | one-line headline per type |
| `facts(alert, extra)` | evidence bullets; `extra` carries the "warehouse cut its orders" sentence for rank alerts |
| `action(alert)` | the recommended action for the owner |
| `messages(alerts, pulse)` | dict of WhatsApp messages: Supply team, one per platform KAM, Marketing, and always a Quick Commerce Manager summary |

Wording rules: Supply gets warehouses, products and units. Marketing and the manager get rupees and ranks. KAM messages say plainly that the data cannot show *why* an order is missing; they ask the KAM to find out.

## 9. Outputs

### 9.1 HTML report (`report.py`, `report.build`)

A single self-contained file (no external assets), responsive, with light and dark mode. Sections: headline cards and the pulse note; **1. Act on these, biggest first**; **2. Recovered recently**; **3. Messages ready to send** (Copy buttons); **4. Backtest table**; **5. What was messy in the data**.

### 9.2 CSV and text

`alerts.csv` has one row per alert (all fields except `lines`, plus a `products` column). `whatsapp_messages.txt` has one block per team.

### 9.3 Backtest (`run.py`)

Replays every Monday from 14 Sep to the chosen date. For each of three hard-coded known problems it finds the first Monday an alert of the right type and warehouse appears, and estimates **sales protected** as the difference between the alert's total loss on the date the brief says it was noticed and on the flag date.

| Problem | Started | Flagged by tool |
| --- | --- | --- |
| Blinkit Bengaluru, BLK-WH-01, about 50% fill | 21 Sep | Mon 28 Sep |
| Zepto Bengaluru, Neem Face Wash 100ml, rank #3 to #13 | 12 Oct | Mon 19 Oct |
| Instamart Hyderabad, IM-WH-16, sunscreen POs missing | 14 Sep | Mon 21 Sep |

The "noticed by us" dates are approximations of the brief's "about 5 weeks, a month, 3 weeks".

## 10. The dashboard (`dashboard.py`)

Streamlit app, wide layout, light custom theme injected through a `<style>` block.

- `load_data()` is wrapped in `st.cache_resource`: CSVs are cleaned and `Data` is built once per server process.
- `get_report(asof)` is wrapped in `st.cache_data(ttl=300)`: runs the engine, pulse and messages, and builds the "warehouse cut its orders" extra for rank alerts. Cache entries last 5 minutes.
- `render_alert()` builds each card's HTML (team tag, status, headline, rupee metrics, evidence, supply table, action box). It HTML-escapes all text.
- The sidebar holds the **Reporting Monday** select box (newest first) and a **Download report** button.
- Below the cards: messages (rendered text plus a copyable code block), a **Data checks** expander, and a **Download alert data** expander (CSV).
- `build_pdf()` uses ReportLab to create an A4 PDF with the same sections (KPIs, alerts, messages, data checks). It runs on every page load.

## 11. Key design decisions

| Decision | Reason |
| --- | --- |
| As-of replay instead of a single report | proves week-1 detection and prevents hindsight bias |
| Four rules only, each mapped to one owner | each alert is actionable by a specific team; low volume |
| Compare against the same product in other cities | removes festive swings and new-store growth without a forecasting model |
| Per store-day normalisation | 51 stores opened mid-period |
| Frozen rank baseline | stops a long problem from becoming the new normal |
| One alert per warehouse, not per SKU | six short products should be one message, not six |
| Missing POs exempt from the rupee filter | a hard yes/no signal that gets costlier each week |
| Run-rate from the last 3 days | late-week deliveries only partly affect the last full week |
| Recovered issues shown separately | builds trust and shows the cost of past problems |
| Static, dependency-light HTML report | easy to email and print; works offline |

## 12. Known limitations and issues

**Found in the shipped package** (recommended fixes):

1. **`requirements.txt` is missing `reportlab`.** `dashboard.py` imports it, so a clean install fails with `ModuleNotFoundError`. Add `reportlab` to the file.
2. **`app.py` is stale.** It calls `load_data()` expecting six return values (the function returns two) and uses `selected` before it is defined. Delete it or keep only `dashboard.py`.
3. **README mentions a "Create / print report" button** that the current dashboard does not have; the PDF button is "Download report" in the sidebar.
4. **Windows date formatting.** The original `d()` used `strftime('%-d')`, which Windows rejects with `ValueError: Invalid format string`. The shipped `text.py` already uses `timestamp.day` and is correct.
5. **Possible lost evidence line on cached reports.** `extras` is keyed by `id(alert)`. Because `st.cache_data` returns copies of cached values, those object IDs can differ from the ones used when `extras` was built, so the "warehouse already cut its orders" bullet may silently disappear on the dashboard. Safer: key it by `(type, warehouse, sku, start)`.
6. **PDF is rebuilt on every rerun** and the dashboard code runs `get_report` twice. Wrap `build_pdf` in `st.cache_data` for speed.
7. **The `reportlab` import sits mid-file** in `dashboard.py`; move it to the top for clarity.
8. **`run.py` always computes the backtest** (the `or True` condition); `--backtest` only controls printing.

**Methodological limits:**

- Rupee figures are estimates, not accounting.
- Thresholds were tuned on 10 weeks of data and need re-tuning on real history.
- The control group assumes other cities are healthy. If a problem hits several cities at once, the loss is understated.
- A baseline built from a single week (for problems starting in week 2) is noisy.
- The tool cannot say why a PO was missing or why a rank fell; actions are questions to ask, not diagnoses.
- The backtest is hard-coded to the three known problems and the brief's approximate notice dates.
- No tests are included beyond the manual validation described in section 13.

## 13. Validation performed

- Duplicates traced to one date by comparing row counts per day.
- All store IDs, product IDs and warehouse-city pairs verified to join cleanly.
- Loss estimate sanity-checked with a plain pivot: Blinkit Bengaluru's six products fell from about 33% of the same products' sales in other cities to about 15% during the problem.
- Threshold tuning: `fill_thresh` raised from 0.75 to 0.70 after a random 74% PO pulled a seventh product into a six-product alert.
- Replay on all ten Mondays: between 0 and 3 active alerts each week; all three known problems flagged in week 1.
- Report rendered and visually inspected on desktop width; a table cut-off in the PDF was fixed.

## 14. Extending the project

**Add a new detector.** (1) Write `detect_x(D_, T)` returning one row per product-week using only data before `T`. (2) Convert rows to episodes with `runs()`. (3) Append alert dicts with the standard keys from section 7.10. (4) Add the type to `TEAM`, and add wording in `text.title`, `text.facts` and `text.action`. (5) Add its colour in `report.card` and `dashboard.render_alert`.

**Change sensitivity.** Edit `P` in `engine.py`. Raise `min_loss_inr` for fewer alerts, lower `rank_jump` to catch smaller slides.

**New data.** Replace the CSVs in `data/` keeping the same columns. Add any new city spelling to `CITY_MAP`. Update the Monday list in `dashboard.py` (`pd.date_range(...)`) and the `known` list in `run.py`.

**New platform.** Add rows to `products.csv` and `dark_stores.csv`, and extend the platform loop in `text.messages` so the new KAM gets a message.

## 15. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ValueError: Invalid format string` | `%-d` in a date format on Windows. Use `timestamp.day` |
| `ModuleNotFoundError: reportlab` or `streamlit` | install the missing package |
| `AssertionError: unmapped city name` | a new city spelling; add it to `CITY_MAP` |
| `AssertionError: unmapped product id` | a product ID missing from `products.csv` |
| Garbled characters (`₹`, arrows) in files on Windows | open files as UTF-8; `run.py` already writes UTF-8 |
| Streamlit port permission error | run with `--server.port 8501` |
| Date dropdown looks dark | custom CSS needed for Streamlit's select box; hard refresh after editing |
| Changing parameters has no effect in the dashboard | `get_report` is cached for 5 minutes; restart the app or clear the cache |

## 16. Glossary

| Term | Meaning |
| --- | --- |
| Dark store | small warehouse that packs and delivers app orders in minutes |
| Platform warehouse | large warehouse run by an app that buys from Joy and supplies dark stores |
| PO | purchase order, placed each Monday per warehouse and SKU |
| Fill rate | units delivered divided by units ordered |
| Availability | share of the day a product could be ordered at a store |
| Search rank | position of a product in category search (1 is best) |
| KAM | Key Account Manager at a platform |
| As-of date | the Monday a report is generated for; no later data is used |
| Run-rate | estimated weekly loss if nothing changes |
