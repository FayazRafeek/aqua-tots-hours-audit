import pytest

import hours_lib as hl


# ---------------------------------------------------------------------------
# parse_day_hours table from the spec
# ---------------------------------------------------------------------------

STANDARD_9_5 = [
    "9am - 5pm",
    "9:00 AM - 5:00 PM",
    "09:00-17:00",
    "9:00am – 5:00pm",
    "9:00am to 5:00pm",
    "9 - 5pm",
]


@pytest.mark.parametrize("raw", STANDARD_9_5)
def test_standard_9_to_5(raw):
    assert hl.fmt(hl.parse_day_hours(raw)) == "09:00-17:00"


def test_midnight_to_noon():
    assert hl.fmt(hl.parse_day_hours("12:00am - 12:00pm")) == "00:00-12:00"


def test_noon_to_8pm():
    assert hl.fmt(hl.parse_day_hours("12:00pm - 8:00pm")) == "12:00-20:00"


def test_overnight_wraps_past_midnight():
    intervals = hl.parse_day_hours("6:00pm - 1:00am")
    assert intervals == [(18 * 60, 25 * 60)]
    assert hl.fmt(intervals) == "18:00-01:00"


# ---------------------------------------------------------------------------
# Ambiguous bare ranges (both hours 1-12, no am/pm at all): a source that
# silently dropped "pm" (e.g. a spreadsheet exporting "8:00" for an intended
# "8:00 PM") is indistinguishable, in the text, from a genuine overnight
# range. Real example from the master sheet: "10:15-08:00" was meant as
# 10:15am-8:00pm, not "open all night until 8am". Refuse to guess rather
# than silently produce a wrong comparison either way.
# ---------------------------------------------------------------------------

AMBIGUOUS_BARE_RANGES = [
    "10:15-08:00",
    "09:00-07:45",
    "12:00-07:45",
    "09:00-08:00",
    "08:30-02:00",
]


@pytest.mark.parametrize("raw", AMBIGUOUS_BARE_RANGES)
def test_ambiguous_bare_range_is_unknown_not_a_guess(raw):
    assert hl.parse_day_hours(raw) is None


def test_ambiguous_range_makes_whole_split_hours_cell_unknown():
    # One bad range shouldn't leave a half-trustworthy result for the day.
    assert hl.parse_day_hours("9:00am - 12:00pm 4:00-2:00") is None


def test_explicit_meridiem_overnight_range_is_not_treated_as_ambiguous():
    # Contrast with the ambiguous case: an explicit am/pm marker makes the
    # overnight span unambiguous, so it must still parse normally.
    assert hl.parse_day_hours("6:00pm - 1:00am") == [(18 * 60, 25 * 60)]


def test_unambiguous_24h_hour_is_not_treated_as_ambiguous():
    # An hour outside 1-12 (here, 17) can only be 24h notation, so this
    # isn't ambiguous even though it's bare -- and it doesn't need a wrap.
    assert hl.fmt(hl.parse_day_hours("9:00-17:00")) == "09:00-17:00"


# ---------------------------------------------------------------------------
# trust_source: re-parsing our own fmt() output must round-trip correctly,
# even for overnight ranges that look identical, as text, to the ambiguous
# case above. Regression test for a real bug: a scraped website's overnight
# hours (e.g. Sarpino's Pizzeria, open until 1-3am) got formatted to
# "10:00-02:00" by fmt(), then silently turned into "unknown" the moment
# three_way_compare/compare_hours re-parsed that same string without
# trust_source, discarding real hours on every comparison run.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["10:00-02:00", "10:00-01:00", "10:00-03:00"])
def test_trust_source_round_trips_overnight_fmt_output(raw):
    assert hl.parse_day_hours(raw, trust_source=True) is not None
    assert hl.fmt(hl.parse_day_hours(raw, trust_source=True)) == raw


def test_trust_source_false_by_default_still_rejects_ambiguous_text():
    # The default stays safe for actual raw/human-entered source text --
    # trust_source is opt-in, not a global relaxation of the safety check.
    assert hl.parse_day_hours("10:00-02:00") is None


def test_fmt_then_reparse_with_trust_source_recovers_original_overnight_range():
    original = hl.parse_day_hours("6:00pm - 1:00am")
    round_tripped = hl.parse_day_hours(hl.fmt(original), trust_source=True)
    assert round_tripped == original
    assert hl.fmt(hl.parse_day_hours("00:00-24:00")) == "24 hours"


def test_split_hours_no_comma():
    assert hl.fmt(hl.parse_day_hours("9:00am - 12:00pm 4:00pm - 7:30pm")) == "09:00-12:00, 16:00-19:30"


def test_split_hours_comma_gets_sorted():
    assert hl.fmt(hl.parse_day_hours("16:00-19:30, 09:00-13:30")) == "09:00-13:30, 16:00-19:30"


def test_adjacent_ranges_merge():
    assert hl.fmt(hl.parse_day_hours("09:00-12:00, 12:00-19:00")) == "09:00-19:00"


@pytest.mark.parametrize("raw", ["Open 24 hours", "24 hours", "00:00-24:00"])
def test_24_hours(raw):
    assert hl.parse_day_hours(raw) == [(0, 1440)]
    assert hl.fmt(hl.parse_day_hours(raw)) == "24 hours"


@pytest.mark.parametrize("raw", ["Closed", "-", "--"])
def test_closed(raw):
    assert hl.parse_day_hours(raw) == []
    assert hl.fmt([]) == "Closed"


@pytest.mark.parametrize("raw", ["", "N/A", "None", None])
def test_unknown(raw):
    assert hl.parse_day_hours(raw) is None
    assert hl.fmt(None) == ""


# ---------------------------------------------------------------------------
# Real rendered text fixtures
# ---------------------------------------------------------------------------

MESA_TEXT = (
    "Hours of Operation Monday 8:00am - 7:00pm Tuesday 8:00am - 7:00pm "
    "Wednesday 8:00am - 7:00pm Thursday 8:00am - 7:00pm Friday 8:00am - 7:00pm "
    "Saturday 8:00am - 1:00pm Sunday Closed"
)

STERLING_TEXT = (
    "Hours of Operation Monday 9:00am - 12:00pm 4:00pm - 7:30pm "
    "Tuesday 9:00am - 1:30pm 4:00pm - 7:30pm Wednesday 4:00pm - 7:30pm "
    "Thursday 9:00am - 1:30pm 4:00pm - 7:30pm Friday Closed "
    "Saturday 9:00am - 5:00pm Sunday 9:00am - 1:00pm"
)


def _split_day_blocks(text):
    """Mirror of the scraper's day-label splitting, used only to test hours_lib
    against the real rendered text without importing the scraper module."""
    positions = []
    for day in hl.GBP_DAY_ORDER:
        m = __import__("re").search(rf"\b{day}\b", text)
        if m:
            positions.append((day, m.start(), m.end()))
    positions.sort(key=lambda p: p[1])
    blocks = {}
    for i, (day, start, end) in enumerate(positions):
        next_start = positions[i + 1][1] if i + 1 < len(positions) else len(text)
        blocks[day] = text[end:next_start].strip()
    return blocks


def test_mesa_fixture_parses_all_seven_days():
    blocks = _split_day_blocks(MESA_TEXT)
    parsed = {day: hl.fmt(hl.parse_day_hours(blocks[day])) for day in hl.GBP_DAY_ORDER}
    assert parsed == {
        "Sunday": "Closed",
        "Monday": "08:00-19:00",
        "Tuesday": "08:00-19:00",
        "Wednesday": "08:00-19:00",
        "Thursday": "08:00-19:00",
        "Friday": "08:00-19:00",
        "Saturday": "08:00-13:00",
    }


def test_sterling_fixture_parses_split_days_and_closed_friday():
    blocks = _split_day_blocks(STERLING_TEXT)
    parsed = {day: hl.fmt(hl.parse_day_hours(blocks[day])) for day in hl.GBP_DAY_ORDER}
    assert parsed == {
        "Sunday": "09:00-13:00",
        "Monday": "09:00-12:00, 16:00-19:30",
        "Tuesday": "09:00-13:30, 16:00-19:30",
        "Wednesday": "16:00-19:30",
        "Thursday": "09:00-13:30, 16:00-19:30",
        "Friday": "Closed",
        "Saturday": "09:00-17:00",
    }


# ---------------------------------------------------------------------------
# Equivalence / tolerance
# ---------------------------------------------------------------------------

def test_equivalent_representations_are_equal():
    assert hl.equal(hl.parse_day_hours("8:00am - 7:00pm"), hl.parse_day_hours("08:00-19:00"))
    assert hl.equal(
        hl.parse_day_hours("9:00am - 12:00pm 4:00pm - 7:30pm"),
        hl.parse_day_hours("09:00-12:00, 16:00-19:30"),
    )


def test_different_end_time_not_equal_without_tolerance():
    assert not hl.equal(hl.parse_day_hours("08:00-19:00"), hl.parse_day_hours("08:00-19:30"))


def test_tolerance_forgives_small_boundary_difference():
    assert hl.equal(hl.parse_day_hours("08:00-19:00"), hl.parse_day_hours("08:00-19:15"), tolerance=15)
    assert not hl.equal(hl.parse_day_hours("08:00-19:00"), hl.parse_day_hours("08:00-19:30"), tolerance=15)


# ---------------------------------------------------------------------------
# gbp_row_hours
# ---------------------------------------------------------------------------

def _row(**overrides):
    base = {f"{day} hours": "" for day in hl.GBP_DAY_ORDER}
    base.update(overrides)
    return base


def test_gbp_row_all_blank_is_unknown_not_closed():
    row = _row()
    result = hl.gbp_row_hours(row)
    assert result == {day: None for day in hl.GBP_DAY_ORDER}


def test_gbp_row_blank_means_closed_by_default():
    row = _row(**{"Monday hours": "09:00-17:00"})
    result = hl.gbp_row_hours(row)
    assert result["Monday"] == [(9 * 60, 17 * 60)]
    assert result["Tuesday"] == []


def test_gbp_row_blank_means_unknown_when_flag_flipped():
    row = _row(**{"Monday hours": "09:00-17:00"})
    result = hl.gbp_row_hours(row, blank_means_closed=False)
    assert result["Monday"] == [(9 * 60, 17 * 60)]
    assert result["Tuesday"] is None


# ---------------------------------------------------------------------------
# GBP's split-at-midnight overnight encoding
# ---------------------------------------------------------------------------

# Real markup of the shape every overnight location in a GBP export uses --
# captured from Sarpino's Pizzeria South Leawood. Fri/Sat nights close at
# 03:00, every other night at 02:00, which is why the tails differ.
SPLIT_OVERNIGHT_ROW = {
    "Sunday hours": "00:00-03:00, 10:00-24:00",
    "Monday hours": "00:00-02:00, 10:00-24:00",
    "Tuesday hours": "00:00-02:00, 10:00-24:00",
    "Wednesday hours": "00:00-02:00, 10:00-24:00",
    "Thursday hours": "00:00-02:00, 10:00-24:00",
    "Friday hours": "00:00-02:00, 10:00-24:00",
    "Saturday hours": "00:00-03:00, 10:00-24:00",
}


def test_split_midnight_becomes_one_overnight_session():
    result = hl.gbp_row_hours(SPLIT_OVERNIGHT_ROW)
    # Read literally this day is "open 00:00-02:00, then again 10:00-24:00";
    # what it actually is, is one session opening at 10:00 and closing at 02:00.
    assert result["Monday"] == [(10 * 60, 24 * 60 + 2 * 60)]
    assert hl.fmt(result["Monday"]) == "10:00-02:00"


def test_closing_time_comes_from_the_following_days_tail():
    # The Friday-night close is published on Saturday's row, so reading
    # Friday's own cell alone gives 02:00 -- Thursday night's close.
    result = hl.gbp_row_hours(SPLIT_OVERNIGHT_ROW)
    assert hl.fmt(result["Friday"]) == "10:00-03:00"
    assert hl.fmt(result["Thursday"]) == "10:00-02:00"


def test_saturday_night_tail_wraps_around_to_sunday():
    result = hl.gbp_row_hours(SPLIT_OVERNIGHT_ROW)
    assert hl.fmt(result["Saturday"]) == "10:00-03:00"  # from Sunday's 00:00-03:00
    assert hl.fmt(result["Sunday"]) == "10:00-02:00"  # from Monday's 00:00-02:00


def test_stitched_gbp_hours_equal_the_websites_single_range():
    # The whole point: GBP's two fragments and a site's "10:00 AM - 2:00 AM"
    # have to land on the same canonical value or every night is a false
    # mismatch.
    result = hl.gbp_row_hours(SPLIT_OVERNIGHT_ROW)
    assert hl.equal(result["Monday"], hl.parse_day_hours("10:00 am - 2:00 am"))


def test_open_24_hours_is_not_stitched_into_a_48_hour_day():
    row = _row(**{f"{day} hours": "00:00-24:00" for day in hl.GBP_DAY_ORDER})
    result = hl.gbp_row_hours(row)
    assert result["Monday"] == [(0, 1440)]


def test_ordinary_hours_are_left_alone():
    row = _row(**{"Monday hours": "10:00-23:00", "Tuesday hours": "10:00-23:00"})
    result = hl.gbp_row_hours(row)
    assert result["Monday"] == [(10 * 60, 23 * 60)]
    assert result["Tuesday"] == [(10 * 60, 23 * 60)]


def test_midnight_close_with_no_tail_next_day_stays_a_midnight_close():
    # Nothing to rejoin: Tuesday is closed, so Monday really does end at 24:00.
    row = _row(**{"Monday hours": "10:00-24:00"})
    result = hl.gbp_row_hours(row)
    assert hl.fmt(result["Monday"]) == "10:00-24:00"


def test_day_that_is_only_a_carryover_becomes_closed():
    # Open Monday 10:00 through Tuesday 02:00 and not otherwise on Tuesday --
    # Tuesday has no opening of its own.
    row = _row(**{"Monday hours": "10:00-24:00", "Tuesday hours": "00:00-02:00"})
    result = hl.gbp_row_hours(row)
    assert hl.fmt(result["Monday"]) == "10:00-02:00"
    assert result["Tuesday"] == []


def test_split_lunch_dinner_hours_are_not_treated_as_overnight():
    row = _row(**{"Monday hours": "11:00-14:00, 17:00-22:00"})
    result = hl.gbp_row_hours(row)
    assert result["Monday"] == [(11 * 60, 14 * 60), (17 * 60, 22 * 60)]
