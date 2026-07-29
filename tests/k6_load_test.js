import http from 'k6/http';
import { sleep, check } from 'k6';

// ----------------------------------------------------
// k6 Load Test Configuration (Tasks 6 - Performance Testing)
// ----------------------------------------------------
export const options = {
  stages: [
    { duration: '30s', target: 20 },  // Ramp-up to 20 concurrent users
    { duration: '1m', target: 20 },   // Maintain 20 users for 1 minute
    { duration: '30s', target: 50 },  // Spike load to 50 users (Stress testing)
    { duration: '1m', target: 50 },   // Maintain 50 users
    { duration: '30s', target: 0 },   // Ramp-down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'], // 95% of requests must complete under 200ms (Gateway Latency Standard)
    http_req_failed: ['rate<0.01'],   // Error rate should be less than 1%
  },
};

const BASE_URL = __ENV.GATEWAY_URL || 'http://localhost:8000/api/v1';

export default function () {
  // Test baseline health endpoint
  const healthRes = http.get('http://localhost:8000/healthz');
  check(healthRes, {
    'healthz status is 200': (r) => r.status === 200,
    'healthz contains status healthy': (r) => r.json().status === 'healthy',
  });

  // Browse catalogue (Hits database and Redis Cache)
  const productRes = http.get(`${BASE_URL}/products`);
  check(productRes, {
    'products list status is 200': (r) => r.status === 200,
    'products count is greater than 0': (r) => JSON.parse(r.body).length > 0,
  });

  // Simulate thinking time between customer actions
  sleep(1);
}
