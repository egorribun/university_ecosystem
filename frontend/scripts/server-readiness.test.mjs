import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import path from "node:path"
import test from "node:test"

import { warmSsrRuntime } from "./server-readiness.mjs"
import { resolveStaticFile } from "./server-static.mjs"

test("warmSsrRuntime consumes the complete SSR body before readiness", async () => {
  let bodyCompleted = false
  const handler = {
    async fetch(request) {
      assert.equal(new URL(request.url).pathname, "/login")
      assert.equal(request.headers.get("accept"), "text/html")
      return new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode("warm"))
            controller.close()
            bodyCompleted = true
          },
        })
      )
    },
  }

  await warmSsrRuntime(handler, { url: "http://frontend.local/login", timeoutMs: 1_000 })

  assert.equal(bodyCompleted, true)
})

test("warmSsrRuntime fails closed on a non-200 route", async () => {
  await assert.rejects(
    warmSsrRuntime(
      { fetch: async () => new Response("unavailable", { status: 503 }) },
      { url: "http://frontend.local/login", timeoutMs: 1_000 }
    ),
    /returned HTTP 503/u
  )
})

test("warmSsrRuntime aborts a hung render before advertising readiness", async () => {
  let signal
  await assert.rejects(
    warmSsrRuntime(
      {
        fetch: (request) => {
          signal = request.signal
          return new Promise(() => undefined)
        },
      },
      { url: "http://frontend.local/login", timeoutMs: 10 }
    ),
    /exceeded 10ms/u
  )
  assert.equal(signal.aborted, true)
})

test("server startup warms SSR before binding the readiness port", async () => {
  const source = await readFile(new URL("./server-prod.mjs", import.meta.url), "utf8")
  const warmup = source.indexOf("await warmSsrRuntime")
  const listen = source.indexOf("server.listen")

  assert.ok(warmup >= 0)
  assert.ok(listen > warmup, "the health port must not bind before SSR warmup completes")
})

test("the Lighthouse SSR preview gives its explicit port precedence", async () => {
  const source = await readFile(new URL("./server-prod.mjs", import.meta.url), "utf8")
  const portDeclaration = source.slice(
    source.indexOf("const PORT ="),
    source.indexOf("const HOST =")
  )

  assert.match(
    portDeclaration,
    /isLhciSsrResponseMode\(\)\s*&&\s*lhciPreviewMode\.kind\s*===\s*"ssr"\s*\?\s*lhciPreviewMode\.port/u
  )
  assert.match(portDeclaration, /process\.env\.PORT/u)
})

test("a failed readiness warmup terminates instead of leaving a non-listening process alive", async () => {
  const source = await readFile(new URL("./server-prod.mjs", import.meta.url), "utf8")
  const catchBlock = source.slice(
    source.indexOf("void startServer().catch"),
    source.indexOf("const shutdown")
  )

  assert.match(catchBlock, /process\.exit\(1\)/u)
  assert.doesNotMatch(catchBlock, /process\.exitCode\s*=/u)
})

test("static asset resolution enforces a directory boundary", () => {
  const root = "C:/app/dist/client"
  const outside = path.resolve(root, "..", "client_secrets", "token")
  const relativeOutside = path.relative(root, outside)
  const encodedOutside = relativeOutside
    .split(path.sep)
    .map((segment) => encodeURIComponent(segment))
    .join("/")

  assert.equal(resolveStaticFile(root, "/assets/app.js"), path.resolve(root, "assets/app.js"))
  assert.equal(resolveStaticFile(root, relativeOutside), null)
  assert.equal(resolveStaticFile(root, encodedOutside), null)
})

test("static asset resolution fails closed on malformed URI encoding", () => {
  assert.equal(resolveStaticFile("C:/app/dist/client", "/%ff"), null)
})
