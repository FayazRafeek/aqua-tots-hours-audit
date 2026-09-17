"""Brand-agnostic scraping plumbing: fetch, cache, retry, and the join key.

Nothing in this module knows how to read any particular website's hours --
that's the one thing that differs per brand, and lives in scrapers/<brand>.py
instead. Each brand module exposes a single function:

    parse_page(html, requested_url) -> (hours_by_day, page_title, page_phone, raw_block, notes)

and everything here (fetching, disk caching, retries, redirect detection,
the GBP-export-to-URL-list step, the output CSV shape) is shared as-is.
"""

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

import hours_lib as hl

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 25

WEBSITE_HOURS_COLUMNS = (
    ["website_url", "slug", "final_url", "fetch_status", "page_title", "page_phone"]
    + [f"{day} hours (site)" for day in hl.GBP_DAY_ORDER]
    + ["raw_hours_block"]
)


def normalize_url(raw):
    """Strip the query string, force a trailing slash, default the scheme to https.

    This is the join key everything uses, so keep it in lockstep across brands.
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
    # A bare User-Agent got a 403 from one brand's WAF on one path even
    # though plain requests otherwise worked fine everywhere else -- a
    # fuller, more browser-like header set fixed it without needing
    # anything brand-specific.
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
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


def process_url(url, cache_dir, use_cache_read, session, parse_page_fn):
    """Fetch one page and hand its HTML to the brand's parse_page_fn.

    parse_page_fn(html, requested_url) must return
    (hours_by_day, page_title, page_phone, raw_block, notes) -- the same
    contract every scrapers/<brand>.py module implements.
    """
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

    hours_by_day, page_title, page_phone, raw_block, parse_notes = parse_page_fn(html, url)
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
