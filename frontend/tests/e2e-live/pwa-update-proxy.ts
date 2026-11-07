import { createServer, request as httpRequest, type OutgoingHttpHeaders } from "node:http"
import type { BrowserContext } from "@playwright/test"
import { isIP, type AddressInfo } from "node:net"
import { brotliDecompressSync, gunzipSync, inflateSync } from "node:zlib"

const LIVE_STAND_MIN_PORT = 20_000
const LIVE_STAND_MAX_PORT = 45_000
const MAX_WORKER_SCRIPT_BYTES = 2 * 1024 * 1024
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
])

type WorkerResponseTransform = (source: string) => string

export type PwaUpdateProxy = {
  origin: string
  setWorkerResponseTransform(transform: WorkerResponseTransform): void
  close(): Promise<void>
}

function validateSignedLiveBaseUrl(value: string): URL {
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    throw new Error("PWA update proxy requires the verified LIVE_BASE_URL")
  }

  if (
    parsed.protocol !== "http:" ||
    parsed.hostname !== "localhost" ||
    !parsed.port ||
    Number(parsed.port) < LIVE_STAND_MIN_PORT ||
    Number(parsed.port) > LIVE_STAND_MAX_PORT ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.pathname !== "/" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new Error("PWA update proxy requires the verified live-stand loopback origin")
  }
  return parsed
}

function isLoopbackAddress(address: string): boolean {
  const version = isIP(address)
  return (
    (version === 4 && address === "127.0.0.1") ||
    (version === 6 && (address === "::1" || address.toLowerCase() === "::ffff:127.0.0.1"))
  )
}

function forwardedRequestHeaders(
  headers: import("node:http").IncomingHttpHeaders
): OutgoingHttpHeaders {
  const forwarded: OutgoingHttpHeaders = {}
  for (const [name, value] of Object.entries(headers)) {
    const normalized = name.toLowerCase()
    if (value === undefined || normalized === "host" || HOP_BY_HOP_HEADERS.has(normalized)) {
      continue
    }
    forwarded[name] = value
  }
  return forwarded
}

function forwardedResponseHeaders(
  headers: import("node:http").IncomingHttpHeaders,
  upstreamOrigin: URL,
  proxyOrigin: URL,
  rewriteBody: boolean
): OutgoingHttpHeaders {
  const forwarded: OutgoingHttpHeaders = {}
  for (const [name, value] of Object.entries(headers)) {
    const normalized = name.toLowerCase()
    if (
      value === undefined ||
      HOP_BY_HOP_HEADERS.has(normalized) ||
      (rewriteBody &&
        [
          "content-length",
          "content-encoding",
          "transfer-encoding",
          "etag",
          "last-modified",
          "content-md5",
        ].includes(normalized))
    ) {
      continue
    }
    if (normalized === "location" && typeof value === "string") {
      try {
        const location = new URL(value, upstreamOrigin)
        if (location.origin === upstreamOrigin.origin) {
          forwarded[name] = new URL(
            `${location.pathname}${location.search}${location.hash}`,
            proxyOrigin
          ).toString()
          continue
        }
      } catch {
        // Preserve a relative or otherwise non-URL Location value unchanged.
      }
    }
    forwarded[name] = value
  }
  return forwarded
}

function decodeWorkerBody(body: Buffer, encoding: string | undefined): Buffer {
  switch (encoding?.toLowerCase()) {
    case undefined:
    case "identity":
      return body
    case "gzip":
      return gunzipSync(body)
    case "deflate":
      return inflateSync(body)
    case "br":
      return brotliDecompressSync(body)
    default:
      throw new Error("Unsupported worker response encoding")
  }
}

export async function startPwaUpdateProxy(
  context: BrowserContext,
  liveBaseUrl: string
): Promise<PwaUpdateProxy> {
  const upstreamOrigin = validateSignedLiveBaseUrl(liveBaseUrl)
  const upstreamPort = Number(upstreamOrigin.port)
  if (
    !Number.isSafeInteger(upstreamPort) ||
    upstreamPort < LIVE_STAND_MIN_PORT ||
    upstreamPort > LIVE_STAND_MAX_PORT
  ) {
    throw new Error("PWA update proxy requires a verified live-stand port")
  }
  const proxyOrigin = new URL("http://localhost:0")
  let proxyReady = false
  let workerTransform: WorkerResponseTransform | undefined
  let closePromise: Promise<void> | undefined

  const server = createServer((request, response) => {
    if (request.method !== "GET" && request.method !== "HEAD") {
      response
        .writeHead(405, {
          Allow: "GET, HEAD",
          "Cache-Control": "no-store",
        })
        .end()
      request.resume()
      return
    }
    if (!proxyReady) {
      response.writeHead(503, { "Cache-Control": "no-store" }).end()
      return
    }
    let localTarget: URL
    try {
      localTarget = new URL(request.url ?? "/", proxyOrigin)
    } catch {
      response.writeHead(400, { "Cache-Control": "no-store" }).end()
      return
    }
    if (localTarget.origin !== proxyOrigin.origin) {
      response.writeHead(403, { "Cache-Control": "no-store" }).end()
      return
    }

    const upstreamTarget = new URL(`${localTarget.pathname}${localTarget.search}`, upstreamOrigin)
    if (upstreamTarget.origin !== upstreamOrigin.origin) {
      response.writeHead(403, { "Cache-Control": "no-store" }).end()
      return
    }

    const rewriteWorker =
      request.method === "GET" &&
      upstreamTarget.pathname === "/sw.js" &&
      workerTransform !== undefined
    const requestHeaders = forwardedRequestHeaders(request.headers)
    if (rewriteWorker) {
      requestHeaders["accept-encoding"] = "identity"
      requestHeaders["cache-control"] = "no-cache"
      delete requestHeaders["if-none-match"]
      delete requestHeaders["if-modified-since"]
    }

    // Keep the socket destination literal and loopback-only. The inbound URL
    // contributes a parsed request path, never a destination authority.
    requestHeaders.host = proxyOrigin.host
    const upstreamRequest = httpRequest(
      "http://127.0.0.1",
      {
        hostname: "127.0.0.1",
        port: upstreamPort,
        method: request.method,
        path: `${upstreamTarget.pathname}${upstreamTarget.search}`,
        headers: requestHeaders,
      },
      (upstreamResponse) => {
        const statusCode = upstreamResponse.statusCode ?? 502
        const headers = forwardedResponseHeaders(
          upstreamResponse.headers,
          upstreamOrigin,
          proxyOrigin,
          rewriteWorker && statusCode === 200
        )

        if (!rewriteWorker || statusCode !== 200) {
          response.writeHead(statusCode, upstreamResponse.statusMessage, headers)
          upstreamResponse.pipe(response)
          return
        }

        const chunks: Buffer[] = []
        let bodyBytes = 0
        let finished = false
        const failClosed = () => {
          if (finished) return
          finished = true
          upstreamResponse.destroy()
          if (!response.headersSent && !response.destroyed) {
            response.writeHead(502, { "Cache-Control": "no-store" }).end()
          } else if (!response.destroyed) {
            response.destroy()
          }
        }
        upstreamResponse.on("data", (chunk: Buffer | string) => {
          if (finished) return
          const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
          bodyBytes += bytes.byteLength
          if (bodyBytes > MAX_WORKER_SCRIPT_BYTES) {
            failClosed()
            return
          }
          chunks.push(bytes)
        })
        upstreamResponse.on("error", failClosed)
        upstreamResponse.on("end", () => {
          if (finished) return
          finished = true
          try {
            const decodedBody = decodeWorkerBody(
              Buffer.concat(chunks),
              upstreamResponse.headers["content-encoding"]
            )
            if (decodedBody.byteLength > MAX_WORKER_SCRIPT_BYTES) {
              response.writeHead(502, { "Cache-Control": "no-store" }).end()
              return
            }
            const source = decodedBody.toString("utf8")
            const transformed = workerTransform?.(source)
            if (typeof transformed !== "string" || transformed === source) {
              response.writeHead(502, { "Cache-Control": "no-store" }).end()
              return
            }
            const body = Buffer.from(transformed, "utf8")
            headers["content-length"] = body.byteLength
            response.writeHead(statusCode, upstreamResponse.statusMessage, headers)
            response.end(body)
          } catch {
            response.writeHead(502, { "Cache-Control": "no-store" }).end()
          }
        })
      }
    )
    upstreamRequest.on("error", () => {
      if (response.destroyed) return
      if (response.headersSent) {
        response.destroy()
        return
      }
      response.writeHead(502, { "Cache-Control": "no-store" }).end()
    })
    request.on("aborted", () => upstreamRequest.destroy())
    response.on("close", () => {
      if (!response.writableEnded) upstreamRequest.destroy()
    })
    request.pipe(upstreamRequest)
  })

  server.on("connect", (_request, socket) => {
    socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
  })

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject)
    // Bind IPv4 loopback explicitly; keep localhost as the browser-facing origin host.
    server.listen(0, "127.0.0.1", () => {
      server.off("error", reject)
      resolve()
    })
  })

  const address = server.address()
  if (!address || typeof address === "string" || !isLoopbackAddress(address.address)) {
    await new Promise<void>((resolve) => server.close(() => resolve()))
    throw new Error("PWA update proxy failed its loopback bind check")
  }

  proxyOrigin.port = String((address as AddressInfo).port)
  proxyReady = true

  const close = (): Promise<void> => {
    if (!closePromise) {
      closePromise = new Promise((resolve, reject) => {
        server.close((error) => (error ? reject(error) : resolve()))
        server.closeAllConnections()
      })
    }
    return closePromise
  }
  context.once("close", () => {
    void close().catch(() => undefined)
  })

  return {
    origin: proxyOrigin.origin,
    setWorkerResponseTransform(transform) {
      if (workerTransform) throw new Error("PWA worker update transform is already configured")
      workerTransform = transform
    },
    close,
  }
}
