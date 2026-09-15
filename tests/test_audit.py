import pandas as pd

import hours_lib as hl
from audit import to_simple_report
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


def test_simple_report_condenses_days_and_maps_verdict_to_yes_no():
    gbp_df = pd.DataFrame(
        [
            _gbp_row("S1", "Matching Location", "https://www.aqua-tots.com/matching/", Monday="09:00-17:00"),
            _gbp_row("S2", "Mismatch Location", "https://www.aqua-tots.com/mismatch/", Monday="09:00-17:00"),
            _gbp_row("S3", "No Website Location", ""),
        ]
    )
    site_df = pd.DataFrame(
        [
            _site_row("https://www.aqua-tots.com/matching/", Monday="09:00-17:00"),
            _site_row("https://www.aqua-tots.com/mismatch/", Monday="10:00-17:00"),
        ]
    )

    full_report = run_comparison(gbp_df, site_df, tolerance=0, blank_gbp_is_closed=True)
    simple = to_simple_report(full_report)

    assert list(simple.columns) == [
        "Store code",
        "Business name",
        "Locality",
        "State",
        "Website",
        "GBP Hours",
        "Website Hours",
        "Do they Match",
    ]

    by_store = {r["Store code"]: r for _, r in simple.iterrows()}
    assert by_store["S1"]["Do they Match"] == "Yes"
    assert by_store["S2"]["Do they Match"] == "No"
    assert by_store["S3"]["Do they Match"] == "N/A (no website)"

    assert by_store["S1"]["GBP Hours"].startswith("Mon 09:00-17:00")
    assert "Mon 10:00-17:00" in by_store["S2"]["Website Hours"]
