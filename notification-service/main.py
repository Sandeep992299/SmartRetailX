import os
import json
import time
import asyncio
import threading
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aws_xray_sdk.core import xray_recorder, patch_all
from starlette.middleware.base import BaseHTTPMiddleware
from kafka import KafkaConsumer
import boto3
from botocore.exceptions import ClientError

def send_ses_email(subject: str, html_body: str, recipient: str = None):
    """Sends a notification email via AWS SES if credentials and verified identities exist."""
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    sender = os.getenv("SES_SENDER_EMAIL", "alerts@smartretailx.com")
    if not recipient:
        recipient = os.getenv("SES_RECIPIENT_EMAIL", "admin@smartretailx.com")
        
    print(f"SES: Attempting to send email from '{sender}' to '{recipient}' (Subject: {subject})")
    
    # Allow bypassing/mocking in non-AWS/local runs to avoid crashing on missing AWS creds
    if os.getenv("AWS_ACCESS_KEY_ID") is None and os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") is None:
        print("SES: AWS credentials not found. Bypassing SES call (simulation fallback).")
        return
        
    try:
        client = boto3.client('ses', region_name=AWS_REGION)
        response = client.send_email(
            Destination={'ToAddresses': [recipient]},
            Message={
                'Body': {
                    'Html': {
                        'Charset': "UTF-8",
                        'Data': html_body,
                    },
                },
                'Subject': {
                    'Charset': "UTF-8",
                    'Data': subject,
                },
            },
            Source=sender,
        )
        print(f"SES: Email successfully sent! Message ID: {response['MessageId']}")
    except ClientError as e:
        print(f"SES: ClientError sending email: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"SES: Unexpected error sending email: {e}")

import urllib.request

def send_slack_webhook(text: str):
    """Sends a notification payload to Slack/Discord webhook URL if configured."""
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        print("Slack: Webhook URL not set. Bypassing Slack notification.")
        return
        
    print(f"Slack: Posting notification: {text}")
    try:
        payload = json.dumps({"text": text}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            print("Slack: Webhook notification posted successfully!")
    except Exception as e:
        print(f"Slack: Error posting webhook: {e}")


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
                order_id = event_data.get('order_id')
                is_fraud = event_data.get('is_fraud', False)
                print(f"ALERT: Payment failure for Order #{order_id} (Fraud: {is_fraud})")
                if is_fraud:
                    ip_addr = event_data.get('ip_address', 'unknown-ip')
                    reason = event_data.get('fraud_reason', 'Suspicious activity.')
                    subject = f"🛑 CRITICAL FRAUD ALERT: Order #{order_id}"
                    html_body = f"<h3>Suspicious Fraud Alert</h3><p>Order <strong>#{order_id}</strong> has been cancelled and flagged as fraud.</p><p><strong>IP Address:</strong> {ip_addr}</p><p><strong>Reason:</strong> {reason}</p>"
                    send_ses_email(subject, html_body)
                    send_slack_webhook(f"🚨 *CRITICAL FRAUD BLOCKED* 🚨\nOrder #{order_id} flagged as *FRAUD* from IP `{ip_addr}`. Reason: {reason}")
            elif event_type == "low-stock-alert":
                product_name = event_data.get('product_name', 'Unknown Product')
                product_id = event_data.get('product_id', 'N/A')
                stock_count = event_data.get('stock_count', 0)
                print(f"ALERT: Product '{product_name}' stock count is low ({stock_count})!")
                
                # Dispatch SES Email Notification
                subject = f"ALERT: Low Stock for Product '{product_name}'"
                html_body = f"<h3>SmartRetailX Inventory Alert</h3><p>The stock level for product <strong>{product_name}</strong> (ID: {product_id}) has fallen below the threshold.</p><p><strong>Current Stock count:</strong> {stock_count}</p><p>Please restock immediately.</p>"
                send_ses_email(subject, html_body)
                send_slack_webhook(f"⚠️ *LOW STOCK ALERT* ⚠️\nProduct *{product_name}* (ID: {product_id}) is down to *{stock_count}* units!")

                
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
# FastAPI Initialization
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

# AWS X-Ray Configuration
_xray_daemon_host = os.getenv("AWS_XRAY_DAEMON_ADDRESS", "127.0.0.1")
xray_recorder.configure(service="notification-service", daemon_address=f"{_xray_daemon_host}:2000")
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

# Notification Service metrics storage
notification_requests_total = {}
notification_latency_sum = 0.0
notification_latency_count = 0
notification_events_broadcast_total = 0

from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.middleware("http")
async def notification_metrics_middleware(request: Request, call_next):
    # WS connections are handled by WebSocket endpoint, not http middleware logging
    if request.scope.get("type") == "websocket" or request.url.path.startswith("/ws"):
        return await call_next(request)
        
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    global notification_latency_sum, notification_latency_count
    notification_latency_sum += duration
    notification_latency_count += 1
    
    if not request.url.path.startswith(("/healthz", "/metrics")):
        key = (request.method, request.url.path, response.status_code)
        notification_requests_total[key] = notification_requests_total.get(key, 0) + 1
        
    return response

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

@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    global notification_latency_sum, notification_latency_count, notification_events_broadcast_total
    lines = []
    
    # Total request counts
    lines.append("# HELP notification_requests_total Total number of HTTP requests handled by the Notification Service.")
    lines.append("# TYPE notification_requests_total counter")
    for (method, path, status_code), count in notification_requests_total.items():
        lines.append(f'notification_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        
    # Latency metric
    lines.append("# HELP notification_request_latency_seconds_sum Sum of request processing duration in seconds.")
    lines.append("# TYPE notification_request_latency_seconds_sum counter")
    lines.append(f"notification_request_latency_seconds_sum {notification_latency_sum}")
    
    lines.append("# HELP notification_request_latency_seconds_count Count of request processing durations.")
    lines.append("# TYPE notification_request_latency_seconds_count counter")
    lines.append(f"notification_request_latency_seconds_count {notification_latency_count}")

    # WebSocket connection counts
    lines.append("# HELP notification_websockets_connected Count of active WebSocket connections.")
    lines.append("# TYPE notification_websockets_connected gauge")
    lines.append(f"notification_websockets_connected {len(manager.active_connections)}")

    # Notification broadcasts count
    lines.append("# HELP notification_events_broadcast_total Total number of events broadcasted over WebSockets.")
    lines.append("# TYPE notification_events_broadcast_total counter")
    lines.append(f"notification_events_broadcast_total {notification_events_broadcast_total}")
    
    return "\n".join(lines)

# Asynchronous event dispatcher loop
async def queue_event_dispatcher():
    print("Notification dispatcher queue task started...")
    while True:
        event = await event_queue.get()
        print(f"Broadcasting event to WebSockets: {event.get('event_type')}")
        await manager.broadcast(event)
        
        # Trigger alerts on specific events
        event_type = event.get("event_type")
        event_data = event.get("data", {})
        if event_type == "low-stock-alert":
            product_name = event_data.get("product_name", "Unknown Product")
            product_id = event_data.get("product_id", "N/A")
            stock_count = event_data.get("stock_count", 0)
            subject = f"ALERT: Low Stock for Product '{product_name}'"
            html_body = f"<h3>SmartRetailX Inventory Alert</h3><p>The stock level for product <strong>{product_name}</strong> (ID: {product_id}) has fallen below the threshold.</p><p><strong>Current Stock count:</strong> {stock_count}</p><p>Please restock immediately.</p>"
            send_ses_email(subject, html_body)
            send_slack_webhook(f"⚠️ *LOW STOCK ALERT* ⚠️\nProduct *{product_name}* (ID: {product_id}) is down to *{stock_count}* units!")
        elif event_type == "payment-failed":
            order_id = event_data.get("order_id")
            is_fraud = event_data.get("is_fraud", False)
            if is_fraud:
                ip_addr = event_data.get("ip_address", "unknown-ip")
                reason = event_data.get("fraud_reason", "Suspicious activity.")
                subject = f"🛑 CRITICAL FRAUD ALERT: Order #{order_id}"
                html_body = f"<h3>Suspicious Fraud Alert</h3><p>Order <strong>#{order_id}</strong> has been cancelled and flagged as fraud.</p><p><strong>IP Address:</strong> {ip_addr}</p><p><strong>Reason:</strong> {reason}</p>"
                send_ses_email(subject, html_body)
                send_slack_webhook(f"🚨 *CRITICAL FRAUD BLOCKED* 🚨\nOrder #{order_id} flagged as *FRAUD* from IP `{ip_addr}`. Reason: {reason}")

            
        # Increment metric
        global notification_events_broadcast_total
        notification_events_broadcast_total += 1
        
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
