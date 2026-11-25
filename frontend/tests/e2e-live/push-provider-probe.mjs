import { randomUUID } from "node:crypto"
import process from "node:process"
import { expect } from "@playwright/test"

// A push provider can report a just-created endpoint as gone (HTTP 410)
// within seconds, while the browser still holds it. Probe each new test-owned
// subscription before a scenario depends on it, and resubscribe once on a
// provider rejection. Scenario assertions stay strict: they never absorb a 410.
// Each rejection is reported through the existing recipient observation
// protocol. Never return an endpoint, key, request or error text to the runner.
const PROJECTS = new Set(["desktop", "mobile"])
const SCENARIOS = { topics: "setup", chat: "chat", reply: "reply" }
const PROBE_TAG_PREFIX = "live-push-provider-probe-"
const NOTIFICATION_WAIT_MS = 30_000
const MAX_RATE_LIMIT_WAIT_MS = 65_000
const MAX_ATTEMPTS = 2

/** Map a `/api/v1/push/test` response for one subscription to a closed class. */
export function classifyProbeResponse(status, body) {
  if (status === 429) return "rate-limited"
  if (status !== 200 || body === null || typeof body !== "object") return "unavailable"
  const { total, sent, removed, failed } = body
  if (![total, sent, removed, failed].every(Number.isInteger) || total !== 1) {
    return "unavailable"
  }
  if (sent === 1) return "sent"
  if (removed === 1) return "gone"
  return "failed"
}

/** Bound the server's Retry-After hint; a missing hint waits the full window. */
export function rateLimitWaitMs(body) {
  const hint =
    body !== null && typeof body === "object"
      ? (body.retry_after ?? body.detail?.retry_after)
      : undefined
  if (!Number.isInteger(hint) || hint <= 0) return MAX_RATE_LIMIT_WAIT_MS
  return Math.min(MAX_RATE_LIMIT_WAIT_MS, hint * 1_000 + 1_000)
}

/** Record a provider rejection that forced one resubscribe, as a closed class. */
export function formatResubscribeLine({ project, retry, probeCase }) {
  const scenario = Object.hasOwn(SCENARIOS, probeCase) ? SCENARIOS[probeCase] : null
  if (!PROJECTS.has(project) || (retry !== 0 && retry !== 1) || scenario === null) return null
  return `UE_LIVE_PUSH_RECIPIENT_V1 project=${project} retry=${retry} scenario=${scenario} check=provider-gone subscription=changed\n`
}

const sendProbe = (adminPage, recipientId, tag) =>
  adminPage.evaluate(
    async ({ userId, probeTag }) => {
      const csrfCookie = globalThis.document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return { status: 0, body: null }
      const response = await globalThis.fetch("/api/v1/push/test", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
        },
        body: JSON.stringify({
          user_id: userId,
          topic: "system",
          title: "Live push provider probe",
          body: "Provider readiness probe",
          tag: probeTag,
          ttl: 60,
        }),
      })
      return { status: response.status, body: await response.json().catch(() => null) }
    },
    { userId: recipientId, probeTag: tag }
  )

const closeProbeNotification = (recipientPage, tag) =>
  expect
    .poll(
      () =>
        recipientPage.evaluate(async (probeTag) => {
          const registration = await globalThis.navigator.serviceWorker.ready
          const shown = await registration.getNotifications({ tag: probeTag })
          for (const notification of shown) notification.close()
          return shown.length
        }, tag),
      {
        timeout: NOTIFICATION_WAIT_MS,
        message: "the provider probe reaches the recipient service worker",
      }
    )
    .toBeGreaterThan(0)

/**
 * Require the push provider to accept the recipient's only subscription.
 * Returns the endpoint to use from now on: the original one, or the one a
 * single resubscribe created after the provider reported the first as gone.
 */
export async function requireProviderAcceptedSubscription({
  adminPage,
  recipientPage,
  recipientId,
  endpoint,
  project,
  retry,
  probeCase,
  resubscribe,
  emit = (line) => process.stdout.write(line),
}) {
  const reportResubscribe = () => {
    const line = formatResubscribeLine({ project, retry, probeCase })
    if (line === null) return
    try {
      emit(line)
    } catch {
      // A diagnostic sink failure cannot change the acceptance result.
    }
  }
  let currentEndpoint = endpoint
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const tag = `${PROBE_TAG_PREFIX}${randomUUID()}`
    let response = await sendProbe(adminPage, recipientId, tag)
    let result = classifyProbeResponse(response.status, response.body)
    if (result === "rate-limited") {
      await adminPage.waitForTimeout(rateLimitWaitMs(response.body))
      response = await sendProbe(adminPage, recipientId, tag)
      result = classifyProbeResponse(response.status, response.body)
    }
    if (result === "sent") {
      await closeProbeNotification(recipientPage, tag)
      return { endpoint: currentEndpoint, resubscribed: attempt > 1 }
    }
    if (result !== "gone" || attempt === MAX_ATTEMPTS) {
      throw new Error(`the push provider did not accept the test-owned subscription: ${result}`)
    }
    reportResubscribe()
    currentEndpoint = await resubscribe()
  }
  throw new Error("the push provider probe ended without a result")
}

/** Turn native push off and on again in Settings and return the new endpoint. */
export async function resubscribeThroughPushSwitch(page, openPushSettings, timeoutMs) {
  await openPushSettings(page)
  const pushSwitch = page.getByRole("switch", { name: "Включить уведомления", exact: true })
  await expect(pushSwitch).toBeChecked()
  const isPushRequest = (pathname) => (response) =>
    response.request().method() === "POST" &&
    new globalThis.URL(response.url()).pathname === pathname
  const unsubscribed = page.waitForResponse(isPushRequest("/api/v1/push/unsubscribe"), {
    timeout: timeoutMs,
  })
  await pushSwitch.click()
  expect((await unsubscribed).status(), "turning push off releases the rejected binding").toBe(200)
  await expect(pushSwitch).not.toBeChecked()

  const subscribed = page.waitForResponse(isPushRequest("/api/v1/push/subscribe"), {
    timeout: timeoutMs,
  })
  await pushSwitch.click()
  const response = await subscribed
  expect(response.status(), "turning push on again stores a new browser endpoint").toBe(200)
  const receipt = await response.json()
  if (typeof receipt?.endpoint !== "string") {
    throw new Error("the server push binding did not include its endpoint")
  }
  const browserEndpoint = await page.evaluate(async () => {
    const registration = await globalThis.navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    if (!subscription) return null
    const url = new globalThis.URL(subscription.endpoint)
    return url.protocol === "https:" && url.hostname !== globalThis.location.hostname
      ? subscription.endpoint
      : null
  })
  expect(
    browserEndpoint === receipt.endpoint,
    "the new server binding belongs to the new provider-issued browser endpoint"
  ).toBe(true)
  await expect(pushSwitch).toBeChecked()
  return receipt.endpoint
}
