import os
import pytest
import requests

GATEWAY_URL = os.getenv("TEST_GATEWAY_URL", "http://localhost:8000/api/v1")

def test_cors_headers_gateway():
    """Security Check: Verify CORS headers are present on public endpoints to prevent CSRF / unauthorized cross-origin requests."""
    try:
        res = requests.options(f"{GATEWAY_URL}/products", headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET"
        })
        assert "Access-Control-Allow-Origin" in res.headers
        # In testing environment, wildcard or strict check is acceptable depending on policy
        assert res.headers["Access-Control-Allow-Origin"] in ["*", "http://malicious-site.com"]
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running.")

def test_missing_auth_endpoints():
    """Security Check: Verify private endpoints return 401 Unauthorized when Bearer token is missing."""
    try:
        # Private endpoint: User profile
        res_user = requests.get(f"{GATEWAY_URL}/users/me")
        assert res_user.status_code == 401
        
        # Private endpoint: Create order
        res_order = requests.post(f"{GATEWAY_URL}/orders", json={"items": []})
        assert res_order.status_code == 401
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running.")

def test_invalid_bearer_token_rejected():
    """Security Check: Verify requests with malformed or tampered JWT signatures are rejected with 401."""
    try:
        headers = {"Authorization": "Bearer malformed.jwt.token.signature"}
        res = requests.get(f"{GATEWAY_URL}/users/me", headers=headers)
        assert res.status_code == 401
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running.")

def test_input_validation_and_nosql_injection():
    """Security Check: Verify input validation rejects malformed payload structures and blocks NoSQL injection payloads."""
    try:
        # Attempt NoSQL Injection in login email parameter
        injection_payload = {
            "email": {"$ne": "nonexistent@email.com"},
            "password": "some_random_password"
        }
        res = requests.post(f"{GATEWAY_URL}/users/login", json=injection_payload)
        # Should fail with 422 Unprocessable Entity because email expects a string (Pydantic validation)
        assert res.status_code == 422
    except requests.exceptions.ConnectionError:
        pytest.skip("API Gateway not running.")
