import { memo, useRef, useEffect, useMemo, useState } from "react"
import { m } from "framer-motion" // Removed AnimatePresence, LayoutGroup as they are not used
import useMediaQuery from "@/hooks/useMediaQuery"
import {
  ArrowDown,
  File,
  Forward,
  Check,
  CheckCheck,
  MessageCircleHeart,
  Pencil,
  Reply,
  RotateCcw,
  SearchX,
  SmilePlus,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { sanitizeUrl } from "@/utils/media"
import { useDebounced } from "@/hooks/useDebounced"
import { Message } from "./types"
import { ReactionPill } from "./ReactionPill"

interface ChatWindowProps {
  messages: Message[]
  /**
   * Wave 184 SW1 (Path A) — search query threaded from ChatArea.
   * When non-empty, ChatWindow filters messages (case-insensitive substring
   * match on `message.text`) and renders a "no search match" empty state if
   * the filtered set is empty. Debouncing happens INSIDE ChatWindow via
   * `useDebounced(searchQuery, "search")` (200ms, PERF-23-04 search preset)
   * to keep the filter cost off the per-keystroke render path.
   * Pre-W184 the ChatArea search input was styled (W183 SW2 matte-input)
   * but non-functional — typing produced no filtering.
   */
  searchQuery?: string
  /**
   * Wave 184 SW1 (Path A) — clear-search callback. When the user has typed
   * a query that filters to zero matches, the search-empty empty state
   * renders a "Clear search" button that invokes this callback. Mirrors
   * the W183 SW1 ContactList search-empty pattern (clears query but keeps
   * the search input mounted so the user can type a new query immediately).
   */
  onClearSearch?: () => void
  /**
   * Wave 184 SW2 (Path B) — messages query loading flag lifted from
   * useMessengerController via ChatArea. When true, renders 6 skeleton
   * message bubbles (h-[80px] alternating left/right alignment matching
   * real bubble dimensions per W184 plan risk #4) BEFORE checking
   * messages.length === 0. Prevents the W183 SW5 "Say hi" empty state
   * from flashing briefly during the initial message history fetch.
   * Uses `.messenger-skeleton` shimmer class from W181 SW1.
   */
  isLoading?: boolean
  /**
   * Wave 184 SW3 (Path B) — messages query error flag. When true,
   * renders a fetch-failure empty state with Retry CTA BEFORE the
   * no-messages-yet branch. Distinguishes "new chat" from "network error".
   */
  isError?: boolean
  /**
   * Wave 184 SW3 (Path B) — retry callback wired to React Query's
   * `refetch()`. Invoked by the Retry button inside the error empty state.
   */
  onRetry?: () => void
  /**
   * Wave 205 SW6 — inline message edit + soft-delete, threaded from
   * useMessengerController via ChatArea. `editingMessageId` is the id of the
   * message currently being edited inline (null = none); when it matches a
   * rendered own-message, that bubble swaps its content `<p>` for a textarea
   * bound to `editingMessageContent` (updated via `onEditingContentChange`).
   * `onEditMessage(id, currentText)` opens the editor (seeds the textarea);
   * `onSaveEdit(id)` commits (the controller closes the editor + fires the
   * optimistic PATCH mutation); `onCancelEdit()` discards. `onDeleteMessage(id)`
   * opens the confirm dialog → soft-delete. All optional so the component
   * still renders standalone in tests/storybook without the messenger wiring.
   */
  editingMessageId?: string | null
  editingMessageContent?: string
  onEditingContentChange?: (content: string) => void
  onEditMessage?: (messageId: string, currentText: string) => void
  onSaveEdit?: (messageId: string) => void
  onCancelEdit?: () => void
  onDeleteMessage?: (messageId: string) => void
  /**
   * Wave 206 — toggle an emoji reaction on a message (any participant, any
   * message). Threaded from useMessengerController via ChatArea. Optional so
   * ChatWindow still renders standalone in tests/storybook: existing reaction
   * pills display read-only, and the "+react" affordance + picker are hidden.
   */
  onToggleReaction?: (messageId: string, emoji: string) => void
  /**
   * Wave 207 — start replying to a message (rendered on ALL bubbles, not just
   * own). Threaded from useMessengerController via ChatArea. Optional so
   * ChatWindow renders standalone in tests/storybook (the reply affordance is
   * hidden without it).
   */
  onStartReply?: (messageId: string) => void
  /**
   * Wave 211 — forward a message into another chat (rendered on ALL bubbles,
   * like reply). Threaded from useMessengerController via ChatArea; opens the
   * ForwardModal destination picker. Optional so ChatWindow renders standalone
   * in tests/storybook (the forward affordance is hidden without it).
   */
  onForward?: (messageId: string) => void
  /**
   * Wave 207 — selected chat id, threaded so each ReactionPill can fetch its
   * reactor-list ("who reacted") on-demand. Optional: without it the reactor
   * query is disabled (the pill still renders + toggles).
   */
  chatId?: string
  /** Whether the server has an older cursor page available. */
  hasMore?: boolean
  /** Prepends the next older cursor page to the message cache. */
  onLoadOlder?: () => void | Promise<void>
  /** Disables duplicate cursor requests while an older page is loading. */
  isLoadingOlder?: boolean
  /** Keeps history-loading failures separate from the initial history error. */
  olderMessagesError?: boolean
}

// Wave 206 — fixed quick-reaction set (no emoji-picker dependency). Module-level
// const per W202 SW1 hoist convention.
const REACTION_EMOJIS = ["👍", "❤️", "😂", "😮", "😢"] as const

// Wave 184 SW2 (Path B) — skeleton bubble count. 6 alternating left/right
// bubbles fills the chat viewport without being visually overwhelming.
const SKELETON_BUBBLE_COUNT = 6

/** Stable React identity for loading rows (keeps reconciliation deterministic). */
export const getMessageSkeletonKey = (index: number): string => `message-skeleton-${index}`

/**
 * Rows only animate when they are newly appended to the unfiltered history.
 * Keeping this policy pure makes the virtualised render contract testable
 * without depending on effect scheduling in a browser test runner.
 */
export const shouldAnimateMessageEntrance = (params: {
  prefersReducedMotion: boolean
  isSearchActive: boolean
  index: number
  animateFromIndex: number
}): boolean =>
  !params.prefersReducedMotion && !params.isSearchActive && params.index >= params.animateFromIndex

export const getMessageEntranceMotion = (animateEntrance: boolean) => ({
  initial: animateEntrance ? { opacity: 0, y: 10, scale: 0.95 } : false,
  animate: { opacity: 1, y: 0, scale: 1 },
  transition: animateEntrance
    ? { duration: 0.3, ease: [0.22, 1, 0.36, 1] as const }
    : { duration: 0 },
})

// Wave 208 SW4 — show the scroll-to-bottom FAB once the user has scrolled this
// many px up from the bottom. Module-level per W202 SW1 hoist convention.
const SCROLL_FAB_THRESHOLD = 240

export const ChatWindow = memo(function ChatWindow({
  messages,
  searchQuery = "",
  onClearSearch,
  isLoading = false,
  isError = false,
  onRetry,
  editingMessageId = null,
  editingMessageContent = "",
  onEditingContentChange,
  onEditMessage,
  onSaveEdit,
  onCancelEdit,
  onDeleteMessage,
  onToggleReaction,
  onStartReply,
  onForward,
  chatId,
  hasMore = false,
  onLoadOlder,
  isLoadingOlder = false,
  olderMessagesError = false,
}: ChatWindowProps) {
  const { t } = useTranslation()
  // Optional controller callbacks are intentionally normalised once per
  // render.  Event handlers must remain total when ChatWindow is used in
  // Storybook/standalone contexts; keeping the no-op boundary outside JSX
  // also makes every interaction deterministic for keyboard and pointer input.
  const handleEditingContentChange = onEditingContentChange ?? (() => undefined)
  const handleEditMessage = onEditMessage ?? (() => undefined)
  const handleSaveEdit = onSaveEdit ?? (() => undefined)
  const handleCancelEdit = onCancelEdit ?? (() => undefined)
  const handleDeleteMessage = onDeleteMessage ?? (() => undefined)
  const handleToggleReaction = onToggleReaction ?? (() => undefined)
  // Wave 206 — which message's emoji picker is open (null = none). The "+react"
  // affordance toggles it; selecting an emoji or clicking outside / Escape closes.
  const [reactionPickerForId, setReactionPickerForId] = useState<string | null>(null)
  // Wave 181 SW3 — useReducedMotion guard. Without this, virtualized message
  // bubbles fade+scale in on every scroll-into-view event, which becomes
  // disorienting motion for reduced-motion users.
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const containerRef = useRef<HTMLDivElement>(null)

  // Wave 184 SW1 (Path A) — debounce the search query so the per-keystroke
  // render does NOT re-filter the message array. 200ms via "search" preset
  // (PERF-23-04) matches ContactList search latency expectations.
  const debouncedSearchQuery = useDebounced(searchQuery, "search")
  const trimmedQuery = debouncedSearchQuery.trim()
  const isSearchActive = trimmedQuery.length > 0

  // Wave 184 SW1 (Path A) — filtered messages array. CRITICAL: this MUST
  // run BEFORE the virtualizer length pass below (per W184 plan risk #1
  // "filter messages BEFORE virtualizer length, not after"). If the
  // virtualizer were initialized with `messages.length` and then the
  // render mapped `filteredMessages[virtualRow.index]`, indices would
  // misalign and most rows would render as nulls. Both virtualizer AND
  // render iteration use `filteredMessages` from this single source.
  const filteredMessages = useMemo(() => {
    if (!isSearchActive) return messages
    const needle = trimmedQuery.toLowerCase()
    return messages.filter((message) => message.text.toLowerCase().includes(needle))
  }, [messages, trimmedQuery, isSearchActive])

  const virtualizer = useVirtualizer({
    count: filteredMessages.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 80,
    // Message identity, rather than an array index, lets Virtual Core retain
    // measurements and the visible anchor when an older cursor page is
    // prepended. The installed virtual-core 3.17.7 supports end anchoring and
    // follows appends only if the viewport was already at the end.
    getItemKey: (index) => filteredMessages[index]!.id,
    anchorTo: "end",
    followOnAppend: "auto",
    scrollEndThreshold: 48,
    overscan: 5,
  })

  const didInitialScrollRef = useRef(false)

  // Wave 202 SW6 — animate ONLY newly-appended messages, not every virtualized
  // row that scrolls back into view (pre-W202 each remount re-fired the entrance
  // = disorienting motion + needless work). `animateFromIndex` = the boundary
  // from which rows count as "new"; rows below it render `initial={false}`
  // (instant, no entrance). Init to Infinity so the first populated render (e.g.
  // loaded history) never stampede-animates; the auto-scroll effect bumps it to
  // the new length after each non-empty length change — which runs AFTER the
  // new-message render, so at render time it still equals the previous length =
  // exactly the just-appended tail. State (not a ref) is safe to read in render
  // under React Compiler; the lifecycle refs are touched solely in effects.
  const [animateFromIndex, setAnimateFromIndex] = useState(Number.POSITIVE_INFINITY)

  // Wave 208 SW4 — scroll-to-bottom FAB visibility. State (not a ref) → safe to
  // read in render under the React Compiler; the scroll position is read only
  // inside the listener's handler below (ref access in a handler, never during
  // render — same discipline as animateFromIndex). The FAB appears once the
  // user scrolls > SCROLL_FAB_THRESHOLD px up from the bottom and hides when
  // they return to (or auto-scroll back to) the latest message.
  const [showJumpButton, setShowJumpButton] = useState(false)

  // Scroll once when history first arrives. Subsequent append/prepend behavior
  // belongs to Virtual Core: followOnAppend keeps a reader at the end only when
  // they were already there, while anchorTo + stable keys preserve the visible
  // item when older history is prepended.
  useEffect(() => {
    const nextLength = messages.length
    if (nextLength === 0) {
      didInitialScrollRef.current = false
    } else {
      if (!isSearchActive && !didInitialScrollRef.current) {
        virtualizer.scrollToIndex(nextLength - 1, { align: "end", behavior: "auto" })
        didInitialScrollRef.current = true
      }
      // The preceding render sees the prior boundary, so only an appended tail
      // animates. Always re-base after any non-empty length change: this prevents
      // messages incorporated during search from replaying when search closes,
      // and lets a later append animate correctly after history contracts.
      setAnimateFromIndex(nextLength)
    }
  }, [messages.length, isSearchActive, virtualizer])

  // Wave 208 SW4 — toggle the scroll-to-bottom FAB based on scroll position.
  // The scroll metrics are read inside the handler (ref access in a handler is
  // allowed; never during render — same discipline as animateFromIndex). Only
  // the main render has a scrollable list; the early-return branches (loading /
  // error / empty / search-empty) mount a non-scrolling containerRef div, so we
  // skip + force the FAB hidden there. The guard reads isLoading/isError/length
  // so they are genuine deps → the listener re-binds to the live scroll element
  // whenever the rendered branch changes. Passive + cleaned up on unmount/re-run.
  useEffect(() => {
    const el = containerRef.current
    if (!el || isLoading || isError || filteredMessages.length === 0) {
      setShowJumpButton(false)
      return
    }
    const updateVisibility = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      setShowJumpButton(distanceFromBottom > SCROLL_FAB_THRESHOLD)
    }
    updateVisibility()
    el.addEventListener("scroll", updateVisibility, { passive: true })
    return () => el.removeEventListener("scroll", updateVisibility)
  }, [filteredMessages.length, isLoading, isError])

  // Wave 206 — close the emoji picker on outside click / Escape. The +react
  // button + picker bar are tagged data-reaction-ui; a mousedown anywhere else
  // closes (the listener is only attached while a picker is open, so the +react
  // toggle itself — guarded by closest('[data-reaction-ui]') — still works).
  useEffect(() => {
    if (!reactionPickerForId) return
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target
      if (target instanceof Element && target.closest("[data-reaction-ui]")) return
      setReactionPickerForId(null)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setReactionPickerForId(null)
    }
    document.addEventListener("mousedown", onMouseDown)
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("mousedown", onMouseDown)
      document.removeEventListener("keydown", onKeyDown)
    }
  }, [reactionPickerForId])

  // Wave 184 SW3 (Path B) — fetch-failure empty state. Order matters:
  // must come AFTER isLoading (so a transient error during refetch
  // doesn't flash the error banner while the spinner should win) but
  // BEFORE the no-messages-yet branch (so network errors don't disguise
  // themselves as "Say hi" UX). Mirrors ContactList isError pattern
  // (W184 SW3) for visual consistency: TriangleAlert + matte card +
  // Retry CTA wired to React Query's refetch().
  if (isError) {
    return (
      <div
        ref={containerRef}
        role="alert"
        aria-live="assertive"
        aria-label={t("messenger:aria.messageList")}
        className="messenger-chat-area flex flex-1 flex-col items-center justify-center px-6 py-10 text-center"
      >
        <m.div
          initial={prefersReducedMotion ? false : { scale: 0.92, opacity: 0, y: 8 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const }
          }
          className="flex w-full max-w-[24rem] flex-col items-center"
        >
          <div
            className="messenger-card-matte mb-5 flex size-16 items-center justify-center"
            style={{ background: "var(--messenger-card-bg)" }}
          >
            <TriangleAlert
              className="size-8 text-(--color-violet-500)"
              style={{ opacity: "var(--opacity-strong)" }}
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </div>
          <h3 className="sf-pro mb-2 text-base font-bold leading-tight text-(--text-primary)">
            {t("messenger:error.failedToLoadMessages")}
          </h3>
          <p className="mb-6 text-sm leading-relaxed text-(--text-secondary)">
            {t("messenger:error.failedToLoadMessagesHint")}
          </p>
          {onRetry && (
            <m.button
              type="button"
              whileHover={prefersReducedMotion ? undefined : { scale: 1.04 }}
              whileTap={prefersReducedMotion ? undefined : { scale: 0.96 }}
              onClick={onRetry}
              className="messenger-send-btn inline-flex min-h-[44px] items-center gap-2 rounded-full px-5 text-sm font-semibold text-(--text-inverse) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
            >
              <RotateCcw className="size-4" strokeWidth={2.5} aria-hidden="true" />
              <span>{t("messenger:error.retry")}</span>
            </m.button>
          )}
        </m.div>
      </div>
    )
  }

  // Wave 184 SW2 (Path B) — loading skeleton state. Rendered when the
  // messages query is in-flight (initial fetch on chat selection). Must
  // come BEFORE the no-messages-yet branch so an empty cache doesn't
  // briefly flash "Say hi" before the real messages arrive. 6 alternating
  // left/right bubble skeletons matching real bubble dimensions
  // (h-[80px] estimate per W184 plan risk #4 — skeleton heights must
  // match real rows to prevent CLS shift on load completion).
  if (isLoading) {
    return (
      <div
        ref={containerRef}
        role="status"
        aria-live="polite"
        aria-label={t("messenger:loading.messages")}
        className="messenger-chat-area flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar"
      >
        <div className="flex flex-col gap-3">
          {Array.from({ length: SKELETON_BUBBLE_COUNT }).map((_, idx) => {
            const isMineSkeleton = idx % 2 === 1
            // Width jitter so skeletons don't look uniformly mechanical.
            // Deterministic per index (avoids hydration mismatches in any
            // future SSR re-enablement).
            const widthPct = 45 + ((idx * 13) % 35)
            return (
              <div
                key={getMessageSkeletonKey(idx)}
                className={cn(
                  "flex items-end gap-2 md:gap-3",
                  isMineSkeleton ? "flex-row-reverse" : "flex-row"
                )}
                aria-hidden="true"
              >
                <div className="messenger-skeleton size-9 shrink-0 rounded-full" />
                <div
                  className={cn(
                    "messenger-skeleton min-h-[44px] rounded-2xl",
                    isMineSkeleton
                      ? "rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                      : "rounded-bl-sm"
                  )}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // Wave 183 SW5 — no-messages-yet empty state when chat is selected but
  // message list is empty (new chat OR cleared chat). Pre-W183 the
  // virtualizer rendered nothing for an empty messages array — user saw
  // a blank chat area with no context about why or what to do next.
  // Now mirrors the ChatArea empty-state visual language: matte icon
  // container, violet accent, encouragement copy.
  if (messages.length === 0) {
    return (
      <div
        ref={containerRef}
        role="log"
        aria-live="polite"
        aria-label={t("messenger:aria.messageList")}
        className="messenger-chat-area flex flex-1 flex-col items-center justify-center px-6 py-10"
      >
        <m.div
          initial={prefersReducedMotion ? false : { scale: 0.92, opacity: 0, y: 8 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const }
          }
          className="flex w-full max-w-[24rem] flex-col items-center text-center"
        >
          <div
            className="messenger-card-matte mb-5 flex size-16 items-center justify-center"
            style={{ background: "var(--messenger-card-bg)" }}
          >
            <MessageCircleHeart
              className="size-8 text-(--color-violet-500)"
              style={{ opacity: "var(--opacity-strong)" }}
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </div>
          <h3 className="sf-pro mb-2 text-base font-bold leading-tight text-(--text-primary)">
            {t("messenger:noMessages.title")}
          </h3>
          <p className="text-sm leading-relaxed text-(--text-secondary)">
            {t("messenger:noMessages.description")}
          </p>
        </m.div>
      </div>
    )
  }

  // Wave 184 SW1 (Path A) — search-no-match empty state. Rendered when
  // chat has messages but user's current search query filters to zero
  // matches. Mirrors W183 SW1 ContactList search-empty pattern exactly
  // (SearchX icon + interpolated query in description + Clear-search
  // CTA). Re-uses the same i18n key shape: `messenger:noMessages.searchEmpty.*`.
  if (isSearchActive && filteredMessages.length === 0) {
    return (
      <div
        ref={containerRef}
        role="log"
        aria-live="polite"
        aria-label={t("messenger:aria.messageList")}
        className="messenger-chat-area flex flex-1 flex-col items-center justify-center px-6 py-10 text-center"
      >
        <m.div
          initial={prefersReducedMotion ? false : { scale: 0.92, opacity: 0, y: 8 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const }
          }
          className="flex w-full max-w-[24rem] flex-col items-center"
        >
          <div
            className="messenger-card-matte mb-5 flex size-16 items-center justify-center"
            style={{ background: "var(--messenger-card-bg)" }}
          >
            <SearchX
              className="size-8 text-(--color-violet-500)"
              style={{ opacity: "var(--opacity-strong)" }}
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </div>
          <h3 className="sf-pro mb-2 text-base font-bold leading-tight text-(--text-primary)">
            {t("messenger:noMessages.searchEmpty.title")}
          </h3>
          <p className="mb-6 text-sm leading-relaxed text-(--text-secondary)">
            {t("messenger:noMessages.searchEmpty.description", { query: trimmedQuery })}
          </p>
          {onClearSearch && (
            <m.button
              type="button"
              whileHover={prefersReducedMotion ? undefined : { scale: 1.04 }}
              whileTap={prefersReducedMotion ? undefined : { scale: 0.96 }}
              onClick={onClearSearch}
              className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-(--color-violet-500)/(--opacity-soft) bg-(--bg-surface)/(--opacity-medium) px-5 text-sm font-semibold text-(--text-primary) transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
            >
              <X className="size-4" strokeWidth={2.5} aria-hidden="true" />
              <span>{t("messenger:noMessages.searchEmpty.clearSearch")}</span>
            </m.button>
          )}
        </m.div>
      </div>
    )
  }

  return (
    <div className="relative flex flex-1 min-h-0 flex-col">
      {hasMore && onLoadOlder ? (
        <div className="flex shrink-0 flex-col items-center gap-1 px-4 py-2">
          <button
            type="button"
            onClick={() => void onLoadOlder()}
            disabled={isLoadingOlder}
            className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-(--glass-border) bg-(--bg-surface-raised) px-4 text-sm font-semibold text-(--text-primary) transition-colors hover:bg-(--bg-surface-hover) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) disabled:cursor-wait disabled:opacity-medium"
          >
            {isLoadingOlder
              ? t("messenger:history.loadingOlder")
              : t("messenger:history.loadOlder")}
          </button>
          {olderMessagesError ? (
            <span role="alert" className="text-sm text-(--error-text)">
              {t("messenger:history.loadOlderError")}
            </span>
          ) : null}
        </div>
      ) : null}
      <div
        ref={containerRef}
        role="log"
        aria-live="polite"
        aria-label={t("messenger:aria.messageList")}
        className="messenger-chat-area flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar"
      >
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: "100%",
            position: "relative",
          }}
        >
          {virtualizer.getVirtualItems().map((virtualRow) => {
            // Wave 184 SW1 (Path A) — index into FILTERED messages, not the raw
            // array, so virtualRow.index aligns with the count passed to
            // useVirtualizer above. Using `messages[virtualRow.index]` would
            // misalign when a search query is active (virtualizer count =
            // filteredMessages.length, but raw messages.length > filtered).
            const message = filteredMessages[virtualRow.index]!

            // Wave 202 SW6 — only newly-appended rows (index >= animateFromIndex)
            // run the entrance; already-seen rows mount with initial={false} so
            // they appear instantly on scroll-into-view (no re-animation). Search
            // results never animate (the filtered set isn't "new" messages).
            const animateEntrance = shouldAnimateMessageEntrance({
              prefersReducedMotion: Boolean(prefersReducedMotion),
              isSearchActive,
              index: virtualRow.index,
              animateFromIndex,
            })
            const entranceMotion = getMessageEntranceMotion(animateEntrance)

            return (
              <div
                key={virtualRow.key}
                ref={virtualizer.measureElement}
                data-index={virtualRow.index}
                className="absolute top-0 left-0 w-full"
                style={{
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                {/* Wave 208 SW5 — date divider above the first message of a new
                    calendar day. Rendered INSIDE the measureElement item so the
                    virtualizer measures the divider + row together (no separate
                    virtual row → the filteredMessages count/index alignment from
                    W184 SW1 stays intact). */}
                {message.showDateDivider && message.dateLabel ? (
                  <div className="flex justify-center py-2">
                    <span className="rounded-full bg-(--bg-surface-raised)/(--opacity-medium) px-3 py-1 text-micro font-semibold uppercase tracking-wide text-(--text-secondary)">
                      {message.dateLabel}
                    </span>
                  </div>
                ) : null}
                <m.div
                  {...entranceMotion}
                  className={cn(
                    "flex items-end gap-2 md:gap-3 w-full md:flex-row group",
                    message.isGroupStart === false ? "py-0.5" : "py-1",
                    message.isMe
                      ? "flex-row-reverse justify-start md:justify-start"
                      : "flex-row justify-start"
                  )}
                >
                  {/* Wave 208 SW5 — sender grouping: hide the avatar (keep a
                      same-size spacer) for non-group-start messages so a run from
                      one sender shares a single avatar. undefined (optimistic /
                      standalone) keeps the avatar. */}
                  <div className="shrink-0 mb-1">
                    {message.isGroupStart === false ? (
                      <div className="w-8 h-8 md:w-9 md:h-9" aria-hidden="true" />
                    ) : (
                      <SmartImage
                        srcRaw={message.senderAvatar || AVATAR_PLACEHOLDER_URL}
                        fallback={AVATAR_PLACEHOLDER_URL}
                        alt={message.senderName || ""}
                        className="w-8 h-8 md:w-9 md:h-9 rounded-full object-cover shadow-sm ring-1 ring-black/(--opacity-faint) dark:ring-white/(--opacity-faint)"
                      />
                    )}
                  </div>

                  {/* Wave 203 SW6 — column wrapper so the single "Seen · HH:MM"
                    marker can sit BELOW the bubble (right-aligned for sent). The
                    max-w-* constraint moves to the column; the bubble keeps its
                    box styling + max-w-full (caps at the column width). */}
                  <div
                    className={cn(
                      "flex min-w-0 max-w-4/5 flex-col gap-1 sm:max-w-3/4 md:max-w-[68%] lg:max-w-[60%] xl:max-w-[52%]",
                      message.isMe ? "items-end" : "items-start"
                    )}
                  >
                    {message.deletedAt ? (
                      // Wave 205 SW6 — deleted tombstone (D1: persistent, WhatsApp-style).
                      // The row stays; content was cleared server-side. Drops
                      // attachments + affordance + status + seen marker; uses the neutral
                      // received-bubble style (not the violet sent bubble) + italic muted text.
                      <div
                        className={cn(
                          "relative max-w-full px-4 py-2.5 text-base messenger-bubble-received rounded-2xl",
                          message.isMe
                            ? "rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                            : "rounded-bl-sm"
                        )}
                      >
                        <p className="italic leading-relaxed text-text-secondary">
                          {t("messenger:messageDeleted")}
                        </p>
                        <div className="mt-(--space-1) flex justify-end opacity-hover">
                          <span className="text-micro font-bold uppercase tracking-wider text-text-secondary">
                            {message.timestamp}
                          </span>
                        </div>
                      </div>
                    ) : editingMessageId === message.id ? (
                      // Wave 205 SW6 — inline edit. Enter saves, Shift+Enter inserts a
                      // newline, Esc cancels. The controller closes the editor + fires the
                      // optimistic PATCH on save (handleSaveEdit). Uses the neutral
                      // received-bubble style so the editor reads as an input, not a sent bubble.
                      <div
                        className={cn(
                          "relative w-full max-w-full messenger-bubble-received rounded-2xl px-3 py-2.5",
                          message.isMe
                            ? "rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                            : "rounded-bl-sm"
                        )}
                      >
                        <label className="sr-only" htmlFor={`edit-message-${message.id}`}>
                          {t("messenger:editMessage")}
                        </label>
                        <textarea
                          id={`edit-message-${message.id}`}
                          value={editingMessageContent}
                          onChange={(event) => handleEditingContentChange(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" && !event.shiftKey) {
                              event.preventDefault()
                              handleSaveEdit(message.id)
                            } else if (event.key === "Escape") {
                              event.preventDefault()
                              handleCancelEdit()
                            }
                          }}
                          rows={2}
                          // eslint-disable-next-line jsx-a11y/no-autofocus
                          autoFocus
                          className="w-full resize-none rounded-lg bg-(--bg-surface)/(--opacity-medium) px-3 py-2 text-base leading-relaxed text-(--text-primary) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                        />
                        <div className="mt-2 flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={handleCancelEdit}
                            className="-my-0.5 inline-flex min-h-[44px] min-w-[44px] items-center rounded-full px-4 text-sm font-semibold text-(--text-secondary) transition-colors hover:text-(--text-primary) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
                          >
                            {t("common:buttons.cancel")}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSaveEdit(message.id)}
                            className="messenger-send-btn -my-0.5 inline-flex min-h-[44px] min-w-[44px] items-center rounded-full px-5 text-sm font-semibold text-[var(--text-inverse)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
                          >
                            {t("common:buttons.save")}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        className={cn(
                          "relative max-w-full px-4 py-2.5 text-base",
                          message.isMe
                            ? "messenger-bubble-sent text-[var(--text-inverse)] rounded-2xl rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                            : "messenger-bubble-received text-text-primary rounded-2xl rounded-bl-sm"
                        )}
                      >
                        {/* Wave 211 — "Forwarded from X" header (snapshot-copy
                          forwarding). Sits at the top of the bubble (above
                          attachments + content), Telegram-style. Theme-aware:
                          text-inverse on the violet sent bubble, brand-main on
                          the neutral received bubble. forwardedFromName is
                          null/absent for non-forwards; a forward carries
                          replyTo=null, so this is mutually exclusive with the
                          reply chip below. */}
                        {message.forwardedFromName ? (
                          <div
                            className={cn(
                              "mb-1.5 flex items-center gap-1 text-micro font-semibold italic",
                              message.isMe
                                ? "text-[var(--text-inverse)] opacity-medium"
                                : "text-(--brand-main)"
                            )}
                          >
                            <Forward
                              className="size-3 shrink-0"
                              strokeWidth={2.5}
                              aria-hidden="true"
                            />
                            <span className="truncate">
                              {t("messenger:forwardedFrom", {
                                name: message.forwardedFromName,
                              })}
                            </span>
                          </div>
                        ) : null}
                        {message.attachments && message.attachments.length > 0 && (
                          <div className="mb-2 space-y-2">
                            {message.attachments.map((attachment) => (
                              <div key={attachment.id} className="overflow-hidden rounded-xl">
                                {attachment.type === "image" ? (
                                  sanitizeUrl(attachment.url) ? (
                                    <button
                                      type="button"
                                      aria-label={`${t("messenger:viewAvatar")}: ${attachment.name}`}
                                      className="block min-h-[44px] min-w-[44px] w-full rounded-xl border-0 bg-transparent p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-violet-500)"
                                      onClick={() => {
                                        // Rendering already proved this immutable URL safe.
                                        window.open(
                                          sanitizeUrl(attachment.url)!,
                                          "_blank",
                                          "noopener,noreferrer"
                                        )
                                      }}
                                    >
                                      <SmartImage
                                        srcRaw={attachment.url}
                                        alt={attachment.name}
                                        className="w-full h-auto max-h-72 object-cover cursor-pointer hover:scale-hover transition-transform duration-slow"
                                      />
                                    </button>
                                  ) : null
                                ) : sanitizeUrl(attachment.url) ? (
                                  <a
                                    href={sanitizeUrl(attachment.url)!}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className={cn(
                                      "flex items-center gap-3 p-3 rounded-xl transition-colors border border-white/(--opacity-faint)",
                                      message.isMe
                                        ? "bg-(--messenger-attachment-bg) hover:bg-(--messenger-attachment-bg-hover)"
                                        : "bg-(--bg-surface-raised)/(--opacity-medium) hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                                    )}
                                  >
                                    <div
                                      className={cn(
                                        "p-2 rounded-lg",
                                        message.isMe
                                          ? "bg-(--messenger-attachment-bg) text-[var(--text-inverse)]"
                                          : "bg-(--bg-surface-raised) text-(--brand-main)"
                                      )}
                                    >
                                      <File size={20} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                      <p className="truncate text-sm font-bold">
                                        {attachment.name}
                                      </p>
                                      <p className="text-micro opacity-medium font-medium">
                                        {(attachment.size / 1024).toFixed(1)} KB
                                      </p>
                                    </div>
                                  </a>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Wave 207 — quoted reply preview. Sits above the content,
                          inside the bubble. Author line = "You" when the quoted
                          message is mine (isMe resolved at transform time), else the
                          sender name. Body = the snippet (line-clamped 2) OR an
                          italic "original deleted" placeholder when the target was
                          soft-deleted. Border-l accent + faint tint, theme-aware
                          per sent (text-inverse on violet) vs received (violet on
                          neutral). */}
                        {message.replyTo ? (
                          <div
                            className={cn(
                              "mb-2 rounded-lg border-l-2 px-2.5 py-1.5",
                              message.isMe
                                ? "border-(--text-inverse)/(--opacity-medium) bg-(--text-inverse)/(--opacity-faint)"
                                : "border-(--color-violet-500)/(--opacity-medium) bg-(--color-violet-500)/(--opacity-faint)"
                            )}
                          >
                            <p
                              className={cn(
                                "text-micro font-semibold",
                                message.isMe ? "text-[var(--text-inverse)]" : "text-(--brand-main)"
                              )}
                            >
                              {message.replyTo.isMe
                                ? t("messenger:replyTo.you")
                                : (message.replyTo.senderName ??
                                  t("messenger:replyTo.unknownSender"))}
                            </p>
                            <p
                              className={cn(
                                "line-clamp-2 text-sm leading-snug",
                                message.replyTo.deletedAt && "italic",
                                message.isMe
                                  ? "text-[var(--text-inverse)] opacity-medium"
                                  : "text-(--text-secondary)"
                              )}
                            >
                              {message.replyTo.deletedAt
                                ? t("messenger:replyTo.deletedOriginal")
                                : message.replyTo.text}
                            </p>
                          </div>
                        ) : null}
                        <p className="wrap-break-word leading-relaxed whitespace-pre-wrap">
                          {message.text}
                        </p>
                        <div className="mt-(--space-1) flex items-center justify-between gap-2">
                          {/* Wave 205 SW6 — own-message edit/delete affordance. Always
                          rendered + reachable (touch + keyboard + mouse), subtle by
                          default (opacity-medium → full on hover/focus). Icons sit on
                          the violet sent bubble so they use text-inverse. The icon
                          remains size-4 while the button exposes the shared 44px hit
                          area contract. A right-context-menu / hover-reveal UX is out
                          of W205 scope. */}
                          {onStartReply || onForward || message.isMe ? (
                            <div className="flex items-center gap-0.5">
                              {/* Wave 207 — reply affordance on ALL bubbles (not just
                              own). On the violet sent bubble it uses text-inverse +
                              inverse focus ring (matching edit/delete); on the neutral
                              received bubble it uses text-secondary + violet focus
                              ring. The button keeps the same glyph and styling while
                              exposing the shared 44px hit area contract. */}
                              {onStartReply ? (
                                <button
                                  type="button"
                                  onClick={() => onStartReply(message.id)}
                                  aria-label={t("messenger:reply")}
                                  className={cn(
                                    "-m-2 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md p-1.5 opacity-medium transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2",
                                    message.isMe
                                      ? "text-[var(--text-inverse)] focus-visible:ring-[var(--text-inverse)]"
                                      : "text-(--text-secondary) focus-visible:ring-(--color-violet-500)"
                                  )}
                                >
                                  <Reply className="size-4" strokeWidth={2} aria-hidden="true" />
                                </button>
                              ) : null}
                              {/* Wave 211 — forward affordance on ALL bubbles (like
                              reply). Opens the ForwardModal destination picker. Same
                              44px hit area + theme-aware styling as reply (text-inverse
                              + inverse ring on the violet sent bubble; text-secondary +
                              violet ring on the neutral received bubble). */}
                              {onForward ? (
                                <button
                                  type="button"
                                  onClick={() => onForward(message.id)}
                                  aria-label={t("messenger:forward")}
                                  className={cn(
                                    "-m-2 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md p-1.5 opacity-medium transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2",
                                    message.isMe
                                      ? "text-[var(--text-inverse)] focus-visible:ring-[var(--text-inverse)]"
                                      : "text-(--text-secondary) focus-visible:ring-(--color-violet-500)"
                                  )}
                                >
                                  <Forward className="size-4" strokeWidth={2} aria-hidden="true" />
                                </button>
                              ) : null}
                              {message.isMe ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => handleEditMessage(message.id, message.text)}
                                    aria-label={t("messenger:editMessage")}
                                    className="-m-2 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md p-1.5 text-[var(--text-inverse)] opacity-medium transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--text-inverse)]"
                                  >
                                    <Pencil className="size-4" strokeWidth={2} aria-hidden="true" />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleDeleteMessage(message.id)}
                                    aria-label={t("messenger:deleteMessage")}
                                    className="-m-2 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md p-1.5 text-[var(--text-inverse)] opacity-medium transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--text-inverse)]"
                                  >
                                    <Trash2 className="size-4" strokeWidth={2} aria-hidden="true" />
                                  </button>
                                </>
                              ) : null}
                            </div>
                          ) : (
                            <span aria-hidden="true" />
                          )}
                          <div className="flex items-center gap-1.5 opacity-hover">
                            {/* Wave 205 SW6 — "(edited)" label when the message was edited
                            (and not deleted). lowercase + muted; full edit timestamp in
                            the title tooltip. */}
                            {message.editedAt ? (
                              <span
                                className="text-micro font-medium lowercase"
                                title={
                                  message.editedAtLabel
                                    ? t("messenger:messageEditedAt", {
                                        time: message.editedAtLabel,
                                      })
                                    : undefined
                                }
                                style={{
                                  color: message.isMe
                                    ? "var(--primary-subtle)"
                                    : "var(--text-secondary)",
                                }}
                              >
                                {t("messenger:edited")}
                              </span>
                            ) : null}
                            <span
                              className="text-micro font-bold uppercase tracking-wider"
                              style={{
                                color: message.isMe
                                  ? "var(--primary-subtle)"
                                  : "var(--text-secondary)",
                              }}
                            >
                              {message.timestamp}
                            </span>
                            {message.isMe && (
                              <span
                                className="flex items-center opacity-hover"
                                role="img"
                                aria-label={
                                  message.status === "read"
                                    ? t("messenger:aria.messageRead")
                                    : t("messenger:aria.messageSent")
                                }
                              >
                                {/* Wave 181 SW3 — text-white → text-[var(--text-inverse)]
                            (theme-aware; same W175 SW2 pattern. text-inverse is
                            white in light, slate-950 in dark. On the violet
                            sent-bubble bg, white in light = 9.9:1 contrast,
                            slate-950 in dark = 9.9:1 contrast on violet-500.
                            Both pass WCAG AA 4.5:1 with comfortable margin.)
                            Wave 183 SW6 — added role=img + aria-label on
                            wrapper span so screen readers announce "Sent" /
                            "Read by recipient" instead of skipping the icon
                            entirely (previous aria-hidden default on lucide
                            icons meant SR users had no message-status feedback). */}
                                {message.status === "read" ? (
                                  <CheckCheck
                                    className="w-3 h-3 text-[var(--text-inverse)]"
                                    aria-hidden="true"
                                  />
                                ) : (
                                  <Check
                                    className="w-3 h-3 text-[var(--text-inverse)] opacity-medium"
                                    aria-hidden="true"
                                  />
                                )}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                    {/* Wave 206 — reaction footer (pills + "+react") + inline emoji
                      picker. Hidden on deleted tombstones + while inline-editing.
                      Pills render read-only without onToggleReaction (tests/
                      storybook); the +react affordance + picker need the handler.
                      reactedByMe pills get the violet tint; clicking a pill toggles
                      that emoji. data-reaction-ui marks the outside-click exemptions. */}
                    {!message.deletedAt &&
                    editingMessageId !== message.id &&
                    ((message.reactions && message.reactions.length > 0) || onToggleReaction) ? (
                      <div
                        className={cn(
                          "flex flex-wrap items-center gap-1",
                          message.isMe ? "justify-end" : "justify-start"
                        )}
                      >
                        {message.reactions?.map((reaction) => (
                          <ReactionPill
                            key={reaction.emoji}
                            chatId={chatId}
                            messageId={message.id}
                            emoji={reaction.emoji}
                            count={reaction.count}
                            reactedByMe={reaction.reactedByMe}
                            onToggle={(value) => handleToggleReaction(message.id, value)}
                          />
                        ))}
                        {onToggleReaction ? (
                          <button
                            type="button"
                            data-reaction-ui
                            onClick={() =>
                              setReactionPickerForId((prev) =>
                                prev === message.id ? null : message.id
                              )
                            }
                            aria-label={t("messenger:reactions.add")}
                            aria-expanded={reactionPickerForId === message.id}
                            className="-m-2 inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full text-(--text-secondary) opacity-medium transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-1 focus-visible:ring-offset-(--bg-surface)"
                          >
                            <SmilePlus className="size-4" strokeWidth={2} aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                    {reactionPickerForId === message.id && onToggleReaction ? (
                      <div
                        data-reaction-ui
                        role="group"
                        aria-label={t("messenger:reactions.add")}
                        className={cn(
                          "messenger-card-matte flex items-center gap-1 rounded-full px-2 py-1",
                          message.isMe ? "self-end" : "self-start"
                        )}
                      >
                        {REACTION_EMOJIS.map((emoji) => (
                          <button
                            key={emoji}
                            type="button"
                            onClick={() => {
                              handleToggleReaction(message.id, emoji)
                              setReactionPickerForId(null)
                            }}
                            aria-label={t("messenger:reactions.react", { emoji })}
                            className="-m-2 inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full text-xl transition-transform hover:scale-125 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                          >
                            <span aria-hidden="true">{emoji}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {!message.deletedAt &&
                      message.isMe &&
                      (message.seenByCount !== undefined && message.seenByTotal !== undefined ? (
                        message.seenByCount > 0 ? (
                          <span className="px-1 text-micro font-medium text-text-secondary">
                            {t("messenger:seenByGroup", {
                              count: message.seenByCount,
                              total: message.seenByTotal,
                            })}
                          </span>
                        ) : null
                      ) : message.isLastRead && message.readAtLabel ? (
                        <span className="px-1 text-micro font-medium text-text-secondary">
                          {t("messenger:seen", { time: message.readAtLabel })}
                        </span>
                      ) : null)}
                  </div>
                </m.div>
              </div>
            )
          })}
        </div>
      </div>
      {showJumpButton ? (
        <m.button
          type="button"
          onClick={() =>
            virtualizer.scrollToIndex(filteredMessages.length - 1, {
              align: "end",
              behavior: "smooth",
            })
          }
          aria-label={t("messenger:aria.jumpToLatest")}
          initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.85, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: 0.2, ease: [0.22, 1, 0.36, 1] as const }
          }
          whileHover={prefersReducedMotion ? undefined : { scale: 1.05 }}
          whileTap={prefersReducedMotion ? undefined : { scale: 0.95 }}
          className="messenger-send-btn absolute bottom-4 right-4 z-10 inline-flex size-11 items-center justify-center rounded-full text-[var(--text-inverse)] shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
        >
          <ArrowDown className="size-5" strokeWidth={2.5} aria-hidden="true" />
        </m.button>
      ) : null}
    </div>
  )
})

export default ChatWindow
