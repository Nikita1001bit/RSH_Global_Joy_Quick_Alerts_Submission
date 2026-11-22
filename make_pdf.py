from playwright.sync_api import sync_playwright
import sys
f = sys.argv[1] if len(sys.argv) > 1 else "output/2026-11-16/report.html"
import os
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 980, "height": 900})
    pg.goto("file://" + os.path.abspath(f)); pg.pdf(path=f.replace(".html", ".pdf"), format="A4", print_background=True)
    pg.screenshot(path=f.replace(".html", "_full.png"), full_page=True); b.close()
