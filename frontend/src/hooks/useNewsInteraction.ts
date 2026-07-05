import { useCallback } from "react"
import api from "@/api/client"
import { isAxiosError } from "axios"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { logWarning } from "@/app/logger"

const NEWS_INTERACTION_STORE = "pending-news-interactions"
const NEWS_INTERACTION_SYNC_TAG = "news-interaction:sync"
const CLICK_DB_NAME = "notification-interactions"
const CLICK_DB_VERSION = 3

export type NewsComment = {
  id: string
  content: string
  user_id: string
  user_name: string
  created_at: string
}

export type NewsInteractions = {
  likes_count: number
  is_liked: boolean
  comments: NewsComment[]
  comments_count?: number
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(CLICK_DB_NAME, CLICK_DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains("pending-navigations")) {
        db.createObjectStore("pending-navigations", { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains("pending-reports")) {
        db.createObjectStore("pending-reports", { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(NEWS_INTERACTION_STORE)) {
        db.createObjectStore(NEWS_INTERACTION_STORE, { keyPath: "id", autoIncrement: true })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function queueInteraction(url: string, payload: unknown, method = "POST") {
  const db = await openDatabase()
  const tx = db.transaction(NEWS_INTERACTION_STORE, "readwrite")
  const store = tx.objectStore(NEWS_INTERACTION_STORE)
  await new Promise<void>((resolve, reject) => {
    const req = store.add({ url, payload, method, timestamp: Date.now() })
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })

  // Trigger SW sync if possible
  if ("serviceWorker" in navigator && "SyncManager" in window) {
    const registration = await navigator.serviceWorker.ready
    try {
      await registration.sync.register(NEWS_INTERACTION_SYNC_TAG)
    } catch (e) {
      logWarning("Failed to register background sync", { error: e })
    }
  }
}

/**
 * Shared error handler for news interaction mutations.
 * - 401 → rethrow (auth interceptor handles it)
 * - Offline/network error → queue to IndexedDB for SW sync
 * - Otherwise → rethrow
 */
async function handleMutationError(
  error: unknown,
  offlineUrl: string,
  offlinePayload: unknown = {},
  offlineMethod = "POST"
): Promise<{ isOfflineStore: true }> {
  if (isAxiosError(error) && error.response?.status === 401) throw error

  const isNetworkError =
    !navigator.onLine ||
    (error &&
      typeof error === "object" &&
      (("message" in error && (error as { message?: string }).message === "Network Error") ||
        ("code" in error && (error as { code?: string }).code === "ERR_NETWORK") ||
        (isAxiosError(error) &&
          (error.message === "Network Error" || error.code === "ERR_NETWORK"))))

  if (isNetworkError) {
    await queueInteraction(offlineUrl, offlinePayload, offlineMethod)
    return { isOfflineStore: true }
  }

  throw error
}

interface NewsInteractionOptions {
  initialData?: Partial<NewsInteractions>
}

export function useNewsInteraction(newsId: string, options: NewsInteractionOptions = {}) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const queryKey = ["news", newsId, "interactions"]

  const { data: interactions, isLoading } = useQuery<NewsInteractions>({
    queryKey,
    queryFn: async () => {
      const res = await api.get<NewsInteractions>(`/news/${newsId}/interactions`)
      return res.data
    },
    staleTime: 30_000, // 30s cache — optimistic updates handle local state immediately
    initialData: options.initialData
      ? {
          likes_count: options.initialData.likes_count ?? 0,
          is_liked: options.initialData.is_liked ?? false,
          comments: options.initialData.comments ?? [],
          comments_count: options.initialData.comments_count ?? 0,
        }
      : undefined,
  })

  const likeMutation = useMutation({
    mutationFn: async () => {
      try {
        await api.post(`/news/${newsId}/like`)
      } catch (error: unknown) {
        return handleMutationError(error, `/api/v1/news/${newsId}/like`)
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
    onError: (_err, _variables, context) => {
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
      } catch (error: unknown) {
        return handleMutationError(error, `/api/v1/news/${newsId}/comment`, { content })
      }
    },
    onMutate: async (content) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<NewsInteractions>(queryKey)
      if (previous) {
        // Optimistic comment
        const optimisticComment: NewsComment = {
          id: "optimistic-" + Date.now(),
          content,
          user_id: user?.id ?? "",
          user_name: user?.full_name ?? "You",
          created_at: new Date().toISOString(),
        }
        queryClient.setQueryData<NewsInteractions>(queryKey, {
          ...previous,
          comments: [...previous.comments, optimisticComment],
          comments_count: (previous.comments_count ?? previous.comments.length) + 1,
        })
      }
      return { previous }
    },
    onError: (_err, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })

  const updateCommentMutation = useMutation({
    mutationFn: async ({ commentId, content }: { commentId: string; content: string }) => {
      try {
        const res = await api.patch(`/news/comments/${commentId}`, { content })
        return res.data
      } catch (error: unknown) {
        return handleMutationError(
          error,
          `/api/v1/news/comments/${commentId}`,
          { content },
          "PATCH"
        )
      }
    },
    onMutate: async ({ commentId, content }) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<NewsInteractions>(queryKey)
      if (previous) {
        queryClient.setQueryData<NewsInteractions>(queryKey, {
          ...previous,
          comments: previous.comments.map((c) => (c.id === commentId ? { ...c, content } : c)),
        })
      }
      return { previous }
    },
    onError: (_err, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })

  const deleteCommentMutation = useMutation({
    mutationFn: async (commentId: string) => {
      try {
        await api.delete(`/news/comments/${commentId}`)
      } catch (error: unknown) {
        return handleMutationError(error, `/api/v1/news/comments/${commentId}`, {}, "DELETE")
      }
    },
    onMutate: async (commentId) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<NewsInteractions>(queryKey)
      if (previous) {
        queryClient.setQueryData<NewsInteractions>(queryKey, {
          ...previous,
          comments: previous.comments.filter((c) => c.id !== commentId),
          comments_count: (previous.comments_count ?? previous.comments.length) - 1,
        })
      }
      return { previous }
    },
    onError: (_err, _variables, context) => {
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
    toggleLike: useCallback(() => likeMutation.mutate(), [likeMutation]),
    addComment: useCallback(
      (content: string) => commentMutation.mutate(content),
      [commentMutation]
    ),
    updateComment: useCallback(
      (commentId: string, content: string) => updateCommentMutation.mutate({ commentId, content }),
      [updateCommentMutation]
    ),
    deleteComment: useCallback(
      (commentId: string) => deleteCommentMutation.mutate(commentId),
      [deleteCommentMutation]
    ),
    isLiking: likeMutation.isPending,
    isCommenting: commentMutation.isPending,
    isUpdatingComment: updateCommentMutation.isPending,
    isDeletingComment: deleteCommentMutation.isPending,
  }
}
