/// <reference types="vitest" />
import "@testing-library/jest-dom"
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

expect.extend(toHaveNoViolations)

if (!process.stdout.columns || process.stdout.columns === 0) {
  process.stdout.columns = 80
}

if (!process.stderr.columns || process.stderr.columns === 0) {
  process.stderr.columns = 80
}

beforeAll(async () => {
  await i18n.changeLanguage("en")
  document.documentElement.lang = "en"
  server.listen({ onUnhandledRequest: "error" })
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
if (!(globalThis as any).TextEncoder) (globalThis as any).TextEncoder = TextEncoder
if (!(globalThis as any).TextDecoder) (globalThis as any).TextDecoder = TextDecoder as any
if (!(globalThis as any).crypto) (globalThis as any).crypto = webcrypto
if (!("matchMedia" in window)) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}
type ScrollToFunction = (options?: ScrollToOptions | number, y?: number) => void
const windowWithScroll = window as typeof window & { scrollTo?: ScrollToFunction }
if (!windowWithScroll.scrollTo) {
  windowWithScroll.scrollTo = () => undefined
}
vi.mock("qrcode.react", () => ({
  QRCodeSVG: () => null,
}))
