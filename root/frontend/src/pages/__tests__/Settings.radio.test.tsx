import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { CssVarsProvider } from "@mui/material/styles"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import { AuthContext } from "@/contexts/AuthContext"
import Settings from "@/pages/Settings"
import type { User } from "@/types/User"
import { LanguageProvider } from "@/contexts/LanguageContext"
import theme from "@/theme"
import i18n from "../../i18n/config"

const tSettings = (key: string, options?: Record<string, unknown>) =>
  i18n.t(`settings:${key}`, options)

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => ({ unreadCount: 0 }),
}))

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

const baseUser: User = {
  id: 1,
  email: "test@example.com",
  full_name: "Test User",
  role: "student",
  group_id: null,
  avatar_url: null,
  cover_url: null,
  about: null,
  record_book_number: null,
  status: null,
  institute: null,
  course: null,
  education_level: null,
  track: null,
  program: null,
  telegram: null,
  achievements: null,
  department: null,
  position: null,
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: false,
  dnd_enabled: false,
  dnd_start: null,
  dnd_end: null,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  mfa_recovery_codes_generated_at: null,
  totp_enrollments: [],
  webauthn_credentials: [],
  recovery_codes: [],
  mfa_challenges: [],
}

const renderSettings = () => {
  const queryClient = createQueryClient()
  const mockSetUser = vi.fn()
  const mockLogout = vi.fn().mockResolvedValue(undefined)

  const utils = render(
    <MemoryRouter initialEntries={["/settings"]}>
      <QueryClientProvider client={queryClient}>
        <CssVarsProvider theme={theme}>
          <LanguageProvider>
            <AuthContext.Provider
              value={{
                user: baseUser,
                setUser: mockSetUser,
                logout: mockLogout,
                login: vi.fn(),
                refresh: vi.fn(),
                isAuth: true,
                loading: false,
                pendingMfa: null,
                submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
                requireMfa: vi.fn().mockResolvedValue(null),
              }}
            >
              <Settings />
            </AuthContext.Provider>
          </LanguageProvider>
        </CssVarsProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )

  return { ...utils, mockSetUser }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  localStorage.clear()
})

describe("Settings radio buttons", () => {
  it("should change theme when radio button is clicked", async () => {
    renderSettings()

    // Find theme radio buttons
    const systemRadio = screen.getByLabelText(
      new RegExp(tSettings("appearance.theme.options.system"), "i")
    )
    const lightRadio = screen.getByLabelText(
      new RegExp(tSettings("appearance.theme.options.light"), "i")
    )
    const darkRadio = screen.getByLabelText(
      new RegExp(tSettings("appearance.theme.options.dark"), "i")
    )

    // System should be selected by default
    expect(systemRadio).toBeChecked()
    expect(lightRadio).not.toBeChecked()
    expect(darkRadio).not.toBeChecked()

    // Click light theme
    fireEvent.click(lightRadio)
    await waitFor(() => expect(lightRadio).toBeChecked())
    expect(systemRadio).not.toBeChecked()
    expect(darkRadio).not.toBeChecked()

    // Click dark theme
    fireEvent.click(darkRadio)
    await waitFor(() => expect(darkRadio).toBeChecked())
    expect(systemRadio).not.toBeChecked()
    expect(lightRadio).not.toBeChecked()
  })

  it("should change language when radio button is clicked", async () => {
    renderSettings()

    // Find language radio buttons - ru should be selected by default
    const ruRadio = screen.getByLabelText(
      new RegExp(tSettings("language.options.ru"), "i")
    ) as HTMLInputElement
    const enRadio = screen.getByLabelText(
      new RegExp(tSettings("language.options.en"), "i")
    ) as HTMLInputElement

    // Check initial state (should be ru)
    expect(ruRadio).toBeChecked()
    expect(enRadio).not.toBeChecked()

    // Click English
    fireEvent.click(enRadio)
    await waitFor(() => expect(enRadio).toBeChecked())
    expect(ruRadio).not.toBeChecked()

    // Click Russian
    fireEvent.click(ruRadio)
    await waitFor(() => expect(ruRadio).toBeChecked())
    expect(enRadio).not.toBeChecked()
  })
})
