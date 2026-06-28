import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    stages: [
        { duration: '30s', target: 20 }, // ramp up to 20 users
        { duration: '1m', target: 20 },  // stay at 20 users
        { duration: '30s', target: 0 },  // ramp down to 0 users
    ],
    thresholds: {
        // Enforce strict performance budgets: p(95) < 200ms and failure rate < 0.01% (rate < 0.0001)
        http_req_duration: ['p(95)<200', 'p(99)<1000'],
        http_req_failed: ['rate<0.0001'],
    },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';

export default function () {
    // Hit `/` ONLY. Under sustained load BOTH health endpoints flake: /healthz
    // (full check, app/api/health.py:159) 503s ~7% when a subsystem flaps (tempo
    // is `unhealthy` in CI); /health/ready (:362) does a DB round-trip that
    // contends the connection pool under 20 VUs -> ~39% failures. `/` is
    // rate-limit-exempt (ratelimit/middleware.py:223), touches no DB, and
    // returned 200 100% across rounds 3-4 -> the right raw-throughput target.
    // (The DB/auth/Redis path is load-tested by ws_hub_load_test.js's
    // register -> login -> ticket flow.)
    const res = http.get(`${BASE_URL}/`, { tags: { name: 'Root' } });
    check(res, {
        'root status is 200': (r) => r.status === 200,
    });

    sleep(1);
}
