import os
import json
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
import redis

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = "smartretailx_products"

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Setup PyMongo
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = mongo_client[DATABASE_NAME]
    mongo_client.server_info()
    print("Product Service connected to MongoDB database successfully!")
except Exception as e:
    print(f"Product Service failed to connect to MongoDB ({e}). Running in offline simulation mode.")
    db = None

# Redis Client
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_connect_timeout=2)
    redis_client.ping()
    print("Product Service connected to Redis Cache!")
except Exception as e:
    print(f"Redis cache not available ({e}). Running without Redis caching.")
    redis_client = None

# Pydantic models
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    category: str
    image_url: Optional[str] = None

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: str

# FastAPI Initialization
app = FastAPI(
    title="SmartRetailX Product Service",
    description="Microservice responsible for product catalogue management, utilizing MongoDB and Redis caches.",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seed database with sample products containing AWS S3 URLs if empty
@app.on_event("startup")
def seed_products():
    if db is not None:
        try:
            if db.products.count_documents({}) == 0:
                s3_base = "https://smartretailx-public-assets.s3.amazonaws.com/products"
                sample_products = [
                    {"name": "Wireless Noise-Canceling Headphones", "description": "Premium sound isolation and 40h battery.", "price": 199.99, "category": "Electronics", "image_url": f"{s3_base}/wireless-headphones.jpg"},
                    {"name": "Ergonomic Office Chair", "description": "High-back mesh chair with Lumbar support.", "price": 249.50, "category": "Furniture", "image_url": f"{s3_base}/office-chair.jpg"},
                    {"name": "Stainless Steel Water Bottle", "description": "Double-wall vacuum insulated, 32 oz.", "price": 29.99, "category": "Outdoor", "image_url": f"{s3_base}/water-bottle.jpg"},
                    {"name": "Smart Fitness Tracker", "description": "Real-time heart rate, sleep tracking, and GPS.", "price": 79.99, "category": "Electronics", "image_url": f"{s3_base}/fitness-tracker.jpg"},
                    {"name": "Mechanical Gaming Keyboard", "description": "RGB Backlit switches with custom keycaps.", "price": 119.00, "category": "Electronics", "image_url": f"{s3_base}/gaming-keyboard.jpg"},
                    {"name": "Minimalist Leather Wallet", "description": "Slim RFID blocking wallet for men & women.", "price": 45.00, "category": "Apparel", "image_url": f"{s3_base}/leather-wallet.jpg"}
                ]
                db.products.insert_many(sample_products)
                print("MongoDB database seeded with sample products containing AWS S3 asset references.")
        except Exception as e:
            print(f"Error seeding products: {e}")

# Helper to format Mongo docs
def format_product_doc(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "description": doc.get("description", ""),
        "price": doc["price"],
        "category": doc["category"],
        "image_url": doc.get("image_url", "")
    }


# In-memory metrics storage
import time
from fastapi import Request

product_requests_total = {}
product_latency_sum = 0.0
product_latency_count = 0
product_cache_hits = 0
product_cache_misses = 0

@app.middleware("http")
async def product_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    global product_latency_sum, product_latency_count
    product_latency_sum += duration
    product_latency_count += 1
    
    if not request.url.path.startswith(("/products/healthz", "/metrics")):
        key = (request.method, request.url.path, response.status_code)
        product_requests_total[key] = product_requests_total.get(key, 0) + 1
        
    return response

# Routes
@app.get("/products", response_model=List[ProductResponse])
def get_products(response: Response, category: Optional[str] = None):
    global product_cache_hits, product_cache_misses
    # Try fetching from Redis cache first
    cache_key = f"products:all:{category or 'none'}"
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                print("Cache HIT - returning cached products list")
                product_cache_hits += 1
                response.headers["X-Cache"] = "HIT"
                return json.loads(cached_data)
        except Exception as e:
            print(f"Redis cache read error: {e}")
            
    print("Cache MISS - query database")
    product_cache_misses += 1
    response.headers["X-Cache"] = "MISS"
    if db is None:
        return []
        
    query = {}
    if category:
        query["category"] = category
        
    products_cursor = db.products.find(query)
    products = [format_product_doc(p) for p in products_cursor]
    
    # Store response in Redis cache
    if redis_client:
        try:
            redis_client.setex(cache_key, 300, json.dumps(products)) # expire in 5 minutes
        except Exception as e:
            print(f"Redis cache write error: {e}")
            
    return products

@app.get("/products/recommendations", response_model=List[ProductResponse])
def get_recommendations(cart_product_ids: Optional[str] = None):
    if db is None:
        s3_base = "https://smartretailx-public-assets.s3.amazonaws.com/products"
        return [
            {"id": "dummy1", "name": "Wireless Noise-Canceling Headphones", "description": "Premium sound isolation and 40h battery.", "price": 199.99, "category": "Electronics", "image_url": f"{s3_base}/wireless-headphones.jpg"},
            {"id": "dummy2", "name": "Ergonomic Office Chair", "description": "High-back mesh chair with Lumbar support.", "price": 249.50, "category": "Furniture", "image_url": f"{s3_base}/office-chair.jpg"},
            {"id": "dummy3", "name": "Stainless Steel Water Bottle", "description": "Double-wall vacuum insulated, 32 oz.", "price": 29.99, "category": "Outdoor", "image_url": f"{s3_base}/water-bottle.jpg"}
        ][:3]

    fallback_cursor = db.products.find().limit(3)
    fallback_products = [format_product_doc(p) for p in fallback_cursor]
    
    if not cart_product_ids:
        return fallback_products
        
    product_id_list = [pid.strip() for pid in cart_product_ids.split(",") if pid.strip()]
    if not product_id_list:
        return fallback_products
        
    from bson import ObjectId
    cart_object_ids = []
    for pid in product_id_list:
        try:
            cart_object_ids.append(ObjectId(pid))
        except Exception:
            pass
            
    if not cart_object_ids:
        return fallback_products
        
    cart_products = list(db.products.find({"_id": {"$in": cart_object_ids}}))
    categories = set(p["category"] for p in cart_products)
    
    if not categories:
        return fallback_products
        
    recommended_cursor = db.products.find({
        "category": {"$in": list(categories)},
        "_id": {"$nin": cart_object_ids}
    }).limit(3)
    
    recommended = [format_product_doc(p) for p in recommended_cursor]
    
    if len(recommended) < 3:
        for p in fallback_products:
            if p["id"] not in product_id_list and not any(r["id"] == p["id"] for r in recommended):
                recommended.append(p)
                if len(recommended) >= 3:
                    break
                    
    return recommended[:3]

@app.get("/products/healthz")
def healthz():
    return {
        "status": "healthy",
        "redis_connected": redis_client is not None and bool(redis_client.ping()),
        "mongodb_connected": db is not None
    }

@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: str, response: Response):
    global product_cache_hits, product_cache_misses
    # Try fetching individual product from cache
    cache_key = f"product:{product_id}"
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                print(f"Cache HIT for product {product_id}")
                product_cache_hits += 1
                response.headers["X-Cache"] = "HIT"
                return json.loads(cached_data)
        except Exception as e:
            print(f"Redis cache read error: {e}")
            
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    print(f"Cache MISS for product {product_id} - query database")
    product_cache_misses += 1
    response.headers["X-Cache"] = "MISS"
    from bson import ObjectId
    try:
        db_product = db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID format")
        
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    product_data = format_product_doc(db_product)
    
    if redis_client:
        try:
            redis_client.setex(cache_key, 600, json.dumps(product_data)) # expire in 10 minutes
        except Exception as e:
            print(f"Redis cache write error: {e}")
            
    return product_data

@app.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product: ProductCreate, 
    x_user_role: Optional[str] = Header(None)
):
    if x_user_role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden: Admin or Manager role required")
        
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    product_doc = product.dict()
    result = db.products.insert_one(product_doc)
    product_doc["_id"] = result.inserted_id
    
    # Invalidate Cache
    if redis_client:
        try:
            keys = redis_client.keys("products:all:*")
            if keys:
                redis_client.delete(*keys)
        except Exception as e:
            print(f"Redis cache invalidation error: {e}")
            
    return format_product_doc(product_doc)

@app.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: str,
    product: ProductCreate,
    x_user_role: Optional[str] = Header(None)
):
    if x_user_role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden: Admin or Manager role required")
        
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    from bson import ObjectId
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID format")
        
    product_doc = product.dict()
    result = db.products.update_one({"_id": oid}, {"$set": product_doc})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Clear Cache
    if redis_client:
        try:
            redis_client.delete(f"product:{product_id}")
            keys = redis_client.keys("products:all:*")
            if keys:
                redis_client.delete(*keys)
        except Exception as e:
            print(f"Redis cache invalidation error: {e}")
            
    # Fetch updated product to return
    updated_doc = db.products.find_one({"_id": oid})
    return format_product_doc(updated_doc)

@app.delete("/products/{product_id}", status_code=status.HTTP_200_OK)
def delete_product(
    product_id: str, 
    x_user_role: Optional[str] = Header(None)
):
    if x_user_role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Forbidden: Admin or Manager role required")
        
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    from bson import ObjectId
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID format")
        
    result = db.products.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Clear Cache
    if redis_client:
        try:
            redis_client.delete(f"product:{product_id}")
            keys = redis_client.keys("products:all:*")
            if keys:
                redis_client.delete(*keys)
        except Exception as e:
            print(f"Redis cache invalidation error: {e}")
            
    return {"detail": "Product deleted successfully"}

from fastapi.responses import PlainTextResponse

@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    """Exposes standard formatted Prometheus text metrics for product service."""
    global product_latency_sum, product_latency_count, product_cache_hits, product_cache_misses
    lines = []
    
    # Total request counts
    lines.append("# HELP product_requests_total Total number of HTTP requests handled by the Product Service.")
    lines.append("# TYPE product_requests_total counter")
    for (method, path, status_code), count in product_requests_total.items():
        lines.append(f'product_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        
    # Latency metric
    lines.append("# HELP product_request_latency_seconds_sum Sum of request processing duration in seconds.")
    lines.append("# TYPE product_request_latency_seconds_sum counter")
    lines.append(f"product_request_latency_seconds_sum {product_latency_sum}")
    
    lines.append("# HELP product_request_latency_seconds_count Count of requests processed for latency computation.")
    lines.append("# TYPE product_request_latency_seconds_count counter")
    lines.append(f"product_request_latency_seconds_count {product_latency_count}")
    
    # Cache hit/miss metrics
    lines.append("# HELP product_cache_hits_total Total count of Redis cache hits.")
    lines.append("# TYPE product_cache_hits_total counter")
    lines.append(f"product_cache_hits_total {product_cache_hits}")
    
    lines.append("# HELP product_cache_misses_total Total count of Redis cache misses.")
    lines.append("# TYPE product_cache_misses_total counter")
    lines.append(f"product_cache_misses_total {product_cache_misses}")
    
    return "\n".join(lines) + "\n"
