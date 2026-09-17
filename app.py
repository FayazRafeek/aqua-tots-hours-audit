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
from scraper_core import WEBSITE_HOURS_COLUMNS, _make_session, normalize_url, process_url
from scrapers import BRANDS
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

SOURCE_OPTIONS_WITH_SHEET = ["sheet", "gbp", "website"]  # "sheet" first: the recommended default
SOURCE_OPTIONS_NO_SHEET = ["website", "gbp"]  # "website" first: the fallback when there's no sheet to trust
BRAND_OPTIONS = list(BRANDS)  # dict order == scrapers/__init__.py's registration order

# Streamlit Cloud's "Manage app" panel just tails this app's stdout/stderr --
# there's no separate log viewer to configure. logging.basicConfig() is a
# no-op after the first call, so this stays safe across Streamlit's repeated
# reruns of the script instead of stacking up duplicate handlers.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger("hours_audit")


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


# Attention-needed first: a mismatch is the thing you actually came here to
# find, so it leads: whether it turned into a low number (great) or a high
# one (needs work) is the first thing to register when glancing at the page.
_VERDICT_PRIORITY = ["No", "N/A (not enough data)", "Yes"]


def _verdict_badges_html(column_name, counts):
    badges = []
    for label in _VERDICT_PRIORITY:
        count = int(counts.get(label, 0))
        style = _match_color(label).replace("background-color", "background")
        badges.append(
            f"<div style='{style} border-radius:10px; padding:10px 16px; flex:1; min-width:110px;'>"
            f"<div style='font-size:12px; opacity:0.85;'>{label}</div>"
            f"<div style='font-size:26px; font-weight:700; line-height:1.3;'>{count}</div>"
            "</div>"
        )
    return (
        f"<div style='font-weight:600; margin-bottom:6px;'>{column_name}</div>"
        f"<div style='display:flex; gap:10px; margin-bottom:18px;'>{''.join(badges)}</div>"
    )


@st.dialog("Hours comparison")
def show_hours_dialog(row, tolerance, source_of_truth, sources):
    st.subheader(row["Name"])

    by_day = {"gbp": row["_gbp_by_day"], "website": row["_site_by_day"]}
    if "sheet" in sources:
        by_day["sheet"] = row["_sheet_by_day"]
    order = dialog_source_order(source_of_truth, sources)  # source of truth first, then the other(s)
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


st.set_page_config(page_title="Hours Audit", layout="wide")

brand = st.selectbox(
    "Brand",
    BRAND_OPTIONS,
    format_func=lambda k: BRANDS[k]["label"],
    help="Only the website parsing differs per brand -- everything else (GBP, the sheet, the "
    "comparison logic) works the same regardless of which one you pick.",
)

# Swap in that brand's default Master Sheet URL the first time it's selected,
# without stomping on anything the user already typed. Streamlit widgets only
# honor their `value=` argument the very first time they're created, so
# switching brands later has to pre-seed session_state instead.
if st.session_state.get("_last_brand") != brand:
    st.session_state["_last_brand"] = brand
    st.session_state["sheet_url_input"] = BRANDS[brand]["default_sheet_url"]

st.title(f"{BRANDS[brand]['label']} Hours Audit")
st.caption("Checks GBP hours against the website and the team's hours sheet.")

# Ordered by priority: the one thing every run needs (the GBP file) comes
# right after picking a brand; the optional sheet comes second; anything
# with a sensible default (source of truth, tuning knobs) is tucked into
# Advanced settings instead of competing for attention up front.
gbp_file = st.file_uploader("GBP export CSV", type="csv")
sheet_url = st.text_input(
    "Master Sheet URL (optional)",
    key="sheet_url_input",
    help="Leave this blank to skip the sheet entirely and compare GBP against the website only. "
    "Once a URL is here, Master Sheet becomes available as a source of truth in Advanced settings.",
)
has_sheet = bool(sheet_url.strip())

truth_options = SOURCE_OPTIONS_WITH_SHEET if has_sheet else SOURCE_OPTIONS_NO_SHEET
# If the sheet just disappeared (cleared, or a brand switch reset it), "sheet"
# is no longer a valid option -- Streamlit errors if a selectbox's current
# value isn't in its options, so this has to be fixed before the widget runs.
if not has_sheet and st.session_state.get("source_of_truth_input") == "sheet":
    st.session_state["source_of_truth_input"] = "website"

with st.expander("Advanced settings"):
    source_of_truth = st.selectbox(
        "Source of truth",
        truth_options,
        key="source_of_truth_input",
        format_func=lambda k: SOURCE_LABELS[k],
        help="The other source(s) are each checked directly against whichever one you pick here -- "
        "not against each other. With a Master Sheet URL given, it's the recommended default since "
        "it's the one the team maintains by hand; without one, Website is used since GBP and the "
        "website are the only two sources available.",
    )
    tolerance = st.number_input("Tolerance (minutes per boundary)", min_value=0, max_value=60, value=0, step=5)
    blank_gbp_is_closed = st.checkbox("Blank GBP cell means Closed", value=True)
    workers = st.slider("Scrape workers", min_value=2, max_value=16, value=8)
    force_refresh = st.checkbox(
        "Force refresh (ignore cached pages)",
        value=False,
        help="Pages are cached on disk after the first fetch so repeat runs are fast. "
        "If a location's website changed recently, its cached copy can be stale -- check this to refetch every page live.",
    )

run_clicked = st.button("Run audit", type="primary", disabled=gbp_file is None, width="stretch")

if run_clicked:
    run_started = time.monotonic()
    gbp_df = pd.read_csv(gbp_file, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    parse_page_fn = BRANDS[brand]["parse_page"]
    logger.info(
        "=== Run audit: brand=%s %d GBP rows | source_of_truth=%s tolerance=%d blank_gbp_is_closed=%s "
        "workers=%d force_refresh=%s ===",
        brand,
        len(gbp_df),
        source_of_truth,
        tolerance,
        blank_gbp_is_closed,
        workers,
        force_refresh,
    )

    if has_sheet:
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
    else:
        logger.info("No Master Sheet URL given -- comparing GBP against the website only.")
        sheet_df = None

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
            futures = {
                pool.submit(process_url, url, cache_dir, not force_refresh, session, parse_page_fn): url
                for url in urls
            }
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

    sources = SOURCE_OPTIONS_WITH_SHEET if has_sheet else SOURCE_OPTIONS_NO_SHEET

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
        for _, column_name in checker_columns(source_of_truth, sources):
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
    # would vanish. This also freezes the source-of-truth choice (and which
    # sources even existed) the report was actually computed with, so
    # changing the inputs afterward without re-running can't desync them
    # from the columns already on screen.
    st.session_state.report = report
    st.session_state.report_tolerance = tolerance
    st.session_state.report_source_of_truth = source_of_truth
    st.session_state.report_sources = sources

if "report" in st.session_state:
    report = st.session_state.report
    report_tolerance = st.session_state.report_tolerance
    report_source_of_truth = st.session_state.report_source_of_truth
    report_sources = st.session_state.report_sources
    checks = checker_columns(report_source_of_truth, report_sources)  # [(other_key, column_name), ...]
    match_columns = [name for _, name in checks]

    st.divider()

    counts_by_column = {}
    for _, column_name in checks:
        counts = report[column_name].value_counts()
        counts_by_column[column_name] = counts
        st.markdown(_verdict_badges_html(column_name, counts), unsafe_allow_html=True)

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
    # errors="ignore" because Sheet Hours / _sheet_by_day don't exist at all
    # when this run had no sheet -- report_columns() already left them out.
    table_view = shown.drop(columns=HOURS_COLUMNS + HIDDEN_COLUMNS + IDENTITY_COLUMNS, errors="ignore")
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
            show_hours_dialog(shown.iloc[idx], report_tolerance, report_source_of_truth, report_sources)
    else:
        st.session_state.last_opened_row = None

    st.download_button(
        "Download CSV",
        data=shown.drop(columns=HIDDEN_COLUMNS, errors="ignore").to_csv(index=False).encode("utf-8-sig"),
        file_name="hours_audit_report.csv",
        mime="text/csv",
    )
