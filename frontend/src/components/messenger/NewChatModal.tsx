import { useEffect, useId, useRef, useState } from "react"
import { m, AnimatePresence } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { Check, RotateCcw, Search, TriangleAlert, Users, X } from "lucide-react"
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
  /**
   * Wave 211 G4 — create a group (name + ≥2 selected members). When provided, a
   * DM/Group mode toggle appears; when absent, the modal stays DM-only (the
   * pre-W211 behavior — keeps existing consumers + tests/stories unchanged).
   */
  onCreateGroup?: (name: string, participantIds: string[]) => void
  /** Group-create mutation in-flight — disables the Create button + rows. */
  isCreatingGroup?: boolean
}

const USERS_PAGE_LIMIT = 10
const MIN_SEARCH_LENGTH = 1
// Wave 211 G4 — backend requires ≥3 total participants (creator + members); the
// creator is auto-included, so the user must select at least 2 others.
const MIN_GROUP_MEMBERS = 2
const MAX_GROUP_NAME_LENGTH = 128

export function NewChatModal({
  open,
  onClose,
  onSelect,
  onCreateGroup,
  isCreatingGroup = false,
}: NewChatModalProps) {
  const { t } = useTranslation(["messenger", "common"])
  const [search, setSearch] = useState("")
  // Wave 211 G4 — group-create mode. The toggle only appears when onCreateGroup
  // is provided (else DM-only, the pre-W211 behavior). selectedUsers holds full
  // User objects so the chips can show name/avatar without a re-lookup.
  const canCreateGroup = !!onCreateGroup
  const [mode, setMode] = useState<"dm" | "group">("dm")
  const [groupName, setGroupName] = useState("")
  const [selectedUsers, setSelectedUsers] = useState<User[]>([])
  const isGroupMode = canCreateGroup && mode === "group"
  const titleId = useId()
  // PERF-20-05: Debounce to prevent API call on every keystroke.
  const debouncedSearch = useDebounced(search, "default") // PERF-23-04: messenger search uses default preset (300ms)
  // Wave 181 SW5 — explicit useReducedMotion guards on DRAMATIC animations
  // (dialog entrance scale:0.95+y:20 and per-row whileHover x:4). Subtle
  // scale-on-hover/tap motions are handled globally by AppProviders
  // MotionConfig reducedMotion="user" (W124 SW1 + W127 SW1).
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // Wave 175 SW3 — focus trap + Escape handler.
  // initialFocus: false lets the TextField's auto-focus (line ~95) win without
  // focus-trap competing for the same target on mount.
  const containerRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: onClose,
    initialFocus: false,
    returnFocus: true,
  })

  // Wave 183 SW4 — replaced ref-callback setTimeout antipattern with proper
  // useEffect-driven autofocus. Pre-W183 the TextField ref callback ran on
  // EVERY render with `setTimeout(() => input.focus(), 0)` which (a)
  // re-triggered focus on rerender (bad UX if user typed + caused re-render),
  // (b) competed with focus-trap initialization, (c) was SSR-unsafe (no
  // typeof window guard around setTimeout, though SSR doesn't reach this
  // branch — the `open` gate prevents render entirely when modal closed).
  // useEffect with [open] dep fires ONCE on modal open + RAF-defers to next
  // frame after the dialog is mounted in DOM.
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  useEffect(() => {
    if (!open) return
    const rafId = requestAnimationFrame(() => searchInputRef.current?.focus())
    return () => cancelAnimationFrame(rafId)
  }, [open])

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

  // Wave 211 G4 — reset group-create state when the modal closes so the next
  // open starts clean (DM mode, no name, no selection, no stale search).
  useEffect(() => {
    if (open) return
    setMode("dm")
    setGroupName("")
    setSelectedUsers([])
    setSearch("")
  }, [open])

  // Wave 211 G4 — group-create derived state + helpers.
  const trimmedGroupName = groupName.trim()
  const selectedIds = new Set(selectedUsers.map((u) => String(u.id)))
  const canSubmitGroup =
    isGroupMode &&
    trimmedGroupName.length > 0 &&
    selectedUsers.length >= MIN_GROUP_MEMBERS &&
    !isCreatingGroup

  const toggleUserSelection = (user: User) => {
    setSelectedUsers((prev) =>
      prev.some((u) => String(u.id) === String(user.id))
        ? prev.filter((u) => String(u.id) !== String(user.id))
        : [...prev, user]
    )
  }

  const handleSubmitGroup = () => {
    if (!canSubmitGroup || !onCreateGroup) return
    onCreateGroup(
      trimmedGroupName,
      selectedUsers.map((u) => String(u.id))
    )
  }

  // Wave 184 SW3 (Path B) — additionally destructure `isError` + `refetch`
  // so the search dropdown can render a fetch-failure state with Retry
  // CTA. Pre-W184 a /users search failure rendered the W183 SW4
  // "noUsersFound" branch wrongly — user couldn't distinguish "no matches"
  // from "network error".
  const {
    data: users = [],
    isLoading,
    isError,
    refetch: refetchUsers,
  } = useQuery({
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
            initial={prefersReducedMotion ? false : { scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { scale: 0.95, opacity: 0, y: 20 }}
            transition={prefersReducedMotion ? { duration: 0 } : undefined}
            className="messenger-card-matte w-full max-w-[28rem] backdrop-blur-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="p-6 pb-4 flex items-center justify-between border-b border-(--glass-border)/(--opacity-subtle) bg-(--bg-surface)/(--opacity-medium)">
              <h3
                id={titleId}
                className="text-xl font-black tracking-tight text-text-primary sf-pro"
              >
                {isGroupMode ? t("messenger:newGroup") : t("messenger:newChat")}
              </h3>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("common:buttons.close")}
                className="min-h-[44px] min-w-[44px] p-2 rounded-xl flex items-center justify-center hover:bg-(--bg-surface-hover)/(--opacity-medium) text-(--text-secondary) transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            <div className="p-6">
              {/* Wave 211 G4 — DM/Group mode toggle (only when group-create is
                  wired via onCreateGroup; else the modal stays DM-only). */}
              {canCreateGroup && (
                <div
                  className="mb-4 grid grid-cols-2 gap-1 rounded-2xl bg-(--bg-surface-raised)/(--opacity-medium) p-1"
                  role="tablist"
                  aria-label={t("messenger:modeToggle")}
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={!isGroupMode}
                    onClick={() => setMode("dm")}
                    className={`min-h-[40px] rounded-xl px-4 text-sm font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) ${
                      !isGroupMode
                        ? "bg-(--color-violet-500) text-(--color-white) shadow-sm"
                        : "text-(--text-secondary) hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                    }`}
                  >
                    {t("messenger:modeDirect")}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={isGroupMode}
                    onClick={() => setMode("group")}
                    className={`min-h-[40px] inline-flex items-center justify-center gap-1.5 rounded-xl px-4 text-sm font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) ${
                      isGroupMode
                        ? "bg-(--color-violet-500) text-(--color-white) shadow-sm"
                        : "text-(--text-secondary) hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                    }`}
                  >
                    <Users className="size-4" strokeWidth={2.25} aria-hidden="true" />
                    {t("messenger:modeGroup")}
                  </button>
                </div>
              )}

              {/* Wave 211 G4 — group name field + the selected-member chip row
                  (a chip tap removes that member). */}
              {isGroupMode && (
                <div className="mb-4 space-y-3">
                  <TextField
                    value={groupName}
                    onChange={(e) => setGroupName(e.target.value)}
                    placeholder={t("messenger:groupName")}
                    aria-label={t("messenger:groupName")}
                    maxLength={MAX_GROUP_NAME_LENGTH}
                    className="w-full"
                  />
                  {selectedUsers.length > 0 && (
                    <div className="flex flex-wrap gap-2" aria-label={t("messenger:selectMembers")}>
                      {selectedUsers.map((u) => (
                        <button
                          key={u.id}
                          type="button"
                          onClick={() => toggleUserSelection(u)}
                          aria-label={t("messenger:removeMember", { name: u.full_name })}
                          className="matte-chip inline-flex items-center gap-1.5 rounded-full py-1 pl-1 pr-2.5 text-sm font-semibold text-(--text-primary) transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                        >
                          <SmartImage
                            srcRaw={u.avatar_url || AVATAR_PLACEHOLDER_URL}
                            fallback={AVATAR_PLACEHOLDER_URL}
                            alt=""
                            className="size-6 rounded-full object-cover"
                          />
                          <span className="max-w-[8rem] truncate">{u.full_name}</span>
                          <X className="size-3.5 shrink-0" aria-hidden="true" />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <TextField
                leadingIcon={<Search className="w-4.5 h-4.5" />}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("messenger:searchUsers")}
                aria-label={t("messenger:searchUsers")}
                className="w-full"
                ref={searchInputRef}
              />

              <div className="max-h-96 overflow-y-auto custom-scrollbar pr-1 -mr-1">
                {/* Wave 184 SW2 (Path B) — replaced spinner with .messenger-skeleton
                    rows matching real user-row dimensions (h-[60px], size-11 avatar,
                    2-line text stack). Pre-W184 the centered spinner was a generic
                    loading visual that didn't telegraph the row count or layout
                    of the eventual results — skeleton rows give users a visual
                    preview of what's coming. W183 SW4 a11y semantics preserved
                    (role=status + aria-live=polite + aria-label). */}
                {isLoading && (
                  <div
                    className="space-y-1"
                    role="status"
                    aria-live="polite"
                    aria-label={t("messenger:loading.users")}
                  >
                    {Array.from({ length: 5 }).map((_, idx) => (
                      <div
                        key={`user-skeleton-${idx}`}
                        className="flex items-center gap-4 p-3.5 rounded-2xl min-h-[60px]"
                        aria-hidden="true"
                      >
                        <div className="messenger-skeleton w-11 h-11 rounded-2xl shrink-0" />
                        <div className="flex flex-1 flex-col gap-2 min-w-0">
                          <div
                            className="messenger-skeleton h-4 rounded-md"
                            style={{ width: `${55 + ((idx * 13) % 30)}%` }}
                          />
                          <div
                            className="messenger-skeleton h-3 rounded-md"
                            style={{ width: `${35 + ((idx * 7) % 30)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Wave 184 SW3 (Path B) — fetch-failure branch. Renders
                    when the /users search query errored AND not currently
                    loading (so refetch-in-flight shows the spinner, not
                    the stale error). TriangleAlert + matte container +
                    Retry button matches ContactList isError pattern. */}
                {!isLoading && isError && (
                  <div
                    className="flex flex-col items-center py-10 px-4 text-center"
                    role="alert"
                    aria-live="assertive"
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
                    <h4 className="sf-pro mb-2 text-base font-bold leading-tight text-(--text-primary)">
                      {t("messenger:error.failedToLoadUsers")}
                    </h4>
                    <p className="mb-5 text-sm leading-relaxed text-(--text-secondary)">
                      {t("messenger:error.failedToLoadUsersHint")}
                    </p>
                    <m.button
                      type="button"
                      whileHover={prefersReducedMotion ? undefined : { scale: 1.04 }}
                      whileTap={prefersReducedMotion ? undefined : { scale: 0.96 }}
                      onClick={() => {
                        void refetchUsers()
                      }}
                      className="messenger-send-btn inline-flex min-h-[44px] items-center gap-2 rounded-full px-5 text-sm font-semibold text-(--text-inverse) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
                    >
                      <RotateCcw className="size-4" strokeWidth={2.5} aria-hidden="true" />
                      <span>{t("messenger:error.retry")}</span>
                    </m.button>
                  </div>
                )}

                {!isLoading &&
                  !isError &&
                  users.length === 0 &&
                  search.length > MIN_SEARCH_LENGTH && (
                    <div
                      className="text-center py-12 px-4 space-y-2"
                      role="status"
                      aria-live="polite"
                    >
                      <div
                        className="w-16 h-16 rounded-full bg-(--bg-surface-raised) mx-auto flex items-center justify-center text-(--text-secondary) opacity-dim"
                        aria-hidden="true"
                      >
                        <Search className="w-8 h-8" />
                      </div>
                      <p className="text-sm font-bold text-(--text-secondary) opacity-medium">
                        {t("messenger:noUsersFound")}
                      </p>
                    </div>
                  )}

                {/* Wave 183 SW4 — added role=listbox on container + role=option on
                    each user row so screen readers announce "list of N options"
                    and let users navigate with arrow keys (WCAG 4.1.2 Name, Role,
                    Value + ARIA APG combobox/listbox pattern). aria-label on
                    container declares the list purpose; aria-busy hides children
                    during async load to suppress "X options" announcement during
                    fetch. */}
                <div
                  className="space-y-1"
                  role="listbox"
                  aria-label={t("messenger:searchUsers")}
                  aria-busy={isLoading}
                >
                  {users.map((user) => {
                    // Wave 211 G4 — group mode: a row tap toggles selection (the
                    // Check indicator + violet tint reflect it); DM mode keeps the
                    // single-select onSelect.
                    const isSelected = selectedIds.has(String(user.id))
                    return (
                      <m.button
                        key={user.id}
                        type="button"
                        role="option"
                        aria-selected={isGroupMode ? isSelected : false}
                        disabled={isGroupMode && isCreatingGroup}
                        whileHover={
                          prefersReducedMotion
                            ? undefined
                            : { x: 4, backgroundColor: "var(--bg-surface-hover)" }
                        }
                        whileTap={prefersReducedMotion ? undefined : { scale: 0.98 }}
                        onClick={() =>
                          isGroupMode ? toggleUserSelection(user) : onSelect(String(user.id))
                        }
                        className={`w-full min-h-[60px] flex items-center gap-4 p-3.5 rounded-2xl transition-all text-left group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface) disabled:opacity-medium disabled:cursor-not-allowed ${
                          isSelected ? "bg-(--messenger-active-bg)" : ""
                        }`}
                      >
                        <div className="relative shrink-0">
                          <SmartImage
                            srcRaw={user.avatar_url || AVATAR_PLACEHOLDER_URL}
                            fallback={AVATAR_PLACEHOLDER_URL}
                            alt=""
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
                        {isGroupMode && (
                          <span
                            className={`flex size-6 shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
                              isSelected
                                ? "border-(--color-violet-500) bg-(--color-violet-500) text-(--color-white)"
                                : "border-(--glass-border)"
                            }`}
                            aria-hidden="true"
                          >
                            {isSelected && <Check className="size-3.5" strokeWidth={3} />}
                          </span>
                        )}
                      </m.button>
                    )
                  })}
                </div>
              </div>

              {/* Wave 211 G4 — group-create CTA + the min-members hint. Disabled
                  until a non-empty name + ≥2 selected (backend ≥3 total). */}
              {isGroupMode && (
                <div className="mt-4 border-t border-(--glass-border)/(--opacity-subtle) pt-4">
                  <button
                    type="button"
                    onClick={handleSubmitGroup}
                    disabled={!canSubmitGroup}
                    className="messenger-send-btn flex min-h-[44px] w-full items-center justify-center gap-2 rounded-full px-5 text-sm font-bold text-(--color-white) transition-opacity disabled:opacity-medium disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
                  >
                    <Users className="size-4" strokeWidth={2.25} aria-hidden="true" />
                    <span>
                      {isCreatingGroup ? t("messenger:creatingGroup") : t("messenger:createGroup")}
                    </span>
                  </button>
                  {selectedUsers.length < MIN_GROUP_MEMBERS && (
                    <p className="mt-2 text-center text-xs font-medium text-(--text-secondary) opacity-medium">
                      {t("messenger:error.minMembers")}
                    </p>
                  )}
                </div>
              )}
            </div>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
