import os
import json
import time
import threading
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from kafka import KafkaConsumer, KafkaProducer
from aws_xray_sdk.core import xray_recorder, patch_all
from starlette.middleware.base import BaseHTTPMiddleware

# Configuration
# By default, use PostgreSQL. If POSTGRES_DB is not defined or connection fails, fallback to SQLite.
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres123")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "smartretailx_payments")

# Fallback URI
SQLITE_DB_URL = "sqlite:///./payments.db"
DEFAULT_DB_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ORDER_EVENTS_TOPIC = os.getenv("ORDER_EVENTS_TOPIC", "order-events")
PAYMENT_EVENTS_TOPIC = os.getenv("PAYMENT_EVENTS_TOPIC", "payment-events")

import random
import requests

def invoke_auth_with_retry(url, payload, max_retries=5):
    """Illustrative authentication service invocation wrapper with exponential backoff and jitter."""
    base_delay = 1.0  # Initial delay in seconds
    max_delay = 16.0  # Cap on backoff delay
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=3.0)
            if response.status_code == 200:
                return response.json()
            elif response.status_code in [429, 500, 503]:
                print(f"Transient error {response.status_code}. Retrying...")
            else:
                response.raise_for_status()
        except requests.RequestException as e:
            print(f"Network error during attempt {attempt}: {e}")
            
        delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
        jitter = random.uniform(0, 0.5 * delay)
        sleep_time = delay + jitter
        print(f"Backing off for {sleep_time:.2f} seconds...")
        time.sleep(sleep_time)
        
    raise Exception("Max retries exceeded: Service invocation failed.")

class CircuitBreaker:
    """Custom Circuit Breaker pattern implementation to prevent cascading failures."""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_state_change = time.time()

    def __call__(self, func, *args, **kwargs):
        now = time.time()
        
        # If open, check if the cool-down/recovery timeout has expired
        if self.state == "OPEN":
            if now - self.last_state_change > self.recovery_timeout:
                self.state = "HALF-OPEN"
                self.last_state_change = now
                print("Circuit Breaker transitioned to HALF-OPEN. Testing downstream health...")
            else:
                print("Circuit Breaker is OPEN. Failing fast immediately.")
                raise Exception("CircuitBreakerOpenException: Downstream service temporarily unavailable.")

        try:
            result = func(*args, **kwargs)
            # If successful in HALF-OPEN state, close the circuit
            if self.state == "HALF-OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                self.last_state_change = now
                print("Circuit Breaker transitioned to CLOSED. Service restored.")
            return result
        except Exception as e:
            self.failure_count += 1
            print(f"Service invocation failed ({e}). Failure count: {self.failure_count}")
            
            if self.state in ["CLOSED", "HALF-OPEN"] and self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_state_change = now
                print("Circuit Breaker tripped to OPEN! Blocking outbound calls.")
            
            raise e

# Setup SQLAlchemy
# Use check_same_thread for SQLite fallback
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") or "sqlite" in DATABASE_URL else {}
try:
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
    # Test connection
    engine.connect()
    print("Payment Service successfully connected to SQL database (PostgreSQL/SQLite)!")
except Exception as e:
    print(f"Failed to connect to configured DB ({e}). Falling back to SQLite local database.")
    DATABASE_URL = SQLITE_DB_URL
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models (ACID Compliant Payment Transactions Schema)
class TransactionDB(Base):
    __tablename__ = "payment_transactions"
    id = Column(Integer, primary_key=True, index=True)
    transaction_uuid = Column(String, unique=True, nullable=False, index=True)
    order_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False)
    user_email = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, default="Success") # Success, Failed, Refunded
    payment_method = Column(String, default="Credit Card")
    ip_address = Column(String, default="unknown-ip")
    is_fraud = Column(Boolean, default=False)
    fraud_reason = Column(String, nullable=True)
    correlation_id = Column(String, default="unknown-correlation")
    created_at = Column(DateTime, default=datetime.utcnow)


# Force recreate database file locally to apply schema migrations cleanly
if os.path.exists("./payments.db"):
    try:
        os.remove("./payments.db")
        print("Payment Service: Deleted existing payments.db to apply new database schema migrations.")
    except Exception as e:
        print(f"Payment Service: Could not delete payments.db: {e}")

Base.metadata.create_all(bind=engine)



# Kafka Producer Client
kafka_producer = None
try:
    kafka_producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        request_timeout_ms=5000,
        max_block_ms=3000
    )
    print("Payment Service successfully connected to Kafka Producer!")
except Exception as e:
    print(f"Payment Service Kafka Producer unavailable ({e}). Using simulation mode.")

# Pydantic Schemas
class TransactionResponse(BaseModel):
    id: int
    transaction_uuid: str
    order_id: int
    user_id: int
    user_email: str
    amount: float
    status: str
    payment_method: str
    ip_address: str
    is_fraud: bool
    fraud_reason: Optional[str] = None
    correlation_id: str
    created_at: datetime

    class Config:
        from_attributes = True

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FastAPI Initialization
app = FastAPI(
    title="SmartRetailX Payment Service",
    description="Microservice responsible for processing order checkout payments and storing records securely in SQL.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AWS X-Ray Configuration
_xray_daemon_host = os.getenv("AWS_XRAY_DAEMON_ADDRESS", "127.0.0.1")
xray_recorder.configure(service="payment-service", daemon_address=f"{_xray_daemon_host}:2000")
patch_all()

class _XRayMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        segment = xray_recorder.begin_segment(f"{request.method} {request.url.path}")
        try:
            response = await call_next(request)
            segment.put_http_meta("response", {"status": response.status_code})
            return response
        except Exception as exc:
            segment.add_exception(exc, [])
            raise
        finally:
            xray_recorder.end_segment()

app.add_middleware(_XRayMiddleware)

# Payment Service metrics storage
payment_requests_total = {}
payment_latency_sum = 0.0
payment_latency_count = 0
payments_processed_total = {"Success": 0, "Failed": 0}

from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.middleware("http")
async def payment_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    global payment_latency_sum, payment_latency_count
    payment_latency_sum += duration
    payment_latency_count += 1
    
    if not request.url.path.startswith(("/payments/healthz", "/metrics")):
        key = (request.method, request.url.path, response.status_code)
        payment_requests_total[key] = payment_requests_total.get(key, 0) + 1
        
    return response

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_time=10):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_state_change = time.time()

    def can_execute(self):
        if self.state == "OPEN":
            if time.time() - self.last_state_change > self.recovery_time:
                self.state = "HALF-OPEN"
                self.last_state_change = time.time()
                print("Circuit Breaker transitioned to HALF-OPEN. Testing downstream gateway...")
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        if self.state != "CLOSED":
            print("Circuit Breaker transitioned to CLOSED. Gateway is healthy.")
            self.state = "CLOSED"
            self.last_state_change = time.time()

    def record_failure(self):
        self.failure_count += 1
        print(f"Circuit Breaker failure recorded. Count: {self.failure_count}/{self.failure_threshold}")
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                print(f"Circuit Breaker transitioned to OPEN. Restricting gateway calls for {self.recovery_time} seconds.")
                self.state = "OPEN"
                self.last_state_change = time.time()

payment_circuit_breaker = CircuitBreaker()
DLT_TOPIC = "payment-failures-dlt"

def handle_dlt_dispatch(order_data: dict, reason: str):
    """Sends failed transaction payloads to the Dead Letter Topic (DLT)."""
    dlt_payload = {
        "dlt_id": f"dlt_{order_data['order_id']}_{int(time.time())}",
        "reason": reason,
        "failed_at": datetime.utcnow().isoformat(),
        "original_payload": order_data
    }
    if kafka_producer:
        try:
            kafka_producer.send(DLT_TOPIC, value=dlt_payload)
            kafka_producer.flush()
            print(f"DLT: Published failed transaction to Kafka topic '{DLT_TOPIC}' successfully.")
            return
        except Exception as e:
            print(f"DLT: Failed to publish to Kafka: {e}. Writing to fallback file.")
            
    # File-based DLT fallback
    dlt_dir = "./logs"
    os.makedirs(dlt_dir, exist_ok=True)
    with open(f"{dlt_dir}/dlt.jsonl", "a") as f:
        f.write(json.dumps(dlt_payload) + "\n")
    print(f"DLT SIMULATOR: Failed transaction written to {dlt_dir}/dlt.jsonl (Reason: {reason})")

def publish_payment_failure_event(order_data: dict):
    """Publishes a payment-failed event for Saga compensating transaction."""
    # Increment metric
    global payments_processed_total
    payments_processed_total["Failed"] = payments_processed_total.get("Failed", 0) + 1

    event_payload = {
        "event_id": f"evt_fail_{order_data['order_id']}_{int(time.time())}",
        "event_type": "payment-failed",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "transaction_uuid": f"txn_failed_{order_data['order_id']}",
            "order_id": order_data["order_id"],
            "user_id": order_data["user_id"],
            "user_email": order_data["user_email"],
            "amount": order_data["total_amount"],
            "status": "Failed"
        }
    }
    if kafka_producer:
        try:
            kafka_producer.send(PAYMENT_EVENTS_TOPIC, value=event_payload)
            kafka_producer.flush()
            print(f"Compensating payment-failed event published to '{PAYMENT_EVENTS_TOPIC}'")
            return
        except Exception as e:
            print(f"Failed publishing compensating event to Kafka: {e}")
            
    # Simulation fallback
    sim_log_dir = "./logs"
    os.makedirs(sim_log_dir, exist_ok=True)
    with open(f"{sim_log_dir}/event_bus.jsonl", "a") as f:
        f.write(json.dumps(event_payload) + "\n")

def call_external_payment_gateway(amount: float):
    """Simulates a call to a third-party payment gateway with a 5s timeout limit."""
    # Simulate a network timeout scenario (takes 6 seconds, which exceeds our 5-second limit)
    if amount == 888.00:
        print("GATEWAY: Simulated connection latency starting (888.00 triggers timeout)...")
        time.sleep(6) # Exceeds 5s timeout
        raise TimeoutError("Third-party payment gateway connection timed out.")
    
    # Normal latency simulation
    time.sleep(0.5)
    
    # Insufficient funds business error simulation
    if amount == 999.00:
        raise ValueError("Third-party payment processor rejected transaction (Insufficient Funds).")
        
    return "Success"

def process_and_persist_payment(order_data: dict):
    """Processes mock payment details and commits transaction to the SQL Database under ACID principles."""
    db = SessionLocal()
    
    order_id = order_data["order_id"]
    user_id = order_data["user_id"]
    email = order_data["user_email"]
    amount = order_data["total_amount"]
    
    # 1. Idempotency Check
    exists = db.query(TransactionDB).filter(TransactionDB.order_id == order_id).first()
    if exists:
        print(f"Transaction for order {order_id} already exists. Skipping.")
        db.close()
        return

    # 2. Circuit Breaker Check
    if not payment_circuit_breaker.can_execute():
        print(f"Circuit Breaker is OPEN. Payment gateway call bypassed. Forwarding Order #{order_id} to DLT.")
        handle_dlt_dispatch(order_data, "Circuit Breaker OPEN - Gateway offline.")
        publish_payment_failure_event(order_data)
        db.close()
        return

    # 2b. Fraud Detection Check
    ip_addr = order_data.get("ip_address", "unknown-ip")
    is_fraud = (amount == 777.00) or (ip_addr == "190.115.18.22")
    fraud_reason = None
    if is_fraud:
        print(f"FRAUD DETECTED: High-risk order #{order_id} flagged (IP: {ip_addr}). Bypassing gateway and triggering rollback.")
        payment_status = "Failed"
        fraud_reason = "Suspicious billing signature or blacklisted proxy IP address."
        # Directly persist fraud status and trigger Saga compensating rollback
        try:
            transaction_uuid = f"txn_fraud_{order_id}_{int(time.time())}"
            transaction = TransactionDB(
                transaction_uuid=transaction_uuid,
                order_id=order_id,
                user_id=user_id,
                user_email=email,
                amount=amount,
                status="Failed",
                payment_method="Credit Card",
                ip_address=ip_addr,
                is_fraud=True,
                fraud_reason=fraud_reason,
                correlation_id=order_data.get("correlation_id", "unknown-correlation")
            )
            db.add(transaction)
            db.commit()
            db.refresh(transaction)
            print(f"Fraud Transaction persisted: UUID {transaction_uuid}")
            publish_payment_event(transaction)
        except Exception as e:
            db.rollback()
            print(f"Error persisting fraud transaction to SQL: {e}")
        finally:
            db.close()
        return

    print(f"Processing payment for Order #{order_id} (Amount: ${amount}) for user {email}")
    
    # 3. Call gateway with Retries and Timeout
    max_retries = 3
    retry_delay = 1.0
    payment_status = "Failed"
    success = False
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Payment gateway call attempt {attempt}/{max_retries}...")
            # call_external_payment_gateway will sleep 6s and raise TimeoutError for 888.00
            status = call_external_payment_gateway(amount)
            
            # If successful
            payment_status = status
            success = True
            payment_circuit_breaker.record_success()
            break
        except TimeoutError as te:
            print(f"Attempt {attempt} failed: Timeout ({te})")
            payment_circuit_breaker.record_failure()
        except Exception as e:
            print(f"Attempt {attempt} failed: Error ({e})")
            payment_circuit_breaker.record_failure()
            # If it's a hard business logic failure (999.00), don't retry
            if amount == 999.00:
                payment_status = "Failed"
                break
                
        if attempt < max_retries:
            backoff = retry_delay * (2 ** (attempt - 1))
            print(f"Retrying in {backoff} seconds...")
            time.sleep(backoff)

    # 4. If all retries failed, send to DLT
    if not success and payment_status != "Failed":
        print(f"All {max_retries} attempts failed or timed out. Dispatching Order #{order_id} to Dead Letter Topic (DLT).")
        handle_dlt_dispatch(order_data, "Gateway connection timeout after maximum retries.")
        publish_payment_failure_event(order_data)
        db.close()
        return

    # 5. Persist to ACID Database
    try:
        transaction_uuid = f"txn_{order_id}_{int(time.time())}"
        transaction = TransactionDB(
            transaction_uuid=transaction_uuid,
            order_id=order_id,
            user_id=user_id,
            user_email=email,
            amount=amount,
            status=payment_status,
            payment_method="Credit Card",
            ip_address=ip_addr,
            is_fraud=False,
            fraud_reason=None,
            correlation_id=order_data.get("correlation_id", "unknown-correlation")
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        print(f"Transaction saved in SQL Database: ID {transaction.id}, UUID {transaction_uuid}, Status: {payment_status}")
        
        # Publish payment status event to Kafka
        publish_payment_event(transaction)
    except Exception as e:
        db.rollback()
        print(f"Error persisting transaction to SQL: {e}")
    finally:
        db.close()

def publish_payment_event(txn: TransactionDB):
    """Publishes payment event to Kafka broker."""
    # Increment metric
    global payments_processed_total
    status_label = "Success" if txn.status == "Success" else "Failed"
    payments_processed_total[status_label] = payments_processed_total.get(status_label, 0) + 1

    event_payload = {
        "event_id": f"evt_{txn.transaction_uuid}",
        "event_type": "payment-settled" if txn.status == "Success" else "payment-failed",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "transaction_uuid": txn.transaction_uuid,
            "order_id": txn.order_id,
            "user_id": txn.user_id,
            "user_email": txn.user_email,
            "amount": txn.amount,
            "status": txn.status,
            "ip_address": txn.ip_address,
            "is_fraud": txn.is_fraud,
            "fraud_reason": txn.fraud_reason,
            "correlation_id": txn.correlation_id
        }
    }
    
    if kafka_producer:
        try:
            kafka_producer.send(PAYMENT_EVENTS_TOPIC, value=event_payload)
            kafka_producer.flush()
            print(f"Payment status event published to topic '{PAYMENT_EVENTS_TOPIC}'")
            return
        except Exception as e:
            print(f"Failed publishing payment event to Kafka: {e}")
            
    # Simulation fallback
    sim_log_dir = "./logs"
    os.makedirs(sim_log_dir, exist_ok=True)
    with open(f"{sim_log_dir}/event_bus.jsonl", "a") as f:
        f.write(json.dumps(event_payload) + "\n")
    print(f"SIMULATOR: Event '{event_payload['event_type']}' written to {sim_log_dir}/event_bus.jsonl")

# Background thread to consume Order Checkout Events
def run_kafka_consumer():
    print("Starting background Order Events Kafka Consumer loop...")
    while True:
        try:
            consumer = KafkaConsumer(
                ORDER_EVENTS_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='payment-service-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            print(f"Payment Service Kafka Consumer subscribed to topic '{ORDER_EVENTS_TOPIC}' successfully.")
            for message in consumer:
                event = message.value
                print(f"Consumed order event from Kafka: {event.get('event_type')}")
                if event.get("event_type") == "order-created":
                    process_and_persist_payment(event["data"])
        except Exception as e:
            print(f"Error in Kafka consumer loop: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

# Background file-watcher simulator for local runs without Kafka
def run_file_simulator():
    print("Starting background File Simulator watcher...")
    sim_log = "./logs/event_bus.jsonl"
    processed_events = set()
    while True:
        if os.path.exists(sim_log):
            try:
                with open(sim_log, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        event_id = event.get("event_id")
                        if event_id not in processed_events:
                            processed_events.add(event_id)
                            # Only process checkout if it's order-created
                            if event.get("event_type") == "order-created":
                                print(f"SIMULATOR: Detected new event: {event.get('event_type')}")
                                process_and_persist_payment(event["data"])
            except Exception as e:
                print(f"Simulator watcher reading error: {e}")
        time.sleep(1)

@app.on_event("startup")
def start_background_workers():
    # Run Kafka consumer in a separate thread
    kafka_thread = threading.Thread(target=run_kafka_consumer, daemon=True)
    kafka_thread.start()
    
    # Also run file simulator to watch event_bus.jsonl locally
    sim_thread = threading.Thread(target=run_file_simulator, daemon=True)
    sim_thread.start()

# API Endpoints
@app.get("/payments/transactions", response_model=List[TransactionResponse])
def get_transactions(
    x_user_role: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Check permissions
    if x_user_role in ["Admin", "Manager"]:
        return db.query(TransactionDB).all()
    else:
        return db.query(TransactionDB).filter(TransactionDB.user_id == int(x_user_id)).all()

@app.get("/payments/healthz")
def healthz():
    return {
        "status": "healthy",
        "database_url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL, # redact password
        "kafka_connected": kafka_producer is not None
    }

@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    global payment_latency_sum, payment_latency_count, payments_processed_total
    lines = []
    
    # Total request counts
    lines.append("# HELP payment_requests_total Total number of HTTP requests handled by the Payment Service.")
    lines.append("# TYPE payment_requests_total counter")
    for (method, path, status_code), count in payment_requests_total.items():
        lines.append(f'payment_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        
    # Latency metric
    lines.append("# HELP payment_request_latency_seconds_sum Sum of request processing duration in seconds.")
    lines.append("# TYPE payment_request_latency_seconds_sum counter")
    lines.append(f"payment_request_latency_seconds_sum {payment_latency_sum}")
    
    lines.append("# HELP payment_request_latency_seconds_count Count of request processing durations.")
    lines.append("# TYPE payment_request_latency_seconds_count counter")
    lines.append(f"payment_request_latency_seconds_count {payment_latency_count}")

    # Transactions processed count
    lines.append("# HELP payments_processed_total Total number of processed payments by status.")
    lines.append("# TYPE payments_processed_total counter")
    for status_label, count in payments_processed_total.items():
        lines.append(f'payments_processed_total{{status="{status_label}"}} {count}')

    # Circuit breaker state
    # 0 = CLOSED, 1 = HALF-OPEN, 2 = OPEN
    cb_state_val = 0
    if payment_circuit_breaker.state == "HALF-OPEN":
        cb_state_val = 1
    elif payment_circuit_breaker.state == "OPEN":
        cb_state_val = 2
    lines.append("# HELP payment_circuit_breaker_state Current state of the payment gateway circuit breaker (0=CLOSED, 1=HALF-OPEN, 2=OPEN).")
    lines.append("# TYPE payment_circuit_breaker_state gauge")
    lines.append(f"payment_circuit_breaker_state {cb_state_val}")

    # Connections status
    lines.append("# HELP payment_kafka_connected Status of Kafka producer connection.")
    lines.append("# TYPE payment_kafka_connected gauge")
    lines.append(f"payment_kafka_connected {1 if kafka_producer is not None else 0}")
    
    return "\n".join(lines)
