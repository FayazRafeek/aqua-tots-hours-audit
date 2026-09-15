import pytest

from sheet_source import export_csv_url, normalize_name, sheet_id_from_url


def test_sheet_id_from_url():
    url = "https://docs.google.com/spreadsheets/d/17q2frziO5xfG55z7E8UsEDT56APvH93FSBPpV4b4Y20/edit?usp=sharing"
    assert sheet_id_from_url(url) == "17q2frziO5xfG55z7E8UsEDT56APvH93FSBPpV4b4Y20"


def test_sheet_id_from_url_raises_on_garbage():
    with pytest.raises(ValueError):
        sheet_id_from_url("not a sheet url")


def test_export_csv_url_accepts_full_url_or_bare_id():
    sheet_id = "17q2frziO5xfG55z7E8UsEDT56APvH93FSBPpV4b4Y20"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?usp=sharing"
    expected = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    assert export_csv_url(url) == expected
    assert export_csv_url(sheet_id) == expected


def test_normalize_name_collapses_case_punctuation_and_whitespace():
    assert normalize_name("Aqua-Tots Swim School  Mesa") == "aqua tots swim school mesa"
    assert normalize_name("AQUA-TOTS SWIM SCHOOL MESA") == "aqua tots swim school mesa"
    assert normalize_name(" Mesa. ") == "mesa"
