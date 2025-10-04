import { QueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"

const retryDelay = (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30_000)

const shouldRetry = (failureCount: number, error: unknown) => {
  if (isAxiosError(error) && error.response?.status === 401) return false
  return failureCount < 3
}

export const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        retryDelay,
        staleTime: 5 * 60 * 1000,
        gcTime: 60 * 60 * 1000,
        refetchOnWindowFocus: true,
      },
      mutations: {
        retry: shouldRetry,
        retryDelay,
      },
    },
  })

export const queryClient = createQueryClient()
