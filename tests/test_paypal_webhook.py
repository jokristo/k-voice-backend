from app.services.billing.webhook_handler import (
    map_paypal_subscription_status,
    should_handle_event,
    _subscription_id_from_resource,
)


def test_map_paypal_subscription_status():
    assert map_paypal_subscription_status("ACTIVE") == "active"
    assert map_paypal_subscription_status("CANCELLED") == "cancelled"
    assert map_paypal_subscription_status("UNKNOWN") == "none"


def test_should_handle_event():
    assert should_handle_event("BILLING.SUBSCRIPTION.CANCELLED") is True
    assert should_handle_event("PAYMENT.SALE.COMPLETED") is False


def test_subscription_id_from_resource():
    assert _subscription_id_from_resource({"id": "I-ABC"}) == "I-ABC"
    assert _subscription_id_from_resource({"subscription_id": "I-XYZ"}) == "I-XYZ"
    assert _subscription_id_from_resource({}) is None
