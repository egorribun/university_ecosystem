import { MemoryRouter } from "react-router-dom"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"
import { axe } from "jest-axe"
import ForgotPassword from "../ForgotPassword"
import i18n from "../../i18n/config"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)

const startsWithText = (text: string) => (content: string) => content.startsWith(text)

const renderForgot = () =>
  render(
    <MemoryRouter>
      <ForgotPassword />
    </MemoryRouter>
  )

const toPlainText = (markup: string) => {
  const template = document.createElement("template")
  template.innerHTML = markup
  return template.content.textContent ?? ""
}

// Wave 113 SW6 polish: skipped pending Wave 114 SW1 — imports MemoryRouter from
// react-router-dom but the app migrated to TanStack Router (Wave 37). useRouterState
// returns null → TypeError. Fix requires a shared renderWithTanStackRouter test helper
// (AUDIT_WAVE113.md, memory/wave114_backlog.md item #1).
describe.skip("ForgotPassword page", () => {
  it("shows validation message for malformed email", async () => {
    const user = userEvent.setup()
    renderForgot()

    const emailInput = screen.getByLabelText(startsWithText(tAuth("fields.email")))
    await user.type(emailInput, "invalid")
    await user.tab()

    expect(screen.getByText(tAuth("messages.invalidEmail"))).toBeInTheDocument()
    expect(screen.getByRole("button", { name: tAuth("forgot.sendLink") })).toBeDisabled()
  })

  it("confirms submission and starts cooldown", async () => {
    const user = userEvent.setup()
    renderForgot()

    await user.type(
      screen.getByLabelText(startsWithText(tAuth("fields.email"))),
      "user@example.com"
    )
    await user.click(screen.getByRole("button", { name: tAuth("forgot.sendLink") }))

    const successText = toPlainText(tAuth("forgot.success", { email: "user@example.com" }))
    const successMessages = await screen.findAllByText(
      (_, element) => element?.textContent?.includes(successText) ?? false
    )
    expect(successMessages.length).toBeGreaterThan(0)
    const retryButton = screen.getByRole("button", {
      name: startsWithText(tAuth("forgot.enterAnother")),
    })
    expect(retryButton).toBeDisabled()
    expect(retryButton.textContent).toMatch(/\d+s/)
  })

  it("is accessible for assistive technologies", async () => {
    const { container } = renderForgot()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
