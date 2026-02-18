import type { ReactElement } from "react"
import { Navigate, useLocation } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import LoadingState from "./LoadingState"

export type RouteGuardProps = { children: ReactElement }

export function PrivateRoute({ children }: RouteGuardProps) {
  const { isAuth, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <LoadingState />
  }

  return isAuth ? children : <Navigate to="/login" state={{ from: location }} replace />
}

export function AdminRoute({ children }: RouteGuardProps) {
  const { isAuth, user, loading } = useAuth()

  if (loading) {
    return <LoadingState />
  }

  if (!isAuth) {
    return <Navigate to="/login" />
  }

  if (!user || user.role !== "admin") {
    return <Navigate to="/dashboard" />
  }

  return children
}

export function PublicRoute({ children }: RouteGuardProps) {
  const { isAuth, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <LoadingState />
  }

  if (isAuth) {
    // Redirect to dashboard, but preserve the source location if they were trying to go somewhere else
    // though usually PublicRoute is for Login/Register which don't have a "from" state in this direction
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/dashboard"
    return <Navigate to={from} replace />
  }

  return children
}
