import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import Register from "../Register"
import i18n from "../../i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@hookform/resolvers/valibot", () => ({
  valibotResolver: () => async () => ({
    values: {},
    errors: {
      email: { type: "manual" },
      full_name: { type: "manual" },
      invite_code: { type: "manual" },
      password: { type: "manual" },
      confirmPassword: { type: "manual" },
    },
  }),
}))

const tAuth = (key: string) => i18n.t(`auth:${key}`)

describe("Register defensive rendering", () => {
  it("uses the translated fallback when an email error has no message", async () => {
    const user = userEvent.setup()
    await renderWithRouter({
      ui: Register,
      path: "/register",
      initialPath: "/register",
    })

    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))

    expect(await screen.findByText(tAuth("messages.invalidFormat"))).toBeInTheDocument()
  })

  it("renders translated fallbacks for registration field errors without messages", async () => {
    const user = userEvent.setup()
    await renderWithRouter({
      ui: Register,
      path: "/register",
      initialPath: "/register",
    })

    await user.click(screen.getByRole("combobox"))
    await user.click(screen.getByRole("option", { name: tAuth("register.role.teacher") }))
    await user.click(screen.getByRole("button", { name: tAuth("actions.signUp") }))

    expect(await screen.findByText(tAuth("validation.nameMinLength"))).toBeInTheDocument()
    expect(screen.getByText(tAuth("validation.inviteCodeRequired"))).toBeInTheDocument()
    expect(screen.getByText(tAuth("validation.passwordMinLength"))).toBeInTheDocument()
    expect(screen.getByText(tAuth("validation.confirmPasswordRequired"))).toBeInTheDocument()
  })
})
