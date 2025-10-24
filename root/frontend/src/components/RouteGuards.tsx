import type { ReactElement } from "react"
import { Navigate } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import RouteGuardLoading from "./RouteGuardLoading"

export type RouteGuardProps = { children: ReactElement }

export function PrivateRoute({ children }: RouteGuardProps) {
  const { isAuth, loading } = useAuth()

  if (loading) {
    return <RouteGuardLoading />
  }

  return isAuth ? children : <Navigate to="/login" />
}

export function AdminRoute({ children }: RouteGuardProps) {
  const { isAuth, user, loading } = useAuth()

  if (loading) {
    return <RouteGuardLoading />
  }

  if (!isAuth) {
    return <Navigate to="/login" />
  }

  if (!user || user.role !== "admin") {
    return <Navigate to="/dashboard" />
  }

  return children
}
