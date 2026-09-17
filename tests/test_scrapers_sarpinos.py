import hours_lib as hl
from scrapers.sarpinos import parse_page

# Real markup shape captured from
# https://www.gosarpinos.com/pizza-delivery/sarpinos-overland-park
OVERLAND_PARK_HTML = """
<html><body>
<h1>Sarpino&#8217;s Overland Park</h1>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"FoodEstablishment","name":"Sarpino's Pizzeria",
"telephone":"913-681-2900","openingHours":["Mo 10:00 am-2:00 am","Tu 10:00 am-2:00 am",
"We 10:00 am-2:00 am","Th 10:00 am-2:00 am","Fr 10:00 am-3:00 am","Sa 10:00 am-3:00 am",
"Su 10:00 am-2:00 am"]}
</script>
</body></html>
"""

# Real data captured from https://www.gosarpinos.com/pizza-delivery/sarpinos-braeswood --
# Sunday is a shorter, different range than the rest of the week.
BRAESWOOD_HTML = """
<html><body>
<h1>Sarpino&#8217;s Braeswood</h1>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"FoodEstablishment","name":"Sarpino's Pizzeria",
"telephone":"713-555-0100","openingHours":["Mo 10:00 am-1:00 am","Tu 10:00 am-1:00 am",
"We 10:00 am-1:00 am","Th 10:00 am-1:00 am","Fr 10:00 am-1:00 am","Sa 10:00 am-1:00 am",
"Su 11:00 am-12:00 pm"]}
</script>
</body></html>
"""

# No real closed-day example was found on the live site; this exercises the
# schema.org convention (a day missing from the array = closed) synthetically.
MISSING_DAY_HTML = """
<html><body>
<h1>Sarpino&#8217;s Nowhere</h1>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"FoodEstablishment","name":"Sarpino's Pizzeria",
"telephone":"555-555-0100","openingHours":["Mo 10:00 am-2:00 am","Tu 10:00 am-2:00 am",
"We 10:00 am-2:00 am","Th 10:00 am-2:00 am","Fr 10:00 am-2:00 am","Sa 10:00 am-2:00 am"]}
</script>
</body></html>
"""

# A page carrying an unrelated JSON-LD block (e.g. breadcrumbs) alongside
# the real one, to confirm the right script gets picked rather than the first.
MULTIPLE_LD_JSON_HTML = """
<html><body>
<h1>Sarpino&#8217;s Multi</h1>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[]}</script>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"FoodEstablishment","telephone":"555-555-0200",
"openingHours":["Mo 10:00 am-2:00 am"]}
</script>
</body></html>
"""

NO_HOURS_BLOCK_HTML = "<html><body><h1>Sarpino&#8217;s Missing</h1><p>No JSON-LD here.</p></body></html>"


def test_parse_page_typical_location():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        OVERLAND_PARK_HTML, "https://www.gosarpinos.com/pizza-delivery/sarpinos-overland-park"
    )
    assert notes == []
    assert page_title == "Sarpino’s Overland Park"
    assert page_phone == "9136812900"
    assert hl.fmt(hours_by_day["Monday"]) == "10:00-02:00"
    assert hl.fmt(hours_by_day["Friday"]) == "10:00-03:00"
    assert hl.fmt(hours_by_day["Sunday"]) == "10:00-02:00"


def test_parse_page_short_sunday_range():
    hours_by_day, _, _, _, notes = parse_page(
        BRAESWOOD_HTML, "https://www.gosarpinos.com/pizza-delivery/sarpinos-braeswood"
    )
    assert notes == []
    assert hl.fmt(hours_by_day["Monday"]) == "10:00-01:00"
    assert hl.fmt(hours_by_day["Sunday"]) == "11:00-12:00"


def test_parse_page_day_missing_from_array_is_closed():
    hours_by_day, _, _, _, notes = parse_page(MISSING_DAY_HTML, "https://www.gosarpinos.com/pizza-delivery/nowhere")
    assert notes == []
    assert hl.fmt(hours_by_day["Sunday"]) == "Closed"
    assert hl.fmt(hours_by_day["Monday"]) == "10:00-02:00"


def test_parse_page_picks_the_ld_json_block_with_hours():
    hours_by_day, _, page_phone, _, notes = parse_page(
        MULTIPLE_LD_JSON_HTML, "https://www.gosarpinos.com/pizza-delivery/multi"
    )
    assert notes == []
    assert page_phone == "5555550200"
    assert hl.fmt(hours_by_day["Monday"]) == "10:00-02:00"
    assert hl.fmt(hours_by_day["Tuesday"]) == "Closed"


def test_parse_page_missing_json_ld_flagged():
    hours_by_day, page_title, page_phone, raw_block, notes = parse_page(
        NO_HOURS_BLOCK_HTML, "https://www.gosarpinos.com/pizza-delivery/missing"
    )
    assert notes == ["no hours block found"]
    assert all(v is None for v in hours_by_day.values())
