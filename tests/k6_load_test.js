/**
 * SmartRetailX – Section 12.5: Performance Testing (Load & Stress)
 * Tool: k6 by Grafana
 *
 * Load Profile:
 *   Ramp-up   (0s  – 30s):  0 → 20 virtual users
 *   Plateau   (30s – 1m30s): 20 users sustained
 *   Stress    (1m30s – 2m):  20 → 50 concurrent users
 *   Cooldown  (2m  – 2m30s): 50 → 0
 *
 * Execution:
 *   k6 run tests/k6_load_test.js
 *
 * Override gateway URL:
 *   GATEWAY_URL=http://your-lb:8000 k6 run tests/k6_load_test.js
 *
 * Output as JSON:
 *   k6 run --out json=results/k6_output.json tests/k6_load_test.js
 */

import http from 'k6/http';
import { sleep, check, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ─── Custom Metrics ────────────────────────────────────────────────────────────
const signupSuccessRate  = new Rate('signup_success_rate');
const loginSuccessRate   = new Rate('login_success_rate');
const productsFetchRate  = new Rate('products_fetch_rate');
const orderCreateRate    = new Rate('order_create_rate');
const inventoryFetchRate = new Rate('inventory_fetch_rate');
const orderCreateTime    = new Trend('order_create_time',  true);
const productFetchTime   = new Trend('product_fetch_time', true);

// ─── Load Profile Stages ──────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: '30s',  target: 20 },  // Ramp-up   (0 → 20 VUs)
    { duration: '1m',   target: 20 },  // Plateau   (20 VUs sustained)
    { duration: '30s',  target: 50 },  // Stress    (20 → 50 VUs spike)
    { duration: '30s',  target: 0  },  // Cooldown  (50 → 0)
  ],

  // ─── SLA Thresholds ─────────────────────────────────────────────────────────
  thresholds: {
    // Overall latency
    http_req_duration:    ['p(95)<2000', 'p(99)<4000'],  // 95% < 2s, 99% < 4s
    http_req_failed:      ['rate<0.05'],                  // Error rate < 5%

    // Per-route custom thresholds
    order_create_time:    ['p(95)<3000'],                 // Order creation < 3s at 95%
    product_fetch_time:   ['p(95)<1000'],                 // Product listing < 1s at 95%

    // Success rates (relaxed during stress spike)
    products_fetch_rate:  ['rate>0.90'],                  // Products succeed 90%+
    login_success_rate:   ['rate>0.85'],                  // Login succeeds 85%+
    order_create_rate:    ['rate>0.80'],                  // Order creation 80%+
  },
};

// ─── Configuration ────────────────────────────────────────────────────────────
const BASE_URL    = __ENV.GATEWAY_URL || 'http://localhost:8000';
const API         = `${BASE_URL}/api/v1`;
const JSON_HEADER = { 'Content-Type': 'application/json' };

// Shared test user pool (pre-seeded to avoid signup conflicts under load)
const TEST_USERS = [
  { email: 'perf_user1@smartretailx.com', password: 'PerfPass123!' },
  { email: 'perf_user2@smartretailx.com', password: 'PerfPass123!' },
  { email: 'perf_user3@smartretailx.com', password: 'PerfPass123!' },
  { email: 'perf_user4@smartretailx.com', password: 'PerfPass123!' },
  { email: 'perf_user5@smartretailx.com', password: 'PerfPass123!' },
];

// ─── Setup: Register test users once before load begins ──────────────────────
export function setup() {
  console.log(`[k6 Setup] Target gateway: ${BASE_URL}`);
  const tokens = {};

  for (const user of TEST_USERS) {
    // Register user (ignore 400 duplicate – already exists)
    http.post(`${API}/users/signup`, JSON.stringify({
      username: user.email.split('@')[0],
      email:    user.email,
      password: user.password,
      role:     'Customer'
    }), { headers: JSON_HEADER });

    // Login to get token
    const loginRes = http.post(`${API}/users/login`, JSON.stringify({
      email:    user.email,
      password: user.password
    }), { headers: JSON_HEADER });

    if (loginRes.status === 200) {
      tokens[user.email] = loginRes.json('access_token');
    }
  }

  console.log(`[k6 Setup] Seeded tokens for ${Object.keys(tokens).length} test users.`);
  return { tokens };
}

// ─── Main Virtual User Scenario ───────────────────────────────────────────────
export default function (data) {
  // Each VU picks a user from the pool by index
  const vuIndex = (__VU - 1) % TEST_USERS.length;
  const user    = TEST_USERS[vuIndex];
  const token   = data.tokens[user.email] || '';
  const authHdr = { headers: { ...JSON_HEADER, 'Authorization': `Bearer ${token}` } };

  // ── 1. Gateway Health Check ────────────────────────────────────────────────
  group('01_health_check', function () {
    const res = http.get(`${BASE_URL}/healthz`);
    check(res, {
      'Gateway health 200': (r) => r.status === 200,
      'Gateway status healthy': (r) => {
        try { return r.json().status === 'healthy'; } catch { return false; }
      },
    });
  });

  sleep(0.2);

  // ── 2. Browse Product Catalogue ────────────────────────────────────────────
  let firstProductId = null;
  group('02_browse_products', function () {
    const start = Date.now();
    const res = http.get(`${API}/products`);
    productFetchTime.add(Date.now() - start);

    const ok = check(res, {
      'Products list 200': (r) => r.status === 200,
      'Products list not empty': (r) => {
        try { return r.json().length > 0; } catch { return false; }
      },
    });
    productsFetchRate.add(ok);

    // Extract a real product ID for later requests
    if (res.status === 200) {
      try {
        const products = res.json();
        if (products.length > 0) firstProductId = products[0].id;
      } catch (_) {}
    }
  });

  sleep(0.3);

  // ── 3. View Individual Product ─────────────────────────────────────────────
  if (firstProductId) {
    group('03_view_product', function () {
      const res = http.get(`${API}/products/${firstProductId}`);
      check(res, {
        'Single product 200': (r) => r.status === 200,
        'Product has name':   (r) => {
          try { return r.json().name !== undefined; } catch { return false; }
        },
      });
    });
    sleep(0.2);
  }

  // ── 4. Check Inventory ─────────────────────────────────────────────────────
  group('04_check_inventory', function () {
    const res = http.get(`${API}/inventory/1`);
    const ok = check(res, {
      'Inventory 200 or 404': (r) => r.status === 200 || r.status === 404,
    });
    inventoryFetchRate.add(res.status === 200);
  });

  sleep(0.2);

  // ── 5. Login (token refresh simulation) ───────────────────────────────────
  // Only every 5th VU iteration re-logs in to test login under load
  if (__ITER % 5 === 0) {
    group('05_login', function () {
      const res = http.post(`${API}/users/login`, JSON.stringify({
        email:    user.email,
        password: user.password
      }), { headers: JSON_HEADER });

      const ok = check(res, {
        'Login 200': (r) => r.status === 200,
        'Login returns token': (r) => {
          try { return r.json('access_token') !== undefined; } catch { return false; }
        },
      });
      loginSuccessRate.add(ok);
    });
    sleep(0.3);
  }

  // ── 6. Place an Order ──────────────────────────────────────────────────────
  if (token) {
    group('06_place_order', function () {
      const payload = JSON.stringify({
        items: [
          {
            product_id:   '1',
            product_name: 'Wireless Noise-Canceling Headphones',
            price:        199.99,
            quantity:     1
          }
        ]
      });

      const start = Date.now();
      const res   = http.post(`${API}/orders`, payload, authHdr);
      orderCreateTime.add(Date.now() - start);

      const ok = check(res, {
        'Create order 201': (r) => r.status === 201,
        'Order has id':     (r) => {
          try { return r.json('id') !== undefined; } catch { return false; }
        },
        'Order is Pending': (r) => {
          try { return r.json('status') === 'Pending'; } catch { return false; }
        },
      });
      orderCreateRate.add(ok);
    });
    sleep(0.5);
  }

  // ── 7. Fetch User Profile ──────────────────────────────────────────────────
  if (token) {
    group('07_user_profile', function () {
      const res = http.get(`${API}/users/profile`, authHdr);
      check(res, {
        'Profile 200':     (r) => r.status === 200,
        'Profile has email': (r) => {
          try { return r.json('email') !== undefined; } catch { return false; }
        },
      });
    });
    sleep(0.2);
  }

  // ── 8. List User Orders ────────────────────────────────────────────────────
  if (token) {
    group('08_list_orders', function () {
      const res = http.get(`${API}/orders`, authHdr);
      check(res, {
        'Orders list 200': (r) => r.status === 200,
      });
    });
    sleep(0.2);
  }

  // User think time between complete flows
  sleep(1);
}

// ─── Teardown: Summary Print ──────────────────────────────────────────────────
export function teardown(data) {
  console.log('[k6 Teardown] Performance test completed.');
  console.log(`[k6] Load Profile: Ramp-up(30s → 20VU) → Plateau(1m @ 20VU) → Stress(30s → 50VU) → Cooldown(30s → 0)`);
}
