import pytest
from unittest.mock import MagicMock

def calculate_total(items):
    return sum(item["price"] * item["quantity"] for item in items)

def create_order_event(order_id, total_amount):
    return {
        "event_type": "order-created",
        "order_id": order_id,
        "total_amount": total_amount
    }

def test_order_total():
    """Unit Test: Verify calculation of order total amount."""
    items = [
        {"price": 100, "quantity": 2},
        {"price": 50, "quantity": 1}
    ]
    total = calculate_total(items)
    assert total == 250

def test_order_event():
    """Unit Test: Verify format and fields of generated Kafka order-created event."""
    event = create_order_event(
        order_id="ORD001",
        total_amount=250
    )
    assert event["event_type"] == "order-created"
    assert event["order_id"] == "ORD001"
    assert event["total_amount"] == 250

def test_order_validation():
    """Unit Test: Verify input validation logic fails with bad quantity inputs."""
    # Simulation of validation error
    def validate_order(items):
        for item in items:
            if item["quantity"] <= 0:
                raise ValueError("Quantity must be positive")
        return True

    with pytest.raises(ValueError, match="Quantity must be positive"):
        validate_order([{"product_id": "p1", "quantity": -5}])
