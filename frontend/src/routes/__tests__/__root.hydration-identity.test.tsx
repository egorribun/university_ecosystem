import { expect, it, vi } from "vitest"
import { act, useId } from "react"
import { renderToString } from "react-dom/server"
import { hydrateRoot } from "react-dom/client"
import { QueryClient } from "@tanstack/react-query"
const seen = vi.hoisted(() => ({ ids: [] as string[] }))
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<any>()),
  HeadContent: () => null,
  Scripts: () => null,
  Outlet: () => {
    const id = useId()
    seen.ids.push(id)
    return <div id={id} data-testid="id-probe" />
  },
  useHydrated: () => false,
  useRouterState: (options: any) => options.select({ matches: [] }),
  useRouteContext: () => ({ queryClient: new QueryClient() }),
}))
vi.mock("@/components/ui/SEO", async (importOriginal) => ({
  ...(await importOriginal<any>()),
  usePageSeoReady: () => false,
}))
vi.mock("@/AppProviders", () => ({ AppProviders: ({ children }: any) => <div>{children}</div> }))
vi.mock("@/components/layout/MainLayout", () => ({
  MainLayout: ({ children }: any) => <div>{children}</div>,
}))
vi.mock("@/components/error/PageErrorBoundary", () => ({
  PageErrorBoundary: ({ children }: any) => <div>{children}</div>,
}))
vi.mock("@/contexts/ThemeContext", () => ({
  ThemeProvider: ({ children }: any) => <div>{children}</div>,
}))
vi.mock("@/components/feedback/BrandBootLoader", () => ({ BrandBootLoader: () => null }))
vi.mock("@/components/layout/DeferredGlobalOverlays", () => ({
  DeferredGlobalOverlays: () => null,
}))
vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<any>()),
  QueryClientProvider: ({ children }: any) => <>{children}</>,
}))
vi.mock("@tanstack/react-query-persist-client", () => ({
  PersistQueryClientProvider: ({ children }: any) => <>{children}</>,
}))
it("keeps real root descendant useId stable through SSR hydration", async () => {
  const { Route } = await import("../__root")
  vi.spyOn(Route, "useLoaderData").mockReturnValue({ campusTimezone: "Europe/Moscow" })
  const Component = (Route.options as any).component
  vi.stubEnv("SSR", true)
  const html = renderToString(<Component />)
  const serverId = seen.ids.at(-1)
  const container = document.createElement("div")
  document.body.append(container)
  container.innerHTML = html
  const originalNode = container.querySelector('[data-testid="id-probe"]')
  const errors = vi.spyOn(console, "error")
  const recoveries: unknown[] = []
  vi.stubEnv("SSR", false)
  let root: ReturnType<typeof hydrateRoot> | undefined
  try {
    await act(async () => {
      root = hydrateRoot(container, <Component />, {
        onRecoverableError: (error) => recoveries.push(error),
      })
    })
    const clientId = seen.ids.at(-1)
    expect(clientId).toBe(serverId)
    expect(container.querySelector('[data-testid="id-probe"]')).toBe(originalNode)
    expect(originalNode?.id).toBe(clientId)
    expect(errors).not.toHaveBeenCalled()
    expect(recoveries).toEqual([])
  } finally {
    await act(async () => root?.unmount())
    container.remove()
    errors.mockRestore()
    vi.unstubAllEnvs()
  }
})
