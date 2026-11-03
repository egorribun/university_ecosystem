import assert from "node:assert/strict"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"
import {
  REGISTRATION_STEP_ORDER,
  registrationTraceViolations,
} from "./register-double-submit.decisions.mjs"
import {
  isOpaqueRegistrationReceipt,
  waitForRegistrationCompletion,
  withRegistrationDetach,
} from "./register-double-submit-lifecycle.mjs"

const specUrl = new URL("./register-double-submit.live.spec.ts", import.meta.url)

test("live registration double-submit acceptance is an executable ordering decision", async () => {
  assert.equal(
    existsSync(specUrl),
    true,
    "the mobile double-submit registration acceptance must exist"
  )

  // Behaviour: evaluate the live Playwright config and read the effective project settings.
  const { default: liveConfig } = await import("../../playwright.live.config.ts")
  const projects = Object.fromEntries(liveConfig.projects.map((project) => [project.name, project]))
  assert.ok(projects.desktop, "the desktop acceptance project must exist")
  assert.ok(projects.mobile, "the mobile acceptance project must exist")
  for (const name of ["desktop", "mobile"]) {
    const use = { ...liveConfig.use, ...projects[name].use }
    assert.equal(use.trace, "off", `${name} must not record traces`)
    assert.equal(use.screenshot, "off", `${name} must not capture screenshots`)
    assert.equal(use.video, "off", `${name} must not record video`)
  }

  // The live spec records each step into a trace and asserts the trace with this validator.
  // Wiring: every step of the decision must be recorded by the spec.
  const spec = await readFile(specUrl, "utf8")
  assert.ok(spec.includes('from "./register-double-submit.decisions.mjs"'))
  for (const step of REGISTRATION_STEP_ORDER) {
    assert.ok(spec.includes(`trace.push("${step}")`), `the spec must record ${step}`)
  }
  assert.ok(spec.includes("registrationTraceViolations(trace, registerPostCount)"))

  // Static policy guards kept deliberately: the acceptance must reach the real registration
  // API (no route mocking or direct API posts) and must not embed a literal password. Only a
  // live run can exercise the behaviour itself.
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|page\.request\.(?:post|put|patch|delete)\(|fulfill\(/u
  )
  assert.doesNotMatch(spec, /password\s*[:=]\s*["'][^"']+/iu)
})

test("the ordering decision accepts the legal sequence with exactly one registration POST", () => {
  assert.deepEqual(registrationTraceViolations([...REGISTRATION_STEP_ORDER], 1), [])
})

test("the ordering decision rejects a registration that is not single or not ordered", () => {
  const legal = [...REGISTRATION_STEP_ORDER]
  const swap = (a, b) => legal.map((step) => (step === a ? b : step === b ? a : step))

  assert.ok(
    registrationTraceViolations(legal, 2).includes("expected exactly one registration POST, saw 2")
  )
  assert.ok(registrationTraceViolations(legal, 0).length > 0)
  assert.ok(
    registrationTraceViolations(swap("hydrated", "filled"), 1).includes("filled before hydrated")
  )
  assert.ok(
    registrationTraceViolations(swap("cleanup-registered", "submitted"), 1).includes(
      "submitted before cleanup-registered"
    )
  )
  assert.ok(
    registrationTraceViolations(swap("listener-attached", "submitted"), 1).includes(
      "submitted before listener-attached"
    )
  )
  assert.ok(registrationTraceViolations([...legal, "submitted"], 1).includes("duplicate submitted"))
  assert.ok(
    registrationTraceViolations(
      legal.filter((step) => step !== "page-closed"),
      1
    ).includes("missing page-closed")
  )
  assert.ok(
    registrationTraceViolations(
      legal.filter((step) => step !== "hydrated"),
      1
    ).length > 0
  )
})

test("registration accepts only the generic success receipt", () => {
  assert.equal(isOpaqueRegistrationReceipt({ status: "ok" }), true)
  for (const invalid of [
    null,
    undefined,
    [],
    "ok",
    {},
    { status: "error" },
    { status: "ok", id: "unexpected-public-identifier" },
  ]) {
    assert.equal(isOpaqueRegistrationReceipt(invalid), false)
  }
})

test("registration detaches after success and preserves the result", async () => {
  let detached = 0
  let reported = 0
  const result = await withRegistrationDetach(
    async () => "result",
    async () => {
      detached += 1
    },
    () => {
      reported += 1
    }
  )
  assert.equal(result, "result")
  assert.equal(detached, 1)
  assert.equal(reported, 0)
})

test("a detach failure does not mask a registration failure", async () => {
  const primary = new Error("registration failed")
  let reported = 0
  await assert.rejects(
    withRegistrationDetach(
      async () => {
        throw primary
      },
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        reported += 1
      }
    ),
    (error) => error === primary
  )
  assert.equal(reported, 1)
})

test("a detach failure after success remains a failure without exposing CDP details", async () => {
  await assert.rejects(
    withRegistrationDetach(
      async () => "result",
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        throw new Error("unused")
      }
    ),
    (error) =>
      error instanceof Error &&
      error.message === "Registration browser cleanup failed" &&
      !String(error).includes("private CDP details")
  )
})

test("a broken detach diagnostic cannot replace the registration failure", async () => {
  const primary = new Error("registration failed")
  let diagnostics = 0
  await assert.rejects(
    withRegistrationDetach(
      async () => {
        throw primary
      },
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        diagnostics += 1
        throw new Error("diagnostic failed")
      }
    ),
    (error) => error === primary
  )
  assert.equal(diagnostics, 1)
})

test("registration cleanup waits for all observed request completions", async () => {
  let finish
  const pending = new Promise((resolve) => {
    finish = resolve
  })
  let settled = false
  const result = waitForRegistrationCompletion([Promise.resolve(true), pending], 500).then(
    (value) => {
      settled = true
      return value
    }
  )
  await new Promise((resolve) => globalThis.setImmediate(resolve))
  assert.equal(settled, false)
  finish(true)
  assert.equal(await result, true)
})

test("failed or missing request completion remains unverified", async () => {
  assert.equal(await waitForRegistrationCompletion([], 100), false)
  assert.equal(await waitForRegistrationCompletion([Promise.resolve(true)], 0), false)
  assert.equal(await waitForRegistrationCompletion([Promise.resolve(false)], 100), false)
  const failedRequest = Promise.reject(new Error("private transport"))
  void failedRequest.catch(() => undefined)
  assert.equal(await waitForRegistrationCompletion([failedRequest], 100), false)
  assert.equal(await waitForRegistrationCompletion([new Promise(() => {})], 10), false)
})

test("every required registration step is mandatory and unique", () => {
  for (const step of REGISTRATION_STEP_ORDER) {
    const missing = REGISTRATION_STEP_ORDER.filter((entry) => entry !== step)
    assert.ok(registrationTraceViolations(missing, 1).includes(`missing ${step}`))
    assert.ok(
      registrationTraceViolations([...REGISTRATION_STEP_ORDER, step], 1).includes(
        `duplicate ${step}`
      )
    )
  }
})

test("every inverted registration step pair is rejected", () => {
  for (let left = 0; left < REGISTRATION_STEP_ORDER.length; left += 1) {
    for (let right = left + 1; right < REGISTRATION_STEP_ORDER.length; right += 1) {
      const trace = [...REGISTRATION_STEP_ORDER]
      ;[trace[left], trace[right]] = [trace[right], trace[left]]
      assert.ok(
        registrationTraceViolations(trace, 1).includes(
          `${REGISTRATION_STEP_ORDER[right]} before ${REGISTRATION_STEP_ORDER[left]}`
        )
      )
    }
  }
})

test("registration count accepts only the integer one", () => {
  for (const count of [-1, 0, 2, 1.5, Number.NaN, Infinity, "1", null, undefined]) {
    assert.ok(registrationTraceViolations([...REGISTRATION_STEP_ORDER], count).length > 0)
  }
})
