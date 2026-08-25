import { screen, cleanup } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import Schedule from "@/pages/Schedule"
import type { User } from "@/types/User"
import type { ReactNode } from "react"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { expect } from "vitest"

type AuthState = {
  isAuth: boolean
  login: ReturnType<typeof vi.fn>
  logout: ReturnType<typeof vi.fn>
  refresh: ReturnType<typeof vi.fn>
  user: User | null
  loading: boolean
  setUser: ReturnType<typeof vi.fn>
}

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  put: vi.fn(),
}))

const baseUser: User = {
  id: "uuid-1",
  email: "student@example.com",
  full_name: "Test Student",
  role: "student",
  group_id: "group-1",
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
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

const authState: AuthState = {
  isAuth: true,
  login: vi.fn(),
  logout: vi.fn(),
  refresh: vi.fn(),
  user: baseUser,
  loading: false,
  setUser: vi.fn(),
}

const { scheduleDataMock } = vi.hoisted(() => {
  const lesson = {
    id: "lesson-42",
    weekday: "Monday",
    parity: "odd",
    start_time: "08:00",
    end_time: "09:30",
    subject: "Linear Algebra",
    teacher: "Ada Lovelace",
    room: "101",
    lesson_type: "lecture",
    group_id: "group-1",
  }

  const scheduleDataMock = {
    user: { role: "student" },
    groups: [{ id: "group-1", name: "CS-101" }],
    selectedGroup: "group-1",
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
  // Passthrough AuthProvider so renderWithRouter's import resolves while
  // this test owns the auth state via the mocked useAuth.
  AuthProvider: ({ children }: { children: ReactNode }) => children,
}))

vi.mock("@/hooks/useScheduleData", () => ({
  useScheduleData: () => scheduleDataMock,
}))

vi.mock("@/api/client", () => ({
  __esModule: true,
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
    patch: apiMocks.patch,
    delete: apiMocks.delete,
    put: apiMocks.put,
    interceptors: { response: { use: vi.fn() }, request: { use: vi.fn() } },
  },
}))

const apiGetMock = apiMocks.get
const apiPostMock = apiMocks.post
const apiPatchMock = apiMocks.patch
const apiDeleteMock = apiMocks.delete
const apiPutMock = apiMocks.put

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

async function renderSchedule() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })

  const result = await renderWithRouter({
    ui: Schedule,
    path: "/schedule",
    initialPath: "/schedule",
    queryClient: client,
  })

  return { client, ...result }
}

describe("Schedule translations", () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
    authState.user = { ...baseUser }
    authState.loading = false
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    apiPatchMock.mockReset()
    apiDeleteMock.mockReset()
    apiPutMock.mockReset()
    if (!(Element.prototype as any).scrollTo) {
      ;(Element.prototype as any).scrollTo = vi.fn()
    }
  })

  afterEach(() => {
    cleanup()
  })

  it("renders English weekday headers and lesson labels", async () => {
    apiGetMock.mockImplementation(async (url: string) => {
      if (url === "/groups") {
        return { data: [{ id: "group-1", name: "CS-101" }] }
      }
      if (url === "/schedule/group-1") {
        return {
          data: [
            {
              id: "lesson-42",
              weekday: "Понедельник",
              parity: "odd",
              start_time: "2024-03-25T08:00:00",
              end_time: "2024-03-25T09:30:00",
              subject: "Linear Algebra",
              teacher: "Ada Lovelace",
              room: "101",
              lesson_type: "Лекция",
              group_id: "group-1",
            },
          ],
        }
      }
      throw new Error(`Unhandled GET ${url}`)
    })

    const { client } = await renderSchedule()

    try {
      expect(await screen.findByText("My schedule")).toBeInTheDocument()
      expect(await screen.findByRole("columnheader", { name: "Monday" })).toBeInTheDocument()
      expect(await screen.findByText("Lecture")).toBeInTheDocument()
    } finally {
      client.clear()
    }
  })
})
