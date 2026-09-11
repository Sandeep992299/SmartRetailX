# 📖 SmartRetailX Platform: API Endpoint Specifications

This document outlines the complete REST API contract specifications for the **SmartRetailX** microservices architecture. It lists the endpoints, HTTP methods, request payload structures, and response schemas for your assignment submission.

---

## 🔐 1. User & Identity Service (`user-service`)
Responsible for customer registration, authentication, JWT issuing, and profile retrieval.

### Endpoint: Register User
* **HTTP Method**: `POST`
* **Path**: `/api/v1/users/signup`
* **Request Payload (`application/json`)**:
  ```json
  {
    "username": "sandeep",
    "email": "dissanayakesandeep@gmail.com",
    "password": "SecurePassword123!"
  }
  ```
* **Response Status**: `201 Created`
* **Response Payload**:
  ```json
  {
    "id": "65cf9c47e8f5e93c788e3c2b",
    "username": "sandeep",
    "email": "dissanayakesandeep@gmail.com",
    "role": "Customer"
  }
  ```

### Endpoint: User Login (Issues JWT)
* **HTTP Method**: `POST`
* **Path**: `/api/v1/users/login`
* **Request Payload (`application/json`)**:
  ```json
  {
    "username": "sandeep",
    "password": "SecurePassword123!"
  }
  ```
* **Response Status**: `200 OK`
* **Response Payload**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjVjZj...",
    "token_type": "bearer"
  }
  ```

### Endpoint: Retrieve Profile (JWT Protected)
* **HTTP Method**: `GET`
* **Path**: `/api/v1/users/me`
* **Headers**: `Authorization: Bearer <JWT_TOKEN>`
* **Response Status**: `200 OK`
* **Response Payload**:
  ```json
  {
    "id": "65cf9c47e8f5e93c788e3c2b",
    "username": "sandeep",
    "email": "dissanayakesandeep@gmail.com",
    "role": "Customer"
  }
  ```

---

## 📦 2. Product Catalog Service (`product-service`)
Handles query operations on the catalog store and cache, and allows inventory addition (Admin only).

### Endpoint: List Catalog Products
* **HTTP Method**: `GET`
* **Path**: `/api/v1/products`
* **Response Status**: `200 OK`
* **Response Payload**:
  ```json
  [
    {
      "product_id": "PRD-001",
      "name": "Smart Wireless Earbuds",
      "category": "Electronics",
      "price": 79.99,
      "description": "True wireless earbuds with active noise cancellation."
    },
    {
      "product_id": "PRD-002",
      "name": "Ergonomic Office Chair",
      "category": "Furniture",
      "price": 249.50,
      "description": "Mesh office chair with adjustable lumbar support."
    }
  ]
  ```

### Endpoint: Get Specific Product Details
* **HTTP Method**: `GET`
* **Path**: `/api/v1/products/{product_id}`
* **Response Status**: `200 OK`
* **Response Payload**:
  ```json
  {
    "product_id": "PRD-001",
    "name": "Smart Wireless Earbuds",
    "category": "Electronics",
    "price": 79.99,
    "description": "True wireless earbuds with active noise cancellation."
  }
  ```

### Endpoint: Create Product (Admin Only)
* **HTTP Method**: `POST`
* **Path**: `/api/v1/products`
* **Headers**: `Authorization: Bearer <ADMIN_JWT_TOKEN>`
* **Request Payload (`application/json`)**:
  ```json
  {
    "name": "Mechanical Keyboard",
    "category": "Electronics",
    "price": 120.00,
    "description": "Tactile blue switch keyboard with RGB backlights."
  }
  ```
* **Response Status**: `201 Created`

---

## 🛒 3. Order Processing Service (`order-service`)
Processes purchases, updates transaction state, and communicates status changes.

### Endpoint: Place Checkout Order (JWT Protected)
* **HTTP Method**: `POST`
* **Path**: `/api/v1/orders`
* **Headers**: `Authorization: Bearer <JWT_TOKEN>`
* **Request Payload (`application/json`)**:
  ```json
  {
    "items": [
      {
        "product_id": "PRD-001",
        "quantity": 2
      }
    ],
    "shipping_address": "123 Main St, London, UK"
  }
  ```
* **Response Status**: `201 Created`
* **Response Payload**:
  ```json
  {
    "order_id": "ORD-77629",
    "user_id": "65cf9c47e8f5e93c788e3c2b",
    "total_amount": 159.98,
    "status": "pending",
    "created_at": "2026-08-19T08:16:00Z"
  }
  ```

### Endpoint: Get Order History
* **HTTP Method**: `GET`
* **Path**: `/api/v1/orders`
* **Headers**: `Authorization: Bearer <JWT_TOKEN>`
* **Response Status**: `200 OK`

---

## 💳 4. Billing & Payment Service (`payment-service`)
Simulates interaction with bank gateways and validates transaction authorization.

### Endpoint: Submit Payment
* **HTTP Method**: `POST`
* **Path**: `/api/v1/payments/process`
* **Request Payload (`application/json`)**:
  ```json
  {
    "order_id": "ORD-77629",
    "amount": 159.98,
    "card_number": "4111222233334444",
    "card_name": "Sandeep Dissanayake",
    "cvv": "123",
    "expiry": "12/28"
  }
  ```
* **Response Status**: `200 OK`
* **Response Payload**:
  ```json
  {
    "transaction_id": "TXN-00998822",
    "order_id": "ORD-77629",
    "status": "approved",
    "message": "Payment captured successfully."
  }
  ```

---

## 📈 5. Inventory Telemetry Service (`inventory-service`)
Validates stock thresholds and updates warehouse quantity tables.

### Endpoint: Retrieve Stock Levels
* **HTTP Method**: `GET`
* **Path**: `/api/v1/inventory`
* **Response Status**: `200 OK`
* **Response Payload**:
  ```json
  [
    {
      "product_id": "PRD-001",
      "stock_count": 48
    },
    {
      "product_id": "PRD-002",
      "stock_count": 3
    }
  ]
  ```
