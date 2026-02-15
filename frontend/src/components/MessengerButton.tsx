import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { MessageSquare } from "lucide-react"
import { cn } from "@/utils/cn"
import { motion } from "framer-motion"
import { useMessenger } from "@/contexts/MessengerContext"

export default function MessengerButton() {
  const navigate = useNavigate()
  const { t } = useTranslation(["navigation"])
  const { unreadCount } = useMessenger()

  return (
    <motion.button
      id="global-messenger-btn"
      whileHover={{
        scale: 1.05,
        backgroundColor: "var(--msg-sidebar-hover)",
        boxShadow: "var(--shadow-glow-blue)",
      }}
      whileTap={{ scale: 0.95 }}
      onClick={() => navigate("/messenger")}
      className={cn(
        "relative flex items-center justify-center rounded-lg transition-all duration-base group focus-ring-premium",
        "w-11 h-11 border border-transparent hover:border-brand/(--opacity-soft) bg-transparent glass-morphism shadow-sm"
      )}
      aria-label={t("navigation:aria.messenger")}
    >
      <MessageSquare
        className="w-5.5 h-5.5 transition-all duration-slow group-hover:rotate-[-8deg] group-hover:scale-110 text-(--text-secondary) group-hover:text-brand"
        strokeWidth={2}
      />
      {unreadCount > 0 && (
        <motion.span
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center"
        >
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand px-1 text-[10px] font-bold text-white opacity-dim shadow-sm"></span>
          <span className="relative inline-flex rounded-full h-4 w-4 bg-(--brand-main) border-2 border-(--bg-surface) dark:border-(--bg-page) text-label-xs font-bold text-white items-center justify-center">
            {unreadCount}
          </span>
        </motion.span>
      )}
    </motion.button>
  )
}
