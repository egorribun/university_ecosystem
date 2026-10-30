import { useCallback } from "react"
import api, { fetchAnonymousNewsInteractions, isValidAnonymousNewsCursor } from "@/api/client"
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import i18n from "@/i18n/config"
import { useAnonymousReadMode } from "@/api/hooks/news"
import { captureSessionEpoch } from "@/stores/sessionEpoch"

// Temporary comments have no server ID until the interactions query reconciles.
export const OPTIMISTIC_COMMENT_ID_PREFIX = "optimistic-"

/** Comments per request; prefer opaque server cursors with legacy offset fallback. */
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
  next_cursor?: string | null
}

type NewsInteractionSummary = Pick<NewsInteractions, "likes_count" | "is_liked" | "comments_count">
// Optimistic inserts and deletes change the visible array, not the number of
// rows the server returned for this page. Keep that length with the page so
// a later request advances from the server offset rather than the UI count.
type InteractionPage = NewsInteractions & {
  serverCommentsLength?: number
  isSummarySeed?: boolean
}
type CommentPageParam = number | { cursor: string; requiresCursor: boolean }
type InteractionPages = InfiniteData<InteractionPage, CommentPageParam>
type MutationOwner = { ownsSession: () => boolean }

function requireCurrentSession(ownsSession: () => boolean) {
  if (!ownsSession()) throw new Error("News interaction session changed")
}

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

function nextCommentsPage(
  lastPage: InteractionPage,
  _allPages: InteractionPage[],
  lastPageParam: CommentPageParam
): CommentPageParam | undefined {
  if (Object.hasOwn(lastPage, "next_cursor")) {
    return lastPage.next_cursor
      ? { cursor: lastPage.next_cursor, requiresCursor: true }
      : undefined
  }
  // Only the initial probe may fall back when an older server omits cursors.
  // Numeric page parameters also preserve already-loaded legacy cache entries.
  const lastOffset = typeof lastPageParam === "number" ? lastPageParam : 0
  const serverLength =
    lastPage.serverCommentsLength ??
    lastPage.comments.filter((comment) => !comment.id.startsWith(OPTIMISTIC_COMMENT_ID_PREFIX))
      .length
  const loaded = lastOffset + serverLength
  const total = lastPage.comments_count ?? loaded
  return serverLength > 0 && loaded < total ? loaded : undefined
}

function mapPages(
  data: InteractionPages,
  update: (page: InteractionPage, isLastPage: boolean) => InteractionPage
): InteractionPages {
  return {
    ...data,
    pages: data.pages.map((page, index) => update(page, index === data.pages.length - 1)),
  }
}

interface NewsInteractionOptions {
  /**
   * Summary already known from the news payload. It is shown at once, but it
   * never counts as a loaded comment list: the comments are always requested.
   */
  initialData?: Partial<NewsInteractionSummary>
  /** `false` keeps the summary only (feed cards show counts and never open comments). */
  loadComments?: boolean
  /** Reuse the detail page's mode so its summary seed stays in the same cache partition. */
  anonymousRead?: boolean
  language?: string
}

export function useNewsInteraction(newsId: string, options: NewsInteractionOptions = {}) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { anonymous: inferredAnonymous } = useAnonymousReadMode()
  const anonymous = options.anonymousRead ?? inferredAnonymous
  const queryKey = anonymous
    ? (["news", newsId, "anonymous-interactions"] as const)
    : (["news", newsId, "interactions"] as const)
  const seed = options.initialData

  const interactionsQuery = useInfiniteQuery({
    queryKey,
    queryFn: async ({ pageParam, signal }) => {
      const pagination =
        typeof pageParam === "number" ? { offset: pageParam } : { cursor: pageParam.cursor }
      const cachedPages = queryClient.getQueryData<InteractionPages>(queryKey)?.pages
      const requiresCursor =
        (typeof pageParam !== "number" && pageParam.requiresCursor) ||
        cachedPages?.some((page) => Object.hasOwn(page, "next_cursor")) === true
      let interactions: NewsInteractions
      if (anonymous) {
        const response = await fetchAnonymousNewsInteractions({
          id: newsId,
          language: options.language ?? i18n.language,
          limit: NEWS_COMMENTS_PAGE_SIZE,
          ...pagination,
          signal,
        })
        if (!response.ok) {
          throw new Error(`News interactions request failed with status ${response.status}`)
        }
        interactions = (await response.json()) as NewsInteractions
      } else {
        const response = await api.get<NewsInteractions>(`/news/${newsId}/interactions`, {
          params: { limit: NEWS_COMMENTS_PAGE_SIZE, ...pagination },
          signal,
        })
        interactions = response.data
      }
      const hasCursor = Object.hasOwn(interactions, "next_cursor")
      if (
        (requiresCursor && !hasCursor) ||
        (hasCursor &&
          interactions.next_cursor !== null &&
          !isValidAnonymousNewsCursor(interactions.next_cursor))
      ) {
        throw new Error("News interactions cursor contract changed")
      }
      return {
        ...interactions,
        serverCommentsLength: interactions.comments.length,
        isSummarySeed: false,
      }
    },
    initialPageParam: { cursor: "start", requiresCursor: false } as CommentPageParam,
    getNextPageParam: nextCommentsPage,
    select: (data) => ({
      interactions: flattenInteractions(data),
      commentsLoaded: data.pages.length > 0 && data.pages[0]?.isSummarySeed !== true,
    }),
    enabled: options.loadComments ?? true,
    staleTime: 30_000, // 30s cache — optimistic updates handle local state immediately
    // The seed is stale on purpose: a detail page mounted after a feed card must
    // still fetch the comments, which the summary does not contain.
    initialData: seed
      ? {
          pages: [
            {
              likes_count: seed.likes_count ?? 0,
              is_liked: anonymous ? false : (seed.is_liked ?? false),
              comments: [],
              comments_count: seed.comments_count ?? 0,
              serverCommentsLength: 0,
              isSummarySeed: true,
            },
          ],
          pageParams: [{ cursor: "start", requiresCursor: false } as CommentPageParam],
        }
      : undefined,
    initialDataUpdatedAt: 0,
    // Optimistic comments and edits must not survive as confirmed account data
    // in a persisted query snapshot while their request is unresolved.
    meta: { persist: false },
  })
  const interactions = interactionsQuery.data?.interactions
  const commentsStatus: "ready" | "loading" | "error" = interactionsQuery.data?.commentsLoaded
    ? "ready"
    : interactionsQuery.isError
      ? "error"
      : "loading"
  const isLoading = interactionsQuery.isLoading
  const fetchNextPage = interactionsQuery.fetchNextPage
  const refetch = interactionsQuery.refetch
  const loadMoreComments = useCallback(() => {
    void fetchNextPage()
  }, [fetchNextPage])
  const retryComments = useCallback(() => {
    void refetch()
  }, [refetch])

  const likeMutation = useMutation({
    networkMode: "always",
    meta: { persist: false },
    mutationFn: async ({ ownsSession }: MutationOwner) => {
      // An ambiguous network failure cannot safely be retried without a
      // server-bound session and durable idempotency. Let it reject so the UI
      // rolls back and the user is not told an unowned operation was queued.
      requireCurrentSession(ownsSession)
      await api.post(`/news/${newsId}/like`)
    },
    onMutate: async ({ ownsSession }) => {
      if (!ownsSession()) return { previous: undefined, ownsSession }
      await queryClient.cancelQueries({ queryKey })
      if (!ownsSession()) return { previous: undefined, ownsSession }
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
      return { previous, ownsSession }
    },
    onError: (_err, _variables, context) => {
      if (context?.previous && context.ownsSession()) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: (_data, _error, _variables, context) => {
      if (context?.ownsSession()) void queryClient.invalidateQueries({ queryKey })
    },
  })

  const commentMutation = useMutation({
    networkMode: "always",
    meta: { persist: false },
    mutationFn: async ({ content, ownsSession }: MutationOwner & { content: string }) => {
      requireCurrentSession(ownsSession)
      const res = await api.post(`/news/${newsId}/comment`, { content })
      return res.data
    },
    onMutate: async ({ content, ownsSession }) => {
      if (!ownsSession()) return { previous: undefined, ownsSession }
      await queryClient.cancelQueries({ queryKey })
      if (!ownsSession()) return { previous: undefined, ownsSession }
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
      return { previous, ownsSession }
    },
    onError: (_err, _variables, context) => {
      if (context?.previous && context.ownsSession()) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: (_data, _error, _variables, context) => {
      if (context?.ownsSession()) void queryClient.invalidateQueries({ queryKey })
    },
  })

  const updateCommentMutation = useMutation({
    networkMode: "always",
    meta: { persist: false },
    mutationFn: async ({
      commentId,
      content,
      ownsSession,
    }: MutationOwner & { commentId: string; content: string }) => {
      requireCurrentSession(ownsSession)
      const res = await api.patch(`/news/comments/${commentId}`, { content })
      return res.data
    },
    onMutate: async ({ commentId, content, ownsSession }) => {
      if (!ownsSession()) return { previous: undefined, ownsSession }
      await queryClient.cancelQueries({ queryKey })
      if (!ownsSession()) return { previous: undefined, ownsSession }
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
      return { previous, ownsSession }
    },
    onError: (_err, _variables, context) => {
      if (context?.previous && context.ownsSession()) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: (_data, _error, _variables, context) => {
      if (context?.ownsSession()) void queryClient.invalidateQueries({ queryKey })
    },
  })

  const deleteCommentMutation = useMutation({
    networkMode: "always",
    meta: { persist: false },
    mutationFn: async ({ commentId, ownsSession }: MutationOwner & { commentId: string }) => {
      requireCurrentSession(ownsSession)
      await api.delete(`/news/comments/${commentId}`)
    },
    onMutate: async ({ commentId, ownsSession }) => {
      if (!ownsSession()) return { previous: undefined, ownsSession }
      await queryClient.cancelQueries({ queryKey })
      if (!ownsSession()) return { previous: undefined, ownsSession }
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
      return { previous, ownsSession }
    },
    onError: (_err, _variables, context) => {
      if (context?.previous && context.ownsSession()) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onSettled: (_data, _error, _variables, context) => {
      if (context?.ownsSession()) void queryClient.invalidateQueries({ queryKey })
    },
  })

  const likeMutate = likeMutation.mutate
  const likeMutateAsync = likeMutation.mutateAsync
  const commentMutateAsync = commentMutation.mutateAsync
  const updateCommentMutate = updateCommentMutation.mutate
  const updateCommentMutateAsync = updateCommentMutation.mutateAsync
  const deleteCommentMutate = deleteCommentMutation.mutate
  const deleteCommentMutateAsync = deleteCommentMutation.mutateAsync

  return {
    interactions,
    isLoading,
    commentsStatus,
    isRetryingComments: interactionsQuery.isFetching,
    retryComments,
    hasMoreComments: interactionsQuery.hasNextPage,
    isLoadingMoreComments: interactionsQuery.isFetchingNextPage,
    isLoadingMoreCommentsError: interactionsQuery.isFetchNextPageError,
    loadMoreComments,
    toggleLike: useCallback(() => likeMutate({ ownsSession: captureSessionEpoch() }), [likeMutate]),
    toggleLikeAsync: useCallback(
      () => likeMutateAsync({ ownsSession: captureSessionEpoch() }),
      [likeMutateAsync]
    ),
    addComment: useCallback(
      (content: string) => commentMutateAsync({ content, ownsSession: captureSessionEpoch() }),
      [commentMutateAsync]
    ),
    updateComment: useCallback(
      (commentId: string, content: string) =>
        updateCommentMutate({ commentId, content, ownsSession: captureSessionEpoch() }),
      [updateCommentMutate]
    ),
    updateCommentAsync: useCallback(
      (commentId: string, content: string) =>
        updateCommentMutateAsync({ commentId, content, ownsSession: captureSessionEpoch() }),
      [updateCommentMutateAsync]
    ),
    deleteComment: useCallback(
      (commentId: string) => deleteCommentMutate({ commentId, ownsSession: captureSessionEpoch() }),
      [deleteCommentMutate]
    ),
    deleteCommentAsync: useCallback(
      (commentId: string) =>
        deleteCommentMutateAsync({ commentId, ownsSession: captureSessionEpoch() }),
      [deleteCommentMutateAsync]
    ),
    isLiking: likeMutation.isPending,
    isCommenting: commentMutation.isPending,
    isUpdatingComment: updateCommentMutation.isPending,
    isDeletingComment: deleteCommentMutation.isPending,
  }
}
