import { ContactList } from "@/components/messenger"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import { motion } from "framer-motion"
import { Search, SquarePen } from "lucide-react"
import { Dispatch, SetStateAction } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"

interface MessengerSidebarProps {
  isMobile: boolean
  contacts: ReturnType<typeof useMessengerController>["contacts"]
  selectedChatId: string | null
  setIsNewChatModalOpen: Dispatch<SetStateAction<boolean>>
}

export function MessengerSidebar({
  isMobile,
  contacts,
  selectedChatId,
  setIsNewChatModalOpen,
}: MessengerSidebarProps) {
  const { t } = useTranslation(["messenger", "common"])
  const navigate = useNavigate()

  return (
    <motion.div
      key="sidebar"
      initial={isMobile ? { x: -300, opacity: 0 } : undefined}
      animate={{ x: 0, opacity: 1 }}
      exit={isMobile ? { x: -300, opacity: 0 } : undefined}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="panel-glass relative z-deep flex h-full w-full flex-col md:w-(--layout-max-sidebar) lg:w-(--layout-max-sidebar)"
    >
      <div className="header-glass flex items-center justify-between p-4">
        <h1 className="sf-pro text-2xl font-bold tracking-tight">
          {t("messenger:title", "Messages")}
        </h1>
        <motion.button
          id="messenger-new-chat-btn"
          whileHover={{ scale: 1.1, backgroundColor: "var(--msg-sidebar-hover)" }}
          whileTap={{ scale: 0.9 }}
          onClick={() => setIsNewChatModalOpen(true)}
          className="rounded-full bg-(--primary-main)/(--opacity-low) p-2 text-msg-active transition-colors"
          aria-label={t("messenger:newChat", "New Chat")}
        >
          <SquarePen className="h-5 w-5" strokeWidth={2.5} />
        </motion.button>
      </div>

      <div className="bg-(--bg-surface-raised) p-4">
        <div className="group relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary transition-colors group-focus-within:text-primary-main" />
          <input
            id="messenger-sidebar-search"
            type="text"
            placeholder={t("messenger:search", "Search")}
            className="w-full rounded-md border-none bg-black/(--opacity-medium) py-25 pl-10 pr-4 text-(--fs-body) shadow-sm outline-none transition-all focus:ring-2 focus:ring-(--brand-main)/(--opacity-medium) dark:bg-white/(--opacity-medium)"
          />
        </div>
      </div>

      <ContactList
        contacts={contacts}
        selectedId={selectedChatId}
        onSelect={(id: string) => navigate(`/messenger/${id}`)}
      />
    </motion.div>
  )
}
