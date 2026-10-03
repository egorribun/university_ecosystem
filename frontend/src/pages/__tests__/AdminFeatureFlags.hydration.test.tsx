import type { ComponentType } from "react"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import type { QueryClient } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client"
import { createQueryClient, persistOptions } from "@/app/queryClient"
import { AppProviders } from "@/AppProviders"
import i18n from "@/i18n/config"
import { useAuthStore } from "@/stores/useAuthStore"
import { server } from "@/tests/mocks/server"
import AdminFeatureFlags from "../AdminFeatureFlags"
import { testUser } from "@/tests/mocks/handlers"
import { currentUserQueryKey } from "@/api/hooks/users"

const clients: QueryClient[] = []

// Match the root route’s provider chain, including the identity-gated
// persister. The generic page helper omits persistence and the SSR marker.
async function renderAdminPage(Component: ComponentType, path: string) {
  const client = createQueryClient()
  clients.push(client)
  const rootRoute = createRootRoute({
    component: () => (
      <AppProviders>
        <Outlet />
      </AppProviders>
    ),
  })
  const route = createRoute({
    getParentRoute: () => rootRoute,
    path,
    component: () => <Component />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([route]),
    history: createMemoryHistory({ initialEntries: [path] }),
    context: { queryClient: client, auth: { isAuth: false, user: null, loading: false } },
  })
  await router.load()
  render(
    <PersistQueryClientProvider client={client} persistOptions={persistOptions}>
      <RouterProvider router={router as never} />
    </PersistQueryClientProvider>
  )
  return client
}

describe("AdminFeatureFlags authenticated SSR bootstrap", () => {
  beforeEach(async () => {
    document.body.innerHTML = '<div id="root" data-ssr-auth="authenticated:admin"></div>'
    localStorage.clear()
    sessionStorage.clear()
    localStorage.setItem("ue:language", "ru")
    await i18n.changeLanguage("ru")
    useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
  })
  afterEach(() => {
    cleanup()
    useAuthStore.setState({ user: null, loading: false })
    document.getElementById("root")?.remove()
    clients.splice(0).forEach((client) => client.clear())
    localStorage.clear()
  })
  it("fetches the real profile before restoring private queries and loading diagnostics", async () => {
    let releaseProfile!: () => void
    const profileReady = new Promise<void>((resolve) => {
      releaseProfile = resolve
    })
    let profileRequested = false
    let flagsRequested = false
    server.use(
      http.get("*/users/me", async () => {
        profileRequested = true
        await profileReady
        return HttpResponse.json({ ...testUser, role: "admin" })
      }),
      http.get("*/admin/feature-flags", () => {
        flagsRequested = true
        return HttpResponse.json([])
      })
    )

    try {
      const client = await renderAdminPage(AdminFeatureFlags, "/admin/feature-flags")
      await waitFor(() => expect(profileRequested).toBe(true))
      // Keep the SSR role available for the initial render, but do not let
      // that placeholder satisfy /users/me or unlock persisted private data.
      expect(useAuthStore.getState().user?.id).toBe("ssr-stub")
      expect(client.getQueryData(currentUserQueryKey)).toBeUndefined()
      expect(flagsRequested).toBe(false)

      releaseProfile()
      await waitFor(() => expect(useAuthStore.getState().user?.id).toBe(testUser.id))
      expect(useAuthStore.getState().user?.role).toBe("admin")
      expect(
        await screen.findByRole("heading", {
          level: 1,
          name: "Диагностика флагов функций",
        })
      ).toBeVisible()
      expect(flagsRequested).toBe(true)
      expect(screen.getByText(i18n.t("admin:featureFlags.empty.title"))).toBeVisible()
    } finally {
      releaseProfile()
    }
  })
})
