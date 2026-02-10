import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import { AuthContext } from "@/contexts/AuthContext"
import Settings from "@/pages/Settings"
import type { User } from "@/types/User"
import { LanguageProvider } from "@/contexts/LanguageContext"
import i18n from "../../i18n/config"
import { resetTestSessions, testSessions } from "@/tests/mocks/handlers"

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
  id: "uuid-1",
  email: "test@example.com",
  full_name: "Test User",
  role: "student",
  group_id: "group-1",
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
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
  recovery_codes_left: 0,
  totp_enrollments: [],
  mfa_challenges: [],
}

const renderSettings = () => {
  const queryClient = createQueryClient()
  const mockSetUser = vi.fn()
  const mockLogout = vi.fn().mockResolvedValue(undefined)

  const result = render(
    <MemoryRouter initialEntries={["/settings"]}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <LanguageProvider>
            <AuthContext.Provider
              value={{
                user: baseUser,
                setUser: mockSetUser,
                logout: mockLogout,
                login: vi.fn(),
                loginWithPasskey: vi.fn(),
                refresh: vi.fn(),
                isAuth: true,
                loading: false,
                pendingMfa: null,
                submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
                requireMfa: vi.fn().mockResolvedValue(null),
                resetEtagCache: vi.fn(),
              }}
            >
              <Settings />
            </AuthContext.Provider>
          </LanguageProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )

  return { ...result, mockLogout }
}

const tSettings = (key: string, options?: Record<string, unknown>) =>
  i18n.t(`settings:${key}`, options)

describe("Settings sessions panel", () => {
  beforeEach(() => {
    resetTestSessions()
  })

  it("lists sessions and revokes a secondary session", async () => {
    const user = userEvent.setup()
    renderSettings()

    await user.click(screen.getByRole("tab", { name: tSettings("tabs.security") }))

    await waitFor(() => {
      expect(screen.getByText(tSettings("sessions.title"))).toBeVisible()
    })

    expect(
      screen.getByText(testSessions[0].user_agent ?? tSettings("sessions.unknownDevice"))
    ).toBeVisible()
    expect(
      screen.getByText(testSessions[1].user_agent ?? tSettings("sessions.unknownDevice"))
    ).toBeVisible()

    const revokeButtons = await screen.findAllByRole("button", {
      name: tSettings("sessions.revoke"),
    })
    const actionable = revokeButtons.find((button) => !button.hasAttribute("disabled"))
    expect(actionable).toBeDefined()

    await user.click(actionable as HTMLButtonElement)

    await screen.findByText(tSettings("sessions.snackbar.revoked"))
    await screen.findByText(tSettings("sessions.status.revoked"))

    expect(testSessions[1].revoked_at).not.toBeNull()
  })
})
