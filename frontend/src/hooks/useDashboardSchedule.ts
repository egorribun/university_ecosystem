import { useMemo } from "react"
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"

import api from "@/api/client"
import type { User } from "@/types/User"

export type DashboardLesson = {
  id: string /* FIX-72-05: was `number` — API ScheduleOut returns string */
  subject: string
  teacher: string
  room: string
  lesson_type: string
  weekday: string
  start_time: string
  end_time: string
  parity: "odd" | "even" | "both"
}

type ScheduleQueryKey = readonly [
  "dashboard",
  "schedule",
  User["role"] | null | undefined,
  string | number | null | undefined,
]

const createScheduleQueryKey = (
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined
): ScheduleQueryKey => ["dashboard", "schedule", role, groupId]

const ensureLessons = (payload: unknown): DashboardLesson[] => {
  if (!Array.isArray(payload)) {
    return []
  }
  return payload.filter(Boolean) as DashboardLesson[]
}

const createScheduleQueryOptions = (
  queryClient: QueryClient,
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined
) => ({
  queryKey: createScheduleQueryKey(role, groupId),
  queryFn: async ({ signal }: { signal?: AbortSignal }) => {
    if (role !== "student" || !groupId) {
      return [] as DashboardLesson[]
    }

    const previous = queryClient.getQueryData<DashboardLesson[]>(
      createScheduleQueryKey(role, groupId)
    )

    const etagKey = `schedule:group:${groupId}`
    try {
      const response = await api.get<DashboardLesson[]>(`/schedule/${groupId}`, {
        signal,
        validateStatus: (status: number) => status >= 200 && status < 400,
        etagCacheKey: etagKey,
      } as Parameters<typeof api.get>[1])

      if (response.status === 304) {
        return previous ?? []
      }

      return ensureLessons(response.data)
    } catch (error) {
      if (signal?.aborted) {
        throw error
      }
      if (previous) {
        return previous
      }
      throw error
    }
  },
  enabled: role === "student" && Boolean(groupId),
  staleTime: 60_000,
  gcTime: 10 * 60_000,
  placeholderData: (previous: DashboardLesson[] | undefined) => previous ?? [],
})

export const useDashboardSchedule = (
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined
) => {
  const queryClient = useQueryClient()

  const queryOptions = useMemo(
    () => createScheduleQueryOptions(queryClient, role, groupId),
    [queryClient, role, groupId]
  )

  return useQuery(queryOptions)
}

export const prefetchDashboardSchedule = (
  queryClient: QueryClient,
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined
) => queryClient.prefetchQuery(createScheduleQueryOptions(queryClient, role, groupId))
