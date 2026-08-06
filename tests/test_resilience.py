import sys
import os
import pytest
import time
from unittest.mock import MagicMock

# ------------------------------------------------------------
# Zero-dependency Python Mocking wrapper
# ------------------------------------------------------------
# Mock sqlalchemy
sqlalchemy_mock = MagicMock()
sys.modules['sqlalchemy'] = sqlalchemy_mock

ext_mock = MagicMock()
class MockBase:
    metadata = MagicMock()

ext_mock.declarative_base.return_value = MockBase
sys.modules['sqlalchemy.ext.declarative'] = ext_mock

orm_mock = MagicMock()
sys.modules['sqlalchemy.orm'] = orm_mock

# Mock kafka
sys.modules['kafka'] = MagicMock()

# Mock fastapi
sys.modules['fastapi'] = MagicMock()
sys.modules['fastapi.responses'] = MagicMock()
sys.modules['fastapi.middleware.cors'] = MagicMock()

# Add payment-service directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "payment-service")))

# Now import modules under test
from main import CircuitBreaker, call_external_payment_gateway

def test_circuit_breaker_logic():
    """Verify that the Circuit Breaker transition logic behaves correctly under failure states."""
    # Create a circuit breaker with 2-failure threshold and 1s recovery
    cb = CircuitBreaker(failure_threshold=2, recovery_time=1)
    
    # 1. Closed state by default
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True
    
    # 2. Record one failure (remains closed)
    cb.record_failure()
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True
    
    # 3. Record second failure (transitions to OPEN)
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.can_execute() is False
    
    # 4. Check that it blocks execution before recovery time expires
    time.sleep(0.1)
    assert cb.can_execute() is False
    
    # 5. After recovery time, should transition to HALF-OPEN upon checking
    time.sleep(1.0)
    assert cb.can_execute() is True
    assert cb.state == "HALF-OPEN"
    
    # 6. Record success (transitions back to CLOSED)
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True

def test_external_gateway_latency_simulation():
    """Verify that the simulated external payment gateway fires correct errors depending on amount inputs."""
    # Normal transaction success
    assert call_external_payment_gateway(50.00) == "Success"
    
    # Timeout amount triggers TimeoutError
    with pytest.raises(TimeoutError):
        call_external_payment_gateway(888.00)
        
    # Insufficient funds triggers ValueError
    with pytest.raises(ValueError):
        call_external_payment_gateway(999.00)
