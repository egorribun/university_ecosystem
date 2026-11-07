import assert from "node:assert/strict"
import { EventEmitter } from "node:events"
import test from "node:test"
import { runInNewContext } from "node:vm"
import { pageErrorsThroughReady } from "./aud151-readiness.mjs"

class FakePage extends EventEmitter {
  async goto(url, options) {
    assert.equal(url, "/")
    assert.equal(options.waitUntil, "domcontentloaded")
  }

  async waitForFunction(predicate, _arg, options) {
    assert.equal(options.timeout, 30_000)
    const probe = `(${predicate.toString()})()`
    assert.equal(runInNewContext(probe, { window: { __APP_HYDRATED: false } }), false)
    assert.equal(runInNewContext(probe, { window: { __APP_HYDRATED: true } }), true)
    this.emit("pageerror", new Error("late hydration failure"))
  }
}

test("captures errors during hydration and route readiness", async () => {
  const page = new FakePage()
  let routeReady = false
  const errors = await pageErrorsThroughReady(page, async () => {
    page.emit("pageerror", new Error("late route failure"))
    routeReady = true
  })

  assert.equal(routeReady, true)
  assert.deepEqual(errors, ["late hydration failure", "late route failure"])
  assert.equal(page.listenerCount("pageerror"), 0)
})

test("propagates readiness failures and removes its listener", async () => {
  const page = new FakePage()
  page.waitForFunction = async () => {
    throw new Error("hydration timed out")
  }

  await assert.rejects(
    pageErrorsThroughReady(page, async () => {}),
    /hydration timed out/u
  )
  assert.equal(page.listenerCount("pageerror"), 0)
})
