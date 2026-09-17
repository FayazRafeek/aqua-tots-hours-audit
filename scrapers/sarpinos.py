"""Sarpino's Pizzeria-specific hours extraction.

Page shape: a `<script type="application/ld+json">` tag holding a
schema.org FoodEstablishment object. Hours live in its "openingHours" array
as strings like "Mo 10:00 am-2:00 am" -- one entry per day the location is
open. A closed day simply doesn't appear in the array at all (the
schema.org convention for openingHours), rather than being listed with
"Closed" text -- no real closed-day example was found while building this,
so that reading is inferred from the spec, not empirically confirmed.
"""

import json
import re

from bs4 import BeautifulSoup

import hours_lib as hl

_DAY_CODES = {
    "Mo": "Monday",
    "Tu": "Tuesday",
    "We": "Wednesday",
    "Th": "Thursday",
    "Fr": "Friday",
    "Sa": "Saturday",
    "Su": "Sunday",
}

_LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)


def _find_business_ld_json(html):
    """The page can in principle carry more than one JSON-LD block (e.g. an
    Organization or breadcrumb schema alongside the location's own) -- pick
    the one that actually has hours rather than assuming it's the first.

    Pulled straight off the raw HTML string with a regex rather than via
    BeautifulSoup's script-tag traversal: it's a self-contained blob of
    text we're handing to json.loads() anyway, so there's no need to route
    it through the DOM parser first.
    """
    for match in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(match)
        except ValueError:
            continue
        if isinstance(data, dict) and "openingHours" in data:
            return data
    return None


def parse_page(html, requested_url):
    """Returns (hours_by_day, page_title, page_phone, raw_block, status_notes)."""
    notes = []
    hours_by_day = {day: None for day in hl.GBP_DAY_ORDER}
    raw_block = ""

    soup = BeautifulSoup(html, "lxml")

    h1 = soup.find("h1")
    page_title = h1.get_text(" ", strip=True) if h1 else ""

    data = _find_business_ld_json(html)
    if data is None:
        notes.append("no hours block found")
        return hours_by_day, page_title, "", raw_block, notes

    page_phone = re.sub(r"\D", "", data.get("telephone", "") or "")

    opening_hours = data.get("openingHours") or []
    if not opening_hours:
        notes.append("no hours block found")
        return hours_by_day, page_title, page_phone, raw_block, notes

    raw_block = ", ".join(opening_hours)[:400]

    # Every day starts Closed; the array only lists days the location is
    # actually open (see the module docstring on this convention).
    for day in hl.GBP_DAY_ORDER:
        hours_by_day[day] = []

    for entry in opening_hours:
        code, _, time_range = entry.partition(" ")
        day = _DAY_CODES.get(code)
        if day is None:
            continue
        hours_by_day[day] = hl.parse_day_hours(time_range)

    return hours_by_day, page_title, page_phone, raw_block, notes
