import { Suspense, lazy, useEffect, type ReactElement } from "react"
import { Routes, Route, Navigate, useLocation } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import MainLayout from "./components/layout/MainLayout"
import Navbar from "./components/Navbar"
import Footer from "./components/Footer"
import MobileBottomNav from "./components/MobileBottomNav"
import BackToTop from "./components/BackToTop"
import InstallPrompt from "./components/InstallPrompt"
import LivePushToasts from "./components/LivePushToasts"
import OfflineIndicator from "./components/OfflineIndicator"
import MotionPresence from "./components/MotionPresence"
import { AdminRoute, PrivateRoute } from "./components/RouteGuards"
import { useAuth, currentUserQueryKey } from "./contexts/AuthContext"
import { usePushSync } from "./hooks/usePushSync"
import { nowPlayingQueryKey } from "./hooks/useNowPlaying"
import { prefetchRouteModules } from "./utils/prefetchRoutes"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"

import PageTransition from "./components/PageTransition"

const routeModules = {
  Dashboard: () => import("./pages/Dashboard"),
  News: () => import("./pages/News"),
  NewsDetail: () => import("./pages/NewsDetail"),
  Schedule: () => import("./pages/Schedule"),
  UserActivity: () => import("./pages/Activity"),
  Events: () => import("./pages/Events"),
  EventDetail: () => import("./components/EventDetail"),
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

    if (isAuth) {
      prefetchRouteModules([...privateLoaders, ...sharedLoaders], { timeoutMs: 800 })
      return
    }

    prefetchRouteModules([...publicLoaders, ...sharedLoaders], { timeoutMs: 800 })
  }, [isAuth])

  const isCompactPage = ["/login", "/register", "/forgot-password"].some(
    (path) => location.pathname.startsWith(path) || location.pathname.startsWith("/reset-password")
  )

  const wrap = (node: ReactElement) => {
    if (reduceMotion || isCompactPage || location.pathname.startsWith("/messenger")) return node
    return <PageTransition>{node}</PageTransition>
  }

  const isLHCI = import.meta.env.VITE_LHCI === "true"

  const fallbackShell = (
    <div
      aria-hidden="false"
      style={{
        minHeight: "100dvh",
        background: isLHCI ? "#FFFFFF" : "var(--bg-page, var(--initial-bg, #060B14))",
        color: isLHCI ? "#000000" : "var(--text-primary)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: isLHCI ? "32px" : "inherit",
        fontWeight: isLHCI ? "bold" : "normal",
      }}
    >
      {isLHCI ? "UNIVERSITY ECOSYSTEM LHCI RENDER" : "Loading..."}
    </div>
  )

  const routes = (
    <Routes location={location} key={location.pathname}>
      <Route path="/login" element={wrap(<Login />)} />
      <Route path="/register" element={wrap(<Register />)} />
      <Route path="/forgot-password" element={wrap(<ForgotPassword />)} />
      <Route path="/reset-password" element={wrap(<ResetPassword />)} />
      <Route path="/reset-password/:token" element={wrap(<ResetPassword />)} />
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
      <Suspense fallback={fallbackShell}>
        {reduceMotion || isCompactPage ? routes : <MotionPresence>{routes}</MotionPresence>}
      </Suspense>

      <BackToTop />
      <LivePushToasts />
      <OfflineIndicator />
      <InstallPrompt />
    </MainLayout>
  )
}




