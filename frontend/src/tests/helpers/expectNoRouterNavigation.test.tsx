import { act, fireEvent, render, screen } from "@testing-library/react"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { describe, expect, it } from "vitest"
import { expectNoRouterNavigation } from "./expectNoRouterNavigation"

async function renderNavigationFixture() {
  let releaseSlowRoute!: () => void
  const slowRouteReady = new Promise<void>((resolve) => {
    releaseSlowRoute = resolve
  })
  const root = createRootRoute({
    component: () => (
      <>
        <Link to="/news">Slow route</Link>
        <Link to="/events">Ready route</Link>
        <Outlet />
      </>
    ),
  })
  const home = createRoute({ getParentRoute: () => root, path: "/", component: () => <p>Home</p> })
  const slow = createRoute({
    getParentRoute: () => root,
    path: "/news",
    loader: () => slowRouteReady,
    component: () => <p>Slow destination</p>,
  })
  const ready = createRoute({
    getParentRoute: () => root,
    path: "/events",
    component: () => <p>Ready destination</p>,
  })
  const router = createRouter({
    routeTree: root.addChildren([home, slow, ready]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
    defaultPendingMs: 0,
    defaultPendingMinMs: 0,
  })
  await router.load()
  const view = render(<RouterProvider router={router as never} />)
  return { router, releaseSlowRoute, ...view }
}

describe("expectNoRouterNavigation cleanup", () => {
  it("fails immediately when an asynchronous fixture does not settle", async () => {
    const { router, releaseSlowRoute, unmount } = await renderNavigationFixture()
    try {
      await expect(
        expectNoRouterNavigation(router, () => {
          fireEvent.click(screen.getByRole("link", { name: "Slow route" }))
        })
      ).rejects.toThrow("static fixture navigation must settle")
      expect(router.state.status).toBe("pending")
    } finally {
      await act(async () => releaseSlowRoute())
      unmount()
    }
  }, 1500)

  it("reports both starts when a second navigation supersedes the first", async () => {
    const { router, releaseSlowRoute, unmount } = await renderNavigationFixture()
    try {
      await expect(
        expectNoRouterNavigation(router, () => {
          fireEvent.click(screen.getByRole("link", { name: "Slow route" }))
          fireEvent.click(screen.getByRole("link", { name: "Ready route" }))
        })
      ).rejects.toMatchObject({
        message: expect.stringMatching(/same-target clicks must not start a route load/),
        actual: ["/news", "/events"],
      })
      expect(router.state.status).toBe("idle")
      expect(router.state.location.pathname).toBe("/events")
      expect(screen.getByText("Ready destination")).toBeInTheDocument()
    } finally {
      await act(async () => releaseSlowRoute())
      unmount()
    }
  }, 1500)
})
