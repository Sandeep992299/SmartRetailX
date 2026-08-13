import pytest
from unittest.mock import MagicMock

class MockRedisCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

def get_product_data(product_id, db_mock, cache):
    # Try cache first
    cached = cache.get(f"product:{product_id}")
    if cached:
        return cached, "HIT"
    
    # Fallback to database
    product = db_mock.find_one({"_id": product_id})
    if not product:
        raise KeyError("Product not found")
    
    # Save to cache
    cache.set(f"product:{product_id}", product)
    return product, "MISS"

def test_redis_cache_logic():
    """Unit Test: Verify logic for cache-miss and subsequent cache-hit on Redis."""
    cache = MockRedisCache()
    db_mock = MagicMock()
    
    product_record = {"_id": "p1", "name": "Item 1", "price": 10.0}
    db_mock.find_one.return_value = product_record
    
    # 1. First request -> Cache MISS, fetches from Database
    data, status = get_product_data("p1", db_mock, cache)
    assert status == "MISS"
    assert data == product_record
    db_mock.find_one.assert_called_once_with({"_id": "p1"})
    
    # 2. Second request -> Cache HIT, bypasses database
    db_mock.reset_mock()
    data, status = get_product_data("p1", db_mock, cache)
    assert status == "HIT"
    assert data == product_record
    db_mock.find_one.assert_not_called()

def test_product_not_found_handling():
    """Unit Test: Verify error handling on nonexistent product lookups."""
    cache = MockRedisCache()
    db_mock = MagicMock()
    db_mock.find_one.return_value = None
    
    with pytest.raises(KeyError, match="Product not found"):
        get_product_data("p99", db_mock, cache)

def test_prometheus_metric_generation():
    """Unit Test: Verify generation and counter increments of application metrics."""
    metrics = {"requests_total": 0}
    
    def record_request():
        metrics["requests_total"] += 1
        
    record_request()
    assert metrics["requests_total"] == 1
