/* eslint-disable @typescript-eslint/no-explicit-any */
import "vitest"
import "@testing-library/jest-dom/vitest"
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
  document.documentElement.lang = "en"
  server.listen({ onUnhandledRequest: "warn" })
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

vi.mock("qrcode.react", () => ({
  QRCodeSVG: () => null,
}))

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

const IGNORED_WARNINGS = ["Warning:"]

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
// eslint-disable-next-line no-console
console.log = (..._args: unknown[]) => {}
