import React, { useEffect, useId, useState } from "react"
import { m, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { Search, X } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import client from "@/api/client"
import type { User } from "@/types/User"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { TextField } from "@/components/ui"
// PERF-20-05 (audit 2026-03-24): Debounce search to prevent API spam.
import { useDebounced } from "@/hooks/useDebounced"
import useFocusTrap from "@/hooks/useFocusTrap"

interface NewChatModalProps {
  open: boolean
  onClose: () => void
  onSelect: (userId: string) => void
}

const USERS_PAGE_LIMIT = 10
const MIN_SEARCH_LENGTH = 1

export const NewChatModal: React.FC<NewChatModalProps> = ({ open, onClose, onSelect }) => {
  const { t } = useTranslation(["messenger", "common"])
  const [search, setSearch] = useState("")
  const titleId = useId()
  // PERF-20-05: Debounce to prevent API call on every keystroke.
  const debouncedSearch = useDebounced(search, "default") // PERF-23-04: messenger search uses default preset (300ms)

  // Wave 175 SW3 — focus trap + Escape handler.
  // initialFocus: false lets the TextField's auto-focus (line ~95) win without
  // focus-trap competing for the same target on mount.
  const containerRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: onClose,
    initialFocus: false,
    returnFocus: true,
  })

  useEffect(() => {
    if (!open) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open, onClose])

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users", debouncedSearch],
    queryFn: async () => {
      if (!debouncedSearch) return []
      const response = await client.get<User[]>(
        `/users?limit=${USERS_PAGE_LIMIT}&search=${debouncedSearch}`
      )
      return response.data
    },
    enabled: open && debouncedSearch.length > MIN_SEARCH_LENGTH,
  })

  return (
    <AnimatePresence>
      {open && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 flex items-center justify-center z-modal p-4"
          role="presentation"
        >
          <div
            className="absolute inset-0 bg-black/(--opacity-strong) backdrop-blur-md cursor-default"
            onClick={onClose}
            aria-hidden="true"
          />
          <m.div
            ref={containerRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
            className="bg-(--bg-surface)/(--opacity-heavy) backdrop-blur-2xl rounded-3xl shadow-premium w-full max-w-[28rem] overflow-hidden border border-(--glass-border) ring-1 ring-white/(--opacity-subtle)"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="p-6 pb-4 flex items-center justify-between border-b border-(--glass-border)/(--opacity-subtle) bg-(--bg-surface)/(--opacity-medium)">
              <h3
                id={titleId}
                className="text-xl font-black tracking-tight text-text-primary sf-pro"
              >
                {t("messenger:newChat", "New Chat")}
              </h3>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("common:buttons.close")}
                className="p-2 rounded-xl hover:bg-(--bg-surface-hover)/(--opacity-medium) text-(--text-secondary) transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            <div className="p-6">
              <TextField
                leadingIcon={<Search className="w-4.5 h-4.5" />}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("messenger:searchUsers", "Search users by name or email...")}
                className="w-full"
                ref={(input) => {
                  if (input && open) {
                    setTimeout(() => input.focus(), 0)
                  }
                }}
              />

              <div className="max-h-96 overflow-y-auto custom-scrollbar pr-1 -mr-1">
                {isLoading && (
                  <div className="flex flex-col items-center py-10">
                    <div className="w-10 h-10 border-4 border-brand/(--opacity-subtle) border-t-brand rounded-full animate-spin"></div>
                  </div>
                )}

                {!isLoading && users.length === 0 && search.length > MIN_SEARCH_LENGTH && (
                  <div className="text-center py-12 px-4 space-y-2">
                    <div className="w-16 h-16 rounded-full bg-(--bg-surface-raised) mx-auto flex items-center justify-center text-(--text-secondary) opacity-dim">
                      <Search className="w-8 h-8" />
                    </div>
                    <p className="text-sm font-bold text-(--text-secondary) opacity-medium">
                      {t("messenger:noUsersFound", "No users found matching your search")}
                    </p>
                  </div>
                )}

                <div className="space-y-1">
                  {users.map((user) => (
                    <m.button
                      key={user.id}
                      type="button"
                      whileHover={{ x: 4, backgroundColor: "var(--bg-surface-hover)" }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => onSelect(String(user.id))}
                      className="w-full flex items-center gap-4 p-3.5 rounded-2xl transition-all text-left group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
                    >
                      <div className="relative shrink-0">
                        <SmartImage
                          srcRaw={user.avatar_url || AVATAR_PLACEHOLDER_URL}
                          fallback={AVATAR_PLACEHOLDER_URL}
                          alt={user.full_name || ""}
                          className="w-11 h-11 rounded-2xl object-cover shadow-sm ring-1 ring-black/(--opacity-faint)"
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-base font-black truncate leading-tight text-text-primary group-hover:text-brand transition-colors sf-pro">
                          {user.full_name}
                        </p>
                        <p className="text-xs text-(--text-secondary) truncate font-medium opacity-medium">
                          {user.email}
                        </p>
                      </div>
                    </m.button>
                  ))}
                </div>
              </div>
            </div>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
