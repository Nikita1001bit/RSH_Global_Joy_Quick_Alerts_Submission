"""Streamlit Cloud entry point; re-run the dashboard script on every rerun."""
from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("dashboard.py")))
