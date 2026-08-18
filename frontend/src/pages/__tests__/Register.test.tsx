import { fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { axe } from "jest-axe"

import Register from "../Register"
import api from "@/api/client"
import { server } from "@/tests/mocks/server"
import i18n from "../../i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)
const matchText = (text: string) => (content: string) => content.startsWith(text)

const passwordAnalysis = vi.hoisted(() => ({
  mode: "normal" as "normal" | "throw" | "unknown",
  calls: 0,
}))

vi.mock("@zxcvbn-ts/core", () => ({
  zxcvbnOptions: { setOptions: vi.fn() },
  zxcvbn: () => {
    passwordAnalysis.calls += 1
    if (passwordAnalysis.mode === "throw") throw new Error("analysis unavailable")
    return { score: passwordAnalysis.mode === "unknown" ? 99 : 3 }
  },
}))
vi.mock("@zxcvbn-ts/language-common", () => ({}))

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
      fireEvent.mouseDown(button)
      fireEvent.mouseUp(button)
      fireEvent.mouseLeave(button)
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

    try {
      await renderRegister()

      expect(document.querySelectorAll("button[aria-label]")).toHaveLength(0)
      expect(document.querySelectorAll("button[title]")).toHaveLength(0)
    } finally {
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

    expect(await screen.findByText("Name must be at least 2 characters")).toBeInTheDocument()
    expect(screen.getByText("Invalid email address")).toBeInTheDocument()
    expect(screen.getByText("Password must be at least 8 characters")).toBeInTheDocument()
    expect(screen.getByText("Please confirm your password")).toBeInTheDocument()
  })

  it("passes automated accessibility checks", async () => {
    const { container } = await renderRegister()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
