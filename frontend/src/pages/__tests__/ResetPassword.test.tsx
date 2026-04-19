import { screen, waitFor } from "@testing-library/react"
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
})
