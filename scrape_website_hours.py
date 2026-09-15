"""Fetch each location's website page and extract its published hours.

    python scrape_website_hours.py --gbp gbp_export.csv

Reads normalized website URLs out of the GBP export, fetches each page
(cached to disk so a parser fix doesn't cost a re-fetch), and writes
website_hours.csv for compare_hours.py to join against.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

import hours_lib as hl

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 25
FALLBACK_WINDOW_CHARS = 700

WEBSITE_HOURS_COLUMNS = (
    ["website_url", "slug", "final_url", "fetch_status", "page_title", "page_phone"]
    + [f"{day} hours (site)" for day in hl.GBP_DAY_ORDER]
    + ["raw_hours_block"]
)


def normalize_url(raw):
    """Strip the query string, force a trailing slash, default the scheme to https.

    This is the join key both scripts use, so keep the two in lockstep.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if s == "" or s.lower() == "nan":
        return ""
    if not re.match(r"^https?://", s, re.IGNORECASE):
        s = "https://" + s
    parsed = urlsplit(s)
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def slug_of(normalized_url):
    path = urlsplit(normalized_url).path.strip("/")
    return path.split("/")[-1] if path else ""


def _make_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _cache_paths(cache_dir, url):
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{key}.html", cache_dir / f"{key}.json"


def fetch_page(session, url, cache_dir, use_cache_read):
    html_path, meta_path = _cache_paths(cache_dir, url)

    if use_cache_read and html_path.exists() and meta_path.exists():
        html = html_path.read_text(encoding="utf-8", errors="replace")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return html, meta["final_url"], meta["status_code"], None

    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        html = resp.text
        final_url = resp.url
        status_code = resp.status_code
    except requests.RequestException as exc:
        return None, url, None, str(exc)

    cache_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    meta_path.write_text(json.dumps({"final_url": final_url, "status_code": status_code}), encoding="utf-8")
    return html, final_url, status_code, None


def _weekday_count(text):
    return sum(1 for day in hl.GBP_DAY_ORDER if re.search(rf"\b{day}\b", text, re.IGNORECASE))


def extract_hours_block(soup):
    """Find the "Hours of Operation" heading, climb to the ancestor that
    actually contains the day-by-day list, and return its text. Falls back
    to a fixed character window after the heading if no such ancestor is found.
    """
    heading_string = soup.find(string=re.compile(r"hours of operation", re.IGNORECASE))
    if heading_string is None:
        return None

    node = heading_string.parent
    best_text = node.get_text(" ", strip=True)
    ancestor = node
    for _ in range(5):
        if ancestor.parent is None:
            break
        ancestor = ancestor.parent
        text = ancestor.get_text(" ", strip=True)
        if _weekday_count(text) >= 5:
            return text

    # No ancestor had enough weekday names -- fall back to a text window.
    full_text = soup.get_text(" ", strip=True)
    idx = full_text.lower().find("hours of operation")
    if idx == -1:
        return best_text
    return full_text[idx : idx + FALLBACK_WINDOW_CHARS]


def split_day_blocks(block_text):
    """Split the hours block on day labels, first occurrence of each day wins."""
    positions = []
    for day in hl.GBP_DAY_ORDER:
        m = re.search(rf"\b{day}\b", block_text, re.IGNORECASE)
        if m:
            positions.append((day, m.start(), m.end()))
    positions.sort(key=lambda p: p[1])

    blocks = {}
    for i, (day, _start, end) in enumerate(positions):
        next_start = positions[i + 1][1] if i + 1 < len(positions) else len(block_text)
        blocks[day] = block_text[end:next_start].strip()
    return blocks


def parse_page(html, requested_url):
    """Returns (hours_by_day, page_title, page_phone, raw_block, status_notes)."""
    notes = []
    hours_by_day = {day: None for day in hl.GBP_DAY_ORDER}
    raw_block = ""

    soup = BeautifulSoup(html, "lxml")

    h1 = soup.find("h1")
    page_title = h1.get_text(" ", strip=True) if h1 else ""

    tel_link = soup.find("a", href=re.compile(r"^tel:"))
    page_phone = tel_link["href"][len("tel:"):] if tel_link else ""

    block_text = extract_hours_block(soup)
    if block_text is None:
        notes.append("no hours block found")
    else:
        raw_block = re.sub(r"\s+", " ", block_text).strip()[:400]
        day_blocks = split_day_blocks(block_text)
        for day in hl.GBP_DAY_ORDER:
            if day in day_blocks:
                hours_by_day[day] = hl.parse_day_hours(day_blocks[day])

    return hours_by_day, page_title, page_phone, raw_block, notes


def process_url(url, cache_dir, use_cache_read, session):
    html, final_url, status_code, error = fetch_page(session, url, cache_dir, use_cache_read)

    row = {
        "website_url": url,
        "slug": slug_of(url),
        "final_url": final_url or "",
        "page_title": "",
        "page_phone": "",
        "raw_hours_block": "",
    }
    for day in hl.GBP_DAY_ORDER:
        row[f"{day} hours (site)"] = ""

    status_notes = []
    if error is not None:
        status_notes.append(f"fetch error: {error}")
        row["fetch_status"] = "; ".join(status_notes)
        return row

    if status_code is not None and status_code >= 400:
        status_notes.append(f"http {status_code}")

    final_normalized = normalize_url(final_url)
    final_slug = slug_of(final_normalized)
    requested_slug = slug_of(url)
    if final_slug and requested_slug and final_slug != requested_slug:
        status_notes.append(f"redirected to /{final_slug}/")

    hours_by_day, page_title, page_phone, raw_block, parse_notes = parse_page(html, url)
    status_notes.extend(parse_notes)

    row["page_title"] = page_title
    row["page_phone"] = page_phone
    row["raw_hours_block"] = raw_block
    for day in hl.GBP_DAY_ORDER:
        row[f"{day} hours (site)"] = hl.fmt(hours_by_day[day])
    row["fetch_status"] = "; ".join(status_notes) if status_notes else "ok"
    return row


def unique_urls_from_gbp(gbp_path):
    df = pd.read_csv(gbp_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    normalized = sorted({normalize_url(u) for u in df["Website"] if normalize_url(u)})
    return normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gbp", required=True, help="Path to the GBP export CSV")
    parser.add_argument("--out", default="website_hours.csv", help="Output CSV path")
    parser.add_argument("--cache", default="./cache", help="Disk cache directory for raw HTML")
    parser.add_argument("--no-cache-read", action="store_true", help="Force refetch, ignore cache")
    parser.add_argument("--workers", type=int, default=8, help="Parallel fetch workers")
    parser.add_argument("--limit", type=int, default=None, help="Only fetch the first N pages (smoke test)")
    args = parser.parse_args()

    cache_dir = Path(args.cache)
    urls = unique_urls_from_gbp(args.gbp)
    if args.limit:
        urls = urls[: args.limit]

    print(f"Fetching {len(urls)} unique location pages ({args.workers} workers)...")

    session = _make_session()
    rows = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_url, url, cache_dir, not args.no_cache_read, session): url for url in urls
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
