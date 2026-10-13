import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { createServer, request as httpRequest } from "node:http"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { gunzipSync, gzipSync } from "node:zlib"
import { JSDOM } from "jsdom"

import {
  applyNodeCspToHtmlResponse,
  buildNodeCspHeaders,
  createCspNoncePlaceholderTransform,
  CSP_NONCE_PLACEHOLDER,
} from "./server-csp.mjs"
import { warmSsrRuntime } from "./server-readiness.mjs"
import { resolveStaticFile } from "./server-static.mjs"

const REPOSITORY_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")

const SAFE_NOT_FOUND_HTML_FIXTURE = [
  "<!doctype html>",
  '<script nonce="__CSP_NONCE__" src="/not-found-i18n.js"></script>',
  "<script>raw()</script>",
].join("")

function parseScriptElements(html) {
  const { document } = new JSDOM(html).window
  return Array.from(document.querySelectorAll("script"), (script) => ({
    nonce: script.getAttribute("nonce"),
    src: script.getAttribute("src"),
    body: script.textContent?.trim() ?? "",
  }))
}

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

function requestRaw(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const request = httpRequest(url, { headers }, (response) => {
      const chunks = []
      response.on("data", (chunk) => chunks.push(Buffer.from(chunk)))
      response.once("error", reject)
      response.once("end", () => {
        resolve({
          status: response.statusCode,
          headers: response.headers,
          body: Buffer.concat(chunks),
        })
      })
    })
    request.once("error", reject)
    request.end()
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

test(
  "warmSsrRuntime keeps the request alive through timeout under forced garbage collection",
  { timeout: 8_000 },
  async () => {
    const readinessModuleUrl = new URL("./server-readiness.mjs", import.meta.url).href
    const childScript = [
      'import assert from "node:assert/strict"',
      `import { warmSsrRuntime } from ${JSON.stringify(readinessModuleUrl)}`,
      'assert.equal(typeof globalThis.gc, "function")',
      "let signal",
      "let requestReference",
      "const warmup = warmSsrRuntime({",
      "  fetch(request) {",
      "    signal = request.signal",
      "    requestReference = new WeakRef(request)",
      "    return new Promise(() => undefined)",
      "  },",
      '}, { url: "http://frontend.local/login", timeoutMs: 1_000 })',
      "for (let attempt = 0; attempt < 8; attempt += 1) {",
      "  globalThis.gc()",
      "  await new Promise((resolve) => setImmediate(resolve))",
      "}",
      "await assert.rejects(warmup, /exceeded 1000ms/u)",
      'assert.ok(requestReference.deref(), "request must survive forced GC through timeout")',
      "assert.equal(signal.aborted, true)",
      'assert.match(signal.reason?.message ?? "", /exceeded 1000ms/u)',
      'process.stdout.write("readiness-abort-gc-ok\\n")',
    ].join("\n")

    let stdout = ""
    let stderr = ""
    const child = spawn(
      process.execPath,
      ["--expose-gc", "--max-old-space-size=128", "--input-type=module", "-e", childScript],
      {
        cwd: REPOSITORY_ROOT,
        env: {
          PATH: process.env.PATH ?? "",
          SYSTEMROOT: process.env.SYSTEMROOT ?? "",
          WINDIR: process.env.WINDIR ?? "",
          TEMP: process.env.TEMP ?? os.tmpdir(),
          TMP: process.env.TMP ?? os.tmpdir(),
        },
        stdio: ["ignore", "pipe", "pipe"],
      }
    )
    child.stdout.setEncoding("utf8")
    child.stdout.on("data", (chunk) => {
      stdout += chunk
    })
    child.stderr.setEncoding("utf8")
    child.stderr.on("data", (chunk) => {
      stderr += chunk
    })

    const result = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => child.kill("SIGKILL"), 5_000)
      child.once("error", (error) => {
        clearTimeout(timeout)
        reject(error)
      })
      child.once("close", (code, signal) => {
        clearTimeout(timeout)
        resolve({ code, signal })
      })
    })
    assert.equal(result.signal, null, stderr)
    assert.equal(result.code, 0, stderr)
    assert.equal(stdout.trim(), "readiness-abort-gc-ok", stderr)
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

test("Node production CSP defaults match the shared policy contract", async () => {
  const contract = JSON.parse(
    await readFile(path.join(REPOSITORY_ROOT, "quality", "frontend-csp-defaults.json"), "utf8")
  )

  const headers = buildNodeCspHeaders(contract.nonce)
  assert.deepEqual(headers, contract.headers)

  const enforced = headers["content-security-policy"]
  const reportOnly = headers["content-security-policy-report-only"].replace(
    "; report-uri /api/v1/csp-report",
    ""
  )
  assert.ok(enforced.includes("upgrade-insecure-requests"))
  assert.equal(reportOnly, enforced.replace("; upgrade-insecure-requests", ""))
  assert.ok(reportOnly.includes("trusted-types app dompurify-news goog#html 'allow-duplicates'"))
  assert.ok(reportOnly.includes("require-trusted-types-for 'script'"))
})

test("HTML CSP response headers preserve compressed bytes and leave non-HTML untouched", async () => {
  const nonce = "ResponseNonce+/_=="
  const htmlBytes = Buffer.from(
    [
      "<!doctype html><!-- <script>comment()</script> -->",
      '<div title="nonce=old"></div>',
      "<script>untrusted()</script>",
    ].join(""),
    "utf8"
  )
  const compressedHtml = gzipSync(htmlBytes)
  const htmlResponse = new Response(compressedHtml, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "content-encoding": "gzip",
      etag: '"stale"',
      "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
    },
  })
  const securedHtml = applyNodeCspToHtmlResponse(htmlResponse, nonce)
  const securedBytes = Buffer.from(await securedHtml.arrayBuffer())

  assert.deepEqual(gunzipSync(securedBytes), htmlBytes)
  assert.equal(securedHtml.headers.get("content-encoding"), "gzip")
  assert.equal(securedHtml.headers.get("cache-control"), "no-store, private, max-age=0")
  assert.equal(securedHtml.headers.has("etag"), false)
  assert.equal(securedHtml.headers.has("last-modified"), false)
  assert.ok(securedHtml.headers.get("content-security-policy").includes(`'nonce-${nonce}'`))

  const jsonResponse = new Response('{"ok":true}', {
    headers: { "content-type": "application/json" },
  })
  assert.equal(applyNodeCspToHtmlResponse(jsonResponse, nonce), jsonResponse)
})

test("stream transform replaces only explicit markers across UTF-8 and chunk boundaries", async () => {
  const nonce = "ChunkNonce+/_=="
  const input = Buffer.from(
    [
      "Сеть ",
      '<div title="nonce=old"><!-- <script>comment()</script> -->',
      `<script nonce="${CSP_NONCE_PLACEHOLDER}">trusted()</script>`,
      "<script>const markup = '<script nonce=\"old\">';</script>",
      "<script>untrusted()</script>",
    ].join(""),
    "utf8"
  )
  const markerStart = input.indexOf(Buffer.from(CSP_NONCE_PLACEHOLDER, "ascii"))
  const chunks = [
    input.subarray(0, 1),
    input.subarray(1, markerStart + 5),
    input.subarray(markerStart + 5, input.length - 1),
    input.subarray(input.length - 1),
  ]
  const output = await new Promise((resolve, reject) => {
    const transform = createCspNoncePlaceholderTransform(nonce)
    const parts = []
    transform.on("data", (part) => parts.push(Buffer.from(part)))
    transform.once("error", reject)
    transform.once("end", () => resolve(Buffer.concat(parts)))
    for (const chunk of chunks) transform.write(chunk)
    transform.end()
  })

  assert.deepEqual(
    output,
    Buffer.from(input.toString("utf8").replaceAll(CSP_NONCE_PLACEHOLDER, nonce), "utf8")
  )
  assert.match(output.toString("utf8"), /<script>untrusted\(\)<\/script>/u)
})

test(
  "server-prod gives controlled static HTML a fresh nonce and keeps raw scripts nonce-less",
  { timeout: 10_000 },
  async () => {
    const fixtureRoot = await mkdtemp(path.join(os.tmpdir(), "ue-server-prod-csp-"))
    const serverDirectory = path.join(fixtureRoot, "dist", "server")
    const clientDirectory = path.join(fixtureRoot, "dist", "client")
    await mkdir(serverDirectory, { recursive: true })
    await mkdir(clientDirectory, { recursive: true })
    await writeFile(path.join(fixtureRoot, "package.json"), '{"type":"module"}\n')
    await writeFile(
      path.join(serverDirectory, "server.js"),
      [
        "export default {",
        "  async fetch(request) {",
        '    if (new URL(request.url).pathname === "/login") {',
        '      return new Response("warm", {',
        '        headers: { "content-type": "text/html; charset=utf-8" },',
        "      })",
        "    }",
        '    if (new URL(request.url).pathname === "/api-data") {',
        "      return new Response(JSON.stringify({ ok: true }), {",
        '        headers: { "content-type": "application/json" },',
        "      })",
        "    }",
        '    return new Response("not found", {',
        "      status: 404,",
        '      headers: { "content-type": "text/html; charset=utf-8" },',
        "    })",
        "  },",
        "}",
        "",
      ].join("\n")
    )
    const offlineHtml = await readFile(new URL("../public/offline.html", import.meta.url))
    await writeFile(path.join(clientDirectory, "offline.html"), offlineHtml)
    // Fixed test-only markup; no request data is placed into this HTML.
    await writeFile(path.join(clientDirectory, "not-found.html"), SAFE_NOT_FOUND_HTML_FIXTURE)

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

      const first = await requestRaw(`${origin}/offline.html`, { "accept-encoding": "gzip" })
      const second = await requestRaw(`${origin}/offline.html`, { "accept-encoding": "gzip" })
      assert.equal(first.status, 200)
      assert.equal(first.headers["content-encoding"], "gzip")
      assert.equal(first.headers["cache-control"], "no-store, private, max-age=0")
      assert.equal(first.headers.etag, undefined)
      assert.equal(first.headers["last-modified"], undefined)
      assert.equal(first.headers["content-length"], undefined)

      const firstHtml = gunzipSync(first.body).toString("utf8")
      const firstNonce = first.headers["content-security-policy"].match(/'nonce-([^']+)'/u)?.[1]
      assert.ok(firstNonce)
      assert.notEqual(
        firstNonce,
        second.headers["content-security-policy"].match(/'nonce-([^']+)'/u)?.[1]
      )
      assert.equal(
        firstHtml,
        offlineHtml.toString("utf8").replaceAll(CSP_NONCE_PLACEHOLDER, firstNonce)
      )
      assert.deepEqual(
        parseScriptElements(firstHtml).map(({ nonce, src }) => ({ nonce, src })),
        [{ nonce: firstNonce, src: null }]
      )
      assert.doesNotMatch(firstHtml, /onclick=/u)

      const notFound = await requestRaw(`${origin}/missing-page`, { accept: "text/html" })
      const notFoundHtml = notFound.body.toString("utf8")
      const notFoundNonce =
        notFound.headers["content-security-policy"].match(/'nonce-([^']+)'/u)?.[1]
      assert.equal(notFound.status, 404)
      assert.ok(notFoundNonce)
      assert.deepEqual(parseScriptElements(notFoundHtml), [
        { nonce: notFoundNonce, src: "/not-found-i18n.js", body: "" },
        { nonce: null, src: null, body: "raw()" },
      ])

      const json = await requestRaw(`${origin}/api-data`)
      assert.equal(json.headers["content-security-policy"], undefined)
      assert.equal(json.headers["content-security-policy-report-only"], undefined)
    } finally {
      if (child) await stopFixtureServer(child)
      await rm(fixtureRoot, { recursive: true, force: true })
    }
  }
)

test("server nonce flows only through the trusted Start router option", async () => {
  const serverSource = await readFile(new URL("../src/server.ts", import.meta.url), "utf8")
  const routerSource = await readFile(new URL("../src/router.ts", import.meta.url), "utf8")
  const shellSource = await readFile(new URL("./post-build-shell.mjs", import.meta.url), "utf8")
  const offlineSource = await readFile(new URL("../public/offline.html", import.meta.url), "utf8")
  const serverProdSource = await readFile(new URL("./server-prod.mjs", import.meta.url), "utf8")

  assert.match(serverSource, /requestNonceStorage\.run\(nonce/u)
  const healthFastPath = serverSource.indexOf('url.pathname === "/healthz"')
  const nonceGeneration = serverSource.search(
    /^[ \t]*const nonce[ \t]*=[ \t\r\n]*process\.env\.TSS_PRERENDERING === "true"/mu
  )
  assert.ok(
    healthFastPath >= 0 && nonceGeneration > healthFastPath,
    "the JSON health fast path stays ahead of nonce and CSP work"
  )
  assert.match(serverSource, /randomBytes\(16\)\.toString\("base64"\)/u)
  assert.doesNotMatch(serverSource, /replaceCspNoncePlaceholder|NonceHeader|nonce-header/iu)
  assert.match(serverSource, /handler\.fetch\(request,\s*requestOptions\)/u)
  assert.match(serverSource, /applyNodeCspToHtmlResponse\(response, nonce\)/u)
  assert.match(routerSource, /ssr:\s*\{\s*nonce:\s*ssrNonce\s*\}/u)
  assert.match(routerSource, /globalThis\.__ssrNonceGetter__\?\.\(\)/u)
  assert.match(routerSource, /meta\[property="csp-nonce"\]/u)
  assert.match(routerSource, /export function getRouter\(\)\s*\{\s*return createAppRouter\(true\)/u)
  assert.doesNotMatch(shellSource, /injectCspNoncePlaceholders|replace\(\/<script/u)
  assert.match(shellSource, /markNotFoundTrustedScript/u)
  assert.match(serverProdSource, /createCspNoncePlaceholderTransform\(nonce\)/u)
  assert.match(serverProdSource, /applyNodeCspToHtmlResponse\(/u)
  assert.doesNotMatch(offlineSource, /\bonclick\s*=/iu)
  assert.match(offlineSource, /<script nonce="__CSP_NONCE__">/u)
  assert.match(offlineSource, /addEventListener\("click"/u)
})
