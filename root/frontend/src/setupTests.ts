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
} from "./tests/mocks/handlers"
import i18n from "./i18n/config"
import { resetEtagCache } from "./api/client"

expect.extend(toHaveNoViolations)

beforeAll(async () => {
  await i18n.changeLanguage("en")
  document.documentElement.lang = "en"
  server.listen({ onUnhandledRequest: "error" })
})
afterEach(() => {
  server.resetHandlers()
  resetTestSessions()
  resetTestEvents()
  resetTestMfa()
  resetAdminDeadLetterJobs()
  resetEtagCache()
})
afterAll(() => server.close())
if (!(globalThis as any).TextEncoder) (globalThis as any).TextEncoder = TextEncoder
if (!(globalThis as any).TextDecoder) (globalThis as any).TextDecoder = TextDecoder as any
if (!(globalThis as any).crypto) (globalThis as any).crypto = webcrypto
if (!("ResizeObserver" in window)) {
  class ResizeObserver {
    callback: ResizeObserverCallback
    observed = new Set<Element>()
    constructor(callback: ResizeObserverCallback) {
      this.callback = callback
    }
    observe(target: Element) {
      this.observed.add(target)
      const el = target as HTMLElement
      const width = typeof el.clientWidth === "number" && el.clientWidth > 0 ? el.clientWidth : 600
      const height =
        typeof el.clientHeight === "number" && el.clientHeight > 0 ? el.clientHeight : 600
      const entry = {
        target,
        contentRect: {
          width,
          height,
          top: 0,
          left: 0,
          bottom: height,
          right: width,
          x: 0,
          y: 0,
          toJSON: () => ({ width, height }),
        },
      } as ResizeObserverEntry
      this.callback([entry], this)
    }
    unobserve(target: Element) {
      this.observed.delete(target)
    }
    disconnect() {
      this.observed.clear()
    }
  }
  ;(window as any).ResizeObserver = ResizeObserver
  ;(globalThis as any).ResizeObserver = ResizeObserver
}
if (!(HTMLElement.prototype as any).scrollTo) {
  ;(HTMLElement.prototype as any).scrollTo = function scrollTo(
    options?: number | ScrollToOptions,
    y?: number
  ) {
    if (typeof options === "number") {
      this.scrollTop = options
      if (typeof y === "number") {
        this.scrollLeft = y
      }
      return
    }
    if (
      options &&
      typeof options === "object" &&
      typeof (options as ScrollToOptions).top === "number"
    ) {
      this.scrollTop = (options as ScrollToOptions).top
    }
    if (
      options &&
      typeof options === "object" &&
      typeof (options as ScrollToOptions).left === "number"
    ) {
      this.scrollLeft = (options as ScrollToOptions).left
    }
  }
}
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
windowWithScroll.scrollTo = (options?: ScrollToOptions | number, y?: number) => {
  if (typeof options === "number") {
    window.scrollY = options
    if (typeof y === "number") {
      window.scrollX = y
    }
    return
  }
  if (!options) {
    return
  }
  const { top, left } = options
  if (typeof top === "number") {
    window.scrollY = top
  }
  if (typeof left === "number") {
    window.scrollX = left
  }
}
vi.mock("qrcode.react", () => ({
  QRCodeSVG: () => null,
}))

vi.mock("@simplewebauthn/browser", () => ({
  startAuthentication: vi.fn(async () => ({
    id: "test-credential",
    rawId: "dGVzdC1jcmVkZW50aWFs",
    response: {
      clientDataJSON: "",
      authenticatorData: "",
      signature: "",
      userHandle: null,
    },
    type: "public-key",
    clientExtensionResults: () => ({}),
    authenticatorAttachment: "platform",
    toJSON() {
      return {
        id: "test-credential",
        rawId: "dGVzdC1jcmVkZW50aWFs",
        response: {
          clientDataJSON: "",
          authenticatorData: "",
          signature: "",
          userHandle: null,
        },
        type: "public-key",
        clientExtensionResults: {},
        authenticatorAttachment: "platform",
      }
    },
  })),
  startRegistration: vi.fn(async () => ({
    id: "test-registration",
    rawId: "dGVzdC1yZWc=",
    response: {
      clientDataJSON: "",
      attestationObject: "",
    },
    type: "public-key",
    clientExtensionResults: () => ({}),
    authenticatorAttachment: "platform",
    toJSON() {
      return {
        id: "test-registration",
        rawId: "dGVzdC1yZWc=",
        response: {
          clientDataJSON: "",
          attestationObject: "",
        },
        type: "public-key",
        clientExtensionResults: {},
        authenticatorAttachment: "platform",
      }
    },
  })),
}))
