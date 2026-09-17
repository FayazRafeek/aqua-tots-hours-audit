"""Shared hours normalization. No I/O, no network.

Canonical form for a single day:
    [(start_minute, end_minute), ...]  sorted, merged, minutes from midnight
    []                                 closed
    None                               unknown / not published

`end_minute` can exceed 1440 for a range that runs past midnight
(e.g. 18:00-01:00 -> (1080, 1500)), so ranges are always start < end
and never negative.
"""

import re

GBP_DAY_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
REPORT_DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_UNKNOWN_TOKENS = {"", "n/a", "na", "none"}
_CLOSED_TOKENS = {"closed", "-", "--", "–", "—"}

_TIME_TOK = r"\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?"
_SEP = r"(?:-|–|—|to|through|until)"
_RANGE_RE = re.compile(rf"({_TIME_TOK})\s*{_SEP}\s*({_TIME_TOK})", re.IGNORECASE)
_TOKEN_WITH_MERIDIEM_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m?\.?$", re.IGNORECASE)
_TOKEN_BARE_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")
_24_HOURS_RE = re.compile(r"^(?:open\s+)?24\s*hours?$", re.IGNORECASE)


def _parse_token(tok):
    tok = tok.strip()
    m = _TOKEN_WITH_MERIDIEM_RE.match(tok)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        return hour, minute, m.group(3).lower()
    m = _TOKEN_BARE_RE.match(tok)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        return hour, minute, None
    raise ValueError(f"unparseable time token: {tok!r}")


def _to24(hour, meridiem):
    if meridiem == "a":
        return 0 if hour == 12 else hour
    return 12 if hour == 12 else hour + 12


class AmbiguousTimeRangeError(ValueError):
    """Raised for a bare (no am/pm) range whose hours could be either a
    genuine overnight span or a 12-hour time that lost its meridiem, and
    which one it is can't be told apart from the text alone."""


def _parse_pair(tok1, tok2, trust_source=False):
    h1, m1, mer1 = _parse_token(tok1)
    h2, m2, mer2 = _parse_token(tok2)

    if mer1 is None and mer2 is None:
        start_h, start_m = h1, m1
        end_h, end_m = h2, m2
        # Bare numbers are read as 24h, per the module contract -- but if
        # BOTH hours fall in 1-12, they're also valid 12-hour-clock hours
        # with no am/pm marker at all. A source that silently drops "pm"
        # (e.g. a spreadsheet exporting "8:00" for an intended "8:00 PM")
        # looks identical, on the page, to a genuine overnight range like
        # "10:00-08:00" meaning open all night. We can't tell those apart,
        # so when the literal 24h reading would require an overnight wrap
        # AND both hours are in the ambiguous 1-12 range, refuse to guess
        # rather than silently produce a wrong comparison either way --
        # UNLESS trust_source says this text is our own fmt() output being
        # read back (see parse_day_hours), in which case it's not a guess
        # at all: fmt() only ever produces this shape for a range that was
        # already a confirmed overnight span, so skipping the check here
        # is what avoids silently losing exactly that data on re-parse.
        if not trust_source and 1 <= h1 <= 12 and 1 <= h2 <= 12 and (h2 * 60 + m2) < (h1 * 60 + m1):
            raise AmbiguousTimeRangeError(f"{tok1} - {tok2}")
    elif mer1 is not None and mer2 is not None:
        start_h, start_m = _to24(h1, mer1), m1
        end_h, end_m = _to24(h2, mer2), m2
    elif mer1 is None and mer2 is not None:
        inferred = "a" if mer2 == "p" else "p"
        start_h, start_m = _to24(h1, inferred), m1
        end_h, end_m = _to24(h2, mer2), m2
    else:
        inferred = "a" if mer1 == "p" else "p"
        start_h, start_m = _to24(h1, mer1), m1
        end_h, end_m = _to24(h2, inferred), m2

    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if end < start:
        end += 1440
    return start, end


def merge(intervals):
    """Sort and merge overlapping or touching ranges."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def parse_day_hours(raw, trust_source=False):
    """Parse one day's raw hours cell (from GBP, the website, or the sheet)
    into canonical form.

    trust_source=True skips the ambiguous-overnight safety check below --
    use it ONLY when re-parsing text this module itself already produced
    via fmt() (e.g. reconstructing canonical hours from a scraped-website
    CSV column), never for raw text typed or exported by a human or a
    third-party site. fmt()'s own overnight-wrap convention (18:00-01:00)
    is indistinguishable, as text, from the ambiguous case the safety check
    exists to catch -- so re-parsing our own output with the check still on
    would silently throw away real overnight hours on every round-trip.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in _UNKNOWN_TOKENS:
        return None
    if s.lower() in _CLOSED_TOKENS:
        return []
    if _24_HOURS_RE.match(s):
        return [(0, 1440)]

    matches = _RANGE_RE.findall(s)
    if not matches:
        return None

    try:
        intervals = [_parse_pair(tok1, tok2, trust_source) for tok1, tok2 in matches]
    except AmbiguousTimeRangeError:
        # Don't guess, and don't half-parse a split-hours cell -- one
        # ambiguous range makes the whole day's data untrustworthy.
        return None

    return merge(intervals)


def _fmt_minute(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def fmt(intervals):
    """Canonical 24h display string for a day's hours."""
    if intervals is None:
        return ""
    if intervals == []:
        return "Closed"
    if intervals == [(0, 1440)]:
        return "24 hours"

    parts = []
    for start, end in intervals:
        start_disp = _fmt_minute(start % 1440)
        if end == 1440:
            end_disp = "24:00"
        elif end > 1440:
            end_disp = _fmt_minute(end - 1440)
        else:
            end_disp = _fmt_minute(end)
        parts.append(f"{start_disp}-{end_disp}")
    return ", ".join(parts)


def equal(a, b, tolerance=0):
    """Compare two canonical day values, with `tolerance` minutes of slack per boundary."""
    if a is None or b is None:
        return a is None and b is None
    if len(a) != len(b):
        return False
    for (a_start, a_end), (b_start, b_end) in zip(a, b):
        if abs(a_start - b_start) > tolerance or abs(a_end - b_end) > tolerance:
            return False
    return True


def gbp_row_hours(row, blank_means_closed=True):
    """One GBP export row -> {day: canonical}.

    If every day cell is blank, the row is treated as "no hours published"
    (None for all seven days) rather than "closed all week".
    """
    raw_by_day = {day: row.get(f"{day} hours", "") for day in GBP_DAY_ORDER}
    all_blank = all((v is None or str(v).strip() == "") for v in raw_by_day.values())
    if all_blank:
        return {day: None for day in GBP_DAY_ORDER}

    result = {}
    for day, raw in raw_by_day.items():
        is_blank = raw is None or str(raw).strip() == ""
        if is_blank:
            result[day] = [] if blank_means_closed else None
        else:
            result[day] = parse_day_hours(raw)
    return result
