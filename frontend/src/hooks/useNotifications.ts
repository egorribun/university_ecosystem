import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react"
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query"

import { logWarning } from "@/app/logger"
import { resolveNotificationAppPath } from "@/notifications/contract"
import {
  getCurrentPushUserId,
  getCurrentPushIdentitySnapshot,
  subscribeToPushIdentity,
  type PushIdentitySnapshot,
} from "@/push/pushMessageBus"
import {
  clearNotifications as clearNotificationsRequest,
  fetchNotificationsList,
  checkSchedule as checkScheduleRequest,
  markAllNotificationsRead as markAllNotificationsReadRequest,
  markNotificationRead as markNotificationReadRequest,
  type NotificationEntry,
  type NotificationsListResult,
} from "@/api/notifications"

type NotificationItem = NotificationEntry & { link?: string }

type NotificationsResponse = NotificationsListResult

type NormalizedNotificationsResponse = {
  items: NotificationItem[]
  unread: number
  hasMore: boolean
  nextCursor: string | null
}

const NOTIFICATIONS_QUERY_KEY = ["notifications", "list"] as const

type NotificationPages = InfiniteData<NormalizedNotificationsResponse, string | undefined>

type MutationBinding = {
  ownerId: string
  ownerRevision: number
  failureKey: string
  attemptId: number
  mutationSequence: number
}

type MarkReadVariables = MutationBinding & {
  operation: "mark-read"
  notificationId: string
}

type MarkAllVariables = MutationBinding & { operation: "mark-all" }
type ClearVariables = MutationBinding & { operation: "clear" }
type NotificationMutationVariables = MarkReadVariables | MarkAllVariables | ClearVariables

type MutationWatermarks = {
  markAllSequence: number
  clearSequence: number
}

export type NotificationMutationFailure = NotificationMutationVariables

type MutationTarget =
  | { operation: "mark-read"; notificationId: string }
  | { operation: "mark-all" }
  | { operation: "clear" }

class NotificationAccountChangedError extends Error {
  constructor() {
    super("The notification account changed before the action completed")
    this.name = "NotificationAccountChangedError"
  }
}

class NotificationMutationSupersededError extends Error {
  constructor() {
    super("The notification action is no longer current")
    this.name = "NotificationMutationSupersededError"
  }
}

const assertMutationOwner = (variables: MutationBinding): void => {
  const activeIdentity = getCurrentPushIdentitySnapshot()
  if (
    variables.ownerId !== activeIdentity.userId ||
    variables.ownerRevision !== activeIdentity.revision
  ) {
    throw new NotificationAccountChangedError()
  }
}

const getMutationFailureKey = (
  ownerId: string,
  ownerRevision: number,
  target: MutationTarget
): string =>
  JSON.stringify([
    ownerId,
    ownerRevision,
    target.operation,
    "notificationId" in target ? target.notificationId : null,
  ])

const SERVER_PUSH_IDENTITY: PushIdentitySnapshot = {
  userId: null,
  revision: 0,
}

// Keeps the first occurrence: a later page can repeat an item after new arrivals shift the pages.
const uniqueById = (items: NotificationItem[]) => {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

// One list for the bell: the unread count and paging state come from the last loaded page,
// which is the freshest response.
function flattenNotificationPages(data: NotificationPages): NormalizedNotificationsResponse {
  const last = data.pages.at(-1)
  return {
    items: uniqueById(data.pages.flatMap((page) => page.items)),
    unread: last?.unread ?? 0,
    hasMore: last?.hasMore ?? false,
    nextCursor: last?.nextCursor ?? null,
  }
}

export function useNotifications() {
  const qc = useQueryClient()
  const identity = useSyncExternalStore(
    subscribeToPushIdentity,
    getCurrentPushIdentitySnapshot,
    () => SERVER_PUSH_IDENTITY
  )
  const ownerId = identity.userId
  const ownerRevision = identity.revision
  const [mutationFailuresByKey, setMutationFailuresByKey] = useState(
    () => new Map<string, NotificationMutationFailure>()
  )
  const mutationAttempts = useRef(new Map<string, number>())
  const mutationSequence = useRef(0)
  const mutationWatermarks = useRef(new Map<string, MutationWatermarks>())
  const seenLiveNotificationIds = useRef(new Set<string>())
  const mutationFailures = Array.from(mutationFailuresByKey.values()).filter(
    (failure) => failure.ownerId === ownerId && failure.ownerRevision === ownerRevision
  )

  useEffect(() => {
    mutationAttempts.current.clear()
    mutationWatermarks.current.clear()
    seenLiveNotificationIds.current.clear()
    setMutationFailuresByKey((current) => {
      const activeFailures = new Map(
        [...current].filter(
          ([, failure]) => failure.ownerId === ownerId && failure.ownerRevision === ownerRevision
        )
      )
      return activeFailures.size === current.size ? current : activeFailures
    })
  }, [ownerId, ownerRevision])

  const beginMutationAttempt = useCallback(
    <T extends MutationTarget>(target: T): (T & MutationBinding) | null => {
      const activeIdentity = getCurrentPushIdentitySnapshot()
      if (
        ownerId === null ||
        activeIdentity.userId !== ownerId ||
        activeIdentity.revision !== ownerRevision
      ) {
        return null
      }
      const failureKey = getMutationFailureKey(ownerId, ownerRevision, target)
      const attemptId = (mutationAttempts.current.get(failureKey) ?? 0) + 1
      mutationAttempts.current.set(failureKey, attemptId)
      mutationSequence.current += 1
      setMutationFailuresByKey((current) => {
        if (!current.has(failureKey)) return current
        const next = new Map(current)
        next.delete(failureKey)
        return next
      })
      return {
        ...target,
        ownerId,
        ownerRevision,
        failureKey,
        attemptId,
        mutationSequence: mutationSequence.current,
      }
    },
    [ownerId, ownerRevision]
  )

  const isCurrentAttempt = useCallback((variables: NotificationMutationVariables) => {
    const activeIdentity = getCurrentPushIdentitySnapshot()
    return (
      variables.ownerId === activeIdentity.userId &&
      variables.ownerRevision === activeIdentity.revision &&
      mutationAttempts.current.get(variables.failureKey) === variables.attemptId
    )
  }, [])

  const rememberMutationFailure = useCallback(
    (_error: unknown, variables: NotificationMutationVariables) => {
      if (!isCurrentAttempt(variables)) return
      const scopeKey = JSON.stringify([variables.ownerId, variables.ownerRevision])
      const watermarks = mutationWatermarks.current.get(scopeKey)
      if (
        watermarks &&
        (variables.mutationSequence < watermarks.clearSequence ||
          (variables.operation === "mark-read" &&
            variables.mutationSequence < watermarks.markAllSequence))
      ) {
        return
      }
      setMutationFailuresByKey((current) => {
        const next = new Map(current)
        next.set(variables.failureKey, variables)
        return next
      })
    },
    [isCurrentAttempt]
  )

  const finishMutationSuccess = useCallback(
    (_data: void, variables: NotificationMutationVariables) => {
      assertMutationOwner(variables)
      // A successful request must reconcile the shared list even if a newer
      // same-target attempt now owns the visible failure state. Refetching is
      // background work; it must not delay navigation after the API succeeds.
      void qc.invalidateQueries({ queryKey: ["notifications"] }).catch((error: unknown) => {
        logWarning("Failed to refresh notifications after a mutation", error)
      })

      if (variables.operation !== "mark-read") {
        const scopeKey = JSON.stringify([variables.ownerId, variables.ownerRevision])
        const current = mutationWatermarks.current.get(scopeKey) ?? {
          markAllSequence: 0,
          clearSequence: 0,
        }
        const next: MutationWatermarks =
          variables.operation === "mark-all"
            ? {
                ...current,
                markAllSequence: Math.max(current.markAllSequence, variables.mutationSequence),
              }
            : {
                ...current,
                clearSequence: Math.max(current.clearSequence, variables.mutationSequence),
              }
        mutationWatermarks.current.set(scopeKey, next)
        setMutationFailuresByKey((currentFailures) => {
          const retainedFailures = new Map(
            [...currentFailures].filter(([, failure]) => {
              if (failure.mutationSequence < next.clearSequence) return false
              if (
                failure.operation === "mark-read" &&
                failure.mutationSequence < next.markAllSequence
              ) {
                return false
              }
              return true
            })
          )
          return retainedFailures.size === currentFailures.size ? currentFailures : retainedFailures
        })
      }

      if (!isCurrentAttempt(variables)) {
        assertMutationOwner(variables)
        throw new NotificationMutationSupersededError()
      }
    },
    [isCurrentAttempt, qc]
  )

  const normalize = (data: NotificationsResponse): NormalizedNotificationsResponse => ({
    items: data.items.map((item) => ({
      ...item,
      link: resolveNotificationAppPath(item.url),
    })),
    unread: data.unread_count,
    hasMore: data.has_more,
    nextCursor: data.next_cursor ?? null,
  })
  // Paged list: every refetch (mutation, interval) replays the loaded pages, so
  // history that was paged in stays visible and its read state stays current.
  const list = useInfiniteQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: async ({ pageParam }) => {
      const data = pageParam
        ? await fetchNotificationsList({ cursor: pageParam })
        : await fetchNotificationsList()
      return normalize(data)
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore && lastPage.nextCursor ? lastPage.nextCursor : undefined,
    select: flattenNotificationPages,
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
    staleTime: 30000,
  })

  // Check for upcoming classes on mount to ensure notifications are generated
  // even if the background worker is idle.
  useEffect(() => {
    void checkScheduleRequest().catch((error: unknown) => {
      logWarning("Failed to generate schedule notifications", error)
    })
  }, [])

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.serviceWorker) return
    const handlePushMessage = (event: MessageEvent<unknown>) => {
      if (!event.data || typeof event.data !== "object") return
      const message = event.data as {
        type?: unknown
        notificationId?: unknown
        recipientUserId?: unknown
      }
      if (
        message.type !== "PUSH_NOTIFICATION" ||
        typeof message.notificationId !== "string" ||
        typeof message.recipientUserId !== "string" ||
        message.recipientUserId.length === 0 ||
        message.recipientUserId !== getCurrentPushUserId()
      ) {
        return
      }
      const notificationId = message.notificationId.trim()
      if (!notificationId || seenLiveNotificationIds.current.has(notificationId)) return
      if (seenLiveNotificationIds.current.size >= 256) {
        seenLiveNotificationIds.current.clear()
      }
      seenLiveNotificationIds.current.add(notificationId)
      void qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY })
    }
    navigator.serviceWorker.addEventListener("message", handlePushMessage)
    return () => navigator.serviceWorker.removeEventListener("message", handlePushMessage)
  }, [qc])

  const markReadMutation = useMutation<void, unknown, MarkReadVariables>({
    mutationFn: async (variables) => {
      assertMutationOwner(variables)
      const { notificationId } = variables
      await markNotificationReadRequest(notificationId)
      assertMutationOwner(variables)
    },
    onError: rememberMutationFailure,
    onSuccess: finishMutationSuccess,
  })
  const markAllMutation = useMutation<void, unknown, MarkAllVariables>({
    mutationFn: async (variables) => {
      assertMutationOwner(variables)
      await markAllNotificationsReadRequest()
      assertMutationOwner(variables)
    },
    onError: rememberMutationFailure,
    onSuccess: finishMutationSuccess,
  })
  const clearMutation = useMutation<void, unknown, ClearVariables>({
    mutationFn: async (variables) => {
      assertMutationOwner(variables)
      await clearNotificationsRequest()
      assertMutationOwner(variables)
    },
    onError: rememberMutationFailure,
    onSuccess: finishMutationSuccess,
  })
  const mutateRead = markReadMutation.mutateAsync
  const mutateMarkAll = markAllMutation.mutateAsync
  const mutateClear = clearMutation.mutateAsync

  const markRead = useCallback(
    (notificationId: string): Promise<void> => {
      const variables = beginMutationAttempt({
        operation: "mark-read",
        notificationId,
      })
      return variables
        ? mutateRead(variables)
        : Promise.reject(new NotificationAccountChangedError())
    },
    [beginMutationAttempt, mutateRead]
  )
  const markAll = useCallback((): Promise<void> => {
    const variables = beginMutationAttempt({ operation: "mark-all" })
    return variables
      ? mutateMarkAll(variables)
      : Promise.reject(new NotificationAccountChangedError())
  }, [beginMutationAttempt, mutateMarkAll])
  const clearAll = useCallback((): Promise<void> => {
    const variables = beginMutationAttempt({ operation: "clear" })
    return variables
      ? mutateClear(variables)
      : Promise.reject(new NotificationAccountChangedError())
  }, [beginMutationAttempt, mutateClear])

  const retryMutationFailure = useCallback(
    (failure: NotificationMutationFailure): Promise<void> => {
      const activeIdentity = getCurrentPushIdentitySnapshot()
      if (
        ownerId === null ||
        failure.ownerId !== ownerId ||
        failure.ownerRevision !== ownerRevision ||
        activeIdentity.userId !== ownerId ||
        activeIdentity.revision !== ownerRevision
      ) {
        return Promise.reject(new NotificationAccountChangedError())
      }
      if (mutationFailuresByKey.get(failure.failureKey)?.attemptId !== failure.attemptId) {
        return Promise.reject(new NotificationMutationSupersededError())
      }
      if (failure.operation === "mark-read") return markRead(failure.notificationId)
      if (failure.operation === "mark-all") return markAll()
      return clearAll()
    },
    [ownerId, ownerRevision, mutationFailuresByKey, markRead, markAll, clearAll]
  )
  const fetchNextPage = list.fetchNextPage
  const fetchMore = useCallback(
    async (cursor?: string | null) => {
      if (!cursor) {
        return
      }
      await fetchNextPage()
    },
    [fetchNextPage]
  )
  return {
    data: list.data?.items ?? [],
    unreadCount: list.data?.unread ?? 0,
    hasMore: list.data?.hasMore ?? false,
    nextCursor: list.data?.nextCursor ?? null,
    isLoading: list.isLoading,
    isError: list.isError,
    error: list.error,
    isRefetching: list.isRefetching,
    refetch: list.refetch,
    markRead,
    markAll,
    clearAll,
    mutationFailures,
    retryMutationFailure,
    isMarkingAll:
      markAllMutation.isPending &&
      markAllMutation.variables?.ownerId === ownerId &&
      markAllMutation.variables?.ownerRevision === ownerRevision,
    isClearing:
      clearMutation.isPending &&
      clearMutation.variables?.ownerId === ownerId &&
      clearMutation.variables?.ownerRevision === ownerRevision,
    fetchMore,
    isFetchingMore: list.isFetchingNextPage,
    isFetchMoreError: list.isFetchNextPageError,
    fetchMoreError: list.isFetchNextPageError ? list.error : null,
  }
}
