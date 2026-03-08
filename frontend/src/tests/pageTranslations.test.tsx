/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"
import { ThemeProvider } from "@/contexts/ThemeContext"
import UserActivity from "@/pages/Activity"
import Schedule from "@/pages/Schedule"
import Settings from "@/pages/Settings"
import Profile from "@/pages/Profile"
import Events from "@/pages/Events"
import MapContent from "@/pages/MapContent"
import AdminUsers from "@/pages/AdminUsers"
import Dashboard from "@/pages/Dashboard"
import News from "@/pages/News"
import Login from "@/pages/Login"
import Register from "@/pages/Register"
import ForgotPassword from "@/pages/ForgotPassword"
import ResetPassword from "@/pages/ResetPassword"
import i18n from "@/i18n/config"
import type { User } from "@/types/User"

const resizeObserverMock = vi.fn()

class MockResizeObserver {
  observe = resizeObserverMock
  unobserve = vi.fn()
  disconnect = vi.fn()
}

const originalSetProperty = CSSStyleDeclaration.prototype.setProperty

type ApiResponse<T = unknown> = Promise<{ data: T }>

const {
  baseUser,
  apiGetMock,
  apiPostMock,
  apiPatchMock,
  apiDeleteMock,
  apiPutMock,
  fetchCurrentUserMock,
} = vi.hoisted(() => {
  const baseUser: User = {
    id: "uuid-1",
    email: "test@example.com",
    full_name: "Test User",
    role: "student",
    group_id: "uuid-101",
    avatar_url: null,
    avatar_url_optimized: null,
    cover_url: null,
    cover_url_optimized: null,
    profile_detail: {
      about: "",
      telegram: "testuser",
      status: "active",
      achievements: null,
      department: null,
      position: null,
    },
    education_path: {
      record_book_number: null,
      institute: "Business",
      course: "2",
      education_level: "bachelor",
      track: "Management",
      program: "General",
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
    mfa_challenges: [],
  }

  const scheduleGroups = [{ id: "uuid-101", name: "IU5-21" }]
  const scheduleLessons = [
    {
      id: "uuid-1",
      // Use the localized weekday so the Tailwind dashboard resolves the lesson under
      // both English and Russian week-day mappings.
      weekday: "Понедельник",
      parity: "both",
      start_time: "09:00",
      end_time: "10:30",
      subject: "Linear Algebra",
      teacher: "Dr. Matrix",
      room: "101",
      lesson_type: "lecture",
      group_id: "uuid-101",
    },
  ]
  const adminUsers = [
    {
      id: "uuid-1",
      full_name: "Alice Admin",
      email: "alice@example.com",
      role: "admin",
      group_id: null,
      avatar_url: null,
      avatar_url_optimized: null,
    },
    {
      id: "uuid-2",
      full_name: "Bob Student",
      email: "bob@example.com",
      role: "student",
      group_id: "uuid-101",
      avatar_url: null,
      avatar_url_optimized: null,
    },
  ]
  const sampleEvent = {
    id: "uuid-1",
    title: "Campus Hackathon",
    title_en: "Campus Hackathon",
    description: "A friendly coding event",
    description_en: "A friendly coding event",
    location: "Main hall",
    location_en: "Main hall",
    event_type: "hackathon",
    event_type_en: "Hackathon",
    starts_at: new Date().toISOString(),
    ends_at: new Date(Date.now() + 3600_000).toISOString(),
    created_by: "uuid-1",
    created_at: new Date().toISOString(),
    is_active: true,
    speaker: "Mentor",
    about: null,
    about_en: null,
    files: [],
    participant_count: 42,
    is_registered: false,
    my_qr_token: null,
  }
  const storiesItems = [
    {
      id: "uuid-1",
      title: "Campus orientation",
      title_en: "Campus orientation",
      short_text: "Welcome week highlights",
      short_text_en: "Welcome week highlights",
      cover_url: null,
      cover_url_optimized: null,
      cta_url: "/events",
      published_at: new Date(Date.now() - 600_000).toISOString(),
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
      is_active: true,
      created_at: new Date().toISOString(),
      created_by: "uuid-1",
    },
  ]

  const newsItems = [
    {
      id: 1,
      title: "Library renovation",
      content: "Reading halls reopen next week.",
      created_at: new Date().toISOString(),
      image_url: null,
      image_url_optimized: null,
      pinned: false,
    },
  ]
  const notificationsResponse = {
    items: [
      {
        id: "uuid-1",
        title: "System update",
        body: "New features have been deployed.",
        created_at: new Date().toISOString(),
        read: false,
      },
    ],
    unread_count: 1,
    has_more: false,
    next_cursor: null,
  }
  const attendanceSummary = {
    percent: 85,
    present: 17,
    total: 20,
    trend: 4,
    period_key: "30d",
    period_label: "Last 30 days",
    recent: [{ date: "2025-09-19", status: "present", course: "Physics" }],
  }
  const gradeSummary = {
    average: 4.6,
    scale: "5" as const,
    trend: 2,
    period_key: "30d",
    period_label: "Last 30 days",
    recent: [{ course: "Physics", score: 5, date: "2025-09-10" }],
  }
  const participationSummary = {
    events: 3,
    hours: 6,
    groups: 2,
    trend: 1,
    period_key: "30d",
    period_label: "Last 30 days",
    recent: [{ title: "Volunteer Day", date: "2025-09-12", role: "helper" }],
  }

  const apiGetMock = vi.fn((url: string): ApiResponse => {
    if (url === "/stats/attendance") return Promise.resolve({ data: attendanceSummary })
    if (url === "/stats/grades") return Promise.resolve({ data: gradeSummary })
    if (url === "/stats/participation") return Promise.resolve({ data: participationSummary })
    if (url === "/events")
      return Promise.resolve({
        data: {
          items: [sampleEvent],
          total: 1,
          limit: 20,
          cursor: null,
          next_cursor: null,
          has_more: false,
        },
      })
    if (url === "/events/my") return Promise.resolve({ data: [] })
    if (url === "/stories" || url === "/api/v1/stories") {
      return Promise.resolve({ data: storiesItems, status: 200 })
    }
    if (url === "/news" || url === "/api/v1/news") return Promise.resolve({ data: newsItems })
    if (url === "/notifications" || url === "/api/v1/notifications")
      return Promise.resolve({ data: notificationsResponse })
    if (url === "/groups") return Promise.resolve({ data: scheduleGroups })
    if (url.startsWith("/schedule/")) return Promise.resolve({ data: scheduleLessons })
    if (url === "/users") return Promise.resolve({ data: adminUsers })
    if (url === "/spotify/auth-url")
      return Promise.resolve({
        data: { url: "https://accounts.spotify.com/authorize?client_id=1" },
      })
    return Promise.resolve({ data: [] })
  })

  const apiPostMock = vi.fn((_url: string, _body?: any) => Promise.resolve({ data: {} }))
  const apiPatchMock = vi.fn((_url: string, _body?: any) => Promise.resolve({ data: {} }))
  const apiDeleteMock = vi.fn((_url: string) => Promise.resolve({ data: {} }))
  const apiPutMock = vi.fn((_url: string, _body?: any) => Promise.resolve({ data: baseUser }))

  const fetchCurrentUserMock = vi.fn(async () => baseUser)

  return {
    storiesItems,
    baseUser,
    apiGetMock,
    apiPostMock,
    apiPatchMock,
    apiDeleteMock,
    apiPutMock,
    fetchCurrentUserMock,
  }
})

const { weatherResult } = vi.hoisted(() => {
  const weatherResult = {
    data: {
      conditionCode: 0,
      conditionLabel: "Clear sky",
      temperatureC: 21,
      observedAt: new Date("2025-09-15T08:45:00Z").toISOString(),
      icon: "☀️",
      translationKeySuffix: "clear",
      translationKey: "dashboard:weather.conditions.clear",
      animation: "glow" as const,
    },
    isLoading: false,
    error: null,
    refresh: vi.fn(),
  }

  return { weatherResult }
})

const authState = {
  isAuth: true,
  login: vi.fn(),
  loginWithPasskey: vi.fn(),
  logout: vi.fn(),
  refresh: vi.fn(),
  user: baseUser,
  loading: false,
  setUser: vi.fn(),
}

const { scheduleDataMock } = vi.hoisted(() => {
  const lesson = {
    id: "uuid-42",
    weekday: "Monday",
    parity: "odd",
    start_time: "08:00",
    end_time: "09:30",
    subject: "Linear Algebra",
    teacher: "Ada Lovelace",
    room: "101",
    lesson_type: "lecture",
    group_id: "uuid-101",
  }

  const scheduleDataMock = {
    user: { role: "student" },
    groups: [{ id: "uuid-101", name: "CS-101" }],
    selectedGroup: "uuid-101",
    setSelectedGroup: () => {},
    currentParity: "odd",
    setCurrentParity: () => {},
    schedule: [lesson],
    rawSchedule: [lesson],
    isLoading: false,
    refresh: () => {},
    applyScheduleUpdate: () => {},
    weekdayConfigs: [{ id: "mon", backend: ["Monday"], long: "Monday", short: "Mon" }],
    weekdayBackend: ["Monday"],
    weekdayLabels: ["Monday"],
    weekdayShort: ["Mon"],
    getDayLabel: (value: string) => value,
    lessonTypeConfigs: [
      { id: "lecture", backend: ["lecture"], label: "Lecture", color: "#3366ff" },
    ],
    lessonTypeOptions: [{ value: "lecture", label: "Lecture" }],
    lessonTypeLabels: new Map([["lecture", "Lecture"]]),
    defaultLessonType: "lecture",
    getLessonTypeColor: () => "#3366ff",
    toBackendLessonType: (value?: string | null) => value ?? "lecture",
    todayIdx: 0,
    hasToday: false,
    nowTick: new Date(),
    todayLessons: [],
    currentLesson: null,
    nextLesson: null,
    conflictedIds: new Set<string>(),
    timeLeftText: "",
    currentProgress: 0,
  }

  return { scheduleDataMock }
})

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
  currentUserQueryKey: ["users", "me"] as const,
  fetchCurrentUser: fetchCurrentUserMock,
}))

vi.mock("@/hooks/useScheduleData", () => ({
  useScheduleData: () => scheduleDataMock,
}))

vi.mock("@/hooks/useNowPlaying", () => ({
  useNowPlaying: () => ({
    data: null,
    isFetching: false,
    status: "success",
    refetch: vi.fn(),
  }),
  nowPlayingQueryKey: ["now-playing"],
}))

vi.mock("@/hooks/useWeather", () => ({
  useWeather: vi.fn(() => weatherResult),
}))

const pushPreferencesMock = {
  pushSupported: true,
  notificationPermission: "default" as NotificationPermission,
  notificationsEnabled: false,
  pushBusy: false,
  pushInitializing: false,
  permissionText: "Default",
  enableNotifications: vi.fn(),
  disableNotifications: vi.fn(),
}

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: () => pushPreferencesMock,
}))

vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="layout-root">{children}</div>
  ),
}))

vi.mock("@/components/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/SmartImage", () => ({
  default: ({ alt }: { alt?: string }) => <img alt={alt ?? ""} />,
}))

vi.mock("@/assets/background.jpg", () => ({ default: "profile-bg.jpg" }))
vi.mock("@/assets/guu_logo.png", () => ({ default: "guu-logo.png" }))
vi.mock("@/assets/spotify_icon.png", () => ({ default: "spotify-icon.png" }))

vi.mock("@/api/client", () => ({
  __esModule: true,
  default: {
    get: apiGetMock,
    post: apiPostMock,
    patch: apiPatchMock,
    delete: apiDeleteMock,
    put: apiPutMock,
    interceptors: { response: { use: vi.fn() }, request: { use: vi.fn() } },
  },
  apiClient: {
    get: apiGetMock,
    post: apiPostMock,
    patch: apiPatchMock,
    delete: apiDeleteMock,
    put: apiPutMock,
    interceptors: { response: { use: vi.fn() }, request: { use: vi.fn() } },
  },
  API_UNAUTHORIZED_EVENT: "auth:unauthorized",
  SKIP_UNAUTHORIZED_HEADER: "X-Client-Skip-Unauthorized",
}))

vi.mock("@/api/generated/client.gen", () => ({
  client: {
    get: (opts: any) => apiGetMock(typeof opts === "string" ? opts : opts.url),
    post: (opts: any) => apiPostMock(typeof opts === "string" ? opts : opts.url, opts?.body),
    patch: (opts: any) => apiPatchMock(typeof opts === "string" ? opts : opts.url, opts?.body),
    delete: (opts: any) => apiDeleteMock(typeof opts === "string" ? opts : opts.url),
    put: (opts: any) => apiPutMock(typeof opts === "string" ? opts : opts.url, opts?.body),
    setConfig: vi.fn(),
    getConfig: vi.fn(),
  },
}))

function LanguageToggleHarness({ children }: { children: ReactNode }) {
  const { language, setLanguage } = useLanguage()

  return (
    <>
      <button
        type="button"
        data-testid="lang-toggle"
        onClick={() => setLanguage(language === "ru" ? "en" : "ru")}
      >
        toggle
      </button>
      {children}
    </>
  )
}

const clients: QueryClient[] = []

type RenderOptions = {
  initialPath?: string
  initialLanguage?: "en" | "ru"
}

function renderWithProviders(ui: ReactNode, options: RenderOptions = {}) {
  const { initialPath = "/", initialLanguage = "en" } = options
  localStorage.setItem("ue:language", initialLanguage)
  document.documentElement.setAttribute("lang", initialLanguage)
  void i18n.changeLanguage(initialLanguage)
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 1_000_000 },
    },
  })
  clients.push(client)
  const user = userEvent.setup()

  const result = render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <LanguageProvider>
          <MemoryRouter initialEntries={[initialPath]}>
            <LanguageToggleHarness>{ui}</LanguageToggleHarness>
          </MemoryRouter>
        </LanguageProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )

  return { user, client, ...result }
}

beforeAll(() => {
  ;(globalThis as any).ResizeObserver = MockResizeObserver
  vi.spyOn(window, "open").mockImplementation(() => null)
  vi.spyOn(window, "confirm").mockReturnValue(true)
  if (!(HTMLElement.prototype as any).scrollTo) {
    ;(HTMLElement.prototype as any).scrollTo = () => {}
  }
  CSSStyleDeclaration.prototype.setProperty = function setProperty(name, value) {
    try {
      originalSetProperty.call(this, name, value)
    } catch {
      Object.defineProperty(this, name, {
        configurable: true,
        enumerable: true,
        value: value ?? "",
        writable: true,
      })
    }
  }
})

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem("ue:language", "en")
  document.documentElement.setAttribute("lang", "en")
  fetchCurrentUserMock.mockClear()
  fetchCurrentUserMock.mockImplementation(async () => authState.user)
  apiGetMock.mockClear()
  apiPostMock.mockClear()
  apiPatchMock.mockClear()
  apiDeleteMock.mockClear()
  apiPutMock.mockClear()
  pushPreferencesMock.enableNotifications.mockClear()
  pushPreferencesMock.disableNotifications.mockClear()
  weatherResult.refresh.mockClear()
})

afterEach(() => {
  while (clients.length) {
    const client = clients.pop()
    client?.clear()
  }
})

afterAll(() => {
  CSSStyleDeclaration.prototype.setProperty = originalSetProperty
})

describe("page translations", () => {
  it("switches activity page translations", async () => {
    const { user } = renderWithProviders(<UserActivity />)

    expect(await screen.findByText("Activity")).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByText("Активность")).toBeInTheDocument()
  })

  it("switches schedule page translations", async () => {
    const { user } = renderWithProviders(<Schedule />, { initialPath: "/schedule" })

    expect(await screen.findByText("My schedule")).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByText("Моё расписание")).toBeInTheDocument()
  })

  it("switches settings translations including notifications", async () => {
    const { user } = renderWithProviders(<Settings />, { initialPath: "/settings" })

    expect(await screen.findByText("Settings")).toBeInTheDocument()
    expect(screen.getByText("Notifications")).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByText("Настройки")).toBeInTheDocument()
    expect(screen.getByText("Уведомления")).toBeInTheDocument()
  })

  it("switches profile translations", async () => {
    const { user } = renderWithProviders(<Profile />, { initialPath: "/profile" })

    expect(await screen.findByLabelText("Profile")).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByLabelText("Профиль")).toBeInTheDocument()
  })

  it("switches events page translations", async () => {
    const { user } = renderWithProviders(<Events />, { initialPath: "/events" })

    expect(await screen.findByText("Events")).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Upcoming" })).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByText("Мероприятия")).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Актуальные" })).toBeInTheDocument()
  })

  it("switches map controls translations", async () => {
    const matchMediaSpy = vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }))

    try {
      const { user } = renderWithProviders(<MapContent />, { initialPath: "/map" })

      expect(await screen.findByText("Campus map")).toBeInTheDocument()
      expect(
        await screen.findByText(
          "Interactive maps are disabled to respect your privacy or reduced motion settings."
        )
      ).toBeInTheDocument()
      // The fallback landmark is intentionally exposed as a region so keyboard users can
      // quickly locate the static points list when the Tailwind map shim takes over.
      expect(await screen.findByRole("region", { name: "Campus overview" })).toBeInTheDocument()

      await user.click(screen.getByTestId("lang-toggle"))

      expect(await screen.findByText("Карта кампуса")).toBeInTheDocument()
      expect(
        await screen.findByText(
          "Интерактивная карта отключена согласно настройкам приватности или уменьшения анимации."
        )
      ).toBeInTheDocument()
      expect(await screen.findByRole("region", { name: "Обзор кампуса" })).toBeInTheDocument()
    } finally {
      matchMediaSpy.mockRestore()
    }
  })

  it("switches admin users page translations", async () => {
    const { user } = renderWithProviders(<AdminUsers />, { initialPath: "/admin/users" })

    expect(await screen.findByRole("heading", { name: "Users" })).toBeInTheDocument()
    // The legacy MUI select still exposes its label text without a name. Assert the
    // rendered label so we track the translation until the filter is replaced in Tailwind.
    expect(screen.getByText("Role", { selector: "label" })).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByRole("heading", { name: "Пользователи" })).toBeInTheDocument()
    expect(screen.getByText("Роль", { selector: "label" })).toBeInTheDocument()
  })

  it("switches dashboard page translations", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2025-09-15T09:30:00"))

    try {
      const { user } = renderWithProviders(<Dashboard />, { initialPath: "/dashboard" })

      expect(await screen.findByText("Today's schedule")).toBeInTheDocument()
      const weatherBadgeEn = await screen.findByLabelText("Weather. Clear sky. Temperature +21°C.")
      expect(weatherBadgeEn).toHaveAttribute("data-animation", "glow")
      expect(weatherBadgeEn).toHaveAttribute("title", "Weather · Clear sky · +21°")
      // The Tailwind dashboard keeps the stories heading visually hidden but exposes it to
      // assistive tech. Querying by role keeps that intentional sr-only <h2> in place.
      expect(await screen.findByRole("heading", { name: "Stories" })).toBeInTheDocument()
      const storyButton = await screen.findByRole("button", {
        name: "Story: Campus orientation",
      })

      await user.click(storyButton)

      expect(await screen.findByText("Stories advance automatically.")).toBeInTheDocument()

      // The progress bar now comes from the Tailwind primitive and exposes an explicit
      // aria-label so screen readers can announce the metric instead of a raw percentage.
      const progressbarsEn = await screen.findAllByRole("progressbar")
      expect(progressbarsEn.map((el) => el.getAttribute("aria-label"))).toContain(
        "Progress of the current lesson"
      )

      await user.click(screen.getByTestId("lang-toggle"))

      expect(await screen.findByText("Расписание на сегодня")).toBeInTheDocument()
      await waitFor(() => {
        const weatherBadgeRu = screen.getByLabelText("Погода. Ясно. Температура +21°C.")
        expect(weatherBadgeRu).toHaveAttribute("data-animation", "glow")
        expect(weatherBadgeRu).toHaveAttribute("title", "Погода · Ясно · +21°")
      })
      expect(await screen.findByText("Истории переключаются автоматически.")).toBeInTheDocument()
      await waitFor(() => {
        const ruLabels = screen
          .getAllByRole("progressbar")
          .map((el) => el.getAttribute("aria-label"))
        expect(ruLabels).toContain("Прогресс текущего занятия")
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it("switches news page translations", async () => {
    const { user } = renderWithProviders(<News />, { initialPath: "/news" })

    expect(await screen.findByRole("heading", { name: "University news" })).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByRole("heading", { name: "Новости университета" })).toBeInTheDocument()
  })

  it("renders login page in Russian when seeded and toggles to English", async () => {
    const { user } = renderWithProviders(<Login />, {
      initialPath: "/login",
      initialLanguage: "ru",
    })

    expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument()
  })

  it("switches register page translations", async () => {
    const { user } = renderWithProviders(<Register />, { initialPath: "/register" })

    expect(await screen.findByRole("heading", { name: "Sign up" })).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByRole("heading", { name: "Регистрация" })).toBeInTheDocument()
  })

  it("switches forgot password page translations", async () => {
    const { user } = renderWithProviders(<ForgotPassword />, { initialPath: "/forgot-password" })

    expect(await screen.findByRole("heading", { name: "Reset password" })).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(
      await screen.findByRole("heading", { name: "Восстановление пароля" })
    ).toBeInTheDocument()
  })

  it("switches reset password page translations", async () => {
    const { user } = renderWithProviders(<ResetPassword />, {
      initialPath: "/reset-password?token=example",
    })

    expect(
      await screen.findByRole("heading", { name: "Create a new password" })
    ).toBeInTheDocument()

    await user.click(screen.getByTestId("lang-toggle"))

    expect(await screen.findByRole("heading", { name: "Новый пароль" })).toBeInTheDocument()
  })
})
