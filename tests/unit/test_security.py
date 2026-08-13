import pytest
from datetime import datetime, timedelta
import jwt

SECRET = "smartretailx-secret-key"

def generate_mock_jwt(username, role, expires_in_seconds=60):
    payload = {
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(seconds=expires_in_seconds)
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

def decode_and_validate_jwt(token):
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token signature has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid credentials token")

def test_jwt_validation_flow():
    """Unit Test: Verify JWT creation, signing, and decoding structure."""
    token = generate_mock_jwt("test_user", "Customer")
    decoded = decode_and_validate_jwt(token)
    assert decoded["username"] == "test_user"
    assert decoded["role"] == "Customer"

def test_jwt_expired_token():
    """Unit Test: Verify rejection of expired credentials tokens."""
    # Generate token already expired by 10 seconds
    token = generate_mock_jwt("test_user", "Customer", expires_in_seconds=-10)
    with pytest.raises(ValueError, match="Token signature has expired"):
        decode_and_validate_jwt(token)

def test_jwt_tampered_signature():
    """Unit Test: Verify signature verification fails on tampered structures."""
    token = generate_mock_jwt("test_user", "Customer")
    tampered_token = token + "modified"
    with pytest.raises(ValueError, match="Invalid credentials token"):
        decode_and_validate_jwt(tampered_token)
