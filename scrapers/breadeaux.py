"""Breadeaux Pizza-specific hours extraction.

Page shape: a `.store-hours-grid` container with flat, alternating
`<div class="day">` / `<div class="hours">` siblings -- one pair per day,
Sunday first. Structurally identical to scrapers/papas_pizza.py and
scrapers/papa_romanos.py (all three appear to run on the same website
vendor's template), but kept as its own independent module for the same
reason as papa_romanos.py: separate businesses that merely share a platform
today, with no guarantee their templates stay in sync going forward.

A day can read "Closed" outright (confirmed on the Pleasant Hill, IA
location) -- hours_lib.parse_day_hours() already handles that text.
"""

import re

from bs4 import BeautifulSoup

import hours_lib as hl


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

    grid = soup.find(class_="store-hours-grid")
    if grid is None:
        notes.append("no hours block found")
        return hours_by_day, page_title, page_phone, raw_block, notes

    raw_block = re.sub(r"\s+", " ", grid.get_text(" ", strip=True)).strip()[:400]

    for day_div in grid.find_all("div", class_="day"):
        day_name = day_div.get_text(strip=True)
        if day_name not in hl.GBP_DAY_ORDER or hours_by_day[day_name] is not None:
            continue  # unrecognized label, or first occurrence already won
        hours_div = day_div.find_next_sibling("div", class_="hours")
        if hours_div is not None:
            hours_by_day[day_name] = hl.parse_day_hours(hours_div.get_text(strip=True))

    return hours_by_day, page_title, page_phone, raw_block, notes
