// Loaded only from a temporary cwd by the real production wrapper in the R67
// browser test. The gate keeps the third render pending while a user retries.
let attempts = 0
let releaseRecovery
const recoveryGate = new Promise((resolve) => {
  releaseRecovery = resolve
})

export default {
  async fetch(request) {
    const path = new globalThis.URL(request.url).pathname
    if (path === "/login") return new globalThis.Response("Synthetic readiness", { status: 200 })
    if (path === "/__r67_release__" && request.method === "POST") {
      releaseRecovery()
      return new globalThis.Response(null, { status: 204 })
    }
    if (path === "/__r67_attempts__") {
      return new globalThis.Response(String(attempts), { status: 200 })
    }
    if (path === "/__r67_safe__") {
      return new globalThis.Response(
        "<!doctype html><html><body><h1>Safe destination</h1></body></html>",
        { headers: { "content-type": "text/html; charset=utf-8" } }
      )
    }
    if (path === "/__r67_error__") {
      attempts += 1
      if (attempts <= 2) {
        throw new Error(
          "R67_SYNTHETIC_PRIVATE_RENDER_ERROR\n    at fixtureRenderer (/private/r67-renderer.ts:17:5)"
        )
      }
      await recoveryGate
      return new globalThis.Response(
        "<!doctype html><html><body><h1>Recovered document</h1></body></html>",
        { headers: { "content-type": "text/html; charset=utf-8" } }
      )
    }
    return new globalThis.Response("Not found", { status: 404 })
  },
}
