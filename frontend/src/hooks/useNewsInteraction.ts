import { useState, useCallback, useEffect } from "react"
import api from "@/api/client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"

const NEWS_INTERACTION_STORE = "pending-news-interactions"
const NEWS_INTERACTION_SYNC_TAG = "news-interaction:sync"
const CLICK_DB_NAME = "notification-interactions"
const CLICK_DB_VERSION = 1

export type NewsComment = {
  id: number
  content: string
  user_id: number
  user_name: string
  created_at: string
}

export type NewsInteractions = {
  likes_count: number
  is_liked: boolean
  comments: NewsComment[]
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(CLICK_DB_NAME, CLICK_DB_VERSION)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function queueInteraction(url: string, payload: any) {
  const db = await openDatabase()
  const tx = db.transaction(NEWS_INTERACTION_STORE, "readwrite")
  const store = tx.objectStore(NEWS_INTERACTION_STORE)
  await new Promise<void>((resolve, reject) => {
    const req = store.add({ url, payload, timestamp: Date.now() })
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })

  // Trigger SW sync if possible
  if ("serviceWorker" in navigator && "SyncManager" in window) {
    const registration = await navigator.serviceWorker.ready
    try {
      // @ts-expect-error: sync is not yet standard in all browsers
      await registration.sync.register(NEWS_INTERACTION_SYNC_TAG)
    } catch (e) {
      console.warn("Failed to register background sync", e)
    }
  }
}

export function useNewsInteraction(newsId: number) {
  const queryClient = useQueryClient()
  const queryKey = ["news", newsId, "interactions"]

  const { data: interactions, isLoading } = useQuery<NewsInteractions>({
    queryKey,
    queryFn: async () => {
      const res = await api.get<NewsInteractions>(`/news/${newsId}/interactions`)
      return res.data
    },
    staleTime: 30000,
  })

  const likeMutation = useMutation({
    mutationFn: async () => {
      try {
        await api.post(`/news/${newsId}/like`)
      } catch (error) {
        if (!navigator.onLine) {
          await queueInteraction(`/api/v1/news/${newsId}/like`, {})
          return { isOfflineStore: true }
        }
        throw error
      }
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<NewsInteractions>(queryKey)
      if (previous) {
        queryClient.setQueryData<NewsInteractions>(queryKey, {
          ...previous,
          is_liked: !previous.is_liked,
          likes_count: previous.is_liked ? previous.likes_count - 1 : previous.likes_count + 1,
        })
      }
      return { previous }
    },
    onError: (err, variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })

  const commentMutation = useMutation({
    mutationFn: async (content: string) => {
      try {
        const res = await api.post(`/news/${newsId}/comment`, { content })
        return res.data
      } catch (error) {
        if (!navigator.onLine) {
          await queueInteraction(`/api/v1/news/${newsId}/comment`, { content })
          return { isOfflineStore: true }
        }
        throw error
      }
    },
    onMutate: async (content) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<NewsInteractions>(queryKey)
      if (previous) {
        // Optimistic comment (minimal details)
        const optimisticComment: NewsComment = {
          id: -Date.now(),
          content,
          user_id: 0, // Will be filled by backend
          user_name: "You (offline)",
          created_at: new Date().toISOString(),
        }
        queryClient.setQueryData<NewsInteractions>(queryKey, {
          ...previous,
          comments: [...previous.comments, optimisticComment],
        })
      }
      return { previous }
    },
    onError: (err, variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })

  return {
    interactions,
    isLoading,
    toggleLike: () => likeMutation.mutate(),
    addComment: (content: string) => commentMutation.mutate(content),
    isLiking: likeMutation.isPending,
    isCommenting: commentMutation.isPending,
  }
}
