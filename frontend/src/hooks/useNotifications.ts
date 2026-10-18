import { useCallback, useEffect, useRef } from "react"
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query"

import { logWarning } from "@/app/logger"
import { resolveNotificationAppPath } from "@/notifications/contract"
import { getCurrentPushUserId } from "@/push/pushMessageBus"
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
    markRead: markRead.mutate,
    markAll: markAll.mutate,
    clearAll: clearAll.mutate,
    isMarkingAll: markAll.isPending,
    isClearing: clearAll.isPending,
    fetchMore,
    isFetchingMore: list.isFetchingNextPage,
    isFetchMoreError: list.isFetchNextPageError,
    fetchMoreError: list.isFetchNextPageError ? list.error : null,
  }
}
