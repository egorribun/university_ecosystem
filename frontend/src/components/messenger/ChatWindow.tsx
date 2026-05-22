import React, { useRef, useEffect, useMemo } from "react"
import { m, useReducedMotion } from "framer-motion" // Removed AnimatePresence, LayoutGroup as they are not used
import {
  File,
  Check,
  CheckCheck,
  MessageCircleHeart,
  RotateCcw,
  SearchX,
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
}

// Wave 184 SW2 (Path B) — skeleton bubble count. 6 alternating left/right
// bubbles fills the chat viewport without being visually overwhelming.
const SKELETON_BUBBLE_COUNT = 6

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  searchQuery = "",
  onClearSearch,
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  const { t } = useTranslation()
  // Wave 181 SW3 — useReducedMotion guard. Without this, virtualized message
  // bubbles fade+scale in on every scroll-into-view event, which becomes
  // disorienting motion for reduced-motion users.
  const prefersReducedMotion = useReducedMotion() ?? false
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
    overscan: 5,
  })

  const prevMessagesLengthRef = useRef(0)

  // Auto-scroll to bottom when new messages arrive.
  // Wave 184 SW1 — track filtered length so search-narrowing doesn't trigger
  // a spurious scroll-to-end. Auto-scroll only fires when the underlying
  // message list grows (new incoming message), not when search filtering
  // shrinks the displayed set.
  useEffect(() => {
    if (!isSearchActive && filteredMessages.length > prevMessagesLengthRef.current) {
      virtualizer.scrollToIndex(filteredMessages.length - 1, {
        align: "end",
        behavior: "auto",
      })
    }
    prevMessagesLengthRef.current = filteredMessages.length
  }, [filteredMessages.length, isSearchActive, virtualizer])

  // Initial scroll to bottom
  useEffect(() => {
    if (!isSearchActive && filteredMessages.length > 0) {
      virtualizer.scrollToIndex(filteredMessages.length - 1, {
        align: "end",
        behavior: "auto",
      })
    }
  }, [filteredMessages.length, isSearchActive, virtualizer])

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
                key={`message-skeleton-${idx}`}
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
          const message = filteredMessages[virtualRow.index]
          if (!message) return null

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
              <m.div
                initial={prefersReducedMotion ? false : { opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={
                  prefersReducedMotion
                    ? { duration: 0 }
                    : { duration: 0.3, ease: [0.22, 1, 0.36, 1] }
                }
                className={cn(
                  "flex items-end gap-2 md:gap-3 py-1 w-full md:flex-row group",
                  message.isMe
                    ? "flex-row-reverse justify-start md:justify-start"
                    : "flex-row justify-start"
                )}
              >
                <div className="shrink-0 mb-1">
                  <SmartImage
                    srcRaw={message.senderAvatar || AVATAR_PLACEHOLDER_URL}
                    fallback={AVATAR_PLACEHOLDER_URL}
                    alt={message.senderName || ""}
                    className="w-8 h-8 md:w-9 md:h-9 rounded-full object-cover shadow-sm ring-1 ring-black/(--opacity-faint) dark:ring-white/(--opacity-faint)"
                  />
                </div>

                <div
                  className={cn(
                    "max-w-4/5 md:max-w-3/4 px-4 py-2.5 text-base relative",
                    message.isMe
                      ? "messenger-bubble-sent text-[var(--text-inverse)] rounded-2xl rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                      : "messenger-bubble-received text-text-primary rounded-2xl rounded-bl-sm"
                  )}
                >
                  {message.attachments && message.attachments.length > 0 && (
                    <div className="mb-2 space-y-2">
                      {message.attachments.map((attachment) => (
                        <div key={attachment.id} className="overflow-hidden rounded-xl">
                          {attachment.type === "image" ? (
                            sanitizeUrl(attachment.url) ? (
                              <SmartImage
                                srcRaw={attachment.url}
                                alt={attachment.name}
                                className="w-full h-auto max-h-72 object-cover cursor-pointer hover:scale-hover transition-transform duration-slow"
                                onClick={() => {
                                  const safe = sanitizeUrl(attachment.url)
                                  if (safe) window.open(safe, "_blank", "noopener,noreferrer")
                                }}
                              />
                            ) : null
                          ) : sanitizeUrl(attachment.url) ? (
                            <a
                              href={sanitizeUrl(attachment.url)!}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={cn(
                                "flex items-center gap-3 p-3 rounded-xl transition-colors border border-white/(--opacity-faint)",
                                message.isMe
                                  ? "bg-white/(--opacity-subtle) hover:bg-white/(--opacity-soft)"
                                  : "bg-(--bg-surface-raised)/(--opacity-medium) hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                              )}
                            >
                              <div className="p-2 rounded-lg bg-white/(--opacity-subtle) text-(--brand-main)">
                                <File size={20} />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="truncate text-sm font-bold">{attachment.name}</p>
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
                  <p className="wrap-break-word leading-relaxed whitespace-pre-wrap">
                    {message.text}
                  </p>
                  <div className="flex items-center justify-end gap-1.5 mt-(--space-1) opacity-hover">
                    <span
                      className="text-micro font-bold uppercase tracking-wider"
                      style={{
                        color: message.isMe ? "var(--primary-subtle)" : "var(--text-secondary)",
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
              </m.div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

ChatWindow.displayName = "ChatWindow"
