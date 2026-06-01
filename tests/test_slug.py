from app.utils.slug import slugify


def test_slugify_accents():
    assert slugify("Église de Paris") == "eglise-de-paris"


def test_slugify_empty_fallback():
    assert slugify("!!!") == "eglise"
