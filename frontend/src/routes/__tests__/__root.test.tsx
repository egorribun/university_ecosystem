import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import { useRouteContext } from "@tanstack/react-router"
import { BrandBootLoader } from "@/components/feedback/BrandBootLoader"

let Route: (typeof import("../__root"))["Route"]

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
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    QueryClientProvider: ({ children }: any) => (
      <div data-testid="query-client-provider">{children}</div>
    ),
  }
})
vi.mock("@tanstack/react-query-persist-client", () => ({
  PersistQueryClientProvider: ({ children }: any) => (
    <div data-testid="persist-query-client-provider">{children}</div>
  ),
}))

describe("__root.tsx components", () => {
  let originalSSR: any

  beforeEach(async () => {
    vi.resetModules()
    ;({ Route } = await import("../__root"))
    originalSSR = import.meta.env.SSR
    vi.clearAllMocks()
    document.documentElement.className = ""
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
      expect(document.documentElement.className).toBe("dark")

      expect(screen.getByText("Test Child")).toBeInTheDocument()
      const root = document.getElementById("root")
      expect(root).toBeInTheDocument()
      // The shell owns the document scaffold only.  BrandBootLoader is
      // mounted by both RootComponent and SsrRoot so React also owns its
      // lifecycle during static-SPA mounts and hydration.
      expect(document.querySelectorAll("[data-brand-boot-loader]")).toHaveLength(0)
      expect(document.head.textContent).toContain("--initial-bg: #f8fafc")
      expect(document.head.textContent).toContain("#root.ready")
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

    it("combines dark and LHCI shell classes without false-value artifacts", () => {
      vi.stubGlobal("__ssrThemeGetter__", () => "dark")
      vi.stubEnv("VITE_LHCI", "true")
      const Shell = (Route.options as any).shellComponent

      render(
        <Shell>
          <div>Combined shell</div>
        </Shell>
      )

      expect(document.documentElement.className).toBe("dark lhci-mode")
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

    it("reuses the existing SSR auth marker during client shell evaluation", () => {
      const existingRoot = document.createElement("div")
      existingRoot.id = "root"
      existingRoot.setAttribute("data-ssr-auth", "authenticated:admin")
      document.body.append(existingRoot)
      const Shell = (Route.options as any).shellComponent
      const shellTree = Shell({ children: null }) as any
      const shellBody = shellTree.props.children.find((child: any) => child?.type === "body")
      const shellRoot = shellBody.props.children.find((child: any) => child?.props?.id === "root")

      expect(shellRoot.props["data-ssr-auth"]).toBe("authenticated:admin")

      render(
        <Shell>
          <div>Hydrated Child</div>
        </Shell>
      )

      expect(document.getElementById("root")).toHaveAttribute(
        "data-ssr-auth",
        "authenticated:admin"
      )
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
      expect(document.documentElement.className).toBe("lhci-mode")
    })

    it("keeps the hidden Lighthouse marker geometry and noscript recovery contract", () => {
      const Shell = (Route.options as any).shellComponent
      render(
        <Shell>
          <div>Marker Child</div>
        </Shell>
      )

      const markerStyle = document.getElementById("lhci-marker")?.style
      expect({
        position: markerStyle?.position,
        top: markerStyle?.top,
        left: markerStyle?.left,
        width: markerStyle?.width,
        height: markerStyle?.height,
        background: markerStyle?.background,
        color: markerStyle?.color,
        display: markerStyle?.display,
        alignItems: markerStyle?.alignItems,
        justifyContent: markerStyle?.justifyContent,
        fontSize: markerStyle?.fontSize,
        zIndex: markerStyle?.zIndex,
      }).toEqual({
        position: "fixed",
        top: "0px",
        left: "0px",
        width: "100%",
        height: "100%",
        background: "white",
        color: "black",
        display: "none",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "1.5rem",
        zIndex: "var(--z-debug)",
      })
      const shellTree = Shell({ children: null }) as any
      const body = shellTree.props.children.find((child: any) => child?.type === "body")
      const noscript = body.props.children.find((child: any) => child?.type === "noscript")
      expect(noscript.props.children.props.children).toBe("#root { display: block !important; }")
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

      expect(screen.getByTestId("persist-query-client-provider")).toBeInTheDocument()
      expect(screen.queryByTestId("query-client-provider")).not.toBeInTheDocument()
      expect(screen.getByTestId("theme-provider")).toBeInTheDocument()
      expect(screen.getByTestId("app-providers")).toBeInTheDocument()
      expect(document.querySelectorAll("[data-brand-boot-loader]")).toHaveLength(1)
    })

    it("renders SsrRoot component when import.meta.env.SSR is true", () => {
      import.meta.env.SSR = true

      const Component = (Route.options as any).component
      render(<Component />)

      expect(screen.getByTestId("query-client-provider")).toBeInTheDocument()
      expect(screen.queryByTestId("persist-query-client-provider")).not.toBeInTheDocument()
      expect(useRouteContext).toHaveBeenCalledWith({ from: "__root__" })
      expect(screen.getByTestId("theme-provider")).toBeInTheDocument()
      expect(screen.getByTestId("app-providers")).toBeInTheDocument()
      expect(document.querySelectorAll("[data-brand-boot-loader]")).toHaveLength(1)
    })

    it("publishes the complete SEO, PWA, connection, and pre-paint head contract", () => {
      const headFn = Route.options.head
      expect(Route.options.ssr).toBe(true)
      expect(headFn).toBeDefined()
      if (headFn) {
        const headData = headFn({} as any) as any
        expect(headData).toEqual({
          meta: [
            { charSet: "UTF-8" },
            {
              name: "viewport",
              content: "width=device-width, initial-scale=1, viewport-fit=cover",
            },
            { name: "color-scheme", content: "light dark" },
            {
              name: "theme-color",
              media: "(prefers-color-scheme: light)",
              content: "#f8fafc",
            },
            {
              name: "theme-color",
              media: "(prefers-color-scheme: dark)",
              content: "#020617",
            },
            {
              name: "description",
              content:
                "Всё необходимое — профиль, расписание, новости и события кампуса — в одном месте.",
            },
            { property: "og:type", content: "website" },
            { property: "og:title", content: "Экосистема ГУУ" },
            {
              property: "og:description",
              content: "Личный кабинет: профиль, расписание, новости и события кампуса.",
            },
            { property: "og:url", content: "/" },
            { property: "og:image", content: "/og-image.png" },
            { property: "og:locale", content: "ru_RU" },
            { name: "twitter:card", content: "summary_large_image" },
            { name: "twitter:title", content: "Экосистема ГУУ" },
            {
              name: "twitter:description",
              content: "Личный кабинет: профиль, расписание, новости и события кампуса.",
            },
            { name: "twitter:image", content: "/og-image.png" },
            { name: "google-site-verification", content: "not-applicable" },
            { name: "mobile-web-app-capable", content: "yes" },
            { name: "apple-mobile-web-app-status-bar-style", content: "black-translucent" },
            { title: "Экосистема ГУУ" },
          ],
          links: [
            { rel: "icon", href: "/favicon.ico", sizes: "any" },
            { rel: "icon", type: "image/png", sizes: "32x32", href: "/favicon-32x32.png" },
            { rel: "icon", type: "image/png", sizes: "16x16", href: "/favicon-16x16.png" },
            { rel: "apple-touch-icon", href: "/apple-touch-icon.png" },
            {
              rel: "manifest",
              href: "/manifest.webmanifest",
              crossOrigin: "use-credentials",
            },
            { rel: "preconnect", href: "https://picsum.photos", crossOrigin: "" },
            { rel: "dns-prefetch", href: "https://picsum.photos" },
          ],
          scripts: [
            {
              children: expect.stringContaining(
                "document.cookie.match(/(?:^|;\\s*)ue:language=(ru|en)(?:;|$)/)"
              ),
            },
          ],
        })
      }
    })
  })
})
