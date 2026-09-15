"""Compare GBP, website, and the team's hours sheet, three ways at once.

The website turned out not to be reliable, so the team's sheet is treated
as the source of truth (same as the hours dialog): both the website and
GBP are checked directly against the sheet, not against each other. That
way, if the sheet is right and the website is wrong, only "Website Matches
Master Sheet" flags it -- GBP isn't blamed just because it happens to
agree with the wrong side.
"""

import pandas as pd

import hours_lib as hl
from scrape_website_hours import normalize_url
from sheet_source import normalize_name

SIMPLE_COLUMNS = [
    "Name",
    "Website Matches Master Sheet",
    "GBP Matches Master Sheet",
    "Store code",
    "Locality",
    "State",
    "Website",
    "GBP Hours",
    "Website Hours",
    "Sheet Hours",
]

# Not for display or CSV export -- the raw {day: canonical} dicts, kept on the
# row so the app can render a proper day-by-day comparison (e.g. in a dialog)
# without re-parsing the combined "Mon 9:00-17:00, Tue ..." strings above.
HIDDEN_COLUMNS = ["_gbp_by_day", "_site_by_day", "_sheet_by_day"]


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


def run_three_way(gbp_df, site_df, sheet_df, tolerance=0, blank_gbp_is_closed=True):
    site_by_url = {row["website_url"]: row for _, row in site_df.iterrows()}
    sheet_by_name = {normalize_name(row["Location Name"]): row for _, row in sheet_df.iterrows()}

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

        sheet_row = sheet_by_name.get(normalize_name(gbp_row.get("Business name", "")))
        sheet_hours = sheet_row_hours(sheet_row) if sheet_row is not None else {day: None for day in hl.GBP_DAY_ORDER}

        rows.append(
            {
                "Name": gbp_row.get("Business name", ""),
                "Website Matches Master Sheet": pairwise_match_label(site_hours, sheet_hours, tolerance),
                "GBP Matches Master Sheet": pairwise_match_label(gbp_hours, sheet_hours, tolerance),
                "Store code": gbp_row.get("Store code", ""),
                "Locality": gbp_row.get("Locality", ""),
                "State": gbp_row.get("Administrative area", ""),
                "Website": website,
                "GBP Hours": _combine_days(gbp_hours),
                "Website Hours": _combine_days(site_hours) if site_row is not None else "(not scraped)",
                "Sheet Hours": _combine_days(sheet_hours) if sheet_row is not None else "(no match in sheet)",
                "_gbp_by_day": gbp_hours,
                "_site_by_day": site_hours,
                "_sheet_by_day": sheet_hours,
            }
        )

    return pd.DataFrame(rows, columns=SIMPLE_COLUMNS + HIDDEN_COLUMNS)
