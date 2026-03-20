import { useCallback, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { formatDate, toDate } from "@/utils/date"

import api from "@/api/client"
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

  const sessionsKey = useMemo(() => ["auth", "sessions", user?.id ?? "me"], [user?.id])

  const fetchSessions = useCallback(async () => {
    const { data } = await api.get<ActiveSession[]>("/auth/sessions")
    return data
  }, [])

  const {
    data: sessionsData,
    isFetching: sessionsFetching,
    isError: sessionsIsError,
    error: sessionsError,
  } = useQuery<ActiveSession[], unknown>({
    queryKey: sessionsKey,
    queryFn: fetchSessions,
    enabled: tabActive && Boolean(user),
    staleTime: 30_000,
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

  const handleRevokeSession = useCallback(
    async (sessionId: string, options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeSessionMutation.mutateAsync(sessionId)
        setSnackbar({ text: t("settings:sessions.snackbar.revoked"), severity: "success" })

        // Update cache immediately and then invalidate
        queryClient.setQueryData<ActiveSession[] | undefined>(sessionsKey, (previous) => {
          if (!Array.isArray(previous)) return previous
          return previous.map((session) => (session.id === result.id ? result : session))
        })
        await queryClient.invalidateQueries({ queryKey: sessionsKey })

        if (result?.is_current) {
          await logout()
        }
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error) && openStepUpFor) {
          openStepUpFor(async () => {
            await handleRevokeSession(sessionId, { skipStepUp: true })
          })
          return
        }
        setSnackbar({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.failed")),
          severity: "error",
        })
      }
    },
    [logout, openStepUpFor, queryClient, revokeSessionMutation, sessionsKey, setSnackbar, t]
  )

  const handleRevokeAllSessions = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeAllSessionsMutation.mutateAsync()
        await queryClient.invalidateQueries({ queryKey: sessionsKey })
        setSnackbar({
          text: t("settings:sessions.snackbar.revokedAll", {
            count: result?.revoked ?? 0,
          }),
          severity: "success",
        })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error) && openStepUpFor) {
          openStepUpFor(async () => {
            await handleRevokeAllSessions({ skipStepUp: true })
          })
          return
        }
        setSnackbar({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.revokeAllFailed")),
          severity: "error",
        })
      }
    },
    [openStepUpFor, queryClient, revokeAllSessionsMutation, sessionsKey, setSnackbar, t]
  )

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
