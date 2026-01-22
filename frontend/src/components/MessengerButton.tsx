import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { MessageSquare } from "lucide-react"
import { cn } from "@/utils/cn"
import { motion } from "framer-motion"

export default function MessengerButton() {
  const navigate = useNavigate()
  const { t } = useTranslation(["navigation"])

  // Mock unread count for now
  const unreadCount = 0

  return (
    <motion.button
      whileHover={{ scale: 1.05, backgroundColor: "var(--glass-tint-2)" }}
      whileTap={{ scale: 0.95 }}
      onClick={() => navigate("/messenger")}
      className={cn(
        "relative flex items-center justify-center rounded-xl transition-all duration-300 outline-none group",
        "w-[clamp(32px,7vw,40px)] h-[clamp(32px,7vw,40px)] border border-transparent hover:border-[var(--glass-border)]"
      )}
      style={{ color: "var(--nav-text)" }}
      aria-label={t("navigation:aria.messenger")}
    >
      <MessageSquare
        className="w-[clamp(18px,4.5vw,22px)] h-[clamp(18px,4.5vw,22px)] transition-transform duration-500 group-hover:rotate-[-5deg]"
        strokeWidth={1.8}
      />
      {unreadCount > 0 && (
        <span className="absolute top-1.5 right-1.5 flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500 border-2 border-white dark:border-[#0F172A]"></span>
        </span>
      )}
    </motion.button>
  )
}
