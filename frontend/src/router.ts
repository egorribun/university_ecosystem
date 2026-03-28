import { createRouter } from "@tanstack/react-router"
import { QueryClient } from "@tanstack/react-query"
import { routeTree } from "./routeTree.gen"

export interface RouterContext {
  auth: {
    isAuth: boolean
    user: { role: string } | null
    loading: boolean
  }
  queryClient: QueryClient
}

export const router = createRouter({
  routeTree,
  context: {
    auth: undefined!,
    queryClient: undefined!,
  },
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
  defaultViewTransition: true,
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
