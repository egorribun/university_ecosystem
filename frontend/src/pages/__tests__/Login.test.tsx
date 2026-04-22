import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { axe } from "jest-axe"
import { QueryClient } from "@tanstack/react-query"

import Login from "../Login"
import { server } from "@/tests/mocks/server"
import { testUser } from "@/tests/mocks/handlers"
import i18n from "../../i18n/config"
import { createTestQueryClient, renderWithRouter } from "@/tests/helpers/renderWithRouter"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)
const matchText = (text: string) => (content: string) => content.startsWith(text)

const clients: QueryClient[] = []

const renderLogin = () => {
  const client = createTestQueryClient()
  clients.push(client)
  return renderWithRouter({
    ui: Login,
    path: "/login",
    initialPath: "/login",
    extraRoutes: [{ path: "/dashboard", Component: () => <div>Welcome!</div> }],
    queryClient: client,
  })
}

describe("Login page", () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
  })

  afterEach(() => {
    localStorage.clear()
    clients.splice(0).forEach((client) => client.clear())
  })

  it("blocks submission for invalid email", async () => {
    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "invalid")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    expect(await screen.findByText(tAuth("messages.invalidEmail"))).toBeInTheDocument()
  })

  it("submits credentials and redirects on success", async () => {
    const captured: Array<{ username: string | null; password: string | null }> = []
    server.use(
      http.post("*/auth/login", async ({ request }) => {
        const body = await request.text()
        const params = new URLSearchParams(body)
        captured.push({ username: params.get("username"), password: params.get("password") })
        return HttpResponse.json({
          access_token: "token-123",
          token_type: "bearer",
          user: testUser,
          session: { signing_key: "test-key-123" },
        })
      })
    )

    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "user@example.com")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByLabelText(tAuth("actions.showPassword")))
    await user.click(screen.getByLabelText(tAuth("actions.showPassword")))
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument())
    expect(captured).toEqual([{ username: "user@example.com", password: "secret123" }])
  }, 15000)

  it("returns server errors to the user", async () => {
    server.use(
      http.post("*/auth/login", () =>
        HttpResponse.json({ detail: tAuth("login.error") }, { status: 401 })
      )
    )

    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "user@example.com")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    expect(await screen.findByText(tAuth("login.error"))).toBeInTheDocument()
  })

  it("shows lockout messaging with retry information", async () => {
    server.use(
      http.post("*/auth/login", () =>
        HttpResponse.json(
          {
            detail:
              "Too many failed attempts. Your account is temporarily locked. Try again in 2 minutes.",
          },
          { status: 423, headers: { "Retry-After": "120" } }
        )
      )
    )

    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "user@example.com")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    const message = await screen.findByText(
      (content) =>
        content.includes("temporarily locked") && content.includes("Try again in 2 minutes")
    )
    expect(message).toBeInTheDocument()
  })

  it("transitions to MFA verification when additional challenges are required", async () => {
    server.use(
      http.get("*/users/me", () =>
        HttpResponse.json({
          ...testUser,
          email: "mfa@example.com",
          mfa_required: true,
          mfa_default_method: "totp",
        })
      )
    )

    const user = userEvent.setup()
    await renderLogin()

    // Wait for initial auth check to complete
    await waitFor(() => expect(screen.queryByText(/loading|загрузка/i)).not.toBeInTheDocument(), {
      timeout: 1000,
    }).catch(() => {}) // Ignore if no loading indicator

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.email")), {
        selector: 'input[type="email"]',
      }),
      "mfa@example.com"
    )

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "Password123"
    )

    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    await screen.findByText(tAuth("mfa.verifyTitle"))

    const otpInputs = await screen.findAllByRole("textbox", { name: /digit/i })
    await user.click(otpInputs[0]!)
    await user.keyboard("123456")
    // OtpEntry auto-submits on complete, so we just wait for the result
    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument())
  }, 15000)

  it("displays errors for invalid OTP attempts and allows retry", async () => {
    server.use(
      http.get("*/users/me", () =>
        HttpResponse.json({
          ...testUser,
          email: "mfa@example.com",
          mfa_required: true,
          mfa_default_method: "totp",
        })
      )
    )

    const user = userEvent.setup()
    await renderLogin()

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.email")), {
        selector: 'input[type="email"]',
      }),
      "mfa@example.com"
    )

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "Password123"
    )

    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    await screen.findByText(tAuth("mfa.verifyTitle"))

    const otpInputs = await screen.findAllByRole("textbox", { name: /digit/i })
    await user.click(otpInputs[0]!)
    await user.keyboard("000000")
    // OtpEntry auto-submits on complete
    await screen.findByText(/Invalid verification code|Неверный код/i)

    // After error, user clears input and types new code
    // Note: OtpEntry component auto-clears on error via useEffect, but mfaError prop stays set
    // which blocks auto-submit. We need to wait for the input to be cleared, then type new code
    // and click the button manually since auto-submit is blocked
    await waitFor(() => expect(otpInputs[0]!).toHaveValue(""))
    await user.click(otpInputs[0]!)
    await user.keyboard("123456")
    // Must click button since error prop blocks auto-submit
    await user.click(screen.getByRole("button", { name: /Verify|Подтвердить/i }))
    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument())
  }, 15000)

  it("meets basic accessibility requirements", async () => {
    const { container } = await renderLogin()
    // Wait for AuthProvider and Login component to settle (initial check/loading)
    await waitFor(() => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument())

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
