import {
  queryOptions,
  useQuery,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"
import { isCancel } from "axios"

import api from "@/api/client"
import type {
  AttendanceSummaryResponse,
  GradeSummaryResponse,
  ParticipationSummaryResponse,
  PeriodKey,
} from "@/features/activity/types"

/**
 * @fileoverview Activity-summary query hook + reusable query options.
 *
 * Replaces the previous bare-axios + useState + useEffect implementation
 * in ``useActivityData``. The fetch contract is preserved exactly:
 *
 *   1. Try ``GET /stats/summary`` — a single round-trip envelope
 *      endpoint that returns ``{ attendance, grades, participation }``
 *      in one payload.
 *   2. On any failure of (1), fall back to three individual
 *      ``GET /stats/{attendance,grades,participation}`` requests via
 *      ``Promise.allSettled`` — covers older backends that haven't
 *      shipped the envelope endpoint and per-service outages where
 *      one of the three feeds is down but the others are healthy.
 *
 * The transformation/parsing layer (``toNumber``,
 * ``parseAttendanceRecent``, etc.) lives in ``useActivityData`` —
 * that's a derivation concern, not a fetch concern.
 *
 * Cache behaviour:
 *   - ``staleTime: 60_000`` (1 minute) — stats are summary
 *     aggregations; sub-minute freshness isn't useful and refetching
 *     too aggressively wastes the API budget.
 *   - ``gcTime: 5 * 60_000`` (5 minutes) — keeps the entry around long
 *     enough that period-toggle round-trips (``week → month → week``)
 *     don't refetch unnecessarily.
 *
 * Caller contract:
 *   - ``data`` is always defined when ``isSuccess`` (envelope or
 *     partial fallback, never undefined).
 *   - On individual endpoint failure inside the fallback path, that
 *     field of the envelope is ``null``; consumer must guard.
 *   - ``signal`` propagates the AbortController through axios so an
 *     unmount cancels the in-flight request.
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

export class ActivitySummaryUnavailableError extends Error {
  override name = "ActivitySummaryUnavailableError"

  constructor() {
    super("All activity summary sources are unavailable")
  }
}

const isRequestCancellation = (error: unknown): boolean => {
  if (isCancel(error)) return true
  if (!error || typeof error !== "object") return false
  const candidate = error as { name?: string; code?: string }
  if (candidate.name === "AbortError") return true
  if (candidate.name === "CanceledError") return true
  return candidate.code === "ERR_CANCELED"
}

/**
 * Canonical query-key factory for the activity-summary cache. Always
 * use this rather than hand-rolling the tuple — both the period and the
 * language are part of the key (backend localises labels per
 * Accept-Language).
 */
export const activityQueryKey = (params: ActivityQueryParams): ActivityQueryKey =>
  ["activity", "summary", params.period, params.language] as const

/**
 * Internal queryFn for the activity-summary cache. Tries the bundled
 * ``/stats/summary`` endpoint first and silently falls back to three
 * per-feed requests if it fails (network error, 4xx, 5xx — anything
 * axios throws). The fallback uses ``Promise.allSettled`` so a single
 * feed outage doesn't take down the other two.
 *
 * @param period - Aggregation window (week / month / semester).
 * @param signal - Forwarded to axios so an unmount cancels both the
 *   primary call and any of the three fallback calls in flight.
 * @returns Envelope where each of ``attendance`` / ``grades`` /
 *   ``participation`` is either the response payload or ``null`` if
 *   that specific feed failed in the fallback path.
 */
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
  } catch (error) {
    if (signal?.aborted) throw error
    if (isRequestCancellation(error)) throw error
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
    if (a.status === "rejected") {
      if (g.status === "rejected" && p.status === "rejected") {
        throw new ActivitySummaryUnavailableError()
      }
    }
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

/**
 * React-component-side hook for the activity summary. Thin wrapper
 * around ``useQuery(activitySummaryOptions(params))`` — the indirection
 * exists so consumers can pass component-local ``options`` (e.g.
 * ``enabled``, ``select``) without re-deriving the cache key.
 *
 * For non-component contexts (route ``loader``, prefetch, headless
 * read), prefer ``activitySummaryOptions(params)`` directly.
 *
 * @param params - ``period`` + ``language``; both are part of the
 *   cache key (backend localises labels via ``Accept-Language``).
 * @param options - Standard ``useQuery`` options EXCEPT ``queryKey``
 *   and ``queryFn`` (those are owned by the hook).
 * @returns Standard ``UseQueryResult`` over ``ActivitySummaryEnvelope``.
 */
export const useActivitySummaryQuery = (
  params: ActivityQueryParams,
  options?: UseActivitySummaryOptions
): UseQueryResult<ActivitySummaryEnvelope, Error> => {
  return useQuery({ ...activitySummaryOptions(params), ...options })
}
