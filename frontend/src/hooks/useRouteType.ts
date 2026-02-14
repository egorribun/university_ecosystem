import { useLocation } from "react-router-dom"

export function useRouteType() {
  const location = useLocation()
  const path = location.pathname

  const isCompactPage = ["/login", "/register", "/forgot-password", "/reset-password"].some((p) =>
    path.startsWith(p)
  )

  const isMessenger = path.startsWith("/messenger")
  const hideFooter = path.startsWith("/map") || path.startsWith("/schedule")

  return {
    isCompactPage,
    isMessenger,
    hideFooter,
    loading: false, // Future proofing if we need async check
  }
}
