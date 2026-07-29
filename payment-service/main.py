import os
import json
import time
import threading
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from kafka import KafkaConsumer, KafkaProducer

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
    order_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    user_email = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, default="Success") # Success, Failed, Refunded
    payment_method = Column(String, default="Credit Card")
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at: datetime
    class Config:
        orm_mode = True

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
DLQ_TOPIC = "payment-failures-dlq"

def handle_dlq_dispatch(order_data: dict, reason: str):
    """Sends failed transaction payloads to the Dead Letter Queue (DLQ)."""
    dlq_payload = {
        "dlq_id": f"dlq_{order_data['order_id']}_{int(time.time())}",
        "reason": reason,
        "failed_at": datetime.utcnow().isoformat(),
        "original_payload": order_data
    }
    if kafka_producer:
        try:
            kafka_producer.send(DLQ_TOPIC, value=dlq_payload)
            kafka_producer.flush()
            print(f"DLQ: Published failed transaction to Kafka topic '{DLQ_TOPIC}' successfully.")
            return
        except Exception as e:
            print(f"DLQ: Failed to publish to Kafka: {e}. Writing to fallback file.")
            
    # File-based DLQ fallback
    dlq_dir = "./logs"
    os.makedirs(dlq_dir, exist_ok=True)
    with open(f"{dlq_dir}/dlq.jsonl", "a") as f:
        f.write(json.dumps(dlq_payload) + "\n")
    print(f"DLQ SIMULATOR: Failed transaction written to {dlq_dir}/dlq.jsonl (Reason: {reason})")

def publish_payment_failure_event(order_data: dict):
    """Publishes a payment-failed event for Saga compensating transaction."""
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
        print(f"Circuit Breaker is OPEN. Payment gateway call bypassed. Forwarding Order #{order_id} to DLQ.")
        handle_dlq_dispatch(order_data, "Circuit Breaker OPEN - Gateway offline.")
        publish_payment_failure_event(order_data)
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

    # 4. If all retries failed, send to DLQ
    if not success and payment_status != "Failed":
        print(f"All {max_retries} attempts failed or timed out. Dispatching Order #{order_id} to Dead Letter Queue (DLQ).")
        handle_dlq_dispatch(order_data, "Gateway connection timeout after maximum retries.")
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
            payment_method="Credit Card"
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
            "status": txn.status
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
