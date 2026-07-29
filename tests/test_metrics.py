import sys
import os
import pytest
import importlib.util
from unittest.mock import MagicMock

# ------------------------------------------------------------
# Zero-dependency Python Mocking wrapper
# ------------------------------------------------------------
# Mock databases & web components
sys.modules['pymongo'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['httpx'] = MagicMock()

sqlalchemy_mock = MagicMock()
sys.modules['sqlalchemy'] = sqlalchemy_mock
ext_mock = MagicMock()
class MockBase:
    metadata = MagicMock()
ext_mock.declarative_base.return_value = MockBase
sys.modules['sqlalchemy.ext.declarative'] = ext_mock
sys.modules['sqlalchemy.orm'] = MagicMock()

sys.modules['kafka'] = MagicMock()

def import_from_path(module_name, file_path):
    """Dynamically imports a python file from its exact filesystem path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def test_api_gateway_metrics():
    """Verify that the API Gateway /metrics endpoint outputs standard Prometheus formatting."""
    gateway_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api-gateway", "main.py"))
    gw_main = import_from_path("gw_main", gateway_path)
    
    # Trigger the endpoint handler
    metrics_response = gw_main.prometheus_metrics()
    
    # Assert typical Prometheus headers are present
    assert "# HELP api_gateway_requests_total" in metrics_response
    assert "# TYPE api_gateway_requests_total counter" in metrics_response
    assert "api_gateway_request_latency_seconds_sum" in metrics_response
    assert "api_gateway_redis_connected" in metrics_response

def test_product_service_metrics():
    """Verify that the Product Service /metrics endpoint contains cache hit/miss details."""
    product_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "product-service", "main.py"))
    prod_main = import_from_path("prod_main", product_path)
    
    # Trigger the endpoint handler
    metrics_response = prod_main.prometheus_metrics()
    
    # Assert Prometheus headers and cache statistics are present
    assert "# HELP product_requests_total" in metrics_response
    assert "# TYPE product_requests_total counter" in metrics_response
    assert "product_cache_hits_total" in metrics_response
    assert "product_cache_misses_total" in metrics_response
