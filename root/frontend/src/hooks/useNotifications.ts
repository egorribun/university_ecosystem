import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import api from "@/api/client"

export type NotificationItem = {
  id: number
  title: string
  body?: string
  created_at: string
  read: boolean
  link?: string
}

type NotificationsResponse = {
  items?: NotificationItem[]
  unread_count?: number
  has_more?: boolean
  next_cursor?: string | null
}

type NormalizedNotificationsResponse = {
  items: NotificationItem[]
  unread: number
  hasMore: boolean
  nextCursor: string | null
}

export function useNotifications() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: async () => {
      const { data } = await api.get<NotificationsResponse>("/notifications")
      const normalized: NormalizedNotificationsResponse = {
        items: Array.isArray(data.items) ? data.items : [],
        unread: typeof data.unread_count === "number" ? data.unread_count : 0,
        hasMore: Boolean(data.has_more),
        nextCursor: data.next_cursor ?? null,
      }
      return normalized
    },
    refetchInterval: 60000,
    staleTime: 30000,
  })
  const markRead = useMutation({
    mutationFn: async (id: number) => {
      await api.post(`/notifications/${id}/read`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  })
  const markAll = useMutation({
    mutationFn: async () => {
      await api.post("/notifications/read-all")
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  })
  return {
    data: list.data?.items ?? [],
    unreadCount: list.data?.unread ?? 0,
    hasMore: list.data?.hasMore ?? false,
    nextCursor: list.data?.nextCursor ?? null,
    isLoading: list.isLoading,
    markRead: (id: number) => markRead.mutate(id),
    markAll: () => markAll.mutate(),
  }
}
