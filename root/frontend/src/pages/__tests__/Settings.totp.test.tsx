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
  webauthn_credentials: [],
  recovery_codes: [],
  mfa_default_method: null,
  mfa_last_verified_at: null,
})

const renderSettings = () => {
  const queryClient = createQueryClient()
  const initialUser = createBaseUser()

  const TestAuthProvider = ({ children }: PropsWithChildren) => {
    const [user, setUser] = useState<User | null>(initialUser)
    return (
      <AuthContext.Provider
        value={{
          user,
          setUser,
          logout: vi.fn(),
          login: vi.fn(),
          refresh: vi.fn(),
          isAuth: true,
          loading: false,
          pendingMfa: null,
          submitMfaChallenge: vi.fn(),
          requireMfa: vi.fn(),
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
    await user.click(screen.getByRole("button", { name: matchTotpSubmit }))

    await waitFor(() => expect(screen.getByText(/Authenticator app connected|Приложение-аутентификатор подключено/i)).toBeVisible())

    await waitFor(() =>
      expect(screen.getByText(/Authenticator 1|Аутентификатор 1/i)).toBeVisible()
    )
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
    await user.click(screen.getByRole("button", { name: matchTotpSubmit }))

    await screen.findByText(/Invalid verification code/i)
    expect(screen.getByText(/Finish setup|Завершите настройку/i)).toBeVisible()
  })
})
