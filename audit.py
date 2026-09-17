"""One-command hours audit: GBP export in, simple pass/fail report out.

    python audit.py --gbp gbp_export.csv

Runs the scrape and the comparison back to back and writes a condensed
report (one row per location: Business name, GBP Hours, Website Hours,
Do they Match) instead of the wide per-day report. For the full per-day
detail, run scrape_website_hours.py + compare_hours.py directly.
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

import hours_lib as hl
from compare_hours import run_comparison
from scraper_core import WEBSITE_HOURS_COLUMNS, _make_session, process_url, unique_urls_from_gbp
from scrapers import BRANDS

SIMPLE_COLUMNS = ["Store code", "Business name", "Locality", "State", "Website", "GBP Hours", "Website Hours", "Do they Match"]

MATCH_LABELS = {
    "MATCH": "Yes",
    "MISMATCH": "No",
    "GBP_NO_HOURS": "N/A (no GBP hours)",
    "SITE_NO_HOURS": "N/A (no site hours)",
    "NO_WEBSITE": "N/A (no website)",
    "NOT_SCRAPED": "N/A (fetch failed)",
}


def _combine_days(report_row, prefix):
    parts = [f"{day[:3]} {report_row[f'{prefix} {day}']}" for day in hl.REPORT_DAY_ORDER]
    return ", ".join(parts)


def to_simple_report(report):
    simple = pd.DataFrame()
    for col in ["Store code", "Business name", "Locality", "State", "Website"]:
        simple[col] = report[col]
    simple["GBP Hours"] = report.apply(lambda r: _combine_days(r, "GBP"), axis=1)
    simple["Website Hours"] = report.apply(lambda r: _combine_days(r, "Site"), axis=1)
    simple["Do they Match"] = report["Verdict"].map(MATCH_LABELS).fillna(report["Verdict"])
    return simple[SIMPLE_COLUMNS]


def scrape(gbp_path, cache_dir, workers, use_cache_read, parse_page_fn):
    urls = unique_urls_from_gbp(gbp_path)
    print(f"Fetching {len(urls)} unique location pages ({workers} workers)...")

    session = _make_session()
    rows = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_url, url, cache_dir, use_cache_read, session, parse_page_fn): url for url in urls
        }
        for future in as_completed(futures):
            rows.append(future.result())
    print(f"Done in {time.time() - start:.1f}s")

    return pd.DataFrame(rows, columns=WEBSITE_HOURS_COLUMNS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gbp", required=True, help="Path to the GBP export CSV")
    parser.add_argument("--brand", choices=list(BRANDS), default="aqua_tots", help="Which site's markup to parse")
    parser.add_argument("--out", default="simple_report.csv", help="Output CSV path")
    parser.add_argument("--cache", default="./cache", help="Disk cache directory for raw HTML")
    parser.add_argument("--no-cache-read", action="store_true", help="Force refetch, ignore cache")
    parser.add_argument("--workers", type=int, default=8, help="Parallel fetch workers")
    parser.add_argument("--tolerance", type=int, default=0, help="Minutes of slack per boundary")
    parser.add_argument(
        "--blank-gbp-is-closed",
        choices=["yes", "no"],
        default="yes",
        help="Whether a blank GBP hours cell means Closed (yes, default) or unknown (no)",
    )
    args = parser.parse_args()

    gbp_df = pd.read_csv(args.gbp, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    parse_page_fn = BRANDS[args.brand]["parse_page"]
    site_df = scrape(args.gbp, Path(args.cache), args.workers, not args.no_cache_read, parse_page_fn)

    full_report = run_comparison(gbp_df, site_df, args.tolerance, args.blank_gbp_is_closed == "yes")
    simple = to_simple_report(full_report)

    counts = simple["Do they Match"].value_counts()
    print("\nResults:")
    for label, count in counts.items():
        print(f"  {label:<22} {count}")

    simple.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"\nWrote {len(simple)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
