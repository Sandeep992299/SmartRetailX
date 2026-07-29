import os
import pytest
import requests

GATEWAY_URL = os.getenv("TEST_GATEWAY_URL", "http://localhost:8000/api/v1")
USER_SERVICE_URL = os.getenv("TEST_USER_URL", "http://localhost:8001")

# Use a static unique email prefix for testing
TEST_EMAIL = "test_user_pytest@smartretailx.com"
TEST_PASSWORD = "TestPassword123!"
TEST_USERNAME = "pytest_user"

@pytest.fixture(scope="session")
def service_token():
    """Sign up and login a test user to obtain a valid Bearer token."""
    # Step 1: Sign up
    signup_url = f"{USER_SERVICE_URL}/users/signup"
    try:
        requests.post(signup_url, json={
            "username": TEST_USERNAME,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "role": "Customer"
        })
    except requests.exceptions.ConnectionError:
        pytest.skip("User service not reachable, skipping integration test.")
        
    # Step 2: Login
    login_url = f"{USER_SERVICE_URL}/users/login"
    res = requests.post(login_url, json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert res.status_code == 200
    return res.json()["access_token"]

def test_gateway_health():
    """Verify that the central API Gateway health endpoint is functioning."""
    try:
        res = requests.get("http://localhost:8000/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running locally.")

def test_get_products():
    """Verify products catalogue list is reachable through Gateway routing."""
    try:
        res = requests.get(f"{GATEWAY_URL}/products")
        assert res.status_code == 200
        assert len(res.json()) > 0
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running.")

def test_create_order_unauthorized():
    """Placing an order without authorization headers should fail with 401."""
    try:
        res = requests.post(f"{GATEWAY_URL}/orders", json={
            "items": [{"product_id": 1, "product_name": "Test", "price": 10.0, "quantity": 1}]
        })
        assert res.status_code == 401
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running.")

def test_create_order_authorized(service_token):
    """Verify that authorized checkout places orders and triggers events."""
    try:
        headers = {"Authorization": f"Bearer {service_token}"}
        res = requests.post(f"{GATEWAY_URL}/orders", headers=headers, json={
            "items": [
                {"product_id": 1, "product_name": "Wireless Noise-Canceling Headphones", "price": 199.99, "quantity": 1}
            ]
        })
        assert res.status_code == 201
        order = res.json()
        assert order["status"] == "Pending"
        assert order["total_amount"] == 199.99
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running.")
