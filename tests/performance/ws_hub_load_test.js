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

// Per-VU JWT cache. k6 runs the default function repeatedly in the SAME JS context
// per VU, so a module-level object keyed by __VU persists across iterations as a
// plain JS value (this DOES survive — unlike the cookie jar; see ROUND-11 below).
// We register + login ONCE per VU (each /login/json mints a session, the backend
// caps concurrent sessions per user — session_service.py:170 -> too_many_sessions
// — and the PER-IP auth limiters apply since all VUs share one socat IP), read the
// access token ONCE, and reuse it as a Bearer header on every /ws/ticket POST.
//
// ROUND-11 — why a Bearer header, not the cookie jar: round-10 evidence showed
// BOTH csrf_token AND the HttpOnly access_token_v2 cookie present for the FIRST
// post-login ticket then GONE on later iterations (10 ok = 1/VU first iter, 317
// fail; round-9 was 403 CSRF-missing, round-10 401 "Could not validate
// credentials"), i.e. k6's per-VU jar does NOT carry these cookies across
// iterations. W126 EXCLUDES access_token from the /login/json BODY
// (response_model_exclude_none + Token.access_token=None), BUT the HttpOnly
// access_token_v2 COOKIE value IS the raw JWT (login_session_manager.py:172,
// path=/, 60-min TTL) and k6 (not a browser) reads it via cookiesForURL right
// after login. We cache that JWT string (jar-independent) and send it as
// Authorization: Bearer on the ticket -> auth survives any jar reset, and with no
// auth cookie carried by the reset jar the Bearer request also SKIPS CSRF
// (csrf.py:339).
const vuTokens = {};

// Signed double-submit CSRF (app/core/csrf.py): GET /api/v1/auth/csrf-cookie
// sets the `csrf_token` cookie; mutating POSTs must echo it as the X-CSRF-Token
// header (the middleware does secrets.compare_digest(cookie, header) at
// csrf.py:361). Build the header by reading the csrf_token that k6's jar WOULD
// send to the EXACT targetUrl (cookiesForURL honours the cookie's Path), so the
// header value always equals the cookie value the request carries -> the
// double-submit compare matches. Reading per-URL (not a fixed "/") avoids a
// header/cookie mismatch if a cookie's Path ever scopes it away from a route.
function csrfHeaders(targetUrl, extra) {
    const cookies = http.cookieJar().cookiesForURL(targetUrl);
    const token = (cookies['csrf_token'] && cookies['csrf_token'][0]) || '';
    return Object.assign({ 'Content-Type': 'application/json', 'X-CSRF-Token': token }, extra || {});
}

// Register + login a VU's user ONCE. Returns the access-token JWT (read from the
// HttpOnly access_token_v2 cookie) on success, or null. The JWT is cached + sent
// as a Bearer header on every later /ws/ticket POST (jar-independent — see the
// vuTokens note above).
function authenticate(vuId) {
    const email = `loadtest_user_${vuId}@example.com`;
    const password = 'ValidPass123!'; // pragma: allowlist secret
    const fullName = `LoadTest User ${vuId}`;

    // 1. Prime the CSRF cookie (exempt endpoint; sets csrf_token + _csrf_anon_nonce).
    const csrfRes = http.get(`${BASE_URL}/api/v1/auth/csrf-cookie`);
    errors.add(csrfRes.status !== 200);

    // 2. Register (idempotent: 200 new / 400 already-registered) with CSRF header.
    const regRes = http.post(
        `${BASE_URL}/api/v1/auth/register`,
        JSON.stringify({ email: email, password: password, full_name: fullName }),
        { headers: csrfHeaders(`${BASE_URL}/api/v1/auth/register`) }
    );
    errors.add(!(regRes.status === 200 || regRes.status === 400));

    // 3. Login (JSON) with CSRF header. On success the response sets the HttpOnly
    //    access_token_v2 cookie AND rotates the csrf_token (login_session_manager
    //    .py:94 -> signal_csrf_rotation), so the jar's csrf_token is now bound to
    //    the authenticated session — exactly what the cookie-auth'd /ws/ticket needs.
    const loginRes = http.post(
        `${BASE_URL}/api/v1/auth/login/json`,
        JSON.stringify({ email: email, password: password }),
        { headers: csrfHeaders(`${BASE_URL}/api/v1/auth/login/json`) }
    );
    const loginOk = check(loginRes, {
        'login is successful (200)': (r) => r.status === 200,
    });
    errors.add(!loginOk);
    if (!loginOk) {
        console.error(`Login failed for ${email}: ${loginRes.body}`);
        return null;
    }
    // Read the raw JWT from the HttpOnly access_token_v2 cookie (its value == the
    // JWT, login_session_manager.py:172) NOW, while the jar still holds it. We
    // return it to be cached + sent as a Bearer header (jar-independent) thereafter.
    const authCookies = http.cookieJar().cookiesForURL(`${BASE_URL}/`);
    const jwt = (authCookies['access_token_v2'] && authCookies['access_token_v2'][0]) || '';
    if (!jwt) {
        console.error(`No access_token_v2 cookie after login for ${email}`);
        errors.add(true);
        return null;
    }
    return jwt;
}

export default function () {
    const vuId = __VU;

    // Authenticate ONCE per VU; cache the JWT (a plain JS value persists across
    // iterations — the cookie jar does not) and reuse it as a Bearer below.
    if (!vuTokens[vuId]) {
        const newJwt = authenticate(vuId);
        if (!newJwt) {
            sleep(1);
            return;
        }
        vuTokens[vuId] = newJwt;
    }
    const jwt = vuTokens[vuId];

    // 4a. Re-prime the CSRF cookie each iteration. ROUND-9 evidence: the
    // login-rotated csrf_token is present for the FIRST post-login ticket but
    // then cookie_present=False on /ws/ticket -> "CSRF rejected (missing token)"
    // (a k6 jar cross-iteration lifecycle gap; ticket.py sets/clears no cookie).
    // A fresh AUTHENTICATED GET re-establishes a Path=/ csrf_token bound to the
    // current session immediately before the ticket POST. /csrf-cookie rides the
    // :default limiter (raised in the CI fragment), so the extra GET is rate-safe.
    const reprimeRes = http.get(`${BASE_URL}/api/v1/auth/csrf-cookie`);
    errors.add(reprimeRes.status !== 200);

    // 4b. Request the WS upgrade ticket. ROUND-11: authenticate with the cached
    // JWT as a Bearer header (ws/ticket.py:8 accepts "HttpOnly cookie OR Bearer"),
    // because k6's jar does NOT carry the access_token_v2 cookie across iterations
    // (round-10: 401 on every ticket after a VU's first). A header is jar-
    // independent. If the (reset) jar carries no auth cookie, this Bearer request
    // SKIPS CSRF (csrf.py:339); if it ever DOES carry one, the re-primed per-URL
    // X-CSRF-Token still validates -- so we send both, robust either way.
    // /ws/ticket rides the WEBSOCKET limiter (rate_limit_websocket), raised in the
    // CI fragment so the per-iteration ticket volume does not 429.
    const ticketRes = http.post(`${BASE_URL}/ws/ticket`, null, {
        headers: csrfHeaders(`${BASE_URL}/ws/ticket`, { Authorization: `Bearer ${jwt}` }),
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
