import { randomUUID } from "node:crypto"
import { act, cleanup, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import ResetPassword from "../ResetPassword"
import i18n from "../../i18n/config"
import { server } from "@/tests/mocks/server"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
const typedValue = "Password123!"

const matchText = (text: string) => (content: string) => content.startsWith(text)
const passwordInput = () => screen.getByLabelText(matchText(i18n.t("auth:fields.password")))
const confirmPasswordInput = () =>
  screen.getByLabelText(matchText(i18n.t("auth:fields.confirmPassword")))

vi.mock("@zxcvbn-ts/core", () => ({
  ZxcvbnFactory: class {
    check() {
      return { score: 3, feedback: { warning: "", suggestions: [] } }
    }
  },
}))
vi.mock("@zxcvbn-ts/language-common", () => ({ adjacencyGraphs: {}, dictionary: {} }))
vi.mock("@zxcvbn-ts/language-en", () => ({ dictionary: {}, translations: { locale: "en" } }))
vi.mock("@zxcvbn-ts/language-ru", () => ({ dictionary: {}, translations: { locale: "ru" } }))

function mockBreachRange() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("", { status: 200 }))
}

function tokenFragment(token: string) {
  return "token=" + encodeURIComponent(token)
}

const tAuthMessage = (key: string) => i18n.t("auth:" + key)

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  cleanup()
  server.resetHandlers()
  vi.restoreAllMocks()
})

describe("ResetPassword token error lifecycle", () => {
  it("clears the clean-route error when a valid fragment arrives in a new history entry and posts that token", async () => {
    const token = "fragment-" + randomUUID()
    const payloads: unknown[] = []
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ ok: true })
      })
    )
    mockBreachRange()
    const user = userEvent.setup()
    const { router } = await renderWithRouter({
      ui: ResetPassword,
      path: "/reset-password",
      authProvider: false,
    })

    expect(await screen.findByRole("alert")).toHaveTextContent(tAuthMessage("reset.invalidLink"))
    const initialIndex = router.history.location.state.__TSR_index
    if (typeof initialIndex !== "number")
      throw new Error("Expected the initial history entry index")

    await act(async () => {
      router.history.push("/reset-password#" + tokenFragment(token), {})
    })
    await waitFor(() => {
      expect(router.history.location.state.__TSR_index).toBeGreaterThan(initialIndex)
      expect(router.state.location.hash).toBe(tokenFragment(token))
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    })

    await user.type(passwordInput(), "Password123!")
    await user.type(confirmPasswordInput(), "Password123!")
    await user.click(screen.getByRole("button", { name: tAuthMessage("reset.saveButton") }))

    expect(await screen.findByText(tAuthMessage("reset.successTitle"))).toBeInTheDocument()
    expect(payloads).toEqual([{ password: typedValue, token }])
  })

  it("keeps a server error through field renders and a same-token history entry", async () => {
    const token = "api-" + randomUUID()
    const errorMessage = "The reset service rejected this request."
    const payloads: unknown[] = []
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ detail: errorMessage }, { status: 400 })
      })
    )
    mockBreachRange()
    const user = userEvent.setup()
    const fragment = tokenFragment(token)
    const { router } = await renderWithRouter({
      ui: ResetPassword,
      path: "/reset-password",
      initialPath: "/reset-password#" + fragment,
      authProvider: false,
    })

    await user.type(passwordInput(), "Password123!")
    await user.type(confirmPasswordInput(), "Password123!")
    await user.click(screen.getByRole("button", { name: tAuthMessage("reset.saveButton") }))
    expect(await screen.findByRole("alert")).toHaveTextContent(errorMessage)

    await user.type(passwordInput(), "x")
    expect(screen.getByRole("alert")).toHaveTextContent(errorMessage)
    const previousIndex = router.history.location.state.__TSR_index
    if (typeof previousIndex !== "number") throw new Error("Expected a history entry index")

    await act(async () => {
      router.history.push("/reset-password#" + fragment, {})
    })
    await waitFor(() => {
      expect(router.history.location.state.__TSR_index).toBeGreaterThan(previousIndex)
      expect(router.state.location.hash).toBe(fragment)
    })
    expect(screen.getByRole("alert")).toHaveTextContent(errorMessage)
    expect(payloads).toHaveLength(1)
  })

  it("keeps the submit-time expired-token error and never posts after the captured token deadline", async () => {
    const token = "ttl-" + randomUUID()
    const payloads: unknown[] = []
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ ok: true })
      })
    )

    const initialTime = Date.now()
    let currentTime = initialTime
    const dateNowSpy = vi.spyOn(Date, "now").mockImplementation(() => currentTime)
    const browserTimers: Pick<Window, "setTimeout" | "clearTimeout"> = window
    const originalSetTimeout = browserTimers.setTimeout.bind(browserTimers)
    const originalClearTimeout = browserTimers.clearTimeout.bind(browserTimers)
    type CapturedExpiryTimer = {
      id: number
      scheduledAt: number
      delay: number
      cleared: boolean
      fired: boolean
      callback: () => void
    }
    const expiryTimers: CapturedExpiryTimer[] = []
    const setTimeoutSpy = vi
      .spyOn(browserTimers, "setTimeout")
      .mockImplementation((handler, timeout, ...args) => {
        const delay = Number(timeout ?? 0)
        const id = originalSetTimeout(handler, timeout, ...args)
        if (typeof handler === "function" && delay === 45 * 60 * 1000) {
          const timer: CapturedExpiryTimer = {
            id,
            scheduledAt: currentTime,
            delay,
            cleared: false,
            fired: false,
            callback: () => {},
          }
          timer.callback = () => {
            if (timer.fired) return
            timer.fired = true
            originalClearTimeout(timer.id)
            Reflect.apply(handler, window, args)
          }
          expiryTimers.push(timer)
        }
        return id
      })
    const clearTimeoutSpy = vi.spyOn(browserTimers, "clearTimeout").mockImplementation((id) => {
      const timer = expiryTimers.find((candidate) => candidate.id === id)
      if (timer) timer.cleared = true
      originalClearTimeout(id)
    })
    let destroyHistory: (() => void) | undefined

    try {
      const rendered = await renderWithRouter({
        ui: ResetPassword,
        path: "/reset-password",
        initialPath: "/reset-password?token=" + encodeURIComponent(token),
        authProvider: false,
      })
      destroyHistory = () => rendered.router.history.destroy()
      await waitFor(() => {
        expect(rendered.router.state.location.search).not.toHaveProperty("token")
        expect(expiryTimers.length).toBeGreaterThan(0)
        expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      })

      const activeExpiryTimers = expiryTimers.filter((timer) => !timer.cleared && !timer.fired)
      expect(activeExpiryTimers.length).toBeGreaterThan(0)
      expect(
        expiryTimers.every(
          (timer) => timer.scheduledAt === initialTime && timer.delay === 45 * 60 * 1000
        )
      ).toBe(true)
      const expiry = activeExpiryTimers[0]
      if (!expiry) throw new Error("Expected an active captured legacy-token expiry timer")
      const tokenDeadline = expiry.scheduledAt + expiry.delay
      expect(tokenDeadline).toBe(initialTime + 45 * 60 * 1000)

      currentTime = tokenDeadline + 1
      expect(expiryTimers.every((timer) => !timer.fired)).toBe(true)
      const user = userEvent.setup()
      mockBreachRange()
      await user.type(passwordInput(), "Password123!")
      await user.type(confirmPasswordInput(), "Password123!")
      await user.click(screen.getByRole("button", { name: tAuthMessage("reset.saveButton") }))

      expect(await screen.findByRole("alert")).toHaveTextContent(tAuthMessage("reset.invalidLink"))
      await user.type(passwordInput(), "x")
      expect(screen.getByRole("alert")).toHaveTextContent(tAuthMessage("reset.invalidLink"))
      expect(payloads).toEqual([])
      expect(expiryTimers.every((timer) => !timer.fired)).toBe(true)
    } finally {
      try {
        cleanup()
      } finally {
        try {
          const cleanupTime =
            Math.max(currentTime, ...expiryTimers.map((timer) => timer.scheduledAt + timer.delay)) +
            1
          currentTime = cleanupTime
          await act(async () => {
            for (let index = 0; index < expiryTimers.length; index += 1) {
              const timer = expiryTimers[index]
              if (timer && !timer.cleared && !timer.fired) timer.callback()
            }
            await Promise.resolve()
          })
          expect(expiryTimers.every((timer) => timer.cleared || timer.fired)).toBe(true)
        } finally {
          destroyHistory?.()
          clearTimeoutSpy.mockRestore()
          setTimeoutSpy.mockRestore()
          dateNowSpy.mockRestore()
        }
      }
    }
  })
})
