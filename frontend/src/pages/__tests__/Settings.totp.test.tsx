import { useState, type PropsWithChildren } from "react"
import { MemoryRouter } from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { CssVarsProvider } from "@mui/material/styles"
import { beforeEach, describe, expect, it, vi } from "vitest"
import Settings from "@/pages/Settings"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { AuthContext } from "@/contexts/AuthContext"
import type { User } from "@/types/User"
import type { MfaTotpEnrollment } from "@/types/Mfa"
import theme from "@/theme"
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

const createBaseUser = (): User => ({
  ...testUser,
  totp_enrollments: [],
  mfa_default_method: null,
  mfa_last_verified_at: null,
})

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

type RenderSettingsOptions = {
  initialUser?: User
}

const renderSettings = (options?: RenderSettingsOptions) => {
  const queryClient = createQueryClient()
  const initialUser = options?.initialUser ?? createBaseUser()

  const TestAuthProvider = ({ children }: PropsWithChildren) => {
    const [user, setUser] = useState<User | null>(initialUser)
    return (
      <AuthContext.Provider
        value={{
          user,
          setUser,
          logout: vi.fn(),
          login: vi.fn(),
          loginWithPasskey: vi.fn(),
          refresh: vi.fn(),
          isAuth: true,
          loading: false,
          pendingMfa: null,
          submitMfaChallenge: vi.fn(),
          requireMfa: vi.fn(),
          resetEtagCache: vi.fn(),
        }}
      >
        {children}
      </AuthContext.Provider>
    )
  }

  const result = render(
    <MemoryRouter initialEntries={["/settings"]}>
      <QueryClientProvider client={queryClient}>
        <CssVarsProvider theme={theme}>
          <LanguageProvider>
            <TestAuthProvider>
              <Settings />
            </TestAuthProvider>
          </LanguageProvider>
        </CssVarsProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )

  return { ...result, queryClient }
}

const matchTotpAddButton = /Set up authenticator app|Настроить приложение/i
const matchTotpSubmit = /Verify|Подтвердить/i
const matchAccountTab = /Account|Аккаунт/i
const matchSecurityHeading = /Security & MFA|Безопасность и MFA/i

describe("Settings TOTP enrollment", () => {
  beforeEach(() => {
    resetTestMfa()
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
  })

  it("starts and completes a new TOTP enrollment", async () => {
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchAccountTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    await screen.findByText(/Finish setup|Завершите настройку/i)

    const manualCode = await screen.findByLabelText(/Manual code|Ручной код/i)
    expect((manualCode as HTMLInputElement).value).toBe("JBSWY3DPEHJK")

    const otpInput = screen.getByLabelText(/Authenticator code|Код из приложения/i)
    await user.type(otpInput, "123456")
    // OtpEntry auto-submits when 6 digits are entered

    await waitFor(() =>
      expect(
        screen.getByText(/Authenticator app connected|Приложение-аутентификатор подключено/i)
      ).toBeVisible()
    )

    await waitFor(() => expect(screen.getByText(/Authenticator 1|Аутентификатор 1/i)).toBeVisible())
  })

  it("surfaces server errors when confirmation fails", async () => {
    server.use(
      http.post("*/auth/mfa/totp/confirm", () =>
        HttpResponse.json({ detail: "Invalid verification code" }, { status: 400 })
      )
    )

    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchAccountTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    const otpInput = await screen.findByLabelText(/Authenticator code|Код из приложения/i)
    await user.type(otpInput, "000000")
    // OtpEntry auto-submits when 6 digits are entered

    const errorMessages = await screen.findAllByText(/Invalid verification code/i)
    expect(errorMessages.length).toBeGreaterThan(0)
    expect(screen.getByText(/Finish setup|Завершите настройку/i)).toBeVisible()
  })

  it("cancels a pending TOTP enrollment", async () => {
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchAccountTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    await screen.findByText(/Finish setup|Завершите настройку/i)
    await user.click(
      await screen.findByRole("button", { name: /Cancel setup|Отменить настройку/i })
    )

    await waitFor(() =>
      expect(screen.queryByText(/Finish setup|Завершите настройку/i)).not.toBeInTheDocument()
    )
    expect(await screen.findByRole("button", { name: matchTotpAddButton })).toBeEnabled()
  })

  it("shows an error if pending cancellation fails", async () => {
    server.use(
      http.delete("*/auth/mfa/totp/pending/:id", () => HttpResponse.json({}, { status: 500 }))
    )

    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole("tab", { name: matchAccountTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })
    await user.click(await screen.findByRole("button", { name: matchTotpAddButton }))

    await screen.findByText(/Finish setup|Завершите настройку/i)
    await user.click(
      await screen.findByRole("button", { name: /Cancel setup|Отменить настройку/i })
    )

    const errorMessages = await screen.findAllByText(
      /Couldn't cancel authenticator setup|Не удалось отменить настройку/i
    )
    expect(errorMessages.length).toBeGreaterThan(0)
    expect(screen.getByText(/Finish setup|Завершите настройку/i)).toBeVisible()
  })

  it("shows pending enrollments only inside the QR panel", async () => {
    const pendingEnrollment = createPendingEnrollment()
    testUser.totp_enrollments = [pendingEnrollment]
    const initialUser = {
      ...createBaseUser(),
      totp_enrollments: [pendingEnrollment],
    }

    const user = userEvent.setup()
    renderSettings({ initialUser })

    await user.click(await screen.findByRole("tab", { name: matchAccountTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })

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
    const initialUser = {
      ...createBaseUser(),
      totp_enrollments: [activeEnrollment],
      mfa_default_method: "totp",
    }

    const user = userEvent.setup()
    renderSettings({ initialUser })

    await user.click(await screen.findByRole("tab", { name: matchAccountTab }))
    await screen.findByRole("heading", { name: matchSecurityHeading })

    expect(
      await screen.findByText(
        /Only one authenticator app can be connected at a time|Можно подключить только одно приложение/i
      )
    ).toBeVisible()
    expect(screen.queryByRole("button", { name: matchTotpAddButton })).not.toBeInTheDocument()
  })
})
