# SmartRetailX: Cloud-Native Distributed Commerce Platform

SmartRetailX is a modern, event-driven, microservices-based e-commerce platform built to replace a legacy monolithic application. It is designed for high availability, multi-region scalability, and real-time transaction processing.

This repository contains the complete source code, infrastructure-as-code blueprints (Terraform), Kubernetes manifests (EKS), testing scripts, and technical documentation.

---

## 🏗️ System Architecture

The architecture consists of a React-based frontend dashboard that interacts with a Python (FastAPI) API Gateway. The Gateway manages rate limiting and distributes traffic across decoupled, database-isolated microservices. Core services save data in a document database (MongoDB/DocumentDB) for schema flexibility, while the Payment Service runs a relational SQL database (PostgreSQL/RDS) to ensure strict transactional integrity (ACID). An event stream broker (Kafka) manages asynchronous communication, and AWS Lambda processes event-driven notifications.

```
                  ┌──────────────────────────────┐
                  │   Frontend SPA (Vite+React)  │◄─────────┐ Load images
                  └──────────────┬───────────────┘          │
                                 │ HTTP / WebSockets        ▼
                                 ▼                   ┌──────────────┐
                  ┌──────────────────────────────┐   │ AWS S3 Bucket│
                  │    API Gateway (FastAPI)     │   └──────────────┘
                  └──────────────┬───────────────┘
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌────────────────┐      ┌────────────────┐      ┌────────────────┐
│  User Service  │      │ Product Service│      │  Order Service │
└────────┬───────┘      └────────┬───────┘      └────────┬───────┘
         │                       │                       │
         └─────────────┬─────────┴───────────────────────┘
                       ▼
               ┌──────────────┐                  ┌──────────────┐
               │MongoDB Database◄────────────────►Inventory Serv.│
               └──────────────┘                  └───────┬──────┘
                                                         │
                                                         ▼
                                                 [Kafka Event Bus]
                                                         │
         ┌───────────────────────────────────────────────┴──────┐
         ▼                                                      ▼
┌────────────────┐                                     ┌────────────────┐
│Payment Service │◄───────────────────────────────────►│Notification Lmb│
└────────┬───────┘                                     └────────┬───────┘
         │                                                      │ WebSockets
         ▼                                                      ▼
 ┌──────────────┐                                       [User Dashboard]
 │ PostgreSQL DB│
 └──────────────┘
```

### Core Architecture Components
1. **API Gateway (Port 8000)**: Serves as the single ingress point. Performs API routing (`/api/v1/*`), handles JSON Web Token (JWT) verification, and applies Redis-backed client rate-limiting.
2. **User Management Service (Port 8001)**: Manages users registration, credentials hashing (bcrypt), authentication, and Role-Based Access Control (RBAC) storing data in MongoDB.
3. **Product Catalogue Service (Port 8002)**: Standard product catalog queries, using Redis for query caching and storing collections in MongoDB. Image assets are hosted on an S3 Bucket.
4. **Order Processing Service (Port 8003)**: Places customer orders in MongoDB, publishing checkout events to Kafka.
5. **Payment Service (Port 8004)**: Consumes Kafka checkout events, performs transactional payment charges, commits records to a PostgreSQL database (retaining ACID consistency), and publishes success status.
6. **Inventory Management Service (Port 8005)**: Consumes Kafka checkouts, manages stock levels in MongoDB, caches counts in Redis, and emits low-stock alerts.
7. **Notification Service (AWS Lambda)**: A serverless function triggered by Event Queues. Broadcasts real-time notifications to the frontend via WebSockets.

---

## 📂 Repository Structure

```
SmartRetailX/
├── api-gateway/            # FastAPI API Gateway, rate limiting & auth proxy
├── user-service/           # FastAPI User registration & RBAC engine (MongoDB backend)
├── product-service/        # FastAPI Product Catalogue service (MongoDB & Redis backend)
├── order-service/          # FastAPI Order Service (MongoDB & Kafka backend)
├── payment-service/        # FastAPI Payment processor (PostgreSQL SQL backend)
├── inventory-service/      # FastAPI Inventory manager (MongoDB & Redis backend)
├── notification-service/   # AWS Lambda notification handler & WebSocket broadcast
├── frontend/               # Vite + React single-page dashboard application (Nginx multi-stage build)
├── k8s/                    # EKS Kubernetes deployments, services, Ingress, HPA, and databases
├── terraform/              # AWS Infrastructure blueprints (modular structure)
│   ├── main.tf
│   ├── vpc/                # Networking (VPC, Subnets, NAT, IGW)
│   ├── eks/                # EKS Cluster and Worker Nodes
│   ├── msk/                # Amazon MSK (Managed Kafka Broker)
│   ├── rds/                # Amazon RDS PostgreSQL instance
│   ├── elasticache/        # Amazon ElastiCache Redis Cluster
│   ├── documentdb/         # Amazon DocumentDB MongoDB cluster
│   ├── s3/                 # AWS S3 Bucket for website image assets
│   └── lambda/             # AWS Lambda and IAM Execution roles
├── tests/                  # Integration test suite (pytest) & load scripts (k6)
└── docs/                   # Assignment report, slides, and walkthrough.md
```

---

## 🚀 Getting Started (Local Development)

The entire microservice topology can be launched locally using Docker Compose, including Kafka, Redis, PostgreSQL, and MongoDB.

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ (optional, for running local script tests)
- Node.js (optional, for local frontend compilation)

### Quick Start
1. Clone the repository and navigate to the directory:
   ```bash
   cd SmartRetailX
   ```
2. Start all services using Docker Compose:
   ```bash
   docker-compose up --build
   ```
3. Open your browser and navigate to:
   - **Frontend UI Dashboard**: `http://localhost:5173`
   - **API Gateway Swagger Docs**: `http://localhost:8000/docs`
   - **Individual Swagger Docs**:
     - User Service: `http://localhost:8001/docs`
     - Product Service: `http://localhost:8002/docs`
     - Order Service: `http://localhost:8003/docs`
     - Payment Service: `http://localhost:8004/docs`
     - Inventory Service: `http://localhost:8005/docs`

---

## 🔒 Security & Identity Management (Task 3)

- **Authentication & Authorization**: Handled via JWT. Users log in via the User Service, which signs a JWT containing the user's role (`Customer`, `Manager`, or `Admin`).
- **Access Control**: The API Gateway inspects and verifies JWTs before routing to restricted endpoints (e.g. creating products requires `Manager`/`Admin` roles).
- **Encryption**: Standard TLS 1.3 is mapped on all ingress paths. Database passwords and credentials are injected into container environments via Kubernetes Secrets.

---

## ⚡ Event Processing & Real-Time Data (Task 4)

- **Kafka Stream Integration**: Order checkouts are asynchronously sent to the Kafka broker. Payment and Inventory services consume these messages, decouple dependencies, and process updates without halting the frontend.
- **WebSocket Updates**: The Notification Lambda pushes message streams back to active browser sessions using WebSocket gateways, creating immediate visual feedback.

---

## 🛠️ Infrastructure as Code (Terraform)

Deploy the infrastructure on AWS using the following command hierarchy in `/terraform`:
```bash
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```
Each AWS component is split into structured subfolders:
- `vpc/`: Creates multi-AZ subnets, Routing, and Nat Gateways.
- `eks/`: Deploys the Kubernetes cluster.
- `rds/`: Launches a PostgreSQL instance for payments.
- `documentdb/`: Launches a DocumentDB (MongoDB-compatible) cluster for core services.
- `s3/`: Configures public assets bucket.
- `elasticache/`: Spins up Redis for gateway rate limiting and catalog caches.
- `msk/`: Launches Managed Streaming for Apache Kafka.
- `lambda/`: Packages and deploys the Notification Lambda.

---

## 🧪 Testing & Validation

Run the end-to-end integration verification suite:
```bash
pip install -r tests/requirements.txt
pytest tests/
```
Run k6 load test:
```bash
k6 run tests/k6_load_test.js
```
