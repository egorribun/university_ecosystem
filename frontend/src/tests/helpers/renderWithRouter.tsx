import type { ComponentType } from "react"
import { render, type RenderResult } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { LazyMotion, domAnimation } from "framer-motion"

import { AuthProvider } from "@/contexts/AuthContext"
import { LanguageProvider } from "@/contexts/LanguageContext"

/**
 * Shared test helper for mounting components under a TanStack Router memory
 * router + the same provider stack AppProviders.tsx uses in production.
 *
 * Replaces the legacy `<MemoryRouter>` + `<Routes><Route>` pattern from
 * `react-router-dom` (removed app-wide in Wave 37, lingered in tests until
 * Wave 114 SW1).
 *
 * Tests previously using `react-router-dom` can port as:
 *
 *   // before
 *   render(
 *     <QueryClientProvider client={client}>
 *       <LanguageProvider>
 *         <AuthProvider>
 *           <MemoryRouter initialEntries={["/foo"]}>
 *             <Routes>
 *               <Route path="/foo" element={<Foo />} />
 *               <Route path="/bar" element={<div>Bar</div>} />
 *             </Routes>
 *           </MemoryRouter>
 *         </AuthProvider>
 *       </LanguageProvider>
 *     </QueryClientProvider>
 *   )
 *
 *   // after
 *   renderWithRouter({
 *     ui: Foo,
 *     path: "/foo",
 *     extraRoutes: [{ path: "/bar", Component: () => <div>Bar</div> }],
 *   })
 *
 * Caveats:
 *   - Test router builds a flat route tree via `createRootRoute +
 *     addChildren`. Production `beforeLoad` guards from `_auth.tsx` /
 *     `_public.tsx` / `_admin.tsx` are NOT exercised — tests that want to
 *     verify guard behaviour should use e2e specs instead.
 *   - Each invocation creates a fresh QueryClient unless one is passed via
 *     `queryClient`. Callers that need to inspect cache entries after render
 *     can read the returned `queryClient`.
 */

export interface RouteDefinition {
  path: string
  Component: ComponentType
}

export interface AuthContextOverride {
  isAuth?: boolean
  user?: { role: string } | null
  loading?: boolean
}

export interface RenderWithRouterOptions {
  /** Component to mount at the main path. */
  ui: ComponentType
  /** Route path the main component lives at. Defaults to "/". */
  path?: string
  /** History initial entry. Defaults to `path`. */
  initialPath?: string
  /** Extra routes (e.g. navigation targets for redirect assertions). */
  extraRoutes?: RouteDefinition[]
  /** Override the test QueryClient. */
  queryClient?: QueryClient
  /** Override the router context's `auth` shape. Default: logged-out. */
  authOverride?: AuthContextOverride
  /**
   * Set to false when the test mounts its own `AuthContext.Provider` inside
   * `ui` — avoids the real `AuthProvider` running `useProfileSync`, which calls
   * `useAuthStore.setState()` and clashes with tests that partially mock the
   * Zustand auth store.
   *
   * Default: true (helper wraps with the real `AuthProvider`).
   */
  authProvider?: boolean
}

export interface RenderWithRouterResult extends RenderResult {
  queryClient: QueryClient
}

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
        gcTime: Number.POSITIVE_INFINITY,
      },
      mutations: { retry: 0 },
    },
  })
}

export async function renderWithRouter({
  ui,
  path = "/",
  initialPath,
  extraRoutes = [],
  queryClient,
  authOverride,
  authProvider = true,
}: RenderWithRouterOptions): Promise<RenderWithRouterResult> {
  const client = queryClient ?? createTestQueryClient()

  if (
    typeof window !== "undefined" &&
    !window.localStorage.getItem("ue:language") &&
    !window.__UE_SELECTED_LANG__
  ) {
    window.localStorage.setItem("ue:language", "en")
  }

  const rootRoute = createRootRoute({
    component: () => <Outlet />,
  })

  // Wrap `ui` + each extras route in a zero-prop function so TanStack's
  // `RouteComponent` shape is satisfied without casts. Passing
  // `ComponentType` directly into `component:` fails because `ComponentType`
  // admits class components, which aren't valid `RouteComponent`s.
  const MainComponent = () => {
    const Ui = ui
    return <Ui />
  }

  const mainRoute = createRoute({
    getParentRoute: () => rootRoute,
    path,
    component: MainComponent,
  })

  const extras = extraRoutes.map(({ path: routePath, Component }) => {
    const Wrapped = () => {
      const C = Component
      return <C />
    }
    return createRoute({
      getParentRoute: () => rootRoute,
      path: routePath,
      component: Wrapped,
    })
  })

  const routeTree = rootRoute.addChildren([mainRoute, ...extras])

  // Production `router.ts` uses `declare module "@tanstack/react-router"` to
  // register the generated routeTree. Tests build an ad-hoc tree, so the
  // types collide. The `as never` cast is safe: `RouterProvider` accepts
  // any router shape at runtime; only the compile-time Register interface
  // enforces the match.
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initialPath ?? path] }),
    context: {
      auth: {
        isAuth: false,
        user: null,
        loading: false,
        ...authOverride,
      },
      queryClient: client,
    },
  })

  // TanStack Router matches the initial route asynchronously. Without awaiting
  // `load()`, the `<Outlet />` renders empty until the first match resolves
  // (after a microtask), and test queries time out seeing `<body><div /></body>`.
  await router.load()

  const routerNode = <RouterProvider router={router as never} />
  // Wave 124 SW1 — mirror AppProviders' LazyMotion wrapper so tests render
  // `<m.X>` components without runtime errors. NO `strict: true` here — tests
  // sometimes mount partial React trees where LazyMotion strict's prod-mode
  // motion.X check would false-flag jsdom-rendered output.
  const result = render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <LazyMotion features={domAnimation}>
          {authProvider ? <AuthProvider>{routerNode}</AuthProvider> : routerNode}
        </LazyMotion>
      </LanguageProvider>
    </QueryClientProvider>
  )

  return { ...result, queryClient: client }
}
