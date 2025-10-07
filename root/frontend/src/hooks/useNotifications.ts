import { useCallback, useEffect, useMemo } from "react"
import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationListResponse,
} from "@/api/notifications"

export type AppNotification = {
  id: number | string
  title: string
  body?: string
  type?: string
  url?: string
  created_at: string
  read: boolean
  read_at?: string
  avatar_url?: string
  icon?: string
}

const PAGE_SIZE = 20

export const notificationsQueryKey = ["notifications", "list"] as const

type NotificationsInfiniteData = InfiniteData<NotificationListResponse, string | null>

type LoadMode = "reset" | "append"

function normalizeItem(item: NotificationListResponse["items"][number]): AppNotification {
  return {
    id: item.id,
    title: item.title,
    body: item.body ?? undefined,
    type: item.type ?? undefined,
    url: item.url ?? undefined,
    created_at: item.created_at,
    read: Boolean(item.read),
    read_at: item.read_at ?? undefined,
  }
}

function markItemReadInCache(
  data: NotificationsInfiniteData | undefined,
  id: number | string,
  iso: string,
): NotificationsInfiniteData | undefined {
  if (!data) return data

  let mutated = false
  let decremented = false

  const pages = data.pages.map(page => {
    const index = page.items.findIndex(item => item.id === Number(id))
    if (index === -1) return page

    const original = page.items[index]
    const wasUnread = !original.read
    const nextItem = {
      ...original,
      read: true,
      read_at: original.read_at ?? iso,
    }

    const unread_count =
      wasUnread && !decremented ? Math.max(0, (page.unread_count ?? 0) - 1) : page.unread_count
    if (wasUnread && !decremented) decremented = true

    mutated = mutated || wasUnread || original.read_at == null

    const nextItems = page.items.slice()
    nextItems[index] = nextItem

    return {
      ...page,
      unread_count,
      items: nextItems,
    }
  })

  if (!mutated) return data

  return {
    ...data,
    pages,
  }
}

function markAllReadInCache(
  data: NotificationsInfiniteData | undefined,
  iso: string,
): NotificationsInfiniteData | undefined {
  if (!data) return data

  let mutated = false

  const pages = data.pages.map(page => {
    let changed = false
    const nextItems = page.items.map(item => {
      if (!item.read || !item.read_at) {
        changed = true
        return {
          ...item,
          read: true,
          read_at: item.read_at ?? iso,
        }
      }
      return item
    })

    if (!changed && (page.unread_count ?? 0) === 0) {
      return page
    }

    mutated = mutated || changed || (page.unread_count ?? 0) > 0

    return {
      ...page,
      unread_count: 0,
      items: changed ? nextItems : page.items,
    }
  })

  if (!mutated) return data

  return {
    ...data,
    pages,
  }
}

export function useNotifications() {
  const queryClient = useQueryClient()

  const query = useInfiniteQuery({
    queryKey: notificationsQueryKey,
    queryFn: async ({ pageParam }) =>
      fetchNotifications({ limit: PAGE_SIZE, cursor: pageParam ?? null }),
    initialPageParam: null as string | null,
    getNextPageParam: lastPage =>
      lastPage.has_more ? lastPage.next_cursor ?? undefined : undefined,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  })

  const {
    data,
    isLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
    error,
    isError,
  } = query

  const items = useMemo(() => {
    if (!data) return [] as AppNotification[]
    return data.pages.flatMap(page => page.items.map(normalizeItem))
  }, [data])

  const unreadCount = useMemo(() => {
    const fromItems = items.reduce((acc, item) => acc + (item.read ? 0 : 1), 0)
    const fromServer =
      data?.pages.reduce((max, page) => Math.max(max, page.unread_count ?? 0), 0) ?? 0
    return Math.max(fromItems, fromServer)
  }, [data, items])

  const load = useCallback(
    async (mode: LoadMode = "reset") => {
      if (mode === "append") {
        if (!hasNextPage) return
        await fetchNextPage()
        return
      }
      await refetch()
    },
    [fetchNextPage, hasNextPage, refetch],
  )

  const markReadMutation = useMutation({
    mutationFn: async ({ id }: { id: number; iso: string }) => {
      await markNotificationRead(id)
    },
    onMutate: async ({ id, iso }: { id: number; iso: string }) => {
      await queryClient.cancelQueries({ queryKey: notificationsQueryKey })
      const previous = queryClient.getQueryData<NotificationsInfiniteData>(notificationsQueryKey)

      queryClient.setQueryData(
        notificationsQueryKey,
        (current: NotificationsInfiniteData | undefined) => markItemReadInCache(current, id, iso),
      )

      return { previous }
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(notificationsQueryKey, context.previous)
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: notificationsQueryKey })
    },
  })

  const markAllMutation = useMutation({
    mutationFn: async () => {
      await markAllNotificationsRead()
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: notificationsQueryKey })
      const previous = queryClient.getQueryData<NotificationsInfiniteData>(notificationsQueryKey)
      const iso = new Date().toISOString()
      queryClient.setQueryData(
        notificationsQueryKey,
        (current: NotificationsInfiniteData | undefined) => markAllReadInCache(current, iso),
      )
      return { previous }
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(notificationsQueryKey, context.previous)
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: notificationsQueryKey })
    },
  })

  const markRead = useCallback(
    async (id: number | string) => {
      const parsed = Number(id)
      const iso = new Date().toISOString()

      if (Number.isFinite(parsed)) {
        await markReadMutation.mutateAsync({ id: parsed, iso })
      } else {
        queryClient.setQueryData(
          notificationsQueryKey,
          (current: NotificationsInfiniteData | undefined) => markItemReadInCache(current, id, iso),
        )
        void queryClient.invalidateQueries({ queryKey: notificationsQueryKey })
      }
    },
    [markReadMutation, queryClient],
  )

  const markAllRead = useCallback(async () => {
    await markAllMutation.mutateAsync()
  }, [markAllMutation])

  const loadMore = useCallback(async () => {
    await load("append")
  }, [load])

  const refresh = useCallback(async () => {
    await load("reset")
  }, [load])

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return

    const onMessage = (event: MessageEvent) => {
      const msg: any = event.data ?? {}
      if (msg?.type === "PUSH_NOTIFICATION") {
        void queryClient.invalidateQueries({ queryKey: notificationsQueryKey })
        return
      }
      if (msg?.type === "NOTIFICATION_MARK_READ" && msg.id != null) {
        const iso = new Date().toISOString()
        queryClient.setQueryData(
          notificationsQueryKey,
          (current: NotificationsInfiniteData | undefined) => markItemReadInCache(current, msg.id, iso),
        )
        return
      }
    }

    navigator.serviceWorker.addEventListener("message", onMessage)
    return () => navigator.serviceWorker.removeEventListener("message", onMessage)
  }, [queryClient])

  useEffect(() => {
    if (!("setAppBadge" in navigator)) return
    try {
      const nav: any = navigator
      if (unreadCount > 0) nav.setAppBadge?.(unreadCount)
      else nav.clearAppBadge?.()
    } catch {}
  }, [unreadCount])

  return {
    items,
    loading: isLoading,
    unreadCount,
    hasMore: Boolean(hasNextPage),
    loadMore,
    markRead,
    markAllRead,
    refresh,
    fetching: isFetching,
    loadingMore: isFetchingNextPage,
    error: (error as Error | null) ?? null,
    isError,
  }
}
