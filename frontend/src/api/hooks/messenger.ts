/**
 * @fileoverview SSR-safe queryOptions factories for /messenger chat data.
 *
 * Wave 180 SW3 — extracted as a queryOptions factory mirroring the W129
 * (events.ts, news.ts), W130 (schedule.ts), W133 (users.ts), and W134 SW2
 * (sessions.ts) pattern. Closes W134 §Honesty #10 — reverses W161 SW2
 * by-design defer of /messenger Phase 5 SSR.
 *
 * Pre-W180 history:
 *  - W125-W149 SSR migration enabled 8 routes (/dashboard, /events × 2,
 *    /news × 2, /schedule, /profile, /settings) via per-route loaders.
 *  - /messenger × 2 stayed `ssr: false` per W161 SW2 explicit defer with
 *    3 architectural concerns: (a) query gate inconsistency in
 *    useMessengerController.ts:68; (b) privacy/cache scoping (chat list
 *    exposes user-private relationship state); (c) UX/value tradeoff
 *    (WebSocket-driven UX makes SSR LCP win marginal).
 *  - W180 plan reverses (a) via this factory + `enabled: !!user` gate.
 *  - W180 plan reverses (b) via Cache-Control: no-store + Vary: Cookie
 *    response headers injected in `frontend/src/server.ts` for /messenger
 *    paths (defensive privacy posture; browsers + intermediaries never
 *    cache SSR responses with per-user state).
 *  - W180 plan accepts (c) — `ssr: 'data-only'` annotation per W127 SW6
 *    pattern means SSR renders route SHELL but NO loader prefetch fires,
 *    so chat data still loads client-side post-hydration via React Query.
 *    LCP win is from shell render only (MainLayout + provider tree
 *    server-rendered into HTML stream — same pattern as /profile + /settings).
 *
 * Cache identity: queryKey tuples match pre-W180 inline keys used by
 * useMessengerController.ts + MessengerContext.tsx:
 *  - chats list: `["chats"]` (unchanged from line 69 pre-W180)
 *  - single chat: `["chats", chatId]` (unchanged from line 75)
 *  - messages: `["messages", chatId]` (unchanged from line 82)
 *
 * SSR cookie forwarding: when `ssr: 'data-only'` is annotated on the
 * route, this factory is NOT consumed by a loader (privacy posture per
 * W161 SW2 #2). Client-side React Query fires the actual chat/message
 * fetches post-hydration via `withCredentials: true` axios cookie chain.
 * The factory's `queryFn` would work in SSR context too (via W133 SW1
 * AsyncLocalStorage cookie forwarding), but we intentionally do not
 * prefetch chat data server-side — privacy gate.
 *
 * Usage:
 *
 * ```ts
 * // Hook (component-side consumer — useMessengerController.ts)
 * useQuery({
 *   ...chatsQueryOptions(),
 *   enabled: !!user,
 * })
 *
 * useQuery({
 *   ...chatQueryOptions(chatId),
 *   enabled: !!chatId && !chats.some((c) => c.id === chatId),
 * })
 *
 * useQuery({
 *   ...messagesQueryOptions(selectedChatId),
 *   enabled: !!selectedChatId,
 * })
 * ```
 */
import type { QueryFunctionContext } from "@tanstack/react-query"

import {
  chatApi,
  type Chat,
  type ChatsListResponse,
  type MessagesListResponse,
  type Reactor,
} from "@/api/chat"

// QueryKeys — preserve pre-W180 cache identity by matching the tuples
// already used inline in useMessengerController.ts (W161 SW2 baseline) +
// MessengerContext.tsx:66-70 (which already has the `enabled` gate that
// W180 brings to useMessengerController).

/**
 * QueryKey for the chat list (GET /chats). Stable across SSR + browser
 * paths. Pre-W180 inline shape preserved for cache identity.
 */
export const chatsQueryKey = ["chats"] as const
export type ChatsQueryKey = typeof chatsQueryKey

/**
 * QueryKey for a single chat by id (GET /chats/:id). Used by the detail
 * route + the useMessengerController fallback when activeChat isn't in
 * the list (e.g., direct URL navigation to a chat the user has access
 * to but hasn't paginated to yet).
 */
export const chatQueryKey = (chatId: string) => ["chats", chatId] as const
export type ChatQueryKey = ReturnType<typeof chatQueryKey>

/**
 * QueryKey for a chat's message list (GET /chats/:id/messages). Used by
 * ChatWindow + the active-chat selection effect in useMessengerController.
 */
export const messagesQueryKey = (chatId: string) => ["messages", chatId] as const
export type MessagesQueryKey = ReturnType<typeof messagesQueryKey>

// Wave 180 SW3 — kept in sync with pre-W180 inline useQuery defaults so the
// factory refactor is a pure code-shape change (no behavioural drift).
const QUERY_STALE_TIME_MS = 30_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Exponential backoff for flaky mobile connections (FIX-68-05; mirrors
 * W130 schedule.ts + W133 users.ts + W134 SW2 sessions.ts).
 */
const retryDelay = (attempt: number) => Math.min(1_000 * 2 ** attempt, 10_000)

/**
 * Wave 180 SW3 — pure factory for the `GET /chats` query.
 *
 * Used by `useMessengerController` (line 68 pre-W180; spread + enabled
 * gate post-W180). Matches MessengerContext.tsx:66-70 which already gates
 * its own chat-list query via `enabled: isAuth`. The factory itself does
 * NOT include an `enabled` gate — that's the consumer's responsibility
 * (mirrors W134 SW2 sessions.ts pattern: factory exports core options,
 * consumer adds `enabled: ...`).
 *
 * SSR-safety: queryFn delegates to `chatApi.getChats` (axios via
 * `@/api/client`). Under Node SSR (`ssr: 'data-only'` routes), this
 * factory would work via W133 SW1 cookie forwarding — but messenger
 * routes intentionally do NOT call `ensureQueryData(chatsQueryOptions())`
 * in their loaders (privacy posture).
 */
export const chatsQueryOptions = () => ({
  queryKey: chatsQueryKey,
  queryFn: async ({ signal }: QueryFunctionContext<ChatsQueryKey>): Promise<ChatsListResponse> => {
    // Pre-W180 useMessengerController called `chatApi.getChats()` without
    // signal. Wave 180 surfaces the AbortSignal via QueryFunctionContext for
    // cancellation parity with W134 SW2 sessions.ts pattern — but the
    // existing `chatApi.getChats` signature doesn't accept it. The signal
    // is reserved here for the future when chat.ts grows AbortSignal
    // support; React Query still aborts the in-flight query when the
    // component unmounts via its own internal cancellation pathway.
    void signal
    return chatApi.getChats()
  },
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})

/**
 * Wave 180 SW3 — pure factory for the `GET /chats/:id` query.
 *
 * Consumer (useMessengerController) adds an additional gate beyond `enabled:
 * !!chatId` to skip the fetch when the chat is already in the cached list:
 *
 * ```ts
 * useQuery({
 *   ...chatQueryOptions(chatId),
 *   enabled: !!chatId && !chats.some((c) => c.id === chatId),
 *   retry: false,
 * })
 * ```
 *
 * `retry: false` override in the consumer matches pre-W180 behaviour (line
 * 78 of useMessengerController.ts) — a chat-not-found should surface
 * quickly without exponential backoff. We expose retry: 2 default in the
 * factory because that's the codebase convention; consumers override.
 */
export const chatQueryOptions = (chatId: string | undefined) => ({
  queryKey: chatQueryKey(chatId ?? ""),
  queryFn: async ({ signal }: QueryFunctionContext<ChatQueryKey>): Promise<Chat> => {
    void signal
    if (!chatId) {
      // Defensive — `enabled: !!chatId` in the consumer prevents this from
      // firing, but if a caller forgets the gate this throws cleanly
      // rather than hitting `chatApi.getChat("")` and producing a 404.
      throw new Error("chatId required")
    }
    return chatApi.getChat(chatId)
  },
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})

/**
 * Wave 207 — QueryKey for the reactor list of one message+emoji
 * (GET /chats/:id/messages/:mid/reactions?emoji=). On-demand: fetched only when a
 * ReactionPill popover opens (hover desktop / long-press mobile), NOT bundled into
 * the message list. Keyed by all three so each emoji's reactor list caches
 * independently.
 */
export const reactorsQueryKey = (chatId: string, messageId: string, emoji: string) =>
  ["reactors", chatId, messageId, emoji] as const
export type ReactorsQueryKey = ReturnType<typeof reactorsQueryKey>

/**
 * Wave 207 — pure factory for one message+emoji's reactor list. The consumer
 * (ReactionPill) adds `enabled: isOpen && !!chatId` so the fetch only fires while
 * the popover is open. A self-toggle updates the count optimistically (separate
 * query key) but not this list — it self-heals on the next stale-open (staleTime
 * 30 s), acceptable for supplementary identity info.
 */
export const reactorsQueryOptions = (chatId: string, messageId: string, emoji: string) => ({
  queryKey: reactorsQueryKey(chatId, messageId, emoji),
  queryFn: async ({ signal }: QueryFunctionContext<ReactorsQueryKey>): Promise<Reactor[]> => {
    void signal
    return chatApi.getReactors(chatId, messageId, emoji)
  },
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})

/**
 * Wave 180 SW3 — pure factory for the `GET /chats/:id/messages` query.
 *
 * Used by useMessengerController (line 81 pre-W180; spread + enabled gate
 * post-W180). The consumer's existing `enabled: !!selectedChatId` gate is
 * preserved as-is.
 *
 * The pre-W180 queryFn had a defensive fallback returning
 * `{ items: [], has_more: false, next_cursor: null }` when chatId was
 * absent — this factory keeps the same behaviour for cache stability
 * (React Query would otherwise see undefined results and refetch eagerly).
 */
export const messagesQueryOptions = (chatId: string | null) => ({
  queryKey: messagesQueryKey(chatId ?? ""),
  queryFn: async ({
    signal,
  }: QueryFunctionContext<MessagesQueryKey>): Promise<MessagesListResponse> => {
    void signal
    if (!chatId) {
      // Defensive — `enabled: !!chatId` gates the fetch; this branch only
      // fires if a caller forgets the gate. Matches pre-W180 line 83-86
      // shape (return empty list instead of throwing).
      return { items: [], has_more: false, next_cursor: null }
    }
    return chatApi.getMessages(chatId)
  },
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})
