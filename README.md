# Joy Quick Commerce: Monday alerts

Turns last week's sales, stock and purchase-order data into a short list of **what to act on, who should do it, and what it costs in rupees**.

## Run the website

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (usually `http://localhost:8501`). Choose a reporting Monday in the sidebar. The report and WhatsApp messages update automatically.

Use **Download report** in the sidebar to download the selected week as a formatted PDF. The PDF includes active alerts, recovered alerts, WhatsApp messages, and data-quality checks.

## Command-line report

```bash
python run.py --data data --asof 2026-11-16 --out output --backtest
```

This creates `output/2026-11-16/report.html`, `whatsapp_messages.txt`, and `alerts.csv`. HTML and WhatsApp text are written in UTF-8, including rupee symbols.

`--asof` is the reporting Monday. The code only uses data from before that Monday, so older weeks can be replayed.

## Files

- `app.py` — Streamlit entry point used locally and on Streamlit Community Cloud
- `dashboard.py` — weekly-report interface and PDF generation
- `joy_alerts/clean.py` — loading and data-quality checks
- `joy_alerts/engine.py` — detectors, loss estimates, and backtesting
- `joy_alerts/text.py` — alert wording and WhatsApp messages
- `joy_alerts/report.py` — static command-line HTML report
- `run.py` — command-line report generator
