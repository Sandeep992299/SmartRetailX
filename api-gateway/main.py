import os
import time
import httpx
import jwt
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import redis
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from starlette.middleware.base import BaseHTTPMiddleware

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "smartretailx-super-secret-key-123456")
JWT_ALGORITHM = "HS256"

# Service URLs
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8002")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8003")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8004")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8005")

# Initialize Redis connection with fallback to mock dictionary for local development
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_connect_timeout=2)
    # Test connection
    redis_client.ping()
    print("API Gateway successfully connected to Redis!")
except Exception as e:
    print(f"Redis not available ({e}). Using in-memory fallback for rate limiting.")
    redis_client = None

# Fallback rate limiting storage
in_memory_rate_limits = {}

app = FastAPI(
    title="SmartRetailX API Gateway",
    description="Central ingress API Gateway with JWT routing, versioning, and Redis rate limiting.",
    version="1.0.0"
)

# Enable CORS for frontend UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AWS X-Ray Configuration
_xray_daemon_host = os.getenv("AWS_XRAY_DAEMON_ADDRESS", "127.0.0.1")
xray_recorder.configure(
    service="api-gateway",
    daemon_address=f"{_xray_daemon_host}:2000"
)
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

# HTTP Client for proxying
http_client = httpx.AsyncClient()

# Rate limiting settings (requests per client IP per minute)
RATE_LIMIT_MAX = 100
RATE_LIMIT_WINDOW = 60

def check_rate_limit(client_ip: str) -> tuple:
    """Checks if client IP is within rate limits. Returns (allowed, remaining, reset_seconds)."""
    now = int(time.time())
    reset_seconds = RATE_LIMIT_WINDOW - (now % RATE_LIMIT_WINDOW)
    
    if redis_client:
        try:
            key = f"rate_limit:{client_ip}:{now // RATE_LIMIT_WINDOW}"
            requests = redis_client.incr(key)
            if requests == 1:
                redis_client.expire(key, RATE_LIMIT_WINDOW)
            allowed = requests <= RATE_LIMIT_MAX
            remaining = max(0, RATE_LIMIT_MAX - requests)
            return allowed, remaining, reset_seconds
        except Exception as e:
            print(f"Redis rate limit error: {e}. Falling back to in-memory.")
    
    # In-memory fallback rate limiting
    key = f"{client_ip}:{now // RATE_LIMIT_WINDOW}"
    count = in_memory_rate_limits.get(key, 0) + 1
    in_memory_rate_limits[key] = count
    
    if len(in_memory_rate_limits) > 5000:
        in_memory_rate_limits.clear()
        
    allowed = count <= RATE_LIMIT_MAX
    remaining = max(0, RATE_LIMIT_MAX - count)
    return allowed, remaining, reset_seconds


def verify_jwt(token: str) -> dict:
    """Decodes and validates JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# In-memory Prometheus metrics storage
metrics_requests_total = {}  # key: (method, path, status_code) -> count
metrics_latency_sum = 0.0
metrics_latency_count = 0

@app.middleware("http")
async def gateway_middleware(request: Request, call_next):
    # Get client IP
    client_ip = request.client.host if request.client else "unknown-ip"
    
    # Generate/Retrieve Correlation ID
    correlation_id = request.headers.get("X-Correlation-ID") or f"corr_{int(time.time())}_{os.urandom(4).hex()}"
    
    # Apply Rate Limiting (exclude Swagger docs, metrics endpoint, and static files)
    allowed, remaining, reset_seconds = True, RATE_LIMIT_MAX, 60
    if not request.url.path.startswith(("/docs", "/openapi.json", "/redoc", "/metrics")):
        allowed, remaining, reset_seconds = check_rate_limit(client_ip)
        if not allowed:
            res = Response(
                content='{"detail": "Rate limit exceeded. Try again in a minute."}',
                status_code=429,
                media_type="application/json"
            )
            res.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX)
            res.headers["X-RateLimit-Remaining"] = "0"
            res.headers["X-RateLimit-Reset"] = str(reset_seconds)
            res.headers["X-Correlation-ID"] = correlation_id
            return res
            
    # Measure request latency
    start_time = time.time()
    
    # Inject Correlation ID into request state to pass it to proxy_request
    request.state.correlation_id = correlation_id
    
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Record Prometheus metrics
    global metrics_latency_sum, metrics_latency_count
    metrics_latency_sum += duration
    metrics_latency_count += 1
    
    # Avoid logging Swagger docs in request stats metrics
    if not request.url.path.startswith(("/docs", "/openapi.json", "/redoc")):
        key = (request.method, request.url.path, response.status_code)
        metrics_requests_total[key] = metrics_requests_total.get(key, 0) + 1
    
    # Inject Custom API Gateway metrics and telemetry headers
    response.headers["X-Gateway-Latency-Seconds"] = f"{duration:.4f}"
    response.headers["X-API-Version"] = "v1"
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_seconds)
    return response


# Reverse proxy routing logic
async def proxy_request(service_url: str, path: str, request: Request) -> Response:
    # Construct target URL
    target_url = f"{service_url}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"
        
    # Read headers and request body
    headers = dict(request.headers)
    
    # Inject Correlation ID into downstream headers
    correlation_id = getattr(request.state, "correlation_id", None)
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    
    # Check authorization JWT for secured endpoints
    auth_header = headers.get("authorization")
    user_payload = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            user_payload = verify_jwt(token)
            # Inject validated user claims into downstream headers
            headers["X-User-Id"] = str(user_payload.get("user_id", ""))
            headers["X-User-Role"] = user_payload.get("role", "Customer")
            headers["X-User-Email"] = user_payload.get("email", "")
            headers["X-Forwarded-For"] = request.client.host if request.client else "unknown-ip"

        except HTTPException as e:
            return Response(content=f'{{"detail": "{e.detail}"}}', status_code=e.status_code, media_type="application/json")

    # Read body content
    body = await request.body()
    
    # Forward the request to downstream microservice
    try:
        response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=10.0
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get("content-type")
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Service at {service_url} is currently unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

# Gateway APIs with versioning
# Users
@app.api_route("/api/v1/users", methods=["GET", "POST", "PUT", "DELETE"])
async def route_users_root(request: Request):
    return await proxy_request(USER_SERVICE_URL, "users", request)

@app.api_route("/api/v1/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_users(path: str, request: Request):
    return await proxy_request(USER_SERVICE_URL, f"users/{path}", request)

# Products
@app.api_route("/api/v1/products", methods=["GET", "POST", "PUT", "DELETE"])
async def route_products_root(request: Request):
    return await proxy_request(PRODUCT_SERVICE_URL, "products", request)

@app.api_route("/api/v1/products/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_products(path: str, request: Request):
    return await proxy_request(PRODUCT_SERVICE_URL, f"products/{path}", request)

# Orders
@app.api_route("/api/v1/orders", methods=["GET", "POST", "PUT", "DELETE"])
async def route_orders_root(request: Request):
    return await proxy_request(ORDER_SERVICE_URL, "orders", request)

@app.api_route("/api/v1/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_orders(path: str, request: Request):
    return await proxy_request(ORDER_SERVICE_URL, f"orders/{path}", request)

# Payments
@app.api_route("/api/v1/payments", methods=["GET", "POST", "PUT", "DELETE"])
async def route_payments_root(request: Request):
    return await proxy_request(PAYMENT_SERVICE_URL, "payments", request)

@app.api_route("/api/v1/payments/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_payments(path: str, request: Request):
    return await proxy_request(PAYMENT_SERVICE_URL, f"payments/{path}", request)

# Inventory
@app.api_route("/api/v1/inventory", methods=["GET", "POST", "PUT", "DELETE"])
async def route_inventory_root(request: Request):
    return await proxy_request(INVENTORY_SERVICE_URL, "inventory", request)

@app.api_route("/api/v1/inventory/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_inventory(path: str, request: Request):
    return await proxy_request(INVENTORY_SERVICE_URL, f"inventory/{path}", request)

# Heartbeat Endpoint
@app.get("/healthz")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "redis_connected": redis_client is not None and bool(redis_client.ping())
    }

from fastapi.responses import PlainTextResponse

@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    """Exposes standard formatted Prometheus text metrics."""
    global metrics_latency_sum, metrics_latency_count
    lines = []
    
    # Total request counts
    lines.append("# HELP api_gateway_requests_total Total number of HTTP requests handled by the API Gateway.")
    lines.append("# TYPE api_gateway_requests_total counter")
    for (method, path, status_code), count in metrics_requests_total.items():
        lines.append(f'api_gateway_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        
    # Latency metric
    lines.append("# HELP api_gateway_request_latency_seconds_sum Sum of request processing duration in seconds.")
    lines.append("# TYPE api_gateway_request_latency_seconds_sum counter")
    lines.append(f"api_gateway_request_latency_seconds_sum {metrics_latency_sum}")
    
    lines.append("# HELP api_gateway_request_latency_seconds_count Count of requests processed for latency computation.")
    lines.append("# TYPE api_gateway_request_latency_seconds_count counter")
    lines.append(f"api_gateway_request_latency_seconds_count {metrics_latency_count}")
    
    # Custom rate limiting metric
    redis_status = 1 if redis_client is not None else 0
    lines.append("# HELP api_gateway_redis_connected Status of connection to Redis backend.")
    lines.append("# TYPE api_gateway_redis_connected gauge")
    lines.append(f"api_gateway_redis_connected {redis_status}")
    
    return "\n".join(lines) + "\n"

# Clean shutdown
@app.on_event("shutdown")
async def shutdown():
    await http_client.aclose()
