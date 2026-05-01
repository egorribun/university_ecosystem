import { ContactList } from "@/components/messenger"
import { TextField } from "@/components/ui"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import { m } from "framer-motion"
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

  return (
    <m.div
      key="sidebar"
      initial={isMobile ? { x: -MOBILE_MENU_WIDTH, opacity: 0 } : undefined}
      animate={{ x: 0, opacity: 1 }}
      exit={isMobile ? { x: -MOBILE_MENU_WIDTH, opacity: 0 } : undefined}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="panel-glass relative z-deep flex h-full w-full flex-col md:w-(--layout-max-sidebar) lg:w-(--layout-max-sidebar)"
    >
      <div className="header-glass flex items-center justify-between p-4">
        <h1 className="sf-pro text-2xl font-bold tracking-tight">
          {t("messenger:title", "Messages")}
        </h1>
        <m.button
          id="messenger-new-chat-btn"
          whileHover={{ scale: 1.1, backgroundColor: "var(--msg-sidebar-hover)" }}
          whileTap={{ scale: 0.9 }}
          onClick={() => setIsNewChatModalOpen(true)}
          className="rounded-full bg-(--primary-main)/(--opacity-low) p-2 text-msg-active transition-colors"
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
          inputClassName="border-none bg-black/(--opacity-medium) py-2.5 shadow-sm outline-none transition-all focus:ring-2 focus:ring-(--brand-main)/(--opacity-medium) dark:bg-white/(--opacity-medium)"
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
