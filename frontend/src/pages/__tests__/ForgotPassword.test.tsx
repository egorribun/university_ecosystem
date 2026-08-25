import { act, fireEvent, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"
import { axe } from "jest-axe"

import ForgotPassword from "../ForgotPassword"
import i18n from "../../i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { server } from "@/tests/mocks/server"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)

const startsWithText = (text: string) => (content: string) => content.startsWith(text)

const renderForgot = () =>
  renderWithRouter({
    ui: ForgotPassword,
    path: "/forgot-password",
    initialPath: "/forgot-password",
  })

const toPlainText = (markup: string) => {
  const template = document.createElement("template")
  template.innerHTML = markup
  return template.content.textContent ?? ""
}

describe("ForgotPassword page", () => {
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
      const { container } = await renderForgot()
      const entrance = container.querySelector(".z-modal")
      expect(entrance?.getAttribute("style") ?? "").not.toMatch(/opacity:\s*0|translate/i)
    } finally {
      matchMedia.mockRestore()
    }
  })

  it("shows validation message for malformed email", async () => {
    const user = userEvent.setup()
    await renderForgot()

    const emailInput = screen.getByLabelText(startsWithText(tAuth("fields.email")))
    await user.type(emailInput, "invalid")
    await user.tab()

    const error = screen.getByText(tAuth("messages.invalidEmail"))
    expect(error).toBeInTheDocument()
    expect(error).toHaveAttribute("role", "alert")
    expect(emailInput).toHaveAttribute("aria-describedby", error.id)
    expect(emailInput.closest("form")).toHaveAttribute("autocomplete", "on")
    expect(screen.getByRole("button", { name: tAuth("forgot.sendLink") })).toBeDisabled()
  })

  it("confirms submission and starts cooldown", async () => {
    const user = userEvent.setup()
    await renderForgot()

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

  it("offers and applies a corrected email domain", async () => {
    const user = userEvent.setup()
    await renderForgot()

    const emailInput = screen.getByLabelText(startsWithText(tAuth("fields.email")))
    fireEvent.blur(emailInput)
    expect(screen.queryByText(/gmail\.com/i)).not.toBeInTheDocument()
    await user.type(emailInput, "user@gmial.com")
    await user.tab()

    const suggestion = tAuth("messages.emailSuggestion", { suggestion: "user@gmail.com" })
    expect(await screen.findByText(suggestion)).toBeInTheDocument()
    await user.click(screen.getByText(suggestion))
    expect(emailInput).toHaveValue("user@gmail.com")
    expect(screen.queryByText(suggestion)).not.toBeInTheDocument()
  })

  it("keeps the same success response when the API rejects the request", async () => {
    server.use(
      http.post("*/password/forgot", () =>
        HttpResponse.json({ detail: "not found" }, { status: 500 })
      )
    )
    const user = userEvent.setup()
    await renderForgot()

    await user.type(
      screen.getByLabelText(startsWithText(tAuth("fields.email"))),
      "user@example.com"
    )
    await user.click(screen.getByRole("button", { name: tAuth("forgot.sendLink") }))

    const successMessages = await screen.findAllByText(
      (_, element) => element?.textContent?.includes("user@example.com") ?? false
    )
    expect(successMessages.length).toBeGreaterThan(0)
    expect(
      screen.getByRole("button", { name: startsWithText(tAuth("forgot.enterAnother")) })
    ).toBeDisabled()
  })

  it("resets the request form after the resend cooldown expires", async () => {
    vi.useFakeTimers()
    try {
      await renderForgot()

      const emailInput = screen.getByLabelText(startsWithText(tAuth("fields.email")))
      fireEvent.change(emailInput, { target: { value: "user@example.com" } })
      fireEvent.blur(emailInput)
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })
      fireEvent.click(screen.getByRole("button", { name: tAuth("forgot.sendLink") }))
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })

      const retryButton = screen.getByRole("button", {
        name: startsWithText(tAuth("forgot.enterAnother")),
      })
      expect(retryButton).toBeDisabled()

      act(() => {
        vi.advanceTimersByTime(30_000)
      })

      expect(retryButton).toBeEnabled()
      expect(retryButton).not.toHaveTextContent("(0s)")
      fireEvent.click(retryButton)

      expect(screen.getByLabelText(startsWithText(tAuth("fields.email")))).toHaveValue("")
      expect(screen.getByRole("button", { name: tAuth("forgot.sendLink") })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("is accessible for assistive technologies", async () => {
    const { container } = await renderForgot()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
