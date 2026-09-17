import pandas as pd

import hours_lib as hl
from compare_hours import run_comparison


def _gbp_row(store_code, name, website, **day_hours):
    row = {
        "Store code": store_code,
        "Business name": name,
        "Locality": "Anytown",
        "Administrative area": "TX",
        "Status": "Published",
        "Website": website,
        "Special hours": "",
    }
    for day in hl.GBP_DAY_ORDER:
        row[f"{day} hours"] = day_hours.get(day, "")
    return row


def _site_row(website_url, fetch_status="ok", **day_hours):
    row = {"website_url": website_url, "fetch_status": fetch_status}
    for day in hl.GBP_DAY_ORDER:
        row[f"{day} hours (site)"] = day_hours.get(day, "")
    return row


def test_three_location_fixture_verdicts_and_what_to_fix():
    gbp_df = pd.DataFrame(
        [
            _gbp_row(
                "S1",
                "Matching Location",
                "https://www.aqua-tots.com/matching/",
                Monday="09:00-17:00",
                Tuesday="09:00-17:00",
            ),
            _gbp_row(
                "S2",
                "Mismatch Location",
                "https://www.aqua-tots.com/mismatch/",
                Monday="09:00-17:00",
                Tuesday="09:00-17:00",
                Wednesday="09:00-17:00",
                Thursday="09:00-17:00",
                Friday="",  # GBP blank -> closed under default policy
                Saturday="09:00-17:00",
                Sunday="",
            ),
            _gbp_row(
                "S3",
                "Missing Site Row",
                "https://www.aqua-tots.com/missing/",
                Monday="09:00-17:00",
            ),
        ]
    )

    site_df = pd.DataFrame(
        [
            _site_row(
                "https://www.aqua-tots.com/matching/",
                Monday="09:00-17:00",
                Tuesday="09:00-17:00",
                Wednesday="",
                Thursday="",
                Friday="",
                Saturday="",
                Sunday="",
            ),
            _site_row(
                "https://www.aqua-tots.com/mismatch/",
                Monday="09:00-17:00",
                Tuesday="09:00-17:00",
                Wednesday="09:00-17:00",
                Thursday="09:00-17:00",
                Friday="09:00-19:30",  # site says open, GBP cell is blank (closed)
                Saturday="09:00-17:00",
                Sunday="10:00-14:00",
            ),
        ]
    )

    report = run_comparison(gbp_df, site_df, tolerance=0, blank_gbp_is_closed=True)
    by_store = {r["Store code"]: r for _, r in report.iterrows()}

    assert by_store["S1"]["Verdict"] == "MATCH"
    assert by_store["S2"]["Verdict"] == "MISMATCH"
    assert by_store["S2"]["What to fix"] == "Fri: GBP Closed vs site 09:00-19:30; Sun: GBP Closed vs site 10:00-14:00"
    assert by_store["S3"]["Verdict"] == "NOT_SCRAPED"

    assert list(report["Verdict"])[:1] == ["MISMATCH"]


def test_gbp_no_hours_verdict_for_all_blank_row():
    gbp_df = pd.DataFrame([_gbp_row("S1", "No Hours Location", "https://www.aqua-tots.com/nohours/")])
    site_df = pd.DataFrame([_site_row("https://www.aqua-tots.com/nohours/", Monday="09:00-17:00")])

    report = run_comparison(gbp_df, site_df, tolerance=0, blank_gbp_is_closed=True)
    assert report.iloc[0]["Verdict"] == "GBP_NO_HOURS"


def test_no_website_verdict():
    gbp_df = pd.DataFrame([_gbp_row("S1", "No Website Location", "", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://www.aqua-tots.com/somewhere/", Monday="09:00-17:00")])

    report = run_comparison(gbp_df, site_df, tolerance=0, blank_gbp_is_closed=True)
    assert report.iloc[0]["Verdict"] == "NO_WEBSITE"


def test_site_no_hours_verdict_when_no_hours_block_found():
    gbp_df = pd.DataFrame([_gbp_row("S1", "Broken Page", "https://www.aqua-tots.com/broken/", Monday="09:00-17:00")])
    site_df = pd.DataFrame([_site_row("https://www.aqua-tots.com/broken/", fetch_status="no hours block found")])

    report = run_comparison(gbp_df, site_df, tolerance=0, blank_gbp_is_closed=True)
    assert report.iloc[0]["Verdict"] == "SITE_NO_HOURS"


def test_tolerance_flag_forgives_small_differences():
    gbp_df = pd.DataFrame([_gbp_row("S1", "Close Enough", "https://www.aqua-tots.com/close/", Monday="09:00-19:00")])
    site_df = pd.DataFrame([_site_row("https://www.aqua-tots.com/close/", Monday="09:00-19:15")])

    strict = run_comparison(gbp_df, site_df, tolerance=0, blank_gbp_is_closed=True)
    assert strict.iloc[0]["Verdict"] == "MISMATCH"

    lenient = run_comparison(gbp_df, site_df, tolerance=15, blank_gbp_is_closed=True)
    assert lenient.iloc[0]["Verdict"] == "MATCH"


def test_overnight_website_hours_are_not_silently_lost():
    # Regression test: site_df's "{day} hours (site)" column holds the
    # scraper's own hl.fmt() output (e.g. "10:00-02:00"), and re-parsing it
    # without trust_source=True made the ambiguous-overnight safety check
    # discard it as unknown, turning a real match into a false SITE_NO_HOURS
    # for any location open past midnight.
    gbp_df = pd.DataFrame([_gbp_row("S1", "Open Late", "https://www.aqua-tots.com/open-late/", Monday="10:00am-2:00am")])
    site_df = pd.DataFrame([_site_row("https://www.aqua-tots.com/open-late/", Monday="10:00-02:00")])

    report = run_comparison(gbp_df, site_df, tolerance=0, blank_gbp_is_closed=True)
    assert report.iloc[0]["Verdict"] == "MATCH"
