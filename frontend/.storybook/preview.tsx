import type { Preview } from "@storybook/react-vite"
import { I18nextProvider } from "react-i18next"
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ComponentType } from "react"
import i18n from "../src/i18n/config"
import { AuthContext } from "../src/contexts/AuthContext"

// Wave 116 SW-Stretch — dropped stale `@mui/material` CssVarsProvider +
// CssBaseline + `../src/theme` + `../src/assets/themes.css` imports.
// MUI was uninstalled long ago (Tailwind v4 + CSS tokens replaced it) and
// src/assets/themes.css never existed in this codebase. Residue from an
// earlier Storybook setup that blocked `build-storybook` from completing.
import "../src/styles/tailwind.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

/**
 * Wave 115 SW5 — replaced the global `<MemoryRouter>` decorator (from
 * `react-router-dom`) with a TanStack Router memory-history equivalent.
 * Stories that use `<Link>`, `useLocation`, `useNavigate`, etc. from
 * `@tanstack/react-router` now have a real router context instead of the
 * legacy react-router-dom one — they were relying on the app-level
 * TanStack provider in production and crashed in Storybook before this
 * change. Mirrors the `renderWithRouter` test helper's approach: a single
 * root route whose component renders the Storybook `Story`. Each story
 * gets a fresh router instance so state doesn't leak between frames.
 *
 * The `routeTree` shape doesn't match the generated app-wide routeTree,
 * so we cast the router to `never` when passing to `RouterProvider`. This
 * is the same pattern `renderWithRouter` uses — compile-time only; the
 * runtime accepts any valid Router.
 */
function buildRouter(Story: ComponentType) {
  const rootRoute = createRootRoute({
    component: () => <Story />,
  })
  return createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
}

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: "light",
      values: [
        { name: "light", value: "#E8F1FB" },
        { name: "dark", value: "#060B14" },
      ],
    },
  },
  decorators: [
    (Story) => {
      const router = buildRouter(Story)
      return (
        <QueryClientProvider client={queryClient}>
          <I18nextProvider i18n={i18n}>
            <AuthContext.Provider
              value={{
                isAuth: true,
                user: {
                  id: 1,
                  full_name: "Mock User",
                  email: "mock@example.com",
                  role: "admin",
                } as any,
                loading: false,
                login: async () => null,
                logout: async () => {},
                setUser: () => {},
                refresh: async () => {},
                pendingMfa: null,
                submitMfaChallenge: async () => {},
                requireMfa: async () => null,
                resetEtagCache: () => {},
              }}
            >
              <div
                style={{
                  padding: "2rem",
                  minHeight: "100vh",
                  background: "var(--bg-page)",
                }}
              >
                <RouterProvider router={router as never} />
              </div>
            </AuthContext.Provider>
          </I18nextProvider>
        </QueryClientProvider>
      )
    },
  ],
}

export default preview
