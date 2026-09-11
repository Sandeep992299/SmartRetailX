# 📊 SmartRetailX Platform: Core Presentation Outline

This document provides a slide-by-slide structure, visual layout suggestions, and speaker notes for a **12-slide presentation** aligned with the official 9-point agenda for the SmartRetailX cloud-native platform project.

---

### Slide 1: Title Slide
* **Title**: SmartRetailX: Cloud-Native Distributed Commerce Platform
* **Subtitle**: Architecting an Event-Driven, Secure, and Scalable Microservice Topology on AWS
* **Presenter Info**: Sandeep Dissanayake
* **Visual Suggestion**: A high-tech dark theme displaying EKS, Terraform, and AWS logos.
* **Speaker Notes**: Welcome everyone. Today we are presenting SmartRetailX, a modern commerce engine designed to replace a legacy retail monolith. This presentation will cover our structural choices on AWS, container management, polyglot databases, Kafka event mesh, managed ingress gateways, and our testing validation.

---

### Slide 2: Presentation Agenda
* **Title**: Agenda
* **Visual Suggestion**: The 9-item grid matching your slide image:
  * **01** Monolith Migration: Objectives & Benefits
  * **02** High-Level System Architecture
  * **03** Compute Orchestration via Kubernetes
  * **04** Decoupled Polyglot Database Design
  * **05** Event Streaming with Managed Kafka
  * **06** Centralized API Gateway Ingress
  * **07** Authentication and RBAC
  * **08** Testing Methodology
  * **09** Cost & Resource Optimization
* **Speaker Notes**: Here is our agenda. We'll start with our migration goals and high-level architecture. Then we will dive into compute, database, and event messaging. Finally, we'll cover the API Gateway, auth, performance testing, and AWS resource cost optimizations.

---

### Slide 3: Topic 01 — Monolith Migration: Objectives & Benefits
* **Title**: Monolith Migration: Objectives & Benefits
* **Visual Suggestion**: A split-screen graphic: legacy monolith on the left, decoupled microservices on the right.
* **Key Points**:
  * **Domain Decoupling**: Deconstructing the monolith into 5 isolated FastAPI microservices.
  * **Database-per-Service**: Eliminates shared-state locking and database single points of failure.
  * **Failure Isolation**: Keeps query/catalog services alive even if transactional services (like Payments) crash.
  * **Targeted Elasticity**: Scales specific container pods (e.g. Catalog) without duplicating the entire platform resource footprint.
* **Speaker Notes**: Our legacy monolith faced severe bottlenecks during peak sales, where database lockouts on the unified database brought down the entire shop. By migrating to a database-per-service microservice pattern, we isolate failures and scale only the services experiencing traffic spikes.

---

### Slide 4: Topic 02 — High-Level System Architecture
* **Title**: High-Level System Architecture
* **Visual Suggestion**: A simplified block diagram mapping Route 53/CloudFront $\rightarrow$ API Gateway v2 $\rightarrow$ EKS Cluster (Private subnets) $\rightarrow$ Polyglot Databases & MSK Kafka.
* **Key Points**:
  * **Edge Layer**: Route 53 DNS and CloudFront CDN serve static React SPA assets from S3.
  * **API Ingress**: Managed API Gateway HTTP API v2 routes traffic to EKS.
  * **EKS Compute**: Microservice pods run in private subnets across Multi-AZ.
  * **Asynchronous Event Mesh**: MSK Apache Kafka coordinates checkout processing.
  * **Serverless Notifications**: SQS-triggered Lambda sends out email and Slack alerts.
* **Speaker Notes**: This is the top-level view of our AWS system. Public ingress is guarded by Route 53 and CloudFront. Dynamically routed API calls enter EKS via our HTTP API Gateway, while background events are handled asynchronously by Amazon MSK. Critical alerts are offloaded to an SQS-triggered VPC Lambda function to save container resources.

---

### Slide 5: Topic 03 — Compute Orchestration via Kubernetes (EKS Cluster details)
* **Title**: Why Amazon EKS?
* **Visual Suggestion**: A three-column grid layout (Deployment & Cluster Reliability, Granular Architectural Control, Financial Efficiency) with a prominent full-width colored box at the bottom containing the Selection Verdict.
* **Key Points**:
  * **Deployment & Cluster Reliability**:
    * Accommodates our multiple persistent API gateway and backend services.
    * Enables decoupled continuous deployment tracks and targeted replica scaling.
    * High-availability distribution of pods and compute nodes across Availability Zones.
    * Zero-downtime rolling upgrades and self-healing container lifecycles (automatic container restarts).
  * **Granular Architectural Control**:
    * Fine-grained scheduling limits and custom pod resource constraints (CPU/Memory limits).
    * Automated horizontal pod scaling (HPA) driven by real-time resource utilization.
    * Seamless metrics ingestion with native Prometheus scraping and Grafana dashboarding.
    * Cloud-agnostic manifest specifications enabling hybrid environment portability.
  * **Financial Efficiency**:
    * Consolidates container workloads onto shared EC2 instance capacity.
    * Optimal container bin-packing to maximize underlying hardware usage.
    * Compatible with discounted EC2 Spot Instances and Compute Savings Plans.
    * Scalability roadmap using Karpenter for sub-minute EC2 worker provisioning.
  * **Selection Verdict**:
    * EKS was selected to ensure fine-grained scaling optimizations and control over scheduling policies. While Fargate reduces operational overhead, it limits our configuration and cost-efficiency tuning for this persistent multi-service workload.
* **Speaker Notes**: When selecting our compute orchestration model, we evaluated both ECS Fargate and Amazon EKS. We chose EKS because of three main pillars: Deployment & Cluster Reliability, Granular Architectural Control, and Financial Efficiency. For reliability, it manages our multiple microservices with automatic pod restarts and rolling updates. Architecturally, it gives us deep scheduling control and native monitoring integrations. For efficiency, EKS enables us to bin-pack containers on shared EC2 nodes to maximize hardware use, with support for Spot instances and Karpenter. Ultimately, while Fargate is simpler to operate, EKS gives us the long-term scalability and fine-grained optimization flexibility needed for our commerce engine.

---

### Slide 6: Topic 04 — Decoupled Polyglot Database Design
* **Title**: Purpose-Built Data Strategy
* **Visual Suggestion**: A split-slide layout displaying a structured comparison table on the left, and a visual flowchart of the asynchronous data flow on the right, underlined by a clean horizontal ribbon displaying the Design Principles.
* **Key Points**:
  * **Database Selection Matrix**:
    | Service | Data Store | Primary Responsibility |
    | :--- | :--- | :--- |
    | **Amazon RDS PostgreSQL** | Relational | Payments, invoices and financial ledger integrity |
    | **Amazon DocumentDB** | NoSQL (Document) | Users, products, carts, orders and inventory datasets |
    | **Amazon ElastiCache Redis** | In-Memory | Frequently accessed cache data and low-latency API rate-limiting |
    | **Amazon S3** | Object Storage | Invoice PDFs, product media, and static application assets |
  * **Data Flow Pipeline**:
    * `Microservice` ➔ `Owned Data Store` ➔ `Domain Event (MSK)` ➔ `Other Services`
  * **Design Principles**:
    * `ACID transactions` • `Independent ownership` • `Managed scaling` • `Encryption` • `Automated backup`
* **Speaker Notes**: For SmartRetailX, we designed a purpose-built data strategy matching database engines to specific domain needs. As shown in the table, payments are stored in RDS PostgreSQL to guarantee transactional ACID compliance. Non-relational datasets like users, products, and checkouts reside in DocumentDB for high schema flexibility. Frequently read data is cached in ElastiCache Redis to achieve sub-millisecond speeds, while static images and invoice PDFs are offloaded to S3. To keep services decoupled, data flows from a microservice to its owned datastore, which then triggers a domain event on Kafka to update secondary stores asynchronously.

---

### Slide 7: Topic 05 — Event Streaming with Managed Kafka
* **Title**: Event Streaming with Managed Kafka (Amazon MSK)
* **Visual Suggestion**: Process flow showing: Order Service $\rightarrow$ MSK (order-events) $\rightarrow$ Payment Service $\rightarrow$ MSK (payment-events) $\rightarrow$ Inventory Service.
* **Key Points**:
  * **Amazon MSK Event Hub**: Fully managed Apache Kafka brokers in private subnets.
  * **Choreographed Saga Pattern**: Coordinates distributed transactions without resource locking.
  * **Topic Topology**: Partitions configured for concurrent scaling (`order-events` and `payment-events` have 3 partitions).
  * **Compensating Transactions**: Automatic stock release if a `payment-failed` event is emitted.
* **Speaker Notes**: Distributed checkouts use the Saga Pattern to maintain eventual consistency. When an order is placed, the Order Service writes a pending record and posts an event to Kafka. The Payment Service consumes it, charges the card, and emits a settled event. The Inventory Service then consumes that event to decrement stock. If payment fails, a compensating event is published to release reserved stock.

---

### Slide 8: Topic 06 — Centralized API Gateway Ingress
* **Title**: Centralized API Gateway Ingress
* **Visual Suggestion**: Diagram showing API Gateway sitting outside the VPC, routing traffic through a VPC Link to the EKS private node network.
* **Key Points**:
  * **AWS API Gateway v2**: Managed serverless HTTP gateway residing in the AWS Public network.
  * **VPC Link Integration**: Connects the managed gateway to EKS private subnets via secure ENI endpoints.
  * **Route Mappings & NodePorts**: Translates path routing directly to EKS node ports (e.g. `30081` to `30085`).
  * **Managed Protection**: Offloads throttling and burst limits from downstream microservices.
* **Speaker Notes**: Our ingress routes are secured using AWS API Gateway v2. Rather than exposing EKS nodes directly to the internet, we route dynamic APIs via an API Gateway VPC Link. The VPC Link maps ingress paths to private NodePorts. This isolates EKS worker ports from public traffic.

---

### Slide 9: Topic 07 — Authentication and RBAC
* **Title**: Identity & Access Control Security
* **Visual Suggestion**: A three-column grid layout (User Identity Security, Stateless Token Strategy, Authorization Rules) with a prominent full-width colored ribbon at the bottom containing the Zero-Trust Security Statement.
* **Key Points**:
  * **User Identity Security**:
    * Password credentials hashed and salted using Bcrypt (rounds: 12).
    * User credentials stored securely in private MongoDB/DocumentDB collections.
    * Login endpoints rate-limited at the Gateway layer to mitigate brute-force attacks.
  * **Stateless Token Strategy**:
    * FastAPI user-service signs secure tokens upon successful login verification.
    * Uses strict `HS256` signature algorithm; unauthorized `"alg": "none"` payloads are rejected.
    * JWT payload contains stateless metadata: User ID, Email, and Role claim.
  * **Authorization Rules (RBAC)**:
    * Centralized JWT validation executed at the AWS API Gateway v2 layer.
    * Role permissions mapped directly: `Customer` (read-only), `Manager` / `Admin` (write/delete).
    * Restrictive endpoints (e.g., product creation, stock updates) block access if claims fail.
  * **Zero-Trust Security Statement**:
    * All inter-service communications operate on zero-trust. Verified user context is forwarded across the VPC Link via headers (`X-User-Id`, `X-User-Role`), preventing role escalation inside the private EKS network.
* **Speaker Notes**: Security on SmartRetailX is built on a Zero-Trust approach. User credentials are encrypted using Bcrypt and stored in DocumentDB. Upon login, the user-service issues a signed JWT. When subsequent API requests enter the API Gateway, the gateway cryptographically verifies the token's signature. If the user attempts to perform restricted actions—such as a Customer attempting to delete inventory—the gateway inspects the role claim and blocks the request immediately. This prevents invalid traffic from ever consuming EKS node compute or database connection resources.

---

### Slide 10: Topic 08 — Testing Methodology
* **Title**: Testing & Verification Methodology
* **Visual Suggestion**: A graph showing load testing thread execution, mapping Virtual Users ramping up to 20, plateauing, spiking to 50, and cooling down.
* **Key Points**:
  * **JMeter Load Scripts**: Runs multi-threaded performance testing scenarios (registration, login, catalog queries, checkouts).
  * **Functional Testing**: Pytest suite validates routes, token claims, and DB validations.
  * **Unique Email Validation**: Confirms user uniqueness checks return `400 Bad Request` under load.
  * **Latency Metrics**: Validates that 95% of queries complete under 12ms under heavy load.
* **Speaker Notes**: We validated system throughput using Apache JMeter and Pytest. The tests simulated concurrent checkout loops. Results showed 100% database integrity under concurrency (such as blocking duplicate email registrations with a 400 response), and confirmed cache hits on Redis dropped product catalog loading times to under 3ms.

---

### Slide 11: Topic 09 — Cost & Resource Optimization
* **Title**: Cost & Resource Optimization
* **Visual Suggestion**: A split-screen dashboard layout. The left side displays the **AWS Pricing Calculator Estimate Summary** showing upfront and monthly costs, alongside the **Major Cost Drivers** breakdown. The right side outlines the **Cost Optimisation Tactics** and the **Future Roadmap** (Graviton, Karpenter, Spot capacity).
* **Key Points**:
  * **AWS Pricing Calculator Estimate (Europe London Region)**:
    * **Upfront Cost**: `$0.00 USD`.
    * **Monthly Cost**: `$493.80 USD`.
    * **Total 12-Month Cost**: `$5,925.60 USD`.
  * **Detailed Service Monthly Costs**:
    * **Amazon ElastiCache (Redis)** — `$107.31 USD` | `21.7%`
    * **Amazon Managed Streaming for Kafka (MSK)** — `$98.68 USD` | `20.0%`
    * **Amazon EKS (Control Plane)** — `$73.00 USD` | `14.8%`
    * **Amazon EC2 (t3a.medium nodes under Compute Savings Plan)** — `$18.10 USD` | `3.7%`
    * **Other Services** (RDS PostgreSQL, ALBs, CloudWatch, NAT Gateways, WAF) — `$196.71 USD` | `39.8%`
  * **Cost Optimisation**:
    * **Bounded HPA**: Scaled limits to `2–5` pods for dev testing.
    * **Networking Consolidation**: Single development NAT Gateway instead of Multi-AZ NATs.
    * **Data Store Lifecycle policies**: Set TTL (Time to Live) on cache data and S3 Glacier tiering policies.
    * **Log Retentions**: CloudWatch log group retention capped at **fourteen-day** limits.
  * **Future Capacity Plan**:
    * Transition to AWS Graviton processors, Karpenter node auto-scaling, and EC2 Spot capacity integration.
* **Speaker Notes**: To keep our staging and development environment cost-effective, we modeled our environment using the AWS Pricing Calculator for the Europe (London) region. The estimate shows zero upfront cost, a monthly cost of $493.80, and a 12-month total of $5,925.60. The primary cost drivers are Amazon ElastiCache at $107.31 and Amazon MSK at $98.68. The EKS control plane has a flat fee of $73.00, and our EC2 worker nodes cost $18.10 under a 3-year Compute Savings Plan. The remainder covers RDS databases, public load balancers, and CloudWatch metrics. To optimize these costs, we limit pod scaling to 2-5 instances, run a single NAT gateway, and enforce a 14-day CloudWatch log retention. In the future, we can lower compute costs further by adopting Graviton nodes and Karpenter.

---

### Slide 12: Summary & Conclusion
* **Title**: Project Retrospective & Key Takeaways
* **Visual Suggestion**: A checklist highlighting completed goals: Decoupled Monolith, Secure JWTs, Active Event Mesh, and Load Tested.
* **Key Points**:
  * **Monolith Successfully Decomposed**: 5 independent services with isolated DBs.
  * **Fully Event-Driven**: MSK Kafka asynchronously processes checkouts.
  * **Zero-Trust VPC Network**: Managed gateway, VPC Link, and Multi-AZ subnet topology.
  * **Validated Performance**: 95% of requests completed under 12ms.
* **Speaker Notes**: In conclusion, the SmartRetailX platform demonstrates a resilient cloud-native architecture. We have successfully broken down the monolith, secured our network with VPC isolation, built an event mesh using Kafka, and verified our setup under stress. Thank you, and I am happy to take any questions.
