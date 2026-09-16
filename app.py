"""Streamlit UI for the hours audit -- upload the GBP export, get a table back.

    streamlit run app.py

Compares GBP vs the website vs the team's Google Sheet, three ways, and
lets you download the result as CSV. No login, no database -- each run
is stateless.
"""

import logging
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import hours_lib as hl
from scrape_website_hours import WEBSITE_HOURS_COLUMNS, _make_session, normalize_url, process_url
from sheet_source import fetch_sheet_hours
from three_way_compare import (
    HIDDEN_COLUMNS,
    HOURS_COLUMNS,
    IDENTITY_COLUMNS,
    SOURCE_LABELS,
    checker_columns,
    dialog_source_order,
    run_three_way,
)

DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/17q2frziO5xfG55z7E8UsEDT56APvH93FSBPpV4b4Y20/edit?usp=sharing"
SOURCE_OPTIONS = ["sheet", "gbp", "website"]  # "sheet" first: the recommended default

# Streamlit Cloud's "Manage app" panel just tails this app's stdout/stderr --
# there's no separate log viewer to configure. logging.basicConfig() is a
# no-op after the first call, so this stays safe across Streamlit's repeated
# reruns of the script instead of stacking up duplicate handlers.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger("aqua_tots_audit")


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
def show_hours_dialog(row, tolerance, source_of_truth):
    st.subheader(row["Name"])

    by_day = {"gbp": row["_gbp_by_day"], "website": row["_site_by_day"], "sheet": row["_sheet_by_day"]}
    order = dialog_source_order(source_of_truth)  # source of truth first, then the other two
    truth_key = order[0]
    truth_by_day = by_day[truth_key]

    header_cells = "".join(
        f"<th style='padding:6px 12px; text-align:left;'>{h}</th>" for h in ["Day"] + [SOURCE_LABELS[k] for k in order]
    )
    body_rows = []
    for day in hl.REPORT_DAY_ORDER:
        truth_val = truth_by_day.get(day)
        cells = [
            f"<td style='padding:6px 12px; font-weight:600;'>{day}</td>",
            f"<td style='padding:6px 12px;'>{hl.fmt(truth_val) or '—'}</td>",
        ]
        for key in order[1:]:
            val = by_day[key].get(day)
            style = _cell_style(_pair_status(truth_val, val, tolerance))
            cells.append(f"<td style='padding:6px 12px; {style}'>{hl.fmt(val) or '—'}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    st.markdown(
        f"<table style='width:100%; border-collapse:collapse;'>"
        f"<tr style='border-bottom:1px solid #555;'>{header_cells}</tr>"
        f"{''.join(body_rows)}</table>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{SOURCE_LABELS[truth_key]} is treated as the source of truth. The other columns are each "
        "colored by comparing against it directly. Gray means one side has no data for that day."
    )

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
source_of_truth = st.selectbox(
    "Source of truth",
    SOURCE_OPTIONS,
    format_func=lambda k: SOURCE_LABELS[k],
    help="The other two sources are each checked directly against whichever one you pick here -- "
    "not against each other. The Master Sheet is the recommended default since it's the one "
    "the team maintains by hand; the website turned out not to be reliable enough to trust on its own.",
)

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
    run_started = time.monotonic()
    gbp_df = pd.read_csv(gbp_file, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    logger.info(
        "=== Run audit: %d GBP rows | source_of_truth=%s tolerance=%d blank_gbp_is_closed=%s "
        "workers=%d force_refresh=%s ===",
        len(gbp_df),
        source_of_truth,
        tolerance,
        blank_gbp_is_closed,
        workers,
        force_refresh,
    )

    with st.spinner("Fetching the master sheet..."):
        logger.info("Fetching master sheet: %s", sheet_url)
        sheet_started = time.monotonic()
        try:
            sheet_df = fetch_sheet_hours(sheet_url)
        except Exception as exc:
            logger.error("Failed to fetch master sheet: %s", exc)
            st.error(f"Couldn't read the sheet: {exc}")
            st.stop()
        logger.info("Master sheet fetched in %.1fs: %d rows", time.monotonic() - sheet_started, len(sheet_df))

    with st.spinner("Scraping location pages... this can take up to a minute"):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        urls = sorted({normalize_url(u) for u in gbp_df["Website"] if normalize_url(u)})
        logger.info("Scraping %d unique location pages with %d workers...", len(urls), workers)
        scrape_started = time.monotonic()
        session = _make_session()
        cache_dir = Path("./cache")
        rows = []
        progress = st.progress(0.0)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_url, url, cache_dir, not force_refresh, session): url for url in urls}
            done = 0
            for future in as_completed(futures):
                result = future.result()
                rows.append(result)
                done += 1
                logger.info("[%d/%d] %s -> %s", done, len(urls), result["website_url"], result["fetch_status"])
                progress.progress(done / len(urls))
        site_df = pd.DataFrame(rows, columns=WEBSITE_HOURS_COLUMNS)

        flagged = site_df[site_df["fetch_status"] != "ok"]
        logger.info(
            "Scrape complete in %.1fs: %d pages, %d flagged for review",
            time.monotonic() - scrape_started,
            len(site_df),
            len(flagged),
        )
        for _, flagged_row in flagged.iterrows():
            logger.warning("Flagged: %s -> %s", flagged_row["website_url"], flagged_row["fetch_status"])

    with st.spinner("Comparing..."):
        logger.info("Comparing %d locations...", len(gbp_df))
        compare_started = time.monotonic()
        report = run_three_way(
            gbp_df,
            site_df,
            sheet_df,
            tolerance=tolerance,
            blank_gbp_is_closed=blank_gbp_is_closed,
            source_of_truth=source_of_truth,
        )
        for _, column_name in checker_columns(source_of_truth):
            counts = report[column_name].value_counts().to_dict()
            logger.info("%s: %s", column_name, counts)
        logger.info(
            "Comparison complete in %.1fs. Total run time: %.1fs",
            time.monotonic() - compare_started,
            time.monotonic() - run_started,
        )

    # Persist across reruns -- every widget interaction below (the filter
    # selectboxes, the download button) triggers a fresh rerun of this whole
    # script, and `run_clicked` is only True on the exact rerun where the
    # button itself was clicked. Without session_state, changing a filter
    # would make this `if run_clicked:` block skip entirely and the results
    # would vanish. This also freezes the source-of-truth choice the report
    # was actually computed with, so changing the selectbox afterward (without
    # re-running) can't desync it from the columns already on screen.
    st.session_state.report = report
    st.session_state.report_tolerance = tolerance
    st.session_state.report_source_of_truth = source_of_truth

if "report" in st.session_state:
    report = st.session_state.report
    report_tolerance = st.session_state.report_tolerance
    report_source_of_truth = st.session_state.report_source_of_truth
    checks = checker_columns(report_source_of_truth)  # [(other_key, column_name), ...]
    match_columns = [name for _, name in checks]

    counts_by_column = {}
    for _, column_name in checks:
        counts = report[column_name].value_counts()
        counts_by_column[column_name] = counts
        st.subheader(column_name)
        cols = st.columns(len(counts))
        for col, (label, count) in zip(cols, counts.items()):
            col.metric(label, count)

    filter_cols = st.columns(len(checks))
    filters = {}
    for filter_col, (_, column_name) in zip(filter_cols, checks):
        filters[column_name] = filter_col.selectbox(
            f"Filter: {column_name}", ["All"] + list(counts_by_column[column_name].index)
        )

    shown = report
    for column_name, value in filters.items():
        if value != "All":
            shown = shown[shown[column_name] == value]

    st.caption("Hours aren't shown in the table -- three columns of comma-separated times were hard to scan. Click a row to view its hours.")
    table_view = shown.drop(columns=HOURS_COLUMNS + HIDDEN_COLUMNS + IDENTITY_COLUMNS)
    styled = table_view.style.map(_match_color, subset=match_columns)

    # Keying on the filter selections (and the source of truth, since that
    # changes which columns even exist) forces Streamlit to treat this as a
    # fresh widget whenever any of them change, so a selection made in one
    # view can't carry over and silently point at the wrong row in another.
    table_key = f"results_table_{report_source_of_truth}_{'_'.join(filters.values())}"
    event = st.dataframe(
        styled,
        width="stretch",
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
            show_hours_dialog(shown.iloc[idx], report_tolerance, report_source_of_truth)
    else:
        st.session_state.last_opened_row = None

    st.download_button(
        "Download CSV",
        data=shown.drop(columns=HIDDEN_COLUMNS).to_csv(index=False).encode("utf-8-sig"),
        file_name="hours_audit_report.csv",
        mime="text/csv",
    )
