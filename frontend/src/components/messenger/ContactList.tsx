import { m, useReducedMotion } from "framer-motion"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { Contact } from "./types"

interface ContactListProps {
  contacts: Contact[]
  selectedId: string | null
  onSelect: (id: string) => void
}

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
export function ContactList({ contacts, selectedId, onSelect }: ContactListProps) {
  const prefersReducedMotion = useReducedMotion() ?? false
  const hoverAnim = prefersReducedMotion ? undefined : { x: 4 }
  const tapAnim = prefersReducedMotion ? undefined : { scale: 0.98 }

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
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                onSelect(contact.id)
              }
            }}
            whileHover={hoverAnim}
            whileTap={tapAnim}
            className={cn(
              "msg-contact-item messenger-stagger-item flex items-center gap-3 p-3 mb-1 rounded-2xl cursor-pointer transition-all duration-base min-h-[60px]",
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
                <span className="msg-online-indicator absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-(--success-bg) border-2 border-(--bg-surface) dark:border-(--bg-page)"></span>
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
                    className="msg-unread-badge min-w-5 h-5 px-1 bg-(--error-text) text-[var(--text-inverse)] rounded-full text-label-xs font-black flex items-center justify-center shadow-lg shadow-(--error-text)/(--opacity-dim)"
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
