/* eslint-disable @typescript-eslint/no-explicit-any */
import "vitest"
import "@testing-library/jest-dom/vitest"
import "fake-indexeddb/auto"
import { TextEncoder, TextDecoder } from "node:util"
import { webcrypto } from "node:crypto"
import { afterAll, afterEach, beforeAll, expect, vi } from "vitest"
import { toHaveNoViolations } from "jest-axe"
import { server } from "./tests/mocks/server"
import {
  resetAdminDeadLetterJobs,
  resetTestEvents,
  resetTestMfa,
  resetTestSessions,
  resetTestStories,
  resetTestNews,
} from "./tests/mocks/handlers"
import i18n from "./i18n/config"
import { resetEtagCache } from "./api/client"
import { validateRequestBody, validateResponseBody } from "./tests/contractValidator"

declare module "vitest" {
  export interface Assertion {
    toBeAccessible(): Promise<void>
  }
  export interface AsymmetricMatchersContaining {
    toBeAccessible(): Promise<void>
  }
}

expect.extend(toHaveNoViolations)

if (!process.stdout.columns || process.stdout.columns === 0) {
  process.stdout.columns = 80
}

if (!process.stderr.columns || process.stderr.columns === 0) {
  process.stderr.columns = 80
}

if (!globalThis.TextEncoder) (globalThis as any).TextEncoder = TextEncoder
if (!globalThis.TextDecoder) (globalThis as any).TextDecoder = TextDecoder as any
if (!globalThis.crypto) (globalThis as any).crypto = webcrypto

beforeAll(async () => {
  await i18n.changeLanguage("en")
  if (typeof document !== "undefined") {
    // jsdom env only — guard for node-env tests (Wave 133 SW1 ssrCookie tests use
    // `@vitest-environment node` directive, where `document` is undefined).
    document.documentElement.lang = "en"
  }
  server.listen({ onUnhandledRequest: "warn" })

  // ── Contract validation hook (Phase 3 QA) ─────────────────────────────────
  // Validates every MSW-mocked request + response pair against openapi.json.
  // Set CONTRACT_VALIDATION_DISABLED=1 in your environment to bypass (e.g.
  // while generating new mock handlers before the schema is updated).
  if (process.env["CONTRACT_VALIDATION_DISABLED"] !== "1") {
    server.events.on("response:mocked", ({ request, response }) => {
      try {
        const url = new URL(request.url)
        const path = url.pathname

        // Only validate paths that look like API calls
        if (!path.startsWith("/api/") && !path.startsWith("/auth/")) return

        // Validate response body
        const contentType = response.headers.get("content-type") ?? ""
        if (contentType.includes("application/json")) {
          response
            .clone()
            .json()
            .then((body: unknown) => {
              validateResponseBody({
                path,
                method: request.method,
                statusCode: response.status,
                body,
              })
            })
            .catch((error: unknown) => {
              // Fail the test on contract violation — console.error surfaces
              // the error in Vitest output even from async callbacks.
              console.error("[ContractValidator]", error)
              throw error
            })
        }

        // Validate request body for mutation methods
        if (["POST", "PUT", "PATCH"].includes(request.method.toUpperCase())) {
          const requestContentType = request.headers.get("content-type") ?? ""
          if (requestContentType.includes("application/json")) {
            request
              .clone()
              .json()
              .then((body: unknown) => {
                validateRequestBody({ path, method: request.method, body })
              })
              .catch((error: unknown) => {
                console.error("[ContractValidator]", error)
                throw error
              })
          }
        }
      } catch (error) {
        // Synchronous errors from URL parsing etc. — propagate to test output
        console.error("[ContractValidator] Unexpected error:", error)
      }
    })
  }
})

afterEach(() => {
  server.resetHandlers()
  resetTestSessions()
  resetTestEvents()
  resetTestStories()
  resetTestNews()
  resetTestMfa()
  resetAdminDeadLetterJobs()
  resetEtagCache()
})

afterAll(() => server.close())

// Wave 133 SW1 — guard window-touching polyfills with typeof check so node-env
// tests (e.g. ssrCookie.test.ts via `@vitest-environment node`) don't crash on
// `window is not defined` when the setupFile loads. jsdom-env tests behave
// identically (typeof window === "object") and continue to receive the polyfills.
if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })

  if (!("IntersectionObserver" in window)) {
    Object.defineProperty(window, "IntersectionObserver", {
      writable: true,
      value: class {
        constructor() {}
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    })
  }

  // ResizeObserver polyfill — jsdom lacks it, StoryList (scroll edge-fade detection) uses it
  // (Wave 113 SW6 polish — fixes 3 StoryList.test.tsx "ResizeObserver is not defined" errors).
  if (!("ResizeObserver" in window)) {
    Object.defineProperty(window, "ResizeObserver", {
      writable: true,
      value: class {
        constructor() {}
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    })
  }
}

// PointerEvent capture polyfill — jsdom doesn't implement Element.hasPointerCapture /
// setPointerCapture / releasePointerCapture. StoryList drag-to-scroll, StoryViewer swipe,
// and various Radix UI triggers call them (Wave 113 SW6 polish).
if (typeof Element !== "undefined") {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => {}
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => {}
  }
  // jsdom lacks scrollIntoView too
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
}

if (typeof window !== "undefined") {
  window.scrollTo = vi.fn()
}

vi.mock("qrcode.react", () => ({
  QRCodeSVG: () => null,
}))

vi.mock("@/push/subscribe", () => ({
  recoverPushConsentFromBrowser: vi.fn(async () => false),
  hasPushConsent: vi.fn(() => false),
  softSyncPushSubscription: vi.fn(async () => null),
  setPushConsent: vi.fn(),
  isPushSupported: vi.fn(() => false),
}))

vi.mock("@/utils/cryptoWorker", () => ({
  cryptoWorker: {
    pbkdf2: vi.fn().mockResolvedValue("mock_pbkdf2"),
    scrypt: vi.fn().mockResolvedValue(new Uint8Array([1, 2, 3])),
    hmacSha256: vi.fn().mockImplementation(async ({ json, key }: { json: string; key: string }) => {
      const crypto = await import("node:crypto")
      return crypto.createHmac("sha256", key).update(json).digest("base64")
    }),
  },
}))

import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { initSync as initSanitizer } from "wasm-sanitizer"

try {
  const dirname = path.dirname(fileURLToPath(import.meta.url))
  const sanitizerWasmPath = path.resolve(dirname, "../wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm")
  const sanitizerWasmBuffer = fs.readFileSync(sanitizerWasmPath)
  initSanitizer({ module: sanitizerWasmBuffer })
} catch (e) {
  console.error("Failed to initialize WASM modules for tests:", e)
}

if (typeof HTMLCanvasElement !== "undefined") {
  HTMLCanvasElement.prototype.getContext = vi.fn(
    () =>
      ({
        fillRect: vi.fn(),
        clearRect: vi.fn(),
        getImageData: vi.fn(() => ({ data: new Uint8ClampedArray() })),
        putImageData: vi.fn(),
        createImageData: vi.fn(),
        setTransform: vi.fn(),
        drawImage: vi.fn(),
        save: vi.fn(),
        restore: vi.fn(),
        beginPath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        stroke: vi.fn(),
        fill: vi.fn(),
        arc: vi.fn(),
        closePath: vi.fn(),
      }) as any
  )
}

const IGNORED_WARNINGS = [
  "Warning:",
  "The current testing environment is not configured to support act(...)",
  "You are trying to animate backgroundColor from",
  "An update to",
]

const originalConsoleError = console.error
const originalConsoleWarn = console.warn
console.error = (...args: unknown[]) => {
  const firstArg = args[0]
  if (typeof firstArg === "string" && IGNORED_WARNINGS.some((w) => firstArg.includes(w))) return
  originalConsoleError(...args)
}
console.warn = (...args: unknown[]) => {
  const firstArg = args[0]
  if (typeof firstArg === "string" && IGNORED_WARNINGS.some((w) => firstArg.includes(w))) return
  originalConsoleWarn(...args)
}
