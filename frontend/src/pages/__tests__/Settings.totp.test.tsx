import { type PropsWithChildren } from "react"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { beforeEach, describe, expect, it, vi } from "vitest"
import Settings from "@/pages/Settings"
import { AuthContext } from "@/contexts/AuthContext"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

import type { MfaTotpEnrollment } from "@/types/Mfa"
import { useAuthStore } from "@/stores/useAuthStore"
import { createQueryClient } from "@/app/queryClient"
import { resetTestMfa, testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import { http, HttpResponse } from "msw"

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: () => ({
    topicKeys: [],
    topicState: {},
    pushSupported: false,
    notificationPermission: "default" as NotificationPermission,
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "",
    selectedTopicsDescription: "",
    enableNotifications: vi.fn(),
    disableNotifications: vi.fn(),
    handleTopicToggle: () => () => {},
    safariIOS: false,
    safariGuideUrl: "#",
  }),
}))

const createPendingEnrollment = (
  overrides: Partial<MfaTotpEnrollment> = {}
): MfaTotpEnrollment => ({
  id: overrides.id ?? `uuid-${Math.floor(Math.random() * 10_000) + 1}`,
  user_id: overrides.user_id ?? testUser.id,
  label: overrides.label ?? "Pending authenticator",
  is_active: overrides.is_active ?? false,
  confirmed_at: overrides.confirmed_at ?? null,
  revoked_at: overrides.revoked_at ?? null,
  created_at: overrides.created_at ?? new Date().toISOString(),
})

const renderSettings = async () => {
  const queryClient = createQueryClient()

  const TestAuthProvider = ({ children }: PropsWithChildren) => {
    const mockLogout = vi.fn()
    const mockSetUser = vi.fn()
    return (
      <AuthContext.Provider
        value={{
          login: vi.fn(),
          loginWithPasskey: vi.fn(),
          logout: mockLogout,
          setUser: mockSetUser,
          refresh: vi.fn(),
          submitMfaChallenge: vi.fn(),
          requireMfa: vi.fn(),
          resetEtagCache: vi.fn(),
          authOperation: false,
        }}
      >
        {children}
      </AuthContext.Provider>
    )
  }

  const WrappedSettings = () => (
    <ThemeProvider>
      <TestAuthProvider>
        <Settings />
      </TestAuthProvider>
    </ThemeProvider>
  )

  const result = await renderWithRouter({
    ui: WrappedSettings,
    path: "/settings",
    initialPath: "/settings",
    queryClient,
  })

  return { ...result, queryClient }
}

const matchTotpAddButton = /Set up authenticator app|Подключить приложение/i
const matchSecurityTab = /Security|Безопасность/i
const matchSecurityHeading = /Security & MFA|Безопасность и MFA/i
const matchTotpSection = /^Authenticator app|^Приложение для аутентификации/i

const openTotpAccordion = async (user: ReturnType<typeof userEvent.setup>) => {
  const accordion = await screen.findByRole("button", { name: matchTotpSection })
  if (accordion.getAttribute("aria-expanded") !== "true") {
    await user.click(accordion)
  }
  await waitFor(() => expect(accordion).toHaveAttribute("aria-expanded", "true"))
}

describe("Settings TOTP enrollment", () => {
  beforeEach(() => {
    resetTestMfa()
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
    useAuthStore.setState({
      user: JSON.parse(JSON.stringify(testUser)),
      loading: false,
      pendingMfa: null,
      authOperation: false,
    })
  })

  it("starts and completes a new TOTP enrollment", async () => {
    const user = userEvent.setup()
    await renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchSecurityTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await openTotpAccordion(user)
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    await screen.findByText(/Finish setup|Завершите настройку/i)

    const manualCode = await screen.findByLabelText(/Manual code|Ручной код/i)
    expect((manualCode as HTMLInputElement).value).toBe("JBSWY3DPEHJK")

    const allInputs = await screen.findAllByRole("textbox")
    const otpInputs = allInputs.filter((input) => input.getAttribute("maxLength") === "1")
    expect(otpInputs).toHaveLength(6)
    await waitFor(() => expect(otpInputs[0]).not.toBeDisabled())

    for (let i = 0; i < 6; i++) {
      await user.type(otpInputs[i]!, (i + 1).toString())
    }

    await waitFor(
      async () => {
        const matches = await screen.findAllByText(
          /Authenticator app connected|Приложение-аутентификатор подключено/i
        )
        expect(matches.length).toBeGreaterThan(0)
      },
      { timeout: 5000 }
    )

    await waitFor(
      () => {
        const matches = screen.queryAllByText(/Authenticator|Приложение/i)
        expect(matches.length).toBeGreaterThan(2) // 1 in title, 1 in section, 1 in enrollment
      },
      { timeout: 7000 }
    )
  })

  it("surfaces server errors when confirmation fails", async () => {
    server.use(
      http.post("*/auth/mfa/totp/confirm", () =>
        HttpResponse.json({ detail: "Invalid verification code" }, { status: 400 })
      )
    )

    const user = userEvent.setup()
    await renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchSecurityTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await openTotpAccordion(user)
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    await screen.findByText(/Finish setup|Завершите настройку/i)

    const allInputs = await screen.findAllByRole("textbox")
    const otpInputs = allInputs.filter((input) => input.getAttribute("maxLength") === "1")
    expect(otpInputs).toHaveLength(6)
    await waitFor(() => expect(otpInputs[0]).not.toBeDisabled())

    for (let i = 0; i < 6; i++) {
      await user.type(otpInputs[i]!, "0")
    }

    const alerts = await screen.findAllByText(/Invalid verification code/i)
    expect(alerts.length).toBeGreaterThan(0)
    expect(screen.getByText(/Finish setup|Завершите настройку/i)).toBeVisible()
  })

  it("cancels a pending TOTP enrollment", async () => {
    const user = userEvent.setup()
    await renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchSecurityTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await openTotpAccordion(user)
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    await screen.findByText(/Finish setup|Завершите настройку/i)
    await user.click(
      await screen.findByRole("button", { name: /Cancel setup|Отменить настройку/i })
    )

    await waitFor(() =>
      expect(screen.queryByText(/Finish setup|Завершите настройку/i)).not.toBeInTheDocument()
    )
    expect(
      await screen.findByRole("button", { name: /Set up authenticator app|Настроить приложение/i })
    ).toBeEnabled()
  })

  it("shows an error if pending cancellation fails", async () => {
    server.use(
      http.delete("*/auth/mfa/totp/pending/*", () => {
        return HttpResponse.json({ detail: "Mock Server Error" }, { status: 500 })
      })
    )

    const user = userEvent.setup()
    await renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchSecurityTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await openTotpAccordion(user)
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    await screen.findByText(/Finish setup|Завершите настройку/i)
    await user.click(
      await screen.findByRole("button", { name: /Cancel setup|Отменить настройку/i })
    )

    await waitFor(async () => {
      const errors = await screen.findAllByText(/Mock Server Error/i)
      expect(errors.length).toBeGreaterThanOrEqual(1)
    })
    expect(screen.getByText(/Finish setup|Завершите настройку/i)).toBeVisible()
  })

  it("shows pending enrollments only inside the QR panel", async () => {
    const pendingEnrollment = createPendingEnrollment()
    testUser.totp_enrollments = [pendingEnrollment]
    useAuthStore.setState({ user: JSON.parse(JSON.stringify(testUser)) })

    const user = userEvent.setup()
    await renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchSecurityTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await openTotpAccordion(user)

    await screen.findByText(/Finish setup|Завершите настройку/i)
    expect(
      screen.getByText(
        /Enter the verification code before leaving|Введите код из приложения перед уходом/i
      )
    ).toBeVisible()
    expect(screen.queryByRole("button", { name: /^(Remove|Удалить)$/i })).not.toBeInTheDocument()
  })

  it("disables additional authenticator enrollment when one is already confirmed", async () => {
    const activeEnrollment = createPendingEnrollment({
      label: "Main authenticator",
      is_active: true,
      confirmed_at: new Date().toISOString(),
    })
    testUser.totp_enrollments = [activeEnrollment]
    testUser.mfa_default_method = "totp"
    useAuthStore.setState({ user: JSON.parse(JSON.stringify(testUser)) })

    const user = userEvent.setup()
    await renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchSecurityTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await openTotpAccordion(user)

    expect(
      await screen.findByText((_, element) => {
        const hasText = (node: Element) =>
          node.textContent?.match(
            /Only one authenticator app can be connected at a time|Можно подключить только одно приложение/i
          )
        const nodeHasText = hasText(element as Element)
        const childrenDontHaveText = Array.from(element?.children || []).every(
          (child) => !hasText(child)
        )
        return Boolean(nodeHasText && childrenDontHaveText)
      })
    ).toBeVisible()
    expect(
      screen.queryByRole("button", { name: /Set up authenticator app|Настроить приложение/i })
    ).not.toBeInTheDocument()
  })
})
