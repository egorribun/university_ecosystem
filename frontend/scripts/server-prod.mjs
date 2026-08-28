// Wave 131 Phase 4 — production Node SSR wrapper.
//
// This script is the runtime that the new frontend.Dockerfile (W131 SW3)
// executes via `node ./scripts/server-prod.mjs`. It binds the tanstackStart
// server entry handler exported by `dist/server/server.js` (built by
// vite + the tanstackStart plugin in spa mode) to a standard Node
// http.createServer, listening on `process.env.PORT ?? 3000`.
//
// Why a custom wrapper instead of the canonical `nitro()` plugin:
// see the comment block at the top of `vite.config.mts`. Adopting
// nitro() restructures outputs from `dist/...` → `.output/...` which
// cascades to vite-plugin-pwa's injectManifest glob (manifest goes
// empty), wave127-build-x3.sh detection, LHCI staticDistDir, and
// frontend.Dockerfile COPY paths. The wrapper preserves all those
// pre-W131 paths.
//
// What this wrapper does:
//   1. Imports `dist/server/server.js`'s default export, which is a
//      TanStack Start `ServerEntry` shape: `{ fetch(request: Request)
//      => Response | Promise<Response> }` (per W126 SW3 server.ts).
//   2. Binds it via Node's built-in `http.createServer` + a Web Standards
//      Request → IncomingMessage adapter. Node 22+ has `Request` /
//      `Response` / `ReadableStream` as globals; the adapter just
//      bridges Node's IncomingMessage <-> Web Request and Web Response
//      <-> ServerResponse.
//   3. Listens on `process.env.PORT ?? 3000` on `0.0.0.0` (bind-all so
//      Docker / k8s probes can reach it).
//   4. Adds graceful SIGTERM shutdown — closes the http server with a
//      30s drain window so in-flight SSR requests complete before
//      Node exits. Matches the k8s `terminationGracePeriodSeconds: 30`
//      in deployment.yaml.
//
// Health check: see SW2. The handler at `/healthz` is added inside
// `frontend/src/server.ts` (or as a route file) and short-circuits
// before any auth / theme / lang extraction so it stays fast.
//
// Logging: simple stdout per-request log line. Production-grade
// observability (Sentry server-side, OTEL traces) can be layered on
// in a future polish wave; out of W131 Phase 4 scope.

import { createReadStream, readFileSync, statSync } from "node:fs"
import { createServer } from "node:http"
import { Readable } from "node:stream"
import path from "node:path"
import process from "node:process"
import { pathToFileURL } from "node:url"
// Wave 175 SW8 — CONTENT_TYPES extracted to a side-effect-free module
// (`scripts/contentTypes.mjs`) so regression tests can import the map
// without triggering this script's top-level createServer + listen.
import { CONTENT_TYPES } from "./contentTypes.mjs"
import { createNotFoundResponse, shouldServeNotFoundDocument } from "./not-found-response.mjs"
import { pipeResponseBody } from "./server-response-stream.mjs"
import { warmSsrRuntime } from "./server-readiness.mjs"
import { sanitizeRequestTarget } from "./server-request-log.mjs"

const PORT = Number(process.env.PORT ?? 3000)
const HOST = process.env.HOST ?? "0.0.0.0"

// `dist/server/server.js` is emitted by `npm run build` in CWD. The
// wrapper expects to be run from the frontend/ directory (Dockerfile
// WORKDIR /app, server-prod.mjs at /app/scripts/server-prod.mjs, dist
// at /app/dist).
const cwd = process.cwd()
const handlerEntryPath = path.resolve(cwd, "dist", "server", "server.js")
const handlerEntryUrl = pathToFileURL(handlerEntryPath).href
// Wave 131 SW7 — static file root. tanstackStart's server-entry handler
// only renders routes; static assets (`/assets/*`, `/favicon.ico`, `/sw.js`,
// `/manifest.webmanifest`, `/icon-*.png`, `/maskable-icon-*.png`,
// `/offline.html`, `/static-shell-i18n.js`, etc.) live in `dist/client/`
// and are served by vite preview's built-in static server during dev.
// Production needs the wrapper to handle that explicitly.
const staticRoot = path.resolve(cwd, "dist", "client")
const notFoundDocumentPath = path.join(staticRoot, "not-found.html")
const DEFAULT_REQUEST_HOST = `${HOST}:${PORT}`

// The 404 page is intentionally read once at startup: it is a small immutable
// document, and doing so keeps unknown navigations off the synchronous file
// system path while still failing closed when a build omitted the artifact.
let notFoundDocument = null
try {
  const candidate = readFileSync(notFoundDocumentPath, "utf8")
  if (candidate.trim().length > 0) notFoundDocument = candidate
} catch {
  // A missing fallback should not prevent health probes from starting. The
  // SSR handler's original 404 response remains the safe fallback in that
  // case, and the build/LHCI route preparation fails when the artifact is
  // required.
}

const handlerModule = await import(handlerEntryUrl)
const handler = handlerModule.default ?? handlerModule
if (typeof handler?.fetch !== "function") {
  console.error(
    `server-prod: imported module from ${handlerEntryPath} does not expose .fetch handler. ` +
      `Run 'npm run build' first to produce dist/server/server.js.`
  )
  process.exit(1)
}

// Wave 131 SW7 — minimal content-type map. Covers what `dist/client/`
// actually contains; unknown extensions fall through to
// `application/octet-stream` (browsers handle that gracefully for the
// few stragglers like .map source-map files).
// Wave 173 SW1 — `.wasm: application/wasm` invariant lives in
// `./contentTypes.mjs` (imported above). Wave 175 SW8 extracted the map
// to a side-effect-free module so regression tests can verify the
// invariant without triggering server startup.
//
// Closes W131 SW7 omission that lay dormant ≥17 waves because /messenger
// (chat — the only feature exercising crypto.worker) was Phase 5 punted.

function serveStatic(req, res, urlPath) {
  // Security: reject paths that escape staticRoot via `..`. path.join +
  // resolve would silently accept `/../etc/passwd`-style traversal under
  // some cwd setups, so we do an explicit prefix check after resolve.
  const requested = path.normalize(decodeURIComponent(urlPath)).replace(/^[/\\]+/, "")
  if (requested.includes("..")) return false
  const filePath = path.resolve(staticRoot, requested)
  if (!filePath.startsWith(staticRoot)) return false
  let stat
  try {
    stat = statSync(filePath)
  } catch {
    return false
  }
  if (!stat.isFile()) return false
  const ext = path.extname(filePath).toLowerCase()
  const contentType = CONTENT_TYPES[ext] ?? "application/octet-stream"
  res.statusCode = 200
  res.setHeader("content-type", contentType)
  res.setHeader("content-length", stat.size)
  // Long-cache hashed assets (everything in /assets/<name>-<hash>.ext is
  // immutable per Vite's hashing convention). Other static files in the
  // root (sw.js, manifest, fallbacks, etc.) get short cache + revalidation.
  if (urlPath.startsWith("/assets/") || urlPath.startsWith("/fonts/")) {
    res.setHeader("cache-control", "public, max-age=31536000, immutable")
  } else if (urlPath === "/sw.js" || urlPath === "/registerSW.js") {
    // Service worker MUST NOT be cached — browsers re-check on every nav.
    res.setHeader("cache-control", "no-store, no-cache, must-revalidate, max-age=0")
    res.setHeader("service-worker-allowed", "/")
  } else {
    res.setHeader("cache-control", "no-cache")
  }
  // HEAD requests get headers only — drain stream after body is built.
  if (req.method === "HEAD") {
    res.end()
    return true
  }
  const stream = createReadStream(filePath)
  stream.on("error", (err) => {
    console.error("server-prod: read error for static file", filePath, err)
    if (!res.writableEnded) res.end()
  })
  stream.pipe(res)
  return true
}

function buildWebRequest(req) {
  const forwardedProto = Array.isArray(req.headers["x-forwarded-proto"])
    ? req.headers["x-forwarded-proto"][0]
    : req.headers["x-forwarded-proto"]
  const protocol = forwardedProto === "https" ? "https:" : "http:"
  const headerHost = Array.isArray(req.headers.host) ? req.headers.host[0] : req.headers.host
  const url = new URL(req.url ?? "/", "http://localhost")
  url.protocol = protocol
  try {
    url.host = headerHost || DEFAULT_REQUEST_HOST
  } catch {
    url.host = DEFAULT_REQUEST_HOST
  }
  const method = req.method ?? "GET"
  const headers = new Headers()
  for (const [name, value] of Object.entries(req.headers)) {
    if (Array.isArray(value)) {
      for (const v of value) headers.append(name, v)
    } else if (value !== undefined) {
      headers.set(name, String(value))
    }
  }
  // Methods other than GET / HEAD may carry a body; stream it through.
  let body
  if (method !== "GET" && method !== "HEAD") {
    body = Readable.toWeb(req)
  }
  // `duplex: "half"` is required by undici when the request has a body
  // even via Web ReadableStream — Node 22+ behaviour.
  const init = { method, headers }
  if (body) {
    init.body = body
    init.duplex = "half"
  }
  return new Request(url, init)
}

async function pipeWebResponse(webResponse, res, extraHeaders) {
  res.statusCode = webResponse.status
  res.statusMessage = webResponse.statusText
  for (const [name, value] of webResponse.headers) {
    res.setHeader(name, value)
  }
  // Caller-provided headers (for example Server-Timing for SSR observability).
  // Append AFTER copying upstream
  // headers so we don't accidentally clobber a set-cookie or content-type
  // that the response already carries.
  if (extraHeaders) {
    for (const [name, value] of Object.entries(extraHeaders)) {
      res.appendHeader(name, value)
    }
  }
  if (!webResponse.body) {
    res.end()
    return
  }
  await pipeResponseBody(webResponse, res)
}

function protectHtmlFromSharedCaching(webResponse) {
  const contentType = webResponse.headers.get("content-type") ?? ""
  if (
    !contentType.toLowerCase().includes("text/html") ||
    webResponse.headers.has("cache-control")
  ) {
    return webResponse
  }

  // SSR shells can vary by cookies (theme, locale, and authentication). A
  // missing cache directive must fail closed: intermediaries must not turn an
  // HTML response into a shared cache entry by default.
  const headers = new Headers(webResponse.headers)
  headers.set("cache-control", "no-store, private, max-age=0")
  return new Response(webResponse.body, {
    status: webResponse.status,
    statusText: webResponse.statusText,
    headers,
  })
}

const server = createServer(async (req, res) => {
  const start = Date.now()
  const logTarget = sanitizeRequestTarget(req.url)
  try {
    // Wave 131 SW7 — static-first request flow:
    //   1. Try to serve from `dist/client/` (assets, sw.js, manifest, etc.).
    //   2. If no static match, delegate to tanstackStart server entry's
    //      `handler.fetch` which handles route SSR + auth + healthz.
    // Static check is GET/HEAD only — POST/PUT/PATCH/DELETE always go to
    // the handler (no static endpoints accept mutations).
    const urlPath = (req.url ?? "/").split("?")[0]
    if ((req.method === "GET" || req.method === "HEAD") && urlPath !== "/") {
      if (serveStatic(req, res, urlPath)) {
        const ms = Date.now() - start
        console.log(`${req.method} ${logTarget} ${res.statusCode} ${ms}ms (static)`)
        return
      }
    }
    const request = buildWebRequest(req)
    // Server-Timing observability for SSR latency and edge diagnostics.
    // `performance.now()` gives sub-ms precision; the duration measured here
    // is the SSR-layer round-trip (router construction + route render +
    // any backend fetches reached during the loader chain).
    //
    // The header lets operators measure the SSR layer independently from the
    // edge proxy and browser timings.
    //
    // Skip for /healthz so the W131 SW2 fast-path response stays clean —
    // probes shouldn't be tagged as SSR-pool traffic.
    const ssrStart = performance.now()
    let response = await handler.fetch(request)
    if (
      response.status === 404 &&
      notFoundDocument &&
      shouldServeNotFoundDocument({
        method: req.method,
        urlPath,
        accept: req.headers.accept,
      })
    ) {
      response = createNotFoundResponse(notFoundDocument, { method: req.method })
    }
    response = protectHtmlFromSharedCaching(response)
    const ssrDur = performance.now() - ssrStart
    // `urlPath` is already declared at the top of this try-block (used for
    // the static-first check). Reuse it for the /healthz Server-Timing
    // skip so we don't re-parse the URL.
    const extraHeaders =
      urlPath === "/healthz"
        ? undefined
        : { "Server-Timing": `ssr;dur=${ssrDur.toFixed(2)};desc="ssr-render"` }
    await pipeWebResponse(response, res, extraHeaders)
    const ms = Date.now() - start
    console.log(`${req.method} ${logTarget} ${res.statusCode} ${ms}ms`)
  } catch (err) {
    console.error("server-prod: handler error:", err)
    if (!res.headersSent) {
      res.statusCode = 500
      res.setHeader("content-type", "text/plain; charset=utf-8")
    }
    if (!res.writableEnded) res.end("Internal Server Error")
  }
})

async function startServer() {
  const warmupStarted = Date.now()
  await warmSsrRuntime(handler, { url: `http://${DEFAULT_REQUEST_HOST}/login` })
  console.log(`server-prod: SSR readiness warmup completed in ${Date.now() - warmupStarted}ms`)
  server.listen(PORT, HOST, () => {
    console.log(`server-prod: listening on http://${HOST}:${PORT} (Node ${process.version})`)
  })
}

void startServer().catch((error) => {
  console.error("server-prod: readiness warmup failed:", error)
  // Fail closed immediately. The SSR bundle may own timers or open handles,
  // so setting exitCode alone can leave an alive container that never binds
  // its health port and never terminates.
  process.exit(1)
})

const shutdown = (signal) => {
  console.log(`server-prod: ${signal} received, draining…`)
  // Stop accepting new connections; existing requests complete naturally.
  server.close(() => {
    console.log("server-prod: shutdown complete")
    process.exit(0)
  })
  // Hard-exit after 30s — matches k8s terminationGracePeriodSeconds.
  setTimeout(() => {
    console.error("server-prod: drain timeout, forcing exit")
    process.exit(1)
  }, 30_000).unref()
}
process.on("SIGTERM", () => shutdown("SIGTERM"))
process.on("SIGINT", () => shutdown("SIGINT"))
