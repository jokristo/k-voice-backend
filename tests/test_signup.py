from app.constants.africa_dial_codes import ALLOWED_DIAL_CODES


def test_all_africa_countries_have_labels():
    assert "+221" in ALLOWED_DIAL_CODES
    assert len(ALLOWED_DIAL_CODES) >= 50
