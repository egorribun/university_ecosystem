import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  DEFERRED_GLOBAL_OVERLAYS_READY_EVENT,
  DEFERRED_OVERLAY_DELAY_MS,
  DeferredGlobalOverlays,
} from "../DeferredGlobalOverlays"
import enCommon from "@/i18n/locales/en/common.json"

vi.mock("@/components/feedback/OfflineIndicator", () => ({
  OfflineIndicator: () => null,
}))
vi.mock("@/components/feedback/LivePushToasts", () => ({
  default: () => null,
}))
vi.mock("@/components/pwa/InstallPrompt", () => ({
  default: () => null,
}))
vi.mock("@/push/pushMessageBus", () => ({
  ensurePushMessageBridge: vi.fn(),
}))

const clients: QueryClient[] = []
const readiness = vi.fn()

async function renderDeferredSearch() {
  const i18n = createInstance()
  await i18n.init({
    lng: "en",
    resources: { en: { common: enCommon } },
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
  clients.push(client)
  const rootRoute = createRootRoute({
    component: () => (
      <>
        <DeferredGlobalOverlays />
        <Outlet />
      </>
    ),
  })
  const route = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([route]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await router.load()
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <RouterProvider router={router as never} />
      </QueryClientProvider>
    </I18nextProvider>
  )
}

async function expectSearchFocused() {
  await screen.findByRole("dialog", { name: "Search" })
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "Search the application" })).toHaveFocus()
  )
}

describe("deferred real SearchDialog shortcut intent", () => {
  beforeEach(() => {
    localStorage.clear()
    readiness.mockClear()
    window.addEventListener(DEFERRED_GLOBAL_OVERLAYS_READY_EVENT, readiness)
  })

  afterEach(async () => {
    cleanup()
    try {
      await vi.dynamicImportSettled()
    } finally {
      clients.splice(0).forEach((client) => client.clear())
      window.removeEventListener(DEFERRED_GLOBAL_OVERLAYS_READY_EVENT, readiness)
      vi.restoreAllMocks()
      localStorage.clear()
    }
  })

  it.each([
    ["Control", { ctrlKey: true }],
    ["Meta", { metaKey: true }],
  ] as const)("opens and focuses search from the first %s+K", async (_label, modifiers) => {
    const timer = vi.spyOn(window, "setTimeout")
    await renderDeferredSearch()

    expect(DEFERRED_OVERLAY_DELAY_MS).toBe(4000)
    expect(timer).toHaveBeenCalledWith(expect.any(Function), 4000)
    expect(readiness).not.toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    fireEvent.keyDown(document, { key: "k", ...modifiers })

    await waitFor(() => expect(readiness).toHaveBeenCalledTimes(1))
    await expectSearchFocused()
  })

  it("promotes overlays for an ordinary key without opening search", async () => {
    await renderDeferredSearch()
    expect(readiness).not.toHaveBeenCalled()

    fireEvent.keyDown(document, { key: "x" })

    await waitFor(() => expect(readiness).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("toggles mounted search exactly once for each shortcut", async () => {
    await renderDeferredSearch()
    fireEvent.keyDown(document, { key: "x" })
    await waitFor(() => expect(readiness).toHaveBeenCalledTimes(1))

    fireEvent.keyDown(document, { key: "k", ctrlKey: true })
    await expectSearchFocused()

    fireEvent.keyDown(document, { key: "k", ctrlKey: true })
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())

    fireEvent.keyDown(document, { key: "k", ctrlKey: true })
    await expectSearchFocused()
    expect(readiness).toHaveBeenCalledTimes(1)
  })
})
