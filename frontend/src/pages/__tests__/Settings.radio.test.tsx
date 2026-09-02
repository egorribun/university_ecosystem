import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import { AuthContext } from "@/contexts/AuthContext"
import Settings from "@/pages/Settings"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => ({ unreadCount: 0 }),
}))

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

  const utils = await renderWithRouter({
    ui: WrappedSettings,
    path: "/settings",
    initialPath: "/settings",
    queryClient,
    // Test mounts its own AuthContext.Provider — skip helper's AuthProvider.
    authProvider: false,
  })

  return { ...utils, mockSetUser }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  localStorage.clear()
})

describe("Settings radio buttons", () => {
  it("renders theme radio buttons and allows interaction", async () => {
    const user = userEvent.setup()
    const { container } = await renderSettings()

    // Wait for page to render with theme section
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /^theme$/i })).toBeInTheDocument()
    })

    // Find theme radio buttons
    const allRadios = Array.from(
      container.querySelectorAll<HTMLInputElement>('input[type="radio"]')
    )
    const themeRadios = allRadios.filter((r) => ["system", "light", "dark"].includes(r.value))

    // Verify all theme radio buttons are present
    expect(themeRadios).toHaveLength(3)

    // Verify radio buttons are not disabled
    themeRadios.forEach((radio) => {
      expect(radio).not.toBeDisabled()
    })

    // Click each radio button to verify it's interactive
    const lightRadio = themeRadios.find((r) => r.value === "light")
    if (lightRadio) {
      await user.click(lightRadio)
      // Wait for MUI to update localStorage
      await waitFor(() => {
        expect(localStorage.getItem("ue-mode")).toBe("light")
      })
    }
  })

  it("renders language radio buttons and allows interaction", async () => {
    const user = userEvent.setup()
    const { container } = await renderSettings()

    // Wait for language section to render
    await waitFor(() => {
      const text = container.textContent
      expect(text).toMatch(/язык|language/i)
    })

    // Find language radio buttons
    const allRadios = Array.from(
      container.querySelectorAll<HTMLInputElement>('input[type="radio"]')
    )
    const langRadios = allRadios.filter((r) => ["ru", "en"].includes(r.value))

    // Verify language radio buttons are present
    expect(langRadios.length).toBeGreaterThanOrEqual(2)

    // Verify radio buttons are not disabled
    langRadios.forEach((radio) => {
      expect(radio).not.toBeDisabled()
    })

    // Click a language radio to verify it's interactive
    const enRadio = langRadios.find((r) => r.value === "en")
    if (enRadio) {
      await user.click(enRadio)
      // Wait a bit for state update
      await new Promise((resolve) => setTimeout(resolve, 100))
      expect(localStorage.getItem("ue:language")).toBe("en")
    }
  })
})
