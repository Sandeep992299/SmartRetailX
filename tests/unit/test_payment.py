import pytest
import time

class SimpleCircuitBreaker:
    def __init__(self, failure_threshold=2, recovery_time=1):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_failure_time = None

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.last_failure_time = time.time()

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def can_execute(self):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_time:
                self.state = "HALF-OPEN"
                return True
            return False
        return True

def calculate_payment(amount, discount_rate=0.0, tax_rate=0.08):
    discounted = amount * (1.0 - discount_rate)
    tax = discounted * tax_rate
    return round(discounted + tax, 2)

def test_payment_calculations():
    """Unit Test: Verify correct calculations of discounts and local taxes on payments."""
    # Baseline check: $100 base with 8% tax
    assert calculate_payment(100.0) == 108.00
    # Coupon discount: $100 base with 10% discount and 8% tax
    assert calculate_payment(100.0, discount_rate=0.10) == 97.20

def test_payment_circuit_breaker():
    """Unit Test: Verify state transitions of the Payment circuit breaker protection."""
    cb = SimpleCircuitBreaker(failure_threshold=2, recovery_time=1)
    
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True
    
    # First failure
    cb.record_failure()
    assert cb.state == "CLOSED"
    
    # Second failure triggers OPEN
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.can_execute() is False
    
    # Test recovery time
    time.sleep(1.1)
    assert cb.can_execute() is True
    assert cb.state == "HALF-OPEN"
    
    cb.record_success()
    assert cb.state == "CLOSED"
