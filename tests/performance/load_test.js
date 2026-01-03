import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    stages: [
        { duration: '30s', target: 20 }, // ramp up to 20 users
        { duration: '1m', target: 20 },  // stay at 20 users
        { duration: '30s', target: 0 },  // ramp down to 0 users
    ],
    thresholds: {
        http_req_duration: ['p(95)<200', 'p(99)<300'], // Relaxed for CI env
        http_req_failed: ['rate<0.01'],    // less than 1% errors
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
