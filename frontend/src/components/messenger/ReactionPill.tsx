import { useRef, useState, type PointerEvent } from "react"
import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import {
  useFloating,
  useHover,
  useFocus,
  useDismiss,
  useRole,
  useInteractions,
  safePolygon,
  offset,
  flip,
  shift,
  autoUpdate,
  FloatingPortal,
} from "@floating-ui/react"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { reactorsQueryOptions } from "@/api/hooks/messenger"

/**
 * Wave 207 — one reaction pill with a "who reacted" popover.
 *
 * Extracted as a component (not inlined in ChatWindow's `.map`) because each pill
 * needs its own `useFloating` + open-state hooks — hooks can't be called in a loop.
 *
 * Dual-purpose: tap/click TOGGLES the reaction (W206, preserved); the popover
 * listing reactors opens on desktop HOVER (mouse only), keyboard FOCUS (tooltip
 * a11y convention), and mobile LONG-PRESS (a `pointerType !== "mouse"` 500 ms timer,
 * which also suppresses the click that would otherwise toggle). Reactor identities
 * are fetched lazily (`enabled: isOpen && !!chatId`) — never bundled into the
 * message list.
 */

const LONG_PRESS_MS = 500

interface ReactionPillProps {
  /** Selected chat id — needed for the on-demand reactor query (absent in standalone tests). */
  chatId?: string
  messageId: string
  emoji: string
  count: number
  reactedByMe: boolean
  /** Toggle this emoji on this message (W206). No-op-safe when the parent omits the handler. */
  onToggle: (emoji: string) => void
}

export function ReactionPill({
  chatId,
  messageId,
  emoji,
  count,
  reactedByMe,
  onToggle,
}: ReactionPillProps) {
  // React Compiler opt-out (FIX-54-01 / RC-91-01 precedent): the imperative
  // long-press refs (longPressFiredRef / longPressTimerRef) + floating-ui's
  // ref-merging via getReferenceProps({onClick,...}) trip the Babel transform's
  // validateNoRefAccessInRender ("Cannot access refs during render"), even though
  // the refs are only touched in event handlers — a false positive. The Babel
  // transform FLAGS it (the build fails without this directive) but the eslint
  // plugin does NOT, so it calls the directive "unused" (W199 plugin-vs-transform
  // mismatch) — hence the paired disable, same as Dashboard.tsx FIX-54-01.
  // eslint-disable-next-line react-compiler/react-compiler -- Babel needs it; eslint thinks it unused
  "use no memo"
  const { t } = useTranslation(["messenger"])
  const [isOpen, setIsOpen] = useState(false)
  const longPressFiredRef = useRef(false)
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: setIsOpen,
    placement: "top",
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })

  // Desktop: mouse hover opens the reactor list (touch uses long-press below).
  // safePolygon lets the cursor cross the gap into the popover (to scroll a long
  // list) without it closing. Keyboard: focus opens it (WAI-ARIA tooltip convention).
  const hover = useHover(context, {
    mouseOnly: true,
    handleClose: safePolygon(),
    delay: { open: 250 },
  })
  const focus = useFocus(context)
  const dismiss = useDismiss(context)
  const role = useRole(context, { role: "tooltip" })
  const { getReferenceProps, getFloatingProps } = useInteractions([hover, focus, dismiss, role])

  // Fetch reactors only while the popover is open + we know which chat.
  const { data: reactors = [], isLoading } = useQuery({
    ...reactorsQueryOptions(chatId ?? "", messageId, emoji),
    enabled: isOpen && !!chatId,
  })

  const clearLongPress = () => {
    if (longPressTimerRef.current !== null) {
      clearTimeout(longPressTimerRef.current)
      longPressTimerRef.current = null
    }
  }

  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    // Mouse uses hover (above) — gate the long-press timer to touch/pen so a
    // desktop press-hold doesn't double-trigger.
    if (event.pointerType === "mouse") return
    longPressFiredRef.current = false
    clearLongPress()
    longPressTimerRef.current = setTimeout(() => {
      longPressFiredRef.current = true
      setIsOpen(true)
    }, LONG_PRESS_MS)
  }

  const handleClick = () => {
    // A long-press that opened the popover must NOT also toggle the reaction.
    if (longPressFiredRef.current) {
      longPressFiredRef.current = false
      return
    }
    onToggle(emoji)
  }

  return (
    <>
      <button
        ref={refs.setReference}
        type="button"
        data-reaction-ui
        aria-pressed={reactedByMe}
        aria-label={t("messenger:reactions.tally", { emoji, count })}
        {...getReferenceProps({
          onClick: handleClick,
          onPointerDown: handlePointerDown,
          onPointerUp: clearLongPress,
          onPointerLeave: clearLongPress,
          onPointerCancel: clearLongPress,
          onPointerMove: clearLongPress,
        })}
        className={cn(
          "inline-flex min-h-[28px] items-center gap-1 rounded-full border px-2 py-0.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-1 focus-visible:ring-offset-(--bg-surface)",
          reactedByMe
            ? "border-(--color-violet-500)/(--opacity-medium) bg-(--color-violet-500)/(--opacity-soft) text-(--text-primary)"
            : "border-(--color-violet-500)/(--opacity-faint) bg-(--bg-surface-raised)/(--opacity-medium) text-(--text-secondary) hover:bg-(--bg-surface-hover)/(--opacity-medium)"
        )}
      >
        <span aria-hidden="true">{emoji}</span>
        <span className="text-micro font-semibold tabular-nums">{count}</span>
      </button>
      {isOpen ? (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            style={floatingStyles}
            {...getFloatingProps()}
            data-reaction-ui
            className="z-popover max-w-[16rem] rounded-xl border border-glass-border bg-(--bg-surface)/(--opacity-heavy) p-2.5 shadow-glass backdrop-blur-xl"
          >
            <p className="mb-1.5 px-1 text-micro font-semibold uppercase tracking-wider text-(--text-secondary)">
              {t("messenger:reactions.whoReacted", { emoji })}
            </p>
            {isLoading ? (
              <p className="px-1 py-1 text-sm text-(--text-secondary)">
                {t("messenger:reactions.reactorsLoading")}
              </p>
            ) : reactors.length === 0 ? (
              <p className="px-1 py-1 text-sm text-(--text-secondary)">
                {t("messenger:reactions.reactorsEmpty")}
              </p>
            ) : (
              <ul className="custom-scrollbar max-h-48 space-y-1 overflow-y-auto">
                {reactors.map((reactor) => (
                  <li key={reactor.user_id} className="flex items-center gap-2 px-1 py-0.5">
                    <SmartImage
                      srcRaw={reactor.avatar_url || AVATAR_PLACEHOLDER_URL}
                      fallback={AVATAR_PLACEHOLDER_URL}
                      alt=""
                      className="size-6 shrink-0 rounded-full object-cover"
                    />
                    <span className="truncate text-sm text-(--text-primary)">
                      {reactor.name ?? t("messenger:replyTo.unknownSender")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </FloatingPortal>
      ) : null}
    </>
  )
}
