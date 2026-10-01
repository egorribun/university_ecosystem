import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { createServer } from "node:http"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

import { warmSsrRuntime } from "./server-readiness.mjs"
import { resolveStaticFile } from "./server-static.mjs"

async function reserveLoopbackPort() {
  const probe = createServer()
  await new Promise((resolve, reject) => {
    probe.once("error", reject)
    probe.listen(0, "127.0.0.1", resolve)
  })
  const address = probe.address()
  if (!address || typeof address === "string") {
    await new Promise((resolve) => probe.close(resolve))
    throw new Error("Could not reserve a loopback port for the isolated SSR fixture")
  }
  await new Promise((resolve, reject) =>
    probe.close((error) => (error ? reject(error) : resolve()))
  )
  return address.port
}

async function waitForFixtureServer(child, url) {
  const deadline = Date.now() + 5_000
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error("Isolated SSR fixture exited before becoming ready")
    }
    try {
      return await fetch(url, { signal: AbortSignal.timeout(500) })
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 50))
    }
  }
  throw new Error("Isolated SSR fixture did not become ready")
}

async function stopFixtureServer(child) {
  if (child.exitCode !== null || child.signalCode !== null) return
  child.kill("SIGTERM")
  const stopped = await waitForChildExit(child, 2_000)
  if (stopped) return

  child.kill("SIGKILL")
  await waitForChildExit(child, 1_000)
}

function waitForChildExit(child, timeoutMs) {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true)

  return new Promise((resolve) => {
    const onExit = () => finish(true)
    const finish = (exited) => {
      clearTimeout(timeout)
      child.off("exit", onExit)
      resolve(exited)
    }
    const timeout = setTimeout(() => finish(false), timeoutMs)
    child.once("exit", onExit)
  })
}

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

test(
  "server-prod returns a generic 500 when an isolated synthetic renderer throws",
  { timeout: 10_000 },
  async () => {
    const fixtureRoot = await mkdtemp(path.join(os.tmpdir(), "ue-server-prod-error-"))
    const serverDirectory = path.join(fixtureRoot, "dist", "server")
    await mkdir(serverDirectory, { recursive: true })
    await writeFile(path.join(fixtureRoot, "package.json"), '{"type":"module"}\n')
    await writeFile(
      path.join(serverDirectory, "server.js"),
      [
        "export default {",
        "  async fetch(request) {",
        "    const pathname = new URL(request.url).pathname",
        '    if (pathname === "/login") {',
        '      return new Response("synthetic warmup", { status: 200, headers: { "content-type": "text/html; charset=utf-8" } })',
        "    }",
        '    if (pathname === "/__synthetic_ssr_error__") {',
        '      throw new Error("SYNTHETIC_RENDER_DIAGNOSTIC_ONLY\\n    at fixtureRenderer (fixture.js:1:1)")',
        "    }",
        '    return new Response("Not Found", { status: 404 })',
        "  },",
        "}",
        "",
      ].join("\n")
    )

    let child
    try {
      const port = await reserveLoopbackPort()
      child = spawn(
        process.execPath,
        [fileURLToPath(new URL("./server-prod.mjs", import.meta.url))],
        {
          cwd: fixtureRoot,
          env: {
            PATH: process.env.PATH ?? "",
            SYSTEMROOT: process.env.SYSTEMROOT ?? "",
            WINDIR: process.env.WINDIR ?? "",
            TEMP: process.env.TEMP ?? os.tmpdir(),
            TMP: process.env.TMP ?? os.tmpdir(),
            HOST: "127.0.0.1",
            PORT: String(port),
          },
          stdio: "ignore",
        }
      )

      const origin = `http://127.0.0.1:${port}`
      const warmupResponse = await waitForFixtureServer(child, `${origin}/login`)
      assert.equal(warmupResponse.status, 200)
      await warmupResponse.body?.cancel()

      const response = await fetch(`${origin}/__synthetic_ssr_error__`)
      assert.equal(response.status, 500)
      assert.equal(response.headers.get("content-type"), "text/plain; charset=utf-8")
      const responseBody = await response.text()
      assert.equal(responseBody, "Internal Server Error")
      assert.doesNotMatch(
        responseBody,
        /SYNTHETIC_RENDER_DIAGNOSTIC_ONLY|Traceback|fixtureRenderer|notFound\.(?:title|description|home|login)/u
      )
    } finally {
      if (child) await stopFixtureServer(child)
      await rm(fixtureRoot, { recursive: true, force: true })
    }
  }
)

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
