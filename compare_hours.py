"""Compare GBP export hours against scraped website hours.

    python compare_hours.py --gbp gbp_export.csv --site website_hours.csv

Writes hours_comparison.csv: one row per GBP export row, joined on
normalize_url(Website) == website_hours.csv's website_url.
"""

import argparse
import sys

import pandas as pd

import hours_lib as hl
from scraper_core import normalize_url

REPORT_COLUMNS = (
    ["Store code", "Business name", "Locality", "State", "Status", "Verdict", "Days differing", "What to fix"]
    + list(hl.REPORT_DAY_ORDER)
    + [f"GBP {day}" for day in hl.REPORT_DAY_ORDER]
    + [f"Site {day}" for day in hl.REPORT_DAY_ORDER]
    + ["Website", "Fetch status", "Special hours (GBP)"]
)

VERDICT_SORT_ORDER = {
    "MISMATCH": 0,
    "SITE_NO_HOURS": 1,
    "GBP_NO_HOURS": 2,
    "NOT_SCRAPED": 3,
    "NO_WEBSITE": 4,
    "MATCH": 5,
}


def _day_status(gbp_val, site_val, tolerance):
    if gbp_val is None and site_val is None:
        return "both blank"
    if gbp_val is None:
        return "GBP blank"
    if site_val is None:
        return "site blank"
    return "match" if hl.equal(gbp_val, site_val, tolerance=tolerance) else "DIFF"


def compare_row(gbp_row, site_row, tolerance, blank_gbp_is_closed):
    website = str(gbp_row.get("Website", "") or "").strip()
    normalized = normalize_url(website)

    if not normalized:
        return _build_report_row(gbp_row, "NO_WEBSITE", {}, {}, {}, "", "no website in export")

    if site_row is None:
        return _build_report_row(gbp_row, "NOT_SCRAPED", {}, {}, {}, website, "URL not found in website_hours.csv")

    gbp_hours = hl.gbp_row_hours(gbp_row, blank_means_closed=blank_gbp_is_closed)

    site_hours = {}
    for day in hl.GBP_DAY_ORDER:
        raw = site_row.get(f"{day} hours (site)", "")
        site_hours[day] = hl.parse_day_hours(raw) if str(raw).strip() else None

    fetch_status = str(site_row.get("fetch_status", "") or "")
    site_has_no_hours_block = "no hours block found" in fetch_status or fetch_status.startswith("fetch error")

    if all(v is None for v in gbp_hours.values()):
        return _build_report_row(gbp_row, "GBP_NO_HOURS", gbp_hours, site_hours, {}, website, "GBP has no hours published", fetch_status)

    if site_has_no_hours_block or all(v is None for v in site_hours.values()):
        return _build_report_row(gbp_row, "SITE_NO_HOURS", gbp_hours, site_hours, {}, website, "no hours block found on site", fetch_status)

    day_statuses = {day: _day_status(gbp_hours[day], site_hours[day], tolerance) for day in hl.GBP_DAY_ORDER}
    diff_days = [day for day, status in day_statuses.items() if status == "DIFF"]

    if diff_days:
        fixes = []
        for day in hl.REPORT_DAY_ORDER:
            if day in diff_days:
                fixes.append(f"{day[:3]}: GBP {hl.fmt(gbp_hours[day])} vs site {hl.fmt(site_hours[day])}")
        return _build_report_row(
            gbp_row, "MISMATCH", gbp_hours, site_hours, day_statuses, website, "; ".join(fixes), fetch_status
        )

    return _build_report_row(gbp_row, "MATCH", gbp_hours, site_hours, day_statuses, website, "", fetch_status)


def _build_report_row(gbp_row, verdict, gbp_hours, site_hours, day_statuses, website, what_to_fix, fetch_status=""):
    out = {
        "Store code": gbp_row.get("Store code", ""),
        "Business name": gbp_row.get("Business name", ""),
        "Locality": gbp_row.get("Locality", ""),
        "State": gbp_row.get("Administrative area", ""),
        "Status": gbp_row.get("Status", ""),
        "Verdict": verdict,
        "Days differing": len([d for d in day_statuses.values() if d == "DIFF"]),
        "What to fix": what_to_fix,
        "Website": website,
        "Fetch status": fetch_status,
        "Special hours (GBP)": gbp_row.get("Special hours", ""),
    }
    for day in hl.REPORT_DAY_ORDER:
        out[day] = day_statuses.get(day, "")
    for day in hl.REPORT_DAY_ORDER:
        out[f"GBP {day}"] = hl.fmt(gbp_hours.get(day)) if gbp_hours else ""
    for day in hl.REPORT_DAY_ORDER:
        out[f"Site {day}"] = hl.fmt(site_hours.get(day)) if site_hours else ""
    return out


def run_comparison(gbp_df, site_df, tolerance, blank_gbp_is_closed):
    site_by_url = {row["website_url"]: row for _, row in site_df.iterrows()}

    report_rows = []
    for _, gbp_row in gbp_df.iterrows():
        normalized = normalize_url(gbp_row.get("Website", ""))
        site_row = site_by_url.get(normalized) if normalized else None
        report_rows.append(compare_row(gbp_row, site_row, tolerance, blank_gbp_is_closed))

    report = pd.DataFrame(report_rows, columns=REPORT_COLUMNS)
    report["_sort"] = report["Verdict"].map(VERDICT_SORT_ORDER).fillna(99)
    report = report.sort_values(["_sort", "Business name"]).drop(columns="_sort").reset_index(drop=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gbp", required=True, help="Path to the GBP export CSV")
    parser.add_argument("--site", default="website_hours.csv", help="Path to scrape_website_hours.py's output")
    parser.add_argument("--out", default="hours_comparison.csv", help="Output CSV path")
    parser.add_argument("--tolerance", type=int, default=0, help="Minutes of slack per boundary")
    parser.add_argument("--only-mismatch", action="store_true", help="Filter output to non-MATCH rows")
    parser.add_argument(
        "--blank-gbp-is-closed",
        choices=["yes", "no"],
        default="yes",
        help="Whether a blank GBP hours cell means Closed (yes, default) or unknown (no)",
    )
    args = parser.parse_args()

    gbp_df = pd.read_csv(args.gbp, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    site_df = pd.read_csv(args.site, encoding="utf-8-sig", dtype=str, keep_default_na=False)

    report = run_comparison(gbp_df, site_df, args.tolerance, args.blank_gbp_is_closed == "yes")

    counts = report["Verdict"].value_counts()
    print("Verdict summary:")
    for verdict in VERDICT_SORT_ORDER:
        print(f"  {verdict:<15} {counts.get(verdict, 0)}")

    mismatches = report[report["Verdict"] == "MISMATCH"]
    if len(mismatches):
        print(f"\nFirst {min(5, len(mismatches))} mismatch(es):")
        for _, r in mismatches.head(5).iterrows():
            print(f"  {r['Business name']} ({r['Locality']}, {r['State']}): {r['What to fix']}")

    if args.only_mismatch:
        report = report[report["Verdict"] != "MATCH"]

    report.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"\nWrote {len(report)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
