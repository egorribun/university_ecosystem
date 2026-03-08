import { Suspense, lazy, useEffect, type ReactElement } from "react"
import { useTranslation } from "react-i18next"
import { Routes, Route, Navigate, useLocation } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"

import MainLayout from "./components/layout/MainLayout"
import BackToTop from "./components/BackToTop"
import InstallPrompt from "./components/InstallPrompt"
import LivePushToasts from "./components/LivePushToasts"
import OfflineIndicator from "./components/OfflineIndicator"
import MotionPresence from "./components/MotionPresence"
import { AdminRoute, PrivateRoute, PublicRoute } from "./components/RouteGuards"
import { useAuth, currentUserQueryKey } from "./contexts/AuthContext"
import { usePushSync } from "./hooks/usePushSync"
import { nowPlayingQueryKey } from "./hooks/useNowPlaying"
import { prefetchRouteModules } from "./utils/prefetchRoutes"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useRouteType } from "@/hooks/useRouteType"
// DEBT-03 (audit 2026-03-06): Wrap lazy-loaded routes in ErrorBoundary so a
// render-phase panic in any page component shows a recovery UI instead of a
// white screen.  PageErrorBoundary auto-resets on route changes and reports to
// Sentry with componentStack context.
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

import PageTransition from "./components/PageTransition"

const routeModules = {
  Dashboard: () => import("./pages/Dashboard"),
  News: () => import("./pages/News"),
  NewsDetail: () => import("./pages/NewsDetail"),
  Schedule: () => import("./pages/Schedule"),
  UserActivity: () => import("./pages/Activity"),
  Events: () => import("./pages/Events"),
  EventDetail: () => import("./pages/EventDetail"),
  MapPage: () => import("./pages/Map"),
  Profile: () => import("./pages/Profile"),
  Login: () => import("./pages/Login"),
  Register: () => import("./pages/Register"),
  AdminUsers: () => import("./pages/AdminUsers"),
  StoriesAdmin: () => import("./pages/StoriesAdmin"),
  AdminNotifications: () => import("./pages/AdminNotifications"),
  ForgotPassword: () => import("./pages/ForgotPassword"),
  ResetPassword: () => import("./pages/ResetPassword"),
  Settings: () => import("./pages/Settings"),
  Messenger: () => import("./pages/Messenger"),
  AdminFeatureFlags: () => import("./pages/AdminFeatureFlags"),
  AdminAudit: () => import("./pages/AdminAudit"),
} as const

const Dashboard = lazy(routeModules.Dashboard)
const News = lazy(routeModules.News)
const NewsDetail = lazy(routeModules.NewsDetail)
const Schedule = lazy(routeModules.Schedule)
const UserActivity = lazy(routeModules.UserActivity)
const Events = lazy(routeModules.Events)
const EventDetail = lazy(routeModules.EventDetail)
const MapPage = lazy(routeModules.MapPage)
const Profile = lazy(routeModules.Profile)
const Login = lazy(routeModules.Login)
const Register = lazy(routeModules.Register)
const AdminUsers = lazy(routeModules.AdminUsers)
const StoriesAdmin = lazy(routeModules.StoriesAdmin)
const AdminNotifications = lazy(routeModules.AdminNotifications)
const ForgotPassword = lazy(routeModules.ForgotPassword)
const ResetPassword = lazy(routeModules.ResetPassword)
const Settings = lazy(routeModules.Settings)
const Messenger = lazy(routeModules.Messenger)
const AdminFeatureFlags = lazy(routeModules.AdminFeatureFlags)
const AdminAudit = lazy(routeModules.AdminAudit)

export function AppRoutes() {
  const { t } = useTranslation(["common"])
  const location = useLocation()
  const queryClient = useQueryClient()
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { isAuth } = useAuth()

  // Global push subscription sync
  usePushSync(isAuth)

  useEffect(() => {
    const searchParams = new URLSearchParams(location.search)
    const spotifyStatus = searchParams.get("spotify")
    if (!spotifyStatus) return
    if (spotifyStatus === "connected") {
      void queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
      void queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey })
    }
    searchParams.delete("spotify")
    const nextPath = location.pathname + (searchParams.toString() ? "?" + searchParams : "")
    window.history.replaceState({}, "", nextPath)
  }, [location.pathname, location.search, queryClient])

  useEffect(() => {
    const publicLoaders = [
      routeModules.Login,
      routeModules.Register,
      routeModules.ForgotPassword,
      routeModules.ResetPassword,
    ]
    const privateLoaders = [
      routeModules.Dashboard,
      routeModules.News,
      routeModules.Schedule,
      routeModules.MapPage,
      routeModules.Profile,
      routeModules.Settings,
      routeModules.UserActivity,
      routeModules.Events,
    ]
    const sharedLoaders = [routeModules.Messenger]

    const PREFETCH_TIMEOUT_MS = 800

    if (isAuth) {
      prefetchRouteModules([...privateLoaders, ...sharedLoaders], {
        timeoutMs: PREFETCH_TIMEOUT_MS,
      })
      return
    }

    prefetchRouteModules([...publicLoaders, ...sharedLoaders], { timeoutMs: PREFETCH_TIMEOUT_MS })
  }, [isAuth])

  const { isCompactPage, isMessenger } = useRouteType()

  const wrap = (node: ReactElement) => {
    if (reduceMotion || isCompactPage || isMessenger) return node
    return <PageTransition>{node}</PageTransition>
  }

  const isLHCI = import.meta.env.VITE_LHCI === "true"

  const fallbackShell = (
    <div
      aria-hidden="false"
      style={{
        minHeight: "100dvh",
        background: isLHCI
          ? "var(--color-white)"
          : "var(--bg-page, var(--initial-bg, var(--color-slate-950)))",
        color: isLHCI ? "var(--color-black)" : "var(--text-primary)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: isLHCI ? "2rem" : "inherit",
        fontWeight: isLHCI ? "bold" : "normal",
      }}
    >
      {isLHCI ? "UNIVERSITY ECOSYSTEM LHCI RENDER" : t("common:loading")}
    </div>
  )

  const routes = (
    <Routes location={location}>
      <Route path="/login" element={<PublicRoute>{wrap(<Login />)}</PublicRoute>} />
      <Route path="/register" element={<PublicRoute>{wrap(<Register />)}</PublicRoute>} />
      <Route
        path="/forgot-password"
        element={<PublicRoute>{wrap(<ForgotPassword />)}</PublicRoute>}
      />
      <Route
        path="/reset-password"
        element={<PublicRoute>{wrap(<ResetPassword />)}</PublicRoute>}
      />
      <Route
        path="/reset-password/:token"
        element={<PublicRoute>{wrap(<ResetPassword />)}</PublicRoute>}
      />
      <Route path="/dashboard" element={<PrivateRoute>{wrap(<Dashboard />)}</PrivateRoute>} />
      <Route path="/news" element={<PrivateRoute>{wrap(<News />)}</PrivateRoute>} />
      <Route path="/news/:id" element={<PrivateRoute>{wrap(<NewsDetail />)}</PrivateRoute>} />
      <Route path="/schedule" element={<PrivateRoute>{wrap(<Schedule />)}</PrivateRoute>} />
      <Route path="/activity" element={<PrivateRoute>{wrap(<UserActivity />)}</PrivateRoute>} />
      <Route path="/events" element={<PrivateRoute>{wrap(<Events />)}</PrivateRoute>} />
      <Route path="/events/:id" element={<PrivateRoute>{wrap(<EventDetail />)}</PrivateRoute>} />
      <Route path="/map" element={<PrivateRoute>{wrap(<MapPage />)}</PrivateRoute>} />
      <Route path="/profile" element={<PrivateRoute>{wrap(<Profile />)}</PrivateRoute>} />
      <Route path="/settings" element={<PrivateRoute>{wrap(<Settings />)}</PrivateRoute>} />
      <Route path="/messenger" element={<PrivateRoute>{wrap(<Messenger />)}</PrivateRoute>} />
      <Route
        path="/messenger/:chatId"
        element={<PrivateRoute>{wrap(<Messenger />)}</PrivateRoute>}
      />
      <Route path="/admin/users" element={<AdminRoute>{wrap(<AdminUsers />)}</AdminRoute>} />
      <Route
        path="/admin/notifications"
        element={<AdminRoute>{wrap(<AdminNotifications />)}</AdminRoute>}
      />
      <Route path="/admin/stories" element={<AdminRoute>{wrap(<StoriesAdmin />)}</AdminRoute>} />
      <Route
        path="/admin/feature-flags"
        element={<AdminRoute>{wrap(<AdminFeatureFlags />)}</AdminRoute>}
      />
      <Route path="/admin/audit" element={<AdminRoute>{wrap(<AdminAudit />)}</AdminRoute>} />
      <Route path="*" element={<Navigate to="/dashboard" />} />
    </Routes>
  )

  return (
    <MainLayout>
      <PageErrorBoundary>
        <Suspense fallback={fallbackShell}>
          {reduceMotion || isCompactPage ? routes : <MotionPresence>{routes}</MotionPresence>}
        </Suspense>
      </PageErrorBoundary>

      <BackToTop />
      <LivePushToasts />
      <OfflineIndicator />
      <InstallPrompt />
    </MainLayout>
  )
}
