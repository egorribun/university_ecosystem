import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { useQueryClient } from "@tanstack/react-query"
import api, { API_UNAUTHORIZED_EVENT } from "@/api/client"
import { hasPushConsent, softSyncPushSubscription, unsubscribePush } from "@/push/subscribe"
import { SPOTIFY_REAUTH_EVENT } from "@/hooks/useNowPlaying"
import type { PendingMfaResponse, MfaVerifyPayload } from "@/types/Mfa"
import type { User } from "@/types/User"
import {
  type PendingMfaState,
  type SubmitMfaChallengePayload,
  type UserState,
  type SetUserArg,
  ChallengeLockedError,
} from "@/types/Auth"
import { fetchCurrentUser } from "./useProfileSync"
import i18n from "@/i18n/config"

type TokenWithProfileResponse = {
  access_token: string
  token_type: string
  user?: User
  session?: { signing_key: string } | null
}

const extractSigningKey = (value: TokenWithProfileResponse | undefined | null): string | null => {
  if (!value) return null
  const key = value.session?.signing_key
  return typeof key === "string" && key.length > 0 ? key : null
}

const isTokenWithProfileResponse = (
  value: unknown
): value is TokenWithProfileResponse & { user: User } => {
  if (!value || typeof value !== "object") {
    return false
  }
  const candidate = value as Record<string, unknown>
  if (typeof candidate.access_token !== "string") {
    return false
  }
  if (!candidate.user || typeof candidate.user !== "object") {
    return false
  }
  return true
}

const formatLockoutDuration = (
  seconds: number | null | undefined,
  t: (key: string, options?: any) => string
): string | null => {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) {
    return null
  }

  if (seconds < 60) {
    const value = Math.max(1, Math.ceil(seconds))
    return t("login.duration.seconds", { count: value })
  }

  if (seconds < 3600) {
    const value = Math.max(1, Math.ceil(seconds / 60))
    return t("login.duration.minutes", { count: value })
  }

  const value = Math.max(1, Math.ceil(seconds / 3600))
  return t("login.duration.hours", { count: value })
}

export const useAuthApi = (
  user: UserState,
  setUser: (value: SetUserArg) => void,
  updatePendingMfa: (value: PendingMfaState | null, options?: { broadcast?: boolean }) => void,
  handleUnauthorized: (options?: { broadcast?: boolean; persist?: boolean }) => void,
  updateSessionSigningKey: (value: string | null) => void,
  authOperation: boolean,
  setAuthOperation: (value: boolean) => void,
  resetEtagCache: () => void
) => {
  const { t } = useTranslation("auth")
  const queryClient = useQueryClient()

  const prefetchDashboardData = useCallback(
    async (profileUser: User) => {
      try {
        const activeLanguage = i18n.resolvedLanguage ?? i18n.language ?? "ru"
        const language = activeLanguage === "en" ? "en" : "ru"

        const [
          { prefetchDashboardStories },
          { prefetchDashboardNews },
          { prefetchDashboardEvents },
          { prefetchEventsListQuery, EVENTS_PAGE_SIZE },
        ] = await Promise.all([
          import("@/hooks/useDashboardStories"),
          import("@/hooks/useDashboardNews"),
          import("@/hooks/useDashboardEvents"),
          import("@/api/hooks/events"),
        ])

        void prefetchDashboardStories(queryClient)
        void prefetchDashboardNews(queryClient, language)
        void prefetchDashboardEvents(queryClient)

        if (profileUser.group_id) {
          void prefetchEventsListQuery(queryClient, {
            language,
            is_active: true,
            limit: EVENTS_PAGE_SIZE,
          })
        }
      } catch (error) {
        if (import.meta.env.DEV) {
          console.warn("Failed to prefetch dashboard data", error)
        }
      }
    },
    [queryClient]
  )

  const login = useCallback(
    async (
      email: string,
      password: string,
      trustDevice = false
    ): Promise<PendingMfaState | null> => {
      if (authOperation) return null
      setAuthOperation(true)
      try {
        const params = new URLSearchParams()
        params.append("username", email)
        params.append("password", password)
        if (trustDevice) {
          params.append("trust_device", "true")
        }

        const response = await api.post<TokenWithProfileResponse | PendingMfaResponse>(
          "/auth/login",
          params,
          {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            skipRateLimitQueue: true,
          }
        )

        if (response.status === 202) {
          const mfaResponse = response.data as PendingMfaResponse
          const pendingState: PendingMfaState = { ...mfaResponse, reason: "login" }
          updatePendingMfa(pendingState)
          return pendingState
        }

        const data = response.data as TokenWithProfileResponse
        if (isTokenWithProfileResponse(data)) {
          updateSessionSigningKey(extractSigningKey(data))
          setUser(data.user)
          updatePendingMfa(null)
          if (data.user.spotify_connected) {
            window.dispatchEvent(new Event(SPOTIFY_REAUTH_EVENT))
          }
          void prefetchDashboardData(data.user)
          return null
        }

        throw new Error("Invalid response from server")
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 423) {
          const retryAfter = error.response.headers["retry-after"]
          const seconds = retryAfter ? parseInt(retryAfter, 10) : null
          const duration = formatLockoutDuration(seconds, t)
          if (duration) {
            throw new Error(`${t("login.locked")} ${t("login.lockedRetry", { duration })}`)
          }
          throw new Error(t("login.locked"))
        }
        throw error
      } finally {
        setAuthOperation(false)
      }
    },
    [
      authOperation,
      prefetchDashboardData,
      setAuthOperation,
      setUser,
      t,
      updatePendingMfa,
      updateSessionSigningKey,
    ]
  )

  const logout = useCallback(async () => {
    try {
      if (user) {
        if (hasPushConsent()) {
          await unsubscribePush()
        }
        await api.post("/auth/logout")
      }
    } catch (error) {
      console.error("Logout failed", error)
    } finally {
      handleUnauthorized()
    }
  }, [handleUnauthorized, user])

  const submitMfaChallenge = useCallback(
    async ({ code, challengeToken, trustDevice }: SubmitMfaChallengePayload) => {
      if (authOperation) return
      setAuthOperation(true)
      try {
        const payload: MfaVerifyPayload = {
          method: "totp",
          code,
          challenge_token: challengeToken || "",
          trust_device: trustDevice ?? false,
        }

        const response = await api.post<TokenWithProfileResponse>("/auth/mfa/verify", payload, {
          skipRateLimitQueue: true,
        })
        const data = response.data

        if (isTokenWithProfileResponse(data)) {
          updateSessionSigningKey(extractSigningKey(data))
          setUser(data.user)
          updatePendingMfa(null)
          if (data.user.spotify_connected) {
            window.dispatchEvent(new Event(SPOTIFY_REAUTH_EVENT))
          }
          void prefetchDashboardData(data.user)
        }
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 423) {
          const retryAfter = error.response.headers["retry-after"]
          const seconds = retryAfter ? parseInt(retryAfter, 10) : null
          const duration = formatLockoutDuration(seconds, t)
          const message = duration
            ? `${t("login.locked")} ${t("login.lockedRetry", { duration })}`
            : t("login.locked")
          throw new ChallengeLockedError(message, { refreshable: false })
        }
        throw error
      } finally {
        setAuthOperation(false)
      }
    },
    [
      authOperation,
      prefetchDashboardData,
      setAuthOperation,
      setUser,
      t,
      updatePendingMfa,
      updateSessionSigningKey,
    ]
  )

  const requireMfa = useCallback(async (): Promise<PendingMfaState | null> => {
    try {
      const response = await api.post<PendingMfaResponse>("/auth/mfa/step-up", null, {
        skipRateLimitQueue: true,
      })
      if (response.status === 202) {
        const pendingState: PendingMfaState = { ...response.data, reason: "step-up" }
        updatePendingMfa(pendingState)
        return pendingState
      }
      return null
    } catch (error) {
      if (isAxiosError(error)) {
        if (error.response?.status === 401) {
          window.dispatchEvent(new Event(API_UNAUTHORIZED_EVENT))
          return null
        }
        if (error.response?.status === 409) {
          // Already fresh
          return null
        }
      }
      throw error
    }
  }, [updatePendingMfa])

  const refresh = useCallback(async () => {
    resetEtagCache()
    setAuthOperation(true)
    try {
      const profile = await fetchCurrentUser()
      setUser(profile)
      if (hasPushConsent()) {
        softSyncPushSubscription().catch(() => {
          /* ignore */
        })
      }
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 401) {
        handleUnauthorized()
      }
    } finally {
      setAuthOperation(false)
    }
  }, [handleUnauthorized, resetEtagCache, setAuthOperation, setUser])

  return {
    login,
    logout,
    submitMfaChallenge,
    requireMfa,
    refresh,
  }
}
