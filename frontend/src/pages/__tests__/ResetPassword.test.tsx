import { fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import ResetPassword from "../ResetPassword"
import { server } from "@/tests/mocks/server"
import i18n from "../../i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)
const matchText = (text: string) => (content: string) => content.startsWith(text)

vi.mock("zxcvbn", () => ({
  default: () => ({ score: 3, feedback: { warning: "", suggestions: [] } }),
}))

const passwordAnalysis = vi.hoisted(() => ({
  shouldThrow: false,
  suggestions: ["Add another word"],
}))
vi.mock("@zxcvbn-ts/core", () => ({
  zxcvbnOptions: { setOptions: vi.fn() },
  zxcvbn: () => {
    if (passwordAnalysis.shouldThrow) throw new Error("analysis unavailable")
    return { score: 3, feedback: { warning: "", suggestions: passwordAnalysis.suggestions } }
  },
}))
vi.mock("@zxcvbn-ts/language-common", () => ({}))

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
    passwordAnalysis.suggestions = ["Add another word"]
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

    expect(password).toHaveAttribute("type", "password")
    await user.click(passwordToggle)
    expect(password).toHaveAttribute("type", "text")
    await user.click(confirmToggle)
    expect(confirmPassword).toHaveAttribute("type", "text")

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
      expect.stringContaining("https://api.pwnedpasswords.com/range/49EFE")
    )
    fetchMock.mockRestore()
  })

  it("swallows password-analysis and breach-service failures", async () => {
    passwordAnalysis.shouldThrow = true
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"))
    const user = userEvent.setup()
    await renderWithToken()

    await user.type(screen.getByLabelText(matchText(tAuth("fields.password"))), "Password123!")
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    fetchMock.mockRestore()
  })
})
