import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const Dashboard = lazy(() => import("@/pages/Dashboard"))

export const Route = createFileRoute("/_auth/dashboard")({
  // Wave 128 SW2 — temporary explicit opt-down to preserve W127
  // client-only behavior in the SW2-vs-SW3 mid-state. Parent _auth.tsx
  // is now ssr:true but __root.tsx SSR branch doesn't yet include
  // MainLayout (SW3 adds it). Without this override, /dashboard would
  // SSR component WITHOUT MainLayout = mid-tree hydration mismatch.
  // Wave 128 SW3 removes this override + enables full SSR with loader.
  ssr: false,
  component: Dashboard,
})
