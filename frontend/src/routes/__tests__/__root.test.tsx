/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import { Route } from "../__root"

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    HeadContent: () => null,
    Scripts: () => null,
    Outlet: () => <div data-testid="outlet">Outlet Content</div>,
    useRouteContext: vi.fn().mockImplementation(() => {
      return {
        queryClient: new QueryClient(),
      }
    }),
  }
})

vi.mock("@/AppProviders", () => ({
  AppProviders: ({ children }: any) => <div data-testid="app-providers">{children}</div>,
}))
vi.mock("@/components/search/SearchDialog", () => ({
  SearchDialog: () => <div data-testid="search-dialog" />,
}))
vi.mock("@/components/feedback/LivePushToasts", () => ({
  default: () => <div data-testid="live-push-toasts" />,
}))
vi.mock("@/components/feedback/OfflineIndicator", () => ({
  default: () => <div data-testid="offline-indicator" />,
}))
vi.mock("@/components/pwa/InstallPrompt", () => ({
  default: () => <div data-testid="install-prompt" />,
}))
vi.mock("@/components/layout/MainLayout", () => ({
  default: ({ children }: any) => <div data-testid="main-layout">{children}</div>,
}))
vi.mock("@/components/error/PageErrorBoundary", () => ({
  PageErrorBoundary: ({ children }: any) => <div data-testid="page-error-boundary">{children}</div>,
}))
vi.mock("@/contexts/ThemeContext", () => ({
  ThemeProvider: ({ children }: any) => <div data-testid="theme-provider">{children}</div>,
}))

describe("__root.tsx components", () => {
  let originalSSR: any

  beforeEach(() => {
    originalSSR = import.meta.env.SSR
    vi.stubGlobal("__ssrThemeGetter__", undefined)
    vi.stubGlobal("__ssrLangGetter__", undefined)
  })

  afterEach(() => {
    import.meta.env.SSR = originalSSR
    vi.unstubAllGlobals()
  })

  describe("RootShell component", () => {
    it("renders root shell markup using global theme/lang cookie variables", () => {
      vi.stubGlobal("__ssrThemeGetter__", () => "dark")
      vi.stubGlobal("__ssrLangGetter__", () => "en")

      const Shell = (Route.options as any).shellComponent
      expect(Shell).toBeDefined()

      render(
        <Shell>
          <div>Test Child</div>
        </Shell>
      )

      // Check document root directly for JSDOM synchronization
      expect(document.documentElement.getAttribute("lang")).toBe("en")
      expect(document.documentElement.className).toContain("dark")

      expect(screen.getByText("Test Child")).toBeInTheDocument()
    })

    it("uses default theme/lang values when globals are undefined", () => {
      const Shell = (Route.options as any).shellComponent
      render(
        <Shell>
          <div>Test Child</div>
        </Shell>
      )

      expect(document.documentElement.getAttribute("lang")).toBe("ru")
      expect(document.documentElement.className).not.toContain("dark")
    })
  })

  describe("RootComponent and SsrRoot", () => {
    it("renders client side RootComponent with PersistQueryClientProvider", () => {
      import.meta.env.SSR = false

      const Component = (Route.options as any).component
      expect(Component).toBeDefined()

      render(<Component />)

      expect(screen.getByTestId("theme-provider")).toBeInTheDocument()
      expect(screen.getByTestId("app-providers")).toBeInTheDocument()
    })

    it("renders SsrRoot component when import.meta.env.SSR is true", () => {
      import.meta.env.SSR = true

      const Component = (Route.options as any).component
      render(<Component />)

      expect(screen.getByTestId("theme-provider")).toBeInTheDocument()
      expect(screen.getByTestId("app-providers")).toBeInTheDocument()
    })

    it("evaluates head() function to return SEO metadata tags", () => {
      const headFn = Route.options.head
      expect(headFn).toBeDefined()
      if (headFn) {
        const headData = headFn({} as any) as any
        expect(headData).toBeDefined()
        expect(headData.meta).toBeDefined()
        expect(headData.links).toBeDefined()
        expect(headData.meta?.some((m: any) => m.title)).toBe(true)
      }
    })
  })
})
