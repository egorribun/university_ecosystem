import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

type HeartbeatPing = { connection: number; nonce: string }
type ClientClose = { code: number | undefined; reason: string | undefined }

const HEARTBEAT_INTERVAL_MS = 30_000
const HEARTBEAT_ACK_TIMEOUT_MS = 10_000
const MAX_RECONNECT_ATTEMPTS = 10
const URL_STATE_E2E_ACTIVE = process.env.URL_STATE_E2E === "true"

test.describe("messenger heartbeat blackhole", () => {
  test.skip(
    !URL_STATE_E2E_ACTIVE,
    "Requires URL_STATE_E2E=true build with VITE_LHCI=true auth bypass and messenger realtime enabled"
  )
  test.skip(
    ({ browserName }) => browserName !== "chromium",
    "clock-controlled WebSocket proof is chromium-only"
  )

  test("native browser WebSocket stays bounded through a silent heartbeat blackhole", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.clock.install({ time: new Date("2026-10-23T10:00:00Z") })
    await page.addInitScript(() => {
      // Reconnect delay uses full jitter; keep the browser-side retry schedule
      // deterministic while leaving the cryptographic heartbeat nonce source intact.
      Math.random = () => 0
    })

    const pings: HeartbeatPing[] = []
    const clientCloses: ClientClose[] = []
    let routedConnections = 0

    try {
      await useMockApi(page, { mockWebSocket: false })
      await page.routeWebSocket("**/ws/chat*", (socket) => {
        const connection = ++routedConnections
        // Deliberately blackhole every application message: no pong, no
        // server-originated data, and no server-originated close frame.
        socket.onMessage((message) => {
          if (typeof message !== "string") return
          try {
            const parsed = JSON.parse(message) as { type?: unknown; nonce?: unknown }
            if (parsed.type === "heartbeat_ping" && typeof parsed.nonce === "string") {
              pings.push({ connection, nonce: parsed.nonce })
            }
          } catch {
            // Other valid client messages are irrelevant to this transport proof.
          }
        })
        socket.onClose((code, reason) => {
          clientCloses.push({ code, reason })
        })
      })

      await page.goto("/messenger", { waitUntil: "domcontentloaded", timeout: 30_000 })
      await expect.poll(() => routedConnections).toBe(1)

      for (let attempt = 0; attempt <= MAX_RECONNECT_ATTEMPTS; attempt += 1) {
        await page.clock.runFor(HEARTBEAT_INTERVAL_MS + 1)
        await expect.poll(() => pings.length).toBe(attempt + 1)
        expect(pings[attempt]?.nonce).toMatch(/^[0-9a-f]{32}$/)

        await page.clock.runFor(HEARTBEAT_ACK_TIMEOUT_MS + 1)
        await expect.poll(() => clientCloses.length).toBe(attempt + 1)
        expect(clientCloses[attempt]).toEqual({ code: 4000, reason: "heartbeat_timeout" })

        if (attempt < MAX_RECONNECT_ATTEMPTS) {
          await expect.poll(() => routedConnections).toBe(attempt + 2)
        }
      }

      expect(routedConnections).toBe(MAX_RECONNECT_ATTEMPTS + 1)
      await page.clock.runFor(HEARTBEAT_INTERVAL_MS + HEARTBEAT_ACK_TIMEOUT_MS + 2)
      expect(routedConnections).toBe(MAX_RECONNECT_ATTEMPTS + 1)
    } finally {
      await page.clock.resume()
    }
  })
})
