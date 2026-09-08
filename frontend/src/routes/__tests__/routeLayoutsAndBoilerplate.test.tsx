import { describe, expect, it, vi } from "vitest"
import { act, render, screen, waitFor } from "@testing-library/react"
import { Route as IndexRoute } from "../index"
import { Route as AdminRoute } from "../_admin"
import { Route as AuthRoute } from "../_auth"
import { Route as PublicRoute } from "../_public"
import { Route as AdminAuditRoute } from "../_admin/admin.audit"
import { Route as AdminFeatureFlagsRoute } from "../_admin/admin.feature-flags"
import { Route as AdminNotificationsRoute } from "../_admin/admin.notifications"
import { Route as AdminUsersRoute } from "../_admin/admin.users"
import { Route as DashboardRoute } from "../_auth/dashboard"
import { Route as MessengerChatRoute } from "../_auth/messenger.$chatId"
import { Route as MessengerRoute } from "../_auth/messenger"
import { Route as NewsDetailRoute } from "../_auth/news.$id"
import { Route as ProfileRoute } from "../_auth/profile"
import { Route as ActivityRoute } from "../_auth/activity"
import { Route as EventsDetailRoute } from "../_auth/events.$id"
import { Route as EventsRoute } from "../_auth/events.index"
import { Route as MapRoute } from "../_auth/map"
import { Route as NewsRoute } from "../_auth/news.index"
import { Route as ScheduleRoute } from "../_auth/schedule"
import { Route as SettingsRoute } from "../_auth/settings"
import { useAuthStore } from "@/stores/useAuthStore"
import { QueryClient } from "@tanstack/react-query"

const routerMocks = vi.hoisted(() => ({ navigate: vi.fn() }))

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    Outlet: () => <div data-testid="outlet" />,
    useNavigate: () => routerMocks.navigate,
    useRouterState: vi.fn().mockImplementation(({ select }) => {
      // Simulate location select
      return select({
        location: {
          pathname: "/login",
          search: { redirect: "/events" },
        },
      })
    }),
  }
})

vi.mock("@/features/admin/components/AdminBackdrop", () => ({
  AdminBackdrop: () => <div data-testid="admin-backdrop" />,
}))

vi.mock("@/pages/AdminAudit", () => ({ default: () => <div data-testid="route-admin-audit" /> }))
vi.mock("@/pages/AdminFeatureFlags", () => ({
  default: () => <div data-testid="route-admin-feature-flags" />,
}))
vi.mock("@/pages/AdminNotifications", () => ({
  default: () => <div data-testid="route-admin-notifications" />,
}))
vi.mock("@/pages/AdminUsers", () => ({ default: () => <div data-testid="route-admin-users" /> }))
vi.mock("@/pages/Dashboard", () => ({ default: () => <div /> }))
vi.mock("@/pages/Messenger", () => ({ default: () => <div data-testid="route-messenger" /> }))
vi.mock("@/pages/NewsDetail", () => ({ default: () => <div data-testid="route-news-detail" /> }))
vi.mock("@/pages/Profile", () => ({ default: () => <div data-testid="route-profile" /> }))
vi.mock("@/pages/Activity", () => ({ default: () => <div data-testid="route-activity" /> }))
vi.mock("@/pages/EventDetail", () => ({ default: () => <div data-testid="route-event-detail" /> }))
vi.mock("@/pages/Events", () => ({ default: () => <div data-testid="route-events" /> }))
vi.mock("@/pages/Map", () => ({ default: () => <div data-testid="route-map" /> }))
vi.mock("@/pages/News", () => ({ default: () => <div data-testid="route-news" /> }))
vi.mock("@/pages/Schedule", () => ({ default: () => <div data-testid="route-schedule" /> }))
vi.mock("@/pages/Settings", () => ({ default: () => <div data-testid="route-settings" /> }))

describe("Routes layouts and boilerplate", () => {
  it("IndexRoute redirect is defined and throws redirect", () => {
    const beforeLoad = IndexRoute.options.beforeLoad
    expect(beforeLoad).toBeDefined()
    expect(() => beforeLoad!({} as any)).toThrow()
  })

  it("AdminRoute, AuthRoute, PublicRoute beforeLoad coverage", () => {
    const adminBefore = AdminRoute.options.beforeLoad
    expect(adminBefore).toBeDefined()
    // Returns undefined or throws redirect. Let's just invoke.
    adminBefore!({ context: { auth: { user: { role: "admin" } } } } as any)

    const authBefore = AuthRoute.options.beforeLoad
    expect(authBefore).toBeDefined()
    authBefore!({ context: { auth: { user: { role: "student" } } } } as any)

    const publicBefore = PublicRoute.options.beforeLoad
    expect(publicBefore).toBeDefined()
    publicBefore!({ context: { auth: { user: null } } } as any)
  })

  it("ActivityRoute and MapRoute validateSearch coverage", () => {
    const activitySearch = ActivityRoute.options.validateSearch
    expect(activitySearch).toBeDefined()
    expect((activitySearch as any)({ p: "30d" })).toEqual({ p: "30d" })

    const mapSearch = MapRoute.options.validateSearch
    expect(mapSearch).toBeDefined()
    expect((mapSearch as any)({ z: 16 })).toEqual({ z: 16 })
  })

  it("AdminLayout renders for admins and reactively redirects settled non-admin states", async () => {
    const AdminComponent = AdminRoute.options.component as any
    expect(AdminComponent).toBeDefined()

    act(() => {
      useAuthStore.setState({ user: { role: "admin" } as any, loading: false })
    })
    const view = render(<AdminComponent />)
    expect(screen.getByTestId("admin-backdrop")).toBeInTheDocument()

    act(() => {
      useAuthStore.setState({ user: { role: "student" } as any, loading: false })
    })
    await waitFor(() =>
      expect(routerMocks.navigate).toHaveBeenCalledWith({ to: "/dashboard", replace: true })
    )

    act(() => {
      useAuthStore.setState({ user: null, loading: false })
    })
    await waitFor(() =>
      expect(routerMocks.navigate).toHaveBeenCalledWith({ to: "/login", replace: true })
    )

    act(() => {
      useAuthStore.setState({ user: null, loading: true })
    })
    view.rerender(<AdminComponent />)
    expect(screen.getByTestId("admin-backdrop")).toBeInTheDocument()
    view.unmount()
  })

  it("AuthLayout rendering", () => {
    const AuthComponent = AuthRoute.options.component as any
    expect(AuthComponent).toBeDefined()
    render(<AuthComponent />)
    expect(screen.getByTestId("outlet")).toBeInTheDocument()
  })

  it("PublicLayout rendering", () => {
    const PublicComponent = PublicRoute.options.component as any
    expect(PublicComponent).toBeDefined()

    // Simulate user state transition
    act(() => {
      useAuthStore.setState({ user: { role: "student" } as any })
    })
    const view = render(<PublicComponent />)
    expect(screen.getByTestId("outlet")).toBeInTheDocument()

    // Clear user state
    act(() => {
      useAuthStore.setState({ user: null })
    })
    view.unmount()
  })

  it("renders Audit, FeatureFlags, Notifications, Users route components", async () => {
    const AuditComp = AdminAuditRoute.options.component as any
    const FFComp = AdminFeatureFlagsRoute.options.component as any
    const NotifComp = AdminNotificationsRoute.options.component as any
    const UsersComp = AdminUsersRoute.options.component as any

    const views = [
      render(<AuditComp />),
      render(<FFComp />),
      render(<NotifComp />),
      render(<UsersComp />),
    ]
    await waitFor(() => {
      expect(screen.getByTestId("route-admin-audit")).toBeInTheDocument()
      expect(screen.getByTestId("route-admin-feature-flags")).toBeInTheDocument()
      expect(screen.getByTestId("route-admin-notifications")).toBeInTheDocument()
      expect(screen.getByTestId("route-admin-users")).toBeInTheDocument()
    })
    views.forEach((view) => view.unmount())
  })

  it("renders simple page route components", async () => {
    const MessengerChatComp = MessengerChatRoute.options.component as any
    const MessengerComp = MessengerRoute.options.component as any
    const NewsDetailComp = NewsDetailRoute.options.component as any
    const ProfileComp = ProfileRoute.options.component as any
    const ActivityComp = ActivityRoute.options.component as any
    const EventsDetailComp = EventsDetailRoute.options.component as any
    const EventsComp = EventsRoute.options.component as any
    const MapComp = MapRoute.options.component as any
    const NewsComp = NewsRoute.options.component as any
    const ScheduleComp = ScheduleRoute.options.component as any
    const SettingsComp = SettingsRoute.options.component as any

    const views = [
      render(<MessengerChatComp />),
      render(<MessengerComp />),
      render(<NewsDetailComp />),
      render(<ProfileComp />),
      render(<ActivityComp />),
      render(<EventsDetailComp />),
      render(<EventsComp />),
      render(<MapComp />),
      render(<NewsComp />),
      render(<ScheduleComp />),
      render(<SettingsComp />),
    ]
    await waitFor(() => {
      expect(screen.getAllByTestId("route-messenger")).toHaveLength(2)
      expect(screen.getByTestId("route-news-detail")).toBeInTheDocument()
      expect(screen.getByTestId("route-profile")).toBeInTheDocument()
      expect(screen.getByTestId("route-activity")).toBeInTheDocument()
      expect(screen.getByTestId("route-event-detail")).toBeInTheDocument()
      expect(screen.getByTestId("route-events")).toBeInTheDocument()
      expect(screen.getByTestId("route-map")).toBeInTheDocument()
      expect(screen.getByTestId("route-news")).toBeInTheDocument()
      expect(screen.getByTestId("route-schedule")).toBeInTheDocument()
      expect(screen.getByTestId("route-settings")).toBeInTheDocument()
    })
    views.forEach((view) => view.unmount())
  })

  it("DashboardRoute loader test", async () => {
    const loader = DashboardRoute.options.loader
    expect(loader).toBeDefined()
    const mockQueryClient = new QueryClient()
    mockQueryClient.ensureQueryData = vi.fn().mockResolvedValue({})

    await (loader as any)({
      context: { queryClient: mockQueryClient },
    })

    expect(mockQueryClient.ensureQueryData).toHaveBeenCalledTimes(2)
  })

  it("NewsDetailRoute loader test", async () => {
    const loader = NewsDetailRoute.options.loader
    expect(loader).toBeDefined()
    const mockQueryClient = new QueryClient()
    mockQueryClient.ensureQueryData = vi.fn().mockResolvedValue({})

    await (loader as any)({
      context: { queryClient: mockQueryClient },
      params: { id: "1" },
    })

    expect(mockQueryClient.ensureQueryData).toHaveBeenCalledTimes(1)
  })

  it("ProfileRoute loader test", async () => {
    const validateSearch = ProfileRoute.options.validateSearch
    expect(validateSearch).toBeDefined()
    expect((validateSearch as any)({ edit: "1" })).toEqual({ edit: "1" })
    expect((validateSearch as any)({ edit: 1 })).toEqual({ edit: "1" })
    expect((validateSearch as any)({ edit: "unexpected" })).toEqual({ edit: undefined })

    const loader = ProfileRoute.options.loader
    expect(loader).toBeDefined()
    const mockQueryClient = new QueryClient()
    mockQueryClient.ensureQueryData = vi.fn().mockResolvedValue({})

    await (loader as any)({
      context: { queryClient: mockQueryClient },
    })

    expect(mockQueryClient.ensureQueryData).toHaveBeenCalledTimes(1)
  })
})
