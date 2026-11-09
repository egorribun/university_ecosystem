import { act, waitFor } from "@testing-library/react"
import { createRoot } from "react-dom/client"
import { createMemoryHistory, createRouter, Outlet, RouterProvider } from "@tanstack/react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import { routeTree } from "@/routeTree.gen"

type TestRoute = {
  id: string
  fullPath?: string
  children?: TestRoute[]
  update: (options: Record<string, unknown>) => TestRoute
}

const publicPages = [
  { path: "/login", routeId: "/_public/login", titleKey: "auth:login.title" },
  { path: "/forgot-password", routeId: "/_public/forgot-password", titleKey: "auth:forgot.title" },
  { path: "/register", routeId: "/_public/register", titleKey: "auth:register.title" },
  { path: "/reset-password", routeId: "/_public/reset-password", titleKey: "auth:reset.title" },
  {
    path: "/reset-password/audit-token",
    routeId: "/_public/reset-password/$token",
    titleKey: "auth:reset.title",
  },
] as const

const authenticatedPages = [
  { path: "/settings", routeId: "/_auth/settings", titleKey: "settings:page.title" },
  { path: "/map", routeId: "/_auth/map", titleKey: "system:map.title" },
  { path: "/messenger", routeId: "/_auth/messenger", titleKey: "messenger:title" },
  {
    path: "/messenger/audit-chat",
    routeId: "/_auth/messenger/$chatId",
    titleKey: "messenger:title",
  },
] as const

const testRoutePaths = new Set([
  "/login",
  "/forgot-password",
  "/register",
  "/reset-password",
  "/reset-password/$token",
  "/settings",
  "/map",
  "/messenger",
  "/messenger/$chatId",
  "/dashboard",
])

const TestRoot = () => <Outlet />
const EmptyPage = () => null
const titleFor = (key: string) => `${i18n.t(key)} | University Ecosystem`

function prepareGeneratedRouteTree(): void {
  const routeTreeForTest = routeTree as unknown as TestRoute
  const visited = new Set<TestRoute>()
  const visit = (route: TestRoute) => {
    if (visited.has(route)) return
    visited.add(route)

    if (route === routeTreeForTest) {
      route.update({ component: TestRoot, loader: undefined })
    } else if (testRoutePaths.has(route.fullPath ?? "")) {
      route.update({ component: EmptyPage, loader: undefined, beforeLoad: undefined })
    } else {
      route.update({ loader: undefined })
    }

    for (const child of route.children ?? []) visit(child)
  }
  visit(routeTreeForTest)
}

let previousStaticMountMarker: unknown
let mountedRoot: ReturnType<typeof createRoot> | undefined

beforeEach(async () => {
  previousStaticMountMarker = Reflect.get(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__")
  Reflect.set(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__", true)
  useAuthStore.setState({ user: null, loading: false })
  await act(async () => {
    await i18n.changeLanguage("en")
  })
})

afterEach(() => {
  if (mountedRoot) {
    act(() => mountedRoot?.unmount())
    mountedRoot = undefined
  }
  if (previousStaticMountMarker === undefined) {
    Reflect.deleteProperty(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__")
  } else {
    Reflect.set(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__", previousStaticMountMarker)
  }
})

describe("page titles on the generated router", () => {
  it("localizes all nine generated route IDs and clears the title on navigation", async () => {
    const router = createRouter({
      routeTree: routeTree as never,
      history: createMemoryHistory({ initialEntries: ["/login"] }),
      context: {} as never,
    })
    prepareGeneratedRouteTree()
    await router.load()
    const root = createRoot(document)
    mountedRoot = root
    await act(async () => {
      root.render(<RouterProvider router={router as never} />)
    })

    const expectPage = async (
      page: (typeof publicPages)[number] | (typeof authenticatedPages)[number]
    ) => {
      await waitFor(() => {
        expect(router.state.matches.at(-1)?.routeId.toString()).toBe(page.routeId)
        expect(document.title).toBe(titleFor(page.titleKey))
      })
    }
    const navigatePages = async (pages: readonly (typeof publicPages)[number][]) => {
      for (const page of pages) {
        await act(async () => {
          await router.navigate({ to: page.path as never } as never)
        })
        await expectPage(page)
      }
    }

    await expectPage(publicPages[0])
    await navigatePages(publicPages)
    await act(async () => {
      await i18n.changeLanguage("ru")
    })
    await waitFor(() => expect(document.title).toBe(titleFor(publicPages.at(-1)!.titleKey)))
    await navigatePages(publicPages)

    act(() =>
      useAuthStore.setState({ user: { id: "title-test-user" } as UserState, loading: false })
    )
    await waitFor(() =>
      expect(router.state.matches.at(-1)?.routeId.toString()).toBe("/_auth/dashboard")
    )
    await act(async () => {
      await router.navigate({ to: "/settings" as never } as never)
    })
    await expectPage(authenticatedPages[0])
    for (const page of authenticatedPages.slice(1)) {
      await act(async () => {
        await router.navigate({ to: page.path as never } as never)
      })
      await expectPage(page)
    }

    await act(async () => {
      await i18n.changeLanguage("en")
    })
    await waitFor(() => expect(document.title).toBe(titleFor(authenticatedPages.at(-1)!.titleKey)))
    for (const page of authenticatedPages) {
      await act(async () => {
        await router.navigate({ to: page.path as never } as never)
      })
      await expectPage(page)
    }

    await act(async () => {
      await router.navigate({ to: "/dashboard" as never } as never)
    })
    await waitFor(() =>
      expect(router.state.matches.at(-1)?.routeId.toString()).toBe("/_auth/dashboard")
    )
    await waitFor(() => expect(document.title).not.toContain(i18n.t("messenger:title")))
  })
})
