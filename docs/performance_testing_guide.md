# SmartRetailX Performance Testing Guide (k6 vs. Apache JMeter)

This guide provides a detailed overview of the performance testing suite configured for the SmartRetailX Global Commerce Platform. It details the design, execution, and verification steps for both **k6 by Grafana** and **Apache JMeter**.

---

## Prerequisites & Installation

To run these performance tests, ensure the tooling is installed on your local machine.

### Installing k6 on Windows
- **Using winget (Built-in on Windows 10/11)**:
  ```powershell
  winget install k6
  ```
- **Using Chocolatey**:
  ```powershell
  choco install k6
  ```
- **Manual Installation**: Download the MSI installer from the [k6 GitHub Releases Page](https://github.com/grafana/k6/releases).

### Installing Apache JMeter on Windows
- **Using winget**:
  ```powershell
  winget install DEVCOM.JMeter
  ```
- **Using Chocolatey**:
  ```powershell
  choco install jmeter
  ```
- **Manual Installation**:
  1. Ensure Java (JDK 8+) is installed on your system.
  2. Download the binary `.zip` package from the [Apache JMeter Download Page](https://jmeter.apache.org/download_jmeter.cgi).
  3. Extract the archive and add the `bin` folder path (e.g. `C:\apache-jmeter-5.5\bin`) to your system's environment `PATH` variable.

---

## 1. Performance Testing Overview

Performance testing is used to ensure the API Gateway and underlying downstream microservices can handle traffic under expected load (Load Testing) and identify the limits of the infrastructure under peak spikes (Stress Testing).

### The Load Profile

Both tools are configured to simulate the exact same user profile:

```
  50 VUs |                                  /-----------------\
         |                                 /                   \
  20 VUs |             /------------------/                     \
         |            /                                          \
   0 VUs +-----------+-------------------+-------------------+-----+
        0s          30s                 1m30s               2m    2m30s
                   [Ramp]    [Plateau]        [Stress Spike]   [Cooldown]
```

- **Ramp-up (0s - 30s)**: Users scale linearly from 0 to 20.
- **Load Plateau (30s - 1m30s)**: Maintains 20 concurrent users to verify stability under normal peak load.
- **Stress Spike (1m30s - 2m)**: Ramps up rapidly from 20 to 50 concurrent users to test autoscaling capacity.
- **Cooldown (2m - 2m30s)**: Ramps back down to 0 users.

---

## 2. Tested Endpoints & Simulation Logic

The test scripts validate the system by simulating a customer browsing the store with a **1-second think-time** between actions.

| Step | Request Type | Target Endpoint | Validation Checks (Assertions) | Purpose |
|---|---|---|---|---|
| **1** | `GET` | `/healthz` | HTTP Status = `200`<br>JSON body `status` = `"healthy"` | Validate gateway health & downstream routing. |
| **2** | `GET` | `/api/v1/products` | HTTP Status = `200`<br>Returns list with size > `0` | Verify catalog database retrieval & Redis caching. |
| **3** | `Sleep` | N/A (1 second delay) | N/A | Simulate real-world human user thinking delay. |

---

## 3. Tool Comparison: k6 vs. JMeter

| Feature | k6 (by Grafana) | Apache JMeter |
|---|---|---|
| **Core Language** | Go (Scripts written in ES6 JavaScript) | Java (Test plans configured via XML/GUI) |
| **Footprint** | Extremely lightweight; low CPU/RAM footprint. | Medium; JVM-based, consumes more memory. |
| **Configuration** | Code-first (`.js` files), version-control friendly. | XML-first (`.jmx` files), config-driven. |
| **Best Used For** | Continuous Integration (CI/CD), CLI developer automation. | Reporting, enterprise standards, GUI test building. |
| **Reporting** | CLI stdout, JSON export, Grafana Cloud integration. | XML results (`.jtl`), HTML Dashboard report generator. |

---

## 4. Guide to k6 Load Testing

The k6 test is located in [k6_load_test.js](file:///c:/Users/dissa/SmartRetailX/tests/k6_load_test.js).

### Running the k6 Test

Execute the test in your terminal:
```bash
k6 run tests/k6_load_test.js
```

### Overriding the Target Host
To test a remote deployment (e.g., staging/production Kubernetes cluster), pass the `GATEWAY_URL` environment variable:
```bash
k6 run -e GATEWAY_URL=http://your-remote-gateway-ip:8000/api/v1 tests/k6_load_test.js
```

### What to Look For in the Output
When the test completes, check the summary metrics printed in the console:
- **`http_req_duration`**: Look at the `p(95)` value. Our target is `< 200ms`.
- **`http_req_failed`**: Shows the request failure rate. Our target is `< 1%` (ideally `0.00%`).
- **`checks`**: Confirms that 100% of the assertions on `/healthz` and `/products` passed.

---

## 5. Guide to Apache JMeter Testing

The JMeter test plan is located in [jmeter_load_test.jmx](file:///c:/Users/dissa/SmartRetailX/tests/jmeter_load_test.jmx).

### Running the JMeter Test

JMeter tests should always be run in CLI/Non-GUI mode for accurate results:
```bash
jmeter -n -t tests/jmeter_load_test.jmx -l tests/jmeter_results.jtl
```
- `-n`: Runs JMeter in non-GUI (command line) mode.
- `-t`: Path to the input test plan (`.jmx`).
- `-l`: Path to save the raw results CSV/XML log (`.jtl`).

### Overriding the Target Host
Pass JVM properties to override the defaults (`localhost` and `port 8000`):
```bash
jmeter -n -t tests/jmeter_load_test.jmx -l tests/jmeter_results.jtl -JGATEWAY_HOST=10.0.0.5 -JGATEWAY_PORT=8000
```

### Generating an HTML Dashboard Report
One of JMeter's strongest features is generating high-quality HTML report dashboards from the `.jtl` log. Run this command after the test completes:
```bash
jmeter -g tests/jmeter_results.jtl -o tests/jmeter_report/
```
Open `tests/jmeter_report/index.html` in any web browser to view:
- Overtime response time percentiles.
- Throughput (Transactions per second).
- Active threads / virtual users count graphs.
- Latency and assertion failure breakdowns.

---

## 6. How to Verify the Test is Working Locally

To verify both tests without impacting production infrastructure:
1. Spin up the platform locally:
   ```bash
   docker-compose up --build
   ```
2. Trigger the k6 test to verify the local gateway is reachable:
   ```bash
   k6 run tests/k6_load_test.js
   ```
3. Run the JMeter command to ensure the XML matches and execution begins:
   ```bash
   jmeter -n -t tests/jmeter_load_test.jmx -l tests/jmeter_results.jtl
   ```
4. Confirm both tools report `0%` error rates and average response times under `20ms` under local configuration.
