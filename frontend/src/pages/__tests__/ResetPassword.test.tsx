import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import ResetPassword from "../ResetPassword"
import api from "@/api/client"
import { server } from "@/tests/mocks/server"
import i18n from "../../i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)
const tCommon = (key: string) => i18n.t(`common:${key}`)
const matchText = (text: string) => (content: string) => content.startsWith(text)

vi.mock("zxcvbn", () => ({
  default: () => ({ score: 3, feedback: { warning: "", suggestions: [] } }),
}))

const passwordAnalysis = vi.hoisted(() => ({
  shouldThrow: false,
  score: 3,
  suggestions: ["Add another word"],
  deferred: false,
  pending: [] as Array<{
    resolve: (result: {
      score: number
      feedback: { warning: string; suggestions: string[] }
    }) => void
    reject: (error: unknown) => void
  }>,
}))
vi.mock("@zxcvbn-ts/core", () => ({
  ZxcvbnFactory: class {
    check() {
      if (passwordAnalysis.shouldThrow) throw new Error("analysis unavailable")
      if (passwordAnalysis.deferred) {
        return new Promise((resolve, reject) => {
          passwordAnalysis.pending.push({ resolve, reject })
        })
      }
      return {
        score: passwordAnalysis.score,
        feedback: { warning: "", suggestions: passwordAnalysis.suggestions },
      }
    }
  },
}))
vi.mock("@zxcvbn-ts/language-common", () => ({ adjacencyGraphs: {}, dictionary: {} }))

const renderWithToken = () =>
  renderWithRouter({
    ui: ResetPassword,
    // TanStack Router path param syntax is `$token` (vs react-router-dom `:token`).
    path: "/reset/$token",
    initialPath: "/reset/token123",
  })

describe("ResetPassword page", () => {
  beforeEach(() => {
    localStorage.clear()
    passwordAnalysis.shouldThrow = false
    passwordAnalysis.score = 3
    passwordAnalysis.suggestions = ["Add another word"]
    passwordAnalysis.deferred = false
    passwordAnalysis.pending = []
  })

  it("uses the i18n language when no resolved language is available", async () => {
    const resolvedLanguage = i18n.resolvedLanguage
    i18n.resolvedLanguage = undefined
    try {
      await renderWithToken()
      expect(screen.getByRole("button", { name: tAuth("reset.saveButton") })).toBeInTheDocument()
    } finally {
      i18n.resolvedLanguage = resolvedLanguage
    }
  })

  it("does not hide or translate the form entrance when reduced motion is requested", async () => {
    const matchMedia = vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          matches: query === "(prefers-reduced-motion: reduce)",
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList
    )

    try {
      const { container } = await renderWithToken()
      const entrance = container.querySelector(".z-modal")
      expect(entrance?.getAttribute("style") ?? "").not.toMatch(/opacity:\s*0|translate/i)
    } finally {
      matchMedia.mockRestore()
    }
  })

  it("propagates API errors to the user", async () => {
    server.use(
      http.post("*/password/reset", () =>
        HttpResponse.json({ detail: tAuth("reset.invalidLink") }, { status: 400 })
      )
    )

    const user = userEvent.setup()
    await renderWithToken()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "Password123!"
    )
    await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))

    expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
  })

  it("uses the generic message for a non-object transport failure", async () => {
    const post = vi.spyOn(api, "post").mockRejectedValueOnce("offline")
    const user = userEvent.setup()
    await renderWithToken()
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "Password123!"
    )

    await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))

    expect(await screen.findByText(tAuth("reset.errorGeneric"))).toBeInTheDocument()
    post.mockRestore()
  })

  it("submits the new password and shows success state", async () => {
    const payloads: unknown[] = []
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        const body = await request.json()
        payloads.push(body)
        return HttpResponse.json({ ok: true })
      })
    )

    const user = userEvent.setup()
    await renderWithToken()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "Password123!"
    )

    const submitButton = screen.getByRole("button", { name: tAuth("reset.saveButton") })
    await user.click(submitButton)

    await waitFor(() => expect(screen.getByText(tAuth("reset.successTitle"))).toBeInTheDocument())
    expect(payloads).toEqual([{ password: "Password123!", token: "token123" }])
  })

  it("shows the success state without an entrance transform under reduced motion", async () => {
    const matchMedia = vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          matches: query === "(prefers-reduced-motion: reduce)",
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList
    )
    try {
      const user = userEvent.setup()
      const { container } = await renderWithToken()
      await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
      await user.type(
        screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
        "Password123!"
      )
      await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))

      await screen.findByText(tAuth("reset.successTitle"))
      expect(
        container.querySelector(".space-y-6.pt-4.text-center")?.getAttribute("style") ?? ""
      ).not.toMatch(/opacity:\s*0|scale/i)
    } finally {
      matchMedia.mockRestore()
    }
  })

  it("rejects a reset page without a route or query token", async () => {
    await renderWithRouter({ ui: ResetPassword, path: "/reset", initialPath: "/reset" })

    expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "Password123!"
    )
    await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))
    expect(screen.getByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
  })

  it("toggles password visibility and reports Caps Lock state", async () => {
    const user = userEvent.setup()
    await renderWithToken()

    const password = screen.getByLabelText(matchText(tAuth("fields.password")))
    const confirmPassword = screen.getByLabelText(matchText(tAuth("fields.confirmPassword")))
    const passwordToggle = document.getElementById("reset-password-toggle")!
    const confirmToggle = document.getElementById("reset-confirm-toggle")!

    expect(password.closest("form")).toHaveAttribute("autocomplete", "on")
    expect(password).toHaveAttribute("autocomplete", "new-password")
    expect(passwordToggle).toHaveClass("min-h-11", "min-w-11")
    expect(confirmToggle).toHaveClass("min-h-11", "min-w-11")
    expect(passwordToggle).not.toHaveAttribute("tabindex", "-1")
    expect(confirmToggle).not.toHaveAttribute("tabindex", "-1")
    expect(passwordToggle).toHaveAccessibleName(tAuth("actions.showPassword"))
    expect(confirmToggle).toHaveAccessibleName(tAuth("actions.showPassword"))

    expect(password).toHaveAttribute("type", "password")
    await user.click(passwordToggle)
    expect(password).toHaveAttribute("type", "text")
    expect(passwordToggle).toHaveAccessibleName(tAuth("actions.hideCredential"))
    await user.click(confirmToggle)
    expect(confirmPassword).toHaveAttribute("type", "text")
    expect(confirmToggle).toHaveAccessibleName(tAuth("actions.hideCredential"))

    const modifierState = vi
      .spyOn(window.KeyboardEvent.prototype, "getModifierState")
      .mockReturnValue(true)
    fireEvent.keyDown(password, { key: "a" })
    expect(screen.getByText(tAuth("messages.capsLock"))).toBeInTheDocument()
    modifierState.mockReturnValue(false)
    fireEvent.keyUp(password, { key: "a" })
    expect(screen.queryByText(tAuth("messages.capsLock"))).not.toBeInTheDocument()
    modifierState.mockRestore()
  })

  it("shows the pwned-password warning when the breach range contains the suffix", async () => {
    passwordAnalysis.suggestions = []
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("F5F70D47ADC2DB2EB397FBEF5F7BC560E29:3\n", { status: 200 }))
    const user = userEvent.setup()
    await renderWithToken()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")

    await waitFor(() => expect(screen.getByText(tAuth("reset.pwnedWarning"))).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("https://api.pwnedpasswords.com/range/49EFE"),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    fetchMock.mockRestore()
  })

  it("keeps the newest breach result when an older request resolves last", async () => {
    let resolveOlder!: (response: Response) => void
    let resolveNewer!: (response: Response) => void
    const olderResponse = new Response("F5F70D47ADC2DB2EB397FBEF5F7BC560E29:3\n", {
      status: 200,
    })
    const newerResponse = new Response("", { status: 200 })
    const olderText = vi.spyOn(olderResponse, "text")
    const newerText = vi.spyOn(newerResponse, "text")
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (resolveOlder = resolve)))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (resolveNewer = resolve)))
    const { unmount } = await renderWithToken()
    const password = screen.getByLabelText(matchText(tAuth("fields.password")))

    fireEvent.change(password, { target: { value: "Password123!" } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    fireEvent.change(password, { target: { value: "Password456!" } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    await act(async () => {
      resolveNewer(newerResponse)
    })
    await waitFor(() => expect(newerText).toHaveBeenCalled())
    expect(screen.queryByText(tAuth("reset.pwnedWarning"))).not.toBeInTheDocument()

    await act(async () => {
      resolveOlder(olderResponse)
    })
    await waitFor(() => expect(olderText).toHaveBeenCalled())
    expect(screen.queryByText(tAuth("reset.pwnedWarning"))).not.toBeInTheDocument()

    unmount()
    fetchMock.mockRestore()
  })

  it("aborts the active breach request when the page unmounts", async () => {
    let requestSignal: AbortSignal | null | undefined
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => {
      requestSignal = init?.signal
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Request aborted", "AbortError"))
        )
      })
    })
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined)
    const { unmount } = await renderWithToken()
    const password = screen.getByLabelText(matchText(tAuth("fields.password")))

    fireEvent.change(password, { target: { value: "Password123!" } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    unmount()

    expect(requestSignal?.aborted).toBe(true)
    await act(async () => Promise.resolve())
    expect(consoleError.mock.calls.some(([message]) => String(message).includes("unmounted"))).toBe(
      false
    )

    consoleError.mockRestore()
    fetchMock.mockRestore()
  })

  it.each(["resolve", "reject"] as const)(
    "does not start a breach lookup when password analysis settles after unmount (%s)",
    async (outcome) => {
      passwordAnalysis.deferred = true
      const fetchMock = vi.spyOn(globalThis, "fetch")
      const { unmount } = await renderWithToken()
      fireEvent.change(screen.getByLabelText(matchText(tAuth("fields.password"))), {
        target: { value: "Password123!" },
      })
      await waitFor(() => expect(passwordAnalysis.pending).toHaveLength(1))

      unmount()
      await act(async () => {
        if (outcome === "resolve") {
          passwordAnalysis.pending[0]!.resolve({
            score: 3,
            feedback: { warning: "", suggestions: [] },
          })
        } else {
          passwordAnalysis.pending[0]!.reject(new Error("analysis unavailable"))
        }
      })

      expect(fetchMock).not.toHaveBeenCalled()
      fetchMock.mockRestore()
    }
  )

  it("swallows password-analysis and breach-service failures", async () => {
    passwordAnalysis.shouldThrow = true
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"))
    const user = userEvent.setup()
    await renderWithToken()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    fetchMock.mockRestore()
  })

  it("handles non-ok and non-matching breach responses without warning", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 503 }))
      .mockResolvedValueOnce(new Response("NOT_THE_SUFFIX:1\n", { status: 200 }))
    const user = userEvent.setup()
    await renderWithToken()

    const password = screen.getByLabelText(matchText(tAuth("fields.password")))
    await user.type(password, "Password123!")
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    expect(screen.queryByText(tAuth("reset.pwnedWarning"))).not.toBeInTheDocument()

    await user.clear(password)
    await user.type(password, "Password456!")
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(screen.queryByText(tAuth("reset.pwnedWarning"))).not.toBeInTheDocument()
    fetchMock.mockRestore()
  })

  it("covers validation helpers and strength color variants", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("", { status: 200 }))
    const user = userEvent.setup()
    await renderWithToken()

    const password = screen.getByLabelText(matchText(tAuth("fields.password")))
    const confirmPassword = screen.getByLabelText(matchText(tAuth("fields.confirmPassword")))

    await user.type(password, "short")
    await user.tab()
    expect(await screen.findByText("Password must be at least 8 characters")).toBeInTheDocument()

    passwordAnalysis.score = 0
    await user.clear(password)
    await user.type(password, "Password123!")
    await waitFor(() => expect(screen.getByText(tCommon("strength.very_weak"))).toBeInTheDocument())

    passwordAnalysis.score = 2
    await user.clear(password)
    await user.type(password, "Password456!")
    await waitFor(() => expect(screen.getByText(tCommon("strength.medium"))).toBeInTheDocument())

    await user.type(confirmPassword, "Different123!")
    await user.tab()
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument()
    fetchMock.mockRestore()
  })

  it("uses the generic error when reset API detail is absent", async () => {
    server.use(http.post("*/password/reset", () => HttpResponse.json({}, { status: 500 })))
    const user = userEvent.setup()
    await renderWithToken()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "Password123!"
    )
    await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))

    expect(await screen.findByText(tAuth("reset.errorGeneric"))).toBeInTheDocument()
  })

  it("accepts a token supplied through the query string", async () => {
    const payloads: unknown[] = []
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ ok: true })
      })
    )
    const user = userEvent.setup()
    await renderWithRouter({
      ui: ResetPassword,
      path: "/reset",
      initialPath: "/reset?token=query-token",
    })

    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "Password123!"
    )
    await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))

    await waitFor(() => expect(screen.getByText(tAuth("reset.successTitle"))).toBeInTheDocument())
    expect(payloads).toEqual([{ password: "Password123!", token: "query-token" }])
  })
})
