import { motion, LayoutGroup } from "framer-motion"
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
export function ContactList({ contacts, selectedId, onSelect }: ContactListProps) {
  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar p-2 bg-(--msg-sidebar-bg)">
      <LayoutGroup>
        {contacts.map((contact) => (
          <motion.div
            layout
            key={contact.id}
            id={`messenger-contact-${contact.id}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(contact.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                onSelect(contact.id)
              }
            }}
            whileHover={{ x: 4 }}
            whileTap={{ scale: 0.98 }}
            className={cn(
              "msg-contact-item flex items-center gap-3 p-3 mb-1 rounded-2xl cursor-pointer transition-all duration-base",
              selectedId === contact.id
                ? "active bg-(--brand-main) text-white"
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
                <h3
                  className={cn(
                    "font-bold text-base truncate sf-pro",
                    selectedId === contact.id ? "text-white" : "text-text-primary"
                  )}
                >
                  {contact.name}
                </h3>
                <span
                  className={cn(
                    "text-xs shrink-0 ml-2 font-medium uppercase tracking-tight",
                    selectedId === contact.id
                      ? "text-white/(--opacity-strong)"
                      : "text-(--text-secondary) opacity-medium"
                  )}
                >
                  {contact.lastMessageTime}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <p
                  className={cn(
                    "text-sm truncate flex-1 leading-tight",
                    selectedId === contact.id
                      ? "text-white/(--opacity-hover)"
                      : "text-(--text-secondary)"
                  )}
                >
                  {contact.lastMessage}
                </p>
                {contact.unread > 0 && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="msg-unread-badge min-w-5 h-5 px-1 bg-(--error-text) text-white rounded-full text-label-xs font-black flex items-center justify-center shadow-lg shadow-(--error-text)/(--opacity-dim)"
                  >
                    {contact.unread > 99 ? "99+" : contact.unread}
                  </motion.span>
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </LayoutGroup>
    </div>
  )
}
