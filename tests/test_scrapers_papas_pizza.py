import hours_lib as hl
from scrapers.papas_pizza import parse_page

# Real markup shape captured from https://papaspizzatogo.com/locations/hi/ (Hiawasee, GA).
HIAWASEE_HTML = """
<html><body>
<h1>
            HIAWASEE
        </h1>
<a href="tel:7068967272">(706) 896-7272</a>
<div class="store-hours">
    <h2 class="secondary-title">Store Hours</h2>
    <div class="store-hours-grid">
					<div class="day">Sunday</div>
					<div class="hours">12:00 pm - 8:00 pm</div>

					<div class="day">Monday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Tuesday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Wednesday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Thursday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Friday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Saturday</div>
					<div class="hours">11:00 am - 9:00 pm</div>
				</div>
</div>
</body></html>
"""

# Real markup shape captured from https://papaspizzatogo.com/locations/lincolnton/ --
# two separate closed days (not just Sunday), a good edge case.
LINCOLNTON_HTML = """
<html><body>
<h1>LINCOLNTON</h1>
<a href="tel:7063593663">(706) 359-3663</a>
<div class="store-hours">
    <h2 class="secondary-title">Store Hours</h2>
    <div class="store-hours-grid">
					<div class="day">Sunday</div>
					<div class="hours">Closed</div>

					<div class="day">Monday</div>
					<div class="hours">11:00 am - 8:00 pm</div>

					<div class="day">Tuesday</div>
					<div class="hours">11:00 am - 8:00 pm</div>

					<div class="day">Wednesday</div>
					<div class="hours">Closed</div>

					<div class="day">Thursday</div>
					<div class="hours">11:00 am - 8:00 pm</div>

					<div class="day">Friday</div>
					<div class="hours">11:00 am - 9:00 pm</div>

					<div class="day">Saturday</div>
					<div class="hours">11:00 am - 9:00 pm</div>
				</div>
</div>
</body></html>
"""

NO_HOURS_BLOCK_HTML = "<html><body><h1>FIND A STORE</h1><p>No hours grid on this page.</p></body></html>"


def test_parse_page_all_open_location():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(HIAWASEE_HTML, "https://papaspizzatogo.com/locations/hi/")
    assert notes == []
    assert page_title == "HIAWASEE"
    assert page_phone == "7068967272"
    assert hl.fmt(hours_by_day["Sunday"]) == "12:00-20:00"
    assert hl.fmt(hours_by_day["Monday"]) == "11:00-21:00"
    assert hl.fmt(hours_by_day["Saturday"]) == "11:00-21:00"


def test_parse_page_multiple_closed_days():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        LINCOLNTON_HTML, "https://papaspizzatogo.com/locations/lincolnton/"
    )
    assert notes == []
    assert hl.fmt(hours_by_day["Sunday"]) == "Closed"
    assert hl.fmt(hours_by_day["Wednesday"]) == "Closed"
    assert hl.fmt(hours_by_day["Monday"]) == "11:00-20:00"
    assert hl.fmt(hours_by_day["Friday"]) == "11:00-21:00"


def test_parse_page_missing_hours_grid_flagged():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        NO_HOURS_BLOCK_HTML, "https://papaspizzatogo.com/locations/nowhere/"
    )
    assert notes == ["no hours block found"]
    assert all(v is None for v in hours_by_day.values())


def test_raw_block_is_captured_and_truncated():
    _, _, _, raw_block, _ = parse_page(HIAWASEE_HTML, "https://papaspizzatogo.com/locations/hi/")
    assert "Sunday" in raw_block
    assert len(raw_block) <= 400
