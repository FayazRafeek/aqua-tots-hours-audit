import hours_lib as hl
from scrape_website_hours import extract_hours_block, normalize_url, parse_page, slug_of, split_day_blocks
from bs4 import BeautifulSoup

STERLING_HTML = """
<html><body>
<h1>Aqua-Tots Swim Lessons in Sterling, VA</h1>
<a href="tel:5715202201">(571) 520-2201</a>
<section>
  <div class="col-a">
    <p>Come see why our Monday classes fill up fast every season.</p>
  </div>
  <div class="col-b">
    <div><span>Hours of Operation</span></div>
    <div class="hours-list">
      <div><div>Monday</div><div><span>9:00am - 12:00pm</span><span>4:00pm - 7:30pm</span></div></div>
      <div><div>Tuesday</div><div><span>9:00am - 1:30pm</span><span>4:00pm - 7:30pm</span></div></div>
      <div><div>Wednesday</div><div><span>4:00pm - 7:30pm</span></div></div>
      <div><div>Thursday</div><div><span>9:00am - 1:30pm</span><span>4:00pm - 7:30pm</span></div></div>
      <div><div>Friday</div><div><span>Closed</span></div></div>
      <div><div>Saturday</div><div><span>9:00am - 5:00pm</span></div></div>
      <div><div>Sunday</div><div><span>9:00am - 1:00pm</span></div></div>
    </div>
  </div>
</section>
<p>Ask us about our Monday night parent-and-me sessions!</p>
</body></html>
"""

NO_HOURS_BLOCK_HTML = "<html><body><h1>Aqua-Tots Swim Lessons in Nowhere</h1><p>No hours heading here.</p></body></html>"


def test_normalize_url_strips_query_and_forces_trailing_slash():
    assert (
        normalize_url("https://www.aqua-tots.com/mesa?utm_source=Google&utm_medium=Organic&utm_campaign=LocalSEO")
        == "https://www.aqua-tots.com/mesa/"
    )


def test_normalize_url_handles_existing_trailing_slash_and_dup_params():
    assert (
        normalize_url(
            "https://www.aqua-tots.com/sterling/?utm_source=Google&utm_medium=Organic"
            "&utm_campaign=LocalSEO&utm_source=google&utm_medium=organic&utm_campaign=local-seo"
        )
        == "https://www.aqua-tots.com/sterling/"
    )


def test_normalize_url_blank_returns_empty_string():
    assert normalize_url("") == ""
    assert normalize_url(None) == ""
    assert normalize_url("   ") == ""


def test_slug_of():
    assert slug_of("https://www.aqua-tots.com/mesa/") == "mesa"
    assert slug_of("https://www.aqua-tots.com/sterling/") == "sterling"


def test_extract_hours_block_scopes_to_hours_container_and_ignores_later_mention():
    soup = BeautifulSoup(STERLING_HTML, "lxml")
    block = extract_hours_block(soup)
    assert block is not None
    assert "parent-and-me" not in block
    assert "fill up fast" not in block


def test_split_day_blocks_first_occurrence_wins():
    soup = BeautifulSoup(STERLING_HTML, "lxml")
    block = extract_hours_block(soup)
    days = split_day_blocks(block)
    assert set(days.keys()) == set(hl.GBP_DAY_ORDER)
    assert hl.fmt(hl.parse_day_hours(days["Monday"])) == "09:00-12:00, 16:00-19:30"
    assert hl.fmt(hl.parse_day_hours(days["Friday"])) == "Closed"


def test_parse_page_full_pipeline():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(STERLING_HTML, "https://www.aqua-tots.com/sterling/")
    assert notes == []
    assert page_title == "Aqua-Tots Swim Lessons in Sterling, VA"
    assert page_phone == "5715202201"
    assert hl.fmt(hours_by_day["Monday"]) == "09:00-12:00, 16:00-19:30"
    assert hl.fmt(hours_by_day["Tuesday"]) == "09:00-13:30, 16:00-19:30"
    assert hl.fmt(hours_by_day["Wednesday"]) == "16:00-19:30"
    assert hl.fmt(hours_by_day["Friday"]) == "Closed"
    assert hl.fmt(hours_by_day["Sunday"]) == "09:00-13:00"


def test_parse_page_missing_hours_block_flagged():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(NO_HOURS_BLOCK_HTML, "https://www.aqua-tots.com/nowhere/")
    assert notes == ["no hours block found"]
    assert all(v is None for v in hours_by_day.values())
