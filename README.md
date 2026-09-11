# 🚀 SmartRetailX: Cloud-Native Distributed Commerce Platform

<p align="center">
  <img src="https://img.shields.io/badge/AWS-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white" alt="AWS" />
  <img src="https://img.shields.io/badge/Kubernetes-326CE5?style=for-the-badge&logo=kubernetes&logoColor=white" alt="Kubernetes" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&logo=terraform&logoColor=white" alt="Terraform" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
</p>

SmartRetailX is a modern, enterprise-grade, event-driven microservices e-commerce platform built to replace legacy monolithic systems. It is engineered for high availability, multi-AZ security isolation, real-time transaction processing, and automated cloud scaling.

This repository hosts the complete source code, Infrastructure-as-Code (Terraform) configurations, Kubernetes manifests (EKS), automated tests, and deployment blueprints.

---

## 🏗️ System Architecture

The platform features a Vite+React frontend dashboard talking to a FastAPI API Gateway. The Gateway decrypts JWT signatures, controls client request rate limiting, and forwards traffic to decoupled, database-isolated microservices.

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

### ⚙️ Core Components:
1. **API Gateway (Port 8000)**: Singular ingress entrypoint. Manages API route mapping, handles **JWT Decryption & Verification**, and applies Redis-backed client rate-limiting.
2. **User Service (Port 8001)**: Handles registration, credential hashing (bcrypt), authentication, and Role-Based Access Control (RBAC) on MongoDB.
3. **Product Catalog Service (Port 8002)**: Catalogs inventory collections, using Redis queries caching. Image binaries reside on S3.
4. **Order Service (Port 8003)**: Places user purchases inside MongoDB, emitting `order-created` event streams to Apache Kafka.
5. **Payment Service (Port 8004)**: Decoupled transactional billing. Consumes Kafka orders, processes charges, updates a relational RDS PostgreSQL instance (guaranteeing ACID compliance), and publishes payment success events.
6. **Inventory Service (Port 8005)**: Decoupled warehouse manager. Tracks remaining counts, updates MongoDB, and publishes `low-stock-alert` triggers.
7. **Serverless Notifier (AWS Lambda & SQS)**: Operates serverless batch alerting using SQS triggers and SES email dispatching.
8. **EventBridge Scheduler**: Drives cron-scheduled operational checkups and compiles daily order transaction ledgers into PDF attachments.

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
├── notification-service/   # AWS Lambda notification handler, PDF generator, and SQS/EventBridge triggers
├── frontend/               # Vite + React single-page dashboard application (Nginx wrapper)
├── k8s/                    # EKS Kubernetes deployments, services, Ingress, HPA, and logging namespace config
├── terraform/              # AWS Infrastructure blueprints (modular structure)
│   ├── main.tf
│   ├── vpc/                # Multi-AZ subnets, NAT Gateways, Internet Gateway
│   ├── eks/                # EKS Cluster, node groups, and cluster policies
│   ├── msk/                # Amazon Managed Streaming for Apache Kafka
│   ├── rds/                # Amazon RDS PostgreSQL instance
│   ├── elasticache/        # Amazon ElastiCache Redis cluster
│   ├── documentdb/         # Amazon DocumentDB cluster
│   ├── s3/                 # AWS S3 Bucket for website image assets
│   └── lambda/             # AWS Lambda rules, EventBridge scheduler & IAM permission mappings
├── tests/                  # Pytest verification suites, Bruno collections, and k6 load tests
└── docs/                   # Walkthroughs, slides, network CIDRs, and API specifications
```

---

## 🔒 Security, Telemetry & Scheduling

### 🔑 JSON Web Tokens (JWT) & API Gateway Protection
* JWT keys containing user IDs, signatures, and roles (`Customer`, `Manager`, `Admin`) are created by the `user-service`.
* The API Gateway enforces signature authentication using a shared `JWT_SECRET`. Tampered tokens or mismatched algorithms (like `"alg": "none"` attacks) are immediately blocked with a `401 Unauthorized` status response.
* Check out the [API Endpoint Specifications](docs/api_specifications.md) for request/response payloads.

### 📅 Amazon EventBridge Scheduling
* **Low-Stock Triggers**: Intercepts custom events (`smartretailx.inventory`) on low stock thresholds and forwards them to the serverless notifier.
* **Daily Sales Summary Report**: Executes a cron schedule at **11:59 PM UTC** (`cron(59 23 * * ? *)`) to query order ledgers, programmatically compile a styled PDF document using ReportLab, and email it as a raw MIME attachment via SES.
* **System Health Check Cron**: Triggers a daily operational checkup at **12:00 PM UTC** (`cron(0 12 * * ? *)`).

### 📡 Telemetry & Observability
* Distributed tracing is implemented across all backend services utilizing **AWS X-Ray SDK**.
* Metrics and application logs are collected by the **AWS CloudWatch Agent** daemonset.

---

## 🚀 Getting Started

### Local Development (Docker Compose)
You can launch the entire microservice topology locally, including Kafka, Redis, PostgreSQL, and MongoDB:

1. Clone the repository and navigate to the directory:
   ```bash
   cd SmartRetailX
   ```
2. Start all services using Docker Compose:
   ```bash
   docker-compose up --build
   ```
3. Open your browser:
   * **Frontend UI Dashboard**: `http://localhost:5173`
   * **API Gateway Swagger Docs**: `http://localhost:8000/docs`
   * **Individual Service Swagger Docs**:
     * User Service: `http://localhost:8001/docs`
     * Product Service: `http://localhost:8002/docs`
     * Order Service: `http://localhost:8003/docs`
     * Payment Service: `http://localhost:8004/docs`
     * Inventory Service: `http://localhost:8005/docs`

---

## 🛠️ AWS Production Deployment

### 1. Provision Infrastructure (Terraform)
Deploy the AWS cloud resources using the Terraform module:
```bash
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply "tfplan"
```

### 2. Build & Push ECR Images
Authenticate your Docker CLI and build/push your microservice containers:
```bash
aws ecr get-login-password --region us-east-1 --profile your-profile | docker login --username AWS --password-stdin your-registry.dkr.ecr.us-east-1.amazonaws.com
# Build and push using local build tools
```

### 3. Deploy Workloads to EKS (Kubernetes)
Update your local kubeconfig context and apply the manifest configurations:
```bash
aws eks update-kubeconfig --name smartretailx-eks-prod --region us-east-1 --profile your-profile
kubectl create namespace amazon-cloudwatch
kubectl apply -f k8s/
```

---

## 🧪 Testing & Validation

Run the pytest integration verification suite:
```bash
pip install -r tests/requirements.txt
pytest tests/
```

### Performance & Load Testing
The platform supports load and stress testing using both **k6** and **Apache JMeter**. Detailed setup and comparisons are documented in the [Performance Testing Guide](docs/performance_testing_guide.md).

* **k6 load test**:
  ```bash
  k6 run tests/k6_load_test.js
  ```
* **Apache JMeter load test**:
  ```bash
  jmeter -n -t tests/jmeter_load_test.jmx -l tests/jmeter_results.jtl -JGATEWAY_HOST=localhost -JGATEWAY_PORT=8000
  ```
