import { QueryClient } from "@tanstack/react-query"

const defaultOptions = {
  queries: { staleTime: 30000, retry: 1, refetchOnWindowFocus: false },
  mutations: { retry: 0 },
} as const

export const createQueryClient = () =>
  new QueryClient({
    defaultOptions,
  })

export const queryClient = createQueryClient()
