import { Suspense, lazy, useEffect, type ReactElement } from "react"
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom"
import type { FutureConfig as RouterDataFutureConfig } from "@remix-run/router"
import type { FutureConfig as RouterComponentFutureConfig } from "react-router"
import Navbar from "./components/Navbar"
import Footer from "./components/Footer"
import { AuthProvider, currentUserQueryKey } from "./contexts/AuthContext"
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

const PageTransition = lazy(() => import("./components/PageTransition"))
const Dashboard = lazy(() => import("./pages/Dashboard"))
const News = lazy(() => import("./pages/News"))
const NewsDetail = lazy(() => import("./pages/NewsDetail"))
const Schedule = lazy(() => import("./pages/Schedule"))
const Activity = lazy(() => import("./pages/Activity"))
const Events = lazy(() => import("./pages/Events"))
const EventDetail = lazy(() => import("./components/EventDetail"))
const MapPage = lazy(() => import("./pages/Map"))
const Profile = lazy(() => import("./pages/Profile"))
const Login = lazy(() => import("./pages/Login"))
const Register = lazy(() => import("./pages/Register"))
const AdminUsers = lazy(() => import("./pages/AdminUsers"))
const StoriesAdmin = lazy(() => import("./pages/StoriesAdmin"))
const AdminNotifications = lazy(() => import("./pages/AdminNotifications"))
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"))
const ResetPassword = lazy(() => import("./pages/ResetPassword"))
const Settings = lazy(() => import("./pages/Settings"))

function AppContent() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

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
