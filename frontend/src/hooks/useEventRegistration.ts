import {
  useState,
  useEffect,
  useCallback,
  useLayoutEffect,
  useMemo,
  useOptimistic,
  useRef,
  useTransition,
} from "react"
import { isAxiosError } from "axios"
import api from "@/api/client"
import type { Event } from "@/types/Event"
import type { User } from "@/types/User"
import { useTranslation } from "react-i18next"

/** Keys for local storage */
const regKey = (eventId: string, userId: number | string) => `event:reg:${eventId}:${userId}`

const qrKey = (eventId: string, userId: number | string | undefined) =>
  `event:qr:${eventId}:${userId ?? "anon"}`

interface UseEventRegistrationOptions {
  eventId: string
  user: User | null
  initialRegistered?: boolean
  initialParticipantCount?: number
  initialQrToken?: string
  onNotify?: (message: string) => void
}

interface RegistrationScope {
  eventId: string
  userId: number | string | undefined
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
  const userId = user?.id
  const [isRegistered, setIsRegistered] = useState(initialRegistered)
  const [participantCount, setParticipantCount] = useState(initialParticipantCount)
  const [qrToken, setQrToken] = useState<string | undefined>(initialQrToken)
  const [stateScope, setStateScope] = useState<RegistrationScope>(() => ({ eventId, userId }))
  const activeScopeRef = useRef<RegistrationScope | null>(stateScope)
  const [pendingOperations, setPendingOperations] = useState<
    ReadonlyMap<RegistrationScope, ReadonlySet<symbol>>
  >(() => new Map())
  const [, startTransition] = useTransition()

  useLayoutEffect(() => {
    activeScopeRef.current = stateScope
    return () => {
      activeScopeRef.current = null
    }
  }, [stateScope])

  const isCurrentScope = useCallback(
    (operationScope: RegistrationScope) => activeScopeRef.current === operationScope,
    []
  )

  const beginPendingOperation = useCallback((operationScope: RegistrationScope) => {
    const token = Symbol()
    setPendingOperations((current) => {
      const next = new Map(current)
      const tokens = new Set(next.get(operationScope))
      tokens.add(token)
      next.set(operationScope, tokens)
      return next
    })

    return () => {
      if (activeScopeRef.current === null) return
      setPendingOperations((current) => {
        const next = new Map(current)
        const tokens = new Set(next.get(operationScope))
        tokens.delete(token)
        if (tokens.size === 0) {
          next.delete(operationScope)
        } else {
          next.set(operationScope, tokens)
        }
        return next
      })
    }
  }, [])

  // Tag optimistic values with the object-identity scope generation. Pending
  // optimistic state from A is ignored as soon as render switches to B.
  const registeredBase = useMemo(
    () => ({ scope: stateScope, value: isRegistered }),
    [isRegistered, stateScope]
  )
  const countBase = useMemo(
    () => ({ scope: stateScope, value: participantCount }),
    [participantCount, stateScope]
  )
  const [optimisticRegistered, setOptimisticRegistered] = useOptimistic(registeredBase)
  const [optimisticCount, setOptimisticCount] = useOptimistic(countBase)

  // A hook instance may be reused for another event or user. Reset during render
  // so React retries with the new scope before persistence/recovery effects commit.
  if (stateScope.eventId !== eventId || stateScope.userId !== userId) {
    setStateScope({ eventId, userId })
    setIsRegistered(initialRegistered)
    setParticipantCount(initialParticipantCount)
    setQrToken(initialQrToken)
  }

  // Sync state from props changes
  useEffect(() => {
    setIsRegistered(initialRegistered)
  }, [initialRegistered])

  useEffect(() => {
    setParticipantCount(initialParticipantCount)
  }, [initialParticipantCount])

  // Restore cached registration state on mount
  useEffect(() => {
    if (!userId) return
    try {
      const cached = localStorage.getItem(regKey(eventId, userId))
      if (cached === "1" && !initialRegistered) {
        setIsRegistered(true)
      }
    } catch {
      // ignore
    }
  }, [eventId, userId, initialRegistered])

  // Persist registration state to localStorage
  useEffect(() => {
    if (!userId) return
    try {
      if (isRegistered) {
        localStorage.setItem(regKey(eventId, userId), "1")
      } else {
        localStorage.removeItem(regKey(eventId, userId))
      }
    } catch {
      // ignore
    }
  }, [isRegistered, eventId, userId])

  // Sync QR token with registered state and localStorage
  useEffect(() => {
    if (!isRegistered) {
      setQrToken(undefined)
      try {
        localStorage.removeItem(qrKey(eventId, userId))
      } catch {
        // ignore
      }
      return
    }

    if (initialQrToken) {
      setQrToken(initialQrToken)
      try {
        localStorage.setItem(qrKey(eventId, userId), initialQrToken)
      } catch {
        // ignore
      }
    } else {
      // Try to recover from localStorage
      try {
        const stored = localStorage.getItem(qrKey(eventId, userId))
        if (stored) setQrToken(stored)
      } catch {
        // ignore
      }
    }
  }, [isRegistered, initialQrToken, eventId, userId])

  const sync = useCallback(async (): Promise<"registered" | "unregistered" | null> => {
    const operationScope = stateScope
    try {
      const res = await api.get<Event>(`/events/${eventId}`)
      if (!isCurrentScope(operationScope)) return null
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
            localStorage.setItem(qrKey(eventId, userId), code)
          } catch {
            // ignore
          }
        }
      } else {
        setQrToken(undefined)
        try {
          localStorage.removeItem(qrKey(eventId, userId))
        } catch {
          // ignore
        }
      }

      setIsRegistered(nextRegistered)
      return nextRegistered ? "registered" : "unregistered"
    } catch {
      return null
    }
  }, [eventId, isCurrentScope, stateScope, userId])

  const register = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    const operationScope = stateScope
    const releasePending = beginPendingOperation(operationScope)
    startTransition(async () => {
      try {
        // Instant optimistic feedback
        setOptimisticRegistered({ scope: operationScope, value: true })
        setOptimisticCount({ scope: operationScope, value: participantCount + 1 })

        try {
          const res = await api.post<{ qr_code: string }>("/events/attendance", {
            event_id: eventId,
          })
          if (!isCurrentScope(operationScope)) return
          const code: string = res.data.qr_code
          setIsRegistered(true)
          setQrToken(code)
          setParticipantCount((c) => c + 1)
          onNotify?.(t("events:card.messages.registerSuccess"))
          try {
            localStorage.setItem(qrKey(eventId, userId), code)
          } catch {
            // ignore
          }
        } catch (error) {
          // Optimistic state auto-reverts when transition completes
          if (!isCurrentScope(operationScope)) return

          const shouldResync =
            isAxiosError(error) &&
            (error.code === "ECONNABORTED" ||
              error.code === "ERR_NETWORK" ||
              !error.response ||
              (typeof error.response?.status === "number" && error.response.status >= 500))

          if (shouldResync) {
            const restored = await sync()
            if (!isCurrentScope(operationScope)) return
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
        }
      } finally {
        releasePending()
      }
    })
  }

  const unregister = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    const operationScope = stateScope
    const releasePending = beginPendingOperation(operationScope)
    startTransition(async () => {
      try {
        // Instant optimistic feedback
        setOptimisticRegistered({ scope: operationScope, value: false })
        setOptimisticCount({ scope: operationScope, value: Math.max(0, participantCount - 1) })

        try {
          await api.delete("/events/attendance", { data: { event_id: eventId } })
          if (!isCurrentScope(operationScope)) return
          setIsRegistered(false)
          setQrToken(undefined)
          setParticipantCount((c) => Math.max(0, c - 1))
          onNotify?.(t("events:card.messages.unregisterSuccess"))
          try {
            localStorage.removeItem(qrKey(eventId, userId))
          } catch {
            // ignore
          }
        } catch (error) {
          // Optimistic state auto-reverts when transition completes
          if (!isCurrentScope(operationScope)) return

          const shouldResync =
            isAxiosError(error) &&
            (error.code === "ECONNABORTED" ||
              error.code === "ERR_NETWORK" ||
              !error.response ||
              (typeof error.response?.status === "number" && error.response.status >= 500))

          if (shouldResync) {
            const restored = await sync()
            if (!isCurrentScope(operationScope)) return
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
        }
      } finally {
        releasePending()
      }
    })
  }

  return {
    isRegistered:
      optimisticRegistered.scope === stateScope ? optimisticRegistered.value : isRegistered,
    participantCount:
      optimisticCount.scope === stateScope ? optimisticCount.value : participantCount,
    qrToken,
    isLoading: (pendingOperations.get(stateScope)?.size ?? 0) > 0,
    register,
    unregister,
    sync,
  }
}
