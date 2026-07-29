import os
import json
import time
import asyncio
import threading
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaConsumer

# ----------------------------------------------------
# 1. AWS Lambda Handler Entrypoint (Task 4 Event-Driven Lambda)
# ----------------------------------------------------
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda entrypoint triggered by SQS, MSK, or EventBridge.
    Processes retail events and routes notifications.
    """
    print(f"AWS Lambda invoked with event: {json.dumps(event)}")
    
    # Process batch records if triggered by SQS
    records = event.get("Records", [])
    notifications_sent = 0
    
    for record in records:
        body_str = record.get("body", "{}")
        try:
            body = json.loads(body_str)
            event_type = body.get("event_type", "unknown")
            event_data = body.get("data", {})
            
            # EventBridge Simulator Routing Logic
            print(f"Processing EventBridge Event Target: {event_type}")
            if event_type == "payment-settled":
                print(f"NOTIFY: Order #{event_data.get('order_id')} paid successfully. User email: {event_data.get('user_email')}")
            elif event_type == "payment-failed":
                print(f"ALERT: Payment failure for Order #{event_data.get('order_id')}")
            elif event_type == "low-stock-alert":
                print(f"ALERT: Product '{event_data.get('product_name')}' stock count is low ({event_data.get('stock_count')})!")
                
            notifications_sent += 1
        except Exception as e:
            print(f"Error parsing record body: {e}")
            
    # Direct EventBridge payload (non-SQS direct invocation)
    if not records and "event_type" in event:
        event_type = event.get("event_type")
        event_data = event.get("data", {})
        print(f"Direct EventBridge Route -> Type: {event_type}, Order ID: {event_data.get('order_id')}")
        notifications_sent += 1

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Notifications processed successfully",
            "notifications_sent": notifications_sent
        })
    }

# ----------------------------------------------------
# 2. Local WebSocket & Kafka Broadcast Server (Local Compose Testing)
# ----------------------------------------------------
app = FastAPI(
    title="SmartRetailX Notification WebSocket Service",
    description="Local runner representing the Lambda event processor with live browser WebSocket streaming.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Manage WebSocket connection states
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"New client connected! Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"Client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        # Async send to all connected UIs
        closed_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                closed_connections.append(connection)
                
        for connection in closed_connections:
            self.disconnect(connection)

manager = ConnectionManager()

# Global Event Queue for thread safety
event_queue = asyncio.Queue()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Keep connection open, receive ping messages if any
        while True:
            data = await websocket.receive_text()
            # Send keep-alive echo
            await websocket.send_json({"type": "ping", "data": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/healthz")
def healthz():
    return {"status": "healthy", "websockets_connected": len(manager.active_connections)}

# Asynchronous event dispatcher loop
async def queue_event_dispatcher():
    print("Notification dispatcher queue task started...")
    while True:
        event = await event_queue.get()
        print(f"Broadcasting event to WebSockets: {event.get('event_type')}")
        await manager.broadcast(event)
        event_queue.task_done()

# Kafka broker consumer
def run_kafka_consumer(loop):
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    while True:
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='notification-service-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            consumer.subscribe(['order-events', 'payment-events', 'inventory-events'])
            print("Notification Service Kafka consumer connected and subscribed!")
            for message in consumer:
                event = message.value
                print(f"Notification consumed event: {event.get('event_type')}")
                loop.call_soon_threadsafe(event_queue.put_nowait, event)
        except Exception as e:
            print(f"Notification Kafka consumer error: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

# Watcher simulating events from local file when Kafka is down
def run_file_simulator(loop):
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
                            print(f"Notification simulator read event: {event.get('event_type')}")
                            loop.call_soon_threadsafe(event_queue.put_nowait, event)
            except Exception as e:
                print(f"Notification File Simulator error: {e}")
        time.sleep(1)

@app.on_event("startup")
def start_ws_broadcaster():
    # Capture running loop
    loop = asyncio.get_event_loop()
    
    # Start dispatcher queue consumer
    asyncio.create_task(queue_event_dispatcher())
    
    # Start Kafka listener thread
    kafka_thread = threading.Thread(target=run_kafka_consumer, args=(loop,), daemon=True)
    kafka_thread.start()
    
    # Start local file listener thread
    sim_thread = threading.Thread(target=run_file_simulator, args=(loop,), daemon=True)
    sim_thread.start()

if __name__ == "__main__":
    import uvicorn
    # Standalone execution launch
    uvicorn.run(app, host="0.0.0.0", port=8006)
