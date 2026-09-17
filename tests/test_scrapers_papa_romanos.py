import hours_lib as hl
from scrapers.papa_romanos import parse_page

# Real markup shape captured from
# https://paparomanos.com/locations/papa-romanos-mr-pita-brownstown/
BROWNSTOWN_HTML = """
<html><body>
<h1>PAPA ROMANO&#8217;S &#038; MR. PITA &#8211; BROWNSTOWN</h1>
<a href="tel:7346711266">(734) 671-1266</a>
<div class="store-hours">
    <h2 class="secondary-title">Store Hours</h2>
    <div class="store-hours-grid">
					<div class="day">Sunday</div>
					<div class="hours">11:00 am - 8:00 pm</div>

					<div class="day">Monday</div>
					<div class="hours">10:00 am - 10:00 pm</div>

					<div class="day">Tuesday</div>
					<div class="hours">10:00 am - 9:00 pm</div>

					<div class="day">Wednesday</div>
					<div class="hours">10:00 am - 9:00 pm</div>

					<div class="day">Thursday</div>
					<div class="hours">10:00 am - 9:00 pm</div>

					<div class="day">Friday</div>
					<div class="hours">10:00 am - 9:00 pm</div>

					<div class="day">Saturday</div>
					<div class="hours">10:00 am - 10:00 pm</div>
				</div>
</div>
</body></html>
"""

# Real markup from https://paparomanos.com/locations/livonia-papa-romanos-pizza-brews/ --
# this location's own tel: link is genuinely malformed on the live site
# (missing digits), which should be reported as-is, not guessed at.
LIVONIA_HTML = """
<html><body>
<h1>PAPA ROMANO&#8217;S PIZZA &#038; BREWS &#8211; Livonia, MI</h1>
<a href="tel:73425132">Call</a>
<div class="store-hours">
    <h2 class="secondary-title">Store Hours</h2>
    <div class="store-hours-grid">
					<div class="day">Sunday</div>
					<div class="hours">10:00 am - 9:00 pm</div>

					<div class="day">Monday</div>
					<div class="hours">10:00 am - 10:00 pm</div>

					<div class="day">Tuesday</div>
					<div class="hours">10:00 am - 10:00 pm</div>

					<div class="day">Wednesday</div>
					<div class="hours">10:00 am - 10:00 pm</div>

					<div class="day">Thursday</div>
					<div class="hours">10:00 am - 10:00 pm</div>

					<div class="day">Friday</div>
					<div class="hours">10:00 am - 11:00 pm</div>

					<div class="day">Saturday</div>
					<div class="hours">10:00 am - 11:00 pm</div>
				</div>
</div>
</body></html>
"""

NO_HOURS_BLOCK_HTML = "<html><body><h1>PAPA ROMANO&#8217;S</h1><p>No hours grid on this page.</p></body></html>"


def test_parse_page_typical_location():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        BROWNSTOWN_HTML, "https://paparomanos.com/locations/papa-romanos-mr-pita-brownstown/"
    )
    assert notes == []
    assert "BROWNSTOWN" in page_title
    assert page_phone == "7346711266"
    assert hl.fmt(hours_by_day["Sunday"]) == "11:00-20:00"
    assert hl.fmt(hours_by_day["Monday"]) == "10:00-22:00"
    assert hl.fmt(hours_by_day["Saturday"]) == "10:00-22:00"


def test_parse_page_reports_malformed_phone_faithfully():
    # The site's own tel: link is missing digits for this location -- the
    # scraper's job is to report what's published, not to validate or fix it.
    hours_by_day, _, page_phone, _, notes = parse_page(
        LIVONIA_HTML, "https://paparomanos.com/locations/livonia-papa-romanos-pizza-brews/"
    )
    assert notes == []
    assert page_phone == "73425132"
    assert hl.fmt(hours_by_day["Friday"]) == "10:00-23:00"


def test_parse_page_missing_hours_grid_flagged():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        NO_HOURS_BLOCK_HTML, "https://paparomanos.com/locations/nowhere/"
    )
    assert notes == ["no hours block found"]
    assert all(v is None for v in hours_by_day.values())


def test_raw_block_is_captured_and_truncated():
    _, _, _, raw_block, _ = parse_page(BROWNSTOWN_HTML, "https://paparomanos.com/locations/papa-romanos-mr-pita-brownstown/")
    assert "Sunday" in raw_block
    assert len(raw_block) <= 400
