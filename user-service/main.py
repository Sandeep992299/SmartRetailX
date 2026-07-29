import os
import time
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import bcrypt
import jwt
from pymongo import MongoClient

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "smartretailx-super-secret-key-123456")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = "smartretailx_users"

# Connect PyMongo
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = mongo_client[DATABASE_NAME]
    # Check connection
    mongo_client.server_info()
    print("User Service connected to MongoDB database successfully!")
except Exception as e:
    print(f"User Service failed to connect to MongoDB ({e}). Running in offline simulation mode.")
    db = None


# Pydantic Schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: Optional[str] = "Customer"

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: str
    created_at: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str

# FastAPI Initialization
app = FastAPI(
    title="SmartRetailX User Management Service",
    description="Microservice responsible for authentication, user storage, JWT signing, and Role-Based Access Control (RBAC) powered by MongoDB.",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication Utilities
def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

# Seed default test users if MongoDB is online and they are missing
@app.on_event("startup")
def seed_default_users():
    if db is not None:
        try:
            # Seed Admin
            if not db.users.find_one({"email": "admin@smartretailx.com"}):
                db.users.insert_one({
                    "username": "admin",
                    "email": "admin@smartretailx.com",
                    "hashed_password": get_password_hash("AdminPass123!"),
                    "role": "Admin",
                    "created_at": datetime.utcnow().isoformat()
                })
                print("Admin user seeded: admin@smartretailx.com / AdminPass123!")
                
            # Seed Manager
            if not db.users.find_one({"email": "manager@smartretailx.com"}):
                db.users.insert_one({
                    "username": "manager",
                    "email": "manager@smartretailx.com",
                    "hashed_password": get_password_hash("ManagerPass123!"),
                    "role": "Manager",
                    "created_at": datetime.utcnow().isoformat()
                })
                print("Manager user seeded: manager@smartretailx.com / ManagerPass123!")

            # Seed Customer
            if not db.users.find_one({"email": "customer@smartretailx.com"}):
                db.users.insert_one({
                    "username": "customer",
                    "email": "customer@smartretailx.com",
                    "hashed_password": get_password_hash("CustomerPass123!"),
                    "role": "Customer",
                    "created_at": datetime.utcnow().isoformat()
                })
                print("Customer user seeded: customer@smartretailx.com / CustomerPass123!")
        except Exception as e:
            print(f"Error seeding default users: {e}")

# Helper to format Mongo docs
def format_user_doc(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "username": doc["username"],
        "email": doc["email"],
        "role": doc.get("role", "Customer"),
        "created_at": doc.get("created_at", "")
    }

# Routes
@app.post("/users/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user: UserCreate):
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    # Check duplicate email
    if db.users.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # Check duplicate username
    if db.users.find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username already taken")
        
    hashed_pwd = get_password_hash(user.password)
    user_doc = {
        "username": user.username,
        "email": user.email,
        "hashed_password": hashed_pwd,
        "role": user.role,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return format_user_doc(user_doc)

@app.post("/users/login", response_model=Token)
def login(credentials: UserLogin):
    if db is None:
        raise HTTPException(status_code=503, detail="Database currently offline")
        
    user_doc = db.users.find_one({"email": credentials.email})
    if not user_doc or not verify_password(credentials.password, user_doc["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
        
    token_data = {
        "user_id": str(user_doc["_id"]),
        "username": user_doc["username"],
        "email": user_doc["email"],
        "role": user_doc.get("role", "Customer")
    }
    access_token = create_access_token(data=token_data)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user_doc.get("role", "Customer"),
        "username": user_doc["username"]
    }

@app.get("/users/me", response_model=UserResponse)
def get_user_profile(x_user_email: Optional[str] = Header(None)):
    if not x_user_email or db is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    from bson import ObjectId
    user_doc = db.users.find_one({"email": x_user_email})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User profile not found")
        
    return format_user_doc(user_doc)

@app.get("/users", response_model=List[UserResponse])
def get_all_users(
    x_user_role: Optional[str] = Header(None)
):
    if x_user_role != "Admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")
    if db is None:
        return []
        
    users_cursor = db.users.find()
    return [format_user_doc(u) for u in users_cursor]

@app.get("/users/healthz")
def healthz():
    return {
        "status": "healthy",
        "database": "mongodb",
        "mongodb_connected": db is not None
    }
