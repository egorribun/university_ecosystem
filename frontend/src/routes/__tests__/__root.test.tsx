import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { act } from "react"
import { createRoot } from "react-dom/client"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { QueryClient } from "@tanstack/react-query"
import { useRouteContext } from "@tanstack/react-router"
import { BrandBootLoader } from "@/components/feedback/BrandBootLoader"
import { withExpectedConsole } from "@/tests/strictConsole"
import type { ReactNode } from "react"

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
  OfflineIndicator: () => <div data-testid="offline-indicator" />,
}))
vi.mock("@/components/pwa/InstallPrompt", () => ({
  default: () => <div data-testid="install-prompt" />,
}))
vi.mock("@/components/layout/MainLayout", () => ({
  MainLayout: ({ children }: any) => <div data-testid="main-layout">{children}</div>,
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

// RootShell owns the complete document (`<html><head><body>`), so the default
// Testing Library `<div>` container is invalid and React reports a hydration
// warning. React DOM accepts a Document container; using it here exercises the
// same document-level ownership as the production hydrateRoot call.
const renderDocumentShell = (Shell: any, children: ReactNode) =>
  render(<Shell>{children}</Shell>, { container: document, baseElement: document })

const REACT_DOCUMENT_SCRIPT_WARNING =
  "Encountered a script tag while rendering React component. " +
  "Scripts inside React components are never executed when rendering on the client. " +
  "Consider using template tag instead " +
  "(https://developer.mozilla.org/en-US/docs/Web/HTML/Element/template)."

const isReactDocumentScriptWarning = (args: readonly unknown[]) =>
  args.length === 1 && args[0] === REACT_DOCUMENT_SCRIPT_WARNING

const stubRootLoaderData = () =>
  vi.spyOn(Route, "useLoaderData").mockReturnValue({ campusTimezone: "Europe/Moscow" })

describe("__root.tsx components", () => {
  let originalSSR: any
  let originalDocumentClass = ""
  let originalDocumentLang: string | null = null
  let originalSelectedLanguageDescriptor: PropertyDescriptor | undefined

  beforeEach(async () => {
    vi.resetModules()
    ;({ Route } = await import("../__root"))
    originalSSR = import.meta.env.SSR
    originalDocumentClass = document.documentElement.className
    originalDocumentLang = document.documentElement.getAttribute("lang")
    originalSelectedLanguageDescriptor = Object.getOwnPropertyDescriptor(
      window,
      "__UE_SELECTED_LANG__"
    )
    vi.clearAllMocks()
    document.documentElement.className = ""
    document.documentElement.removeAttribute("lang")
    Reflect.deleteProperty(window, "__UE_SELECTED_LANG__")
    vi.stubGlobal("__ssrThemeGetter__", undefined)
    vi.stubGlobal("__ssrLangGetter__", undefined)
    vi.stubGlobal("__ssrNonceGetter__", undefined)
    vi.stubGlobal("__ssrOriginGetter__", undefined)
  })

  afterEach(() => {
    import.meta.env.SSR = originalSSR
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    document.documentElement.className = originalDocumentClass
    if (originalDocumentLang === null) document.documentElement.removeAttribute("lang")
    else document.documentElement.setAttribute("lang", originalDocumentLang)
    Reflect.deleteProperty(window, "__UE_SELECTED_LANG__")
    if (originalSelectedLanguageDescriptor) {
      Object.defineProperty(window, "__UE_SELECTED_LANG__", originalSelectedLanguageDescriptor)
    }
  })

  describe("RootShell component", () => {
    it("renders root shell markup using global theme/lang cookie variables", async () => {
      const initialDocumentClass = document.documentElement.className
      const initialDocumentLang = document.documentElement.getAttribute("lang")
      document.documentElement.setAttribute("lang", "ru")
      window.__UE_SELECTED_LANG__ = "ru"
      vi.stubGlobal("__ssrThemeGetter__", () => "dark")
      vi.stubGlobal("__ssrLangGetter__", () => "en")

      const Shell = (Route.options as any).shellComponent
      expect(Shell).toBeDefined()

      // ReactDOM has a module-global warn-once flag for the inert client-rendered
      // script. Scope its exact dev diagnostic to this first render; keep all other
      // console output strict. The source SPA shell runs parser-owned prepaint code
      // before its module entry, so this script is not its execution mechanism.
      const serverRender = await withExpectedConsole("error", isReactDocumentScriptWarning, () =>
        renderDocumentShell(Shell, <div>Test Child</div>)
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

      serverRender.unmount()

      const bootstrapRoot = document.createElement("div")
      bootstrapRoot.id = "root"
      document.body.append(bootstrapRoot)

      // Exercise the actual entrypoint branch and document renderer together:
      // the parser asset has already selected the browser theme and language.
      const previousSelectedLanguage = window.__UE_SELECTED_LANG__
      const previousThemeMarker = Object.getOwnPropertyDescriptor(
        window,
        "__UE_THEME_INIT_SCRIPT_RAN__"
      )
      const previousRenderMode = document.documentElement.getAttribute("data-render-mode")
      const nonceMeta = document.createElement("meta")
      nonceMeta.setAttribute("property", "csp-nonce")
      nonceMeta.content = "static-spa-nonce"
      const prepaintScript = document.createElement("script")
      prepaintScript.id = "theme-init-script"
      prepaintScript.src = window.location.origin + "/theme-init.js"
      prepaintScript.setAttribute("nonce", "static-spa-nonce")
      let staticRoot: ReturnType<typeof createRoot> | undefined

      try {
        document.head.append(nonceMeta, prepaintScript)
        document.documentElement.classList.add("dark")
        document.documentElement.setAttribute("lang", "en")
        document.documentElement.dataset.renderMode = "static-spa"
        window.__UE_SELECTED_LANG__ = "en"
        Reflect.set(window, "__UE_THEME_INIT_SCRIPT_RAN__", true)
        vi.stubGlobal("__ssrThemeGetter__", undefined)
        vi.stubGlobal("__ssrLangGetter__", undefined)
        vi.stubEnv("PROD", false)
        vi.stubEnv("VITE_LHCI", "true")

        expect(document.querySelectorAll('[id="theme-init-script"]')).toHaveLength(1)

        vi.doMock("@fontsource-variable/inter", () => ({}))
        vi.doMock("@fontsource-variable/outfit", () => ({}))
        vi.doMock("../../styles/tailwind.css", () => ({}))
        vi.doMock("../../App", () => ({
          default: () => {
            const StaticShell = (Route.options as any).shellComponent
            return (
              <StaticShell>
                <div>Static SPA child</div>
              </StaticShell>
            )
          },
        }))
        vi.doMock("../../app/globalErrorHandlers", () => ({
          initGlobalErrorHandlers: vi.fn(),
        }))
        vi.doMock("react-dom/client", async (importOriginal) => {
          const actual = await importOriginal<typeof import("react-dom/client")>()
          return {
            ...actual,
            createRoot: (...args: Parameters<typeof createRoot>) => {
              expect(args[0]).toBe(document)
              expect(prepaintScript.isConnected).toBe(false)
              staticRoot = actual.createRoot(...args)
              return staticRoot
            },
          }
        })

        await act(async () => {
          await import("../../main")
        })

        expect(staticRoot).toBeDefined()
        expect(document.documentElement).toHaveClass("dark")
        expect(document.documentElement).toHaveAttribute("lang", "en")
        expect(window.__UE_SELECTED_LANG__).toBe("en")
        expect(document.documentElement).not.toHaveAttribute("data-render-mode")
        expect(document.getElementById("theme-init-script")).toHaveAttribute(
          "src",
          prepaintScript.getAttribute("src")
        )
        expect(document.getElementById("theme-init-script")).toHaveAttribute(
          "nonce",
          "static-spa-nonce"
        )
        expect(document.querySelectorAll('[id="theme-init-script"]')).toHaveLength(1)
      } finally {
        if (staticRoot) {
          await act(async () => {
            staticRoot?.unmount()
          })
        }
        vi.doUnmock("../../App")
        vi.doUnmock("../../app/globalErrorHandlers")
        vi.doUnmock("react-dom/client")
        vi.doUnmock("@fontsource-variable/inter")
        vi.doUnmock("@fontsource-variable/outfit")
        vi.doUnmock("../../styles/tailwind.css")
        bootstrapRoot.remove()
        nonceMeta.remove()
        prepaintScript.remove()
        if (previousRenderMode === null)
          document.documentElement.removeAttribute("data-render-mode")
        else document.documentElement.setAttribute("data-render-mode", previousRenderMode)
        if (previousSelectedLanguage === undefined) delete window.__UE_SELECTED_LANG__
        else window.__UE_SELECTED_LANG__ = previousSelectedLanguage
        if (previousThemeMarker) {
          Object.defineProperty(window, "__UE_THEME_INIT_SCRIPT_RAN__", previousThemeMarker)
        } else {
          Reflect.deleteProperty(window, "__UE_THEME_INIT_SCRIPT_RAN__")
        }
        document.documentElement.className = initialDocumentClass
        if (initialDocumentLang === null) document.documentElement.removeAttribute("lang")
        else document.documentElement.setAttribute("lang", initialDocumentLang)
      }
    })

    it("renders a nonce-bearing external pre-paint asset outside route-managed inline scripts", () => {
      vi.stubGlobal("__ssrNonceGetter__", () => "per-response-nonce")
      vi.stubGlobal("__ssrOriginGetter__", () => "https://app.example")
      const Shell = (Route.options as any).shellComponent
      const shellTree = Shell({ children: null }) as any
      const head = shellTree.props.children.find((child: any) => child?.type === "head")
      const script = head.props.children.find(
        (child: any) => child?.props?.id === "theme-init-script"
      )

      expect(script).toBeDefined()
      expect(script.props.src).toBe("http://localhost:3000/theme-init.js")
      expect(script.props.nonce).toBe("per-response-nonce")
      expect(script.props.children).toBeUndefined()
      expect(script.props.dangerouslySetInnerHTML).toBeUndefined()
      const styles = head.props.children.filter((child: any) => child?.type === "style")
      expect(styles).toHaveLength(1)
      expect(styles.every((style: any) => style.props.dangerouslySetInnerHTML === undefined)).toBe(
        true
      )

      const headData = (Route.options.head as any)({})
      expect(headData).not.toHaveProperty("scripts")
    })

    it("passes an app-policy TrustedScriptURL through the document-root createRoot sink", async () => {
      const policyCacheKeys = ["__ttAppPolicy", "__ttSanitizePolicy"] as const
      const previousPolicyCache = policyCacheKeys.map((key) => ({
        key,
        hadOwnProperty: Object.prototype.hasOwnProperty.call(window, key),
        value: Reflect.get(window, key),
      }))
      const brandedUrls = new WeakSet<object>()
      const appPolicy = {
        createScriptURL: vi.fn((value: string) => {
          const trustedUrl = { toString: () => value }
          brandedUrls.add(trustedUrl)
          return trustedUrl
        }),
        createHTML: (value: string) => value,
      }
      const createPolicy = vi.fn((name: string) => {
        expect(name).toBe("app")
        return appPolicy
      })
      const nonceMeta = document.createElement("meta")
      nonceMeta.setAttribute("property", "csp-nonce")
      nonceMeta.content = "static-shell-nonce"
      let root: ReturnType<typeof createRoot> | undefined
      let scriptSourceSink: ReturnType<typeof vi.spyOn> | undefined

      try {
        vi.stubGlobal("trustedTypes", { createPolicy })
        for (const { key } of previousPolicyCache) Reflect.deleteProperty(window, key)
        document.head.append(nonceMeta)

        const originalSetAttribute = HTMLScriptElement.prototype.setAttribute
        scriptSourceSink = vi
          .spyOn(HTMLScriptElement.prototype, "setAttribute")
          .mockImplementation(function (this: HTMLScriptElement, name: string, value: string) {
            if (name === "src" && this.id === "theme-init-script") {
              expect(typeof value).toBe("object")
              expect(brandedUrls.has(value as unknown as object)).toBe(true)
            }
            return originalSetAttribute.call(this, name, value)
          })

        const Shell = (Route.options as any).shellComponent
        root = createRoot(document)
        await act(async () => {
          root?.render(
            <Shell>
              <div>Static SPA content</div>
            </Shell>
          )
        })

        expect(createPolicy).toHaveBeenCalledOnce()
        expect(scriptSourceSink).toHaveBeenCalled()
        expect(document.getElementById("theme-init-script")).toHaveAttribute(
          "src",
          `${window.location.origin}/theme-init.js`
        )
        expect(document.getElementById("theme-init-script")).toHaveAttribute(
          "nonce",
          "static-shell-nonce"
        )
        expect(document.getElementById("theme-init-script")?.textContent).toBe("")
        expect(document.querySelector("style")?.textContent).toContain("--initial-bg")
      } finally {
        if (root) await act(async () => root?.unmount())
        scriptSourceSink?.mockRestore()
        nonceMeta.remove()
        for (const { key, hadOwnProperty, value } of previousPolicyCache) {
          if (hadOwnProperty) Reflect.set(window, key, value)
          else Reflect.deleteProperty(window, key)
        }
      }
    })

    it("reuses the serialized CSP nonce and exact URL while rendering the client shell", () => {
      const nonceMeta = document.createElement("meta")
      nonceMeta.setAttribute("property", "csp-nonce")
      nonceMeta.content = "hydrated-request-nonce"
      document.head.append(nonceMeta)
      const serverScript = document.createElement("script")
      serverScript.id = "theme-init-script"
      serverScript.src = "https://app.example/theme-init.js"
      document.head.append(serverScript)

      try {
        const Shell = (Route.options as any).shellComponent
        const shellTree = Shell({ children: null }) as any
        const head = shellTree.props.children.find((child: any) => child?.type === "head")
        const script = head.props.children.find(
          (child: any) => child?.props?.id === "theme-init-script"
        )

        expect(script?.props.nonce).toBe("hydrated-request-nonce")
        expect(script?.props.src).toBe("https://app.example/theme-init.js")
      } finally {
        nonceMeta.remove()
        serverScript.remove()
      }
    })

    it("keeps the pre-paint language-cookie matcher and static remount guard in the public asset", () => {
      const themeInitScript = readFileSync(resolve(process.cwd(), "public/theme-init.js"), "utf8")
      expect(themeInitScript).toContain(
        "document.cookie.match(/(?:^|;\\s*)ue:language=(ru|en)(?:;|$)/)"
      )
      expect(themeInitScript).toContain("window.__UE_THEME_INIT_SCRIPT_RAN__")
      expect(themeInitScript).toContain("window.__UE_SELECTED_LANG__ = lang")
    })

    it("uses default theme/lang values when globals are undefined", () => {
      expect(document.documentElement).not.toHaveAttribute("lang")
      expect(window.__UE_SELECTED_LANG__).toBeUndefined()
      const Shell = (Route.options as any).shellComponent
      renderDocumentShell(Shell, <div>Test Child</div>)

      expect(document.documentElement.getAttribute("lang")).toBe("ru")
      expect(document.documentElement.className).not.toContain("dark")
    })

    it("combines dark and LHCI shell classes without false-value artifacts", () => {
      vi.stubGlobal("__ssrThemeGetter__", () => "dark")
      vi.stubEnv("VITE_LHCI", "true")
      const Shell = (Route.options as any).shellComponent

      renderDocumentShell(Shell, <div>Combined shell</div>)

      expect(document.documentElement.className).toBe("dark lhci-mode")
    })

    it("serializes only the authenticated role marker from the SSR auth hint", () => {
      vi.stubGlobal("__ssrAuthGetter__", () => ({
        isAuth: true,
        user: { role: "teacher" },
        loading: false,
      }))
      const Shell = (Route.options as any).shellComponent

      renderDocumentShell(Shell, <div>Authenticated Child</div>)

      expect(document.getElementById("root")).toHaveAttribute(
        "data-ssr-auth",
        "authenticated:teacher"
      )
    })

    it("does not require a DOM when the shell is evaluated during SSR", () => {
      const originalDocument = globalThis.document
      const originalWindow = globalThis.window
      vi.stubGlobal("__ssrNonceGetter__", () => "request-scoped-nonce")
      vi.stubGlobal("__ssrOriginGetter__", () => "https://ssr.example")
      vi.stubGlobal("document", undefined)
      vi.stubGlobal("window", undefined)
      try {
        const Shell = (Route.options as any).shellComponent
        const shellTree = Shell({ children: null }) as any
        const head = shellTree.props.children.find((child: any) => child?.type === "head")
        const script = head.props.children.find(
          (child: any) => child?.props?.id === "theme-init-script"
        )

        expect(script.props.src).toBe("https://ssr.example/theme-init.js")
        expect(script.props.nonce).toBe("request-scoped-nonce")
      } finally {
        vi.stubGlobal("document", originalDocument)
        vi.stubGlobal("window", originalWindow)
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

      renderDocumentShell(Shell, <div>Hydrated Child</div>)

      expect(document.getElementById("root")).toHaveAttribute(
        "data-ssr-auth",
        "authenticated:admin"
      )
    })

    it("keeps LHCI mode and static effect rules in the React-owned shell", () => {
      vi.stubEnv("VITE_LHCI", "true")
      const Shell = (Route.options as any).shellComponent

      renderDocumentShell(Shell, <div>LHCI Child</div>)

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
      renderDocumentShell(Shell, <div>Marker Child</div>)

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
      renderDocumentShell(Shell, <BrandBootLoader />)

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
      stubRootLoaderData()

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
      stubRootLoaderData()

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
        })
      }
    })
  })
})
