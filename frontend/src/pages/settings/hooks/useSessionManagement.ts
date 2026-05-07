import { useCallback, useMemo, useRef, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { formatDate, toDate } from "@/utils/date"

import api from "@/api/client"
import {
  invalidateSessions,
  sessionsQueryOptions,
  updateSessionInCache,
} from "@/api/hooks/sessions"
import { useAuth } from "@/contexts/AuthContext"
import type { ActiveSession } from "@/types/Session"
import type { SetSnackbar } from "@/pages/settings/types"

export interface UseSessionManagementOptions {
  setSnackbar: SetSnackbar
  tabActive: boolean
  openStepUpFor?: (action: () => Promise<void>) => void
}

export interface UseSessionManagementReturn {
  sessions: ActiveSession[]
  sortedSessions: ActiveSession[]
  sessionsFetching: boolean
  sessionsIsError: boolean
  sessionsError: unknown
  handleRevokeSession: (sessionId: string, options?: { skipStepUp?: boolean }) => Promise<void>
  handleRevokeAllSessions: (options?: { skipStepUp?: boolean }) => Promise<void>
  revokeSessionBusy: boolean
  revokeAllSessionsBusy: boolean
  formatSessionTimestamp: (value: string | null) => string
}

const resolveDetailMessage = (error: unknown, fallback: string): string => {
  if (isAxiosError(error) && error.response?.data?.detail) {
    return String(error.response.data.detail)
  }
  return error instanceof Error ? error.message : fallback
}

const isStepUpError = (error: unknown): boolean =>
  isAxiosError(error) && error.response?.status === 428

export function useSessionManagement({
  setSnackbar,
  tabActive,
  openStepUpFor,
}: UseSessionManagementOptions): UseSessionManagementReturn {
  const { t } = useTranslation(["settings"])
  const { user, logout } = useAuth()
  const queryClient = useQueryClient()

  // Wave 134 SW2 — sessions queryKey + queryFn now provided by the
  // sessionsQueryOptions factory at api/hooks/sessions.ts so the SSR
  // loader for /settings (routes/_auth/settings.tsx) can prefetch on
  // ?tab=2 (Security) using the SAME cache slot that this client-side
  // useQuery reads from. Cache identity is preserved at the queryKey
  // tuple shape ["auth", "sessions", userId] (matches pre-W134 behaviour
  // exactly). The factory also supplies staleTime: 30_000, gcTime, retry
  // semantics — preserved verbatim from the pre-W134 inline config.
  //
  // Wave 135 SW1 — mutation cache writes now route through the factory's
  // updateSessionInCache + invalidateSessions exports so the cache key is
  // never touched directly from this hook. Closes W134 §Honesty #5.
  const userId = user?.id ?? "me"

  const {
    data: sessionsData,
    isFetching: sessionsFetching,
    isError: sessionsIsError,
    error: sessionsError,
  } = useQuery({
    ...sessionsQueryOptions(userId),
    enabled: tabActive && Boolean(user),
  })

  const sessions = useMemo(() => (Array.isArray(sessionsData) ? sessionsData : []), [sessionsData])

  const sortedSessions = useMemo(() => {
    const weight = (session: ActiveSession) => {
      if (session.is_current) return 0
      if (session.revoked_at) return 2
      return 1
    }

    const timeValue = (session: ActiveSession) => {
      const source = session.last_seen_at ?? session.created_at ?? null
      if (!source) return 0
      const parsed = toDate(source)
      return !isNaN(parsed.getTime()) ? parsed.valueOf() : 0
    }

    if (!Array.isArray(sessions)) return []

    return [...sessions].sort((a, b) => {
      const weightDiff = weight(a) - weight(b)
      if (weightDiff !== 0) return weightDiff
      return timeValue(b) - timeValue(a)
    })
  }, [sessions])

  const revokeSessionMutation = useMutation({
    mutationFn: async (sessionId: string) => {
      const { data } = await api.delete<ActiveSession>(`/auth/sessions/${sessionId}`)
      return data
    },
  })

  const revokeAllSessionsMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ revoked: number }>("/auth/sessions/revoke-others")
      return data
    },
  })

  const handleRevokeSessionRef = useRef<
    ((sessionId: string, options?: { skipStepUp?: boolean }) => Promise<void>) | null
  >(null)
  const handleRevokeAllSessionsRef = useRef<
    ((options?: { skipStepUp?: boolean }) => Promise<void>) | null
  >(null)

  const handleRevokeSession = useCallback(
    async (sessionId: string, options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeSessionMutation.mutateAsync(sessionId)
        setSnackbar({ text: t("settings:sessions.snackbar.revoked"), severity: "success" })

        // Wave 135 SW1 — factory-routed cache mutation. The previous
        // inline setQueryData + invalidateQueries pattern is now in
        // updateSessionInCache + invalidateSessions at api/hooks/sessions.ts
        // (closes W134 §Honesty #5).
        updateSessionInCache(queryClient, userId, result)
        await invalidateSessions(queryClient, userId)

        if (result?.is_current) {
          await logout()
        }
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error) && openStepUpFor) {
          openStepUpFor(async () => {
            await handleRevokeSessionRef.current?.(sessionId, { skipStepUp: true })
          })
          return
        }
        setSnackbar({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.failed")),
          severity: "error",
        })
      }
    },
    [logout, openStepUpFor, queryClient, revokeSessionMutation, setSnackbar, t, userId]
  )

  const handleRevokeAllSessions = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeAllSessionsMutation.mutateAsync()
        // Wave 135 SW1 — factory-routed invalidation (closes W134 §Honesty #5).
        await invalidateSessions(queryClient, userId)
        setSnackbar({
          text: t("settings:sessions.snackbar.revokedAll", {
            count: result?.revoked ?? 0,
          }),
          severity: "success",
        })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error) && openStepUpFor) {
          openStepUpFor(async () => {
            await handleRevokeAllSessionsRef.current?.({ skipStepUp: true })
          })
          return
        }
        setSnackbar({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.revokeAllFailed")),
          severity: "error",
        })
      }
    },
    [openStepUpFor, queryClient, revokeAllSessionsMutation, setSnackbar, t, userId]
  )

  useEffect(() => {
    handleRevokeSessionRef.current = handleRevokeSession
  }, [handleRevokeSession])

  useEffect(() => {
    handleRevokeAllSessionsRef.current = handleRevokeAllSessions
  }, [handleRevokeAllSessions])

  const formatSessionTimestamp = useCallback(
    (value: string | null) => {
      if (!value) return t("settings:sessions.lastSeen.never")
      const formatted = formatDate(value, {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
      return formatted || t("settings:sessions.lastSeen.never")
    },
    [t]
  )

  return {
    sessions,
    sortedSessions,
    sessionsFetching,
    sessionsIsError,
    sessionsError,
    handleRevokeSession,
    handleRevokeAllSessions,
    revokeSessionBusy: revokeSessionMutation.isPending,
    revokeAllSessionsBusy: revokeAllSessionsMutation.isPending,
    formatSessionTimestamp,
  }
}
