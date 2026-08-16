import { useCallback, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { logWarning } from "@/app/logger"
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

export function useNotifications() {
  const qc = useQueryClient()
  const queryKey = ["notifications", "list"] as const
  const normalize = (data: NotificationsResponse): NormalizedNotificationsResponse => ({
    items: data.items.map((item) => ({
      ...item,
      link: item.url ?? undefined,
    })),
    unread: data.unread_count,
    hasMore: data.has_more,
    nextCursor: data.next_cursor ?? null,
  })
  const list = useQuery<NormalizedNotificationsResponse>({
    queryKey,
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
      qc.setQueryData<NormalizedNotificationsResponse | undefined>(queryKey, (current) => {
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
      })
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
    markRead: (id: string) => markRead.mutate(id),
    markAll: () => markAll.mutate(),
    clearAll: clearAll.mutate,
    isMarkingAll: markAll.isPending,
    isClearing: clearAll.isPending,
    fetchMore,
    isFetchingMore,
    isFetchMoreError,
    fetchMoreError,
  }
}
