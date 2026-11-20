import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import {
  IsRestoringProvider,
  QueryClient,
  QueryClientProvider,
  onlineManager,
} from "@tanstack/react-query"
import { pageScheduleQueryOptions, scheduleGroupsQueryOptions } from "@/api/hooks/schedule"
import Schedule from "@/pages/Schedule"
import type { User } from "@/types/User"
import type { ComponentType, ReactNode } from "react"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { LazyMotion, domAnimation } from "framer-motion"
import {
  Outlet,
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"
import { AppShellProvider } from "@/contexts/AppShellContext"
import { CampusTimezoneProvider } from "@/contexts/CampusTimezoneContext"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
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

vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: async () => ({
    schedule: { bulkUpsert: async () => {} },
    notes: { find: () => ({ exec: async () => [] }) },
  }),
}))

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

const apiGetMock = apiMocks.get

function setScheduleViewport(viewport: "desktop" | "mobile") {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: viewport === "mobile" && query.startsWith("(max-width:"),
      addEventListener: () => {},
      removeEventListener: () => {},
    }))
  )
}

async function renderSchedule(Page: ComponentType = Schedule) {
  useAuthStore.setState({ user: authState.user, loading: authState.loading })
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  const result = await renderWithRouter({
    ui: Page,
    path: "/schedule",
    initialPath: "/schedule",
    queryClient: client,
  })

  return { client, ...result }
}

describe("Schedule cache handling", () => {
  beforeEach(() => {
    localStorage.clear()
    acceptBrowserSessionGeneration()
    useAuthStore.setState({ user: null, loading: true })
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
    useAuthStore.setState({ user: null, loading: true })
    vi.unstubAllGlobals()
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
            parity: "both",
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
              parity: "both",
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

  it("keeps the focused mobile day mounted while a newly selected group loads", async () => {
    setScheduleViewport("mobile")
    authState.user = { ...baseUser, role: "teacher" }
    let finishGroup = () => {}
    const pendingGroup = new Promise<{ data: never[] }>((resolve) => {
      finishGroup = () => resolve({ data: [] })
    })
    apiGetMock.mockImplementation(async (url: string) => {
      if (url === "/groups") {
        return {
          data: [
            { id: "group-1", name: "First group" },
            { id: "group-2", name: "Second group" },
          ],
        }
      }
      if (url === "/schedule/group-1")
        return {
          data: [
            {
              id: "first-lesson",
              weekday: "Monday",
              parity: "both",
              start_time: "09:00",
              end_time: "10:00",
              subject: "First group subject",
              teacher: "Teacher",
              room: "101",
              lesson_type: "lecture",
              group_id: "group-1",
            },
          ],
        }
      if (url === "/schedule/group-2") return pendingGroup
      throw new Error(`Unhandled GET ${url}`)
    })
    const { client, unmount } = await renderSchedule()
    try {
      const tab = await screen.findByRole("tab", { selected: true })
      expect(await screen.findByText("First group subject")).toBeInTheDocument()
      const status = tab.closest("section")?.querySelector(':scope > [role="status"]')
      expect(status).toHaveClass("sr-only")
      expect(status).toBeEmptyDOMElement()
      fireEvent.click(screen.getByRole("combobox"))
      const nextGroup = await screen.findByRole("option", { name: "Second group" })
      tab.focus()
      expect(tab).toHaveFocus()
      fireEvent.mouseDown(nextGroup, { button: 0 })
      await waitFor(() =>
        expect(apiGetMock).toHaveBeenCalledWith("/schedule/group-2", expect.anything())
      )
      expect(screen.getByRole("tab", { selected: true })).toBe(tab)
      expect(tab).toHaveFocus()
      expect(tab.closest('[aria-busy="true"]')).not.toBeNull()
      expect(screen.queryByText("First group subject")).not.toBeInTheDocument()
      expect(screen.getByText("Loading…")).toBe(status)
      await act(async () => {
        finishGroup()
        await pendingGroup
      })
      await waitFor(() => expect(screen.getByRole("tab", { selected: true })).toBe(tab))
      await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument())
      expect(status).toBeEmptyDOMElement()
      expect(tab).toHaveFocus()
    } finally {
      unmount()
      client.clear()
    }
  })

  it("keeps the initial skeleton until a confirmed user's empty group list is settled", async () => {
    useAuthStore.setState({ user: baseUser, loading: false })
    expect(getConfirmedUserId(useAuthStore.getState())).toBe(baseUser.id)
    setScheduleViewport("mobile")
    let finishGroups = () => {}
    const pendingGroups = new Promise<{ data: never[] }>((resolve) => {
      finishGroups = () => resolve({ data: [] })
    })
    apiGetMock.mockImplementation(async (url: string) => {
      if (url === "/groups") return pendingGroups
      throw new Error(`Unhandled GET ${url}`)
    })
    const { client, unmount } = await renderSchedule()
    try {
      expect(screen.queryByRole("tab")).not.toBeInTheDocument()
      await act(async () => {
        finishGroups()
        await pendingGroups
      })
      expect(await screen.findByRole("tab", { selected: true })).toBeInTheDocument()
      expect(apiGetMock).toHaveBeenCalledTimes(1)
      expect(screen.queryByText("Loading…")).not.toBeInTheDocument()
    } finally {
      unmount()
      client.clear()
    }
  })

  it.each(["anonymous", "unconfirmed"] as const)(
    "does not introduce a skeleton when restoration leaves an unstarted query idle for an %s identity",
    async (identity) => {
      setScheduleViewport("mobile")
      authState.user = identity === "anonymous" ? null : { ...baseUser, id: "ssr-stub" }
      authState.loading = identity === "unconfirmed"
      useAuthStore.setState({ user: authState.user, loading: authState.loading })
      expect(getConfirmedUserId(useAuthStore.getState())).toBeNull()
      const RestoringPage = () => (
        <IsRestoringProvider value={true}>
          <Schedule />
        </IsRestoringProvider>
      )
      const { client, unmount } = await renderSchedule(RestoringPage)
      try {
        const tab = await screen.findByRole("tab", { selected: true })
        expect(tab).toBeInTheDocument()
        expect(tab.closest(`[aria-busy="${identity === "unconfirmed"}"]`)).not.toBeNull()
        expect(apiGetMock).not.toHaveBeenCalled()
        if (identity === "unconfirmed") {
          expect(screen.getByText("Loading…")).toHaveAttribute("role", "status")
        } else {
          expect(screen.queryByText("Loading…")).not.toBeInTheDocument()
        }
      } finally {
        unmount()
        client.clear()
      }
    }
  )

  it.each(["student", "anonymous"] as const)(
    "keeps the %s offline fallback available while groups are paused",
    async (identity) => {
      setScheduleViewport("mobile")
      authState.user = identity === "anonymous" ? null : { ...baseUser }
      useAuthStore.setState({ user: authState.user, loading: false })
      expect(getConfirmedUserId(useAuthStore.getState())).toBe(
        identity === "anonymous" ? null : baseUser.id
      )
      onlineManager.setOnline(false)
      const { client, unmount } = await renderSchedule()
      try {
        const tab = await screen.findByRole("tab", { selected: true })
        expect(tab.closest('[aria-busy="false"]')).not.toBeNull()
        expect(apiGetMock).not.toHaveBeenCalled()
      } finally {
        unmount()
        client.clear()
        onlineManager.setOnline(true)
      }
    }
  )

  it("keeps the focused day usable while cached schedule data revalidates", async () => {
    setScheduleViewport("mobile")
    let requests = 0
    let finishRevalidation = () => {}
    const pendingRevalidation = new Promise<{ data: never[] }>((resolve) => {
      finishRevalidation = () => resolve({ data: [] })
    })
    apiGetMock.mockImplementation(async (url: string) => {
      if (url === "/groups") return { data: [{ id: "group-1", name: "First group" }] }
      if (url === "/schedule/group-1") return ++requests === 1 ? { data: [] } : pendingRevalidation
      throw new Error(`Unhandled GET ${url}`)
    })
    const { client, unmount } = await renderSchedule()
    try {
      const tab = await screen.findByRole("tab", { selected: true })
      tab.focus()
      let revalidation: Promise<void> | undefined
      act(() => {
        revalidation = client.invalidateQueries({
          queryKey: pageScheduleQueryOptions("group-1").queryKey,
        })
      })
      await waitFor(() => expect(requests).toBe(2))
      expect(screen.getByRole("tab", { selected: true })).toBe(tab)
      expect(tab).toHaveFocus()
      expect(tab.closest('[aria-busy="false"]')).not.toBeNull()
      expect(screen.queryByText("Loading…")).not.toBeInTheDocument()
      await act(async () => {
        finishRevalidation()
        await revalidation
      })
      expect(screen.getByRole("tab", { selected: true })).toBe(tab)
      expect(tab).toHaveFocus()
    } finally {
      unmount()
      client.clear()
    }
  })

  it.each([
    ["desktop", "cold"],
    ["desktop", "cached"],
    ["mobile", "cold"],
    ["mobile", "cached"],
  ] as const)(
    "hydrates the schedule markup without recovery at the %s viewport with a %s cache",
    async (viewport, cache) => {
      setScheduleViewport(viewport)
      const serverClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      serverClient.setQueryData(scheduleGroupsQueryOptions().queryKey, [
        { id: "group-1", name: "First group" },
      ])
      const browserClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      if (cache === "cached") {
        browserClient.setQueryData(scheduleGroupsQueryOptions().queryKey, [
          { id: "group-1", name: "First group" },
        ])
        browserClient.setQueryData(pageScheduleQueryOptions("group-1").queryKey, [])
      }
      const createScheduleRouter = async (client: QueryClient) => {
        const rootRoute = createRootRoute({ component: () => <Outlet /> })
        const route = createRoute({
          getParentRoute: () => rootRoute,
          path: "/schedule",
          component: Schedule,
        })
        const router = createRouter({
          routeTree: rootRoute.addChildren([route]),
          history: createMemoryHistory({ initialEntries: ["/schedule"] }),
          context: {
            auth: { isAuth: true, user: authState.user, loading: false },
            queryClient: client,
          },
        })
        await router.load()
        return router
      }
      const serverRouter = await createScheduleRouter(serverClient)
      const browserRouter = await createScheduleRouter(browserClient)
      const renderTree = (client: QueryClient, router: typeof serverRouter, restoring: boolean) => (
        <QueryClientProvider client={client}>
          <IsRestoringProvider value={restoring}>
            <LanguageProvider>
              <LazyMotion features={domAnimation}>
                <AppShellProvider>
                  <CampusTimezoneProvider timeZone="UTC">
                    <RouterProvider router={router as never} />
                  </CampusTimezoneProvider>
                </AppShellProvider>
              </LazyMotion>
            </LanguageProvider>
          </IsRestoringProvider>
        </QueryClientProvider>
      )
      const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window")!
      Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
      let html: string
      try {
        html = renderToString(renderTree(serverClient, serverRouter, false))
      } finally {
        Object.defineProperty(globalThis, "window", descriptor)
      }
      const holder = document.createElement("div")
      holder.innerHTML = html
      document.body.append(holder)
      const errors: unknown[] = []
      let root: ReturnType<typeof hydrateRoot> | undefined
      try {
        await act(async () => {
          root = hydrateRoot(holder, renderTree(browserClient, browserRouter, true), {
            onRecoverableError: (error) => errors.push(error),
          })
        })
        if (viewport === "mobile")
          await waitFor(() =>
            expect(holder.querySelector('[role="tab"][aria-selected="true"]')).not.toBeNull()
          )
        else expect(holder.querySelector('[role="grid"]')).not.toBeNull()
        expect(errors).toEqual([])
      } finally {
        await act(async () => root?.unmount())
        holder.remove()
        serverClient.clear()
        browserClient.clear()
      }
    }
  )
})
