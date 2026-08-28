import { useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { MessageSquare } from "lucide-react"
import { cn } from "@/utils/cn"
import { m } from "framer-motion"
import { useMessenger } from "@/contexts/MessengerContextCore"

export default function MessengerButton() {
  const navigate = useNavigate()
  const { t } = useTranslation(["navigation"])
  const { unreadCount } = useMessenger()

  return (
    <button
      id="global-messenger-btn"
      onClick={() => navigate({ to: "/messenger" })}
      className={cn(
        "relative nav-action-btn group focus-ring-premium",
        "text-text-primary hover:text-brand"
      )}
      data-unread={unreadCount > 0 ? "" : undefined}
      aria-label={t("navigation:aria.messenger")}
    >
      <MessageSquare
        className="nav-action-icon transition-transform duration-slow group-hover:-rotate-6 group-hover:scale-110"
        strokeWidth={2}
      />
      {unreadCount > 0 && (
        <m.span
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-0.5 -right-0.5 flex items-center justify-center"
        >
          <span className="relative inline-flex rounded-full h-4 min-w-4 bg-(--brand-main) border-2 border-(--bg-surface) dark:border-(--bg-page) text-label-xs font-bold text-white items-center justify-center px-0.5">
            {unreadCount}
          </span>
        </m.span>
      )}
    </button>
  )
}
