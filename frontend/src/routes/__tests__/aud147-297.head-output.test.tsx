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
import { SEO, SeoReadinessProvider } from "@/components/ui/SEO"
import { createI18nInstance } from "@/i18n/config"
import { useAuthStore } from "@/stores/useAuthStore"
import { Route as AuthRoute } from "../_auth"
import { Route as MapRoute } from "../_auth/map"
import { Route as MessengerRoute } from "../_auth/messenger"
import { Route as MessengerDetailRoute } from "../_auth/messenger.$chatId"
import { Route as PublicRoute } from "../_public"
import { Route as LoginRoute } from "../_public/login"
import { ActivityRootSeoFallback, Route as ProductionRootRoute } from "../__root"

type Language = "en" | "ru"

const titleCases = [
  ["/login", "Sign in", "Вход"],
  ["/forgot-password", "Reset password", "Восстановление пароля"],
  ["/register", "Sign up", "Регистрация"],
  ["/reset-password", "Create a new password", "Новый пароль"],
  ["/reset-password/example-token", "Create a new password", "Новый пароль"],
  ["/settings", "Settings", "Настройки"],
  ["/map", "Campus map", "Карта кампуса"],
  ["/messenger", "Messages", "Сообщения"],
  ["/messenger/example-chat", "Messages", "Сообщения"],
] as const

// Only page bodies are stubs: the real route layouts, their PageRouteSEO,
// production root head, React metadata hoisting and SSR modes are exercised.
function createHeadRouter(
  isServer: boolean,
  initialPath: string,
  language: Language,
  failNestedRoute = false
) {
  const i18n = createI18nInstance(language)
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
  const root = createRootRoute({
    head: (options) => {
      const productionHead = ProductionRootRoute.options.head
      if (!productionHead) throw new Error("Production root head metadata is missing")
      return productionHead(options as never)
    },
    component: () => <Outlet />,
    shellComponent: DocumentShell,
  })
  const publicLayout = createRoute({
    getParentRoute: () => root as never,
    id: "_public",
    component: PublicRoute.options.component,
  })
  const authLayout = createRoute({
    getParentRoute: () => root as never,
    id: "_auth",
    component: AuthRoute.options.component,
  })
  const publicPages = ["/login", "/forgot-password", "/register"].map((path) =>
    createRoute({
      getParentRoute: () => publicLayout as never,
      path,
      validateSearch: path === "/login" ? LoginRoute.options.validateSearch : undefined,
      component: () => <p>Public</p>,
    })
  )
  const resetPage = createRoute({
    getParentRoute: () => publicLayout as never,
    path: "/reset-password",
    component: () => <p>Public</p>,
  })
  const resetTokenPage = createRoute({
    getParentRoute: () => resetPage as never,
    path: "/$token",
    loader: failNestedRoute
      ? () => {
          throw new Error("Nested route failed")
        }
      : undefined,
    component: () => <p>Reset</p>,
  })
  const authPages = [
    { path: "/settings", ssr: true as const },
    { path: "/map", ssr: MapRoute.options.ssr },
  ].map(({ path, ssr }) =>
    createRoute({
      getParentRoute: () => authLayout as never,
      path,
      ssr,
      component: () => <p>Authenticated</p>,
    })
  )
  const messengerPage = createRoute({
    getParentRoute: () => authLayout as never,
    path: "/messenger",
    ssr: MessengerRoute.options.ssr,
    component: () => <p>Messenger</p>,
  })
  const messengerDetailPage = createRoute({
    getParentRoute: () => messengerPage as never,
    path: "/$chatId",
    ssr: MessengerDetailRoute.options.ssr,
    component: () => <p>Chat</p>,
  })
  const customPage = createRoute({
    getParentRoute: () => authLayout as never,
    path: "/dashboard",
    component: () => (
      <>
        <SEO title="Custom dashboard" description="Custom description" image="/custom-image.png" />
        <p>Dashboard</p>
      </>
    ),
  })
  const fallbackPage = createRoute({
    getParentRoute: () => root as never,
    path: "/fallback",
    component: () => <p>Fallback</p>,
  })
  const router = createRouter({
    routeTree: root.addChildren([
      publicLayout.addChildren([
        ...publicPages,
        resetPage.addChildren([resetTokenPage as unknown as AnyRoute]),
      ] as unknown as AnyRoute[]) as unknown as AnyRoute,
      authLayout.addChildren([
        ...authPages,
        customPage,
        messengerPage.addChildren([messengerDetailPage as unknown as AnyRoute]),
      ] as unknown as AnyRoute[]) as unknown as AnyRoute,
      fallbackPage as unknown as AnyRoute,
    ]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
    isServer,
  })
  return { router, i18n }
}

function expectPageHead(
  head: HTMLHeadElement,
  title: string,
  description: string,
  socialDescription: string
) {
  const fullTitle = `${title} | University Ecosystem`
  expect(Array.from(head.querySelectorAll("title"), (element) => element.textContent)).toEqual([
    fullTitle,
  ])
  const expected = [
    ['meta[name="title"]', fullTitle],
    ['meta[name="description"]', description],
    ['meta[property="og:type"]', "website"],
    ['meta[property="og:title"]', fullTitle],
    ['meta[property="og:description"]', socialDescription],
    ['meta[property="og:image"]', "/icon-512.png"],
    ['meta[name="twitter:card"]', "summary_large_image"],
    ['meta[name="twitter:title"]', fullTitle],
    ['meta[name="twitter:description"]', socialDescription],
    ['meta[name="twitter:image"]', "/icon-512.png"],
  ] as const
  for (const [selector, content] of expected) {
    const elements = head.querySelectorAll<HTMLMetaElement>(selector)
    expect(elements, selector).toHaveLength(1)
    expect(elements[0]?.content, selector).toBe(content)
  }
}

describe("AUD-147 and AUD-297 rendered head ownership", () => {
  let initialSsr: boolean
  let initialLanguage: string
  let initialSelectedLanguage: "en" | "ru" | undefined
  let root: Root | undefined
  const histories: Array<{ destroy: () => void }> = []

  beforeEach(() => {
    initialSsr = import.meta.env.SSR
    initialLanguage = document.documentElement.lang
    initialSelectedLanguage = window.__UE_SELECTED_LANG__
    useAuthStore.setState({ user: null, loading: true })
  })

  afterEach(async () => {
    if (root) await act(async () => root?.unmount())
    root = undefined
    histories.splice(0).forEach((history) => history.destroy())
    vi.unstubAllGlobals()
    import.meta.env.SSR = initialSsr
    document.documentElement.lang = initialLanguage
    if (initialSelectedLanguage === undefined) delete window.__UE_SELECTED_LANG__
    else window.__UE_SELECTED_LANG__ = initialSelectedLanguage
  })

  it.each(titleCases)("renders one localized metadata set for %s on SSR", async (path, en, ru) => {
    for (const language of ["en", "ru"] as const) {
      import.meta.env.SSR = true
      const { router, i18n } = createHeadRouter(true, path, language)
      histories.push(router.history)
      vi.stubGlobal("__ssrLangGetter__", () => language)
      vi.stubGlobal("__ssrI18nGetter__", () => i18n)
      await router.load()
      const markup = renderToString(<RouterProvider router={router as never} />)
      const rendered = new DOMParser().parseFromString(markup, "text/html")
      const title = language === "en" ? en : ru
      const expectedDescription = i18n.t("navigation:brandDescription")
      const expectedSocialDescription = i18n.t("navigation:socialDescription")
      expectPageHead(rendered.head, title, expectedDescription, expectedSocialDescription)
    }
  })

  it("keeps exactly one fallback metadata set when login search validation fails", async () => {
    import.meta.env.SSR = true
    const { router, i18n } = createHeadRouter(true, "/login?redirect=%7B%7D", "en")
    histories.push(router.history)
    vi.stubGlobal("__ssrLangGetter__", () => "en")
    vi.stubGlobal("__ssrI18nGetter__", () => i18n)
    await router.load()
    expect(router.state.matches.at(-1)?.status).toBe("error")
    const markup = renderToString(<RouterProvider router={router as never} />)
    const rendered = new DOMParser().parseFromString(markup, "text/html")
    expect(
      Array.from(rendered.head.querySelectorAll("title"), (element) => element.textContent)
    ).toEqual(["GUU Ecosystem"])
    for (const selector of [
      'meta[name="description"]',
      'meta[property="og:title"]',
      'meta[property="og:description"]',
      'meta[name="twitter:title"]',
      'meta[name="twitter:description"]',
    ]) {
      expect(rendered.head.querySelectorAll(selector), selector).toHaveLength(1)
    }
  })

  it("keeps the successful parent metadata when a nested mapped route fails", async () => {
    import.meta.env.SSR = true
    const { router, i18n } = createHeadRouter(true, "/reset-password/example-token", "en", true)
    histories.push(router.history)
    vi.stubGlobal("__ssrLangGetter__", () => "en")
    vi.stubGlobal("__ssrI18nGetter__", () => i18n)
    await router.load()
    expect(router.state.matches.at(-2)?.routeId).toBe("/_public/reset-password")
    expect(router.state.matches.at(-2)?.status).toBe("success")
    expect(router.state.matches.at(-1)?.status).toBe("error")
    const markup = renderToString(<RouterProvider router={router as never} />)
    const rendered = new DOMParser().parseFromString(markup, "text/html")
    expectPageHead(
      rendered.head,
      "Create a new password",
      i18n.t("navigation:brandDescription"),
      i18n.t("navigation:socialDescription")
    )
  })

  it("keeps custom page metadata unique, then updates titles through client navigation and language changes", async () => {
    const language = "en"
    import.meta.env.SSR = true
    // Match the existing hydration harness: router.isServer stays false on
    // both sides because this fixture does not run TanStack's SSR dehydrate /
    // client rehydrate protocol. The matrix above exercises isServer=true.
    const server = createHeadRouter(false, "/dashboard", language)
    histories.push(server.router.history)
    vi.stubGlobal("__ssrLangGetter__", () => language)
    vi.stubGlobal("__ssrI18nGetter__", () => server.i18n)
    await server.router.load()
    const markup = renderToString(<RouterProvider router={server.router as never} />)
    const rendered = new DOMParser().parseFromString(markup, "text/html")
    expect(rendered.head.querySelectorAll("title")).toHaveLength(1)
    expect(rendered.title).toBe("Custom dashboard | University Ecosystem")
    for (const selector of [
      'meta[name="description"]',
      'meta[property="og:description"]',
      'meta[name="twitter:description"]',
    ]) {
      expect(rendered.head.querySelectorAll(selector)).toHaveLength(1)
      expect(rendered.head.querySelector<HTMLMetaElement>(selector)?.content).toBe(
        "Custom description"
      )
    }
    for (const selector of ['meta[property="og:image"]', 'meta[name="twitter:image"]']) {
      expect(rendered.head.querySelectorAll(selector)).toHaveLength(1)
      expect(rendered.head.querySelector<HTMLMetaElement>(selector)?.content).toBe(
        "/custom-image.png"
      )
    }

    document.open()
    document.write(`<!doctype html>${markup}`)
    document.close()
    import.meta.env.SSR = false
    const client = createHeadRouter(false, "/dashboard", language)
    histories.push(client.router.history)
    await client.router.load()
    const recoverableErrors: string[] = []
    await act(async () => {
      root = hydrateRoot(document, <RouterProvider router={client.router as never} />, {
        onRecoverableError: (error) => recoverableErrors.push(String(error)),
      })
    })
    expect(recoverableErrors, "initial hydration").toEqual([])
    for (const [path, title] of [
      ["/login", "Sign in"],
      ["/settings", "Settings"],
      ["/map", "Campus map"],
      ["/messenger/example-chat", "Messages"],
    ] as const) {
      await act(async () => {
        await client.router.navigate({ to: path as never })
      })
      await waitFor(() => expect(document.title).toBe(`${title} | University Ecosystem`))
      expect(recoverableErrors, path).toEqual([])
      expect(document.head.querySelectorAll("title")).toHaveLength(1)
      for (const selector of [
        'meta[name="description"]',
        'meta[property="og:title"]',
        'meta[property="og:description"]',
        'meta[name="twitter:title"]',
        'meta[name="twitter:description"]',
      ]) {
        expect(document.head.querySelectorAll(selector), selector).toHaveLength(1)
      }
    }
    await act(async () => {
      await client.i18n.changeLanguage("ru")
    })
    await waitFor(() => expect(document.title).toBe("Сообщения | University Ecosystem"))
    expect(recoverableErrors).toEqual([])
    expect(document.head.querySelectorAll("title")).toHaveLength(1)
    await act(async () => {
      await client.router.navigate({ to: "/fallback" as never })
    })
    await waitFor(() => expect(document.title).toBe("GUU Ecosystem"))
    expect(document.head.querySelectorAll("title")).toHaveLength(1)
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1)
    expect(recoverableErrors).toEqual([])
  })
})
