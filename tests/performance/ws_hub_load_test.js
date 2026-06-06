import ws from 'k6/ws';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom error-rate metric backing the `errors` threshold in options below.
// Without this definition k6 fails at init with "threshold defined on
// non-existent metric 'errors'". Recorded only at the deterministic steps
// (register/login/ticket/connect) — NOT the message handler, whose delivery
// depends on NATS fan-out and is best-effort, so the threshold passes on a
// successful 101 upgrade alone.
const errors = new Rate('errors');

// k6 Options & SLA thresholds
export const options = {
    stages: [
        { duration: '10s', target: 10 }, // Ramp up to 10 users
        { duration: '30s', target: 10 }, // Stay at 10 users
        { duration: '10s', target: 0 },  // Ramp down
    ],
    thresholds: {
        // SLA: 95% of connections should be established in less than 200ms
        ws_connecting: ['p(95)<200'],
        // Ensure error rate is less than 1%
        errors: ['rate<0.01'],
    },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const WS_URL = __ENV.WS_URL || 'ws://localhost:8083';

export default function () {
    const vuId = __VU;
    const email = `loadtest_user_${vuId}@example.com`;
    const password = 'ValidPass123!'; // pragma: allowlist secret
    const fullName = `LoadTest User ${vuId}`;

    const headers = { 'Content-Type': 'application/json' };

    // 1. Register User (Ignore 400 Bad Request if already registered)
    const registerPayload = JSON.stringify({
        email: email,
        password: password,
        full_name: fullName,
    });
    const regRes = http.post(`${BASE_URL}/api/v1/auth/register`, registerPayload, { headers });
    const regOk = check(regRes, {
        'registration status is 200 or 400': (r) => r.status === 200 || r.status === 400,
    });
    errors.add(!regOk);

    // 2. Login User via JSON
    const loginPayload = JSON.stringify({
        email: email,
        password: password,
    });
    const loginRes = http.post(`${BASE_URL}/api/v1/auth/login/json`, loginPayload, { headers });
    const loginOk = check(loginRes, {
        'login is successful (200)': (r) => r.status === 200,
    });
    errors.add(!loginOk);

    if (!loginOk) {
        console.error(`Login failed for ${email}: ${loginRes.body}`);
        return;
    }

    const loginData = JSON.parse(loginRes.body);
    const token = loginData.access_token;

    // 3. Request WS Upgrade Ticket
    const authHeaders = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
    };
    const ticketRes = http.post(`${BASE_URL}/ws/ticket`, null, { headers: authHeaders });
    const ticketOk = check(ticketRes, {
        'ticket issued (201)': (r) => r.status === 201,
    });
    errors.add(!ticketOk);

    if (!ticketOk) {
        console.error(`Ticket issuance failed: ${ticketRes.body}`);
        return;
    }

    const ticketData = JSON.parse(ticketRes.body);
    const ticket = ticketData.ticket;

    // 4. Establish WebSocket connection with the ticket.
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
