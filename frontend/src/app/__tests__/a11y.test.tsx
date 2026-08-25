import { screen, waitFor } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import { describe, it, beforeEach, afterEach, expect, vi } from "vitest"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import type { ComponentType } from "react"

import Navbar from "@/components/navbar"
import Dashboard from "@/pages/Dashboard"
import Profile from "@/pages/Profile"
import { AuthContext } from "@/contexts/AuthContext"
import { checkA11y } from "@/tests/axeTest"
import { createQueryClient } from "@/app/queryClient"
import api from "@/api/client"
import * as sdk from "@/api/generated/sdk.gen"
import type { User } from "@/types/User"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { AppShellProvider } from "@/contexts/AppShellContext"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@/components/feedback/NotificationsBell", () => ({
  default: ({ iconColor }: { iconColor?: string }) => (
    <div data-testid="notifications-bell" data-color={iconColor ?? ""} />
  ),
}))

vi.mock("@/components/layout/MessengerButton", () => ({
  default: () => <button aria-label="Messenger">Messenger</button>,
}))

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => ({
    items: [],
    loading: false,
    unreadCount: 0,
    hasMore: false,
    loadMore: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    refresh: vi.fn(),
    fetching: false,
  }),
}))

vi.mock("@/hooks/useNowPlaying", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/useNowPlaying")>("@/hooks/useNowPlaying")
  return {
    ...actual,
    useNowPlaying: () => ({
      data: null,
      status: "success",
      fetchStatus: "idle",
      isFetching: false,
      isLoading: false,
      isSuccess: true,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
  }
})

const baseUser: User = {
  id: "uuid-1",
  email: "user@example.com",
  full_name: "Тестовый Пользователь",
  role: "student",
  group_id: "uuid-101",
  avatar_url: "",
  avatar_url_optimized: null,
  cover_url: "",
  cover_url_optimized: null,
  profile_detail: {
    about: "Студент ГУУ",
    telegram: "@testuser",
    status: "Студент",
    achievements: "Победитель олимпиады|ГУУ|2023",
    department: "Кафедра ИТ",
    position: "",
  },
  education_path: {
    record_book_number: "123456",
    institute: "Институт цифровых технологий",
    course: "3",
    education_level: null,
    track: "Разработка",
    program: "Информатика",
  },
  preferences: {
    dnd_enabled: false,
    dnd_start: null,
    dnd_end: null,
    timezone: null,
  },
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: false,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  recovery_codes_left: 0,
  totp_enrollments: [],
}

const activeClients: QueryClient[] = []

async function renderForA11y(Component: ComponentType, route = "/dashboard") {
  const queryClient = createQueryClient()
  activeClients.push(queryClient)
  const authValue = {
    isAuth: true,
    login: vi.fn(),
    logout: vi.fn(),
    setUser: vi.fn(),
    refresh: vi.fn(),
    loading: false,
    user: { ...baseUser },
    pendingMfa: null,
    submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
    requireMfa: vi.fn().mockResolvedValue(null),
    resetEtagCache: vi.fn(),
    authOperation: false,
  }

  const Wrapped = () => (
    <ThemeProvider>
      <AppShellProvider>
        <AuthContext.Provider value={authValue}>
          <Component />
        </AuthContext.Provider>
      </AppShellProvider>
    </ThemeProvider>
  )

  return renderWithRouter({
    ui: Wrapped,
    path: route,
    initialPath: route,
    queryClient,
    authProvider: false,
  })
}

describe("Accessibility checks", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn().mockReturnValue(false),
      }),
    })
  })

  afterEach(() => {
    activeClients.splice(0).forEach((client) => client.clear())
    vi.clearAllMocks()
  })

  it("Navbar has no axe violations", async () => {
    const { container } = await renderForA11y(Navbar, "/dashboard")

    await waitFor(() => expect(screen.getByRole("navigation")).toBeInTheDocument())

    await checkA11y(container)
  })

  it("Dashboard page has no axe violations", async () => {
    const stories = [
      {
        id: "uuid-1",
        title: "Orientation",
        short_text: "Welcome week",
        cover_url: null,
        cover_url_optimized: null,
        cta_url: null,
        published_at: new Date(Date.now() - 3_600_000).toISOString(),
        expires_at: new Date(Date.now() + 86_400_000).toISOString(),
        is_active: true,
        created_at: new Date().toISOString(),
        title_en: "Orientation",
        short_text_en: "Welcome week",
        created_by: "uuid-1",
      },
    ]

    const mockResponse = <T,>(data: T): AxiosResponse<T> => ({
      data,
      status: 200,
      statusText: "OK",
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    })

    const getSpy = vi.spyOn(api, "get").mockImplementation(async (url: string) => {
      if (url === "/stories") {
        return mockResponse(stories)
      }
      return mockResponse([])
    })
    const typedGetSpy = vi.spyOn(sdk, "newsListApiV1NewsGet").mockImplementation(async () => {
      return mockResponse({
        items: [],
        total: 0,
        limit: 12,
        cursor: null,
        next_cursor: null,
        has_more: false,
      })
    })

    const { container } = await renderForA11y(Dashboard, "/dashboard")

    await waitFor(() => expect(api.get).toHaveBeenCalled())
    // Wait for internal components to finish loading (e.g. ScheduleCard)
    await waitFor(() => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument(), {
      timeout: 2000,
    })

    await checkA11y(container)
    getSpy.mockRestore()
    typedGetSpy.mockRestore()
  })

  it("Profile page has no axe violations", async () => {
    const { container } = await renderForA11y(Profile, "/profile")

    await waitFor(() => expect(screen.getByTestId("profile-root")).toBeInTheDocument())

    await checkA11y(container)
  })
})
