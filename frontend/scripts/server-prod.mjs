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

import { createReadStream, statSync } from "node:fs"
import { createServer } from "node:http"
import { Readable } from "node:stream"
import path from "node:path"
import process from "node:process"
import { pathToFileURL } from "node:url"

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

const handlerModule = await import(handlerEntryUrl)
const handler = handlerModule.default ?? handlerModule
if (typeof handler?.fetch !== "function") {
  console.error(
    `server-prod: imported module from ${handlerEntryPath} does not expose .fetch handler. ` +
      `Run 'npm run build' first to produce dist/server/server.js.`,
  )
  process.exit(1)
}

// Wave 131 SW7 — minimal content-type map. Covers what `dist/client/`
// actually contains; unknown extensions fall through to
// `application/octet-stream` (browsers handle that gracefully for the
// few stragglers like .map source-map files).
const CONTENT_TYPES = Object.freeze({
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".ttf": "font/ttf",
  ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
})

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
    console.error(`server-prod: read error for ${filePath}:`, err)
    if (!res.writableEnded) res.end()
  })
  stream.pipe(res)
  return true
}

function buildWebRequest(req) {
  const protocol = req.headers["x-forwarded-proto"] ?? "http"
  const host = req.headers.host ?? `${HOST}:${PORT}`
  const url = `${protocol}://${host}${req.url}`
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

async function pipeWebResponse(webResponse, res) {
  res.statusCode = webResponse.status
  res.statusMessage = webResponse.statusText
  for (const [name, value] of webResponse.headers) {
    res.setHeader(name, value)
  }
  if (!webResponse.body) {
    res.end()
    return
  }
  const nodeStream = Readable.fromWeb(webResponse.body)
  nodeStream.on("error", (err) => {
    console.error("server-prod: response stream error:", err)
    if (!res.writableEnded) res.end()
  })
  nodeStream.pipe(res)
}

const server = createServer(async (req, res) => {
  const start = Date.now()
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
        console.log(`${req.method} ${req.url} ${res.statusCode} ${ms}ms (static)`)
        return
      }
    }
    const request = buildWebRequest(req)
    const response = await handler.fetch(request)
    await pipeWebResponse(response, res)
    const ms = Date.now() - start
    console.log(`${req.method} ${req.url} ${res.statusCode} ${ms}ms`)
  } catch (err) {
    console.error("server-prod: handler error:", err)
    if (!res.headersSent) {
      res.statusCode = 500
      res.setHeader("content-type", "text/plain; charset=utf-8")
    }
    if (!res.writableEnded) res.end("Internal Server Error")
  }
})

server.listen(PORT, HOST, () => {
  console.log(`server-prod: listening on http://${HOST}:${PORT} (Node ${process.version})`)
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
