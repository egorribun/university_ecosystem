import ws from 'k6/ws';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom error-rate metric backing the `errors` threshold in options below.
// Without this definition k6 fails at init with "threshold defined on
// non-existent metric 'errors'". Recorded at the deterministic steps
// (csrf/register/login/ticket/connect) — NOT the message handler, whose
// delivery depends on NATS fan-out and is best-effort, so the threshold passes
// on a successful 101 upgrade alone.
const errors = new Rate('errors');

// k6 Options & SLA thresholds
export const options = {
    stages: [
        { duration: '10s', target: 10 }, // Ramp up to 10 users
        { duration: '30s', target: 10 }, // Stay at 10 users
        { duration: '10s', target: 0 },  // Ramp down
    ],
    thresholds: {
        // Relaxed for CI: ws_connecting is noisy on a contended multi-service
        // runner (the WS handshake traverses ws-hub -> Redis ticket GETDEL). The
        // `errors` rate (csrf/register/login/ticket/connect all succeed) is the
        // meaningful gate (precedent: f75de0ed7 "relax k6 latencies for CI").
        ws_connecting: ['p(95)<500'],
        errors: ['rate<0.01'],
    },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const WS_URL = __ENV.WS_URL || 'ws://localhost:8083';

// Per-VU token cache. k6 runs the default function repeatedly in the SAME JS
// context per VU, so a module-level object keyed by __VU persists across
// iterations. We register + login ONCE per VU and reuse the token: the auth
// endpoints (/login/json, /register) are PER-IP rate-limited
// (app/core/ratelimit/fastapi.py keys unauthenticated requests by client IP),
// and ALL k6 VUs share one source IP via the socat host-publish, so re-logging
// in every iteration trips the limiter (429). The unthrottled /ws/ticket + the
// WS upgrade are the per-iteration workload — the actual WS load being measured.
const vuTokens = {};

// Signed double-submit CSRF (app/core/csrf.py): GET /api/v1/auth/csrf-cookie
// sets the `csrf_token` cookie; mutating POSTs must echo it as the X-CSRF-Token
// header (the middleware does secrets.compare_digest(cookie, header) at
// csrf.py:361). k6's cookie jar is per-VU + persists across iterations, so it
// carries csrf_token automatically; we re-read it from the jar on each call so
// a server-side token rotation (csrf.py:397) is picked up.
function csrfHeaders(extra) {
    const jar = http.cookieJar();
    const cookies = jar.cookiesForURL(`${BASE_URL}/`);
    const token = (cookies['csrf_token'] && cookies['csrf_token'][0]) || '';
    return Object.assign({ 'Content-Type': 'application/json', 'X-CSRF-Token': token }, extra || {});
}

// Register + login a VU's user ONCE; returns the access token (or null).
function authenticate(vuId) {
    const email = `loadtest_user_${vuId}@example.com`;
    const password = 'ValidPass123!'; // pragma: allowlist secret
    const fullName = `LoadTest User ${vuId}`;

    // 1. Prime the CSRF cookie (exempt endpoint; sets csrf_token in the jar).
    const csrfRes = http.get(`${BASE_URL}/api/v1/auth/csrf-cookie`);
    errors.add(csrfRes.status !== 200);

    // 2. Register (idempotent: 200 new / 400 already-registered) with CSRF header.
    const regRes = http.post(
        `${BASE_URL}/api/v1/auth/register`,
        JSON.stringify({ email: email, password: password, full_name: fullName }),
        { headers: csrfHeaders() }
    );
    errors.add(!(regRes.status === 200 || regRes.status === 400));

    // 3. Login (JSON) with CSRF header.
    const loginRes = http.post(
        `${BASE_URL}/api/v1/auth/login/json`,
        JSON.stringify({ email: email, password: password }),
        { headers: csrfHeaders() }
    );
    const loginOk = check(loginRes, {
        'login is successful (200)': (r) => r.status === 200,
    });
    errors.add(!loginOk);
    if (!loginOk) {
        console.error(`Login failed for ${email}: ${loginRes.body}`);
        return null;
    }
    return JSON.parse(loginRes.body).access_token;
}

export default function () {
    const vuId = __VU;

    // Authenticate ONCE per VU; reuse the token for all subsequent iterations.
    if (!vuTokens[vuId]) {
        const token = authenticate(vuId);
        if (!token) {
            sleep(1);
            return;
        }
        vuTokens[vuId] = token;
    }
    const token = vuTokens[vuId];

    // 4. Request a WS upgrade ticket (NOT rate-limited; ws/ticket.py has no
    // sensitive_route_limit). Bearer auth + carry the CSRF header too, since the
    // jar may hold an auth cookie which disables the Bearer-only CSRF bypass
    // (csrf.py:339 skips CSRF only for Bearer requests WITHOUT an auth cookie).
    const ticketRes = http.post(`${BASE_URL}/ws/ticket`, null, {
        headers: csrfHeaders({ Authorization: `Bearer ${token}` }),
    });
    const ticketOk = check(ticketRes, {
        'ticket issued (201)': (r) => r.status === 201,
    });
    errors.add(!ticketOk);
    if (!ticketOk) {
        console.error(`Ticket issuance failed: ${ticketRes.body}`);
        sleep(1);
        return;
    }
    const ticket = JSON.parse(ticketRes.body).ticket;

    // 5. Establish the WebSocket connection with the ticket.
    // ws-hub serves the upgrade at exact /ws (services/ws-hub/main.go:133
    // http.Handle("/ws", ...)). The /ws/chat -> /ws rewrite lives only in the
    // DEV infrastructure/Caddyfile; k6 connects directly to ws-hub (Caddy is
    // bypassed in CI), so /ws/chat would 404 — connect to /ws.
    const url = `${WS_URL}/ws?ticket=${encodeURIComponent(ticket)}`;

    const res = ws.connect(url, {}, function (socket) {
        socket.on('open', function () {
            // Join a chat room
            const joinFrame = JSON.stringify({
                type: 'join',
                room: 'room1',
            });
            socket.send(joinFrame);

            // Periodically send chat messages every 2 seconds
            socket.setInterval(function () {
                const msgFrame = JSON.stringify({
                    type: 'message',
                    room: 'room1',
                    payload: { text: `Hello from VU ${vuId}` },
                });
                socket.send(msgFrame);
            }, 2000);
        });

        socket.on('message', function (message) {
            check(message, {
                'received ws message': (msg) => msg && msg.length > 0,
            });
        });

        socket.on('close', function () {
            // normal disconnect
        });

        socket.on('error', function (e) {
            console.error(`WebSocket error: ${e.error()}`);
        });

        // Close connection after 8 seconds
        socket.setTimeout(function () {
            socket.close();
        }, 8000);
    });

    const wsOk = check(res, {
        'websocket connection established': (r) => r && r.status === 101,
    });
    errors.add(!wsOk);

    sleep(1);
}
