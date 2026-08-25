import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import { AuthContext } from "@/contexts/AuthContext"
import Settings from "@/pages/Settings"
import i18n from "../../i18n/config"
import { resetTestSessions, testSessions } from "@/tests/mocks/handlers"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@/stores/useAuthStore", () => {
  const user = {
    id: "uuid-1",
    email: "test@example.com",
    full_name: "Test User",
    role: "student",
    group_id: "group-1",
    avatar_url: "/media/avatars/original.png",
    avatar_url_optimized: null,
    cover_url: "/media/covers/original.jpg",
    cover_url_optimized: null,
    profile_detail: undefined,
    education_path: undefined,
    preferences: { dnd_enabled: false, timezone: null, dnd_start: null, dnd_end: null },
    spotify_connected: false,
    is_active: true,
    mfa_required: false,
    mfa_default_method: null,
    mfa_last_verified_at: null,
    recovery_codes_left: 0,
    totp_enrollments: [],
  }
  return {
    useAuthStore: () => ({
      user,
      loading: false,
      pendingMfa: null,
      authOperation: false,
      setUser: vi.fn(),
    }),
    useAuthUser: () => user,
    useAuthLoading: () => false,
    useAuthPendingMfa: () => null,
    useAuthActions: () => ({
      setUser: vi.fn(),
      setLoading: vi.fn(),
      setPendingMfa: vi.fn(),
      setAuthOperation: vi.fn(),
    }),
  }
})

const renderSettings = async () => {
  const queryClient = createQueryClient()
  const mockSetUser = vi.fn()
  const mockLogout = vi.fn().mockResolvedValue(undefined)

  const WrappedSettings = () => (
    <ThemeProvider>
      <AuthContext.Provider
        value={{
          setUser: mockSetUser,
          logout: mockLogout,
          login: vi.fn(),
          refresh: vi.fn(),
          submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
          requireMfa: vi.fn().mockResolvedValue(null),
          resetEtagCache: vi.fn(),
          authOperation: false,
        }}
      >
        <Settings />
      </AuthContext.Provider>
    </ThemeProvider>
  )

  const result = await renderWithRouter({
    ui: WrappedSettings,
    path: "/settings",
    initialPath: "/settings",
    queryClient,
    // Test mounts its own AuthContext.Provider — skip helper's AuthProvider.
    authProvider: false,
  })

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
    await renderSettings()

    await user.click(screen.getByRole("tab", { name: tSettings("tabs.security") }))

    await waitFor(() => {
      expect(screen.getByText(tSettings("sessions.title"))).toBeVisible()
    })
    await user.click(screen.getByText(tSettings("sessions.title")))

    expect(
      screen.getByText(testSessions[0]!.user_agent ?? tSettings("sessions.unknownDevice"))
    ).toBeVisible()
    expect(
      screen.getByText(testSessions[1]!.user_agent ?? tSettings("sessions.unknownDevice"))
    ).toBeVisible()

    const revokeButtons = await screen.findAllByRole("button", {
      name: tSettings("sessions.revoke"),
    })
    const actionable = revokeButtons.find((button) => !button.hasAttribute("disabled"))
    expect(actionable).toBeDefined()

    await user.click(actionable as HTMLButtonElement)

    await screen.findByText(tSettings("sessions.snackbar.revoked"))
    await screen.findByText(tSettings("sessions.status.revoked"))

    expect(testSessions[1]!.revoked_at).not.toBeNull()
  })
})
