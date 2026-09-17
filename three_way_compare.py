"""Compare GBP, website, and (optionally) the team's hours sheet.

The website turned out not to be reliable, so rather than always trusting
one particular source, whichever one is picked as the "source of truth"
(GBP, the website, or the sheet -- see SOURCE_LABELS) gets checked against
by the other(s) directly, not against each other. That way, if the trusted
source is right and one of the others is wrong, only that one gets flagged
-- a third source isn't blamed just because it happens to agree with the
wrong side.

The sheet is optional: pass sheet_df=None to compare GBP against the website
only (source_of_truth must then be "gbp" or "website"). Every function here
takes the same `sources` list -- which sources actually exist this run --
so the columns, the dialog, and the CSV all agree on what's available.
"""

import pandas as pd

import hours_lib as hl
from scraper_core import normalize_url
from sheet_source import normalize_name

SOURCE_LABELS = {"gbp": "GBP", "website": "Website", "sheet": "Master Sheet"}

# Fixed relative order sources are shown in, regardless of which one is
# picked as truth or which are actually available (this is what made
# "Website Matches Master Sheet" come before "GBP Matches Master Sheet"
# originally, back when the sheet was the only option -- kept for a stable,
# predictable column order).
ALL_SOURCES = ["website", "gbp", "sheet"]

BY_DAY_KEYS = {"gbp": "_gbp_by_day", "website": "_site_by_day", "sheet": "_sheet_by_day"}

IDENTITY_COLUMNS = ["Store code", "Locality", "State", "Website"]
HOURS_COLUMNS = ["GBP Hours", "Website Hours", "Sheet Hours"]

# Not for display or CSV export -- the raw {day: canonical} dicts, kept on the
# row so the app can render a proper day-by-day comparison (e.g. in a dialog)
# without re-parsing the combined "Mon 9:00-17:00, Tue ..." strings above.
HIDDEN_COLUMNS = ["_gbp_by_day", "_site_by_day", "_sheet_by_day"]


def checker_columns(source_of_truth, sources=ALL_SOURCES):
    """The "<other> Matches <truth>" column names for this source of truth,
    in a stable order. Returns [(other_key, column_name), ...] -- one entry
    per source in `sources` other than the truth itself."""
    if source_of_truth not in sources:
        raise ValueError(f"source_of_truth must be one of {sources}, got {source_of_truth!r}")
    truth_label = SOURCE_LABELS[source_of_truth]
    others = [k for k in ALL_SOURCES if k in sources and k != source_of_truth]
    return [(k, f"{SOURCE_LABELS[k]} Matches {truth_label}") for k in others]


def dialog_source_order(source_of_truth, sources=ALL_SOURCES):
    """Source keys in the order the hours dialog should display them: the
    source of truth first, then the other(s) in checker_columns' order."""
    return [source_of_truth] + [k for k, _ in checker_columns(source_of_truth, sources)]


def report_columns(source_of_truth, sources=ALL_SOURCES):
    """Full display+CSV column order for a given source of truth (excludes
    the hidden per-day dict columns). Sheet Hours is only included when the
    sheet is actually one of `sources`."""
    checker_names = [name for _, name in checker_columns(source_of_truth, sources)]
    hours_columns = ["GBP Hours", "Website Hours"] + (["Sheet Hours"] if "sheet" in sources else [])
    return ["Name"] + checker_names + IDENTITY_COLUMNS + hours_columns


def sheet_row_hours(sheet_row):
    """One sheet row -> {day: canonical}. Blank means unknown here, not closed --
    unlike the GBP export, we don't have ground truth on this sheet's blank-cell
    convention, so we don't guess."""
    return {day: hl.parse_day_hours(sheet_row.get(day, "")) for day in hl.GBP_DAY_ORDER}


def _combine_days(hours_by_day):
    return ", ".join(f"{day[:3]} {hl.fmt(hours_by_day.get(day))}" for day in hl.REPORT_DAY_ORDER)


def pairwise_match_label(hours_a_by_day, hours_b_by_day, tolerance):
    """Yes / No / N/A (not enough data) for one pair of sources across all seven days.
    A day only counts if both sides actually have data for it."""
    statuses = []
    for day in hl.GBP_DAY_ORDER:
        a, b = hours_a_by_day.get(day), hours_b_by_day.get(day)
        if a is None or b is None:
            statuses.append("insufficient data")
        elif hl.equal(a, b, tolerance=tolerance):
            statuses.append("match")
        else:
            statuses.append("DIFF")

    if any(s == "DIFF" for s in statuses):
        return "No"
    if all(s == "insufficient data" for s in statuses):
        return "N/A (not enough data)"
    return "Yes"


def run_three_way(gbp_df, site_df, sheet_df, tolerance=0, blank_gbp_is_closed=True, source_of_truth="sheet"):
    """sheet_df=None means no sheet was provided -- GBP is compared against
    the website only, and source_of_truth must be "gbp" or "website"."""
    has_sheet = sheet_df is not None
    sources = ALL_SOURCES if has_sheet else [s for s in ALL_SOURCES if s != "sheet"]
    checks = checker_columns(source_of_truth, sources)

    site_by_url = {row["website_url"]: row for _, row in site_df.iterrows()}
    sheet_by_name = {normalize_name(row["Location Name"]): row for _, row in sheet_df.iterrows()} if has_sheet else {}

    rows = []
    for _, gbp_row in gbp_df.iterrows():
        gbp_hours = hl.gbp_row_hours(gbp_row, blank_means_closed=blank_gbp_is_closed)

        website = str(gbp_row.get("Website", "") or "").strip()
        normalized_url = normalize_url(website)
        site_row = site_by_url.get(normalized_url) if normalized_url else None
        if site_row is not None:
            site_hours = {
                day: hl.parse_day_hours(site_row.get(f"{day} hours (site)", "")) for day in hl.GBP_DAY_ORDER
            }
        else:
            site_hours = {day: None for day in hl.GBP_DAY_ORDER}

        by_source = {"gbp": gbp_hours, "website": site_hours}
        if has_sheet:
            sheet_row = sheet_by_name.get(normalize_name(gbp_row.get("Business name", "")))
            sheet_hours = sheet_row_hours(sheet_row) if sheet_row is not None else {day: None for day in hl.GBP_DAY_ORDER}
            by_source["sheet"] = sheet_hours

        truth_hours = by_source[source_of_truth]

        row = {"Name": gbp_row.get("Business name", "")}
        for other_key, column_name in checks:
            row[column_name] = pairwise_match_label(by_source[other_key], truth_hours, tolerance)
        row.update(
            {
                "Store code": gbp_row.get("Store code", ""),
                "Locality": gbp_row.get("Locality", ""),
                "State": gbp_row.get("Administrative area", ""),
                "Website": website,
                "GBP Hours": _combine_days(gbp_hours),
                "Website Hours": _combine_days(site_hours) if site_row is not None else "(not scraped)",
                "_gbp_by_day": gbp_hours,
                "_site_by_day": site_hours,
            }
        )
        if has_sheet:
            row["Sheet Hours"] = _combine_days(sheet_hours) if sheet_row is not None else "(no match in sheet)"
            row["_sheet_by_day"] = sheet_hours
        rows.append(row)

    hidden = HIDDEN_COLUMNS if has_sheet else [c for c in HIDDEN_COLUMNS if c != "_sheet_by_day"]
    return pd.DataFrame(rows, columns=report_columns(source_of_truth, sources) + hidden)
