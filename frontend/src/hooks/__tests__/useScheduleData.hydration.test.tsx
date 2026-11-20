import { act } from "react"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { QueryClientProvider } from "@tanstack/react-query"
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client"
import { afterEach, expect, it, vi } from "vitest"
import api from "@/api/client"
import { pageScheduleQueryOptions, scheduleGroupsQueryOptions } from "@/api/hooks/schedule"
import {
  persistOptions,
  queryClient as browserClient,
  setQueryCacheIdentity,
} from "@/app/queryClient"
import { AuthProvider } from "@/contexts/AuthContext"
import { CampusTimezoneProvider } from "@/contexts/CampusTimezoneContext"
import { useScheduleData } from "@/hooks/useScheduleData"
import { getRouter } from "@/router"
import { Route as scheduleRoute } from "@/routes/_auth/schedule"
import { useAuthStore } from "@/stores/useAuthStore"

const groups = [{ id: "group-1", name: "Fixture Group" }]
const lessons = [
  {
    id: "lesson-1",
    group_id: "group-1",
    weekday: "monday",
    start_time: "09:00",
    end_time: "10:00",
    subject: "Fixture lesson",
    parity: "both",
  },
]
const user = {
  id: "fixture-user",
  role: "student",
  group_id: "group-1",
  full_name: "Fixture",
  email: "fixture@example.invalid",
}

function Probe() {
  const { selectedGroup, isLoading, rawSchedule } = useScheduleData()
  return (
    <div data-group={selectedGroup ?? "none"} data-loading={String(isLoading)}>
      {isLoading ? "loading" : `ready:${rawSchedule.length}`}
    </div>
  )
}

afterEach(() => {
  globalThis.__ssrAuthGetter__ = undefined
  browserClient.clear()
  setQueryCacheIdentity(null)
  useAuthStore.setState({ user: null, loading: true })
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  document.body.replaceChildren()
})

it.each(["cold", "cached"] as const)(
  "hydrates the unselected schedule tree with a %s browser cache without transferring schedule data",
  async (cacheState) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => undefined))
    )
    let server = true
    const apiGet = vi.spyOn(api, "get").mockImplementation(async (url) => {
      if (!server) return new Promise(() => undefined)
      if (url === "/users/me") return { data: user } as never
      if (url === "/groups") return { data: groups } as never
      if (url === "/schedule/group-1") return { data: lessons } as never
      throw new Error("unexpected request")
    })
    globalThis.__ssrAuthGetter__ = () => ({
      isAuth: true,
      user: { role: "student" },
      loading: false,
    })
    vi.stubEnv("SSR", true)
    const serverRouter = getRouter()
    const serverClient = serverRouter.options.context.queryClient
    const loader = scheduleRoute.options.loader
    if (typeof loader !== "function") throw new Error("missing schedule loader")
    await loader({ context: serverRouter.options.context } as never)
    expect(serverClient.getQueryData(scheduleGroupsQueryOptions().queryKey)).toEqual(groups)
    expect(serverClient.getQueryData(pageScheduleQueryOptions("group-1").queryKey)).toEqual(lessons)
    const dehydrate = serverRouter.options.dehydrate
    if (!dehydrate) throw new Error("missing router dehydration")
    const transferred = await dehydrate()
    expect(transferred.queries).toEqual([])
    expect(JSON.stringify(transferred)).not.toContain("Fixture")
    expect(JSON.stringify(transferred)).not.toContain("fixture-user")

    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window")!
    const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage")!
    Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: undefined })
    let html: string
    try {
      html = renderToString(
        <QueryClientProvider client={serverClient}>
          <CampusTimezoneProvider timeZone="UTC">
            <AuthProvider>
              <Probe />
            </AuthProvider>
          </CampusTimezoneProvider>
        </QueryClientProvider>
      )
      const priorGroupReads = apiGet.mock.calls.filter(([url]) => url === "/groups").length
      await serverClient.refetchQueries({
        queryKey: scheduleGroupsQueryOptions().queryKey,
        type: "all",
      })
      expect(apiGet.mock.calls.filter(([url]) => url === "/groups")).toHaveLength(
        priorGroupReads + 1
      )
      expect(serverClient.getQueryData(scheduleGroupsQueryOptions().queryKey)).toEqual(groups)
    } finally {
      Object.defineProperty(globalThis, "window", descriptor)
      Object.defineProperty(globalThis, "localStorage", storageDescriptor)
    }
    expect(html).toContain('data-group="none"')
    expect(html).toContain('data-loading="false"')
    expect(html).toContain("ready:0")
    const holder = document.createElement("div")
    holder.id = "root"
    holder.setAttribute("data-ssr-auth", "authenticated:student")
    holder.innerHTML = html
    document.body.append(holder)

    globalThis.__ssrAuthGetter__ = undefined
    vi.stubEnv("SSR", false)
    server = false
    browserClient.clear()
    if (cacheState === "cached") {
      browserClient.setQueryData(scheduleGroupsQueryOptions().queryKey, groups)
      browserClient.setQueryData(pageScheduleQueryOptions("group-1").queryKey, lessons)
    }
    const clientRouter = getRouter()
    const hydrate = clientRouter.options.hydrate as unknown as
      ((state: typeof transferred) => void | Promise<void>) | undefined
    if (!hydrate) throw new Error("missing router hydration")
    await hydrate(transferred)
    const errors: unknown[] = []
    let root: ReturnType<typeof hydrateRoot> | undefined
    await act(async () => {
      root = hydrateRoot(
        holder,
        <PersistQueryClientProvider client={browserClient} persistOptions={persistOptions}>
          <CampusTimezoneProvider timeZone="UTC">
            <AuthProvider>
              <Probe />
            </AuthProvider>
          </CampusTimezoneProvider>
        </PersistQueryClientProvider>,
        { onRecoverableError: (error) => errors.push(error) }
      )
      await Promise.resolve()
    })
    await act(async () => root?.unmount())
    expect(errors).toEqual([])
  }
)
