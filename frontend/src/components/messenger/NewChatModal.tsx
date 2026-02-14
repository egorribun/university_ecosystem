import React, { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { Search, X } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import client from "../../api/client"
import type { User } from "../../types/User"
import SmartImage from "@/components/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"

interface NewChatModalProps {
  open: boolean
  onClose: () => void
  onSelect: (userId: string) => void
}

export const NewChatModal: React.FC<NewChatModalProps> = ({ open, onClose, onSelect }) => {
  const { t } = useTranslation(["messenger", "common"])
  const [search, setSearch] = useState("")

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users", search],
    queryFn: async () => {
      if (!search) return []
      const response = await client.get<User[]>(`/users?limit=10&search=${search}`)
      return response.data
    },
    enabled: open && search.length > 1,
  })

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/(--opacity-strong) backdrop-blur-md flex items-center justify-center z-(--z-modal) p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
            className="bg-(--bg-surface)/(--opacity-heavy) backdrop-blur-2xl rounded-3xl shadow-premium w-full max-w-md overflow-hidden border border-(--glass-border) ring-1 ring-white/(--opacity-subtle)"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="p-6 pb-4 flex items-center justify-between border-b border-(--glass-border)/(--opacity-subtle) bg-(--bg-surface)/(--opacity-medium)">
              <h3 className="text-xl font-black tracking-tight text-(--text-primary) sf-pro">
                {t("messenger:newChat", "New Chat")}
              </h3>
              <button
                onClick={onClose}
                className="p-2 rounded-xl hover:bg-(--bg-surface-hover)/(--opacity-medium) text-(--text-secondary) transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6">
              <div className="relative group mb-6">
                <Search className="w-4.5 h-4.5 absolute left-3.5 top-1/2 -translate-y-1/2 text-(--text-secondary) group-focus-within:text-(--brand-main) transition-colors" />
                <input
                  type="text"
                  ref={(input) => {
                    if (input && open) {
                      setTimeout(() => input.focus(), 0)
                    }
                  }}
                  placeholder={t("messenger:searchUsers", "Search users by name or email...")}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="w-full pl-11 pr-4 py-3 rounded-2xl border border-(--glass-border)/(--opacity-dim) bg-(--bg-surface-raised)/(--opacity-medium) focus:ring-4 focus:ring-(--brand-main)/(--opacity-subtle) focus:border-(--brand-main)/(--opacity-soft) outline-none transition-all text-base font-medium text-(--text-primary) placeholder:text-(--text-secondary) placeholder:opacity-medium"
                />
              </div>

              <div className="max-h-[350px] overflow-y-auto custom-scrollbar pr-1 -mr-1">
                {isLoading && (
                  <div className="flex flex-col items-center py-10">
                    <div className="w-10 h-10 border-4 border-(--brand-main)/(--opacity-subtle) border-t-(--brand-main) rounded-full animate-spin"></div>
                  </div>
                )}

                {!isLoading && users.length === 0 && search.length > 1 && (
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
                    <motion.button
                      key={user.id}
                      whileHover={{ x: 4, backgroundColor: "var(--bg-surface-hover)" }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => onSelect(String(user.id))}
                      className="w-full flex items-center gap-4 p-3.5 rounded-2xl transition-all text-left group"
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
                        <p className="text-base font-black truncate leading-tight text-(--text-primary) group-hover:text-(--brand-main) transition-colors sf-pro">
                          {user.full_name}
                        </p>
                        <p className="text-xs text-(--text-secondary) truncate font-medium opacity-medium">
                          {user.email}
                        </p>
                      </div>
                    </motion.button>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
