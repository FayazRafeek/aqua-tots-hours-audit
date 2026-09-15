"""Streamlit UI for the hours audit -- upload the GBP export, get a table back.

    streamlit run app.py

Compares GBP vs the website vs the team's Google Sheet, three ways, and
lets you download the result as CSV. No login, no database -- each run
is stateless.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

import hours_lib as hl
from scrape_website_hours import WEBSITE_HOURS_COLUMNS, _make_session, normalize_url, process_url
from sheet_source import fetch_sheet_hours
from three_way_compare import HIDDEN_COLUMNS, run_three_way

DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/17q2frziO5xfG55z7E8UsEDT56APvH93FSBPpV4b4Y20/edit?usp=sharing"

MATCH_COLUMNS = ["GBP Matches Master Sheet", "Website Matches Master Sheet"]
HOURS_COLUMNS = ["GBP Hours", "Website Hours", "Sheet Hours"]
# Kept in the underlying data (and the CSV export) but not shown in the
# on-screen table -- Website moves into the hours dialog instead, and the
# rest just clutter the table without adding much once "Name" already
# identifies the location.
IDENTITY_COLUMNS_HIDDEN_FROM_TABLE = ["Store code", "Locality", "State", "Website"]


def _match_color(value):
    if value == "Yes":
        return "background-color: #1e5b34; color: #d9f7e2"
    if value == "No":
        return "background-color: #6e2020; color: #fbdcdc"
    if isinstance(value, str) and value.startswith("N/A"):
        return "background-color: #5c5424; color: #f5efc9"
    return ""


def _pair_status(a, b, tolerance):
    if a is None or b is None:
        return "insufficient"
    return "match" if hl.equal(a, b, tolerance=tolerance) else "DIFF"


def _cell_style(status):
    if status == "match":
        return "background:#1e5b34; color:#d9f7e2;"
    if status == "DIFF":
        return "background:#6e2020; color:#fbdcdc;"
    return "background:#33363d; color:#c9cdd6;"


@st.dialog("Hours comparison")
def show_hours_dialog(row, tolerance):
    st.subheader(row["Name"])

    gbp_by_day, site_by_day, sheet_by_day = row["_gbp_by_day"], row["_site_by_day"], row["_sheet_by_day"]

    header_cells = "".join(f"<th style='padding:6px 12px; text-align:left;'>{h}</th>" for h in ["Day", "Master Sheet", "Website", "GBP"])
    body_rows = []
    for day in hl.REPORT_DAY_ORDER:
        g, s, sh = gbp_by_day.get(day), site_by_day.get(day), sheet_by_day.get(day)
        # Master Sheet is the source of truth: both other columns are judged
        # against it directly, not against each other.
        site_style = _cell_style(_pair_status(sh, s, tolerance))
        gbp_style = _cell_style(_pair_status(sh, g, tolerance))
        body_rows.append(
            "<tr>"
            f"<td style='padding:6px 12px; font-weight:600;'>{day}</td>"
            f"<td style='padding:6px 12px;'>{hl.fmt(sh) or '—'}</td>"
            f"<td style='padding:6px 12px; {site_style}'>{hl.fmt(s) or '—'}</td>"
            f"<td style='padding:6px 12px; {gbp_style}'>{hl.fmt(g) or '—'}</td>"
            "</tr>"
        )

    st.markdown(
        f"<table style='width:100%; border-collapse:collapse;'>"
        f"<tr style='border-bottom:1px solid #555;'>{header_cells}</tr>"
        f"{''.join(body_rows)}</table>",
        unsafe_allow_html=True,
    )
    st.caption("Master Sheet is treated as the source of truth. Website and GBP are each colored by comparing against it directly. Gray means one side has no data for that day.")

    website = row.get("Website", "")
    if website:
        st.markdown(f"[{website}]({website})")
    else:
        st.caption("No website on file for this location.")

st.set_page_config(page_title="Aqua-Tots Hours Audit", layout="wide")
st.title("Aqua-Tots Hours Audit")
st.caption("Checks GBP hours against the website and the team's hours sheet.")

sheet_url = st.text_input("Master Sheet URL", value=DEFAULT_SHEET_URL)
gbp_file = st.file_uploader("GBP export CSV", type="csv")

with st.expander("Advanced settings"):
    tolerance = st.number_input("Tolerance (minutes per boundary)", min_value=0, max_value=60, value=0, step=5)
    blank_gbp_is_closed = st.checkbox("Blank GBP cell means Closed", value=True)
    workers = st.slider("Scrape workers", min_value=2, max_value=16, value=8)
    force_refresh = st.checkbox(
        "Force refresh (ignore cached pages)",
        value=False,
        help="Pages are cached on disk after the first fetch so repeat runs are fast. "
        "If a location's website changed recently, its cached copy can be stale -- check this to refetch every page live.",
    )

run_clicked = st.button("Run audit", type="primary", disabled=gbp_file is None)

if run_clicked:
    gbp_df = pd.read_csv(gbp_file, encoding="utf-8-sig", dtype=str, keep_default_na=False)

    with st.spinner("Fetching the master sheet..."):
        try:
            sheet_df = fetch_sheet_hours(sheet_url)
        except Exception as exc:
            st.error(f"Couldn't read the sheet: {exc}")
            st.stop()

    with st.spinner("Scraping location pages... this can take up to a minute"):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        urls = sorted({normalize_url(u) for u in gbp_df["Website"] if normalize_url(u)})
        session = _make_session()
        cache_dir = Path("./cache")
        rows = []
        progress = st.progress(0.0)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_url, url, cache_dir, not force_refresh, session): url for url in urls}
            done = 0
            for future in as_completed(futures):
                rows.append(future.result())
                done += 1
                progress.progress(done / len(urls))
        site_df = pd.DataFrame(rows, columns=WEBSITE_HOURS_COLUMNS)

    with st.spinner("Comparing..."):
        report = run_three_way(gbp_df, site_df, sheet_df, tolerance=tolerance, blank_gbp_is_closed=blank_gbp_is_closed)

    # Persist across reruns -- every widget interaction below (the filter
    # selectboxes, the download button) triggers a fresh rerun of this whole
    # script, and `run_clicked` is only True on the exact rerun where the
    # button itself was clicked. Without session_state, changing a filter
    # would make this `if run_clicked:` block skip entirely and the results
    # would vanish.
    st.session_state.report = report
    st.session_state.report_tolerance = tolerance

if "report" in st.session_state:
    report = st.session_state.report
    report_tolerance = st.session_state.report_tolerance

    gbp_vs_sheet_counts = report["GBP Matches Master Sheet"].value_counts()
    site_vs_sheet_counts = report["Website Matches Master Sheet"].value_counts()

    st.subheader("GBP vs Master Sheet")
    cols = st.columns(len(gbp_vs_sheet_counts))
    for col, (label, count) in zip(cols, gbp_vs_sheet_counts.items()):
        col.metric(label, count)

    st.subheader("Website vs Master Sheet")
    cols = st.columns(len(site_vs_sheet_counts))
    for col, (label, count) in zip(cols, site_vs_sheet_counts.items()):
        col.metric(label, count)

    filter_col1, filter_col2 = st.columns(2)
    gbp_vs_sheet_filter = filter_col1.selectbox("Filter: GBP Matches Master Sheet", ["All"] + list(gbp_vs_sheet_counts.index))
    site_vs_sheet_filter = filter_col2.selectbox(
        "Filter: Website Matches Master Sheet", ["All"] + list(site_vs_sheet_counts.index)
    )

    shown = report
    if gbp_vs_sheet_filter != "All":
        shown = shown[shown["GBP Matches Master Sheet"] == gbp_vs_sheet_filter]
    if site_vs_sheet_filter != "All":
        shown = shown[shown["Website Matches Master Sheet"] == site_vs_sheet_filter]

    st.caption("Hours aren't shown in the table -- three columns of comma-separated times were hard to scan. Click a row to view its hours.")
    table_view = shown.drop(columns=HOURS_COLUMNS + HIDDEN_COLUMNS + IDENTITY_COLUMNS_HIDDEN_FROM_TABLE)
    styled = table_view.style.map(_match_color, subset=MATCH_COLUMNS)

    # Keying on the filter selections forces Streamlit to treat this as a
    # fresh widget whenever the filters change, so a selection made in one
    # filtered view can't carry over and silently point at the wrong row in
    # another.
    table_key = f"results_table_{gbp_vs_sheet_filter}_{site_vs_sheet_filter}"
    event = st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=table_key,
    )

    selected_rows = event.selection.rows
    if selected_rows:
        idx = selected_rows[0]
        # A row click triggers a rerun where the selection is still set to
        # the same row -- without this guard, closing the dialog (which is
        # also just a rerun) would immediately reopen it, since the
        # underlying selection state never actually changed.
        if st.session_state.get("last_opened_row") != (table_key, idx):
            st.session_state.last_opened_row = (table_key, idx)
            show_hours_dialog(shown.iloc[idx], report_tolerance)
    else:
        st.session_state.last_opened_row = None

    st.download_button(
        "Download CSV",
        data=shown.drop(columns=HIDDEN_COLUMNS).to_csv(index=False).encode("utf-8-sig"),
        file_name="hours_audit_report.csv",
        mime="text/csv",
    )
