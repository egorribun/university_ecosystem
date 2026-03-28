import { useRouterState } from "@tanstack/react-router"

export function useRouteType() {
  const path = useRouterState({ select: (s) => s.location.pathname })

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
