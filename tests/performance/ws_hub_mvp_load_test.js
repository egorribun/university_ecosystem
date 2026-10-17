import http from "k6/http";
import ws from "k6/ws";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import { Counter, Rate, Trend } from "k6/metrics";

/* global __ENV:readonly, __VU:readonly, open:readonly */

// Block 5 MVP acceptance profile. This is an executable load scenario, not a
// CI network test. It requires an isolated disposable stack, 500 pre-created
// synthetic DM pairs, and 100+ source IPs already configured on the k6 host.
// Do not point it at a shared/persistent stand: a successful run creates about
// 180,000 synthetic chat messages and intentionally performs no cleanup.
//
// Fixture shape (kept outside the repository):
// [
//   {"chat_id":"<uuid>","left":{"user_id":"<uuid>","access_token":"<jwt>"},
//    "right":{"user_id":"<uuid>","access_token":"<jwt>"}}, ... 500 pairs
// ]
// Both tokens must remain valid for the entire run (at least 31 minutes). The
// `docker-compose.ci-loadtest.yml` overlay is expected to raise only isolated
// test-stack backend limits. This harness never changes production rate limits.
// Supply WS_MVP_PAIR_FIXTURE_PATH, API_BASE_URL, WS_URL, WS_MVP_RUN_ID,
// WS_MVP_COMPOSE_PROJECT=ue-mvp-<lowercase-run-id>,
// WS_MVP_DISPOSABLE_TARGET_CONFIRMATION=I_UNDERSTAND_SYNTHETIC_DATA and
// WS_MVP_SOURCE_IPS out-of-band when invoking `k6 run` with this file. This must
// be a separate disposable Compose project. Start the stack under the matching
// project name, for example:
// `docker compose -p "ue-mvp-${WS_MVP_RUN_ID,,}" -f docker-compose.yml -f docker-compose.ci-loadtest.yml up -d`.
// Pass the same comma-separated address list to both `-e WS_MVP_SOURCE_IPS=...`
// and `--local-ips=...`; this avoids exposing unrelated system environment values
// to the script. Keep the fixture and generated k6 output private; never check
// either into the repository.
// Use a fresh WS_MVP_RUN_ID for every run so chat idempotency keys do not replay
// messages from an earlier acceptance attempt.
// Message deletion is intentionally outside this load script. After evidence is
// preserved, the owner must tear down only the isolated Compose project created
// for this run; never point this harness at a persistent stand or delete shared
// chat history as a cleanup shortcut.
// The ws-hub's production 10-upgrades/IP/60s guard remains in force: provide at
// least 100 dedicated local IPs and verify that the network path presents them
// as distinct peers to both ws-hub and the backend (a proxy or host-published
// port can collapse them). Source IP addresses must be preconfigured on the
// load-generator OS; `--local-ips` binds VUs to that existing address pool.

const PROFILE = Object.freeze({
  connectionCount: 1000,
  pairCount: 500,
  targetMessagesPerSecond: 100,
  messageIntervalMs: 5000,
  senderWarmupMs: 15000,
  senderPhaseSpacingMs: 10,
  duration: "30m",
  connectionDurationMs: 30 * 60 * 1000,
  deliveryP95Ms: 500,
  maxConnectionsPerSourceIp: 10,
  minimumSourceIpCount: Math.ceil(1000 / 10),
  minimumMessagesSent: 175000,
  minimumMessagesDelivered: 175000,
});

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const pairFixturePath = __ENV.WS_MVP_PAIR_FIXTURE_PATH || "";
const pairs = new SharedArray("ws-mvp-pairs", () => {
  if (!pairFixturePath) return [];
  const parsed = JSON.parse(open(pairFixturePath));
  if (!Array.isArray(parsed))
    throw new Error("WS MVP fixture must be a JSON array");
  return parsed;
});

const sendFailures = new Counter("ws_mvp_send_failures");
const messagesSent = new Counter("ws_mvp_messages_sent");
const messagesDelivered = new Counter("ws_mvp_messages_delivered");
const duplicateDeliveries = new Counter("ws_mvp_duplicate_deliveries");
const connectionsOpened = new Counter("ws_mvp_connections_opened");
const connectionsClosed = new Counter("ws_mvp_connections_closed");
const connectionSuccess = new Rate("ws_mvp_connection_success");
const connectionDurationSuccess = new Rate(
  "ws_mvp_connection_duration_success",
);
const connectionDuration = new Trend("ws_mvp_connection_duration_ms", true);
const deliveryLatency = new Trend("ws_mvp_delivery_latency", true);

export const options = {
  // Excluding `url` prevents ticket-bearing WebSocket URLs from becoming metric
  // tags in generated summaries or remote metric sinks.
  systemTags: ["status", "method", "name", "group", "check", "scenario"],
  scenarios: {
    ws_mvp_acceptance: {
      executor: "constant-vus",
      vus: PROFILE.connectionCount,
      duration: PROFILE.duration,
      gracefulStop: "60s",
    },
  },
  thresholds: {
    ws_mvp_connection_success: ["rate>=1"],
    ws_mvp_connections_opened: [`count==${PROFILE.connectionCount}`],
    ws_mvp_connections_closed: [`count==${PROFILE.connectionCount}`],
    ws_mvp_connection_duration_success: ["rate==1"],
    ws_mvp_send_failures: ["count==0"],
    ws_mvp_duplicate_deliveries: ["count==0"],
    ws_mvp_messages_sent: [`count>${PROFILE.minimumMessagesSent - 1}`],
    ws_mvp_messages_delivered: [
      `count>${PROFILE.minimumMessagesDelivered - 1}`,
    ],
    ws_mvp_delivery_latency: [`p(95)<=${PROFILE.deliveryP95Ms}`],
    http_req_failed: ["rate<0.01"],
  },
};

function failSetup(message) {
  // Never include fixture values, tokens, response bodies, or ticket URLs.
  throw new Error(`WS MVP load preflight failed: ${message}`);
}

function isLiteralIpAddress(value) {
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(value)) {
    return value.split(".").every((part) => Number(part) <= 255);
  }
  return value.includes(":") && /^[0-9a-f:]+$/i.test(value);
}

function validateFixture() {
  if (pairs.length !== PROFILE.pairCount) {
    failSetup(`fixture must contain exactly ${PROFILE.pairCount} pairs`);
  }

  const chatIds = new Set();
  const userIds = new Set();
  const accessTokens = new Set();
  for (const pair of pairs) {
    if (
      !pair ||
      typeof pair.chat_id !== "string" ||
      !UUID_PATTERN.test(pair.chat_id) ||
      !pair.left ||
      !pair.right
    ) {
      failSetup("fixture entry shape is invalid");
    }
    if (chatIds.has(pair.chat_id)) failSetup("fixture chat IDs must be unique");
    chatIds.add(pair.chat_id);
    for (const side of [pair.left, pair.right]) {
      if (
        typeof side.user_id !== "string" ||
        !UUID_PATTERN.test(side.user_id) ||
        typeof side.access_token !== "string" ||
        !/^\S+$/.test(side.access_token)
      ) {
        failSetup("fixture participants require user IDs and access tokens");
      }
      if (userIds.has(side.user_id))
        failSetup("fixture user IDs must be unique");
      if (accessTokens.has(side.access_token))
        failSetup("fixture tokens must be unique");
      userIds.add(side.user_id);
      accessTokens.add(side.access_token);
    }
  }
  if (userIds.size !== PROFILE.connectionCount) {
    failSetup(`fixture must contain exactly ${PROFILE.connectionCount} users`);
  }
}

export function setup() {
  if (
    PROFILE.pairCount * 2 !== PROFILE.connectionCount ||
    (PROFILE.pairCount * 1000) / PROFILE.messageIntervalMs !==
      PROFILE.targetMessagesPerSecond ||
    PROFILE.pairCount * PROFILE.senderPhaseSpacingMs !==
      PROFILE.messageIntervalMs ||
    PROFILE.connectionDurationMs !== 30 * 60 * 1000
  ) {
    failSetup(
      "declared profile does not match its connection, message-rate, and duration calculations",
    );
  }
  if (!__ENV.API_BASE_URL || !__ENV.WS_URL) {
    failSetup("API_BASE_URL and WS_URL must point at the isolated test stack");
  }
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(__ENV.WS_MVP_RUN_ID || "")) {
    failSetup("WS_MVP_RUN_ID must be a non-secret, 1-32 character run label");
  }
  const expectedComposeProject = `ue-mvp-${__ENV.WS_MVP_RUN_ID.toLowerCase()}`;
  if (__ENV.WS_MVP_COMPOSE_PROJECT !== expectedComposeProject) {
    failSetup(
      "WS_MVP_COMPOSE_PROJECT must identify the run-scoped disposable Compose project",
    );
  }
  if (
    __ENV.WS_MVP_DISPOSABLE_TARGET_CONFIRMATION !==
    "I_UNDERSTAND_SYNTHETIC_DATA"
  ) {
    failSetup("explicit disposable-target confirmation is required");
  }
  validateFixture();

  const localIps = (__ENV.WS_MVP_SOURCE_IPS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (
    localIps.length < PROFILE.minimumSourceIpCount ||
    new Set(localIps).size !== localIps.length ||
    localIps.some((value) => !isLiteralIpAddress(value))
  ) {
    failSetup(
      `WS_MVP_SOURCE_IPS must contain at least ${PROFILE.minimumSourceIpCount} unique literal IPs`,
    );
  }
  return { runId: __ENV.WS_MVP_RUN_ID };
}

function requestTicket(accessToken) {
  try {
    const response = http.post(
      `${__ENV.API_BASE_URL.replace(/\/$/, "")}/ws/ticket`,
      null,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
        tags: { name: "ws-mvp-ticket" },
      },
    );
    const ok = check(response, {
      "WS ticket issued": (res) => res.status === 201,
    });
    if (!ok) return null;
    const ticket = response.json("ticket");
    return typeof ticket === "string" && ticket.length > 0 ? ticket : null;
  } catch {
    return null;
  }
}

function sendSyntheticMessage(pair, pairIndex, runId, seq, accessToken) {
  const sentAt = Date.now();
  const content = `UEWSMVP|${runId}|${sentAt}|${pairIndex}|${seq}`;
  const url = `${__ENV.API_BASE_URL.replace(/\/$/, "")}/api/v1/chats/${pair.chat_id}/messages`;
  try {
    const response = http.post(url, JSON.stringify({ content }), {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
        "Idempotency-Key": `ws-mvp-${runId}-${pairIndex}-${seq}`,
      },
      tags: { name: "ws-mvp-send-message" },
    });
    if (response.status === 200 || response.status === 201) {
      messagesSent.add(1);
      return true;
    }
  } catch {
    // Keep the failure counter value-only; never log request credentials.
  }
  sendFailures.add(1);
  return false;
}

export default function ({ runId }) {
  const zeroBasedVu = __VU - 1;
  const pairIndex = Math.floor(zeroBasedVu / 2);
  const isSender = zeroBasedVu % 2 === 0;
  const pair = pairs[pairIndex];
  const participant = isSender ? pair.left : pair.right;
  const ticket = requestTicket(participant.access_token);
  if (!ticket) {
    connectionSuccess.add(false);
    // A failed VU must not retry /ws/ticket in a tight constant-vus loop.
    sleep(PROFILE.connectionDurationMs / 1000 + 60);
    return;
  }

  const wsBase = __ENV.WS_URL.replace(/\/$/, "");
  const url = `${wsBase}/ws?ticket=${encodeURIComponent(ticket)}`;
  const seenMessages = Object.create(null);
  let connectionOpenedAt = 0;
  let response;
  try {
    response = ws.connect(
      url,
      { tags: { name: "ws-mvp-upgrade" } },
      (socket) => {
        socket.on("open", () => {
          connectionOpenedAt = Date.now();
          connectionsOpened.add(1);
          socket.send(JSON.stringify({ type: "join", room: pair.chat_id }));
          socket.setInterval(() => socket.ping(), 25000);
          socket.setTimeout(() => socket.close(), PROFILE.connectionDurationMs);

          if (isSender) {
            let seq = 0;
            let senderPaused = false;
            const send = () => {
              if (senderPaused) return;
              senderPaused = !sendSyntheticMessage(
                pair,
                pairIndex,
                runId,
                seq,
                participant.access_token,
              );
              seq += 1;
            };
            const initialDelay =
              PROFILE.senderWarmupMs + pairIndex * PROFILE.senderPhaseSpacingMs;
            socket.setTimeout(() => {
              send();
              socket.setInterval(send, PROFILE.messageIntervalMs);
            }, initialDelay);
          }
        });

        socket.on("close", () => {
          connectionsClosed.add(1);
          if (connectionOpenedAt === 0) {
            connectionDurationSuccess.add(false);
            return;
          }

          const durationMs = Date.now() - connectionOpenedAt;
          connectionDuration.add(durationMs);
          connectionDurationSuccess.add(
            durationMs >= PROFILE.connectionDurationMs,
          );
        });

        socket.on("message", (frame) => {
          if (isSender) return;
          const marker = String(frame).match(
            new RegExp(`UEWSMVP\\|${runId}\\|(\\d+)\\|${pairIndex}\\|(\\d+)`),
          );
          if (!marker) return;
          const uniqueKey = `${marker[1]}|${marker[2]}`;
          if (seenMessages[uniqueKey]) {
            duplicateDeliveries.add(1);
            return;
          }
          seenMessages[uniqueKey] = true;
          const elapsed = Date.now() - Number(marker[1]);
          if (elapsed >= 0) {
            deliveryLatency.add(elapsed);
            messagesDelivered.add(1);
          }
        });
      },
    );
  } catch {
    connectionSuccess.add(false);
    sleep(PROFILE.connectionDurationMs / 1000 + 60);
    return;
  }

  const connected = response && response.status === 101;
  connectionSuccess.add(connected);
  check(response, {
    "WS upgrade accepted": (res) => res && res.status === 101,
  });
  if (!connected) sleep(PROFILE.connectionDurationMs / 1000 + 60);
}
