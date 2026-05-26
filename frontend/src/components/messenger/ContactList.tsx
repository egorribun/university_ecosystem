import { m } from "framer-motion"
import {
  MessageCirclePlus,
  MessagesSquare,
  RotateCcw,
  SearchX,
  TriangleAlert,
  X,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { Contact } from "./types"

interface ContactListProps {
  contacts: Contact[]
  selectedId: string | null
  onSelect: (id: string) => void
  /**
   * Wave 183 SW1 — empty-state context.
   * `isSearchActive` = true → render "no results match {query}" variant
   * with SearchX icon and "Clear search" CTA.
   * `isSearchActive` = false → render "no conversations yet" variant
   * with MessagesSquare icon and "Start new conversation" CTA.
   */
  isSearchActive?: boolean
  searchQuery?: string
  onStartNewChat?: () => void
  onClearSearch?: () => void
  /**
   * Wave 184 SW2 (Path B) — chats list query loading state. When true,
   * renders 6 skeleton rows (h-[60px] matching real ContactRow dimensions
   * per W184 plan risk #4 — skeleton heights must match real rows to
   * prevent CLS shift on load completion) BEFORE checking contacts.length
   * === 0. This prevents the W183 SW1 "No conversations yet" empty state
   * from flashing briefly while the initial chats fetch is in-flight.
   * Uses `.messenger-skeleton` shimmer class from W181 SW1 (messenger.css:635).
   */
  isLoading?: boolean
  /**
   * Wave 184 SW3 (Path B) — chats list query error state. When true,
   * renders a fetch-failure empty state with TriangleAlert icon + i18n
   * description + Retry CTA. Distinguishes "no chats" (W183 SW1 empty
   * state) from "network error" (this branch) so users have an actionable
   * retry path without page reload. Order: isLoading → isError →
   * contacts.length === 0 → normal render.
   */
  isError?: boolean
  /**
   * Wave 184 SW3 (Path B) — retry callback wired to React Query's
   * `refetch()` (via MessengerFeature → useMessengerController). Invoked
   * by the Retry button inside the error empty state.
   */
  onRetry?: () => void
}

// Wave 184 SW2 (Path B) — skeleton row count. 6 rows is enough to fill the
// sidebar viewport on most screens without being visually overwhelming.
const SKELETON_ROW_COUNT = 6

// PERF-24-02: Removed React.memo() — React Compiler "infer" mode handles
// memoization automatically. Manual memo() caused redundant double-wrapping.
//
// Wave 124 SW1 — Removed LayoutGroup + `layout` prop (require domMax). Items
// snap-reorder when contacts list is re-sorted (e.g., new message moves
// contact to top). Per plan: messenger contact reorder is rare and snap is
// acceptable UX. whileHover + whileTap + the unread-badge initial/animate
// remain — they're in domAnimation set.
//
// Wave 181 SW3 — visual polish to match feature-page parity:
// - Active row uses `.messenger-active-chip` (left accent stripe ::before +
//   subtle violet bg tint via --messenger-active-bg) instead of strong
//   bg-(--brand-main) fill. Modern chat-app pattern (Telegram/Discord/IG-DM)
//   where active row is visually distinct WITHOUT shouting at the user.
// - Text inside active row stays at text-text-primary (NOT text-inverse)
//   since the bg is now subtle violet tint, not a strong brand fill.
// - CSS `.messenger-stagger-item` entrance via @starting-style + inline
//   `--stagger-index` (W118 SW3 cap at 60ms * 6 = 360ms total).
// - useReducedMotion guard on whileHover + whileTap (otherwise rows shift
//   horizontally on hover for users who opted into reduced motion).
// - focus-visible ring on keyboard nav (WCAG 2.4.7).
// - aria-current="true" on selected row for screen-reader awareness.
//
// Wave 183 SW1 — Empty-state pattern. When contacts.length === 0:
//  - With active search → "No results found" variant + Clear search CTA.
//  - Without active search → "No conversations yet" variant + Start new chat CTA.
// User-reported Issue #1: sidebar previously rendered an empty `<div>` when
// contacts were absent (LHCI bypass user or zero-contact accounts), exposing
// raw bg-(--msg-sidebar-bg) with no hierarchy. Now matches feature-page
// parity (Activity/Events polish arcs) with matte icon container + violet
// accent CTA. NEW i18n keys: messenger:noChats.{title, description, cta,
// searchEmpty.{title, description, clearSearch}} in EN + RU.
export function ContactList({
  contacts,
  selectedId,
  onSelect,
  isSearchActive = false,
  searchQuery = "",
  onStartNewChat,
  onClearSearch,
  isLoading = false,
  isError = false,
  onRetry,
}: ContactListProps) {
  const { t } = useTranslation(["messenger"])
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const hoverAnim = prefersReducedMotion ? undefined : { x: 4 }
  const tapAnim = prefersReducedMotion ? undefined : { scale: 0.98 }

  // Wave 184 SW2 (Path B) — skeleton rows render BEFORE both empty-state
  // branches (W183 SW1 no-conversations + no-search-match) so first-paint
  // feedback during the initial chats fetch doesn't flash "No conversations
  // yet" wrongly. Rows match the dimensions of real ContactRow (line ~150+
  // below: 60px tall with size-12 avatar circle + 2 text lines stacked).
  // Order matters: this MUST come before the contacts.length===0 branch.
  if (isLoading) {
    return (
      <div
        className="flex-1 overflow-y-auto custom-scrollbar p-2 bg-(--msg-sidebar-bg)"
        role="status"
        aria-live="polite"
        aria-label={t("messenger:loading.contacts")}
      >
        {Array.from({ length: SKELETON_ROW_COUNT }).map((_, idx) => (
          <div
            key={`contact-skeleton-${idx}`}
            className="flex items-center gap-3 px-3 py-2.5 min-h-[60px]"
            aria-hidden="true"
          >
            <div className="messenger-skeleton size-12 shrink-0 rounded-full" />
            <div className="flex flex-1 flex-col gap-2 min-w-0">
              <div
                className="messenger-skeleton h-3.5 rounded-md"
                style={{ width: `${65 + ((idx * 11) % 25)}%` }}
              />
              <div
                className="messenger-skeleton h-3 rounded-md"
                style={{ width: `${45 + ((idx * 7) % 35)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    )
  }

  // Wave 184 SW3 (Path B) — fetch-failure empty state. Order matters:
  // must come AFTER isLoading (so a transient fetch error during refetch
  // doesn't flash the error banner while the spinner should win) but
  // BEFORE the contacts.length === 0 empty state (so a network error
  // doesn't disguise itself as "No conversations yet"). Reuses the
  // .messenger-card-matte container + violet accent palette (W181 SW1)
  // for visual consistency with sibling empty states (W183 SW1).
  if (isError) {
    const errorEntrance = prefersReducedMotion ? undefined : { scale: 0.92, opacity: 0, y: 8 }
    const errorAnimate = { scale: 1, opacity: 1, y: 0 }
    const errorTransition = prefersReducedMotion
      ? { duration: 0 }
      : { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const }
    return (
      <div
        className="flex flex-1 flex-col items-center justify-center bg-(--msg-sidebar-bg) px-6 py-10 text-center"
        role="alert"
        aria-live="assertive"
      >
        <m.div
          initial={errorEntrance}
          animate={errorAnimate}
          transition={errorTransition}
          className="flex w-full max-w-[18rem] flex-col items-center"
        >
          <div
            className="messenger-card-matte mb-6 flex size-20 items-center justify-center"
            style={{ background: "var(--messenger-card-bg)" }}
          >
            <TriangleAlert
              className="size-10 text-(--color-violet-500)"
              style={{ opacity: "var(--opacity-strong)" }}
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </div>
          <h3 className="sf-pro mb-2 text-base font-bold leading-tight text-(--text-primary)">
            {t("messenger:error.failedToLoadChats")}
          </h3>
          <p className="mb-6 text-sm leading-relaxed text-(--text-secondary)">
            {t("messenger:error.failedToLoadChatsHint")}
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

  if (contacts.length === 0) {
    const emptyEntrance = prefersReducedMotion ? undefined : { scale: 0.92, opacity: 0, y: 8 }
    const emptyAnimate = { scale: 1, opacity: 1, y: 0 }
    const emptyTransition = prefersReducedMotion
      ? { duration: 0 }
      : { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const }

    const showSearchEmpty = isSearchActive
    const Icon = showSearchEmpty ? SearchX : MessagesSquare
    const titleKey = showSearchEmpty
      ? "messenger:noChats.searchEmpty.title"
      : "messenger:noChats.title"
    const descriptionKey = showSearchEmpty
      ? "messenger:noChats.searchEmpty.description"
      : "messenger:noChats.description"
    const descriptionInterp = showSearchEmpty ? { query: searchQuery } : undefined

    return (
      <div
        className="flex flex-1 flex-col items-center justify-center bg-(--msg-sidebar-bg) px-6 py-10 text-center"
        role="status"
        aria-live="polite"
      >
        <m.div
          initial={emptyEntrance}
          animate={emptyAnimate}
          transition={emptyTransition}
          className="flex w-full max-w-[18rem] flex-col items-center"
        >
          <div
            className="messenger-card-matte mb-6 flex size-20 items-center justify-center"
            style={{ background: "var(--messenger-card-bg)" }}
          >
            <Icon
              className="size-10 text-(--color-violet-500)"
              style={{ opacity: "var(--opacity-strong)" }}
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </div>
          <h3 className="sf-pro mb-2 text-base font-bold leading-tight text-(--text-primary)">
            {t(titleKey)}
          </h3>
          <p className="mb-6 text-sm leading-relaxed text-(--text-secondary)">
            {t(descriptionKey, descriptionInterp)}
          </p>
          {showSearchEmpty
            ? onClearSearch && (
                <m.button
                  type="button"
                  whileHover={prefersReducedMotion ? undefined : { scale: 1.04 }}
                  whileTap={prefersReducedMotion ? undefined : { scale: 0.96 }}
                  onClick={onClearSearch}
                  className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-(--color-violet-500)/(--opacity-soft) bg-(--bg-surface)/(--opacity-medium) px-5 text-sm font-semibold text-(--text-primary) transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
                >
                  <X className="size-4" strokeWidth={2.5} aria-hidden="true" />
                  <span>{t("messenger:noChats.searchEmpty.clearSearch")}</span>
                </m.button>
              )
            : onStartNewChat && (
                <m.button
                  type="button"
                  whileHover={prefersReducedMotion ? undefined : { scale: 1.04 }}
                  whileTap={prefersReducedMotion ? undefined : { scale: 0.96 }}
                  onClick={onStartNewChat}
                  className="messenger-send-btn inline-flex min-h-[44px] items-center gap-2 rounded-full px-5 text-sm font-semibold text-(--text-inverse) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
                >
                  <MessageCirclePlus className="size-4" strokeWidth={2.5} aria-hidden="true" />
                  <span>{t("messenger:noChats.cta")}</span>
                </m.button>
              )}
        </m.div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar p-2 bg-(--msg-sidebar-bg)">
      {contacts.map((contact, index) => {
        const isActive = selectedId === contact.id
        return (
          <m.div
            key={contact.id}
            id={`messenger-contact-${contact.id}`}
            role="button"
            tabIndex={0}
            aria-current={isActive ? "true" : undefined}
            style={{ "--stagger-index": Math.min(index, 6) } as React.CSSProperties}
            onClick={() => onSelect(contact.id)}
            onKeyDown={(event) => {
              // Wave 183 SW4 — added Arrow Up/Down + Home/End keyboard nav
              // (WCAG 2.1.1 Keyboard + ARIA APG navigation widget pattern).
              // Pre-W183 only Enter/Space worked; users had to Tab through
              // contacts to navigate. No wrap-around (matches Slack/Discord
              // UX where Home/End jump to extremes deliberately).
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                onSelect(contact.id)
                return
              }
              if (
                event.key === "ArrowDown" ||
                event.key === "ArrowUp" ||
                event.key === "Home" ||
                event.key === "End"
              ) {
                event.preventDefault()
                let targetIndex = index
                if (event.key === "ArrowDown")
                  targetIndex = Math.min(index + 1, contacts.length - 1)
                else if (event.key === "ArrowUp") targetIndex = Math.max(index - 1, 0)
                else if (event.key === "Home") targetIndex = 0
                else if (event.key === "End") targetIndex = contacts.length - 1
                const target = contacts[targetIndex]
                if (target) {
                  document.getElementById(`messenger-contact-${target.id}`)?.focus()
                }
              }
            }}
            whileHover={hoverAnim}
            whileTap={tapAnim}
            className={cn(
              "messenger-stagger-item flex items-center gap-3 p-3 mb-1 rounded-2xl cursor-pointer transition-all duration-base min-h-[60px]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)",
              isActive
                ? "messenger-active-chip"
                : "hover:bg-(--bg-surface-hover)/(--opacity-subtle)"
            )}
          >
            <div className="relative shrink-0">
              <SmartImage
                srcRaw={contact.avatar || AVATAR_PLACEHOLDER_URL}
                fallback={AVATAR_PLACEHOLDER_URL}
                alt={contact.name}
                className="w-12 h-12 rounded-full object-cover shadow-sm"
              />
              {contact.online && (
                <span
                  className="messenger-online-indicator absolute bottom-0 right-0 w-3.5 h-3.5 border-2 border-(--bg-surface) dark:border-(--bg-page)"
                  aria-hidden="true"
                />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-center mb-0.5">
                <h3 className="font-bold text-base truncate sf-pro text-text-primary">
                  {contact.name}
                </h3>
                <span className="text-xs shrink-0 ml-2 font-medium uppercase tracking-tight text-(--text-secondary) opacity-medium">
                  {contact.lastMessageTime}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <p className="text-sm truncate flex-1 leading-tight text-(--text-secondary)">
                  {contact.lastMessage}
                </p>
                {contact.unread > 0 && (
                  <m.span
                    initial={prefersReducedMotion ? false : { scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={prefersReducedMotion ? { duration: 0 } : undefined}
                    className="messenger-unread-badge min-w-5 h-5 px-1 rounded-full text-label-xs flex items-center justify-center"
                    aria-label={t("messenger:aria.unread", { count: contact.unread })}
                  >
                    {contact.unread > 99 ? "99+" : contact.unread}
                  </m.span>
                )}
              </div>
            </div>
          </m.div>
        )
      })}
    </div>
  )
}
