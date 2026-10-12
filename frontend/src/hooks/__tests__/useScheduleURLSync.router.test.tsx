import { StrictMode } from "react"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import * as v from "valibot"

import { useScheduleURLSync } from "@/hooks/useScheduleURLSync"
import { scheduleSearchSchema } from "@/features/schedule/schema"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"

const MAX_FORWARDED_NAVIGATIONS = 8
const MAX_STORE_SYNC_WRITES = 8

type DeferredLoad = {
  promise: Promise<void>
  resolve: () => void
}

type NavigationGuard = {
  forwardedWrites: number
  storeSyncWrites: number
  limitReached: boolean
}

function createDeferredLoad(): DeferredLoad {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  const gate = { promise, resolve }
  activeLoadGates.push(gate)
  return gate
}

function ScheduleSyncProbe() {
  useScheduleURLSync()
  const weekOffset = useScheduleUIStore((state) => state.weekOffset)

  return (
    <>
      <output data-testid="week-offset">{weekOffset}</output>
      <button type="button" onClick={() => useScheduleUIStore.getState().nextWeek()}>
        Next week
      </button>
    </>
  )
}

const subscriptions: Array<() => void> = []
const activeLoadGates: DeferredLoad[] = []
const activeRouters: Array<{ state: { status: string } }> = []
const restoreStoreActions: Array<() => void> = []

async function mountSchedule(
  initialPath: string,
  loaderGates: ReadonlyMap<number, DeferredLoad> = new Map()
) {
  const rootRoute = createRootRoute()
  const scheduleRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/schedule",
    validateSearch: (search: Record<string, unknown>) => v.parse(scheduleSearchSchema, search),
    loaderDeps: ({ search }) => ({ week: search.w ?? 0 }),
    loader: async ({ deps }) => {
      await loaderGates.get(deps.week)?.promise
    },
    component: ScheduleSyncProbe,
  })
  const history = createMemoryHistory({ initialEntries: [initialPath] })
  const guard: NavigationGuard = {
    forwardedWrites: 0,
    storeSyncWrites: 0,
    limitReached: false,
  }
  const originalPush = history.push.bind(history)
  const originalReplace = history.replace.bind(history)

  history.push = (path, state, options) => {
    if (guard.forwardedWrites >= MAX_FORWARDED_NAVIGATIONS) {
      guard.limitReached = true
      return
    }
    guard.forwardedWrites += 1
    originalPush(path, state, options)
  }
  history.replace = (path, state, options) => {
    if (guard.forwardedWrites >= MAX_FORWARDED_NAVIGATIONS) {
      guard.limitReached = true
      return
    }
    guard.forwardedWrites += 1
    originalReplace(path, state, options)
  }

  const router = createRouter({
    routeTree: rootRoute.addChildren([scheduleRoute]),
    history,
  })

  const originalSetWeekOffset = useScheduleUIStore.getState().setWeekOffset
  useScheduleUIStore.setState({
    setWeekOffset: (offset) => {
      if (guard.storeSyncWrites >= MAX_STORE_SYNC_WRITES) {
        guard.limitReached = true
        return
      }
      guard.storeSyncWrites += 1
      originalSetWeekOffset(offset)
    },
  })
  restoreStoreActions.push(() =>
    useScheduleUIStore.setState({ setWeekOffset: originalSetWeekOffset })
  )
  await router.load()
  activeRouters.push(router)

  const historyChanges: string[] = []
  subscriptions.push(
    history.subscribe(({ location }) => {
      historyChanges.push(location.href)
    })
  )

  render(
    <StrictMode>
      <RouterProvider router={router as never} />
    </StrictMode>
  )

  return { router, historyChanges, guard }
}

async function expectSynchronizedWeek(
  router: {
    state: {
      location: { search: unknown }
      status: string
    }
  },
  guard: NavigationGuard,
  offset: number
) {
  await waitFor(() => {
    expect(guard.limitReached).toBe(false)
    expect(screen.getByTestId("week-offset")).toHaveTextContent(String(offset))
    expect(router.state.location.search).toEqual(offset === 0 ? {} : { w: offset })
    expect(router.state.status).toBe("idle")
  })
}

describe("schedule URL week synchronization through the real router", () => {
  beforeEach(() => {
    useScheduleUIStore.setState({ weekOffset: 0 })
  })

  afterEach(async () => {
    cleanup()
    activeLoadGates.splice(0).forEach((gate) => gate.resolve())
    await Promise.all(
      activeRouters
        .splice(0)
        .map((router) => waitFor(() => expect(router.state.status).toBe("idle")))
    )
    subscriptions.splice(0).forEach((unsubscribe) => unsubscribe())
    restoreStoreActions.splice(0).forEach((restore) => restore())
    useScheduleUIStore.setState({ weekOffset: 0 })
  })

  it("preserves the shared week in StrictMode and follows only the side that changed", async () => {
    const user = userEvent.setup()
    const { router, historyChanges, guard } = await mountSchedule("/schedule?w=2")

    await expectSynchronizedWeek(router, guard, 2)
    expect(historyChanges).toEqual([])
    expect(guard.forwardedWrites).toBe(0)

    await user.click(screen.getByRole("button", { name: "Next week" }))
    await expectSynchronizedWeek(router, guard, 3)
    expect(historyChanges).toHaveLength(1)
    expect(guard.forwardedWrites).toBe(1)

    await act(async () => {
      await router.navigate({ to: "/schedule", search: { w: -2 } } as never)
    })
    await expectSynchronizedWeek(router, guard, -2)
    expect(historyChanges).toHaveLength(2)
    expect(guard.forwardedWrites).toBe(2)

    await user.click(screen.getByRole("button", { name: "Next week" }))
    await expectSynchronizedWeek(router, guard, -1)
    expect(historyChanges).toHaveLength(3)
    expect(guard.forwardedWrites).toBe(3)

    await act(async () => {
      await router.navigate({ to: "/schedule", search: {} } as never)
    })
    await expectSynchronizedWeek(router, guard, 0)
    expect(historyChanges).toHaveLength(4)
    expect(guard.forwardedWrites).toBe(4)
  })

  it("does not write on mount when the URL and store already agree", async () => {
    useScheduleUIStore.setState({ weekOffset: 3 })
    const { router, historyChanges, guard } = await mountSchedule("/schedule?w=3")

    await expectSynchronizedWeek(router, guard, 3)
    expect(historyChanges).toEqual([])
    expect(guard.forwardedWrites).toBe(0)
  })

  it("keeps the latest store value when an earlier router load is still pending", async () => {
    const earlierLoad = createDeferredLoad()
    const latestLoad = createDeferredLoad()
    const { router, historyChanges, guard } = await mountSchedule(
      "/schedule",
      new Map([
        [1, earlierLoad],
        [2, latestLoad],
      ])
    )

    expect(historyChanges).toEqual([])
    expect(guard.forwardedWrites).toBe(0)

    await act(async () => {
      useScheduleUIStore.getState().setWeekOffset(1)
    })
    await waitFor(() => {
      expect(guard.limitReached).toBe(false)
      expect(router.state.status).toBe("pending")
      expect(router.state.location.search).toEqual({ w: 1 })
      expect(historyChanges).toHaveLength(1)
    })

    await act(async () => {
      useScheduleUIStore.getState().setWeekOffset(2)
    })
    await waitFor(() => {
      expect(guard.limitReached).toBe(false)
      expect(router.state.status).toBe("pending")
      expect(router.state.location.search).toEqual({ w: 2 })
      expect(historyChanges).toHaveLength(2)
      expect(screen.getByTestId("week-offset")).toHaveTextContent("2")
    })

    await act(async () => {
      earlierLoad.resolve()
    })
    await waitFor(() => {
      expect(guard.limitReached).toBe(false)
      expect(router.state.status).toBe("pending")
      expect(router.state.location.search).toEqual({ w: 2 })
      expect(router.state.resolvedLocation?.search).not.toEqual({ w: 1 })
      expect(screen.getByTestId("week-offset")).toHaveTextContent("2")
    })

    await act(async () => {
      latestLoad.resolve()
    })
    await expectSynchronizedWeek(router, guard, 2)
    expect(historyChanges).toHaveLength(2)
    expect(guard.forwardedWrites).toBe(2)
  })
})
