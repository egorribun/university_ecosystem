import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"

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
  warning: "",
  suggestions: ["Add another word"] as string[] | undefined,
  omitFeedback: false,
  reportLocale: false,
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
    private readonly locale: string
    constructor(options: { translations: { locale: string } }) {
      this.locale = options.translations.locale
    }
    check() {
      if (passwordAnalysis.shouldThrow) throw new Error("analysis unavailable")
      if (passwordAnalysis.deferred) {
        return new Promise((resolve, reject) => {
          passwordAnalysis.pending.push({ resolve, reject })
        })
      }
      if (passwordAnalysis.omitFeedback) return { score: passwordAnalysis.score }
      return {
        score: passwordAnalysis.score,
        feedback: {
          warning: passwordAnalysis.reportLocale
            ? `locale:${this.locale}`
            : passwordAnalysis.warning,
          suggestions: passwordAnalysis.suggestions,
        },
      }
    }
  },
}))
vi.mock("@zxcvbn-ts/language-common", () => ({ adjacencyGraphs: {}, dictionary: {} }))
vi.mock("@zxcvbn-ts/language-en", () => ({ dictionary: {}, translations: { locale: "en" } }))
vi.mock("@zxcvbn-ts/language-ru", () => ({ dictionary: {}, translations: { locale: "ru" } }))

const renderWithToken = () =>
  renderWithRouter({
    ui: ResetPassword,
    // TanStack Router path param syntax is `$token` (vs react-router-dom `:token`).
    path: "/reset/$token",
    initialPath: "/reset/token123",
    // Reset-password is a public form; no auth profile synchronization is
    // needed for its behavior and would outlive the test's mounted tree.
    authProvider: false,
  })

describe("ResetPassword page", () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    localStorage.clear()
    passwordAnalysis.shouldThrow = false
    passwordAnalysis.score = 3
    passwordAnalysis.warning = ""
    passwordAnalysis.suggestions = ["Add another word"]
    passwordAnalysis.omitFeedback = false
    passwordAnalysis.reportLocale = false
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

describe("ResetPassword behaviour details", () => {
  // SHA-1 suffix of a fixture password, the shape of an HIBP range response.
  const breachSuffixForPassword123 = "F5F70D47ADC2DB2EB397FBEF5F7BC560E29:3\n" // pragma: allowlist secret
  const passwordInput = () => screen.getByLabelText(matchText(tAuth("fields.password")))
  const confirmInput = () => screen.getByLabelText(matchText(tAuth("fields.confirmPassword")))
  const feedbackIcon = (container: HTMLElement) => container.querySelector(".lucide-shield-check")
  const mockBreachRange = (body = "", status = 200) =>
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(body, { status }))
  const mockReducedMotion = () =>
    vi.spyOn(window, "matchMedia").mockImplementation(
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
  const fillMatchingPasswords = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.type(passwordInput(), "Password123!")
    await user.type(confirmInput(), "Password123!")
    await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))
  }
  const motionView = (element: Element | null) => element?.closest("[style]") ?? null
  const renderNestedResetRoute = (initialPath: string) => {
    const rootRoute = createRootRoute({ component: Outlet })
    const pageRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: "/reset-password",
      component: ResetPassword,
    })
    const tokenRoute = createRoute({
      getParentRoute: () => pageRoute,
      path: "$token",
      component: () => null,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([pageRoute.addChildren([tokenRoute])]),
      history: createMemoryHistory({ initialEntries: [initialPath] }),
    })
    render(<RouterProvider router={router} />)
    return router
  }

  beforeEach(() => {
    passwordAnalysis.shouldThrow = false
    passwordAnalysis.score = 3
    passwordAnalysis.warning = ""
    passwordAnalysis.suggestions = ["Add another word"]
    passwordAnalysis.omitFeedback = false
    passwordAnalysis.reportLocale = false
    passwordAnalysis.deferred = false
    passwordAnalysis.pending = []
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("renders its guidance without transient hints for a valid link", async () => {
    const { container } = await renderWithToken()

    expect(screen.getByText(tAuth("reset.subtitle"))).toBeInTheDocument()
    expect(screen.getByRole("link", { name: tAuth("reset.linkHelp") })).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.queryByText(tAuth("messages.capsLock"))).not.toBeInTheDocument()
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
    expect(feedbackIcon(container)).toBeNull()
    expect(passwordInput()).toHaveAttribute("type", "password")
    expect(confirmInput()).toHaveAttribute("type", "password")
    expect(passwordInput()).toHaveAttribute("aria-invalid", "false")
    expect(confirmInput()).toHaveAttribute("aria-invalid", "false")
  })

  it("marks both fields invalid when their validation fails", async () => {
    mockBreachRange()
    const user = userEvent.setup()
    await renderWithToken()

    await user.type(passwordInput(), "short")
    await user.tab()
    await waitFor(() => expect(passwordInput()).toHaveAttribute("aria-invalid", "true"))

    await user.clear(passwordInput())
    await user.type(passwordInput(), "Password123!")
    await user.type(confirmInput(), "Different123!")
    await user.tab()
    await waitFor(() => expect(confirmInput()).toHaveAttribute("aria-invalid", "true"))
  })

  it("shows the success copy with a way back to sign in", async () => {
    server.use(http.post("*/password/reset", () => HttpResponse.json({ ok: true })))
    mockBreachRange()
    const user = userEvent.setup()
    await renderWithToken()

    await fillMatchingPasswords(user)

    expect(await screen.findByText(tAuth("reset.successMessage"))).toBeInTheDocument()
    expect(screen.getByRole("link", { name: tAuth("actions.goToLogin") })).toBeInTheDocument()
  })

  it.each([
    [0, "strength.very_weak", 10],
    [1, "strength.weak", 30],
    [2, "strength.medium", 55],
    [3, "strength.strong", 75],
    [4, "strength.very_strong", 100],
  ] as const)("renders score %i as %s at %i percent", async (score, labelKey, percent) => {
    passwordAnalysis.score = score
    mockBreachRange()
    await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password123!" } })

    const progress = await screen.findByRole("progressbar")
    expect(progress).toHaveAttribute("aria-valuenow", String(percent))
    expect(progress.firstElementChild).toHaveClass(
      score < 2 ? "bg-error-text" : score === 2 ? "bg-warning-text" : "bg-success-text"
    )
    expect(screen.getByText(tCommon(labelKey))).toBeInTheDocument()
    expect(screen.getByText(tAuth("register.passwordStrength"))).toBeInTheDocument()
  })

  it.each([
    [
      "a warning and suggestions",
      "Too guessable",
      ["Add a word", "Avoid years"],
      "Too guessable · Add a word · Avoid years",
    ],
    ["only a warning", "Too guessable", [], "Too guessable"],
    ["a warning without a suggestion list", "Too guessable", undefined, "Too guessable"],
    ["only suggestions", "", ["Add a word"], "· Add a word"],
  ])("composes password feedback from %s", async (_label, warning, suggestions, expected) => {
    passwordAnalysis.warning = warning
    passwordAnalysis.suggestions = suggestions
    mockBreachRange()
    await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password123!" } })

    expect(await screen.findByText(expected)).toBeInTheDocument()
  })

  it("keeps the strength meter when the analyzer returns no feedback", async () => {
    passwordAnalysis.omitFeedback = true
    mockBreachRange()
    const { container } = await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password123!" } })

    expect(await screen.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "75")
    expect(feedbackIcon(container)).toBeNull()
  })

  it("clears strength, feedback and the breach warning when the password is emptied", async () => {
    mockBreachRange(breachSuffixForPassword123)
    const { container } = await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password123!" } })
    expect(await screen.findByText(tAuth("reset.pwnedWarning"))).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toBeInTheDocument()
    expect(feedbackIcon(container)).not.toBeNull()

    fireEvent.change(passwordInput(), { target: { value: "" } })

    await waitFor(() => {
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
      expect(screen.queryByText(tAuth("reset.pwnedWarning"))).not.toBeInTheDocument()
      expect(feedbackIcon(container)).toBeNull()
    })
  })

  it("drops the previous strength when a later analysis fails", async () => {
    mockBreachRange()
    const { container } = await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password123!" } })
    expect(await screen.findByText("· Add another word")).toBeInTheDocument()

    passwordAnalysis.shouldThrow = true
    fireEvent.change(passwordInput(), { target: { value: "Password456!" } })

    await waitFor(() => {
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
      expect(feedbackIcon(container)).toBeNull()
    })
  })

  it("analyses only the latest password typed within the debounce window", async () => {
    passwordAnalysis.deferred = true
    mockBreachRange()
    await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password1!" } })
    fireEvent.change(passwordInput(), { target: { value: "Password2!" } })
    await waitFor(() => expect(passwordAnalysis.pending.length).toBeGreaterThan(0))
    await act(() => new Promise((resolve) => setTimeout(resolve, 400)))

    expect(passwordAnalysis.pending).toHaveLength(1)
  })

  it.each(["resolve", "reject"] as const)(
    "ignores a superseded analysis that settles last (%s)",
    async (outcome) => {
      passwordAnalysis.deferred = true
      passwordAnalysis.suggestions = []
      mockBreachRange()
      await renderWithToken()

      fireEvent.change(passwordInput(), { target: { value: "Password1!" } })
      await waitFor(() => expect(passwordAnalysis.pending).toHaveLength(1))
      fireEvent.change(passwordInput(), { target: { value: "Password2!" } })
      await waitFor(() => expect(passwordAnalysis.pending).toHaveLength(2))

      await act(async () => {
        passwordAnalysis.pending[1]!.resolve({
          score: 4,
          feedback: { warning: "", suggestions: [] },
        })
      })
      expect(await screen.findByText(tCommon("strength.very_strong"))).toBeInTheDocument()

      await act(async () => {
        if (outcome === "resolve") {
          passwordAnalysis.pending[0]!.resolve({
            score: 0,
            feedback: { warning: "", suggestions: [] },
          })
        } else {
          passwordAnalysis.pending[0]!.reject(new Error("analysis unavailable"))
        }
      })

      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100")
      expect(screen.getByText(tCommon("strength.very_strong"))).toBeInTheDocument()
    }
  )

  it("does not query the breach range when the page unmounts while hashing", async () => {
    let finishDigest!: (hash: ArrayBuffer) => void
    const digest = vi
      .spyOn(crypto.subtle, "digest")
      .mockImplementation(() => new Promise<ArrayBuffer>((resolve) => (finishDigest = resolve)))
    const fetchMock = mockBreachRange()
    const { unmount } = await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password123!" } })
    await waitFor(() => expect(digest).toHaveBeenCalled())
    unmount()
    await act(async () => {
      finishDigest(new ArrayBuffer(20))
    })

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("queries only the hash prefix and ignores a failed range response", async () => {
    const fetchMock = mockBreachRange(breachSuffixForPassword123, 503)
    await renderWithToken()

    fireEvent.change(passwordInput(), { target: { value: "Password123!" } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)))

    expect(fetchMock.mock.calls[0]?.[0]).toBe("https://api.pwnedpasswords.com/range/49EFE")
    expect(screen.queryByText(tAuth("reset.pwnedWarning"))).not.toBeInTheDocument()
  })

  it.each([
    ["null", null],
    ["a response without data", { response: {} }],
  ])("uses the generic error when the reset request rejects with %s", async (_label, error) => {
    vi.spyOn(api, "post").mockRejectedValueOnce(error)
    mockBreachRange()
    const user = userEvent.setup()
    await renderWithToken()

    await fillMatchingPasswords(user)

    expect(await screen.findByText(tAuth("reset.errorGeneric"))).toBeInTheDocument()
  })

  it("does not send a reset request without a token", async () => {
    const post = vi.spyOn(api, "post")
    mockBreachRange()
    const user = userEvent.setup()
    await renderWithRouter({ ui: ResetPassword, path: "/reset", initialPath: "/reset" })

    await fillMatchingPasswords(user)

    expect(screen.getByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
  })

  it("reports Caps Lock from key down and key up on both fields", async () => {
    const modifierState = vi.spyOn(window.KeyboardEvent.prototype, "getModifierState")
    const capsOn = () => modifierState.mockImplementation((key) => key === "CapsLock")
    const capsOff = () => modifierState.mockImplementation(() => false)
    const capsWarning = () => screen.queryByText(tAuth("messages.capsLock"))
    await renderWithToken()

    for (const field of [passwordInput(), confirmInput()]) {
      capsOn()
      fireEvent.keyDown(field, { key: "a" })
      expect(capsWarning()).toBeInTheDocument()
      capsOff()
      fireEvent.keyDown(field, { key: "a" })
      expect(capsWarning()).not.toBeInTheDocument()
      capsOn()
      fireEvent.keyUp(field, { key: "a" })
      expect(capsWarning()).toBeInTheDocument()
      capsOff()
      fireEvent.keyUp(field, { key: "a" })
      expect(capsWarning()).not.toBeInTheDocument()
    }
  })

  it("starts the entrance hidden and offset when motion is allowed", async () => {
    await renderWithToken()

    const formView = motionView(screen.getByRole("button", { name: tAuth("reset.saveButton") }))
    expect(formView).toHaveStyle({ opacity: "0" })
    expect(motionView(formView!.parentElement)).toHaveStyle({
      opacity: "0",
      transform: "translateY(20px)",
    })
  })

  it("renders every view in its final state under reduced motion", async () => {
    mockReducedMotion()
    server.use(http.post("*/password/reset", () => HttpResponse.json({ ok: true })))
    mockBreachRange()
    const user = userEvent.setup()
    await renderWithToken()

    const formView = motionView(screen.getByRole("button", { name: tAuth("reset.saveButton") }))
    expect(formView).toHaveStyle({ opacity: "1" })
    expect(motionView(formView!.parentElement)).toHaveStyle({ opacity: "1", transform: "none" })

    await fillMatchingPasswords(user)

    const successView = motionView(await screen.findByText(tAuth("reset.successTitle")))
    expect(successView).toHaveStyle({ opacity: "1", transform: "none" })
  })

  it("starts the success view faded and scaled down when motion is allowed", async () => {
    server.use(http.post("*/password/reset", () => HttpResponse.json({ ok: true })))
    mockBreachRange()
    const user = userEvent.setup()
    await renderWithToken()

    await fillMatchingPasswords(user)

    const successView = motionView(await screen.findByText(tAuth("reset.successTitle")))
    expect(successView).toHaveStyle({ opacity: "0", transform: "scale(0.95)" })
  })

  it("reads the reset token from the nested token route", async () => {
    const payloads: unknown[] = []
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ ok: true })
      })
    )
    mockBreachRange()
    const user = userEvent.setup()
    renderNestedResetRoute("/reset-password/nested-token")

    await screen.findByRole("button", { name: tAuth("reset.saveButton") })
    await fillMatchingPasswords(user)

    await screen.findByText(tAuth("reset.successTitle"))
    expect(payloads).toEqual([{ password: "Password123!", token: "nested-token" }])
  })

  it("flags the link as invalid once navigation drops the token", async () => {
    const router = renderNestedResetRoute("/reset-password/nested-token")
    await screen.findByRole("button", { name: tAuth("reset.saveButton") })
    expect(screen.queryByText(tAuth("reset.invalidLink"))).not.toBeInTheDocument()

    await act(() => router.navigate({ to: "/reset-password" }))

    expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
  })

  it("analyses strength in the resolved interface language", async () => {
    const selectedLanguage = window.__UE_SELECTED_LANG__
    passwordAnalysis.reportLocale = true
    passwordAnalysis.suggestions = []
    mockBreachRange()
    window.__UE_SELECTED_LANG__ = "ru"
    try {
      await renderWithToken()
      fireEvent.change(passwordInput(), { target: { value: "Password123!" } })

      expect(await screen.findByText("locale:ru")).toBeInTheDocument()
    } finally {
      if (selectedLanguage === undefined) delete window.__UE_SELECTED_LANG__
      else window.__UE_SELECTED_LANG__ = selectedLanguage
    }
  })
})
