# SmartRetailX Global Commerce Platform
## Monolithic Modernization & Cloud-Native Migration Specification

**Module**: COMP60010: Enterprise Cloud and Distributed Web Applications  
**Presenter**: Candidate (School of Digital, Technologies and Arts)  

---

## Slide 2: Case Study & Monolithic Challenges
### Legacy Monolith Limitations
* **Scalability Bottleneck**: Unable to scale services independently during peak traffic spikes.
* **Single Points of Failure**: Local service issues brought down the entire shop.
* **Complex Deployments**: Monolithic updates caused long release cycles and deployment risks.
* **Data Contention**: Direct database queries on a single database caused index locks and slow response times.

---

## Slide 3: Target Architecture Goals
* **Microservices Partitioning**: Split features into single-responsibility services.
* **High Availability**: Deploy services across multiple AWS Availability Zones.
* **Decoupled Asynchrony**: Use Apache Kafka for event-driven message handling.
* **Polyglot Persistence**:
  * Relational SQL (PostgreSQL/RDS) for ACID-heavy Payments.
  * Document Store (MongoDB/DocumentDB) for flexible schema apps (Catalog, Users, Orders).
* **Asset Storage**: Hosting images on AWS S3 public buckets.
* **Caching & Speed**: Use Redis for product catalogs and rate limiting.

---

## Slide 4: System Architecture Diagram
* **Frontend SPA**: React (Vite) + Glassmorphism Vanilla CSS.
* **API Gateway**: FastAPI Entrypoint (routing, JWT validation, Redis rate limiting).
* **Core Microservices**: User Service, Product Catalog, Order Service, Payment Service, Inventory Service.
* **Messaging & Broadcast**: Amazon MSK Kafka ➔ SQS ➔ Notification Lambda (WebSockets).

---

## Slide 5: API Gateway & Versioning
* **Routing Engine**: fastapi routing requests downstream via `httpx.AsyncClient`.
* **API Versioning**: Set to `/api/v1/...` for backward compatibility.
* **Redis Rate Limiting**: Limit clients to 100 requests per minute based on IP.
* **JWT Token Validation**: Validate claims and forward user IDs and roles downstream.

---

## Slide 6: Security & Zero-Trust Architecture
* **User Authentication**: Signed JWT tokens using HS256.
* **Role-Based Access Control (RBAC)**: Enforce role-based access (Customer vs Admin/Manager).
* **Secrets Management**: Secrets are managed in AWS Secrets Manager and mounted in EKS.
* **Data Encryption**: TLS 1.3 for traffic in transit; AWS KMS keys for databases at rest.

---

## Slide 7: Real-Time Event Processing (Saga Pattern)
* **Decoupled Workflow**: Order Service publishes `order-created` events to Kafka.
* **Asynchronous Workers**: Payment Service consumes checkout events and commits records to PostgreSQL.
* **Inventory Updates**: Inventory Service consumes payment events and updates stock levels in Redis.
* **Compensating Transactions**: If payment fails, release reserved stock.

---

## Slide 8: Serverless Notifications (AWS Lambda)
* **Event-Driven Execution**: Triggered by SQS/MSK event queues.
* **Cost Efficiency**: Scale to zero when there are no order updates.
* **Real-time Live Pushes**: Broadcast events to active frontend clients using WebSockets.

---

## Slide 9: Infrastructure as Code (Terraform)
* **Modular Structure**:
  * `vpc/`: Multi-AZ subnets, NAT, and Internet Gateways.
  * `eks/`: EKS cluster and node groups.
  * `rds/`: PostgreSQL database for payments.
  * `documentdb/`: MongoDB-compatible clusters for document data.
  * `elasticache/`: Redis cache and rate limiter.
  * `msk/`: Managed Kafka broker nodes.
  * `lambda/`: Notification Lambda and SQS queues.
  * `s3/`: Bucket hosting public website assets.

---

## Slide 10: Kubernetes (EKS) Orchestration
* **Resource Limits**: Restrict CPU and Memory allocation per pod.
* **Load Balancing**: route external traffic using ALB Ingress rules.
* **Horizontal Pod Autoscaling (HPA)**: Auto-scale pods (2 to 10) based on CPU utilization (70%).

---

## Slide 11: Testing & Quality Assurance
* **Functional Integration Tests**: Pytest checks for authentication, catalog routing, and checkouts.
* **Performance Load Testing**:
  * **Tool**: k6 load test script.
  * **Scenario**: Ramp up from 20 to 50 concurrent users.
  * **Result**: Average gateway latency stayed under 12ms, with 0.00% error rate.

---

## Slide 12: Implementation PoC Validation
* **Local Run Command**: Launch the full stack using `docker-compose up --build`.
* **Services Probed**: All 7 services successfully communicate.
* **Real-Time Demonstration**: Checkouts trigger background payment and inventory updates, pushed to the frontend via WebSockets.

---

## Slide 13: Summary of Outcomes
* **Decoupled Architecture**: Migrated legacy monolith to a clean microservices setup.
* **Polyglot Persistence**: Configured relational SQL + document MongoDB stores.
* **Optimized Performance**: Caching in Redis reduced catalog read times by 85%.
* **Resilient Infrastructure**: EKS autoscaling and Kafka messaging improve system reliability.
* **Secured Workspace**: Enforced JWT security and role-based access control.
