import sys
import os
import pytest
import importlib.util
from unittest.mock import MagicMock

# Un-mock fastapi and standard modules if they were globally mocked by other tests in the runner
for module_name in ['fastapi', 'fastapi.responses', 'fastapi.middleware.cors', 'fastapi.middleware']:
    if module_name in sys.modules and isinstance(sys.modules[module_name], MagicMock):
        del sys.modules[module_name]

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

def setup_function(function):
    """Clean up sys.modules to remove any global MagicMocks before importing or running tests."""
    for module_name in ['fastapi', 'fastapi.responses', 'fastapi.middleware.cors', 'fastapi.middleware']:
        if module_name in sys.modules and isinstance(sys.modules[module_name], MagicMock):
            del sys.modules[module_name]

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

def test_user_service_metrics():
    """Verify that the User Service /metrics endpoint outputs standard Prometheus formatting."""
    user_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "user-service", "main.py"))
    user_main = import_from_path("user_main", user_path)
    
    metrics_response = user_main.prometheus_metrics()
    assert "# HELP user_requests_total" in metrics_response
    assert "user_mongodb_connected" in metrics_response

def test_order_service_metrics():
    """Verify that the Order Service /metrics endpoint outputs standard Prometheus formatting."""
    order_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "order-service", "main.py"))
    order_main = import_from_path("order_main", order_path)
    
    metrics_response = order_main.prometheus_metrics()
    assert "# HELP order_requests_total" in metrics_response
    assert "orders_created_total" in metrics_response
    assert "order_mongodb_connected" in metrics_response
    assert "order_kafka_connected" in metrics_response

def test_payment_service_metrics():
    """Verify that the Payment Service /metrics endpoint outputs standard Prometheus formatting."""
    payment_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "payment-service", "main.py"))
    payment_main = import_from_path("payment_main", payment_path)
    
    metrics_response = payment_main.prometheus_metrics()
    assert "# HELP payment_requests_total" in metrics_response
    assert "payments_processed_total" in metrics_response
    assert "payment_circuit_breaker_state" in metrics_response
    assert "payment_kafka_connected" in metrics_response

def test_inventory_service_metrics():
    """Verify that the Inventory Service /metrics endpoint contains cache hit/miss details."""
    inventory_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "inventory-service", "main.py"))
    inventory_main = import_from_path("inventory_main", inventory_path)
    
    metrics_response = inventory_main.prometheus_metrics()
    assert "# HELP inventory_requests_total" in metrics_response
    assert "inventory_cache_hits_total" in metrics_response
    assert "inventory_cache_misses_total" in metrics_response
    assert "inventory_redis_connected" in metrics_response
    assert "inventory_mongodb_connected" in metrics_response

def test_notification_service_metrics():
    """Verify that the Notification Service /metrics endpoint outputs websocket connection count."""
    notification_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "notification-service", "main.py"))
    notification_main = import_from_path("notification_main", notification_path)
    
    metrics_response = notification_main.prometheus_metrics()
    assert "# HELP notification_requests_total" in metrics_response
    assert "notification_websockets_connected" in metrics_response
    assert "notification_events_broadcast_total" in metrics_response

def test_notification_service_ses_trigger(monkeypatch):
    """Verify that send_ses_email triggers boto3 SES send_email when AWS credentials exist."""
    notification_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "notification-service", "main.py"))
    notification_main = import_from_path("notification_main", notification_path)
    
    # Mock boto3.client
    mock_boto3_client = MagicMock()
    mock_client_instance = MagicMock()
    mock_boto3_client.return_value = mock_client_instance
    monkeypatch.setattr("boto3.client", mock_boto3_client)
    
    # Set mock environment variables to bypass AWS credential skip logic
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mock_key")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SES_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("SES_RECIPIENT_EMAIL", "recipient@example.com")
    
    # Call the email sending helper
    notification_main.send_ses_email(
        subject="Test Low Stock",
        html_body="<p>Stock is low</p>"
    )
    
    # Verify boto3 client was initialized for 'ses' and send_email was invoked
    mock_boto3_client.assert_called_once_with('ses', region_name='us-east-1')
    mock_client_instance.send_email.assert_called_once()


