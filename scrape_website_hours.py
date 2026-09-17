"""Fetch each location's website page and extract its published hours.

    python scrape_website_hours.py --gbp gbp_export.csv --brand aqua_tots

Reads normalized website URLs out of the GBP export, fetches each page
(cached to disk so a parser fix doesn't cost a re-fetch), and writes
website_hours.csv for compare_hours.py to join against.

The actual HTML parsing is brand-specific and lives in scrapers/<brand>.py;
everything else here (fetching, caching, retries, the CSV shape) is shared
-- see scraper_core.py.
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

# Re-exported for backward compatibility -- audit.py, app.py, compare_hours.py,
# and three_way_compare.py all import the generic pieces from this module.
from scraper_core import (  # noqa: F401
    USER_AGENT,
    WEBSITE_HOURS_COLUMNS,
    _make_session,
    fetch_page,
    normalize_url,
    process_url,
    slug_of,
    unique_urls_from_gbp,
)
from scrapers import BRANDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gbp", required=True, help="Path to the GBP export CSV")
    parser.add_argument("--brand", choices=list(BRANDS), default="aqua_tots", help="Which site's markup to parse")
    parser.add_argument("--out", default="website_hours.csv", help="Output CSV path")
    parser.add_argument("--cache", default="./cache", help="Disk cache directory for raw HTML")
    parser.add_argument("--no-cache-read", action="store_true", help="Force refetch, ignore cache")
    parser.add_argument("--workers", type=int, default=8, help="Parallel fetch workers")
    parser.add_argument("--limit", type=int, default=None, help="Only fetch the first N pages (smoke test)")
    args = parser.parse_args()

    parse_page_fn = BRANDS[args.brand]["parse_page"]
    cache_dir = Path(args.cache)
    urls = unique_urls_from_gbp(args.gbp)
    if args.limit:
        urls = urls[: args.limit]

    print(f"Fetching {len(urls)} unique {BRANDS[args.brand]['label']} location pages ({args.workers} workers)...")

    session = _make_session()
    rows = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_url, url, cache_dir, not args.no_cache_read, session, parse_page_fn): url
            for url in urls
        }
        for future in as_completed(futures):
            rows.append(future.result())
    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s")

    rows.sort(key=lambda r: r["website_url"])
    out_df = pd.DataFrame(rows, columns=WEBSITE_HOURS_COLUMNS)
    out_df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(out_df)} rows to {args.out}")

    review = out_df[out_df["fetch_status"].str.contains("no hours block found|redirected to|fetch error|http ", regex=True, na=False)]
    if len(review):
        print(f"\n{len(review)} row(s) need a manual look:")
        for _, r in review.iterrows():
            print(f"  {r['website_url']}  ->  {r['fetch_status']}")
    else:
        print("\nNo rows flagged for review.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
