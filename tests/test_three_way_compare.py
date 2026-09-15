import pandas as pd

import hours_lib as hl
from three_way_compare import run_three_way


def _gbp_row(store_code, name, website, **day_hours):
    row = {
        "Store code": store_code,
        "Business name": name,
        "Locality": "Anytown",
        "Administrative area": "TX",
        "Website": website,
    }
    for day in hl.GBP_DAY_ORDER:
        row[f"{day} hours"] = day_hours.get(day, "")
    return row


def _site_row(website_url, **day_hours):
    row = {"website_url": website_url, "fetch_status": "ok"}
    for day in hl.GBP_DAY_ORDER:
        row[f"{day} hours (site)"] = day_hours.get(day, "")
    return row


def _sheet_row(location_name, **day_hours):
    row = {"Location Name": location_name}
    for day in hl.GBP_DAY_ORDER:
        row[day] = day_hours.get(day, "")
    return row


def test_all_three_sources_agree_is_yes_on_both_columns():
    gbp_df = pd.DataFrame([_gbp_row("S1", "All Agree", "https://example.com/agree/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/agree/", Monday="09:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("All Agree", Monday="09:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df)
    assert report.iloc[0]["GBP Matches Master Sheet"] == "Yes"
    assert report.iloc[0]["Website Matches Master Sheet"] == "Yes"


def test_sheet_being_wrong_flags_both_columns():
    """The Master Sheet is treated as the source of truth, so both other
    columns are judged against it directly -- not against each other. If
    the sheet itself is wrong, GBP and the website both look wrong relative
    to it, even though they agree with each other. That's the intended
    trade-off of trusting the sheet, matching the hours dialog exactly."""
    gbp_df = pd.DataFrame([_gbp_row("S1", "Sheet Is Off", "https://example.com/sheet-off/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/sheet-off/", Monday="09:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("Sheet Is Off", Monday="10:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df)
    assert report.iloc[0]["GBP Matches Master Sheet"] == "No"
    assert report.iloc[0]["Website Matches Master Sheet"] == "No"


def test_gbp_disagreeing_with_sheet_only_flags_that_column():
    gbp_df = pd.DataFrame([_gbp_row("S1", "GBP Is Off", "https://example.com/gbp-off/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/gbp-off/", Monday="10:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("GBP Is Off", Monday="10:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df)
    assert report.iloc[0]["GBP Matches Master Sheet"] == "No"
    assert report.iloc[0]["Website Matches Master Sheet"] == "Yes"


def test_website_disagreeing_with_sheet_only_flags_that_column():
    gbp_df = pd.DataFrame([_gbp_row("S1", "Website Is Off", "https://example.com/site-off/", Monday="10:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/site-off/", Monday="09:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("Website Is Off", Monday="10:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df)
    assert report.iloc[0]["GBP Matches Master Sheet"] == "Yes"
    assert report.iloc[0]["Website Matches Master Sheet"] == "No"


def test_sheet_name_join_is_case_and_punctuation_insensitive():
    gbp_df = pd.DataFrame([_gbp_row("S1", "Aqua-Tots Swim School Mesa", "https://example.com/mesa/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/mesa/", Monday="09:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("aqua tots swim school mesa", Monday="09:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df)
    assert report.iloc[0]["Website Matches Master Sheet"] == "Yes"
    assert "(no match in sheet)" not in report.iloc[0]["Sheet Hours"]


def test_no_sheet_match_or_site_scrape_is_not_enough_data():
    gbp_df = pd.DataFrame([_gbp_row("S1", "Lonely Location", "https://example.com/lonely/", Monday="09:00-17:00")])
    site_df = pd.DataFrame(columns=["website_url", "fetch_status"] + [f"{d} hours (site)" for d in hl.GBP_DAY_ORDER])
    sheet_df = pd.DataFrame(columns=["Location Name"] + hl.GBP_DAY_ORDER)

    report = run_three_way(gbp_df, site_df, sheet_df)
    row = report.iloc[0]
    assert row["GBP Matches Master Sheet"] == "N/A (not enough data)"
    assert row["Website Matches Master Sheet"] == "N/A (not enough data)"
    assert row["Website Hours"] == "(not scraped)"
    assert row["Sheet Hours"] == "(no match in sheet)"


def test_tolerance_forgives_small_differences_independently_per_column():
    # GBP is 10 minutes off the sheet; the website matches the sheet exactly.
    gbp_df = pd.DataFrame([_gbp_row("S1", "Close Enough", "https://example.com/close/", Monday="09:00-19:10")])
    site_df = pd.DataFrame([_site_row("https://example.com/close/", Monday="09:00-19:00")])
    sheet_df = pd.DataFrame([_sheet_row("Close Enough", Monday="09:00-19:00")])

    strict = run_three_way(gbp_df, site_df, sheet_df, tolerance=0)
    assert strict.iloc[0]["GBP Matches Master Sheet"] == "No"
    assert strict.iloc[0]["Website Matches Master Sheet"] == "Yes"

    lenient = run_three_way(gbp_df, site_df, sheet_df, tolerance=15)
    assert lenient.iloc[0]["GBP Matches Master Sheet"] == "Yes"
    assert lenient.iloc[0]["Website Matches Master Sheet"] == "Yes"
