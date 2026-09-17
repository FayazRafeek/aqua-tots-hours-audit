import pandas as pd

import hours_lib as hl
from three_way_compare import checker_columns, report_columns, run_three_way


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


# ---------------------------------------------------------------------------
# Configurable source of truth -- any of GBP, the website, or the sheet can
# be picked as the thing the other two are checked against.
# ---------------------------------------------------------------------------

def test_checker_columns_names_per_source_of_truth():
    assert checker_columns("sheet") == [
        ("website", "Website Matches Master Sheet"),
        ("gbp", "GBP Matches Master Sheet"),
    ]
    assert checker_columns("gbp") == [
        ("website", "Website Matches GBP"),
        ("sheet", "Master Sheet Matches GBP"),
    ]
    assert checker_columns("website") == [
        ("gbp", "GBP Matches Website"),
        ("sheet", "Master Sheet Matches Website"),
    ]


def test_checker_columns_rejects_unknown_source():
    try:
        checker_columns("bogus")
        assert False, "expected a ValueError"
    except ValueError:
        pass


def test_report_columns_matches_run_three_way_output_columns():
    gbp_df = pd.DataFrame([_gbp_row("S1", "Loc", "https://example.com/loc/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/loc/", Monday="09:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("Loc", Monday="09:00-17:00")])

    for source in ["sheet", "gbp", "website"]:
        report = run_three_way(gbp_df, site_df, sheet_df, source_of_truth=source)
        assert list(report.columns[: len(report_columns(source))]) == report_columns(source)


def test_gbp_as_source_of_truth():
    # GBP is truth. The website disagrees with GBP; the sheet matches GBP.
    gbp_df = pd.DataFrame([_gbp_row("S1", "GBP Is Truth", "https://example.com/gbp-truth/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/gbp-truth/", Monday="10:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("GBP Is Truth", Monday="09:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df, source_of_truth="gbp")
    row = report.iloc[0]
    assert row["Website Matches GBP"] == "No"
    assert row["Master Sheet Matches GBP"] == "Yes"
    # The old sheet-as-truth columns shouldn't exist under this mode.
    assert "GBP Matches Master Sheet" not in report.columns


def test_website_as_source_of_truth():
    # Website is truth. GBP disagrees with the website; the sheet matches it.
    gbp_df = pd.DataFrame([_gbp_row("S1", "Website Is Truth", "https://example.com/site-truth/", Monday="10:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/site-truth/", Monday="09:00-17:00")])
    sheet_df = pd.DataFrame([_sheet_row("Website Is Truth", Monday="09:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df, source_of_truth="website")
    row = report.iloc[0]
    assert row["GBP Matches Website"] == "No"
    assert row["Master Sheet Matches Website"] == "Yes"


# ---------------------------------------------------------------------------
# Optional sheet: sheet_df=None means GBP vs website only.
# ---------------------------------------------------------------------------

def test_no_sheet_produces_single_checker_column():
    gbp_df = pd.DataFrame([_gbp_row("S1", "No Sheet Here", "https://example.com/no-sheet/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/no-sheet/", Monday="09:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df=None, source_of_truth="website")
    assert "GBP Matches Website" in report.columns
    assert "Master Sheet Matches Website" not in report.columns
    assert "Sheet Hours" not in report.columns
    assert report.iloc[0]["GBP Matches Website"] == "Yes"


def test_no_sheet_gbp_as_truth():
    gbp_df = pd.DataFrame([_gbp_row("S1", "GBP Truth No Sheet", "https://example.com/gbp-no-sheet/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/gbp-no-sheet/", Monday="10:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df=None, source_of_truth="gbp")
    assert "Website Matches GBP" in report.columns
    assert "Master Sheet Matches GBP" not in report.columns
    assert report.iloc[0]["Website Matches GBP"] == "No"


def test_no_sheet_rejects_sheet_as_source_of_truth():
    gbp_df = pd.DataFrame([_gbp_row("S1", "Bad Truth", "https://example.com/bad-truth/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/bad-truth/", Monday="09:00-17:00")])

    try:
        run_three_way(gbp_df, site_df, sheet_df=None, source_of_truth="sheet")
        assert False, "expected a ValueError"
    except ValueError:
        pass


def test_no_sheet_hidden_columns_omit_sheet_by_day():
    gbp_df = pd.DataFrame([_gbp_row("S1", "No Sheet Hidden", "https://example.com/no-sheet-hidden/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://example.com/no-sheet-hidden/", Monday="09:00-17:00")])

    report = run_three_way(gbp_df, site_df, sheet_df=None, source_of_truth="website")
    assert "_sheet_by_day" not in report.columns
    assert "_gbp_by_day" in report.columns
    assert "_site_by_day" in report.columns
