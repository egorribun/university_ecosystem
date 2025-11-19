import { MemoryRouter } from "react-router-dom"
import { render, screen, cleanup } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LanguageProvider } from "@/contexts/LanguageContext"
import Schedule from "@/pages/Schedule"
import type { User } from "@/types/User"
import type { ReactNode } from "react"

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
  id: 1,
  email: "student@example.com",
  full_name: "Test Student",
  role: "student",
  group_id: 1,
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
  totp_enrollments: [],
  mfa_challenges: [],
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

vi.mock("@/components/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

function renderSchedule() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })

  const result = render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <MemoryRouter initialEntries={["/schedule"]}>
          <Schedule />
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>
  )

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
        return { data: [{ id: 1, name: "CS-101" }] }
      }
      if (url === "/schedule/1") {
        return {
          data: [
            {
              id: 42,
              weekday: "Понедельник",
              parity: "odd",
              start_time: "2024-03-25T08:00:00",
              end_time: "2024-03-25T09:30:00",
              subject: "Linear Algebra",
              teacher: "Ada Lovelace",
              room: "101",
              lesson_type: "Лекция",
              group_id: 1,
            },
          ],
        }
      }
      throw new Error(`Unhandled GET ${url}`)
    })

    const { client } = renderSchedule()

    try {
      expect(await screen.findByText("My schedule")).toBeInTheDocument()
      expect(await screen.findByRole("columnheader", { name: "Monday" })).toBeInTheDocument()
      expect(await screen.findByText("Lecture")).toBeInTheDocument()
    } finally {
      client.clear()
    }
  })
})
