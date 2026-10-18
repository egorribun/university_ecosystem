import { useTranslation } from "react-i18next"
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"

import api, { fetchAnonymousGroupSchedule } from "@/api/client"
import { useAnonymousReadMode } from "@/api/hooks/news"
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
type AnonymousScheduleQueryKey = readonly [
  "dashboard",
  "anonymous-schedule",
  string | number | null | undefined,
]
type DashboardScheduleQueryKey = ScheduleQueryKey | AnonymousScheduleQueryKey

const createScheduleQueryKey = (
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined
): ScheduleQueryKey => ["dashboard", "schedule", role, groupId]

const createAnonymousScheduleQueryKey = (
  groupId: string | number | null | undefined
): AnonymousScheduleQueryKey => ["dashboard", "anonymous-schedule", groupId]

const ensureLessons = (payload: unknown): DashboardLesson[] => {
  if (!Array.isArray(payload)) {
    return []
  }
  return payload.filter(Boolean) as DashboardLesson[]
}

type DashboardSchedulePlaceholder = (previous: DashboardLesson[] | undefined) => DashboardLesson[]

const emptyDashboardSchedulePlaceholder: DashboardSchedulePlaceholder = () => []
const keepDashboardSchedulePlaceholder: DashboardSchedulePlaceholder = (previous) => previous ?? []

// Wave 128 SW3 — exported for forward-compat with /dashboard SSR loader.
// W128 SW3 doesn't yet prefetch schedule server-side (loader has only role
// from JWT, not groupId — needs /users/me prefetch first to derive groupId).
// W129+ may add /users/me to loader for full schedule SSR.
export const createScheduleQueryOptions = (
  queryClient: QueryClient,
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined,
  anonymous = false,
  language = "ru"
) => {
  const queryKey: DashboardScheduleQueryKey = anonymous
    ? createAnonymousScheduleQueryKey(groupId)
    : createScheduleQueryKey(role, groupId)

  return {
    queryKey,
    queryFn: async ({ signal }: { signal?: AbortSignal }) => {
      if (role !== "student" || !groupId) {
        return [] as DashboardLesson[]
      }

      const previous = queryClient.getQueryData<DashboardLesson[]>(queryKey)
      if (anonymous) {
        if (typeof groupId !== "string") return []
        const response = await fetchAnonymousGroupSchedule({ groupId, language, signal })
        if (!response.ok) {
          throw new Error(`Schedule request failed with status ${response.status}`)
        }
        return ensureLessons(await response.json())
      }

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
    placeholderData: anonymous
      ? emptyDashboardSchedulePlaceholder
      : keepDashboardSchedulePlaceholder,
    meta: anonymous ? { persist: false } : undefined,
  }
}

export const useDashboardSchedule = (
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined
) => {
  const queryClient = useQueryClient()
  const { anonymous } = useAnonymousReadMode()
  const { i18n: translation } = useTranslation()
  const queryOptions = createScheduleQueryOptions(
    queryClient,
    role,
    groupId,
    anonymous,
    translation.language
  )

  return useQuery(queryOptions)
}

export const prefetchDashboardSchedule = (
  queryClient: QueryClient,
  role: User["role"] | null | undefined,
  groupId: string | number | null | undefined
) => queryClient.prefetchQuery(createScheduleQueryOptions(queryClient, role, groupId))
