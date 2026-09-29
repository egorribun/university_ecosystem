import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, it, vi } from "vitest"
import { axe } from "jest-axe"

import ForgotPassword from "../ForgotPassword"
import i18n from "../../i18n/config"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { server } from "@/tests/mocks/server"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)

const startsWithText = (text: string) => (content: string) => content.startsWith(text)

const renderForgot = async () => {
  const result = await renderWithRouter({
    ui: ForgotPassword,
    path: "/forgot-password",
    initialPath: "/forgot-password",
    // This is a public form; mounting the real AuthProvider only starts an
    // unrelated `/users/me` request and can race form assertions in jsdom.
    authProvider: false,
  })
  // React Hook Form performs an asynchronous initial validation pass. Flush
  // it before callers begin assertions so the update is inside act().
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
  return result
}

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
      const { container } = await renderForgot()
      await user.type(
        screen.getByLabelText(startsWithText(tAuth("fields.email"))),
        "user@example.com"
      )
      await user.click(screen.getByRole("button", { name: tAuth("forgot.sendLink") }))

      await screen.findByText(tAuth("forgot.successSent"))
      expect(container.querySelector(".space-y-6.pt-4")?.getAttribute("style") ?? "").not.toMatch(
        /opacity:\s*0|scale/i
      )
    } finally {
      matchMedia.mockRestore()
    }
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

  it("shows the email suggestion without an entrance transform under reduced motion", async () => {
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
      const { container } = await renderForgot()
      const emailInput = screen.getByLabelText(startsWithText(tAuth("fields.email")))
      await user.type(emailInput, "user@gmial.com")
      await user.tab()

      await screen.findByText(tAuth("messages.emailSuggestion", { suggestion: "user@gmail.com" }))
      const suggestionMotion = container.querySelector("[data-testid='email-suggestion-motion']")
      expect(suggestionMotion?.getAttribute("style") ?? "").not.toMatch(/opacity:\s*0|translate/i)
    } finally {
      matchMedia.mockRestore()
    }
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
      await act(async () => {
        fireEvent.change(emailInput, { target: { value: "user@example.com" } })
        fireEvent.blur(emailInput)
        await Promise.resolve()
        await Promise.resolve()
      })
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: tAuth("forgot.sendLink") }))
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
      await act(async () => {
        fireEvent.click(retryButton)
      })

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

describe("ForgotPassword behaviour details", () => {
  const emailInput = () => screen.getByLabelText(startsWithText(tAuth("fields.email")))
  const sendButton = () => screen.getByRole("button", { name: tAuth("forgot.sendLink") })
  const retryButton = () =>
    screen.getByRole("button", { name: startsWithText(tAuth("forgot.enterAnother")) })
  const motionView = (element: Element | null) => element?.closest("[style]") ?? null
  const suggestionText = (suggestion: string) => tAuth("messages.emailSuggestion", { suggestion })
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
  // Synchronous events keep these helpers usable under fake timers.
  const changeEmail = async (email: string, { blur = false } = {}) => {
    await act(async () => {
      fireEvent.change(emailInput(), { target: { value: email } })
      if (blur) fireEvent.blur(emailInput())
      await Promise.resolve()
      await Promise.resolve()
    })
  }
  const clickSend = async () => {
    await act(async () => {
      fireEvent.click(sendButton())
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("sends only the entered address to the reset endpoint", async () => {
    const payloads: unknown[] = []
    server.use(
      http.post("*/password/forgot", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ ok: true })
      })
    )
    const user = userEvent.setup()
    await renderForgot()

    await user.type(emailInput(), "user@example.com")
    await user.click(sendButton())

    await screen.findByText(tAuth("forgot.successSent"))
    expect(payloads).toEqual([{ email: "user@example.com" }])
  })

  it("explains the request before it is sent and shows no hint for a valid address", async () => {
    const user = userEvent.setup()
    await renderForgot()

    expect(screen.getByText(tAuth("forgot.subtitle"))).toBeInTheDocument()
    expect(screen.queryByText(tAuth("forgot.successSent"))).not.toBeInTheDocument()

    await user.type(emailInput(), "user@example.com")
    expect(emailInput()).toHaveAttribute("aria-invalid", "false")
    expect(emailInput()).not.toHaveAttribute("aria-describedby")
    expect(sendButton()).toBeEnabled()
  })

  it("validates the address while it is typed", async () => {
    const user = userEvent.setup()
    await renderForgot()

    await user.type(emailInput(), "invalid")

    expect(screen.getByText(tAuth("messages.invalidEmail"))).toBeInTheDocument()
    expect(emailInput()).toHaveFocus()
  })

  it("validates an untouched address when the field loses focus", async () => {
    await renderForgot()

    await act(async () => {
      fireEvent.blur(emailInput())
    })

    expect(await screen.findByText(tAuth("messages.invalidEmail"))).toBeInTheDocument()
  })

  it("keeps the offered correction when the address is cleared", async () => {
    const user = userEvent.setup()
    await renderForgot()

    await user.type(emailInput(), "user@gmial.com")
    await user.tab()
    expect(await screen.findByText(suggestionText("user@gmail.com"))).toBeInTheDocument()

    await user.clear(emailInput())
    await user.tab()

    expect(screen.getByText(suggestionText("user@gmail.com"))).toBeInTheDocument()
  })

  it("re-validates the address when a suggested correction is applied", async () => {
    const user = userEvent.setup()
    await renderForgot()

    await user.type(emailInput(), "user@gmail.c")
    await user.tab()
    expect(screen.getByText(tAuth("messages.invalidEmail"))).toBeInTheDocument()

    await user.click(await screen.findByText(suggestionText("user@gmail.com")))

    expect(emailInput()).toHaveValue("user@gmail.com")
    await waitFor(() =>
      expect(screen.queryByText(tAuth("messages.invalidEmail"))).not.toBeInTheDocument()
    )
    expect(sendButton()).toBeEnabled()
  })

  it("locks the address while the request is in flight", async () => {
    let finish!: () => void
    server.use(
      http.post(
        "*/password/forgot",
        () =>
          new Promise<Response>((resolve) => {
            finish = () => resolve(HttpResponse.json({ ok: true }))
          })
      )
    )
    const user = userEvent.setup()
    await renderForgot()

    await user.type(emailInput(), "user@example.com")
    await user.click(sendButton())

    await waitFor(() => expect(emailInput()).toBeDisabled())
    await act(async () => finish())
    expect(await screen.findByText(tAuth("forgot.successSent"))).toBeInTheDocument()
  })

  it("confirms the request with the highlighted address and a way back to sign in", async () => {
    const user = userEvent.setup()
    await renderForgot()

    await user.type(emailInput(), "user@example.com")
    await user.click(sendButton())

    const address = await screen.findByText("user@example.com")
    expect(address).toHaveClass("font-extrabold", "text-text-primary")
    expect(address.parentElement).toHaveTextContent(
      toPlainText(tAuth("forgot.success", { email: "user@example.com" }))
    )
    expect(screen.getByText(tAuth("forgot.successHint"))).toBeInTheDocument()
    expect(screen.getByRole("link", { name: tAuth("actions.backToLogin") })).toBeInTheDocument()
    expect(screen.queryByText(tAuth("forgot.subtitle"))).not.toBeInTheDocument()
  })

  it("counts the resend cooldown down one second at a time", async () => {
    vi.useFakeTimers()
    await renderForgot()
    await changeEmail("user@example.com")
    await clickSend()

    expect(retryButton()).toHaveTextContent(/\(30s\)$/)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(retryButton()).toHaveTextContent(/\(29s\)$/)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(retryButton()).toHaveTextContent(/\(28s\)$/)

    act(() => {
      vi.advanceTimersByTime(28_000)
    })
    expect(retryButton()).toBeEnabled()
    expect(retryButton()).toHaveAccessibleName(tAuth("forgot.enterAnother"))
  })

  it("does not run a countdown timer while no cooldown is active", async () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval")
    const user = userEvent.setup()
    await renderForgot()

    await user.type(emailInput(), "user@example.com")

    expect(setIntervalSpy).not.toHaveBeenCalled()
  })

  it("drops a pending correction when another address is requested", async () => {
    vi.useFakeTimers()
    await renderForgot()
    await changeEmail("user@gmial.com", { blur: true })
    expect(screen.getByText(suggestionText("user@gmail.com"))).toBeInTheDocument()

    await clickSend()
    act(() => {
      vi.advanceTimersByTime(30_000)
    })
    await act(async () => {
      fireEvent.click(retryButton())
    })

    expect(emailInput()).toHaveValue("")
    expect(screen.queryByText(suggestionText("user@gmail.com"))).not.toBeInTheDocument()
  })

  it("starts every view hidden and offset when motion is allowed", async () => {
    const user = userEvent.setup()
    await renderForgot()

    const formView = motionView(sendButton())
    expect(formView).toHaveStyle({ opacity: "0" })
    expect(motionView(formView!.parentElement)).toHaveStyle({
      opacity: "0",
      transform: "translateY(20px)",
    })

    await user.type(emailInput(), "user@gmial.com")
    await user.tab()
    expect(screen.getByTestId("email-suggestion-motion")).toHaveStyle({
      opacity: "0",
      transform: "translateX(-10px)",
    })

    await user.clear(emailInput())
    await user.type(emailInput(), "user@example.com")
    await user.click(sendButton())

    const successView = motionView(await screen.findByText(tAuth("forgot.successHint")))
    expect(successView).toHaveStyle({ opacity: "0", transform: "scale(0.95)" })
  })

  it("renders every view in its final state under reduced motion", async () => {
    mockReducedMotion()
    const user = userEvent.setup()
    await renderForgot()

    const formView = motionView(sendButton())
    expect(formView).toHaveStyle({ opacity: "1" })
    expect(motionView(formView!.parentElement)).toHaveStyle({ opacity: "1", transform: "none" })

    await user.type(emailInput(), "user@gmial.com")
    await user.tab()
    expect(screen.getByTestId("email-suggestion-motion")).toHaveStyle({
      opacity: "1",
      transform: "none",
    })

    await user.clear(emailInput())
    await user.type(emailInput(), "user@example.com")
    await user.click(sendButton())

    const successView = motionView(await screen.findByText(tAuth("forgot.successHint")))
    expect(successView).toHaveStyle({ opacity: "1", transform: "none" })
  })
})
