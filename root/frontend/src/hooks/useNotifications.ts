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

export function useNotifications() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: async () => {
      const { data } = await api.get<{ items: NotificationItem[]; unread: number }>("/notifications")
      return data
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
    isLoading: list.isLoading,
    markRead: (id: number) => markRead.mutate(id),
    markAll: () => markAll.mutate(),
  }
}
