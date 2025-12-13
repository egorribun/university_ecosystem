import { Suspense, lazy, useEffect, type ReactElement } from "react"
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom"
import type { FutureConfig as RouterDataFutureConfig } from "@remix-run/router"
import type { FutureConfig as RouterComponentFutureConfig } from "react-router"
import Navbar from "./components/Navbar"
import Footer from "./components/Footer"
import { AuthProvider, currentUserQueryKey, useAuth } from "./contexts/AuthContext"
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider"
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs"
import { LanguageProvider, useLanguage } from "./contexts/LanguageContext"
import MotionPresence from "./components/MotionPresence"
import useMediaQuery from "@mui/material/useMediaQuery"
import MobileBottomNav from "./components/MobileBottomNav"
import BackToTop from "./components/BackToTop"
import ErrorBoundary from "./app/ErrorBoundary"
import InstallPrompt from "./components/InstallPrompt"
import LivePushToasts from "./components/LivePushToasts"
import { useQueryClient } from "@tanstack/react-query"
import { nowPlayingQueryKey } from "./hooks/useNowPlaying"
import { useTranslation } from "react-i18next"
import { AppShellProvider } from "./contexts/AppShellContext"
import { AdminRoute, PrivateRoute } from "./components/RouteGuards"
import { prefetchRouteModules } from "./utils/prefetchRoutes"

const routeModules = {
  PageTransition: () => import("./components/PageTransition"),
  Dashboard: () => import("./pages/Dashboard"),
  News: () => import("./pages/News"),
  NewsDetail: () => import("./pages/NewsDetail"),
  Schedule: () => import("./pages/Schedule"),
  Activity: () => import("./pages/Activity"),
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
} as const

const PageTransition = lazy(routeModules.PageTransition)
const Dashboard = lazy(routeModules.Dashboard)
const News = lazy(routeModules.News)
const NewsDetail = lazy(routeModules.NewsDetail)
const Schedule = lazy(routeModules.Schedule)
const Activity = lazy(routeModules.Activity)
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

function AppContent() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { isAuth } = useAuth()

  const hideNavbar =
    location.pathname === "/login" ||
    location.pathname === "/register" ||
    location.pathname === "/forgot-password" ||
    location.pathname.startsWith("/reset-password")

  useEffect(() => {
    const sp = new URLSearchParams(location.search)
    const s = sp.get("spotify")
    if (!s) return
    if (s === "connected") {
      void queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
      void queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey })
    }
    sp.delete("spotify")
    const next = location.pathname + (sp.toString() ? "?" + sp : "")
    window.history.replaceState({}, "", next)
  }, [location.pathname, location.search, queryClient])

  useEffect(() => {
    const publicLoaders = [routeModules.Login, routeModules.Register, routeModules.ForgotPassword, routeModules.ResetPassword]
    const privateLoaders = [
      routeModules.Dashboard,
      routeModules.News,
      routeModules.Schedule,
      routeModules.MapPage,
      routeModules.Profile,
      routeModules.Settings,
      routeModules.Activity,
      routeModules.Events,
    ]
    const sharedLoaders = [routeModules.PageTransition, routeModules.Messenger]

    if (isAuth) {
      prefetchRouteModules([...privateLoaders, ...sharedLoaders], { timeoutMs: 800 })
      return
    }

    prefetchRouteModules([...publicLoaders, ...sharedLoaders], { timeoutMs: 800 })
  }, [isAuth])

  const wrap = (node: ReactElement) => {
    if (reduceMotion || hideNavbar) return node
    return <PageTransition>{node}</PageTransition>
  }

  const fallbackShell = (
    <div
      aria-hidden="true"
      style={{
        minHeight: "100dvh",
        background: "var(--page-bg, var(--initial-bg, #060B14))",
        color: "var(--page-text)",
      }}
    />
  )

  const routedContent = (
    <div
      style={{
        minHeight: "100dvh",
        background: "var(--page-bg, var(--initial-bg, #060B14))",
        color: "var(--page-text)",
      }}
    >
      <Suspense fallback={fallbackShell}>
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
          <Route path="/activity" element={<PrivateRoute>{wrap(<Activity />)}</PrivateRoute>} />
          <Route path="/events" element={<PrivateRoute>{wrap(<Events />)}</PrivateRoute>} />
          <Route
            path="/events/:id"
            element={<PrivateRoute>{wrap(<EventDetail />)}</PrivateRoute>}
          />
          <Route path="/map" element={<PrivateRoute>{wrap(<MapPage />)}</PrivateRoute>} />
          <Route path="/profile" element={<PrivateRoute>{wrap(<Profile />)}</PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute>{wrap(<Settings />)}</PrivateRoute>} />
          <Route path="/messenger" element={<PrivateRoute>{wrap(<Messenger />)}</PrivateRoute>} />
          <Route path="/admin/users" element={<AdminRoute>{wrap(<AdminUsers />)}</AdminRoute>} />
          <Route
            path="/admin/notifications"
            element={<AdminRoute>{wrap(<AdminNotifications />)}</AdminRoute>}
          />
          <Route
            path="/admin/stories"
            element={<AdminRoute>{wrap(<StoriesAdmin />)}</AdminRoute>}
          />
          <Route path="*" element={<Navigate to="/dashboard" />} />
        </Routes>
      </Suspense>
    </div>
  )

  return (
    <>
      {!hideNavbar && <Navbar />}
      {reduceMotion || hideNavbar ? (
        routedContent
      ) : (
        <MotionPresence>{routedContent}</MotionPresence>
      )}
      {!hideNavbar && <BackToTop />}
      {!hideNavbar && <Footer />}
      {!hideNavbar && <MobileBottomNav />}
      <LivePushToasts />
      {!hideNavbar && <InstallPrompt />}
    </>
  )
}

type RouterFutureFlags = Partial<RouterDataFutureConfig> & Partial<RouterComponentFutureConfig>

export const routerFutureFlags = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
  v7_partialHydration: true,
  v7_fetcherPersist: true,
  v7_normalizeFormMethod: true,
  v7_skipActionErrorRevalidation: true,
} satisfies RouterFutureFlags

function AppShell() {
  const { language } = useLanguage()
  const { t } = useTranslation("common")

  return (
    <>
      <a href="#main" className="skip-link">
        {t("skipToContent")}
      </a>
      <AppShellProvider>
        <AuthProvider>
          <LocalizationProvider key={language} dateAdapter={AdapterDayjs} adapterLocale={language}>
            <ErrorBoundary>
              <Router future={routerFutureFlags}>
                <AppContent />
              </Router>
            </ErrorBoundary>
          </LocalizationProvider>
        </AuthProvider>
      </AppShellProvider>
    </>
  )
}

export default function App() {
  return (
    <LanguageProvider>
      <AppShell />
    </LanguageProvider>
  )
}
