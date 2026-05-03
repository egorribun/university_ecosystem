import {
  queryOptions,
  useQuery,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"

import api from "@/api/client"
import type {
  AttendanceSummaryResponse,
  GradeSummaryResponse,
  ParticipationSummaryResponse,
  PeriodKey,
} from "@/features/activity/types"

/**
 * Activity Stats Query — Wave 112 SW2 migration.
 *
 * Replaces the previous bare-axios+useState+useEffect implementation in
 * useActivityData. The fetch contract is preserved exactly:
 *   1. Try /stats/summary (single round-trip envelope endpoint)
 *   2. On any failure, fall back to three individual /stats/{kind} requests
 *      via Promise.allSettled — covers older backends + per-service outages
 *
 * The transformation/parsing layer (toNumber, parseAttendanceRecent, etc.)
 * stays in useActivityData where the hook composes the raw envelope into
 * UI-friendly stats — that's a derivation concern, not a fetch concern.
 *
 * Contract for callers:
 *   - `data` is always defined when `isSuccess` (envelope or partial fallback)
 *   - On individual endpoint failure, that field of the envelope is `null`
 *   - `signal` propagates AbortController through axios for in-flight cancellation
 *
 * staleTime: 60s — stats are summary aggregations; sub-minute freshness
 * isn't useful and refetching too aggressively wastes the API budget.
 */

export type ActivitySummaryEnvelope = {
  attendance: AttendanceSummaryResponse | null
  grades: GradeSummaryResponse | null
  participation: ParticipationSummaryResponse | null
}

export type ActivityQueryParams = {
  period: PeriodKey
  /** Language is part of the cache key — backend localises labels per Accept-Language */
  language: string
}

export type ActivityQueryKey = readonly ["activity", "summary", PeriodKey, string]

/**
 * Canonical query-key factory for the activity-summary cache. Always
 * use this rather than hand-rolling the tuple — both the period and the
 * language are part of the key (backend localises labels per
 * Accept-Language).
 */
export const activityQueryKey = (params: ActivityQueryParams): ActivityQueryKey =>
  ["activity", "summary", params.period, params.language] as const

const fetchActivitySummary = async (
  period: PeriodKey,
  signal: AbortSignal | undefined
): Promise<ActivitySummaryEnvelope> => {
  try {
    const summary = await api.get<ActivitySummaryEnvelope>("/stats/summary", {
      params: { period },
      signal,
    })
    return {
      attendance: summary.data?.attendance ?? null,
      grades: summary.data?.grades ?? null,
      participation: summary.data?.participation ?? null,
    }
  } catch {
    // Fallback: per-endpoint requests for older backend or partial outage.
    const [a, g, p] = await Promise.allSettled([
      api.get<AttendanceSummaryResponse>("/stats/attendance", {
        params: { period },
        signal,
      }),
      api.get<GradeSummaryResponse>("/stats/grades", {
        params: { period },
        signal,
      }),
      api.get<ParticipationSummaryResponse>("/stats/participation", {
        params: { period },
        signal,
      }),
    ])
    return {
      attendance: a.status === "fulfilled" ? a.value.data : null,
      grades: g.status === "fulfilled" ? g.value.data : null,
      participation: p.status === "fulfilled" ? p.value.data : null,
    }
  }
}

/**
 * Reusable typed query options. Use `useQuery(activitySummaryOptions(params))`
 * or `queryClient.prefetchQuery(activitySummaryOptions(params))` — both share
 * the same cache key and behaviour.
 */
export const activitySummaryOptions = (params: ActivityQueryParams) =>
  queryOptions({
    queryKey: activityQueryKey(params),
    queryFn: ({ signal }) => fetchActivitySummary(params.period, signal),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
  })

type UseActivitySummaryOptions = Omit<
  UseQueryOptions<ActivitySummaryEnvelope, Error, ActivitySummaryEnvelope, ActivityQueryKey>,
  "queryKey" | "queryFn"
>

export const useActivitySummaryQuery = (
  params: ActivityQueryParams,
  options?: UseActivitySummaryOptions
): UseQueryResult<ActivitySummaryEnvelope, Error> => {
  return useQuery({ ...activitySummaryOptions(params), ...options })
}
