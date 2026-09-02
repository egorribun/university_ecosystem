import { useCallback, useEffect, useRef } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { logWarning } from "@/app/logger"
import { resolveNotificationAppPath } from "@/notifications/contract"
import {
  clearNotifications as clearNotificationsRequest,
  fetchNotificationsList,
  checkSchedule as checkScheduleRequest,
  markAllNotificationsRead as markAllNotificationsReadRequest,
  markNotificationRead as markNotificationReadRequest,
  type NotificationEntry,
  type NotificationsListResult,
} from "@/api/notifications"

export type NotificationItem = NotificationEntry & { link?: string }

type NotificationsResponse = NotificationsListResult

type NormalizedNotificationsResponse = {
  items: NotificationItem[]
  unread: number
  hasMore: boolean
  nextCursor: string | null
}

const NOTIFICATIONS_QUERY_KEY = ["notifications", "list"] as const

export function useNotifications() {
  const qc = useQueryClient()
  const seenLiveNotificationIds = useRef(new Set<string>())
  const normalize = (data: NotificationsResponse): NormalizedNotificationsResponse => ({
    items: data.items.map((item) => ({
      ...item,
      link: resolveNotificationAppPath(item.url),
    })),
    unread: data.unread_count,
    hasMore: data.has_more,
    nextCursor: data.next_cursor ?? null,
  })
  const list = useQuery<NormalizedNotificationsResponse>({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: async () => {
      const data = await fetchNotificationsList()
      return normalize(data)
    },
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
      const message = event.data as { type?: unknown; notificationId?: unknown }
      if (message.type !== "PUSH_NOTIFICATION" || typeof message.notificationId !== "string") {
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

  const markRead = useMutation({
    mutationFn: async (id: string) => {
      await markNotificationReadRequest(id)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  })
  const markAll = useMutation({
    mutationFn: async () => {
      await markAllNotificationsReadRequest()
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  })
  const clearAll = useMutation({
    mutationFn: async () => {
      await clearNotificationsRequest()
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  })
  const {
    mutateAsync: fetchMoreMutateAsync,
    isPending: isFetchingMore,
    isError: isFetchMoreError,
    error: fetchMoreError,
  } = useMutation<NormalizedNotificationsResponse, unknown, string>({
    mutationFn: async (cursor: string) => {
      const data = await fetchNotificationsList({ cursor })
      return normalize(data)
    },
    onSuccess: (nextPage) => {
      qc.setQueryData<NormalizedNotificationsResponse | undefined>(
        NOTIFICATIONS_QUERY_KEY,
        (current) => {
          if (!current) {
            return nextPage
          }

          const existingIds = new Set(current.items.map((item) => item.id))
          const mergedItems = [...current.items]
          for (const item of nextPage.items) {
            if (!existingIds.has(item.id)) {
              mergedItems.push(item)
            }
          }

          return {
            items: mergedItems,
            unread: nextPage.unread,
            hasMore: nextPage.hasMore,
            nextCursor: nextPage.nextCursor,
          }
        }
      )
    },
  })
  const fetchMore = useCallback(
    async (cursor?: string | null) => {
      if (!cursor) {
        return
      }
      await fetchMoreMutateAsync(cursor)
    },
    [fetchMoreMutateAsync]
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
    markRead: markRead.mutate,
    markAll: markAll.mutate,
    clearAll: clearAll.mutate,
    isMarkingAll: markAll.isPending,
    isClearing: clearAll.isPending,
    fetchMore,
    isFetchingMore,
    isFetchMoreError,
    fetchMoreError,
  }
}
