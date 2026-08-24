import { ContactList } from "@/components/messenger"
import { TextField } from "@/components/ui"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import useMediaQuery from "@/hooks/useMediaQuery"
import { m } from "framer-motion"
import { Search, SquarePen } from "lucide-react"
import { Dispatch, SetStateAction, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"

interface MessengerSidebarProps {
  isMobile: boolean
  contacts: ReturnType<typeof useMessengerController>["contacts"]
  selectedChatId: string | null
  setIsNewChatModalOpen: Dispatch<SetStateAction<boolean>>
  /**
   * Wave 184 SW2 (Path B) — chats list query loading flag lifted from
   * useMessengerController (`chatsLoading` at hook line 451). When true,
   * ContactList renders skeleton rows BEFORE checking contacts.length === 0
   * so the user sees first-paint feedback during async fetch rather than
   * the W183 SW1 "No conversations yet" empty state flashing briefly.
   */
  isLoading?: boolean
  /**
   * Wave 184 SW3 (Path B) — chats list query error flag lifted from
   * useMessengerController. When true, ContactList renders a fetch-failure
   * error empty state with Retry CTA BEFORE the contacts-empty branch.
   * Distinguishes "no chats" (W183 SW1 empty state) from "network error"
   * (this branch) so users have an actionable retry path.
   */
  isError?: boolean
  /**
   * Wave 184 SW3 (Path B) — retry callback wired to React Query's
   * `refetch()` (typically `() => { void refetchChats() }`). Invoked
   * when the user clicks the Retry button inside the error empty state.
   */
  onRetry?: () => void
}

const MOBILE_MENU_WIDTH = 300

export function MessengerSidebar({
  isMobile,
  contacts,
  selectedChatId,
  setIsNewChatModalOpen,
  isLoading = false,
  isError = false,
  onRetry,
}: MessengerSidebarProps) {
  const { t } = useTranslation(["messenger", "common"])
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState("")
  // Wave 181 SW3 — useReducedMotion guards new-chat button micro-interactions
  // + sidebar slide-in/out transitions (Framer Motion already provides motion
  // reduction at MotionConfig level via W127 hoist, but framer-motion docs
  // recommend explicit per-component guards for prop-level control).
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const newChatHoverAnim = prefersReducedMotion
    ? undefined
    : { scale: 1.08, backgroundColor: "var(--msg-sidebar-hover)" }
  const newChatTapAnim = prefersReducedMotion ? undefined : { scale: 0.94 }
  const sidebarInitial =
    isMobile && !prefersReducedMotion ? { x: -MOBILE_MENU_WIDTH, opacity: 0 } : undefined
  const sidebarExit =
    isMobile && !prefersReducedMotion ? { x: -MOBILE_MENU_WIDTH, opacity: 0 } : undefined

  // Wave 183 SW1 — Filter contacts by search query. Search input previously
  // had no effect on the rendered list (the search query was local state
  // disconnected from ContactList). Now matches user expectation that typing
  // narrows the contact list by name + last-message preview. Search empty
  // state is rendered by ContactList itself (isSearchActive prop + dedicated
  // "no results found" variant).
  const normalisedSearch = searchQuery.trim().toLowerCase()
  const isSearchActive = normalisedSearch.length > 0
  const filteredContacts = useMemo(() => {
    if (!isSearchActive) return contacts
    return contacts.filter((contact) => {
      const name = contact.name.toLowerCase()
      const lastMessage = contact.lastMessage.toLowerCase()
      return name.includes(normalisedSearch) || lastMessage.includes(normalisedSearch)
    })
  }, [contacts, isSearchActive, normalisedSearch])

  const handleStartNewChat = () => setIsNewChatModalOpen(true)
  const handleClearSearch = () => setSearchQuery("")

  return (
    <m.div
      key="sidebar"
      initial={sidebarInitial}
      animate={{ x: 0, opacity: 1 }}
      exit={sidebarExit}
      transition={
        prefersReducedMotion ? { duration: 0 } : { duration: 0.4, ease: [0.22, 1, 0.36, 1] }
      }
      className="panel-glass relative z-deep flex h-full w-full flex-col md:w-(--layout-max-sidebar) lg:w-(--layout-max-sidebar)"
    >
      {/* Wave 183 polish-v1: dropped `.header-glass border-b` cheap divider +
          `bg-(--bg-surface-raised)` search wrapper that introduced a hard
          background-color edge against the chat list below. Header + search
          now share the panel-glass surface; ambient gradient divider below
          (`.messenger-controls-divider`) provides intentional separation
          matching W181 violet/pink palette. Increased header padding
          (px-5 pt-5 pb-4) for breathing room around the title — user
          reported "верхняя часть левого блока" needed visual upgrade. */}
      <div className="sticky top-0 z-deep flex items-center justify-between bg-surface/(--opacity-medium) px-5 pt-5 pb-4 backdrop-blur-xl">
        <h1 className="sf-pro text-2xl font-bold tracking-tight">{t("messenger:title")}</h1>
        <m.button
          id="messenger-new-chat-btn"
          type="button"
          whileHover={newChatHoverAnim}
          whileTap={newChatTapAnim}
          onClick={handleStartNewChat}
          className="rounded-full bg-(--primary-main)/(--opacity-low) p-2 text-msg-active min-h-[44px] min-w-[44px] flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
          aria-label={t("messenger:newChat")}
        >
          <SquarePen className="h-5 w-5" strokeWidth={2.5} />
        </m.button>
      </div>

      <div className="px-5 pb-4">
        <TextField
          id="messenger-sidebar-search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          inputClassName="matte-input border-none py-2.5 outline-none transition-all"
          leadingIcon={<Search className="h-4 w-4" />}
          placeholder={t("messenger:search")}
          className="w-full"
        />
      </div>

      <div className="messenger-controls-divider" aria-hidden="true" />

      <ContactList
        contacts={filteredContacts}
        selectedId={selectedChatId}
        onSelect={(id: string) => navigate({ to: "/messenger/$chatId", params: { chatId: id } })}
        isSearchActive={isSearchActive}
        searchQuery={searchQuery.trim()}
        onStartNewChat={handleStartNewChat}
        onClearSearch={handleClearSearch}
        isLoading={isLoading}
        isError={isError}
        onRetry={onRetry}
      />
    </m.div>
  )
}
