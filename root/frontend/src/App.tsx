import { Suspense, lazy, useEffect, type ReactNode, type ReactElement } from "react"
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom"
import Navbar from "./components/Navbar"
import Footer from "./components/Footer"
import { AuthProvider, useAuth } from "./contexts/AuthContext"
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider"
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs"
import MotionPresence from "./components/MotionPresence"
import api from "./api/axios"
import useMediaQuery from "@mui/material/useMediaQuery"
import { registerServiceWorker } from "./push/register-sw"
import MobileBottomNav from "./components/MobileBottomNav"
import BackToTop from "./components/BackToTop"

const PageTransition = lazy(() => import("./components/PageTransition"))
const Dashboard = lazy(() => import("./pages/Dashboard"))
const News = lazy(() => import("./pages/News"))
const NewsDetail = lazy(() => import("./components/NewsDetail"))
const Schedule = lazy(() => import("./pages/Schedule"))
const Activity = lazy(() => import("./pages/Activity"))
const Events = lazy(() => import("./pages/Events"))
const EventDetail = lazy(() => import("./components/EventDetail"))
const MapPage = lazy(() => import("./pages/Map"))
const Profile = lazy(() => import("./pages/Profile"))
const Login = lazy(() => import("./pages/Login"))
const Register = lazy(() => import("./pages/Register"))
const AdminUsers = lazy(() => import("./pages/AdminUsers"))
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"))
const ResetPassword = lazy(() => import("./pages/ResetPassword"))
const Settings = lazy(() => import("./pages/Settings"))

function PrivateRoute({ children }: { children: ReactNode }) {
  const { isAuth, loading } = useAuth()
  if (loading) return null
  return isAuth ? children : <Navigate to="/login" />
}

function AdminRoute({ children }: { children: ReactNode }) {
  const { isAuth, user, loading } = useAuth()
  if (loading) return null
  if (!isAuth) return <Navigate to="/login" />
  if (!user || user.role !== "admin") return <Navigate to="/dashboard" />
  return children
}

function AppContent() {
  const location = useLocation()
  const { setUser } = useAuth()
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const hideNavbar =
    location.pathname === "/login" ||
    location.pathname === "/register" ||
    location.pathname === "/forgot-password" ||
    location.pathname.startsWith("/reset-password")

  useEffect(() => {
    if (import.meta.env.DEV) return
    registerServiceWorker()
  }, [])

  useEffect(() => {
    const sp = new URLSearchParams(location.search)
    const s = sp.get("spotify")
    if (!s) return
    if (s === "connected") {
      api
        .get("/users/me")
        .then((r) => setUser(r.data))
        .catch(() => {})
    }
    sp.delete("spotify")
    const next = location.pathname + (sp.toString() ? "?" + sp : "")
    window.history.replaceState({}, "", next)
  }, [location.pathname, location.search, setUser])

  const wrap = (node: ReactElement) => {
    if (reduceMotion || hideNavbar) return node
    return <PageTransition>{node}</PageTransition>
  }

  const fallbackShell = (
    <div
      aria-hidden="true"
      style={{ minHeight: "100dvh", background: "var(--page-bg)", color: "var(--page-text)" }}
    />
  )

  const routedContent = (
    <div style={{ minHeight: "100dvh", background: "var(--page-bg)", color: "var(--page-text)" }}>
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
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="ru">
        <Router>
          <AppContent />
        </Router>
      </LocalizationProvider>
    </AuthProvider>
  )
}
