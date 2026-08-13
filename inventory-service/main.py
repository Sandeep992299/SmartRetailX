import os
import json
import time
import threading
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from aws_xray_sdk.core import xray_recorder, patch_all
from aws_xray_sdk.ext.fastapi.middleware import AWSXRayMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from kafka import KafkaConsumer, KafkaProducer
import redis

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = "smartretailx_inventory"

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ORDER_EVENTS_TOPIC = os.getenv("ORDER_EVENTS_TOPIC", "order-events")
PAYMENT_EVENTS_TOPIC = os.getenv("PAYMENT_EVENTS_TOPIC", "payment-events")
INVENTORY_EVENTS_TOPIC = os.getenv("INVENTORY_EVENTS_TOPIC", "inventory-events")

# Setup PyMongo
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = mongo_client[DATABASE_NAME]
    mongo_client.server_info()
    print("Inventory Service connected to MongoDB database successfully!")
except Exception as e:
    print(f"Inventory Service failed to connect to MongoDB ({e}). Running in offline simulation mode.")
    db = None

# Redis Client Setup
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_connect_timeout=2)
    redis_client.ping()
    print("Inventory Service successfully connected to Redis!")
except Exception as e:
    print(f"Redis not available in Inventory Service ({e}). Running without Redis cache.")
    redis_client = None

# Kafka Producer Client
kafka_producer = None
try:
    kafka_producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        request_timeout_ms=5000,
        max_block_ms=3000
    )
    print("Inventory Service successfully connected to Kafka Producer!")
except Exception as e:
    print(f"Inventory Kafka Producer unavailable ({e}). Running in localized simulation mode.")

# Pydantic Schemas
class InventoryBase(BaseModel):
    product_id: str # modified to string as product IDs in MongoDB are strings
    product_name: str
    stock_count: int
    reserved_count: int

class StockUpdate(BaseModel):
    stock_count: int

class InventoryResponse(InventoryBase):
    pass

# FastAPI Initialization
app = FastAPI(
    title="SmartRetailX Inventory Management Service",
    description="Microservice responsible for tracking catalog stock counts in MongoDB, reserving items, and caching in Redis.",
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
_xray_daemon_host = os.getenv("AWS_XRAY_DAEMON_ADDRESS", "127.0.0.1")
xray_recorder.configure(service="inventory-service", daemon_address=f"{_xray_daemon_host}:2000")
patch_all()
app.add_middleware(AWSXRayMiddleware, recorder=xray_recorder)

# Inventory Service metrics storage
inventory_requests_total = {}
inventory_latency_sum = 0.0
inventory_latency_count = 0
inventory_cache_hits = 0
inventory_cache_misses = 0

from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.middleware("http")
async def inventory_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    global inventory_latency_sum, inventory_latency_count
    inventory_latency_sum += duration
    inventory_latency_count += 1
    
    if not request.url.path.startswith(("/inventory/healthz", "/metrics")):
        key = (request.method, request.url.path, response.status_code)
        inventory_requests_total[key] = inventory_requests_total.get(key, 0) + 1
        
    return response
# Seed database with starting quantities
@app.on_event("startup")
def seed_inventory():
    if db is not None:
        try:
            if db.inventory.count_documents({}) == 0:
                starting_stock = [
                    {"product_id": "1", "product_name": "Wireless Noise-Canceling Headphones", "stock_count": 50, "reserved_count": 0},
                    {"product_id": "2", "product_name": "Ergonomic Office Chair", "stock_count": 20, "reserved_count": 0},
                    {"product_id": "3", "product_name": "Stainless Steel Water Bottle", "stock_count": 150, "reserved_count": 0},
                    {"product_id": "4", "product_name": "Smart Fitness Tracker", "stock_count": 4, "reserved_count": 0}, # low stock seed
                    {"product_id": "5", "product_name": "Mechanical Gaming Keyboard", "stock_count": 40, "reserved_count": 0},
                    {"product_id": "6", "product_name": "Minimalist Leather Wallet", "stock_count": 80, "reserved_count": 0}
                ]
                db.inventory.insert_many(starting_stock)
                print("MongoDB inventory database seeded with starting stock.")
        except Exception as e:
            print(f"Error seeding inventory: {e}")

# Helper to format Mongo docs
def format_inventory_doc(doc) -> dict:
    return {
        "product_id": doc["product_id"],
        "product_name": doc["product_name"],
        "stock_count": doc.get("stock_count", 0),
        "reserved_count": doc.get("reserved_count", 0)
    }


def update_redis_cache(product_id: str, stock: int):
    if redis_client:
        try:
            redis_client.set(f"inventory:stock:{product_id}", stock)
        except Exception as e:
            print(f"Redis cache write error: {e}")

def publish_inventory_event(event_type: str, product_id: str, name: str, current_stock: int):
    event_payload = {
        "event_id": f"evt_inv_{product_id}_{int(time.time())}",
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "product_id": product_id,
            "product_name": name,
            "stock_count": current_stock
        }
    }
    
    if kafka_producer:
        try:
            kafka_producer.send(INVENTORY_EVENTS_TOPIC, value=event_payload)
            kafka_producer.flush()
            print(f"Inventory event '{event_type}' published to Kafka topic '{INVENTORY_EVENTS_TOPIC}'")
            return
        except Exception as e:
            print(f"Failed to publish inventory event to Kafka: {e}")

    # Local simulation log fallback
    sim_log_dir = "./logs"
    os.makedirs(sim_log_dir, exist_ok=True)
    with open(f"{sim_log_dir}/event_bus.jsonl", "a") as f:
        f.write(json.dumps(event_payload) + "\n")
    print(f"SIMULATOR: Event '{event_type}' written to {sim_log_dir}/event_bus.jsonl")

def handle_order_created(order_data: dict):
    """Reserves inventory items upon checking out."""
    if db is None:
        return
    try:
        items = order_data.get("items", [])
        order_id = order_data.get("order_id")
        print(f"Inventory: Reserving stock for Order #{order_id}")
        
        for item in items:
            product_id = str(item["product_id"])
            quantity = item["quantity"]
            
            db_item = db.inventory.find_one({"product_id": product_id})
            if db_item:
                new_reserved = db_item.get("reserved_count", 0) + quantity
                new_stock = db_item.get("stock_count", 0) - quantity
                
                db.inventory.update_one(
                    {"product_id": product_id},
                    {"$set": {"reserved_count": new_reserved, "stock_count": new_stock}}
                )
                
                # Check low-stock threshold
                if new_stock < 5:
                    publish_inventory_event("low-stock-alert", product_id, db_item["product_name"], new_stock)
                    
                update_redis_cache(product_id, new_stock)
                
        print(f"Inventory successfully reserved for Order #{order_id}")
    except Exception as e:
        print(f"Error reserving inventory stock: {e}")

def handle_payment_settled(payment_data: dict):
    """Finalizes inventory reservation upon payment success: clears reserved count."""
    if db is None:
        return
    order_id = payment_data.get("order_id")
    print(f"Inventory: Finalizing stock reservation for Order #{order_id}")
    try:
        import requests
        # Get order items from order service
        res = requests.get(
            f"http://order-service:8003/orders/{order_id}",
            headers={"x-user-id": "system", "x-user-role": "Admin"}
        )
        if res.ok:
            order = res.json()
            items = order.get("items", [])
            for item in items:
                product_id = str(item["product_id"])
                quantity = item["quantity"]
                db_item = db.inventory.find_one({"product_id": product_id})
                if db_item:
                    new_reserved = max(0, db_item.get("reserved_count", 0) - quantity)
                    db.inventory.update_one(
                        {"product_id": product_id},
                        {"$set": {"reserved_count": new_reserved}}
                    )
            print(f"Inventory: Reservations finalized for Order #{order_id}")
    except Exception as e:
        print(f"Inventory: Error settling payment reservation: {e}")

def handle_payment_failed(payment_data: dict):
    """Rollbacks inventory reservation upon payment failure: restores stock count."""
    if db is None:
        return
    order_id = payment_data.get("order_id")
    print(f"Inventory: Rolling back stock reservation for Order #{order_id}")
    try:
        import requests
        res = requests.get(
            f"http://order-service:8003/orders/{order_id}",
            headers={"x-user-id": "system", "x-user-role": "Admin"}
        )
        if res.ok:
            order = res.json()
            items = order.get("items", [])
            for item in items:
                product_id = str(item["product_id"])
                quantity = item["quantity"]
                db_item = db.inventory.find_one({"product_id": product_id})
                if db_item:
                    new_reserved = max(0, db_item.get("reserved_count", 0) - quantity)
                    new_stock = db_item.get("stock_count", 0) + quantity
                    db.inventory.update_one(
                        {"product_id": product_id},
                        {"$set": {"reserved_count": new_reserved, "stock_count": new_stock}}
                    )
                    update_redis_cache(product_id, new_stock)
            print(f"Inventory: Rollback completed for Order #{order_id}")
    except Exception as e:
        print(f"Inventory: Error rolling back reservation: {e}")

# Background consumer loops
def run_kafka_consumer():
    while True:
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='inventory-service-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            consumer.subscribe([ORDER_EVENTS_TOPIC, PAYMENT_EVENTS_TOPIC])
            print(f"Inventory Service Kafka Consumer subscribed to topics: {ORDER_EVENTS_TOPIC}, {PAYMENT_EVENTS_TOPIC}")
            for message in consumer:
                event = message.value
                event_type = event.get("event_type")
                print(f"Inventory Service consumed Kafka event: {event_type}")
                if event_type == "order-created":
                    handle_order_created(event["data"])
                elif event_type == "payment-settled":
                    handle_payment_settled(event["data"])
                elif event_type == "payment-failed":
                    handle_payment_failed(event["data"])
        except Exception as e:
            print(f"Error in Kafka consumer loop: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

def run_file_simulator():
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
                            if event_type == "order-created":
                                handle_order_created(event["data"])
                            elif event_type == "payment-settled":
                                handle_payment_settled(event["data"])
                            elif event_type == "payment-failed":
                                handle_payment_failed(event["data"])
            except Exception as e:
                print(f"Simulator watcher reading error: {e}")
        time.sleep(1)

@app.on_event("startup")
def start_workers():
    # Start EKS Kafka thread
    kafka_thread = threading.Thread(target=run_kafka_consumer, daemon=True)
    kafka_thread.start()
    
    # Start local file simulator watcher
    sim_thread = threading.Thread(target=run_file_simulator, daemon=True)
    sim_thread.start()

# REST Endpoints
@app.get("/inventory", response_model=List[InventoryResponse])
def get_all_inventory():
    if db is None:
        return []
    cursor = db.inventory.find()
    return [format_inventory_doc(i) for i in cursor]

@app.get("/inventory/healthz")
def healthz():
    return {
        "status": "healthy",
        "redis_connected": redis_client is not None and bool(redis_client.ping()),
        "mongodb_connected": db is not None
    }

@app.get("/inventory/{product_id}", response_model=InventoryResponse)
def get_inventory(product_id: str):
    # Try fetching stock level from Redis first
    if redis_client:
        try:
            cached_stock = redis_client.get(f"inventory:stock:{product_id}")
            if cached_stock:
                print(f"Inventory Cache HIT for product {product_id}")
                global inventory_cache_hits
                inventory_cache_hits += 1
                if db is not None:
                    item = db.inventory.find_one({"product_id": product_id})
                    if item:
                        item["stock_count"] = int(cached_stock)
                        return format_inventory_doc(item)
        except Exception as e:
            print(f"Redis cache read error: {e}")
            
    global inventory_cache_misses
    inventory_cache_misses += 1
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    item = db.inventory.find_one({"product_id": product_id})
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
        
    update_redis_cache(product_id, item.get("stock_count", 0))
    return format_inventory_doc(item)

@app.put("/inventory/{product_id}", response_model=InventoryResponse)
def update_stock(
    product_id: str,
    update: StockUpdate,
    x_user_role: Optional[str] = Header(None)
):
    if x_user_role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden: Staff permission required")
        
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    item = db.inventory.find_one({"product_id": product_id})
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
        
    db.inventory.update_one(
        {"product_id": product_id},
        {"$set": {"stock_count": update.stock_count}}
    )
    
    updated_item = db.inventory.find_one({"product_id": product_id})
    update_redis_cache(product_id, update.stock_count)
    publish_inventory_event("inventory-restocked", product_id, updated_item["product_name"], update.stock_count)
    
    return format_inventory_doc(updated_item)

@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    global inventory_latency_sum, inventory_latency_count, inventory_cache_hits, inventory_cache_misses
    lines = []
    
    # Total request counts
    lines.append("# HELP inventory_requests_total Total number of HTTP requests handled by the Inventory Service.")
    lines.append("# TYPE inventory_requests_total counter")
    for (method, path, status_code), count in inventory_requests_total.items():
        lines.append(f'inventory_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        
    # Latency metric
    lines.append("# HELP inventory_request_latency_seconds_sum Sum of request processing duration in seconds.")
    lines.append("# TYPE inventory_request_latency_seconds_sum counter")
    lines.append(f"inventory_request_latency_seconds_sum {inventory_latency_sum}")
    
    lines.append("# HELP inventory_request_latency_seconds_count Count of request processing durations.")
    lines.append("# TYPE inventory_request_latency_seconds_count counter")
    lines.append(f"inventory_request_latency_seconds_count {inventory_latency_count}")

    # Cache hit/miss stats
    lines.append("# HELP inventory_cache_hits_total Total number of Redis cache hits.")
    lines.append("# TYPE inventory_cache_hits_total counter")
    lines.append(f"inventory_cache_hits_total {inventory_cache_hits}")

    lines.append("# HELP inventory_cache_misses_total Total number of Redis cache misses.")
    lines.append("# TYPE inventory_cache_misses_total counter")
    lines.append(f"inventory_cache_misses_total {inventory_cache_misses}")

    # Connections status
    redis_conn = 0
    if redis_client:
        try:
            if redis_client.ping():
                redis_conn = 1
        except Exception:
            pass
    lines.append("# HELP inventory_redis_connected Status of Redis cache connection.")
    lines.append("# TYPE inventory_redis_connected gauge")
    lines.append(f"inventory_redis_connected {redis_conn}")

    lines.append("# HELP inventory_mongodb_connected Status of MongoDB connection.")
    lines.append("# TYPE inventory_mongodb_connected gauge")
    lines.append(f"inventory_mongodb_connected {1 if db is not None else 0}")

    lines.append("# HELP inventory_kafka_connected Status of Kafka connection.")
    lines.append("# TYPE inventory_kafka_connected gauge")
    lines.append(f"inventory_kafka_connected {1 if kafka_producer is not None else 0}")
    
    return "\n".join(lines)
