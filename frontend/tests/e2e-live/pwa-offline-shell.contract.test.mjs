import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFile } from "node:fs/promises"
import { clearTimeout as clearNodeTimeout, setTimeout as setNodeTimeout } from "node:timers"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./pwa-offline-shell.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const globalSetupUrl = new URL("../../scripts/playwright-live-global-setup.mjs", import.meta.url)
const precachingUrl = new URL("../../src/sw/precaching.ts", import.meta.url)
const workboxConfigUrl = new URL("../../scripts/workbox-config.mjs", import.meta.url)
const serviceWorkerRegistrationUrl = new URL("../../src/push/register-sw.ts", import.meta.url)
const serviceWorkerUrl = new URL("../../src/sw.ts", import.meta.url)
const updateProxyUrl = new URL("./pwa-update-proxy.ts", import.meta.url)

const [
  spec,
  config,
  globalSetup,
  precaching,
  workboxConfig,
  serviceWorkerRegistration,
  serviceWorker,
  updateProxy,
] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(globalSetupUrl, "utf8"),
  readFile(precachingUrl, "utf8"),
  readFile(workboxConfigUrl, "utf8"),
  readFile(serviceWorkerRegistrationUrl, "utf8"),
  readFile(serviceWorkerUrl, "utf8"),
  readFile(updateProxyUrl, "utf8"),
])

function assertProxySource(pattern, message) {
  assert.ok(pattern.test(updateProxy), message)
}

test("live PWA shell acceptance exercises the real worker without server mutations or mocks", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /globalSetup:\s*["']\.\/scripts\/playwright-live-global-setup\.mjs["']/u)
  assert.match(globalSetup, /verify-endpoints/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /page\.goto\(["']\/login["']/u)
  assert.match(spec, /page\.goto\(["']\/register["']/u)
  assert.match(spec, /context\.setOffline\(true\)/u)
  assert.match(spec, /context\.setOffline\(false\)/u)
  assert.match(spec, /Network\.setCacheDisabled/u)
  assert.match(spec, /data-render-mode/u)
  assert.match(spec, /window\.__APP_HYDRATED/u)
  assert.match(spec, /workbox-precache/u)
  assert.match(spec, /requestfailed/u)
  assert.match(spec, /const offlineAssetRequests: string\[\] = \[\]/u)
  assert.match(spec, /const recordOfflineAssetRequest = \(request: Request\)/u)
  assert.match(spec, /offlineAssetRequests\.push\(url\.pathname\)/u)
  assert.match(
    spec,
    /offlineAssetRequests\.every\(\(path\) => precacheEvidence\.precachedPaths\.includes\(path\)\)/u
  )
  assert.doesNotMatch(
    spec,
    /useMockApi|page\.route|routeWebSocket|page\.request|\.fill\(|\.click\(/u
  )

  assert.match(precaching, /new NetworkOnly\(/u)
  assert.match(precaching, /handlerDidError/u)
  assert.match(precaching, /matchPrecache\("_shell\.html"\)/u)
  assert.ok(
    workboxConfig.includes('globPatterns: ["**/*.{js,css,html,ico,png,svg,webp,json}"]'),
    "the production precache must include shell HTML and its app bundles"
  )
})

test("live PWA update replaces the active precache and proves the new app bundle works offline", () => {
  assert.match(
    spec,
    /updates the active service worker online and serves the new precached bundle offline/u
  )
  assert.match(spec, /replacePrecacheRevision/u)
  assert.match(spec, /startPwaUpdateProxy\(context,\s*ownedSessionOrigin\(\)\)/u)
  assert.match(spec, /setWorkerResponseTransform/u)
  assert.doesNotMatch(spec, /context\.route\(["']\*\*\/sw\.js["']/u)
  assert.match(spec, /context\.route\(["']\*\*\/assets\/\*\*["']/u)
  assertProxySource(
    /import \{ isIP, type AddressInfo \} from ["\x27]node:net["\x27]/u,
    "proxy uses Node loopback address helpers"
  )
  assertProxySource(
    /parsed\.protocol !== ["\x27]http:["\x27]/u,
    "proxy requires HTTP for the owned local stand"
  )
  assertProxySource(
    /parsed\.hostname !== ["\x27]localhost["\x27]/u,
    "proxy pins the configured live origin host"
  )
  assertProxySource(
    /const proxyOrigin = new URL\(["\x27]http:\/\/localhost:0["\x27]\)/u,
    "browser-facing proxy keeps localhost origin semantics"
  )
  assertProxySource(
    /server\.listen\(\s*0\s*,\s*["\x27]127\.0\.0\.1["\x27]/u,
    "proxy binds only to IPv4 loopback"
  )
  assertProxySource(
    /proxyOrigin\.port = String\(\(address as AddressInfo\)\.port\)/u,
    "proxy advertises the port of its bound loopback listener"
  )
  assertProxySource(
    /proxyReady\s*=\s*true/u,
    "proxy becomes ready only after its actual loopback address is verified"
  )
  assertProxySource(
    /isLoopbackAddress\(address\.address\)/u,
    "proxy verifies the bound address is loopback"
  )
  assertProxySource(
    /const address = server\.address\(\)[\s\S]*?if\s*\(!address\s*\|\|\s*typeof address === ["\x27]string["\x27]\s*\|\|\s*!isLoopbackAddress\(address\.address\)\)[\s\S]*?proxyOrigin\.port = String\(\(address as AddressInfo\)\.port\)[\s\S]*?proxyReady = true/u,
    "proxy exposes its origin only after verifying the loopback bind"
  )
  assertProxySource(
    /request\.method\s*!==\s*["\x27]GET["\x27]\s*&&\s*request\.method\s*!==\s*["\x27]HEAD["\x27]/u,
    "proxy rejects unsafe request methods"
  )
  assertProxySource(/Allow:\s*["\x27]GET, HEAD["\x27]/u, "proxy declares its safe methods")
  assert.match(
    spec,
    /finally\s*\{\s*try\s*\{[\s\S]*?\}\s*finally\s*\{\s*await updateProxy\.close\(\)\s*\}\s*\}/u
  )
  assertProxySource(
    /upstreamTarget\.origin !== upstreamOrigin\.origin/u,
    "proxy rejects any target outside the signed upstream origin"
  )
  assertProxySource(
    /request\.method\s*===\s*["\x27]GET["\x27]\s*&&\s*upstreamTarget\.pathname\s*===\s*["\x27]\/sw\.js["\x27]/u,
    "only GET /sw.js receives the worker transform"
  )
  assertProxySource(
    /response\.on\(["\x27]close["\x27],\s*\(\)\s*=>\s*\{\s*if\s*\(!response\.writableEnded\)\s*upstreamRequest\.destroy\(\)/u,
    "closed browser responses cancel stalled upstream requests"
  )
  assertProxySource(
    /if\s*\(response\.destroyed\)\s*return/u,
    "upstream errors do not write to destroyed clients"
  )
  assertProxySource(/MAX_WORKER_SCRIPT_BYTES/u, "worker transformation remains size bounded")
  assert.match(spec, /url\.pathname !== appBundlePath/u)
  assert.match(spec, /pwa-build-marker/u)
  assert.match(spec, /controllerchange/u)
  assert.match(spec, /await activeRegistration\.update\(\)/u)
  assert.match(spec, /setOffline\(true\)[\s\S]*?setOffline\(false\)[\s\S]*?setOffline\(true\)/u)
  assert.match(spec, /oldBundleCacheKeys[\s\S]*?not\.toContain/u)
  assert.match(spec, /newBundleCacheEntries[\s\S]*?hasBuildMarker/u)
  assert.match(
    spec,
    /newBundleCacheEntries\.some\([\s\S]*?new URL\(entry\.requestUrl\)\.searchParams\.get\(["']__WB_REVISION__["']\)\s*===\s*updateRevision/u
  )
  assert.doesNotMatch(spec, /routeWebSocket|page\.request|useMockApi/u)

  assert.match(serviceWorkerRegistration, /updateViaCache:\s*["']none["']/u)
  assert.match(serviceWorkerRegistration, /controllerchange[\s\S]*?window\.location\.reload\(\)/u)
  assert.match(serviceWorker, /self\.skipWaiting\(\)/u)
  assert.match(precaching, /cleanupOutdatedCaches\(\)/u)
})

// Exercise the proxy with a transport-only loopback peer. This server exposes no
// application, API, or authentication behavior; all sentinel values are synthetic.
const { createServer } = await import("node:http")
const { EventEmitter } = await import("node:events")
const { startPwaUpdateProxy } = await import("./pwa-update-proxy.ts")

function withinDeadline(promise, message, timeoutMs = 3_000) {
  let timer
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timer = setNodeTimeout(() => reject(new Error(message)), timeoutMs)
    }),
  ]).finally(() => clearNodeTimeout(timer))
}

async function listenOnValidatedLoopbackPort(server) {
  const minPort = 20_000
  const portCount = 25_001
  const firstPort = minPort + Math.floor(Math.random() * portCount)
  for (let attempt = 0; attempt < 64; attempt += 1) {
    const port = minPort + ((firstPort - minPort + attempt) % portCount)
    try {
      await new Promise((resolve, reject) => {
        const onListening = () => {
          server.off("error", onError)
          resolve()
        }
        const onError = (error) => {
          server.off("listening", onListening)
          reject(error)
        }
        server.once("listening", onListening)
        server.once("error", onError)
        server.listen(port, "127.0.0.1")
      })
      return new URL(`http://localhost:${port}`)
    } catch (error) {
      if (error?.code !== "EADDRINUSE" && error?.code !== "EACCES") throw error
    }
  }
  throw new Error("Unable to bind the isolated transport test server")
}

async function closeTransportServer(server) {
  if (!server.listening) return
  await new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()))
    server.closeAllConnections()
  })
}

test(
  "PWA update proxy preserves ordinary transport, rejects unsafe forwarding, and closes stalled upstreams",
  { timeout: 12_000 },
  async () => {
    const originalWorkerSource = "self.__workerRevision = 'source-v1';"
    const transformedWorkerSource = "self.__workerRevision = 'transformed-revision';"
    const forwarded = []
    let markStalledRequestSeen
    let markStalledResponseClosed
    const stalledRequestSeen = new Promise((resolve) => {
      markStalledRequestSeen = resolve
    })
    const stalledResponseClosed = new Promise((resolve) => {
      markStalledResponseClosed = resolve
    })
    const upstream = createServer((request, response) => {
      const record = {
        method: request.method,
        url: request.url,
        cookie: request.headers.cookie,
        origin: request.headers.origin,
        csrf: request.headers["x-csrf-token"],
      }
      forwarded.push(record)
      if (request.url === "/stalled") {
        markStalledRequestSeen()
        response.once("close", markStalledResponseClosed)
        return
      }
      if (request.url === "/sw.js") {
        response.writeHead(200, {
          "content-type": "application/javascript",
          "content-length": Buffer.byteLength(originalWorkerSource, "utf8"),
          etag: '"source-v1"',
          "last-modified": "Sun, 11 Oct 2026 12:00:00 GMT",
          "content-md5": "synthetic-stale-digest",
        })
        response.end(originalWorkerSource)
        return
      }
      response.writeHead(200, {
        "content-type": "text/plain",
        "set-cookie": "transport-probe=synthetic; Path=/; SameSite=Strict",
      })
      response.end("transport-probe")
    })

    let proxy
    let originServer
    try {
      originServer = await listenOnValidatedLoopbackPort(upstream)
      proxy = await startPwaUpdateProxy(new EventEmitter(), originServer.origin)
      assert.equal(new URL(proxy.origin).hostname, "localhost")
      proxy.setWorkerResponseTransform((source) =>
        source.replace(originalWorkerSource, transformedWorkerSource)
      )

      const syntheticHeaders = {
        cookie: "transport-probe=synthetic-request",
        origin: proxy.origin,
        "x-csrf-token": "synthetic-csrf-probe",
      }
      const getResponse = await globalThis.fetch(
        new URL("/transport-probe?probe=1", proxy.origin),
        {
          headers: syntheticHeaders,
        }
      )
      assert.equal(getResponse.status, 200)
      assert.equal(await getResponse.text(), "transport-probe")
      assert.equal(
        getResponse.headers.get("set-cookie"),
        "transport-probe=synthetic; Path=/; SameSite=Strict"
      )
      assert.deepEqual(forwarded[0], {
        method: "GET",
        url: "/transport-probe?probe=1",
        cookie: syntheticHeaders.cookie,
        origin: syntheticHeaders.origin,
        csrf: syntheticHeaders["x-csrf-token"],
      })

      const headResponse = await globalThis.fetch(new URL("/transport-probe", proxy.origin), {
        method: "HEAD",
      })
      assert.equal(headResponse.status, 200)
      assert.equal(await headResponse.text(), "")
      assert.equal(forwarded[1].method, "HEAD")

      assert.notEqual(
        Buffer.byteLength(transformedWorkerSource, "utf8"),
        Buffer.byteLength(originalWorkerSource, "utf8")
      )
      const workerResponse = await globalThis.fetch(new URL("/sw.js", proxy.origin))
      assert.equal(workerResponse.status, 200)
      assert.equal(await workerResponse.text(), transformedWorkerSource)
      assert.equal(
        workerResponse.headers.get("content-length"),
        String(Buffer.byteLength(transformedWorkerSource, "utf8"))
      )
      assert.equal(workerResponse.headers.get("content-encoding"), null)
      for (const staleHeader of ["etag", "last-modified", "content-md5"]) {
        assert.equal(
          workerResponse.headers.get(staleHeader),
          null,
          `${staleHeader} must not describe rewritten bytes`
        )
      }
      assert.equal(forwarded[2].method, "GET")
      assert.equal(forwarded[2].url, "/sw.js")

      const beforeUnsafeMethod = forwarded.length
      const unsafeResponse = await globalThis.fetch(new URL("/transport-probe", proxy.origin), {
        method: "POST",
        body: "synthetic-body-that-must-not-be-forwarded",
      })
      assert.equal(unsafeResponse.status, 405)
      assert.equal(unsafeResponse.headers.get("allow"), "GET, HEAD")
      assert.equal(forwarded.length, beforeUnsafeMethod)

      const stalledFetch = globalThis.fetch(new URL("/stalled", proxy.origin)).then(
        () => false,
        () => true
      )
      await withinDeadline(
        stalledRequestSeen,
        "The loopback upstream did not receive the stalled request"
      )
      await withinDeadline(proxy.close(), "The proxy did not close with a stalled request")
      await withinDeadline(
        stalledResponseClosed,
        "Proxy close did not cancel the stalled upstream response"
      )
      assert.equal(
        await withinDeadline(stalledFetch, "The browser-side request did not close"),
        true
      )
    } finally {
      try {
        if (proxy) await proxy.close()
      } finally {
        await closeTransportServer(upstream)
      }
    }
  }
)
