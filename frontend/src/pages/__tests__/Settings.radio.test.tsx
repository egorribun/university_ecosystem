import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import { AuthContext } from "@/contexts/AuthContext"
import Settings from "@/pages/Settings"
import type { User } from "@/types/User"
import { LanguageProvider } from "@/contexts/LanguageContext"
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

  const utils = render(
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

  return { ...utils, mockSetUser }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  localStorage.clear()
})

describe("Settings radio buttons", () => {
  it("renders theme radio buttons and allows interaction", async () => {
    const { container } = renderSettings()

    // Wait for page to render with theme section
    await waitFor(() => {
      expect(screen.getByText(/theme/i)).toBeInTheDocument()
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
      fireEvent.click(lightRadio)
      // Wait for MUI to update localStorage
      await waitFor(() => {
        expect(localStorage.getItem("theme")).toBe("light")
      })
    }
  })

  it("renders language radio buttons and allows interaction", async () => {
    const { container } = renderSettings()

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
      fireEvent.click(enRadio)
      // Wait a bit for state update
      await new Promise((resolve) => setTimeout(resolve, 100))
      expect(localStorage.getItem("ue:language")).toBe("en")
    }
  })
})
