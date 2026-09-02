import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { axe } from "jest-axe"

import Register, { resolveRegistrationEmailErrorKey } from "../Register"
import api from "@/api/client"
import { server } from "@/tests/mocks/server"
import i18n from "../../i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)
const matchText = (text: string) => (content: string) => content.startsWith(text)

const passwordAnalysis = vi.hoisted(() => ({
  mode: "normal" as "normal" | "throw" | "unknown",
  calls: 0,
  constructors: 0,
  deferred: false,
  pending: [] as Array<{
    password: string
    resolve: (result: { score: number }) => void
    reject: (error: unknown) => void
  }>,
}))

vi.mock("@zxcvbn-ts/core", () => ({
  ZxcvbnFactory: class {
    constructor() {
      passwordAnalysis.constructors += 1
    }

    check(password: string) {
      passwordAnalysis.calls += 1
      if (passwordAnalysis.mode === "throw") throw new Error("analysis unavailable")
      if (passwordAnalysis.deferred) {
        return new Promise<{ score: number }>((resolve, reject) => {
          passwordAnalysis.pending.push({ password, resolve, reject })
        })
      }
      return { score: passwordAnalysis.mode === "unknown" ? 99 : 3 }
    }
  },
}))
vi.mock("@zxcvbn-ts/language-common", () => ({ adjacencyGraphs: {}, dictionary: {} }))

const renderRegister = () =>
  renderWithRouter({
    ui: Register,
    path: "/register",
    initialPath: "/register",
    extraRoutes: [{ path: "/login", Component: () => <div>Sign in page</div> }],
  })

describe("Register page", () => {
  beforeEach(() => {
    passwordAnalysis.mode = "normal"
    passwordAnalysis.calls = 0
    passwordAnalysis.constructors = 0
    passwordAnalysis.deferred = false
    passwordAnalysis.pending = []
  })

  it("uses the i18n language when no resolved language is available", async () => {
    const resolvedLanguage = i18n.resolvedLanguage
    i18n.resolvedLanguage = undefined
    try {
      await renderRegister()
      expect(screen.getByRole("button", { name: tAuth("actions.signUp") })).toBeInTheDocument()
    } finally {
      i18n.resolvedLanguage = resolvedLanguage
    }
  })

  it("provides a stable fallback key for missing email validation messages", () => {
    expect(resolveRegistrationEmailErrorKey(undefined)).toBe("auth:messages.invalidFormat")
    expect(resolveRegistrationEmailErrorKey("")).toBe("auth:messages.invalidFormat")
    expect(resolveRegistrationEmailErrorKey("custom.message")).toBe("custom.message")
  })

  it("does not translate the form entrance when reduced motion is requested", async () => {
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
      await renderRegister()
      const entrance = screen
        .getByRole("button", { name: tAuth("actions.signUp") })
        .closest("form")?.parentElement
      expect(entrance?.getAttribute("style") ?? "").not.toMatch(/translate/i)
    } finally {
      matchMedia.mockRestore()
    }
  })

  it("surfaces API error messages", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json({ detail: "Email already used" }, { status: 400 })
      )
    )

    const user = userEvent.setup()
    await renderRegister()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.name"))), "Test User")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.email"))), "user@example.com")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "password123")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "password123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))

    expect(await screen.findByText("Email already used")).toBeInTheDocument()
  })

  it("sends registration payload and navigates to login", async () => {
    const payloads: unknown[] = []
    server.use(
      http.post("*/auth/register", async ({ request }) => {
        const body = await request.json()
        payloads.push(body)
        return HttpResponse.json({ status: "ok" })
      })
    )

    const user = userEvent.setup()
    await renderRegister()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.name"))), "Test User")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.email"))), "user@example.com")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "password123")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "password123"
    )

    const submitButton = screen.getByRole("button", { name: tAuth("actions.signUp") })
    await user.click(submitButton)

    await waitFor(() => expect(screen.getByText("Sign in page")).toBeInTheDocument())
    expect(payloads).toEqual([
      {
        email: "user@example.com",
        full_name: "Test User",
        invite_code: "",
        password: "password123",
        role: "student",
      },
    ])
  })

  it("requires an invite code for teacher accounts and validates confirmation", async () => {
    const user = userEvent.setup()
    await renderRegister()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.name"))), "Test User")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.email"))), "user@example.com")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "password123")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))), "different")

    await user.click(screen.getByRole("combobox"))
    await user.click(screen.getByRole("option", { name: tAuth("register.role.teacher") }))
    const inviteInput = screen.getByLabelText(matchText(tAuth("fields.inviteCode")))
    expect(inviteInput).toBeInTheDocument()
    expect(screen.getByText(tAuth("register.inviteRequired"))).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument()

    await user.clear(screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))))
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "password123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))
    expect(inviteInput).toBeInTheDocument()
  })

  it("suggests and accepts a corrected email domain", async () => {
    const user = userEvent.setup()
    await renderRegister()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")))
    fireEvent.blur(emailInput)
    expect(screen.queryByRole("button", { name: /gmail\.com/i })).not.toBeInTheDocument()
    await user.type(emailInput, "student@gmial.com")
    fireEvent.blur(emailInput)

    const suggestion = await screen.findByRole("button", { name: /gmail\.com/i })
    await user.click(suggestion)

    expect(emailInput).toHaveValue("student@gmail.com")
    expect(screen.queryByRole("button", { name: /gmail\.com/i })).not.toBeInTheDocument()
  })

  it("renders password strength, caps-lock hints, and reveal controls", async () => {
    const user = userEvent.setup()
    await renderRegister()

    const passwordInput = screen.getByLabelText(matchText(tAuth("fields.password")))
    const confirmInput = screen.getByLabelText(matchText(tAuth("fields.confirmPassword")))
    const revealButtons = screen.getAllByRole("button", {
      name: tAuth("actions.showPassword"),
    })

    for (const button of revealButtons) {
      expect(button).toHaveClass("min-h-11", "min-w-11")
    }

    await user.click(revealButtons[0]!)
    expect(
      screen.getByRole("button", { name: tAuth("actions.hideCredential") })
    ).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: tAuth("actions.hideCredential") }))

    for (const button of revealButtons) {
      fireEvent.click(button)
      fireEvent.click(button)
    }
    expect(passwordInput).toHaveAttribute("type", "password")
    expect(confirmInput).toHaveAttribute("type", "password")

    fireEvent.keyDown(passwordInput, {
      key: "a",
      getModifierState: (key: string) => key === "CapsLock",
    })
    fireEvent.keyDown(confirmInput, {
      key: "a",
      getModifierState: (key: string) => key === "CapsLock",
    })
    const getModifierState = vi
      .spyOn(KeyboardEvent.prototype, "getModifierState")
      .mockReturnValue(true)
    fireEvent.keyDown(passwordInput, { key: "a" })
    fireEvent.keyDown(confirmInput, { key: "a" })
    expect(screen.getAllByText(tAuth("messages.capsLock"))).toHaveLength(2)
    getModifierState.mockRestore()

    await user.type(passwordInput, "correct-horse-battery-staple")
    await waitFor(() => {
      expect(document.querySelector('[style*="width"]')).toBeInTheDocument()
    })
  })

  it("reuses the password analyzer across password changes", async () => {
    await renderRegister()
    const passwordInput = screen.getByLabelText(matchText(tAuth("fields.password")))

    fireEvent.change(passwordInput, { target: { value: "first-password" } })
    await waitFor(() => expect(passwordAnalysis.calls).toBeGreaterThan(0))
    fireEvent.change(passwordInput, { target: { value: "second-password" } })
    await waitFor(() => expect(passwordAnalysis.calls).toBeGreaterThan(1))

    expect(passwordAnalysis.constructors).toBeLessThanOrEqual(1)
  })

  it("keeps the newest password score when an older analysis resolves last", async () => {
    passwordAnalysis.deferred = true
    await renderRegister()
    const passwordInput = screen.getByLabelText(matchText(tAuth("fields.password")))
    const olderInputValue = "older-input-value"
    const newerInputValue = "newer-input-value"

    fireEvent.change(passwordInput, { target: { value: olderInputValue } })
    await waitFor(() =>
      expect(passwordAnalysis.pending.some(({ password }) => password === olderInputValue)).toBe(
        true
      )
    )
    fireEvent.change(passwordInput, { target: { value: newerInputValue } })
    await waitFor(() =>
      expect(passwordAnalysis.pending.some(({ password }) => password === newerInputValue)).toBe(
        true
      )
    )

    const older = passwordAnalysis.pending.find(({ password }) => password === olderInputValue)!
    const newer = passwordAnalysis.pending.find(({ password }) => password === newerInputValue)!
    await act(async () => newer.resolve({ score: 4 }))
    expect(screen.getByText(tAuth("register.passwordStrengthLevel.excellent"))).toBeInTheDocument()

    await act(async () => older.resolve({ score: 0 }))
    expect(screen.getByText(tAuth("register.passwordStrengthLevel.excellent"))).toBeInTheDocument()
    expect(
      screen.queryByText(tAuth("register.passwordStrengthLevel.veryWeak"))
    ).not.toBeInTheDocument()
  })

  it("keeps the newest password score when an older analysis rejects last", async () => {
    passwordAnalysis.deferred = true
    await renderRegister()
    const passwordInput = screen.getByLabelText(matchText(tAuth("fields.password")))

    fireEvent.change(passwordInput, { target: { value: "older-input-value" } })
    await waitFor(() => expect(passwordAnalysis.pending).toHaveLength(1))
    fireEvent.change(passwordInput, { target: { value: "newer-input-value" } })
    await waitFor(() => expect(passwordAnalysis.pending).toHaveLength(2))

    await act(async () => passwordAnalysis.pending[1]!.resolve({ score: 4 }))
    expect(screen.getByText(tAuth("register.passwordStrengthLevel.excellent"))).toBeInTheDocument()
    await act(async () => passwordAnalysis.pending[0]!.reject(new Error("stale analysis")))

    expect(screen.getByText(tAuth("register.passwordStrengthLevel.excellent"))).toBeInTheDocument()
  })

  it("hides password strength when analysis fails", async () => {
    passwordAnalysis.mode = "throw"
    const user = userEvent.setup()
    await renderRegister()

    const passwordInput = screen.getByLabelText(matchText(tAuth("fields.password")))
    await user.type(passwordInput, "password123")

    await waitFor(() => expect(passwordAnalysis.calls).toBeGreaterThan(0))
    expect(
      document.querySelector('[class~="bg-brand"][class~="transition-all"]')
    ).not.toBeInTheDocument()
  })

  it("keeps the strength bar usable when the score has no translated label", async () => {
    passwordAnalysis.mode = "unknown"
    const user = userEvent.setup()
    await renderRegister()

    const passwordInput = screen.getByLabelText(matchText(tAuth("fields.password")))
    await user.type(passwordInput, "password123")

    await waitFor(() => {
      expect(passwordAnalysis.calls).toBeGreaterThan(0)
      expect(
        document.querySelector('[class~="bg-brand"][class~="transition-all"]')
      ).toBeInTheDocument()
    })
    expect(
      screen.queryByText(tAuth("register.passwordStrengthLevel.excellent"))
    ).not.toBeInTheDocument()
  })

  it("omits optional password labels when translations are unavailable", async () => {
    const translationSpy = vi.spyOn(i18n, "t").mockReturnValue(undefined as never)
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined)

    try {
      await renderRegister()

      expect(document.querySelectorAll("button[aria-label]")).toHaveLength(0)
      expect(document.querySelectorAll("button[title]")).toHaveLength(0)
      expect(consoleError).not.toHaveBeenCalled()
    } finally {
      consoleError.mockRestore()
      translationSpy.mockRestore()
    }
  })

  it("surfaces structured API validation errors", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json({ detail: ["Name is invalid", "Email is invalid"] }, { status: 422 })
      )
    )

    const user = userEvent.setup()
    await renderRegister()
    await user.type(screen.getByLabelText(matchText(tAuth("fields.name"))), "Test User")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.email"))), "user@example.com")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "password123")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "password123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))

    expect(await screen.findByText("Name is invalid; Email is invalid")).toBeInTheDocument()
  })

  it("falls back to the translated error for an unstructured API failure", async () => {
    server.use(
      http.post("*/auth/register", () => HttpResponse.json({ error: "internal" }, { status: 500 }))
    )

    const user = userEvent.setup()
    await renderRegister()
    await user.type(screen.getByLabelText(matchText(tAuth("fields.name"))), "Test User")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.email"))), "user@example.com")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "password123")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "password123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))

    expect(await screen.findByText(tAuth("register.error"))).toBeInTheDocument()
  })

  it("falls back to the translated error for a non-object transport failure", async () => {
    const post = vi.spyOn(api, "post").mockRejectedValueOnce("offline")
    const user = userEvent.setup()
    await renderRegister()
    await user.type(screen.getByLabelText(matchText(tAuth("fields.name"))), "Test User")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.email"))), "user@example.com")
    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "password123")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.confirmPassword"))),
      "password123"
    )

    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))

    expect(await screen.findByText(tAuth("register.error"))).toBeInTheDocument()
    post.mockRestore()
  })

  it("shows client-side validation messages without calling the API", async () => {
    const user = userEvent.setup()
    await renderRegister()

    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))

    const nameError = await screen.findByText("Name must be at least 2 characters")
    const emailError = screen.getByText("Invalid email address")
    const passwordError = screen.getByText("Password must be at least 8 characters")
    const confirmError = screen.getByText("Please confirm your password")

    const name = screen.getByLabelText(matchText(tAuth("fields.name")))
    const email = screen.getByLabelText(matchText(tAuth("fields.email")))
    const password = screen.getByLabelText(matchText(tAuth("fields.password")))
    const confirm = screen.getByLabelText(matchText(tAuth("fields.confirmPassword")))

    expect(name.closest("form")).toHaveAttribute("autocomplete", "on")
    expect(name).toHaveAttribute("aria-describedby", nameError.id)
    expect(email).toHaveAttribute("aria-describedby", emailError.id)
    expect(password).toHaveAttribute("aria-describedby", expect.stringContaining(passwordError.id))
    expect(confirm).toHaveAttribute("aria-describedby", confirmError.id)
    for (const error of [nameError, emailError, passwordError, confirmError]) {
      expect(error).toHaveAttribute("role", "alert")
    }
  })

  it("passes automated accessibility checks", async () => {
    const { container } = await renderRegister()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
