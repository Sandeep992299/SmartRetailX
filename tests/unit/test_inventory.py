import pytest

def calculate_remaining_stock(current_stock, quantity_demanded):
    if quantity_demanded > current_stock:
        raise ValueError("Insufficient inventory available")
    return current_stock - quantity_demanded

def is_low_stock_level(remaining_stock, threshold=5):
    return remaining_stock <= threshold

def test_inventory_calculation():
    """Unit Test: Verify correct decrement calculations and exceptions on over-drafts."""
    current = 10
    remaining = calculate_remaining_stock(current, 3)
    assert remaining == 7
    
    with pytest.raises(ValueError, match="Insufficient inventory available"):
        calculate_remaining_stock(current, 12)

def test_low_stock_boundary_detection():
    """Unit Test: Verify stock levels that trigger low stock alerts."""
    # Threshold is 5 by default
    assert is_low_stock_level(10) is False
    assert is_low_stock_level(5) is True
    assert is_low_stock_level(2) is True
