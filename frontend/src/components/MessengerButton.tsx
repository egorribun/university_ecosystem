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
      whileHover={{
        scale: 1.05,
        backgroundColor: "var(--msg-sidebar-hover)",
        boxShadow: "0 0 20px rgba(59, 130, 246, 0.2)",
      }}
      whileTap={{ scale: 0.95 }}
      onClick={() => navigate("/messenger")}
      className={cn(
        "relative flex items-center justify-center rounded-[14px] transition-all duration-300 outline-none group",
        "w-10 h-10 border border-transparent hover:border-blue-500/30 bg-transparent glass-morphism shadow-sm"
      )}
      aria-label={t("navigation:aria.messenger")}
    >
      <MessageSquare
        className="w-5 h-5 transition-all duration-500 group-hover:rotate-[-8deg] group-hover:scale-110 text-gray-600 dark:text-gray-300 group-hover:text-blue-500"
        strokeWidth={2}
      />
      {unreadCount > 0 && (
        <motion.span
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center"
        >
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-40"></span>
          <span className="relative inline-flex rounded-full h-4 w-4 bg-blue-500 border-2 border-white dark:border-[#0F172A] text-[9px] font-bold text-white items-center justify-center">
            {unreadCount}
          </span>
        </motion.span>
      )}
    </motion.button>
  )
}
