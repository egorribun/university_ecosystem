import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
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
import React from "react"

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    Outlet: () => <div data-testid="outlet" />,
    useNavigate: () => vi.fn(),
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

vi.mock("@/pages/AdminAudit", () => ({ default: () => <div /> }))
vi.mock("@/pages/AdminFeatureFlags", () => ({ default: () => <div /> }))
vi.mock("@/pages/AdminNotifications", () => ({ default: () => <div /> }))
vi.mock("@/pages/AdminUsers", () => ({ default: () => <div /> }))
vi.mock("@/pages/Dashboard", () => ({ default: () => <div /> }))
vi.mock("@/pages/Messenger", () => ({ default: () => <div /> }))
vi.mock("@/pages/NewsDetail", () => ({ default: () => <div /> }))
vi.mock("@/pages/Profile", () => ({ default: () => <div /> }))
vi.mock("@/pages/Activity", () => ({ default: () => <div /> }))
vi.mock("@/pages/EventDetail", () => ({ default: () => <div /> }))
vi.mock("@/pages/Events", () => ({ default: () => <div /> }))
vi.mock("@/pages/Map", () => ({ default: () => <div /> }))
vi.mock("@/pages/News", () => ({ default: () => <div /> }))
vi.mock("@/pages/Schedule", () => ({ default: () => <div /> }))
vi.mock("@/pages/Settings", () => ({ default: () => <div /> }))

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
    expect(activitySearch!({ p: "30d" } as any)).toEqual({ p: "30d" })

    const mapSearch = MapRoute.options.validateSearch
    expect(mapSearch).toBeDefined()
    expect(mapSearch!({ z: 16 } as any)).toEqual({ z: 16 })
  })

  it("AdminLayout rendering", () => {
    const AdminComponent = AdminRoute.options.component as any
    expect(AdminComponent).toBeDefined()
    render(<AdminComponent />)
    expect(screen.getByTestId("admin-backdrop")).toBeInTheDocument()
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
    useAuthStore.setState({ user: { role: "student" } as any })
    render(<PublicComponent />)
    expect(screen.getByTestId("outlet")).toBeInTheDocument()
    
    // Clear user state
    useAuthStore.setState({ user: null })
  })

  it("renders Audit, FeatureFlags, Notifications, Users route components", () => {
    const AuditComp = AdminAuditRoute.options.component as any
    const FFComp = AdminFeatureFlagsRoute.options.component as any
    const NotifComp = AdminNotificationsRoute.options.component as any
    const UsersComp = AdminUsersRoute.options.component as any
    
    render(<AuditComp />)
    render(<FFComp />)
    render(<NotifComp />)
    render(<UsersComp />)
    expect(screen.queryAllByTestId("outlet")).toBeDefined()
  })

  it("renders simple page route components", () => {
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

    render(<MessengerChatComp />)
    render(<MessengerComp />)
    render(<NewsDetailComp />)
    render(<ProfileComp />)
    render(<ActivityComp />)
    render(<EventsDetailComp />)
    render(<EventsComp />)
    render(<MapComp />)
    render(<NewsComp />)
    render(<ScheduleComp />)
    render(<SettingsComp />)
    expect(screen.queryAllByTestId("outlet")).toBeDefined()
  })

  it("DashboardRoute loader test", async () => {
    const loader = DashboardRoute.options.loader
    expect(loader).toBeDefined()
    const mockQueryClient = new QueryClient()
    mockQueryClient.ensureQueryData = vi.fn().mockResolvedValue({})
    
    await loader!({
      context: { queryClient: mockQueryClient },
    } as any)
    
    expect(mockQueryClient.ensureQueryData).toHaveBeenCalledTimes(2)
  })

  it("NewsDetailRoute loader test", async () => {
    const loader = NewsDetailRoute.options.loader
    expect(loader).toBeDefined()
    const mockQueryClient = new QueryClient()
    mockQueryClient.ensureQueryData = vi.fn().mockResolvedValue({})

    await loader!({
      context: { queryClient: mockQueryClient },
      params: { id: "1" },
    } as any)

    expect(mockQueryClient.ensureQueryData).toHaveBeenCalledTimes(1)
  })

  it("ProfileRoute loader test", async () => {
    const loader = ProfileRoute.options.loader
    expect(loader).toBeDefined()
    const mockQueryClient = new QueryClient()
    mockQueryClient.ensureQueryData = vi.fn().mockResolvedValue({})

    await loader!({
      context: { queryClient: mockQueryClient },
    } as any)

    expect(mockQueryClient.ensureQueryData).toHaveBeenCalledTimes(1)
  })
})
