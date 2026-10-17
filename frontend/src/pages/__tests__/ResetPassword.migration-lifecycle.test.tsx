import { randomUUID } from "node:crypto"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {
  createBrowserHistory,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "../../i18n/config"
import ResetPassword from "../ResetPassword"
import { server } from "@/tests/mocks/server"
const typedValue = "Password123!"

const tAuth = (key: string) => i18n.t(`auth:${key}`)
const matchText = (text: string) => (content: string) => content.startsWith(text)

type ResetTestRouter = ReturnType<typeof createRouter>
type BeforeRender = (router: Pick<ResetTestRouter, "navigate">) => void

const passwordInput = () => screen.getByLabelText(matchText(tAuth("fields.password")))
const confirmInput = () => screen.getByLabelText(matchText(tAuth("fields.confirmPassword")))

function mockBreachRange() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("", { status: 200 }))
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(passwordInput(), "Password123!")
  await user.type(confirmInput(), "Password123!")
  await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))
}

async function renderPathResetRoute(initialPath: string, beforeRender?: BeforeRender) {
  const rootRoute = createRootRoute({ component: Outlet })
  const previousRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/previous",
    component: () => <div>previous page</div>,
  })
  const pageRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/reset-password",
    component: ResetPassword,
  })
  const tokenRoute = createRoute({
    getParentRoute: () => pageRoute,
    path: "$token",
    component: ResetPassword,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([previousRoute, pageRoute.addChildren([tokenRoute])]),
    history: createMemoryHistory({ initialEntries: ["/previous", initialPath] }),
  })
  await router.load()
  beforeRender?.(router)
  await router.load()
  render(<RouterProvider router={router} />)
  return router
}

async function renderQueryResetRoute(initialPath: string, beforeRender?: BeforeRender) {
  const rootRoute = createRootRoute({ component: Outlet })
  const previousRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/previous",
    component: () => <div>previous page</div>,
  })
  const pageRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/reset",
    component: ResetPassword,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([previousRoute, pageRoute]),
    history: createMemoryHistory({ initialEntries: ["/previous", initialPath] }),
  })
  await router.load()
  beforeRender?.(router)
  await router.load()
  render(<RouterProvider router={router} />)
  return router
}

async function renderBrowserQueryResetRoute(
  history: ReturnType<typeof createBrowserHistory>,
  beforeRender?: BeforeRender
) {
  const rootRoute = createRootRoute({ component: Outlet })
  const pageRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/reset",
    component: ResetPassword,
  })
  const router = createRouter({ routeTree: rootRoute.addChildren([pageRoute]), history })
  await router.load()
  beforeRender?.(router)
  await router.load()
  render(<RouterProvider router={router} />)
  return router
}

afterEach(() => {
  cleanup()
  server.resetHandlers()
  vi.restoreAllMocks()
})

describe("ResetPassword legacy migration lifecycle", () => {
  it("scrubs a path token after success when its initial migration rejects", async () => {
    const token = `lifecycle-${randomUUID()}`
    const payloads: unknown[] = []
    const navigationTargets: string[] = []
    let navigateCalls = 0
    let realNavigate: ResetTestRouter["navigate"] | undefined
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ ok: true })
      })
    )
    mockBreachRange()
    const user = userEvent.setup()
    const initialPath = `/reset-password/${token}`
    const router = await renderPathResetRoute(initialPath, (candidate) => {
      realNavigate = candidate.navigate.bind(candidate)
      vi.spyOn(candidate, "navigate").mockImplementation((options) => {
        navigationTargets.push(String((options as { to?: unknown }).to ?? ""))
        navigateCalls += 1
        if (navigateCalls === 1) return Promise.reject(new Error("initial migration rejected"))
        return realNavigate!(options)
      })
    })

    await screen.findByRole("button", { name: tAuth("reset.saveButton") })
    await waitFor(() => expect(navigateCalls).toBe(1))
    expect(router.state.location.pathname).toBe(initialPath)

    await fillAndSubmit(user)

    expect(await screen.findByText(tAuth("reset.successTitle"))).toBeInTheDocument()
    await waitFor(() => expect(router.state.location.pathname).toBe("/reset-password"))
    expect(navigationTargets).toEqual(["/reset-password", "/reset-password"])
    expect(router.state.location.search).not.toHaveProperty("token")
    expect(router.state.location.state).not.toHaveProperty("resetPasswordToken")
    expect(payloads).toEqual([{ password: typedValue, token }])
  })

  it("does not reuse a query token when its pending migration rejects after leaving the page", async () => {
    const token = `lifecycle-${randomUUID()}`
    const payloads: unknown[] = []
    let rejectMigration!: (reason?: unknown) => void
    let migrationStarted = false
    const pendingMigration = new Promise<void>((_resolve, reject) => {
      rejectMigration = reject
    })
    const handledMigration = pendingMigration.catch(() => undefined)
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        payloads.push(await request.json())
        return HttpResponse.json({ ok: true })
      })
    )
    mockBreachRange()
    const user = userEvent.setup()
    const router = await renderQueryResetRoute(`/reset?token=${token}`, (candidate) => {
      vi.spyOn(candidate, "navigate").mockImplementation(() => {
        migrationStarted = true
        return pendingMigration
      })
    })

    await waitFor(() => expect(migrationStarted).toBe(true))
    await screen.findByRole("button", { name: tAuth("reset.saveButton") })

    await act(async () => {
      router.history.push("/previous", {})
    })
    expect(await screen.findByText("previous page")).toBeInTheDocument()
    await act(async () => {
      await Promise.resolve()
    })
    await act(async () => {
      rejectMigration(new Error("migration rejected after unmount"))
      await handledMigration
    })

    await act(async () => {
      router.history.push("/reset", {})
    })
    await screen.findByRole("button", { name: tAuth("reset.saveButton") })
    expect(router.state.location.search).not.toHaveProperty("token")
    expect(router.state.location.state).not.toHaveProperty("resetPasswordToken")

    await fillAndSubmit(user)

    expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
    expect(payloads).toEqual([])
  })

  it.each([
    {
      name: "migration marker",
      missingMarker: true,
      missingKey: false,
      wrongIndex: false,
      query: false,
    },
    {
      name: "history key",
      missingMarker: false,
      missingKey: true,
      wrongIndex: false,
      query: false,
    },
    {
      name: "history index",
      missingMarker: false,
      missingKey: false,
      wrongIndex: true,
      query: false,
    },
    {
      name: "query token",
      missingMarker: false,
      missingKey: false,
      wrongIndex: false,
      query: true,
    },
  ])(
    "rejects a captured token after an unowned browser replacement with invalid $name metadata",
    async (invalidState) => {
      const token = `lifecycle-${randomUUID()}`
      const conflictingToken = `other-${randomUUID()}`
      const payloads: unknown[] = []
      const originalState = window.history.state
      const originalHref = `${window.location.pathname}${window.location.search}${window.location.hash}`
      let resolveMigration!: () => void
      let migrationStateOption: unknown
      const pendingMigration = new Promise<void>((resolve) => {
        resolveMigration = resolve
      })
      const handledMigration = pendingMigration.catch(() => undefined)
      window.history.replaceState(null, "", `/reset?token=${encodeURIComponent(token)}`)
      const history = createBrowserHistory()

      try {
        server.use(
          http.post("*/password/reset", async ({ request }) => {
            payloads.push(await request.json())
            return HttpResponse.json({ ok: true })
          })
        )
        mockBreachRange()
        const user = userEvent.setup()
        const router = await renderBrowserQueryResetRoute(history, (candidate) => {
          vi.spyOn(candidate, "navigate").mockImplementation((options) => {
            migrationStateOption = (options as { state?: unknown }).state
            return pendingMigration
          })
        })

        await waitFor(() => expect(migrationStateOption).toBeDefined())
        await screen.findByRole("button", { name: tAuth("reset.saveButton") })
        expect(typeof migrationStateOption).toBe("function")
        const sourceState = { ...router.history.location.state }
        const stateUpdater = migrationStateOption as (previous: unknown) => Record<string, unknown>
        const replacementState = { ...stateUpdater(sourceState) }
        let replacementHref = "/reset"

        if (invalidState.missingMarker || invalidState.wrongIndex) {
          const replacementKey = `external-${randomUUID()}`
          replacementState.key = replacementKey
          replacementState.__TSR_key = replacementKey
        }
        if (invalidState.missingMarker) delete replacementState.__resetPasswordMigration
        if (invalidState.missingKey) {
          delete replacementState.key
          delete replacementState.__TSR_key
        }
        if (invalidState.wrongIndex) {
          const sourceIndex = sourceState.__TSR_index
          expect(typeof sourceIndex).toBe("number")
          replacementState.__TSR_index = (sourceIndex as number) + 1
        }
        if (invalidState.query) {
          replacementHref = `/reset?token=${encodeURIComponent(conflictingToken)}`
        }

        // createBrowserHistory observes same-origin History API calls and reports
        // them as REPLACE events; this exercises the component's real observer.
        act(() => window.history.replaceState(replacementState, "", replacementHref))
        await waitFor(() => {
          expect(router.state.location.pathname).toBe("/reset")
          if (invalidState.query) {
            expect(router.state.location.search).toHaveProperty("token", conflictingToken)
          } else {
            expect(router.state.location.search).not.toHaveProperty("token")
          }
        })

        await act(async () => {
          resolveMigration()
          await handledMigration
        })
        expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
        await fillAndSubmit(user)

        expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
        expect(payloads).toEqual([])
      } finally {
        cleanup()
        history.destroy()
        window.history.replaceState(originalState, "", originalHref)
      }
    }
  )

  it("does not revive a query token when its pending migration completes after the 45-minute deadline", async () => {
    const token = `ttl-${randomUUID()}`
    const payloads: unknown[] = []
    let migrationStarted = false
    let completeMigration!: () => void
    let migrationSettled = false
    const pendingMigration = new Promise<void>((resolve) => {
      completeMigration = () => {
        migrationSettled = true
        resolve()
      }
    })
    const handledMigration = pendingMigration.catch(() => undefined)
    const initialTime = Date.now()
    let currentTime = initialTime
    const dateNowSpy = vi.spyOn(Date, "now").mockImplementation(() => currentTime)
    const browserTimers: Pick<Window, "setTimeout"> = window
    const originalSetTimeout = browserTimers.setTimeout.bind(browserTimers)
    const migrationExpiryTimers: Array<{
      scheduledAt: number
      delay: number
      callback: () => void
    }> = []
    const setTimeoutSpy = vi
      .spyOn(browserTimers, "setTimeout")
      .mockImplementation((handler, timeout, ...args) => {
        const delay = Number(timeout ?? 0)
        const timer = originalSetTimeout(handler, timeout, ...args)
        if (typeof handler === "function" && delay === 45 * 60 * 1000) {
          migrationExpiryTimers.push({
            scheduledAt: currentTime,
            delay,
            callback: () => Reflect.apply(handler, window, args),
          })
        }
        return timer
      })
    let router: Awaited<ReturnType<typeof renderQueryResetRoute>> | undefined

    try {
      server.use(
        http.post("*/password/reset", async ({ request }) => {
          payloads.push(await request.json())
          return HttpResponse.json({ ok: true })
        })
      )
      router = await renderQueryResetRoute(
        `/reset?token=${encodeURIComponent(token)}`,
        (candidate) => {
          vi.spyOn(candidate, "navigate").mockImplementation(() => {
            migrationStarted = true
            return pendingMigration
          })
        }
      )

      expect(migrationStarted).toBe(true)
      expect(screen.getByRole("button", { name: tAuth("reset.saveButton") })).toBeInTheDocument()
      expect(migrationExpiryTimers).toHaveLength(1)
      const expiry = migrationExpiryTimers[0]
      if (!expiry) throw new Error("Expected the captured legacy-token expiry timer")

      await act(async () => {
        currentTime = expiry.scheduledAt + expiry.delay
        expiry.callback()
        await Promise.resolve()
      })
      expect(screen.getByText(tAuth("reset.invalidLink"))).toBeInTheDocument()

      await act(async () => {
        completeMigration()
        await handledMigration
        await Promise.resolve()
      })
      expect(screen.getByText(tAuth("reset.invalidLink"))).toBeInTheDocument()

      setTimeoutSpy.mockRestore()
      dateNowSpy.mockRestore()
      mockBreachRange()
      const user = userEvent.setup()
      await fillAndSubmit(user)

      expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
      expect(payloads).toEqual([])
    } finally {
      cleanup()
      if (!migrationSettled) {
        completeMigration()
        await handledMigration
      }
      router?.history.destroy()
      setTimeoutSpy.mockRestore()
      dateNowSpy.mockRestore()
    }
  })

  it("does not reuse a legacy token after real history replacement during synchronous unmount", async () => {
    const token = `unmount-${randomUUID()}`
    const payloads: unknown[] = []
    const originalState = window.history.state
    const originalHref = `${window.location.pathname}${window.location.search}${window.location.hash}`
    let completeMigration!: () => void
    let migrationSettled = false
    let migrationStateOption: unknown
    const pendingMigration = new Promise<void>((resolve) => {
      completeMigration = () => {
        migrationSettled = true
        resolve()
      }
    })
    const handledMigration = pendingMigration.catch(() => undefined)
    let history: ReturnType<typeof createBrowserHistory> | undefined
    let remountedHistory: ReturnType<typeof createBrowserHistory> | undefined

    try {
      server.use(
        http.post("*/password/reset", async ({ request }) => {
          payloads.push(await request.json())
          return HttpResponse.json({ ok: true })
        })
      )
      mockBreachRange()
      window.history.replaceState(null, "", `/reset?token=${encodeURIComponent(token)}`)
      history = createBrowserHistory()
      await renderBrowserQueryResetRoute(history, (candidate) => {
        vi.spyOn(candidate, "navigate").mockImplementation((options) => {
          migrationStateOption = (options as { state?: unknown }).state
          return pendingMigration
        })
      })

      await waitFor(() => expect(migrationStateOption).toBeDefined())
      await screen.findByRole("button", { name: tAuth("reset.saveButton") })
      expect(typeof migrationStateOption).toBe("function")
      const stateUpdater = migrationStateOption as (previous: unknown) => Record<string, unknown>
      const sourceState = { ...history.location.state }
      const replacementState = { ...stateUpdater(sourceState) }
      expect(typeof sourceState.__TSR_index).toBe("number")
      expect(replacementState.__resetPasswordMigration).toBeDefined()
      expect(replacementState.__TSR_index).toBe(sourceState.__TSR_index)

      act(() => {
        cleanup()
        window.history.replaceState(replacementState, "", "/reset")
      })
      expect(history.location.pathname).toBe("/reset")
      expect(new URLSearchParams(history.location.search).has("token")).toBe(false)
      expect(history.location.state.__TSR_index).toBe(sourceState.__TSR_index)
      await act(async () => {
        await Promise.resolve()
      })

      await act(async () => {
        completeMigration()
        await handledMigration
        await Promise.resolve()
      })
      expect(payloads).toEqual([])

      history.destroy()
      history = undefined
      remountedHistory = createBrowserHistory()
      const remountedRouter = await renderBrowserQueryResetRoute(remountedHistory)
      expect(remountedRouter.state.location.pathname).toBe("/reset")
      expect(remountedRouter.state.location.search).not.toHaveProperty("token")
      expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
      const user = userEvent.setup()
      await fillAndSubmit(user)

      expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
      expect(payloads).toEqual([])
    } finally {
      cleanup()
      if (!migrationSettled) {
        completeMigration()
        await handledMigration
      }
      history?.destroy()
      remountedHistory?.destroy()
      window.history.replaceState(originalState, "", originalHref)
    }
  })
  it("expires a captured query token when the public navigation boundary crosses its deadline before the expiry effect", async () => {
    const token = `clock-jump-${randomUUID()}`
    const payloads: unknown[] = []
    let migrationStarted = false
    let completeMigration!: () => void
    let migrationSettled = false
    const pendingMigration = new Promise<void>((resolve) => {
      completeMigration = () => {
        migrationSettled = true
        resolve()
      }
    })
    const handledMigration = pendingMigration.catch(() => undefined)
    const initialTime = Date.now()
    let currentTime = initialTime
    const dateNowSpy = vi.spyOn(Date, "now").mockImplementation(() => currentTime)
    const scheduledExpiryDelays: number[] = []
    const browserTimers: Pick<Window, "setTimeout"> = window
    const originalSetTimeout = browserTimers.setTimeout.bind(browserTimers)
    const setTimeoutSpy = vi
      .spyOn(browserTimers, "setTimeout")
      .mockImplementation((handler, timeout, ...args) => {
        const delay = Number(timeout ?? 0)
        if (typeof handler === "function" && delay === 45 * 60 * 1000) {
          scheduledExpiryDelays.push(delay)
        }
        return originalSetTimeout(handler, timeout, ...args)
      })
    let router: Awaited<ReturnType<typeof renderQueryResetRoute>> | undefined

    try {
      server.use(
        http.post("*/password/reset", async ({ request }) => {
          payloads.push(await request.json())
          return HttpResponse.json({ ok: true })
        })
      )
      router = await renderQueryResetRoute(
        `/reset?token=${encodeURIComponent(token)}`,
        (candidate) => {
          vi.spyOn(candidate, "navigate").mockImplementation(() => {
            migrationStarted = true
            // The migration effect has captured the token but React has not yet
            // committed that state to the separate expiry effect.
            currentTime = initialTime + 45 * 60 * 1000 + 1
            return pendingMigration
          })
        }
      )

      await waitFor(() => expect(migrationStarted).toBe(true))
      await waitFor(() => expect(screen.getByText(tAuth("reset.invalidLink"))).toBeInTheDocument())
      expect(router.state.location.search).toHaveProperty("token", token)
      expect(currentTime).toBe(initialTime + 45 * 60 * 1000 + 1)
      expect(scheduledExpiryDelays).toEqual([])

      mockBreachRange()
      const user = userEvent.setup()
      await fillAndSubmit(user)
      expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
      expect(payloads).toEqual([])
    } finally {
      try {
        cleanup()
      } finally {
        try {
          if (!migrationSettled) {
            completeMigration()
            await handledMigration
          }
        } finally {
          router?.history.destroy()
          setTimeoutSpy.mockRestore()
          dateNowSpy.mockRestore()
        }
      }
    }
  })
})
