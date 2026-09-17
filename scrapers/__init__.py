"""Registry of supported brands.

Adding a brand means writing scrapers/<brand>.py with a parse_page(html,
requested_url) function (see aqua_tots.py or papas_pizza.py for the
contract) and adding one line here -- nothing else in the project needs to
change, since scraper_core.py, hours_lib.py, sheet_source.py,
three_way_compare.py, and app.py are all brand-agnostic.
"""

from . import aqua_tots, papa_romanos, papas_pizza, sarpinos

BRANDS = {
    "aqua_tots": {
        "label": "Aqua-Tots",
        "parse_page": aqua_tots.parse_page,
        "default_sheet_url": "https://docs.google.com/spreadsheets/d/17q2frziO5xfG55z7E8UsEDT56APvH93FSBPpV4b4Y20/edit?usp=sharing",
    },
    "papas_pizza": {
        "label": "Papa's Pizza To Go",
        "parse_page": papas_pizza.parse_page,
        "default_sheet_url": "",
    },
    "sarpinos": {
        "label": "Sarpino's Pizzeria",
        "parse_page": sarpinos.parse_page,
        "default_sheet_url": "",
    },
    "papa_romanos": {
        "label": "Papa Romano's",
        "parse_page": papa_romanos.parse_page,
        "default_sheet_url": "",
    },
}
