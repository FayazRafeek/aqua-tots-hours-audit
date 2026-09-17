import hours_lib as hl
from scrapers.breadeaux import parse_page

# Real markup shape captured from https://breadeauxpizza.com/locations/palmyra/
PALMYRA_HTML = """
<html><body>
<h1>
    Palmyra
</h1>
<a href="tel:5737692671" class="gtutilize-local-call-button">Call</a>
<div class="store-hours">
    <h2 class="secondary-title">Store Hours</h2>
    <div class="store-hours-grid">
					<div class="day">Sunday</div>
					<div class="hours">11:00 am - 10:00 pm</div>

					<div class="day">Monday</div>
					<div class="hours">11:00 am - 10:00 pm</div>

					<div class="day">Tuesday</div>
					<div class="hours">11:00 am - 10:00 pm</div>

					<div class="day">Wednesday</div>
					<div class="hours">11:00 am - 10:00 pm</div>

					<div class="day">Thursday</div>
					<div class="hours">11:00 am - 10:00 pm</div>

					<div class="day">Friday</div>
					<div class="hours">11:00 am - 10:00 pm</div>

					<div class="day">Saturday</div>
					<div class="hours">11:00 am - 10:00 pm</div>
				</div>
</div>
</body></html>
"""

# Real markup from https://breadeauxpizza.com/locations/boonville/ -- hours
# vary by day, including a shorter Monday.
BOONVILLE_HTML = """
<html><body>
<h1>
    Boonville
</h1>
<a href="tel:6608823401" class="gtutilize-local-call-button">Call</a>
<div class="store-hours">
    <h2 class="secondary-title">Store Hours</h2>
    <div class="store-hours-grid">
					<div class="day">Sunday</div>
					<div class="hours">11:00 am - 8:00 pm</div>

					<div class="day">Monday</div>
					<div class="hours">4:30 pm - 9:00 pm</div>

					<div class="day">Tuesday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Wednesday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Thursday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Friday</div>
					<div class="hours">11:00 am - 10:00 pm</div>

					<div class="day">Saturday</div>
					<div class="hours">11:00 am - 10:00 pm</div>
				</div>
</div>
</body></html>
"""

# Real markup from https://breadeauxpizza.com/locations/pleasant-hill/ -- this
# location is closed on Mondays.
PLEASANT_HILL_HTML = """
<html><body>
<h1>
    Pleasant Hill
</h1>
<a href="tel:5152638888" class="gtutilize-local-call-button">Call</a>
<div class="store-hours">
    <h2 class="secondary-title">Store Hours</h2>
    <div class="store-hours-grid">
					<div class="day">Sunday</div>
					<div class="hours">4:00 pm - 9:00 pm</div>

					<div class="day">Monday</div>
					<div class="hours">Closed</div>

					<div class="day">Tuesday</div>
					<div class="hours">4:00 pm - 9:00 pm</div>

					<div class="day">Wednesday</div>
					<div class="hours">4:00 pm - 9:00 pm</div>

					<div class="day">Thursday</div>
					<div class="hours">4:00 pm - 9:00 pm</div>

					<div class="day">Friday</div>
					<div class="hours">4:00 pm - 9:00 pm</div>

					<div class="day">Saturday</div>
					<div class="hours">4:00 pm - 9:00 pm</div>
				</div>
</div>
</body></html>
"""

NO_HOURS_BLOCK_HTML = "<html><body><h1>Nowhere</h1><p>No hours grid on this page.</p></body></html>"


def test_parse_page_typical_location():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        PALMYRA_HTML, "https://breadeauxpizza.com/locations/palmyra/"
    )
    assert notes == []
    assert page_title == "Palmyra"
    assert page_phone == "5737692671"
    assert hl.fmt(hours_by_day["Sunday"]) == "11:00-22:00"
    assert hl.fmt(hours_by_day["Saturday"]) == "11:00-22:00"


def test_parse_page_hours_vary_by_day():
    hours_by_day, _, page_phone, _, notes = parse_page(
        BOONVILLE_HTML, "https://breadeauxpizza.com/locations/boonville/"
    )
    assert notes == []
    assert page_phone == "6608823401"
    assert hl.fmt(hours_by_day["Monday"]) == "16:30-21:00"
    assert hl.fmt(hours_by_day["Friday"]) == "11:00-22:00"


def test_parse_page_reports_closed_day():
    hours_by_day, _, _, _, notes = parse_page(
        PLEASANT_HILL_HTML, "https://breadeauxpizza.com/locations/pleasant-hill/"
    )
    assert notes == []
    assert hours_by_day["Monday"] == []
    assert hl.fmt(hours_by_day["Sunday"]) == "16:00-21:00"


def test_parse_page_missing_hours_grid_flagged():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        NO_HOURS_BLOCK_HTML, "https://breadeauxpizza.com/locations/nowhere/"
    )
    assert notes == ["no hours block found"]
    assert all(v is None for v in hours_by_day.values())


def test_raw_block_is_captured_and_truncated():
    _, _, _, raw_block, _ = parse_page(PALMYRA_HTML, "https://breadeauxpizza.com/locations/palmyra/")
    assert "Sunday" in raw_block
    assert len(raw_block) <= 400
