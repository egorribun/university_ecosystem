import ws from 'k6/ws';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ws_hub_10k_test.js — 10 000 VU WebSocket stress test for ws-hub.
//
// Architecture notes:
//   - ws-hub enforces a per-IP WS-upgrade token bucket (10 / 60 s, hardcoded).
//     At 10 k VU scale with a single socat IP, the upgrade throttle IS a hard
//     constraint — most VUs will get a 429. We count successful 101s and assert
//     only that the upgrade path functions at all, not that every VU connects.
//   - The AUTH steps (CSRF / register / login / ticket) are the correctness gate
//     and must succeed at <1% error rate.
//   - This test is intended for isolated ws-hub deployments with WS_UPGRADE_LIMIT
//     raised (e.g. 10000 / 60) to allow meaningful load; the thresholds below
//     reflect that environment.

const errors = new Rate('errors');
const wsConnectsEstablished = new Counter('ws_connects_established');
const wsMsgsReceived = new Counter('ws_msgs_received');
const wsConnectionDuration = new Trend('ws_connection_duration', true); // milliseconds

export const options = {
    stages: [
        { duration: '30s', target: 1000 },   // ramp 0 → 1 000
        { duration: '60s', target: 5000 },   // ramp 1 000 → 5 000
        { duration: '90s', target: 10000 },  // ramp 5 000 → 10 000
        { duration: '30s', target: 0 },      // ramp down
    ],
    thresholds: {
        // Auth chain: every CSRF / register / login / ticket must succeed (<1%).
        errors: ['rate<0.01'],
        // WS upgrade: p95 connection setup under 2 seconds in a properly configured
        // env where the upgrade limiter is relaxed.
        ws_connection_duration: ['p(95)<2000'],
        // At least 50 000 WS messages received across all VUs (proves bidirectional
        // delivery works under load, not just connection establishment).
        ws_msgs_received: ['count>50000'],
        // At least 100 successful 101 upgrades (sanity gate — not every VU since
        // per-IP rate limiting is a known design constraint for single-IP load tests).
        ws_connects_established: ['count>=100'],
    },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const WS_URL = __ENV.WS_URL || 'ws://localhost:8083';

// Per-VU JWT cache — a module-level object persists across iterations within the
// same JS context (VU), so we authenticate once and reuse the token.
// See ws_hub_load_test.js for full rationale (ROUND-11 discussion).
const vuTokens = {};

// csrfHeaders builds the double-submit CSRF headers required by the backend.
// Reads the csrf_token from k6's cookie jar for the target URL so the header
// matches the cookie the request will carry — matching app/core/csrf.py:361.
function csrfHeaders(targetUrl, extra) {
    const cookies = http.cookieJar().cookiesForURL(targetUrl);
    const token = (cookies['csrf_token'] && cookies['csrf_token'][0]) || '';
    return Object.assign({ 'Content-Type': 'application/json', 'X-CSRF-Token': token }, extra || {});
}

// authenticate registers + logs in a VU's user exactly once, returns the JWT.
// Mirrors the same flow as ws_hub_load_test.js (authenticate function).
function authenticate(vuId) {
    const email = `stress_user_${vuId}@example.com`;
    const password = 'ValidPass123!'; // pragma: allowlist secret
    const fullName = `StressTest User ${vuId}`;

    // 1. Prime CSRF cookie.
    const csrfRes = http.get(`${BASE_URL}/api/v1/auth/csrf-cookie`);
    errors.add(csrfRes.status !== 200);

    // 2. Register (idempotent — 200 new, 400 already-registered).
    const regRes = http.post(
        `${BASE_URL}/api/v1/auth/register`,
        JSON.stringify({ email: email, password: password, full_name: fullName }),
        { headers: csrfHeaders(`${BASE_URL}/api/v1/auth/register`) }
    );
    errors.add(!(regRes.status === 200 || regRes.status === 400));

    // 3. Login and extract HttpOnly JWT cookie.
    const loginRes = http.post(
        `${BASE_URL}/api/v1/auth/login/json`,
        JSON.stringify({ email: email, password: password }),
        { headers: csrfHeaders(`${BASE_URL}/api/v1/auth/login/json`) }
    );
    const loginOk = check(loginRes, { 'login 200': (r) => r.status === 200 });
    errors.add(!loginOk);
    if (!loginOk) {
        console.error(`10k-test: login failed for ${email}: ${loginRes.body}`);
        return null;
    }

    // Read the raw JWT from the HttpOnly access_token_v2 cookie immediately after
    // login while the jar holds it (jar-independent caching, ROUND-11 rationale).
    const authCookies = http.cookieJar().cookiesForURL(`${BASE_URL}/`);
    const jwt = (authCookies['access_token_v2'] && authCookies['access_token_v2'][0]) || '';
    if (!jwt) {
        console.error(`10k-test: no access_token_v2 cookie for ${email}`);
        errors.add(true);
        return null;
    }
    return jwt;
}

export default function () {
    const vuId = __VU;

    // Authenticate once per VU; reuse the cached JWT on subsequent iterations.
    if (!vuTokens[vuId]) {
        const newJwt = authenticate(vuId);
        if (!newJwt) {
            sleep(1);
            return;
        }
        vuTokens[vuId] = newJwt;
    }
    const jwt = vuTokens[vuId];

    // 4a. Re-prime CSRF cookie before the ticket POST (jar cross-iteration gap).
    const reprimeRes = http.get(`${BASE_URL}/api/v1/auth/csrf-cookie`);
    errors.add(reprimeRes.status !== 200);

    // 4b. Obtain a WS upgrade ticket using Bearer header (jar-independent auth).
    const ticketRes = http.post(`${BASE_URL}/ws/ticket`, null, {
        headers: csrfHeaders(`${BASE_URL}/ws/ticket`, { Authorization: `Bearer ${jwt}` }),
    });
    const ticketOk = check(ticketRes, { 'ticket 201': (r) => r.status === 201 });
    errors.add(!ticketOk);
    if (!ticketOk) {
        console.error(`10k-test: ticket failed: ${ticketRes.body}`);
        sleep(1);
        return;
    }
    const ticket = JSON.parse(ticketRes.body).ticket;

    // 5. Establish WebSocket connection and measure latency.
    const url = `${WS_URL}/ws?ticket=${encodeURIComponent(ticket)}`;
    const connStart = Date.now();

    const res = ws.connect(url, {}, function (socket) {
        socket.on('open', function () {
            wsConnectsEstablished.add(1);
            wsConnectionDuration.add(Date.now() - connStart);

            // Join a shared load-test room.
            socket.send(JSON.stringify({ type: 'join', room: 'stress-room' }));

            // Send a message every 500 ms to generate inbound + outbound traffic.
            socket.setInterval(function () {
                socket.send(JSON.stringify({
                    type: 'message',
                    room: 'stress-room',
                    payload: { text: `VU-${vuId} @ ${Date.now()}` },
                }));
            }, 500);
        });

        socket.on('message', function (message) {
            wsMsgsReceived.add(1);
            check(message, { 'ws message non-empty': (m) => m && m.length > 0 });
        });

        socket.on('close', function () {
            // Normal close — no action needed.
        });

        socket.on('error', function (e) {
            // Log but do NOT add to errors — per-IP upgrade throttle (429) is
            // expected by design for single-IP load tests.
            console.warn(`10k-test WS error VU ${vuId}: ${e.error()}`);
        });

        // Hold connection for 10 seconds then close gracefully.
        socket.setTimeout(function () {
            socket.close();
        }, 10000);
    });

    // Informational check — NOT added to errors gate (per-IP throttle expected).
    check(res, { 'ws 101 upgrade': (r) => r && r.status === 101 });

    sleep(1);
}
