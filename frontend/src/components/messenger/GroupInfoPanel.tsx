import { memo, useEffect, useId, useState } from "react"
import { AnimatePresence, m } from "framer-motion"
import { Check, Crown, LogOut, Pencil, Search, Trash2, UserPlus, X } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import client from "@/api/client"
import type { Chat, PresenceStatus } from "@/api/chat"
import type { User } from "@/types/User"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { useDebounced } from "@/hooks/useDebounced"
import useFocusTrap from "@/hooks/useFocusTrap"
import useMediaQuery from "@/hooks/useMediaQuery"
import { GroupAvatar } from "./GroupAvatar"

interface GroupInfoPanelProps {
  open: boolean
  onClose: () => void
  /** The active group chat (participants + created_by + name). */
  chat: Chat | null
  currentUserId?: string
  presenceMap: Record<string, PresenceStatus>
  /** Rename the group (any member — backend authz, W209). */
  onRename: (name: string) => void
  /** Add a user as a member (any member). */
  onAddMember: (userId: string) => void
  /** Remove a member — kick (owner-only) OR self-leave (always). */
  onRemoveMember: (userId: string) => void
  isRenaming?: boolean
  isAddingMember?: boolean
}

const USERS_PAGE_LIMIT = 10
const MIN_SEARCH_LENGTH = 1

/**
 * Wave 211 G4 (SW10) — group info / member-management panel. Mirrors
 * ProfileModal's a11y shell (focus trap, role=dialog + aria-modal, Escape, matte
 * card, reduced-motion guards, 44px close). Authz mirrors the backend (W209):
 * rename + add = any member; KICK (remove someone else) = owner only
 * (created_by === currentUserId); LEAVE (remove self) = always.
 */
export const GroupInfoPanel = memo(function GroupInfoPanel({
  open,
  onClose,
  chat,
  currentUserId,
  presenceMap,
  onRename,
  onAddMember,
  onRemoveMember,
  isRenaming = false,
  isAddingMember = false,
}: GroupInfoPanelProps) {
  const { t } = useTranslation(["messenger", "common"])
  const titleId = useId()
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const [isEditingName, setIsEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState("")
  const [showAddSearch, setShowAddSearch] = useState(false)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebounced(search, "search")

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

  // Reset transient sub-state when the panel closes.
  useEffect(() => {
    if (open) return
    setIsEditingName(false)
    setNameDraft("")
    setShowAddSearch(false)
    setSearch("")
  }, [open])

  const members = chat?.participants ?? []
  const ownerId = chat?.created_by ?? null
  const isOwner = !!currentUserId && ownerId === currentUserId
  const memberIds = new Set(members.map((m) => String(m.id)))

  // Add-member search — exclude existing members from the results.
  const { data: searchResults = [], isLoading: searchLoading } = useQuery({
    queryKey: ["users", debouncedSearch],
    queryFn: async () => {
      const response = await client.get<User[]>(
        `/users?limit=${USERS_PAGE_LIMIT}&search=${debouncedSearch}`
      )
      return response.data
    },
    enabled: open && showAddSearch && debouncedSearch.length > MIN_SEARCH_LENGTH,
  })
  const addableResults = searchResults.filter((u) => !memberIds.has(String(u.id)))

  const startRename = () => {
    setNameDraft(chat?.name ?? "")
    setIsEditingName(true)
  }
  const saveRename = () => {
    const trimmed = nameDraft.trim()
    if (trimmed) onRename(trimmed)
    setIsEditingName(false)
  }

  return (
    <AnimatePresence>
      {open && chat && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-overlay flex items-center justify-center bg-overlay/(--opacity-strong) p-4 backdrop-blur-md"
          role="presentation"
          onClick={onClose}
        >
          <m.div
            ref={containerRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.92, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { scale: 0.92, opacity: 0, y: 20 }}
            transition={prefersReducedMotion ? { duration: 0 } : undefined}
            className="messenger-card-matte z-modal flex max-h-[85vh] w-full max-w-[28rem] flex-col md:max-w-[32rem]"
            onClick={(event) => event.stopPropagation()}
          >
            {/* Header — group identity + rename + close */}
            <div className="flex items-center justify-between border-b border-(--glass-border)/(--opacity-subtle) p-6 pb-4">
              <div className="flex min-w-0 items-center gap-3">
                <GroupAvatar className="size-11" iconSize={20} />
                <div className="min-w-0">
                  <h3 id={titleId} className="sf-pro truncate text-xl font-bold tracking-tight">
                    {chat.name?.trim() || t("messenger:group.untitled")}
                  </h3>
                  <p className="text-xs font-medium text-(--text-secondary)">
                    {t("messenger:group.members", { count: members.length })}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("common:buttons.close")}
                className="min-h-[44px] min-w-[44px] shrink-0 rounded-full p-2 flex items-center justify-center transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
              {/* Rename (any member) */}
              <div className="mb-5">
                {isEditingName ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={nameDraft}
                      onChange={(e) => setNameDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveRename()
                        if (e.key === "Escape") setIsEditingName(false)
                      }}
                      maxLength={128}
                      aria-label={t("messenger:groupName")}
                      // eslint-disable-next-line jsx-a11y/no-autofocus
                      autoFocus
                      className="matte-input flex-1 min-h-[44px] rounded-xl px-4 text-sm font-medium"
                    />
                    <button
                      type="button"
                      onClick={saveRename}
                      disabled={isRenaming || !nameDraft.trim()}
                      aria-label={t("common:buttons.save")}
                      className="messenger-send-btn flex size-11 shrink-0 items-center justify-center rounded-full text-(--color-white) disabled:opacity-medium disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                    >
                      <Check className="size-5" strokeWidth={2.5} aria-hidden="true" />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={startRename}
                    className="inline-flex min-h-[40px] items-center gap-2 rounded-xl px-3 text-sm font-semibold text-(--text-secondary) transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                  >
                    <Pencil className="size-4" strokeWidth={2} aria-hidden="true" />
                    {t("messenger:renameGroup")}
                  </button>
                )}
              </div>

              {/* Add members (any member) */}
              <div className="mb-4">
                {showAddSearch ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <Search
                          className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-(--text-secondary)"
                          aria-hidden="true"
                        />
                        <input
                          type="text"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder={t("messenger:searchUsers")}
                          aria-label={t("messenger:searchUsers")}
                          // eslint-disable-next-line jsx-a11y/no-autofocus
                          autoFocus
                          className="matte-input w-full min-h-[44px] rounded-xl pl-10 pr-4 text-sm font-medium"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setShowAddSearch(false)
                          setSearch("")
                        }}
                        aria-label={t("common:buttons.cancel")}
                        className="flex size-11 shrink-0 items-center justify-center rounded-full text-(--text-secondary) transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                      >
                        <X className="size-5" aria-hidden="true" />
                      </button>
                    </div>
                    {!searchLoading &&
                      addableResults.length === 0 &&
                      search.length > MIN_SEARCH_LENGTH && (
                        <p className="px-2 py-3 text-center text-xs font-medium text-(--text-secondary) opacity-medium">
                          {t("messenger:noUsersFound")}
                        </p>
                      )}
                    {addableResults.map((u) => (
                      <button
                        key={u.id}
                        type="button"
                        disabled={isAddingMember}
                        onClick={() => onAddMember(String(u.id))}
                        className="flex w-full min-h-[52px] items-center gap-3 rounded-2xl p-2.5 text-left transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) disabled:opacity-medium disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                      >
                        <SmartImage
                          srcRaw={u.avatar_url || AVATAR_PLACEHOLDER_URL}
                          fallback={AVATAR_PLACEHOLDER_URL}
                          alt=""
                          className="size-9 rounded-full object-cover shadow-sm"
                        />
                        <span className="flex-1 truncate text-sm font-bold text-text-primary sf-pro">
                          {u.full_name}
                        </span>
                        <UserPlus
                          className="size-4 shrink-0 text-(--color-violet-500)"
                          strokeWidth={2}
                          aria-hidden="true"
                        />
                      </button>
                    ))}
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setShowAddSearch(true)}
                    className="inline-flex min-h-[44px] items-center gap-2 rounded-full px-4 text-sm font-semibold text-(--color-violet-500) transition-colors hover:bg-(--color-violet-500)/(--opacity-subtle) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                  >
                    <UserPlus className="size-4" strokeWidth={2.25} aria-hidden="true" />
                    {t("messenger:addMember")}
                  </button>
                )}
              </div>

              {/* Member list */}
              <ul
                className="space-y-1"
                aria-label={t("messenger:group.members", { count: members.length })}
              >
                {members.map((member) => {
                  const id = String(member.id)
                  const isSelf = id === currentUserId
                  const isMemberOwner = ownerId === id
                  const online = presenceMap[id]?.active
                  // Owner can kick anyone but themselves; everyone can leave (self).
                  const canRemove = isSelf || (isOwner && !isMemberOwner)
                  return (
                    <li
                      key={id}
                      className="flex items-center gap-3 rounded-2xl p-2.5 transition-colors hover:bg-(--bg-surface-hover)/(--opacity-faint)"
                    >
                      <div className="relative shrink-0">
                        <SmartImage
                          srcRaw={member.avatar_url || AVATAR_PLACEHOLDER_URL}
                          fallback={AVATAR_PLACEHOLDER_URL}
                          alt=""
                          className="size-10 rounded-full object-cover shadow-sm"
                        />
                        {online && (
                          <span
                            className="messenger-online-indicator absolute bottom-0 right-0 size-3 border-2 border-(--bg-surface)"
                            aria-hidden="true"
                          />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-bold text-text-primary sf-pro">
                          {member.full_name}
                          {isSelf && (
                            <span className="ml-1.5 text-xs font-medium text-(--text-secondary) opacity-medium">
                              {t("messenger:memberYou")}
                            </span>
                          )}
                        </p>
                        {isMemberOwner && (
                          <span className="inline-flex items-center gap-1 text-xs font-semibold text-(--color-violet-500)">
                            <Crown className="size-3" strokeWidth={2.25} aria-hidden="true" />
                            {t("messenger:groupOwner")}
                          </span>
                        )}
                      </div>
                      {canRemove && (
                        <button
                          type="button"
                          onClick={() => onRemoveMember(id)}
                          aria-label={
                            isSelf
                              ? t("messenger:leaveGroup")
                              : t("messenger:removeMember", { name: member.full_name })
                          }
                          className="flex size-9 shrink-0 items-center justify-center rounded-full text-(--text-secondary) transition-colors hover:bg-(--error-text)/(--opacity-subtle) hover:text-(--error-text) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--error-text)"
                        >
                          {isSelf ? (
                            <LogOut className="size-4" strokeWidth={2} aria-hidden="true" />
                          ) : (
                            <Trash2 className="size-4" strokeWidth={2} aria-hidden="true" />
                          )}
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>

            {/* Leave group (always) */}
            <div className="border-t border-(--glass-border)/(--opacity-subtle) p-6 pt-4">
              <button
                type="button"
                onClick={() => currentUserId && onRemoveMember(currentUserId)}
                className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-full px-5 text-sm font-bold text-(--error-text) transition-colors hover:bg-(--error-text)/(--opacity-subtle) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--error-text)"
              >
                <LogOut className="size-4" strokeWidth={2.25} aria-hidden="true" />
                {t("messenger:leaveGroup")}
              </button>
            </div>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
})

export default GroupInfoPanel
