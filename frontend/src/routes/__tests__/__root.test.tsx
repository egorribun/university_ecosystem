import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import { Route } from "../__root"
import { BrandBootLoader } from "@/components/feedback/BrandBootLoader"

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
    vi.unstubAllEnvs()
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
      const root = document.getElementById("root")
      expect(root).toBeInTheDocument()
      // The shell owns the document scaffold only.  BrandBootLoader is
      // mounted by both RootComponent and SsrRoot so React also owns its
      // lifecycle during static-SPA mounts and hydration.
      expect(document.querySelectorAll("[data-brand-boot-loader]")).toHaveLength(0)
      expect(document.head.textContent).toContain("@keyframes brand-boot-loader-mark-exit")
      expect(document.head.textContent).not.toContain("@keyframes status-exit")
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

    it("serializes only the authenticated role marker from the SSR auth hint", () => {
      vi.stubGlobal("__ssrAuthGetter__", () => ({
        isAuth: true,
        user: { role: "teacher" },
        loading: false,
      }))
      const Shell = (Route.options as any).shellComponent

      render(
        <Shell>
          <div>Authenticated Child</div>
        </Shell>
      )

      expect(document.getElementById("root")).toHaveAttribute(
        "data-ssr-auth",
        "authenticated:teacher"
      )
    })

    it("does not require a DOM when the shell is evaluated during SSR", () => {
      const originalDocument = globalThis.document
      vi.stubGlobal("document", undefined)
      try {
        const Shell = (Route.options as any).shellComponent
        expect(Shell({ children: null })).toBeDefined()
      } finally {
        vi.stubGlobal("document", originalDocument)
      }
    })

    it("keeps LHCI mode and static effect rules in the React-owned shell", () => {
      vi.stubEnv("VITE_LHCI", "true")
      const Shell = (Route.options as any).shellComponent

      render(
        <Shell>
          <div>LHCI Child</div>
        </Shell>
      )

      expect(document.documentElement).toHaveClass("lhci-mode")
      const staticEffects = document.querySelector("style[data-lhci-static-effects]")
      expect(staticEffects).toBeInTheDocument()
      expect(staticEffects?.textContent).toContain(".lhci-mode .aurora-mesh::after")
      expect(staticEffects?.textContent).toContain("animation: none !important")
      expect(staticEffects?.textContent).toContain(".lhci-mode .glass-noise::before")
      expect(staticEffects?.textContent).toContain("backdrop-filter: none !important")
      expect(staticEffects?.textContent).toContain(".lhci-mode .skeleton")
      expect(staticEffects?.textContent).toContain(".lhci-mode .skeleton::after")
    })

    it("keeps the loading label outside the cycling logo mark", () => {
      const Shell = (Route.options as any).shellComponent
      render(
        <Shell>
          <BrandBootLoader />
        </Shell>
      )

      const status = screen.getByText("Загрузка").closest(".brand-boot-loader__status")
      const mark = document.querySelector(".brand-boot-loader__mark")
      expect(status).toBeInTheDocument()
      expect(mark).toBeInTheDocument()
      expect(mark?.contains(status)).toBe(false)
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
      expect(document.querySelectorAll("[data-brand-boot-loader]")).toHaveLength(1)
    })

    it("renders SsrRoot component when import.meta.env.SSR is true", () => {
      import.meta.env.SSR = true

      const Component = (Route.options as any).component
      render(<Component />)

      expect(screen.getByTestId("theme-provider")).toBeInTheDocument()
      expect(screen.getByTestId("app-providers")).toBeInTheDocument()
      expect(document.querySelectorAll("[data-brand-boot-loader]")).toHaveLength(1)
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
