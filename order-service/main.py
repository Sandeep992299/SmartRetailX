import os
import json
import time
import threading
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from pymongo import MongoClient
from kafka import KafkaProducer, KafkaConsumer
from aws_xray_sdk.core import xray_recorder, patch_all
from aws_xray_sdk.core.async_context import AsyncContext

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = "smartretailx_orders"

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ORDER_EVENTS_TOPIC = os.getenv("ORDER_EVENTS_TOPIC", "order-events")

# Setup PyMongo
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = mongo_client[DATABASE_NAME]
    mongo_client.server_info()
    print("Order Service connected to MongoDB database successfully!")
except Exception as e:
    print(f"Order Service failed to connect to MongoDB ({e}). Running in offline simulation mode.")
    db = None

# Kafka Client Initialization
kafka_producer = None
try:
    kafka_producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        request_timeout_ms=5000,
        max_block_ms=3000
    )
    print("Order Service successfully connected to Kafka Producer!")
except Exception as e:
    print(f"Kafka Producer connection failed ({e}). Running in localized mode (events will be simulated).")

# Pydantic Schemas
class OrderItemBase(BaseModel):
    product_id: str # modified to string as MongoDB uses string ObjectIds for products
    product_name: str
    price: float
    quantity: int

    @validator("price")
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Price must be greater than zero")
        return v

    @validator("quantity")
    def quantity_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v

class OrderCreate(BaseModel):
    items: List[OrderItemBase]

class OrderResponse(BaseModel):
    id: str
    user_id: str
    user_email: str
    total_amount: float
    status: str
    created_at: str
    items: List[OrderItemBase]
    ip_address: Optional[str] = "unknown-ip"
    correlation_id: Optional[str] = "unknown-correlation"


# FastAPI Initialization
app = FastAPI(
    title="SmartRetailX Order Service",
    description="Microservice responsible for creating and retrieving orders in MongoDB, publishing checkout events to Apache Kafka.",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AWS X-Ray Configuration
_xray_daemon_host = os.getenv("XRAY_DAEMON_HOST", "127.0.0.1")
xray_recorder.configure(
    service="order-service",
    daemon_address=f"{_xray_daemon_host}:2000",
    context=AsyncContext()
)
patch_all()

class XRayMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        segment_name = f"{scope.get('method', 'GET')} {scope.get('path', '/')}"
        segment = xray_recorder.begin_segment(segment_name)
        segment.put_http_meta("request", {
            "url": scope.get("path", "/"),
            "method": scope.get("method", "GET")
        })

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status = message.get("status")
                segment.put_http_meta("response", {"status": status})
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            segment.add_exception(exc, [])
            raise
        finally:
            xray_recorder.end_segment()

app.add_middleware(XRayMiddleware)

# Order Service metrics storage
order_requests_total = {}
order_latency_sum = 0.0
order_latency_count = 0
orders_created_total = 0

from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.middleware("http")
async def order_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    global order_latency_sum, order_latency_count
    order_latency_sum += duration
    order_latency_count += 1
    
    if not request.url.path.startswith(("/orders/healthz", "/metrics")):
        key = (request.method, request.url.path, response.status_code)
        order_requests_total[key] = order_requests_total.get(key, 0) + 1
        
    return response

def publish_order_event(event_type: str, order_doc: dict):
    """Utility to publish events to Kafka topic with graceful simulation fallback."""
    event_payload = {
        "event_id": f"evt_{order_doc['id']}_{int(time.time())}",
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "order_id": order_doc["id"],
            "user_id": order_doc["user_id"],
            "user_email": order_doc["user_email"],
            "total_amount": order_doc["total_amount"],
            "status": order_doc["status"],
            "correlation_id": order_doc.get("correlation_id", "unknown-correlation"),
            "items": [
                {
                    "product_id": item["product_id"],
                    "product_name": item["product_name"],
                    "price": item["price"],
                    "quantity": item["quantity"]
                } for item in order_doc["items"]
            ]
        }
    }
    
    if kafka_producer:
        try:
            kafka_producer.send(ORDER_EVENTS_TOPIC, value=event_payload)
            kafka_producer.flush()
            print(f"Event '{event_type}' published to Kafka topic '{ORDER_EVENTS_TOPIC}'")
            return
        except Exception as e:
            print(f"Error writing to Kafka: {e}. Falling back to simulation.")

    # Simulation fallback (writes to a local log file)
    sim_log_dir = "./logs"
    os.makedirs(sim_log_dir, exist_ok=True)
    with open(f"{sim_log_dir}/event_bus.jsonl", "a") as f:
        f.write(json.dumps(event_payload) + "\n")
    print(f"SIMULATOR: Event '{event_type}' written to {sim_log_dir}/event_bus.jsonl")

# Helper to format Mongo docs
def format_order_doc(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "user_id": doc["user_id"],
        "user_email": doc["user_email"],
        "total_amount": doc["total_amount"],
        "status": doc.get("status", "Pending"),
        "created_at": doc.get("created_at", ""),
        "items": doc["items"],
        "ip_address": doc.get("ip_address", "unknown-ip"),
        "correlation_id": doc.get("correlation_id", "unknown-correlation")
    }

# Routes
@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    request: Request,
    order_in: OrderCreate,
    x_user_id: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_forwarded_for: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None)
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized - User session missing")
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    try:
        total = sum(item.price * item.quantity for item in order_in.items)
        items_list = [item.dict() for item in order_in.items]
        
        order_doc = {
            "user_id": x_user_id,
            "user_email": x_user_email or "unknown@smartretailx.com",
            "total_amount": total,
            "status": "Pending",
            "created_at": datetime.utcnow().isoformat(),
            "items": items_list,
            "ip_address": x_forwarded_for or (request.client.host if request.client else "unknown-ip"),
            "correlation_id": x_correlation_id or f"corr_fallback_{int(time.time())}"
        }
        
        result = db.orders.insert_one(order_doc)
        order_doc["_id"] = result.inserted_id
        
        # Increment metric
        global orders_created_total
        orders_created_total += 1
        
        formatted = format_order_doc(order_doc)
        
        # Asynchronously trigger Kafka workflow
        publish_order_event("order-created", formatted)
        
        return formatted
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Order creation failed: {e}")

@app.get("/orders", response_model=List[OrderResponse])
def get_orders(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if db is None:
        return []
        
    # If role is Admin or Manager, show all orders. Otherwise show user's own orders.
    if x_user_role in ["Admin", "Manager"]:
        orders_cursor = db.orders.find()
    else:
        orders_cursor = db.orders.find({"user_id": x_user_id})
        
    return [format_order_doc(o) for o in orders_cursor]

@app.get("/orders/healthz")
def healthz():
    return {
        "status": "healthy",
        "kafka_connected": kafka_producer is not None,
        "mongodb_connected": db is not None
    }

@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: str,
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    from bson import ObjectId
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    db_order = db.orders.find_one({"_id": oid})
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # RBAC logic: verify access ownership or staff authorization
    if db_order["user_id"] != x_user_id and x_user_role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this order")
        
    return format_order_doc(db_order)

@app.put("/orders/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: str,
    status_update: dict,
    x_user_role: Optional[str] = Header(None)
):
    if x_user_role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden: Staff permission required")
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    new_status = status_update.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing status field")
        
    from bson import ObjectId
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    result = db.orders.update_one({"_id": oid}, {"$set": {"status": new_status}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
        
    db_order = db.orders.find_one({"_id": oid})
    formatted = format_order_doc(db_order)
    
    # Publish event
    publish_order_event("order-status-changed", formatted)
    return formatted

@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    global order_latency_sum, order_latency_count, orders_created_total
    lines = []
    
    # Total request counts
    lines.append("# HELP order_requests_total Total number of HTTP requests handled by the Order Service.")
    lines.append("# TYPE order_requests_total counter")
    for (method, path, status_code), count in order_requests_total.items():
        lines.append(f'order_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        
    # Latency metric
    lines.append("# HELP order_request_latency_seconds_sum Sum of request processing duration in seconds.")
    lines.append("# TYPE order_request_latency_seconds_sum counter")
    lines.append(f"order_request_latency_seconds_sum {order_latency_sum}")
    
    lines.append("# HELP order_request_latency_seconds_count Count of request processing durations.")
    lines.append("# TYPE order_request_latency_seconds_count counter")
    lines.append(f"order_request_latency_seconds_count {order_latency_count}")

    # Orders created count
    lines.append("# HELP orders_created_total Total number of checkout orders created.")
    lines.append("# TYPE orders_created_total counter")
    lines.append(f"orders_created_total {orders_created_total}")

    # Connections status
    lines.append("# HELP order_mongodb_connected Status of MongoDB connection.")
    lines.append("# TYPE order_mongodb_connected gauge")
    lines.append(f"order_mongodb_connected {1 if db is not None else 0}")

    lines.append("# HELP order_kafka_connected Status of Kafka producer connection.")
    lines.append("# TYPE order_kafka_connected gauge")
    lines.append(f"order_kafka_connected {1 if kafka_producer is not None else 0}")
    
    return "\n".join(lines)

def handle_payment_event(payment_data: dict, status: str):
    """Updates order status in MongoDB when payment event occurs."""
    order_id = payment_data.get("order_id")
    if not order_id or db is None:
        return
    from bson import ObjectId
    try:
        oid = ObjectId(order_id)
        db.orders.update_one({"_id": oid}, {"$set": {"status": status}})
        print(f"Order Service: Updated Order #{order_id} status to '{status}' in database.")
    except Exception as e:
        print(f"Order Service: Error updating status for Order #{order_id}: {e}")

def run_kafka_consumer():
    """Listens to payment-events and updates order status."""
    PAYMENT_EVENTS_TOPIC = os.getenv("PAYMENT_EVENTS_TOPIC", "payment-events")
    while True:
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='order-service-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            consumer.subscribe([PAYMENT_EVENTS_TOPIC])
            print(f"Order Service: Kafka Consumer subscribed to topic: {PAYMENT_EVENTS_TOPIC}")
            for message in consumer:
                event = message.value
                event_type = event.get("event_type")
                print(f"Order Service consumed Kafka event: {event_type}")
                if event_type == "payment-settled":
                    handle_payment_event(event["data"], "Paid")
                elif event_type == "payment-failed":
                    handle_payment_event(event["data"], "Failed")
        except Exception as e:
            print(f"Order Service: Error in Kafka consumer loop: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

def run_file_simulator():
    """Watches local event log file for payment-events."""
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
                            event_type = event.get("event_type")
                            if event_type == "payment-settled":
                                handle_payment_event(event["data"], "Paid")
                            elif event_type == "payment-failed":
                                handle_payment_event(event["data"], "Failed")
            except Exception as e:
                print(f"Order Service Simulator watcher reading error: {e}")
        time.sleep(1)

@app.on_event("startup")
def start_workers():
    # Start background threads
    kafka_thread = threading.Thread(target=run_kafka_consumer, daemon=True)
    kafka_thread.start()
    
    sim_thread = threading.Thread(target=run_file_simulator, daemon=True)
    sim_thread.start()
    print("Order Service background consumer workers started.")



