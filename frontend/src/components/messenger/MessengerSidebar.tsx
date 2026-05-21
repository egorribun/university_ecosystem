import { ContactList } from "@/components/messenger"
import { TextField } from "@/components/ui"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import { m, useReducedMotion } from "framer-motion"
import { Search, SquarePen } from "lucide-react"
import { Dispatch, SetStateAction, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"

interface MessengerSidebarProps {
  isMobile: boolean
  contacts: ReturnType<typeof useMessengerController>["contacts"]
  selectedChatId: string | null
  setIsNewChatModalOpen: Dispatch<SetStateAction<boolean>>
}

const MOBILE_MENU_WIDTH = 300

export function MessengerSidebar({
  isMobile,
  contacts,
  selectedChatId,
  setIsNewChatModalOpen,
}: MessengerSidebarProps) {
  const { t } = useTranslation(["messenger", "common"])
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState("")
  // Wave 181 SW3 — useReducedMotion guards new-chat button micro-interactions
  // + sidebar slide-in/out transitions (Framer Motion already provides motion
  // reduction at MotionConfig level via W127 hoist, but framer-motion docs
  // recommend explicit per-component guards for prop-level control).
  const prefersReducedMotion = useReducedMotion() ?? false
  const newChatHoverAnim = prefersReducedMotion
    ? undefined
    : { scale: 1.08, backgroundColor: "var(--msg-sidebar-hover)" }
  const newChatTapAnim = prefersReducedMotion ? undefined : { scale: 0.94 }
  const sidebarInitial =
    isMobile && !prefersReducedMotion ? { x: -MOBILE_MENU_WIDTH, opacity: 0 } : undefined
  const sidebarExit =
    isMobile && !prefersReducedMotion ? { x: -MOBILE_MENU_WIDTH, opacity: 0 } : undefined

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
      <div className="header-glass flex items-center justify-between p-4">
        <h1 className="sf-pro text-2xl font-bold tracking-tight">
          {t("messenger:title", "Messages")}
        </h1>
        <m.button
          id="messenger-new-chat-btn"
          type="button"
          whileHover={newChatHoverAnim}
          whileTap={newChatTapAnim}
          onClick={() => setIsNewChatModalOpen(true)}
          className="rounded-full bg-(--primary-main)/(--opacity-low) p-2 text-msg-active min-h-[44px] min-w-[44px] flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
          aria-label={t("messenger:newChat", "New Chat")}
        >
          <SquarePen className="h-5 w-5" strokeWidth={2.5} />
        </m.button>
      </div>

      <div className="bg-(--bg-surface-raised) p-4">
        <TextField
          id="messenger-sidebar-search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          inputClassName="matte-input border-none py-2.5 outline-none transition-all"
          leadingIcon={<Search className="h-4 w-4" />}
          placeholder={t("messenger:search", "Search")}
          className="w-full"
        />
      </div>

      <ContactList
        contacts={contacts}
        selectedId={selectedChatId}
        onSelect={(id: string) => navigate({ to: "/messenger/$chatId", params: { chatId: id } })}
      />
    </m.div>
  )
}
