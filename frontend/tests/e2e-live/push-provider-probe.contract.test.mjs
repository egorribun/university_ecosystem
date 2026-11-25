import assert from "node:assert/strict"
import test from "node:test"

import {
  classifyProbeResponse,
  formatResubscribeLine,
  rateLimitWaitMs,
  requireProviderAcceptedSubscription,
} from "./push-provider-probe.mjs"

const summary = (sent, removed, failed = 0) => ({
  total: 1,
  sent,
  removed,
  failed,
  detail: null,
})

const fakeRun = (responses) => {
  const requests = []
  const waits = []
  const adminPage = {
    evaluate: async (_callback, argument) => {
      requests.push(argument)
      const next = responses.shift()
      if (!next) throw new Error("unexpected probe")
      return next
    },
    waitForTimeout: async (ms) => {
      waits.push(ms)
    },
  }
  const recipientPage = { evaluate: async () => 1 }
  return { adminPage, recipientPage, requests, waits }
}

const options = (run, overrides = {}) => ({
  adminPage: run.adminPage,
  recipientPage: run.recipientPage,
  recipientId: "00000000-0000-4000-8000-000000000001",
  endpoint: "first-endpoint",
  project: "mobile",
  retry: 0,
  probeCase: "topics",
  ...overrides,
})

test("probe responses map to closed classes for exactly one subscription", () => {
  assert.equal(classifyProbeResponse(200, summary(1, 0)), "sent")
  assert.equal(classifyProbeResponse(200, summary(0, 1)), "gone")
  assert.equal(classifyProbeResponse(200, summary(0, 0, 1)), "failed")
  assert.equal(classifyProbeResponse(429, null), "rate-limited")
  assert.equal(classifyProbeResponse(200, { ...summary(1, 0), total: 2 }), "unavailable")
  assert.equal(classifyProbeResponse(200, { total: 1, sent: "1" }), "unavailable")
  assert.equal(classifyProbeResponse(403, summary(1, 0)), "unavailable")
  assert.equal(classifyProbeResponse(200, null), "unavailable")
})

test("the rate-limit wait honours a bounded Retry-After hint", () => {
  assert.equal(rateLimitWaitMs({ retry_after: 4 }), 5_000)
  assert.equal(rateLimitWaitMs({ detail: { retry_after: 9 } }), 10_000)
  assert.equal(rateLimitWaitMs({ retry_after: 600 }), 65_000)
  assert.equal(rateLimitWaitMs({ retry_after: "4" }), 65_000)
  assert.equal(rateLimitWaitMs(null), 65_000)
})

test("a resubscribe record carries only closed project, retry and scenario classes", () => {
  assert.equal(
    formatResubscribeLine({ project: "mobile", retry: 1, probeCase: "topics" }),
    "UE_LIVE_PUSH_RECIPIENT_V1 project=mobile retry=1 scenario=setup check=provider-gone subscription=changed\n"
  )
  assert.equal(
    formatResubscribeLine({ project: "desktop", retry: 0, probeCase: "reply" }),
    "UE_LIVE_PUSH_RECIPIENT_V1 project=desktop retry=0 scenario=reply check=provider-gone subscription=changed\n"
  )
  assert.equal(formatResubscribeLine({ project: "tablet", retry: 0, probeCase: "chat" }), null)
  assert.equal(formatResubscribeLine({ project: "mobile", retry: 2, probeCase: "chat" }), null)
  assert.equal(formatResubscribeLine({ project: "mobile", retry: 0, probeCase: "toString" }), null)
})

test("an accepted subscription is kept and nothing is reported", async () => {
  const run = fakeRun([{ status: 200, body: summary(1, 0) }])
  const lines = []
  let resubscribes = 0
  const result = await requireProviderAcceptedSubscription(
    options(run, {
      resubscribe: async () => {
        resubscribes += 1
        return "second-endpoint"
      },
      emit: (line) => lines.push(line),
    })
  )
  assert.deepEqual(result, { endpoint: "first-endpoint", resubscribed: false })
  assert.equal(resubscribes, 0)
  assert.deepEqual(lines, [])
  assert.deepEqual(run.waits, [15_000], "a new subscription settles before its first probe")
  assert.equal(run.requests[0].userId, "00000000-0000-4000-8000-000000000001")
  assert.match(run.requests[0].probeTag, /^live-push-provider-probe-[0-9a-f-]{36}$/u)
})

test("a provider rejection resubscribes once, is reported, and the new endpoint is used", async () => {
  const run = fakeRun([
    { status: 200, body: summary(0, 1) },
    { status: 200, body: summary(1, 0) },
  ])
  const lines = []
  let resubscribes = 0
  const result = await requireProviderAcceptedSubscription(
    options(run, {
      resubscribe: async () => {
        resubscribes += 1
        run.waits.push("resubscribe")
        return "second-endpoint"
      },
      emit: (line) => lines.push(line),
    })
  )
  assert.deepEqual(result, { endpoint: "second-endpoint", resubscribed: true })
  assert.equal(resubscribes, 1)
  assert.deepEqual(
    run.waits,
    [15_000, "resubscribe", 15_000],
    "the replacement subscription also settles before it is probed"
  )
  assert.equal(lines.length, 1)
  assert.match(lines[0], /scenario=setup check=provider-gone subscription=changed\n$/u)
  assert.notEqual(run.requests[0].probeTag, run.requests[1].probeTag)
})

test("a second provider rejection fails instead of retrying again", async () => {
  const run = fakeRun([
    { status: 200, body: summary(0, 1) },
    { status: 200, body: summary(0, 1) },
  ])
  let resubscribes = 0
  await assert.rejects(
    requireProviderAcceptedSubscription(
      options(run, {
        resubscribe: async () => {
          resubscribes += 1
          return "second-endpoint"
        },
        emit: () => {},
      })
    ),
    /did not accept the test-owned subscription: gone/u
  )
  assert.equal(resubscribes, 1)
})

test("a rate-limited probe waits once and is sent again without resubscribing", async () => {
  const run = fakeRun([
    { status: 429, body: { retry_after: 3 } },
    { status: 200, body: summary(1, 0) },
  ])
  const result = await requireProviderAcceptedSubscription(
    options(run, {
      resubscribe: async () => assert.fail("a rate limit is not a provider rejection"),
      emit: () => {},
    })
  )
  assert.deepEqual(result, { endpoint: "first-endpoint", resubscribed: false })
  assert.deepEqual(run.waits, [15_000, 4_000])
})

test("an unavailable or failed probe fails without resubscribing", async () => {
  for (const response of [
    { status: 0, body: null },
    { status: 200, body: summary(0, 0, 1) },
  ]) {
    const run = fakeRun([response])
    await assert.rejects(
      requireProviderAcceptedSubscription(
        options(run, {
          resubscribe: async () => assert.fail("only a provider rejection resubscribes"),
          emit: () => {},
        })
      ),
      /did not accept the test-owned subscription/u
    )
  }
})

test("a diagnostic sink failure cannot change the acceptance result", async () => {
  const run = fakeRun([
    { status: 200, body: summary(0, 1) },
    { status: 200, body: summary(1, 0) },
  ])
  const result = await requireProviderAcceptedSubscription(
    options(run, {
      resubscribe: async () => "second-endpoint",
      emit: () => {
        throw new Error("sink closed")
      },
    })
  )
  assert.equal(result.endpoint, "second-endpoint")
})
