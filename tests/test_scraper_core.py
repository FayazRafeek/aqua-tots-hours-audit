from scraper_core import normalize_url, slug_of


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


def test_normalize_url_works_for_any_brands_domain():
    # normalize_url is brand-agnostic by design -- no site-specific logic here.
    assert (
        normalize_url("https://papaspizzatogo.com/locations/hi?utm_source=Google&utm_medium=Organic")
        == "https://papaspizzatogo.com/locations/hi/"
    )


def test_slug_of():
    assert slug_of("https://www.aqua-tots.com/mesa/") == "mesa"
    assert slug_of("https://www.aqua-tots.com/sterling/") == "sterling"
    assert slug_of("https://papaspizzatogo.com/locations/hi/") == "hi"
