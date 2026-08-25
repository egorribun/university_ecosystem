import { cleanup, screen, waitFor } from "@testing-library/react"
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

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
  currentUserQueryKey: ["users", "me"] as const,
  AuthProvider: ({ children }: { children: ReactNode }) => children,
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

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

const apiGetMock = apiMocks.get

async function renderSchedule() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  const result = await renderWithRouter({
    ui: Schedule,
    path: "/schedule",
    initialPath: "/schedule",
    queryClient: client,
  })

  return { client, ...result }
}

describe("Schedule cache handling", () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
    authState.user = { ...baseUser }
    authState.loading = false
    apiGetMock.mockReset()
    apiMocks.post.mockReset()
    apiMocks.patch.mockReset()
    apiMocks.delete.mockReset()
    apiMocks.put.mockReset()
    if (!(Element.prototype as any).scrollTo) {
      ;(Element.prototype as any).scrollTo = vi.fn()
    }
  })

  afterEach(() => {
    cleanup()
  })

  it("falls back to network fetch when cached schedule is stale", async () => {
    const stalePayload = {
      version: 1,
      timestamp: 0,
    }
    localStorage.setItem(
      "sched:groups",
      JSON.stringify({ ...stalePayload, data: [{ id: "group-1", name: "Stale Group" }] })
    )
    localStorage.setItem(
      "sched:group-1",
      JSON.stringify({
        ...stalePayload,
        data: [
          {
            id: "lesson-100",
            weekday: "Monday",
            parity: "odd",
            start_time: "2024-03-25T08:00:00",
            end_time: "2024-03-25T09:30:00",
            subject: "Stale Subject",
            teacher: "Ada",
            room: "101",
            lesson_type: "Lecture",
            group_id: "group-1",
          },
        ],
      })
    )

    apiGetMock.mockImplementation(async (url: string) => {
      if (url === "/groups") {
        return { data: [{ id: "group-1", name: "Fresh Group" }] }
      }
      if (url === "/schedule/group-1") {
        return {
          data: [
            {
              id: "lesson-101",
              weekday: "Monday",
              parity: "odd",
              start_time: "2024-03-25T08:00:00",
              end_time: "2024-03-25T09:30:00",
              subject: "Fresh Subject",
              teacher: "Alan",
              room: "202",
              lesson_type: "Lecture",
              group_id: "group-1",
            },
          ],
        }
      }
      throw new Error(`Unhandled GET ${url}`)
    })

    const { client, unmount } = await renderSchedule()

    try {
      await waitFor(() => {
        // Wave 130 SW1 — factory queryFns pass `{ signal }` for AbortController
        // cancellation (matches events.ts/news.ts W129 pattern). Use
        // expect.anything() for the options arg since AbortSignal identity
        // varies per render.
        expect(apiGetMock).toHaveBeenCalledWith("/groups", expect.anything())
        expect(apiGetMock).toHaveBeenCalledWith("/schedule/group-1", expect.anything())
      })

      expect((await screen.findAllByText("Fresh Subject"))[0]).toBeInTheDocument()
      expect(screen.queryByText("Stale Subject")).not.toBeInTheDocument()
    } finally {
      unmount()
      client.clear()
    }
  })
})
