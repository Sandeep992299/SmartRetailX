# SmartRetailX — AWS Production Deployment Guide

This guide provides step-by-step instructions to provision the production infrastructure on AWS and deploy the SmartRetailX microservices stack.

---

## 📋 Prerequisites

Ensure you have the following installed on your machine:
* [AWS CLI](https://aws.amazon.com/cli/)
* [Terraform CLI](https://developer.hashicorp.com/terraform/downloads)
* [Docker Desktop](https://www.docker.com/products/docker-desktop/)
* [kubectl](https://kubernetes.io/docs/tasks/tools/)

---

## 🚀 Step 1: Configure AWS CLI Credentials

The deployment uses the `aquasense` profile mapping to account `595529181954`. Configure the profile with your access keys:

```powershell
aws configure --profile aquasense
```
* **AWS Access Key ID**: `AKIAXXXXXXXXXXXXXXXX` (or your latest key)
* **AWS Secret Access Key**: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (or your latest secret)
* **Default region name**: `us-east-1`
* **Default output format**: `json`

Verify authorization:
```powershell
aws sts get-caller-identity --profile aquasense
```

---

## 🛠️ Step 2: Provision AWS Infrastructure via Terraform

1. Navigate to the terraform directory:
   ```powershell
   cd C:\Users\dissa\SmartRetailX\terraform
   ```
2. Initialize provider plugins and modules:
   ```powershell
   terraform init
   ```
3. Validate syntax and configuration rules:
   ```powershell
   terraform validate
   ```
4. Create and inspect the execution plan:
   ```powershell
   terraform plan -out=tfplan
   ```
5. Apply the plan to provision the resources (takes ~15–20 minutes):
   ```powershell
   terraform apply tfplan
   ```

Upon completion, Terraform will output the **ECR Repository URLs**, **EKS Cluster Endpoint**, and the **API Gateway Stage Endpoint**.

---

## 📦 Step 3: Build & Push Docker Images to Amazon ECR

Before EKS can start the pods, you must build and push the container images to ECR.

1. **Login Docker to the ECR Registry**:
   ```powershell
   aws ecr get-login-password --region us-east-1 --profile aquasense | docker login --username AWS --password-stdin 595529181954.dkr.ecr.us-east-1.amazonaws.com
   ```

2. **Build and Push the Frontend and Services** (run from `C:\Users\dissa\SmartRetailX`):
   ```powershell
   cd C:\Users\dissa\SmartRetailX

   # User Service
   docker build -t 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-user-service:v1.0.0 ./user-service
   docker push 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-user-service:v1.0.0

   # Product Service
   docker build -t 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-product-service:v1.0.0 ./product-service
   docker push 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-product-service:v1.0.0

   # Order Service
   docker build -t 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-order-service:v1.0.0 ./order-service
   docker push 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-order-service:v1.0.0

   # Payment Service
   docker build -t 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-payment-service:v1.0.0 ./payment-service
   docker push 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-payment-service:v1.0.0

   # Inventory Service
   docker build -t 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-inventory-service:v1.0.0 ./inventory-service
   docker push 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-inventory-service:v1.0.0

   # Notification Service
   docker build -t 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-notification-service:v1.0.0 ./notification-service
   docker push 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-notification-service:v1.0.0

   # Frontend Web App
   docker build -t 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-frontend:v1.0.0 ./frontend
   docker push 595529181954.dkr.ecr.us-east-1.amazonaws.com/smartretailx-frontend:v1.0.0
   ```

---

## ☸️ Step 4: Configure Kubectl for EKS

1. Update your local kubeconfig to point to the newly created EKS cluster:
   ```powershell
   aws eks update-kubeconfig --name smartretailx-eks-prod --region us-east-1 --profile aquasense
   ```
2. Verify connection to the cluster:
   ```powershell
   kubectl get nodes
   ```
   *(Ensure both worker nodes show `STATUS: Ready`)*

---

## ⛵ Step 5: Deploy Resources to Kubernetes (EKS)

1. Create the dedicated `smartretailx` namespace:
   ```powershell
   kubectl apply -f k8s/namespace.yaml
   ```
2. Apply the Console AWS Root session access permission patch:
   ```powershell
   kubectl apply -f k8s/aws-auth-patch.yaml
   ```
3. Deploy all workloads (Databases, Message Queues, Microservices, and Ingress):
   ```powershell
   kubectl apply -f k8s/ --namespace=smartretailx
   ```
4. Verify the pods have successfully started up:
   ```powershell
   kubectl get pods -n smartretailx -w
   ```

---

## 🌐 Step 6: Connect EKS to AWS API Gateway (Post-Teardown)

Because of initial load balancer limits on new AWS accounts, the private Network Load Balancer (NLB) resources inside `apigateway.tf` are commented out. To fully link your public API Gateway to the EKS cluster:

1. Open a **Service Limit Increase Case** in the AWS Support console for *Elastic Load Balancers* in `us-east-1`.
2. Once approved, open `terraform/apigateway.tf` and **uncomment the `aws_lb.eks_internal`** block.
3. Replace the `local.nlb_host` value in `apigateway.tf` with your NLB DNS name output.
4. Run `terraform apply` again to wire the Gateway stage routing directly into your EKS microservices.

---

## 🛡️ Step 7: Configure CloudFront CDN for the Frontend Website

The CloudFront CDN distribution is configured in `cloudfront.tf` to route public dynamic client web requests and WebSocket endpoints to your EKS Application Load Balancer (ALB).

Since the EKS ALB Ingress DNS is created dynamically by the Kubernetes controller, follow these steps to wire it into CloudFront:

1. Retrieve the public DNS name of your EKS Application Load Balancer:
   ```powershell
   kubectl get ingress smartretailx-ingress -n smartretailx -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
   ```
   *(Wait a few minutes if the hostname is empty; AWS ALB takes 2-3 mins to provision).*

2. Re-run `terraform apply`, passing the ALB DNS name as a variable:
   ```powershell
   cd C:\Users\dissa\SmartRetailX\terraform
   terraform apply -var="eks_ingress_dns=<YOUR_ALB_INGRESS_DNS_NAME>" -auto-approve
   ```

3. Once complete, CloudFront will output a new **`cloudfront_domain_name`** (e.g. `d123456789.cloudfront.net`). Users can now access the full production website securely over HTTPS via the global CDN!

