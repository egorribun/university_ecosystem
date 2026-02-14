import { useState, useEffect, useCallback } from "react"
import { isAxiosError } from "axios"
import api from "@/api/client"
import type { Event } from "@/types/Event"
import type { User } from "@/types/User"
import { useTranslation } from "react-i18next"

/** Keys for local storage */
const regKey = (eventId: string, userId: number | string | undefined) =>
  `event:reg:${eventId}:${userId ?? "anon"}`

const qrKey = (eventId: string, user: User | null) => `event:qr:${eventId}:${user?.id ?? "anon"}`

interface UseEventRegistrationOptions {
  eventId: string
  user: User | null
  initialRegistered?: boolean
  initialParticipantCount?: number
  initialQrToken?: string
  onNotify?: (message: string) => void
}

export function useEventRegistration({
  eventId,
  user,
  initialRegistered = false,
  initialParticipantCount = 0,
  initialQrToken,
  onNotify,
}: UseEventRegistrationOptions) {
  const { t } = useTranslation(["events"])
  const [isRegistered, setIsRegistered] = useState(initialRegistered)
  const [participantCount, setParticipantCount] = useState(initialParticipantCount)
  const [qrToken, setQrToken] = useState<string | undefined>(initialQrToken)
  const [isLoading, setIsLoading] = useState(false)

  // Sync state from props changes
  useEffect(() => {
    setIsRegistered(initialRegistered)
  }, [initialRegistered])

  useEffect(() => {
    setParticipantCount(initialParticipantCount)
  }, [initialParticipantCount])

  // Restore cached registration state on mount
  useEffect(() => {
    if (!user?.id) return
    try {
      const cached = localStorage.getItem(regKey(eventId, user.id))
      if (cached === "1" && !initialRegistered) {
        setIsRegistered(true)
      }
    } catch {
      // ignore
    }
  }, [eventId, user?.id, initialRegistered])

  // Persist registration state to localStorage
  useEffect(() => {
    if (!user?.id) return
    try {
      if (isRegistered) {
        localStorage.setItem(regKey(eventId, user.id), "1")
      } else {
        localStorage.removeItem(regKey(eventId, user.id))
      }
    } catch {
      // ignore
    }
  }, [isRegistered, eventId, user?.id])

  // Sync QR token with registered state and localStorage
  useEffect(() => {
    if (!isRegistered) {
      setQrToken(undefined)
      try {
        localStorage.removeItem(qrKey(eventId, user))
      } catch {
        // ignore
      }
      return
    }

    if (initialQrToken) {
      setQrToken(initialQrToken)
      try {
        localStorage.setItem(qrKey(eventId, user), initialQrToken)
      } catch {
        // ignore
      }
    } else {
      // Try to recover from localStorage
      try {
        const stored = localStorage.getItem(qrKey(eventId, user))
        if (stored) setQrToken(stored)
      } catch {
        // ignore
      }
    }
  }, [isRegistered, initialQrToken, eventId, user])

  const sync = useCallback(async (): Promise<"registered" | "unregistered" | null> => {
    try {
      const res = await api.get<Event>(`/events/${eventId}`)
      const event = res.data
      const nextRegistered = Boolean(event?.is_registered)

      if (typeof event?.participant_count === "number") {
        setParticipantCount(event.participant_count)
      }

      if (nextRegistered) {
        const code = event?.my_qr_token
        if (code) {
          setQrToken(code)
          try {
            localStorage.setItem(qrKey(eventId, user), code)
          } catch {
            // ignore
          }
        }
      } else {
        setQrToken(undefined)
        try {
          localStorage.removeItem(qrKey(eventId, user))
        } catch {
          // ignore
        }
      }

      setIsRegistered(nextRegistered)
      return nextRegistered ? "registered" : "unregistered"
    } catch {
      return null
    }
  }, [eventId, user])

  const register = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    setIsLoading(true)
    try {
      const res = await api.post<{ qr_code: string }>("/events/attendance", { event_id: eventId })
      const code: string = res.data.qr_code
      setIsRegistered(true)
      setQrToken(code)
      setParticipantCount((c) => c + 1)
      onNotify?.(t("events:card.messages.registerSuccess"))
      try {
        localStorage.setItem(qrKey(eventId, user), code)
      } catch {
        // ignore
      }
    } catch (error) {
      const shouldResync =
        isAxiosError(error) &&
        (error.code === "ECONNABORTED" ||
          error.code === "ERR_NETWORK" ||
          !error.response ||
          (typeof error.response?.status === "number" && error.response.status >= 500))

      if (shouldResync) {
        const restored = await sync()
        if (restored === "registered") {
          onNotify?.(t("events:card.messages.registerSuccess"))
          return
        }
      }

      const detail =
        (isAxiosError(error) && typeof error.response?.data?.detail === "string"
          ? error.response?.data?.detail
          : null) || t("events:card.messages.registerFailure")
      onNotify?.(detail)
    } finally {
      setIsLoading(false)
    }
  }

  const unregister = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    setIsLoading(true)
    try {
      await api.delete("/events/attendance", { data: { event_id: eventId } })
      setIsRegistered(false)
      setQrToken(undefined)
      setParticipantCount((c) => Math.max(0, c - 1))
      onNotify?.(t("events:card.messages.unregisterSuccess"))
      try {
        localStorage.removeItem(qrKey(eventId, user))
      } catch {
        // ignore
      }
    } catch (error) {
      const shouldResync =
        isAxiosError(error) &&
        (error.code === "ECONNABORTED" ||
          error.code === "ERR_NETWORK" ||
          !error.response ||
          (typeof error.response?.status === "number" && error.response.status >= 500))

      if (shouldResync) {
        const restored = await sync()
        if (restored === "unregistered") {
          onNotify?.(t("events:card.messages.unregisterSuccess"))
          return
        }
      }

      const detail =
        (isAxiosError(error) && typeof error.response?.data?.detail === "string"
          ? error.response?.data?.detail
          : null) || t("events:card.messages.unregisterFailure")
      onNotify?.(detail)
    } finally {
      setIsLoading(false)
    }
  }

  return {
    isRegistered,
    participantCount,
    qrToken,
    isLoading,
    register,
    unregister,
    sync,
  }
}
