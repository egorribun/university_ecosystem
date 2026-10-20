import { act, waitFor } from "@testing-library/react"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  HeadContent,
  Outlet,
  RouterProvider,
  type AnyRoute,
} from "@tanstack/react-router"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { I18nextProvider } from "react-i18next"
import { lazy } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createI18nInstance } from "@/i18n/config"
import { SEO, SeoReadinessProvider } from "@/components/ui/SEO"
import { Route as ActivityFileRoute } from "../_auth/activity"
import { ActivityRootSeoFallback, Route as ProductionRootRoute } from "../__root"

vi.mock("@/features/activity", () => ({
  ActivityFeature: () => <div data-testid="activity-feature">Activity feature</div>,
}))

function createActivityRouter(
  isServer: boolean,
  language: "en" | "ru",
  i18n: ReturnType<typeof createI18nInstance>,
  failActivity = false,
  initialPath = "/activity",
  activityComponent = ActivityFileRoute.options.component
) {
  const DocumentShell = ({ children }: { children: React.ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <SeoReadinessProvider>
        <html lang={language}>
          <head>
            <HeadContent />
            <ActivityRootSeoFallback />
          </head>
          <body>
            <div id="root">{children}</div>
          </body>
        </html>
      </SeoReadinessProvider>
    </I18nextProvider>
  )

  const rootRoute = createRootRoute({
    head: (options) => {
      const productionHead = ProductionRootRoute.options.head
      if (!productionHead) throw new Error("Production root head metadata is missing")
      return productionHead(options as never)
    },
    component: () => <Outlet />,
    shellComponent: DocumentShell,
  })
  const authRoute = createRoute({
    getParentRoute: () => rootRoute as never,
    id: "_auth",
    component: () => <Outlet />,
  })
  const activityRoute = createRoute({
    getParentRoute: () => authRoute as never,
    path: "/activity",
    ssr: ActivityFileRoute.options.ssr,
    loader: failActivity
      ? async () => {
          throw new Error("Activity loader failed")
        }
      : undefined,
    errorComponent: () => <div data-testid="activity-error">Activity unavailable</div>,
    component: activityComponent,
  })
  const publicRoute = createRoute({
    getParentRoute: () => rootRoute as never,
    path: "/public",
    component: () => <div data-testid="public-page">Public page</div>,
  })
  const dashboardRoute = createRoute({
    getParentRoute: () => authRoute as never,
    path: "/dashboard",
    component: () => (
      <SEO title="Dashboard" description="Your dashboard keeps university work together" />
    ),
  })
  const routeTree = rootRoute.addChildren([
    authRoute.addChildren([
      activityRoute as unknown as AnyRoute,
      dashboardRoute as unknown as AnyRoute,
    ]) as unknown as AnyRoute,
    publicRoute as unknown as AnyRoute,
  ])

  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initialPath] }),
    isServer,
  })

  return router
}

function metaValue(selector: string): string | null {
  return document.head.querySelector<HTMLMetaElement>(selector)?.content ?? null
}

function expectRootFallbackMetadata(head: HTMLHeadElement): void {
  const values = [
    [
      'meta[name="description"]',
      "Everything you need—profile, schedule, news, and campus events—in one place.",
    ],
    ['meta[property="og:type"]', "website"],
    ['meta[property="og:title"]', "GUU Ecosystem"],
    [
      'meta[property="og:description"]',
      "Your personal account: profile, schedule, news, and campus events.",
    ],
    ['meta[property="og:image"]', "/og-image.png"],
    ['meta[name="twitter:card"]', "summary_large_image"],
    ['meta[name="twitter:title"]', "GUU Ecosystem"],
    [
      'meta[name="twitter:description"]',
      "Your personal account: profile, schedule, news, and campus events.",
    ],
    ['meta[name="twitter:image"]', "/og-image.png"],
  ] as const

  expect(Array.from(head.querySelectorAll("title"), (title) => title.textContent)).toEqual([
    "GUU Ecosystem",
  ])
  expect(head.querySelectorAll('meta[name="title"]')).toHaveLength(0)
  for (const [selector, content] of values) {
    const tags = head.querySelectorAll<HTMLMetaElement>(selector)
    expect(tags).toHaveLength(1)
    expect(tags[0]?.content).toBe(content)
  }
}

describe("Activity data-only SEO document hydration", () => {
  let mountedRoot: Root | undefined
  let serverI18n: ReturnType<typeof createI18nInstance> | undefined
  let previousSsr: boolean | undefined
  let previousHtmlLang: string
  let previousSelectedLanguage: "en" | "ru" | undefined
  let serverRouter: ReturnType<typeof createActivityRouter> | undefined
  let clientRouter: ReturnType<typeof createActivityRouter> | undefined

  beforeEach(() => {
    previousSsr = import.meta.env.SSR
    previousHtmlLang = document.documentElement.lang
    previousSelectedLanguage = window.__UE_SELECTED_LANG__
    serverRouter = undefined
    clientRouter = undefined
    mountedRoot = undefined
    serverI18n = undefined
  })

  afterEach(async () => {
    if (mountedRoot) {
      await act(async () => mountedRoot?.unmount())
      mountedRoot = undefined
    }
    serverRouter?.history.destroy()
    clientRouter?.history.destroy()
    serverRouter = undefined
    clientRouter = undefined
    serverI18n = undefined
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    if (typeof previousSsr === "boolean") {
      import.meta.env.SSR = previousSsr
      document.documentElement.lang = previousHtmlLang
      if (previousSelectedLanguage === undefined) {
        Reflect.deleteProperty(window, "__UE_SELECTED_LANG__")
      } else {
        window.__UE_SELECTED_LANG__ = previousSelectedLanguage
      }
    }
  })

  it("replaces the server root fallback with one localized Activity metadata set after real hydration", async () => {
    const language = "en"
    serverI18n = createI18nInstance(language)
    vi.stubGlobal("__ssrLangGetter__", () => language)
    vi.stubGlobal("__ssrI18nGetter__", () => serverI18n)
    window.__UE_SELECTED_LANG__ = language

    import.meta.env.SSR = true
    serverRouter = createActivityRouter(false, language, serverI18n)
    await serverRouter.load()
    const serverMarkup = renderToString(<RouterProvider router={serverRouter as never} />)
    const serverDocument = new DOMParser().parseFromString(serverMarkup, "text/html")

    expect(ActivityFileRoute.options.ssr).toBe("data-only")
    expect(serverRouter.state.matches.at(-1)?.ssr).toBe("data-only")
    expectRootFallbackMetadata(serverDocument.head)
    expect(serverDocument.querySelector('[data-testid="activity-feature"]')).toBeNull()

    document.open()
    document.write(`<!doctype html>${serverMarkup}`)
    document.close()

    import.meta.env.SSR = false
    clientRouter = createActivityRouter(false, language, serverI18n)
    await clientRouter.load()
    expect(
      clientRouter.state.matches.map(({ routeId, status }) => [routeId, status])
    ).toContainEqual(["/_auth/activity", "success"])
    await act(async () => {
      mountedRoot = hydrateRoot(document, <RouterProvider router={clientRouter as never} />)
    })
    expectRootFallbackMetadata(document.head)

    await waitFor(() =>
      expect(document.querySelector('[data-testid="activity-feature"]')).toBeInTheDocument()
    )
    expect(document.title).toBe("Activity | University Ecosystem")
    expect(
      Array.from(document.head.querySelectorAll("title"), (title) => title.textContent)
    ).toEqual(["Activity | University Ecosystem"])
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[property="og:title"]')).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[property="og:description"]')).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[name="twitter:title"]')).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[name="twitter:description"]')).toHaveLength(1)
    expect(metaValue('meta[name="description"]')).toBe(
      "Track your event registrations, grades, and participation"
    )
    expect(metaValue('meta[property="og:title"]')).toBe("Activity | University Ecosystem")
    expect(metaValue('meta[property="og:description"]')).toBe(
      "Track your event registrations, grades, and participation"
    )
    expect(metaValue('meta[name="twitter:title"]')).toBe("Activity | University Ecosystem")
    expect(metaValue('meta[name="twitter:description"]')).toBe(
      "Track your event registrations, grades, and participation"
    )

    await act(async () => {
      await clientRouter?.navigate({ to: "/public" as never })
    })
    expect(document.querySelector('[data-testid="public-page"]')).toBeInTheDocument()
    expectRootFallbackMetadata(document.head)

    await act(async () => {
      await clientRouter?.navigate({ to: "/activity" as never })
    })
    expect(document.querySelector('[data-testid="activity-feature"]')).toBeInTheDocument()
    expect(document.title).toBe("Activity | University Ecosystem")
    expect(document.head.querySelectorAll("title")).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1)
    expect(metaValue('meta[property="og:title"]')).toBe("Activity | University Ecosystem")
  })

  it("keeps root metadata while a lazy Activity route follows an SEO page in SPA navigation", async () => {
    const language = "en"
    const i18n = createI18nInstance(language)
    serverI18n = i18n
    vi.stubGlobal("__ssrLangGetter__", () => language)
    vi.stubGlobal("__ssrI18nGetter__", () => i18n)
    window.__UE_SELECTED_LANG__ = language

    let releaseActivityImport!: () => void
    let activityImportLoaded!: () => void
    const activityImportGate = new Promise<void>((resolve) => {
      releaseActivityImport = resolve
    })
    const activityImportFinished = new Promise<void>((resolve) => {
      activityImportLoaded = resolve
    })
    const DeferredActivity = lazy(async () => {
      await activityImportGate
      const pageModule = await import("@/pages/Activity")
      activityImportLoaded()
      return pageModule
    })

    import.meta.env.SSR = true
    serverRouter = createActivityRouter(
      false,
      language,
      i18n,
      false,
      "/dashboard",
      DeferredActivity
    )
    await serverRouter.load()
    const serverMarkup = renderToString(<RouterProvider router={serverRouter as never} />)
    const serverDocument = new DOMParser().parseFromString(serverMarkup, "text/html")
    expect(serverDocument.title).toBe("Dashboard | University Ecosystem")
    expect(serverDocument.head.querySelectorAll("title")).toHaveLength(1)

    document.open()
    document.write(`<!doctype html>${serverMarkup}`)
    document.close()

    import.meta.env.SSR = false
    clientRouter = createActivityRouter(
      false,
      language,
      i18n,
      false,
      "/dashboard",
      DeferredActivity
    )
    await clientRouter.load()
    await act(async () => {
      mountedRoot = hydrateRoot(document, <RouterProvider router={clientRouter as never} />)
    })
    expect(document.title).toBe("Dashboard | University Ecosystem")
    expect(document.head.querySelectorAll("title")).toHaveLength(1)

    await act(async () => {
      await clientRouter?.navigate({ to: "/activity" as never })
    })
    expect(clientRouter.state.matches.at(-1)?.status).toBe("success")
    expect(document.title).toBe("GUU Ecosystem")
    expect(document.head.querySelectorAll("title")).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1)
    expect(metaValue('meta[property="og:title"]')).toBe("GUU Ecosystem")

    await act(async () => {
      await clientRouter?.navigate({ to: "/dashboard" as never })
    })
    expect(document.title).toBe("Dashboard | University Ecosystem")
    expect(document.head.querySelectorAll("title")).toHaveLength(1)
    expect(metaValue('meta[property="og:title"]')).toBe("Dashboard | University Ecosystem")

    await act(async () => {
      releaseActivityImport()
      await activityImportFinished
    })
    expect(document.querySelector('[data-testid="activity-feature"]')).toBeNull()
    expect(document.title).toBe("Dashboard | University Ecosystem")
    expect(document.head.querySelectorAll("title")).toHaveLength(1)

    await act(async () => {
      await clientRouter?.navigate({ to: "/activity" as never })
    })
    await waitFor(() =>
      expect(document.querySelector('[data-testid="activity-feature"]')).toBeInTheDocument()
    )
    expect(document.title).toBe("Activity | University Ecosystem")
    expect(document.head.querySelectorAll("title")).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1)
    expect(metaValue('meta[property="og:title"]')).toBe("Activity | University Ecosystem")

    await act(async () => {
      await clientRouter?.navigate({ to: "/dashboard" as never })
    })
    expect(document.title).toBe("Dashboard | University Ecosystem")
    expect(document.head.querySelectorAll("title")).toHaveLength(1)
    expect(metaValue('meta[property="og:title"]')).toBe("Dashboard | University Ecosystem")
  })

  it("keeps the localized root metadata when the Activity route fails", async () => {
    const language = "en"
    serverI18n = createI18nInstance(language)
    vi.stubGlobal("__ssrLangGetter__", () => language)
    vi.stubGlobal("__ssrI18nGetter__", () => serverI18n)
    window.__UE_SELECTED_LANG__ = language
    import.meta.env.SSR = true

    serverRouter = createActivityRouter(false, language, serverI18n, true)
    await serverRouter.load()
    const markup = renderToString(<RouterProvider router={serverRouter as never} />)
    const serverDocument = new DOMParser().parseFromString(markup, "text/html")

    expect(serverRouter.state.matches.at(-1)?.status).toBe("error")
    expect(serverDocument.querySelector('[data-testid="activity-feature"]')).toBeNull()
    expectRootFallbackMetadata(serverDocument.head)
  })
})
