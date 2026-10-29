import assert from "node:assert/strict"
import { EventEmitter } from "node:events"
import test from "node:test"
import { runInNewContext } from "node:vm"
import { collectNewsStartupErrors } from "../tests/e2e/aud151-news-errors.mjs"

function deferred() {
  let resolve
  const promise = new Promise((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

function consoleMessage(type, text) {
  return { type: () => type, text: () => text }
}

class FakePage extends EventEmitter {
  hydration = deferred()
  navigationError = undefined
  hydrationError = undefined
  duringNavigation = undefined

  async goto(url, options) {
    assert.equal(url, "/news")
    assert.deepEqual(options, { waitUntil: "commit", timeout: 30_000 })
    this.duringNavigation?.()
    if (this.navigationError) throw this.navigationError
  }

  async waitForFunction(predicate, _arg, options) {
    assert.deepEqual(options, { timeout: 30_000 })
    const probe = `(${predicate.toString()})()`
    assert.equal(runInNewContext(probe, { window: { __APP_HYDRATED: false } }), false)
    assert.equal(runInNewContext(probe, { window: { __APP_HYDRATED: true } }), true)
    if (this.hydrationError) throw this.hydrationError
    await this.hydration.promise
  }
}

const nextTurn = () => new Promise((resolve) => setImmediate(resolve))

test("captures errors until hydration and the route are both ready", async () => {
  const page = new FakePage()
  const route = deferred()
  page.duringNavigation = () => {
    page.emit("console", consoleMessage("error", "console during navigation"))
    page.emit("pageerror", new Error("page error during navigation"))
  }
  let routeStarted = false
  let settled = false
  const result = collectNewsStartupErrors(page, async () => {
    routeStarted = true
    await route.promise
  }).then((errors) => {
    settled = true
    return errors
  })

  await nextTurn()
  assert.equal(settled, false)
  assert.equal(routeStarted, false)
  assert.equal(page.listenerCount("console"), 1)
  assert.equal(page.listenerCount("pageerror"), 1)
  page.emit("console", consoleMessage("error", "console during hydration"))
  page.emit("pageerror", new Error("page error during hydration"))

  page.hydration.resolve()
  await nextTurn()
  assert.equal(routeStarted, true)
  assert.equal(settled, false)
  page.emit("console", consoleMessage("error", "console before route ready"))
  page.emit("pageerror", new Error("page error before route ready"))

  route.resolve()
  assert.deepEqual(await result, {
    consoleErrors: [
      "console during navigation",
      "console during hydration",
      "console before route ready",
    ],
    pageErrors: [
      "page error during navigation",
      "page error during hydration",
      "page error before route ready",
    ],
  })
  assert.equal(page.listenerCount("console"), 0)
  assert.equal(page.listenerCount("pageerror"), 0)
})

test("preserves the existing expected noise filters", async () => {
  const page = new FakePage()
  page.hydration.resolve()
  const errors = await collectNewsStartupErrors(page, async () => {
    for (const text of [
      "ResizeObserver",
      "favicon",
      "net::ERR_CONNECTION_REFUSED",
      "Failed to load resource",
      "status code 401",
    ]) {
      page.emit("console", consoleMessage("error", text))
    }
    page.emit("console", consoleMessage("log", "ordinary log"))
    page.emit("console", consoleMessage("error", "unexpected console error"))
    for (const text of ["ResizeObserver", "AbortError", "NetworkError"]) {
      page.emit("pageerror", new Error(text))
    }
    page.emit("pageerror", new Error("unexpected page error"))
  })

  assert.deepEqual(errors, {
    consoleErrors: ["unexpected console error"],
    pageErrors: ["unexpected page error"],
  })
})

for (const phase of ["navigation", "hydration", "route"]) {
  test(`propagates a ${phase} failure and removes both listeners`, async () => {
    const page = new FakePage()
    const failure = new Error(`${phase} failed`)
    if (phase === "navigation") page.navigationError = failure
    if (phase === "hydration") page.hydrationError = failure
    if (phase === "route") page.hydration.resolve()

    await assert.rejects(
      collectNewsStartupErrors(page, async () => {
        if (phase === "route") throw failure
      }),
      (error) => error === failure
    )
    assert.equal(page.listenerCount("console"), 0)
    assert.equal(page.listenerCount("pageerror"), 0)
  })
}
