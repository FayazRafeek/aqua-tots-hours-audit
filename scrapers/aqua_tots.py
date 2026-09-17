"""Aqua-Tots-specific hours extraction.

Page shape: a "Hours of Operation" heading followed by a day-by-day list
somewhere in an ancestor element. There's no stable CSS class to hook, so
we find the heading text and climb until we hit an ancestor whose text
contains enough weekday names to be confident it's the real hours block,
falling back to a fixed character window if no such ancestor exists.
"""

import re

from bs4 import BeautifulSoup

import hours_lib as hl

FALLBACK_WINDOW_CHARS = 700


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
