"""Pull the team's hours sheet from Google Sheets as plain CSV.

Works with zero credentials as long as the sheet is shared as
"Anyone with the link can view" -- we just hit Google's built-in CSV
export endpoint. If the sheet is ever made private, this will start
failing (Google returns an HTML sign-in page instead of CSV) and a
service-account setup would be needed instead.
"""

import re

import pandas as pd
import requests

SHEET_COLUMNS = ["Location Name", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def sheet_id_from_url(url):
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Couldn't find a spreadsheet ID in: {url!r}")
    return m.group(1)


def export_csv_url(sheet_url_or_id):
    sheet_id = sheet_url_or_id if re.fullmatch(r"[a-zA-Z0-9_-]+", sheet_url_or_id) else sheet_id_from_url(sheet_url_or_id)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def normalize_name(name):
    """Loose join key: lowercase, collapse whitespace, drop punctuation."""
    s = str(name or "").strip().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_sheet_hours(sheet_url_or_id, timeout=25):
    """Returns a DataFrame with SHEET_COLUMNS. Raises if the sheet isn't publicly readable."""
    resp = requests.get(export_csv_url(sheet_url_or_id), timeout=timeout)
    resp.raise_for_status()
    if resp.text.lstrip().lower().startswith("<!doctype html") or "<html" in resp.text[:200].lower():
        raise RuntimeError(
            "Got an HTML page instead of CSV -- the sheet probably isn't shared as "
            "'Anyone with the link can view'. Check sharing settings and try again."
        )

    from io import StringIO

    df = pd.read_csv(StringIO(resp.text), dtype=str, keep_default_na=False)
    missing = [c for c in SHEET_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Sheet is missing expected column(s): {missing}. Found: {list(df.columns)}")
    return df[SHEET_COLUMNS]
