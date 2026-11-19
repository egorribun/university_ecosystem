import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  auth: { user: { id: "ssr-stub" } as { id: string | number } | null, loading: false },
  emailChallenge: null as null | { delivery_hint: string },
  startEmail: vi.fn(),
  confirmEmail: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => state.auth }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("@/pages/settings/sections", () => ({
  EmailSection: () => null,
  PasswordSection: () => null,
}))
vi.mock("@/pages/settings/hooks", () => ({
  useEmailChange: () => ({}),
  usePasswordChange: () => ({}),
  useTotpEnrollment: () => ({ activeTotp: [] }),
  useEmailMfa: () => ({
    emailChallenge: state.emailChallenge,
    emailMfaEnabled: false,
    emailVerified: false,
    handleStartEmailMfa: state.startEmail,
    handleConfirmEmailMfa: state.confirmEmail,
  }),
}))

import { SettingsSecurity } from "../SettingsSecurity"
import { invalidateSessionEpoch, rotateBrowserSession } from "@/stores/sessionEpoch"

const view = () => <SettingsSecurity setSnackbar={vi.fn()} openStepUpFor={vi.fn()} />
const disclosure = (method: "totp" | "emailOtp") =>
  screen.getByRole("button", {
    name:
      method === "totp" ? /settings:security\.method\.totp/ : /settings:security\.method\.emailOtp/,
  })

beforeEach(() => {
  rotateBrowserSession()
  state.auth = { user: { id: "ssr-stub" }, loading: false }
  state.emailChallenge = null
  state.startEmail.mockReset()
  state.confirmEmail.mockReset()
})

describe("MFA disclosure identity readiness", () => {
  it.each([
    ["SSR identity", "ssr-stub", false],
    ["encrypted cache placeholder", "-1", false],
    ["loading account", "account-a", true],
    ["signed-out state", null, false],
  ])(
    "keeps both disclosures unavailable for %s but leaves descriptions visible",
    async (_, id, loading) => {
      const user = userEvent.setup()
      state.auth = { user: id === null ? null : { id }, loading }
      const { rerender } = render(view())
      for (const method of ["totp", "emailOtp"] as const) {
        const button = disclosure(method)
        expect(button).toBeVisible()
        expect(button).toHaveAttribute("aria-disabled", "true")
        expect(button).toHaveAttribute("aria-expanded", "false")
        expect(button.nextElementSibling).toHaveAttribute("hidden")
        await user.click(button)
        fireEvent.click(button)
        expect(button).toHaveAttribute("aria-expanded", "false")
      }
      expect(screen.getByText("settings:security.totp.description")).toBeVisible()
      expect(screen.getByText("settings:security.emailMfa.description")).toBeVisible()

      state.auth = { user: { id: "account-a" }, loading: false }
      rerender(view())
      for (const method of ["totp", "emailOtp"] as const) {
        expect(disclosure(method)).not.toHaveAttribute("aria-disabled")
        await user.click(disclosure(method))
        expect(disclosure(method)).toHaveAttribute("aria-expanded", "true")
      }
      expect(
        screen.getByRole("button", { name: "settings:security.emailMfa.verifyEmail" })
      ).toBeEnabled()
      expect(state.startEmail).not.toHaveBeenCalled()
    }
  )

  it("keeps pending disclosures keyboard reachable but blocks activation until ready", async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <>
        <button type="button">outside</button>
        {view()}
      </>
    )
    await user.tab()
    expect(screen.getByRole("button", { name: "outside" })).toHaveFocus()
    await user.tab()
    expect(disclosure("totp")).toHaveFocus()
    await user.keyboard("{Enter}")
    expect(disclosure("totp")).toHaveAttribute("aria-expanded", "false")

    state.auth = { user: { id: "account-a" }, loading: false }
    rerender(
      <>
        <button type="button">outside</button>
        {view()}
      </>
    )
    await user.click(screen.getByRole("button", { name: "outside" }))
    await user.tab()
    expect(disclosure("totp")).toHaveFocus()
    await user.keyboard("{Enter}")
    expect(disclosure("totp")).toHaveAttribute("aria-expanded", "true")
  })

  it("preserves focus and an expanded disclosure during a same-account pause", async () => {
    const user = userEvent.setup()
    state.auth = { user: { id: "account-a" }, loading: false }
    const { rerender } = render(view())
    await user.click(disclosure("emailOtp"))
    const button = disclosure("emailOtp")
    expect(button).toHaveFocus()

    state.auth.loading = true
    rerender(view())
    expect(button).toHaveFocus()
    expect(button).not.toHaveAttribute("aria-disabled")
    expect(button).toHaveAttribute("aria-expanded", "true")

    state.auth.loading = false
    rerender(view())
    expect(button).toHaveFocus()
    expect(button).not.toHaveAttribute("aria-disabled")
    expect(button).toHaveAttribute("aria-expanded", "true")
  })

  it("retains the open form and partial code through loading for the same account", async () => {
    const user = userEvent.setup()
    state.auth = { user: { id: "account-a" }, loading: false }
    state.emailChallenge = { delivery_hint: "example" }
    const { rerender } = render(
      <>
        <button type="button">outside</button>
        {view()}
      </>
    )
    await user.click(disclosure("emailOtp"))
    const firstDigit = screen.getAllByRole("textbox")[0]!
    await user.type(firstDigit, "1")
    expect(firstDigit).toHaveValue("1")

    state.auth.loading = true
    rerender(
      <>
        <button type="button">outside</button>
        {view()}
      </>
    )
    expect(disclosure("emailOtp")).not.toHaveAttribute("aria-disabled")
    expect(disclosure("emailOtp")).toHaveAttribute("aria-expanded", "true")
    expect(firstDigit).toBeDisabled()
    expect(firstDigit).toHaveValue("1")
    await user.click(screen.getByRole("button", { name: "outside" }))

    state.auth.loading = false
    rerender(
      <>
        <button type="button">outside</button>
        {view()}
      </>
    )
    expect(disclosure("emailOtp")).not.toHaveAttribute("aria-disabled")
    expect(disclosure("emailOtp")).toHaveAttribute("aria-expanded", "true")
    expect(firstDigit).toBeEnabled()
    expect(firstDigit).toHaveValue("1")
    expect(screen.getByRole("button", { name: "outside" })).toHaveFocus()
    expect(state.confirmEmail).not.toHaveBeenCalled()
  })

  it("allows collapse while pending, then blocks reopening until ready without losing the code", async () => {
    const user = userEvent.setup()
    state.auth = { user: { id: "account-a" }, loading: false }
    state.emailChallenge = { delivery_hint: "example" }
    const { rerender } = render(view())
    await user.click(disclosure("emailOtp"))
    const firstDigit = screen.getAllByRole("textbox")[0]!
    await user.type(firstDigit, "1")

    state.auth.loading = true
    rerender(view())
    const button = disclosure("emailOtp")
    expect(button).not.toHaveAttribute("aria-disabled")
    expect(button).toHaveAttribute("aria-expanded", "true")
    await user.click(button)
    expect(button).toHaveFocus()
    expect(button).toHaveAttribute("aria-expanded", "false")
    expect(button).toHaveAttribute("aria-disabled", "true")
    expect(firstDigit.isConnected).toBe(true)
    expect(firstDigit).toHaveValue("1")
    expect(screen.queryAllByRole("textbox")).toHaveLength(0)
    await user.keyboard("{Enter}")
    fireEvent.click(button)
    expect(button).toHaveAttribute("aria-expanded", "false")

    state.auth.loading = false
    rerender(view())
    expect(button).toHaveFocus()
    expect(button).not.toHaveAttribute("aria-disabled")
    await user.keyboard("{Enter}")
    expect(button).toHaveAttribute("aria-expanded", "true")
    expect(screen.getAllByRole("textbox")[0]).toBe(firstDigit)
    expect(firstDigit).toHaveValue("1")
    expect(state.confirmEmail).not.toHaveBeenCalled()
  })

  it("also allows collapsing the authenticator disclosure while pending", async () => {
    const user = userEvent.setup()
    state.auth = { user: { id: "account-a" }, loading: false }
    const { rerender } = render(view())
    await user.click(disclosure("totp"))
    state.auth.loading = true
    rerender(view())
    const button = disclosure("totp")
    expect(button).not.toHaveAttribute("aria-disabled")
    await user.click(button)
    expect(button).toHaveAttribute("aria-expanded", "false")
    expect(button).toHaveAttribute("aria-disabled", "true")
  })

  it.each(["account", "epoch"] as const)("drops the open form on %s change", async (change) => {
    const user = userEvent.setup()
    state.auth = { user: { id: "account-a" }, loading: false }
    state.emailChallenge = { delivery_hint: "example" }
    const { rerender } = render(view())
    await user.click(disclosure("emailOtp"))
    const firstDigit = screen.getAllByRole("textbox")[0]!
    await user.type(firstDigit, "1")
    if (change === "account") {
      state.auth = { user: { id: "account-b" }, loading: false }
      rerender(view())
    } else {
      await act(async () => {
        invalidateSessionEpoch()
        await Promise.resolve()
      })
    }
    expect(firstDigit.isConnected).toBe(false)
    expect(disclosure("emailOtp")).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryAllByRole("textbox")).toHaveLength(0)
    await user.click(disclosure("emailOtp"))
    expect(screen.getAllByRole("textbox")[0]).toHaveValue("")
    expect(state.confirmEmail).not.toHaveBeenCalled()
  })

  it("disables the new disclosure after a foreign session generation appears", async () => {
    const user = userEvent.setup()
    state.auth = { user: { id: "account-a" }, loading: false }
    state.emailChallenge = { delivery_hint: "example" }
    render(view())
    await user.click(disclosure("emailOtp"))
    const oldDigit = screen.getAllByRole("textbox")[0]!
    await user.type(oldDigit, "1")

    await act(async () => {
      localStorage.setItem(
        "ecosystem.session.generation.v1",
        JSON.stringify({ nonce: "other-session", hash: null })
      )
      window.dispatchEvent(new StorageEvent("storage", { key: "ecosystem.session.generation.v1" }))
      await Promise.resolve()
    })
    expect(oldDigit.isConnected).toBe(false)
    expect(disclosure("emailOtp")).toHaveAttribute("aria-expanded", "false")
    expect(disclosure("emailOtp")).toHaveAttribute("aria-disabled", "true")
    fireEvent.click(disclosure("emailOtp"))
    expect(disclosure("emailOtp")).toHaveAttribute("aria-expanded", "false")
    expect(state.confirmEmail).not.toHaveBeenCalled()
  })

  it("hydrates the pending disclosures without an accessibility-state mismatch", async () => {
    const container = document.createElement("div")
    container.innerHTML = renderToString(view())
    document.body.append(container)
    const error = vi.spyOn(console, "error").mockImplementation(() => {})
    let root: ReturnType<typeof hydrateRoot> | undefined
    try {
      await act(async () => {
        root = hydrateRoot(container, view())
        await Promise.resolve()
      })
      expect(error).not.toHaveBeenCalled()
      expect(disclosure("totp")).toHaveAttribute("aria-disabled", "true")
      expect(disclosure("emailOtp")).toHaveAttribute("aria-disabled", "true")
    } finally {
      await act(async () => {
        root?.unmount()
      })
      container.remove()
      error.mockRestore()
    }
  })
})
