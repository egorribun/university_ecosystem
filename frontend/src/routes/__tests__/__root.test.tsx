import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { act } from "react"
import { createRoot } from "react-dom/client"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { QueryClient } from "@tanstack/react-query"
import { useRouteContext } from "@tanstack/react-router"
import { BrandBootLoader } from "@/components/feedback/BrandBootLoader"
import { createI18nInstance } from "@/i18n/config"
import { withExpectedConsole } from "@/tests/strictConsole"
import type { ReactNode } from "react"

let Route: (typeof import("../__root"))["Route"]
const mockedScripts = vi.hoisted(() => vi.fn((): any => null))
const mockedFetchCampusTimezone = vi.hoisted(() =>
  vi.fn(() => Promise.resolve<string | null>(null))
)

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    HeadContent: () => null,
    Scripts: mockedScripts,
    Outlet: () => <div data-testid="outlet">Outlet Content</div>,
    useRouterState: vi.fn().mockReturnValue(false),
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

const shellDocumentElement = (shellTree: any) =>
  shellTree?.type === "html" ? shellTree : shellTree?.props?.children

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

  it("returns campus timezone from the root route loader", async () => {
    mockedFetchCampusTimezone.mockReset()
    vi.doMock("@/api/hooks/campusConfig", () => ({
      fetchCampusTimezone: mockedFetchCampusTimezone,
    }))
    vi.resetModules()

    try {
      const { Route: loaderRoute } = await import("../__root")
      const loader = (loaderRoute.options as any).loader
      mockedFetchCampusTimezone.mockResolvedValueOnce("Europe/Istanbul")

      await expect(loader()).resolves.toEqual({ campusTimezone: "Europe/Istanbul" })
      expect(mockedFetchCampusTimezone).toHaveBeenCalledOnce()
    } finally {
      vi.doUnmock("@/api/hooks/campusConfig")
      vi.resetModules()
    }
  })

  it("uses the request or pre-paint language for the root document title", () => {
    const getHead = () => (Route.options as any).head({ matches: [] })
    const getDocumentTitle = () =>
      getHead().meta.find((entry: { title?: string }) => "title" in entry).title
    const getMeta = (key: string) =>
      getHead().meta.find(
        (entry: { name?: string; property?: string }) =>
          entry.name === key || entry.property === key
      )

    document.documentElement.lang = "ru"
    window.__UE_SELECTED_LANG__ = "ru"
    const requestI18n = createI18nInstance("en")
    vi.stubGlobal("__ssrLangGetter__", () => "en")
    vi.stubGlobal("__ssrI18nGetter__", () => requestI18n)
    expect(getDocumentTitle()).toBe("GUU Ecosystem")
    expect(getMeta("og:title").content).toBe("GUU Ecosystem")
    expect(getMeta("og:locale").content).toBe("en_US")
    expect(getMeta("description").content).toBe(
      "Everything you need—profile, schedule, news, and campus events—in one place."
    )
    expect(getMeta("og:description").content).toBe(
      "Your personal account: profile, schedule, news, and campus events."
    )
    expect(getMeta("twitter:description").content).toBe(
      "Your personal account: profile, schedule, news, and campus events."
    )

    vi.stubGlobal("__ssrLangGetter__", undefined)
    vi.stubGlobal("__ssrI18nGetter__", undefined)
    window.__UE_SELECTED_LANG__ = "en"
    expect(getDocumentTitle()).toBe("GUU Ecosystem")
    expect(getMeta("og:locale").content).toBe("en_US")

    Reflect.deleteProperty(window, "__UE_SELECTED_LANG__")
    expect(getDocumentTitle()).toBe("Экосистема ГУУ")
    expect(getMeta("og:locale").content).toBe("ru_RU")
  })

  it("uses the selected browser locale when root metadata is reevaluated after a switch", () => {
    const getHead = () => (Route.options as any).head({ matches: [] })
    const getDocumentTitle = () =>
      getHead().meta.find((entry: { title?: string }) => "title" in entry).title
    const getMeta = (key: string) =>
      getHead().meta.find(
        (entry: { name?: string; property?: string }) =>
          entry.name === key || entry.property === key
      )

    document.documentElement.lang = "ru"
    window.__UE_SELECTED_LANG__ = "ru"
    expect(getMeta("og:locale").content).toBe("ru_RU")

    // LanguageProvider writes both values together after a browser locale switch.
    document.documentElement.lang = "en"
    window.__UE_SELECTED_LANG__ = "en"
    expect(getDocumentTitle()).toBe("GUU Ecosystem")
    expect(getMeta("og:locale").content).toBe("en_US")
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
      const previousStaticMountMarker = Object.getOwnPropertyDescriptor(
        window,
        "__UE_STATIC_SPA_DOCUMENT_MOUNT__"
      )
      const previousRenderMode = document.documentElement.getAttribute("data-render-mode")
      const nonceMeta = document.createElement("meta")
      nonceMeta.setAttribute("property", "csp-nonce")
      nonceMeta.content = "static-spa-nonce"
      const prepaintScript = document.createElement("script")
      prepaintScript.id = "theme-init-script"
      prepaintScript.src = window.location.origin + "/theme-init.js"
      prepaintScript.setAttribute("nonce", "static-spa-nonce")
      const prepaintScriptText = prepaintScript.textContent
      const moduleEntryScript = document.createElement("script")
      moduleEntryScript.type = "module"
      moduleEntryScript.src = window.location.origin + "/assets/static-entry.js"
      moduleEntryScript.async = true
      moduleEntryScript.setAttribute("nonce", "static-spa-nonce")
      const moduleEntryText = moduleEntryScript.textContent
      let staticRoot: ReturnType<typeof createRoot> | undefined

      try {
        document.head.append(nonceMeta, prepaintScript)
        document.body.append(moduleEntryScript)
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
              expect(prepaintScript.isConnected).toBe(true)
              expect(moduleEntryScript.isConnected).toBe(true)
              staticRoot = actual.createRoot(...args)
              return staticRoot
            },
          }
        })

        await act(async () => {
          await import("../../main")
        })

        expect(staticRoot).toBeDefined()
        expect(Reflect.get(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__")).toBe(true)
        expect(document.documentElement).toHaveClass("dark")
        expect(document.documentElement).toHaveAttribute("lang", "en")
        expect(window.__UE_SELECTED_LANG__).toBe("en")
        expect(document.documentElement).not.toHaveAttribute("data-render-mode")
        expect(document.getElementById("theme-init-script")).toBe(prepaintScript)
        expect(document.querySelectorAll('script[src$="/assets/static-entry.js"]')).toHaveLength(1)
        expect(document.querySelector('script[src$="/assets/static-entry.js"]')).toBe(
          moduleEntryScript
        )
        expect(prepaintScript.src).toBe(window.location.origin + "/theme-init.js")
        expect(prepaintScript.nonce).toBe("static-spa-nonce")
        expect(prepaintScript.textContent).toBe(prepaintScriptText)
        expect(moduleEntryScript.nonce).toBe("static-spa-nonce")
        expect(moduleEntryScript.textContent).toBe(moduleEntryText)
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
        moduleEntryScript.remove()
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
        if (previousStaticMountMarker) {
          Object.defineProperty(
            window,
            "__UE_STATIC_SPA_DOCUMENT_MOUNT__",
            previousStaticMountMarker
          )
        } else {
          Reflect.deleteProperty(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__")
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
      const head = shellDocumentElement(shellTree).props.children.find(
        (child: any) => child?.type === "head"
      )
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

    it("preserves parser-run scripts during a strict Trusted Types static document mount", async () => {
      const previousStaticMountMarker = Object.getOwnPropertyDescriptor(
        window,
        "__UE_STATIC_SPA_DOCUMENT_MOUNT__"
      )
      const policyCacheKeys = ["__ttAppPolicy", "__ttSanitizePolicy"] as const
      const previousPolicyCache = policyCacheKeys.map((key) => ({
        key,
        hadOwnProperty: Object.prototype.hasOwnProperty.call(window, key),
        value: Reflect.get(window, key),
      }))
      const originalInnerHTMLDescriptor = Object.getOwnPropertyDescriptor(
        Element.prototype,
        "innerHTML"
      )
      if (!originalInnerHTMLDescriptor?.set) throw new Error("Element.innerHTML setter is missing")
      const strictInnerHTMLSetter = function (this: Element, value: string) {
        if (/<script(?:\s|>)/iu.test(value)) {
          throw new TypeError("TrustedHTML required for script markup")
        }
        originalInnerHTMLDescriptor.set?.call(this, value)
      }
      const createPolicy = vi.fn((name: string) => {
        expect(name).toBe("app")
        return {
          createScriptURL: (value: string) => value,
          createHTML: (value: string) => value,
        }
      })
      const nonceMeta = document.createElement("meta")
      nonceMeta.setAttribute("property", "csp-nonce")
      nonceMeta.content = "static-shell-nonce"
      const parserThemeScript = document.createElement("script")
      parserThemeScript.id = "theme-init-script"
      parserThemeScript.src = window.location.origin + "/theme-init.js"
      parserThemeScript.setAttribute("nonce", "static-shell-nonce")
      const parserModuleScript = document.createElement("script")
      parserModuleScript.type = "module"
      parserModuleScript.src = window.location.origin + "/assets/static-entry.js"
      parserModuleScript.async = true
      parserModuleScript.setAttribute("nonce", "static-shell-nonce")
      const themeText = parserThemeScript.textContent
      const moduleText = parserModuleScript.textContent
      document.documentElement.classList.add("dark")
      document.documentElement.lang = "en"
      window.__UE_SELECTED_LANG__ = "en"
      let root: ReturnType<typeof createRoot> | undefined

      try {
        mockedScripts.mockReturnValue(<script type="module" src="/assets/static-entry.js" />)
        vi.stubGlobal("trustedTypes", { createPolicy })
        for (const { key } of previousPolicyCache) Reflect.deleteProperty(window, key)
        Reflect.set(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__", true)
        document.head.append(nonceMeta, parserThemeScript)
        document.body.append(parserModuleScript)
        Object.defineProperty(Element.prototype, "innerHTML", {
          ...originalInnerHTMLDescriptor,
          set: strictInnerHTMLSetter,
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

        expect(createPolicy).not.toHaveBeenCalled()
        expect(mockedScripts).not.toHaveBeenCalled()
        expect(document.querySelectorAll('[id="theme-init-script"]')).toHaveLength(1)
        expect(document.getElementById("theme-init-script")).toBe(parserThemeScript)
        expect(parserThemeScript.isConnected).toBe(true)
        expect(parserThemeScript.src).toBe(window.location.origin + "/theme-init.js")
        expect(parserThemeScript.nonce).toBe("static-shell-nonce")
        expect(parserThemeScript.textContent).toBe(themeText)
        expect(document.querySelectorAll('script[src$="/assets/static-entry.js"]')).toHaveLength(1)
        expect(document.querySelector('script[src$="/assets/static-entry.js"]')).toBe(
          parserModuleScript
        )
        expect(parserModuleScript.isConnected).toBe(true)
        expect(parserModuleScript.nonce).toBe("static-shell-nonce")
        expect(parserModuleScript.textContent).toBe(moduleText)
        expect(document.querySelector("style")?.textContent).toContain("--initial-bg")
        expect(document.documentElement).toHaveClass("dark")
        expect(document.documentElement).toHaveAttribute("lang", "en")
        expect(window.__UE_SELECTED_LANG__).toBe("en")

        await act(async () => {
          root?.render(
            <Shell>
              <div>Updated static SPA content</div>
            </Shell>
          )
        })

        expect(document.querySelectorAll('[id="theme-init-script"]')).toHaveLength(1)
        expect(document.getElementById("theme-init-script")).toBe(parserThemeScript)
        expect(parserThemeScript.nonce).toBe("static-shell-nonce")
        expect(parserThemeScript.textContent).toBe(themeText)
        expect(document.querySelectorAll('script[src$="/assets/static-entry.js"]')).toHaveLength(1)
        expect(document.querySelector('script[src$="/assets/static-entry.js"]')).toBe(
          parserModuleScript
        )
        expect(parserModuleScript.nonce).toBe("static-shell-nonce")
        expect(parserModuleScript.textContent).toBe(moduleText)
        expect(document.documentElement).toHaveClass("dark")
        expect(document.documentElement).toHaveAttribute("lang", "en")
        expect(window.__UE_SELECTED_LANG__).toBe("en")
        expect(mockedScripts).not.toHaveBeenCalled()
      } finally {
        if (originalInnerHTMLDescriptor) {
          Object.defineProperty(Element.prototype, "innerHTML", originalInnerHTMLDescriptor)
        }
        try {
          if (root) await act(async () => root?.unmount())
        } finally {
          mockedScripts.mockReset()
          mockedScripts.mockReturnValue(null)
          nonceMeta.remove()
          parserThemeScript.remove()
          parserModuleScript.remove()
          if (previousStaticMountMarker) {
            Object.defineProperty(
              window,
              "__UE_STATIC_SPA_DOCUMENT_MOUNT__",
              previousStaticMountMarker
            )
          } else {
            Reflect.deleteProperty(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__")
          }
          for (const { key, hadOwnProperty, value } of previousPolicyCache) {
            if (hadOwnProperty) Reflect.set(window, key, value)
            else Reflect.deleteProperty(window, key)
          }
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
        const head = shellDocumentElement(shellTree).props.children.find(
          (child: any) => child?.type === "head"
        )
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
        const head = shellDocumentElement(shellTree).props.children.find(
          (child: any) => child?.type === "head"
        )
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

    it("keeps an existing relative theme URL when SSR has no window origin", () => {
      const previousScripts = Array.from(
        document.querySelectorAll<HTMLScriptElement>('script[id="theme-init-script"]')
      )
      previousScripts.forEach((script) => script.remove())
      const existingScript = document.createElement("script")
      existingScript.id = "theme-init-script"
      existingScript.setAttribute("src", "theme-init.js")
      document.head.append(existingScript)
      const originalWindow = globalThis.window
      vi.stubGlobal("window", undefined)

      try {
        const Shell = (Route.options as any).shellComponent
        const shellTree = Shell({ children: null }) as any
        const head = shellDocumentElement(shellTree).props.children.find(
          (child: any) => child?.type === "head"
        )
        const script = head.props.children.find(
          (child: any) => child?.props?.id === "theme-init-script"
        )

        expect(script.props.src).toBe("theme-init.js")
      } finally {
        vi.stubGlobal("window", originalWindow)
        existingScript.remove()
        previousScripts.forEach((script) => document.head.append(script))
      }
    })

    it("uses relative theme URL and no nonce when SSR has neither DOM nor origin", () => {
      const originalDocument = globalThis.document
      const originalWindow = globalThis.window
      vi.stubGlobal("__ssrNonceGetter__", undefined)
      vi.stubGlobal("__ssrOriginGetter__", undefined)
      vi.stubGlobal("document", undefined)
      vi.stubGlobal("window", undefined)
      try {
        const Shell = (Route.options as any).shellComponent
        const shellTree = Shell({ children: null }) as any
        const head = shellDocumentElement(shellTree).props.children.find(
          (child: any) => child?.type === "head"
        )
        const script = head.props.children.find(
          (child: any) => child?.props?.id === "theme-init-script"
        )

        expect(script.props.src).toBe("/theme-init.js")
        expect(script.props.nonce).toBeUndefined()
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
      const shellBody = shellDocumentElement(shellTree).props.children.find(
        (child: any) => child?.type === "body"
      )
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
      const body = shellDocumentElement(shellTree).props.children.find(
        (child: any) => child?.type === "body"
      )
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

    it("keeps route-managed root SEO out of matches with page metadata", () => {
      const headFn = Route.options.head
      expect(headFn).toBeDefined()
      if (!headFn) throw new Error("Root head metadata is missing")

      const rootHead = headFn({ matches: [] } as any) as any
      const dashboardHead = headFn({
        matches: [{ routeId: "/_auth/dashboard", status: "success" }],
      } as any) as any
      const newsHead = headFn({
        matches: [{ routeId: "/_auth/news/", status: "success" }],
      } as any) as any
      const publicHead = headFn({
        matches: [{ routeId: "/_public/login", status: "success" }],
      } as any) as any
      const failedDashboardHead = headFn({
        matches: [{ routeId: "/_auth/dashboard", status: "error" }],
      } as any) as any
      const pageSeoRouteIds = [
        "/_auth/activity",
        "/_auth/dashboard",
        "/_auth/events/",
        "/_auth/events/$id",
        "/_auth/news/",
        "/_auth/news/$id",
        "/_auth/profile",
        "/_auth/schedule",
      ]
      const originalSsr = import.meta.env.SSR
      import.meta.env.SSR = false
      const activityClientHead = headFn({
        matches: [{ routeId: "/_auth/activity", status: "success" }],
      } as any) as any
      import.meta.env.SSR = true
      const activityServerHead = headFn({
        matches: [{ routeId: "/_auth/activity", status: "success" }],
      } as any) as any
      import.meta.env.SSR = originalSsr

      const rootTitle = rootHead.meta.find((meta: { title?: string }) => meta.title)?.title
      expect(rootTitle).toBe("Экосистема ГУУ")
      expect(
        rootHead.meta.filter((meta: { name?: string }) => meta.name === "description")
      ).toHaveLength(1)
      expect(dashboardHead.meta.some((meta: { title?: string }) => meta.title)).toBe(false)
      expect(
        dashboardHead.meta.some((meta: { name?: string }) => meta.name === "description")
      ).toBe(false)
      expect(
        newsHead.meta.some((meta: { property?: string }) => meta.property === "og:title")
      ).toBe(false)
      expect(
        newsHead.meta.some((meta: { property?: string }) => meta.property === "og:description")
      ).toBe(false)
      expect(newsHead.meta.some((meta: { name?: string }) => meta.name === "twitter:card")).toBe(
        false
      )
      expect(publicHead.meta.some((meta: { name?: string }) => meta.name === "description")).toBe(
        true
      )
      expect(failedDashboardHead.meta.some((meta: { title?: string }) => meta.title)).toBe(true)
      expect(
        failedDashboardHead.meta.filter((meta: { name?: string }) => meta.name === "description")
      ).toHaveLength(1)
      expect(
        dashboardHead.meta.some(
          (meta: { name?: string }) => meta.name === "google-site-verification"
        )
      ).toBe(true)
      expect(dashboardHead.links).toEqual(rootHead.links)
      for (const routeId of pageSeoRouteIds) {
        const pageHead = headFn({ matches: [{ routeId, status: "success" }] } as any) as any
        expect(pageHead.meta.some((meta: { title?: string }) => meta.title)).toBe(false)
        expect(pageHead.meta.some((meta: { name?: string }) => meta.name === "description")).toBe(
          false
        )
        expect(
          pageHead.meta.some((meta: { property?: string }) => meta.property === "og:type")
        ).toBe(false)
        expect(
          pageHead.meta.some((meta: { property?: string }) => meta.property === "og:title")
        ).toBe(false)
        expect(
          pageHead.meta.some((meta: { property?: string }) => meta.property === "og:description")
        ).toBe(false)
        expect(
          pageHead.meta.some((meta: { property?: string }) => meta.property === "og:image")
        ).toBe(false)
        expect(pageHead.meta.some((meta: { name?: string }) => meta.name === "twitter:card")).toBe(
          false
        )
        expect(pageHead.meta.some((meta: { name?: string }) => meta.name === "twitter:title")).toBe(
          false
        )
        expect(
          pageHead.meta.some((meta: { name?: string }) => meta.name === "twitter:description")
        ).toBe(false)
        expect(pageHead.meta.some((meta: { name?: string }) => meta.name === "twitter:image")).toBe(
          false
        )
      }
      expect(activityClientHead.meta.some((meta: { title?: string }) => meta.title)).toBe(false)
      expect(activityServerHead.meta.some((meta: { title?: string }) => meta.title)).toBe(false)
    })
  })
})
