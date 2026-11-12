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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createI18nInstance } from "@/i18n/config"
import { withExpectedConsole } from "@/tests/strictConsole"
import { SEO, SeoReadinessProvider } from "@/components/ui/SEO"
import enActivity from "@/i18n/locales/en/activity.json"
import enNavigation from "@/i18n/locales/en/navigation.json"
import { Route as ActivityFileRoute } from "../_auth/activity"
import { ActivityRootSeoFallback, Route as ProductionRootRoute } from "../__root"

vi.mock("@/features/activity", () => ({
  ActivityFeature: () => <div data-testid="activity-feature">Activity feature</div>,
}))

type ActivityLoaderGate = {
  loader: () => Promise<void>
  release: (outcome: "ok" | "fail") => void
}

// The Activity loader decides when a client navigation leaves `pending`, so
// holding it open makes the pending window observable from the test.
function createActivityLoaderGate(): ActivityLoaderGate {
  let release!: (outcome: "ok" | "fail") => void
  const outcome = new Promise<"ok" | "fail">((resolve) => {
    release = resolve
  })
  return {
    loader: async () => {
      if ((await outcome) === "fail") throw new Error("Activity loader failed")
    },
    release,
  }
}

function createSpaRouter(
  isServer: boolean,
  i18n: ReturnType<typeof createI18nInstance>,
  language: "en" | "ru",
  initialPath: string,
  activityLoader?: () => Promise<void>
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
    loader: activityLoader,
    errorComponent: () => <div data-testid="activity-error">Activity unavailable</div>,
    component: ActivityFileRoute.options.component,
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

  return createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initialPath] }),
    isServer,
  })
}

const SINGLE_TAG_SELECTORS = [
  "title",
  'meta[name="description"]',
  'meta[property="og:title"]',
  'meta[property="og:description"]',
  'meta[name="twitter:title"]',
  'meta[name="twitter:description"]',
] as const

// Asserts exactly one copy of each brand/page SEO tag. A duplicate here is the
// AUD-432 regression: root brand metadata and page metadata both in <head>.
function expectSingleSeoSet(): void {
  for (const selector of SINGLE_TAG_SELECTORS) {
    expect(document.head.querySelectorAll(selector), selector).toHaveLength(1)
  }
}

function headTitles(): string[] {
  return Array.from(document.head.querySelectorAll("title"), (title) => title.textContent ?? "")
}

async function flushMicrotasks(): Promise<void> {
  await new Promise<void>((resolve) => setTimeout(resolve, 0))
}

const BRAND_TITLE = enNavigation.brandName
const DASHBOARD_TITLE = "Dashboard | University Ecosystem"
const ACTIVITY_TITLE = `${enActivity.title} | University Ecosystem`

const SPA_CASES = [
  {
    name: "from the dashboard page SEO",
    startPath: "/dashboard",
    startTitle: DASHBOARD_TITLE,
    awayPath: "/public",
    awayTitle: BRAND_TITLE,
  },
  {
    name: "from a brand-only page",
    startPath: "/public",
    startTitle: BRAND_TITLE,
    awayPath: "/dashboard",
    awayTitle: DASHBOARD_TITLE,
  },
] as const

describe("Activity SPA navigation keeps exactly one SEO set", () => {
  let mountedRoot: Root | undefined
  let serverRouter: ReturnType<typeof createSpaRouter> | undefined
  let clientRouter: ReturnType<typeof createSpaRouter> | undefined
  let previousSsr: boolean
  let previousHtmlLang: string
  let previousSelectedLanguage: "en" | "ru" | undefined

  beforeEach(() => {
    previousSsr = import.meta.env.SSR
    previousHtmlLang = document.documentElement.lang
    previousSelectedLanguage = window.__UE_SELECTED_LANG__
    mountedRoot = undefined
    serverRouter = undefined
    clientRouter = undefined
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
    vi.unstubAllGlobals()
    import.meta.env.SSR = previousSsr
    document.documentElement.lang = previousHtmlLang
    if (previousSelectedLanguage === undefined) {
      Reflect.deleteProperty(window, "__UE_SELECTED_LANG__")
    } else {
      window.__UE_SELECTED_LANG__ = previousSelectedLanguage
    }
  })

  // Server-renders the start page, writes it into the document, and hydrates
  // the client router there. The Activity loader is gated so that the SPA
  // navigation can be observed while the route is still pending.
  async function hydrateStartPage(startPath: string, gate: ActivityLoaderGate): Promise<void> {
    const language = "en"
    const i18n = createI18nInstance(language)
    vi.stubGlobal("__ssrLangGetter__", () => language)
    vi.stubGlobal("__ssrI18nGetter__", () => i18n)
    window.__UE_SELECTED_LANG__ = language

    import.meta.env.SSR = true
    serverRouter = createSpaRouter(false, i18n, language, startPath)
    await serverRouter.load()
    const markup = renderToString(<RouterProvider router={serverRouter as never} />)
    document.open()
    document.write(`<!doctype html>${markup}`)
    document.close()

    import.meta.env.SSR = false
    clientRouter = createSpaRouter(false, i18n, language, startPath, gate.loader)
    await clientRouter.load()
    await act(async () => {
      mountedRoot = hydrateRoot(document, <RouterProvider router={clientRouter as never} />)
    })
  }

  it.each(SPA_CASES)(
    "keeps one SEO set through pending, success and leaving Activity $name",
    async ({ startPath, startTitle, awayPath, awayTitle }) => {
      const gate = createActivityLoaderGate()
      await hydrateStartPage(startPath, gate)
      expect(document.title).toBe(startTitle)
      expect(headTitles()).toEqual([startTitle])
      expectSingleSeoSet()

      let navigation: Promise<unknown> = Promise.resolve()
      await act(async () => {
        navigation = clientRouter!.navigate({ to: "/activity" as never })
        await flushMicrotasks()
      })
      // The router keeps the previous matches committed while the Activity
      // loader is pending, so the head must still describe the start page.
      expect(clientRouter?.state.status).toBe("pending")
      expect(clientRouter?.state.isLoading).toBe(true)
      expect(clientRouter?.state.location.pathname).toBe("/activity")
      expect(headTitles()).toEqual([startTitle])
      expectSingleSeoSet()

      await act(async () => {
        gate.release("ok")
        await navigation
      })
      expect(clientRouter?.state.status).toBe("idle")
      expect(clientRouter?.state.matches.at(-1)?.status).toBe("success")
      await waitFor(() =>
        expect(document.querySelector('[data-testid="activity-feature"]')).toBeInTheDocument()
      )
      expect(headTitles()).toEqual([ACTIVITY_TITLE])
      expectSingleSeoSet()

      await act(async () => {
        await clientRouter?.navigate({ to: awayPath as never })
      })
      expect(headTitles()).toEqual([awayTitle])
      expectSingleSeoSet()
    }
  )

  it.each(SPA_CASES)(
    "keeps one SEO set when the Activity loader fails $name",
    async ({ startPath }) => {
      const gate = createActivityLoaderGate()
      await hydrateStartPage(startPath, gate)

      let navigation: Promise<unknown> = Promise.resolve()
      await act(async () => {
        navigation = clientRouter!.navigate({ to: "/activity" as never })
        await flushMicrotasks()
      })
      expect(clientRouter?.state.status).toBe("pending")
      expectSingleSeoSet()

      // TanStack reports the uncaught loader error through the router warning
      // and React's caught-error log; both are the expected outcome here.
      // TanStack logs the route error and the uncaught-route warning, and React
      // logs the caught error. The allow-list must stay open until the error UI
      // has committed, because those logs are emitted by that commit.
      const formatted = (args: readonly unknown[]) => args.map((arg) => String(arg)).join(" ")
      await withExpectedConsole(
        "warn",
        (args) =>
          formatted(args).includes("Error in route match") ||
          formatted(args).includes("wasn't caught by any route"),
        () =>
          withExpectedConsole(
            "error",
            (args) => formatted(args).includes("Activity loader failed"),
            async () => {
              await act(async () => {
                gate.release("fail")
                await navigation.catch(() => undefined)
              })
              await waitFor(() =>
                expect(document.querySelector('[data-testid="activity-error"]')).toBeInTheDocument()
              )
            }
          )
      )
      expect(clientRouter?.state.matches.at(-1)?.status).toBe("error")
      expect(headTitles()).toEqual([BRAND_TITLE])
      expectSingleSeoSet()
    }
  )
})
