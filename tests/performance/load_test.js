import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    stages: [
        { duration: '30s', target: 20 }, // ramp up to 20 users
        { duration: '1m', target: 20 },  // stay at 20 users
        { duration: '30s', target: 0 },  // ramp down to 0 users
    ],
    thresholds: {
        // Latency is noisy in CI: the backend is reached through a socat
        // host-publish hop on a multi-service runner (temporal + ES + spicedb +
        // minio + go services). http_req_failed (all requests succeed under
        // load) is the meaningful gate; latency kept generous for CI stability
        // (precedent: f75de0ed7 "relax k6 latencies for CI stability").
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        http_req_failed: ['rate<0.01'], // less than 1% errors
    },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';

export default function () {
    const responses = http.batch([
        ['GET', `${BASE_URL}/`, null, { tags: { name: 'Root' } }],
        ['GET', `${BASE_URL}/healthz`, null, { tags: { name: 'Health' } }],
    ]);

    check(responses[0], {
        'root status is 200': (r) => r.status === 200,
    });

    check(responses[1], {
        'healthz status is 200': (r) => r.status === 200,
    });

    sleep(1);
}
