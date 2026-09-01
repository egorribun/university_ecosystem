import { m, AnimatePresence } from "framer-motion"
import { Cloud, CloudUpload, RefreshCw, CheckCircle2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { useSyncStatus } from "@/hooks/useSyncStatus"

export function SyncStatus() {
  const { t } = useTranslation(["common"])
  const { isOnline, syncState, totalPendingCount, triggerManualSync } = useSyncStatus()

  if (!isOnline && totalPendingCount === 0) return null

  const statusTitle = !isOnline
    ? t("common:sync.offline", {
        count: totalPendingCount,
      })
    : t("common:sync.online")

  return (
    <AnimatePresence>
      <m.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        role="status"
        title={statusTitle}
        onClick={triggerManualSync}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-full transition-all duration-base cursor-pointer select-none",
          "bg-glass-subtle border border-border-subtle shadow-sm hover:bg-glass-hover",
          !isOnline && "border-warning-border/(--opacity-dim) bg-warning-bg/(--opacity-subtle)",
          syncState === "syncing" && "border-brand/30 bg-brand/10",
          syncState === "synced" && "border-success-border bg-success-bg/20"
        )}
      >
        {!isOnline ? (
          <m.div animate={{ opacity: [1, 0.5, 1] }} transition={{ repeat: Infinity, duration: 2 }}>
            <CloudUpload className="h-4 w-4 text-(--warning-text)" />
          </m.div>
        ) : syncState === "syncing" ? (
          <RefreshCw className="h-4 w-4 animate-spin text-brand" />
        ) : syncState === "synced" ? (
          <CheckCircle2 className="h-4 w-4 text-success-text" />
        ) : (
          <Cloud className="h-4 w-4 text-white/(--opacity-medium)" />
        )}
        {totalPendingCount > 0 && (
          <span className="z-deep text-xs font-black uppercase tracking-tight text-text-primary/(--opacity-strong) tabular-nums sf-pro">
            {totalPendingCount}
          </span>
        )}
      </m.div>
    </AnimatePresence>
  )
}
