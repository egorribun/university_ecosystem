import { useCallback } from "react"
import api from "@/api/client"
import { isAxiosError } from "axios"
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { logWarning } from "@/app/logger"
import {
  NOTIFICATION_INTERACTIONS_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION,
} from "@/constants/notificationInteractionsDb"

const NEWS_INTERACTION_STORE = "pending-news-interactions"
const NEWS_INTERACTION_SYNC_TAG = "news-interaction:sync"

// Temporary comments have no server ID until the interactions query reconciles.
export const OPTIMISTIC_COMMENT_ID_PREFIX = "optimistic-"

/** Comments per /interactions request. The backend pages comments by offset, oldest first. */
export const NEWS_COMMENTS_PAGE_SIZE = 20

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

type NewsInteractionSummary = Pick<NewsInteractions, "likes_count" | "is_liked" | "comments_count">
type InteractionPages = InfiniteData<NewsInteractions, number>

// Each page repeats the summary; only the comments differ between pages.
function flattenInteractions(data: InteractionPages): NewsInteractions {
  const first = data.pages[0]
  return {
    likes_count: first?.likes_count ?? 0,
    is_liked: first?.is_liked ?? false,
    comments: data.pages.flatMap((page) => page.comments),
    comments_count: first?.comments_count,
  }
}

function nextCommentsOffset(lastPage: NewsInteractions, allPages: NewsInteractions[]) {
  const loaded = allPages.reduce((total, page) => total + page.comments.length, 0)
  const total = lastPage.comments_count ?? loaded
  return lastPage.comments.length > 0 && loaded < total ? loaded : undefined
}

function mapPages(
  data: InteractionPages,
  update: (page: NewsInteractions, isLastPage: boolean) => NewsInteractions
): InteractionPages {
  return {
    ...data,
    pages: data.pages.map((page, index) => update(page, index === data.pages.length - 1)),
  }
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(
      NOTIFICATION_INTERACTIONS_DB_NAME,
      NOTIFICATION_INTERACTIONS_DB_VERSION
    )
    request.onupgradeneeded = () => {
      // Mirror the service worker's schema (src/sw/offline.ts). If the page creates
      // this version first, the worker never upgrades it, so every store it reads
      // must exist here too.
      const db = request.result
      if (!db.objectStoreNames.contains("pending-navigations")) {
        db.createObjectStore("pending-navigations", { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains("pending-reports")) {
        db.createObjectStore("pending-reports", { keyPath: "id", autoIncrement: true }).createIndex(
          "dedupeKey",
          "dedupeKey",
          { unique: false }
        )
      }
      if (!db.objectStoreNames.contains(NEWS_INTERACTION_STORE)) {
        db.createObjectStore(NEWS_INTERACTION_STORE, { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains("pending-mutations")) {
        const mutations = db.createObjectStore("pending-mutations", {
          keyPath: "id",
          autoIncrement: true,
        })
        mutations.createIndex("mutationId", "mutationId", { unique: true })
        mutations.createIndex("category", "category", { unique: false })
        mutations.createIndex("dedupeKey", "dedupeKey", { unique: false })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function queueInteraction(url: string, payload: unknown, method: string) {
  const db = await openDatabase()
  try {
    const tx = db.transaction(NEWS_INTERACTION_STORE, "readwrite")
    const store = tx.objectStore(NEWS_INTERACTION_STORE)
    await new Promise<void>((resolve, reject) => {
      const req = store.add({ url, payload, method, timestamp: Date.now() })
      req.onsuccess = () => resolve()
      req.onerror = () => reject(req.error)
    })
  } finally {
    // Queue writes are short-lived. Close the connection after the request
    // settles so repeated offline interactions cannot accumulate handles and
    // block IndexedDB upgrades/deletion in long-lived browser sessions.
    db.close()
  }

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
  /**
   * Summary already known from the news payload. It is shown at once, but it
   * never counts as a loaded comment list: the comments are always requested.
   */
  initialData?: Partial<NewsInteractionSummary>
  /** `false` keeps the summary only (feed cards show counts and never open comments). */
  loadComments?: boolean
}

export function useNewsInteraction(newsId: string, options: NewsInteractionOptions = {}) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const queryKey = ["news", newsId, "interactions"]
  const seed = options.initialData

  const interactionsQuery = useInfiniteQuery({
    queryKey,
    queryFn: async ({ pageParam }) => {
      const res = await api.get<NewsInteractions>(`/news/${newsId}/interactions`, {
        params: { limit: NEWS_COMMENTS_PAGE_SIZE, offset: pageParam },
      })
      return res.data
    },
    initialPageParam: 0,
    getNextPageParam: nextCommentsOffset,
    select: flattenInteractions,
    enabled: options.loadComments ?? true,
    staleTime: 30_000, // 30s cache — optimistic updates handle local state immediately
    // The seed is stale on purpose: a detail page mounted after a feed card must
    // still fetch the comments, which the summary does not contain.
    initialData: seed
      ? {
          pages: [
            {
              likes_count: seed.likes_count ?? 0,
              is_liked: seed.is_liked ?? false,
              comments: [],
              comments_count: seed.comments_count ?? 0,
            },
          ],
          pageParams: [0],
        }
      : undefined,
    initialDataUpdatedAt: 0,
  })
  const interactions = interactionsQuery.data
  const isLoading = interactionsQuery.isLoading
  const fetchNextPage = interactionsQuery.fetchNextPage
  const loadMoreComments = useCallback(() => {
    void fetchNextPage()
  }, [fetchNextPage])

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
      const previous = queryClient.getQueryData<InteractionPages>(queryKey)
      if (previous) {
        queryClient.setQueryData<InteractionPages>(
          queryKey,
          mapPages(previous, (page) => ({
            ...page,
            is_liked: !page.is_liked,
            likes_count: page.is_liked ? page.likes_count - 1 : page.likes_count + 1,
          }))
        )
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
      const previous = queryClient.getQueryData<InteractionPages>(queryKey)
      if (previous) {
        // Optimistic comment
        const optimisticComment: NewsComment = {
          id: OPTIMISTIC_COMMENT_ID_PREFIX + Date.now(),
          content,
          user_id: user?.id ?? "",
          user_name: user?.full_name ?? "You",
          created_at: new Date().toISOString(),
        }
        const loaded = flattenInteractions(previous).comments.length
        queryClient.setQueryData<InteractionPages>(
          queryKey,
          mapPages(previous, (page, isLastPage) => ({
            ...page,
            comments: isLastPage ? [...page.comments, optimisticComment] : page.comments,
            comments_count: (page.comments_count ?? loaded) + 1,
          }))
        )
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
      const previous = queryClient.getQueryData<InteractionPages>(queryKey)
      if (previous) {
        queryClient.setQueryData<InteractionPages>(
          queryKey,
          mapPages(previous, (page) => ({
            ...page,
            comments: page.comments.map((c) => (c.id === commentId ? { ...c, content } : c)),
          }))
        )
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
      const previous = queryClient.getQueryData<InteractionPages>(queryKey)
      if (previous) {
        const loaded = flattenInteractions(previous).comments.length
        queryClient.setQueryData<InteractionPages>(
          queryKey,
          mapPages(previous, (page) => ({
            ...page,
            comments: page.comments.filter((c) => c.id !== commentId),
            comments_count: (page.comments_count ?? loaded) - 1,
          }))
        )
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

  const likeMutate = likeMutation.mutate
  const commentMutateAsync = commentMutation.mutateAsync
  const updateCommentMutate = updateCommentMutation.mutate
  const deleteCommentMutate = deleteCommentMutation.mutate

  return {
    interactions,
    isLoading,
    hasMoreComments: interactionsQuery.hasNextPage,
    isLoadingMoreComments: interactionsQuery.isFetchingNextPage,
    loadMoreComments,
    toggleLike: useCallback(() => likeMutate(), [likeMutate]),
    addComment: useCallback((content: string) => commentMutateAsync(content), [commentMutateAsync]),
    updateComment: useCallback(
      (commentId: string, content: string) => updateCommentMutate({ commentId, content }),
      [updateCommentMutate]
    ),
    deleteComment: useCallback(
      (commentId: string) => deleteCommentMutate(commentId),
      [deleteCommentMutate]
    ),
    isLiking: likeMutation.isPending,
    isCommenting: commentMutation.isPending,
    isUpdatingComment: updateCommentMutation.isPending,
    isDeletingComment: deleteCommentMutation.isPending,
  }
}
