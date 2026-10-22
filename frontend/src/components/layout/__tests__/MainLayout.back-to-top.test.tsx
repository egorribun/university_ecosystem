import { act, cleanup, render, screen } from "@testing-library/react"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { LazyMotion, domAnimation } from "framer-motion"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MainLayout } from "../MainLayout"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("@/components/navbar", () => ({
  default: () => <nav data-testid="navbar" />,
}))
vi.mock("@/components/layout/Footer", () => ({
  default: () => <footer role="contentinfo" />,
}))
vi.mock("@/components/layout/MobileBottomNav", () => ({
  default: () => <nav data-testid="mobile-bottom-nav" />,
}))

function RouteLayout() {
  return (
    <MainLayout>
      <Outlet />
    </MainLayout>
  )
}

function rectangleAt(top: number): DOMRectReadOnly {
  const values = {
    x: 0,
    y: top,
    width: 100,
    height: 200,
    top,
    right: 100,
    bottom: top + 200,
    left: 0,
  }
  return { ...values, toJSON: () => ({ ...values }) }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("MainLayout BackToTop route lifecycle", () => {
  it("observes replacement footers across routes without remounting the control", async () => {
    const observers: MockIntersectionObserver[] = []

    class MockIntersectionObserver implements IntersectionObserver {
      readonly root: Element | Document | null
      readonly rootMargin: string
      readonly thresholds: readonly number[]
      readonly scrollMargin = "0px"
      readonly delay = 0
      readonly trackVisibility = false

      observe = vi.fn<(target: Element) => void>()
      unobserve = vi.fn<(target: Element) => void>()
      disconnect = vi.fn<() => void>()
      takeRecords = vi.fn<() => IntersectionObserverEntry[]>(() => [])

      constructor(
        private readonly callback: IntersectionObserverCallback,
        options: IntersectionObserverInit = {}
      ) {
        this.root = options.root ?? null
        this.rootMargin = options.rootMargin ?? "0px"
        const threshold = options.threshold ?? 0
        this.thresholds = Array.isArray(threshold) ? threshold : [threshold]
        observers.push(this)
      }

      intersect(target: Element, top: number) {
        const rectangle = rectangleAt(top)
        this.callback(
          [
            {
              target,
              time: 0,
              isIntersecting: true,
              intersectionRatio: 0.5,
              boundingClientRect: rectangle,
              intersectionRect: rectangle,
              rootBounds: null,
            },
          ],
          this
        )
      }
    }

    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)
    vi.stubGlobal("innerHeight", 800)
    vi.stubGlobal("scrollY", 500)

    const root = createRootRoute({ component: RouteLayout })
    const messenger = createRoute({
      getParentRoute: () => root,
      path: "/messenger",
      component: () => <p>messenger</p>,
    })
    const dashboard = createRoute({
      getParentRoute: () => root,
      path: "/dashboard",
      component: () => <p>dashboard</p>,
    })
    const schedule = createRoute({
      getParentRoute: () => root,
      path: "/schedule",
      component: () => <p>schedule</p>,
    })
    const news = createRoute({
      getParentRoute: () => root,
      path: "/news",
      component: () => <p>news</p>,
    })
    const router = createRouter({
      routeTree: root.addChildren([messenger, dashboard, schedule, news]),
      history: createMemoryHistory({ initialEntries: ["/messenger"] }),
    })
    await router.load()

    const { unmount } = render(
      <LazyMotion features={domAnimation}>
        <RouterProvider<typeof router> router={router} />
      </LazyMotion>
    )

    const button = screen.getByRole("button", { name: "common:buttons.backToTop" })
    const shell = button.closest(".back-to-top-wrap")
    expect(shell).not.toBeNull()
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument()
    expect(observers).toHaveLength(0)
    expect(shell).toHaveStyle("bottom: 24px")

    await act(async () => {
      await router.navigate({ to: "/dashboard" })
    })

    expect(screen.getByRole("button", { name: "common:buttons.backToTop" })).toBe(button)
    const firstFooter = screen.getByRole("contentinfo")
    expect(observers).toHaveLength(1)
    const first = observers[0]
    if (!first) throw new Error("The first visible route did not create a footer observer")
    expect(first.observe).toHaveBeenCalledExactlyOnceWith(firstFooter)
    expect(first.thresholds).toEqual(Array.from({ length: 21 }, (_, i) => i / 20))

    act(() => first.intersect(firstFooter, 700))
    expect(shell).toHaveStyle("bottom: 140px")

    await act(async () => {
      await router.navigate({ to: "/schedule" })
    })

    expect(screen.getByRole("button", { name: "common:buttons.backToTop" })).toBe(button)
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument()
    expect(firstFooter).not.toBeInTheDocument()
    expect(first.disconnect).toHaveBeenCalledOnce()
    expect(observers).toHaveLength(1)
    expect(shell).toHaveStyle("bottom: 24px")

    act(() => first.intersect(firstFooter, 600))
    expect(shell).toHaveStyle("bottom: 24px")

    await act(async () => {
      await router.navigate({ to: "/news" })
    })

    expect(screen.getByRole("button", { name: "common:buttons.backToTop" })).toBe(button)
    const secondFooter = screen.getByRole("contentinfo")
    expect(secondFooter).not.toBe(firstFooter)
    expect(observers).toHaveLength(2)
    const second = observers[1]
    if (!second) throw new Error("The second visible route did not create a footer observer")
    expect(second.observe).toHaveBeenCalledExactlyOnceWith(secondFooter)
    expect(shell).toHaveStyle("bottom: 24px")

    act(() => second.intersect(secondFooter, 650))
    expect(shell).toHaveStyle("bottom: 190px")

    act(() => first.intersect(firstFooter, 600))
    expect(shell).toHaveStyle("bottom: 190px")

    unmount()
    expect(first.disconnect).toHaveBeenCalledOnce()
    expect(second.disconnect).toHaveBeenCalledOnce()
  })
})
