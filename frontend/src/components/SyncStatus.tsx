import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Cloud, CloudOff, CloudUpload } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

const CLICK_DB_NAME = "notification-interactions"
const CLICK_DB_VERSION = 3
const NEWS_INTERACTION_STORE = "pending-news-interactions"

export function SyncStatus() {
  const { t } = useTranslation(["common"])
  const [pendingCount, setPendingCount] = useState(0)
  const [isOnline, setIsOnline] = useState(navigator.onLine)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)

    const checkQueue = async () => {
      try {
        const db = await new Promise<IDBDatabase>((resolve, reject) => {
          const request = indexedDB.open(CLICK_DB_NAME, CLICK_DB_VERSION)
          request.onupgradeneeded = () => {
            const database = request.result
            if (!database.objectStoreNames.contains("pending-navigations")) {
              database.createObjectStore("pending-navigations", {
                keyPath: "id",
                autoIncrement: true,
              })
            }
            if (!database.objectStoreNames.contains("pending-reports")) {
              database.createObjectStore("pending-reports", { keyPath: "id", autoIncrement: true })
            }
            if (!database.objectStoreNames.contains(NEWS_INTERACTION_STORE)) {
              database.createObjectStore(NEWS_INTERACTION_STORE, {
                keyPath: "id",
                autoIncrement: true,
              })
            }
          }
          request.onsuccess = () => resolve(request.result)
          request.onerror = () => reject(request.error)
        })

        if (!db.objectStoreNames.contains(NEWS_INTERACTION_STORE)) {
          db.close()
          return
        }

        const tx = db.transaction(NEWS_INTERACTION_STORE, "readonly")
        const store = tx.objectStore(NEWS_INTERACTION_STORE)
        const countReq = store.count()
        countReq.onsuccess = () => {
          setPendingCount(countReq.result)
          db.close()
        }
      } catch (e) {
        // Silently fail if DB not ready
      }
    }

    const interval = setInterval(checkQueue, 3000)
    checkQueue()

    return () => {
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
      clearInterval(interval)
    }
  }, [])

  if (!isOnline && pendingCount === 0) return null

  const statusTitle = !isOnline
    ? t("common:sync.offline", {
        count: pendingCount,
        defaultValue: `Offline (${pendingCount} queued)`,
      })
    : t("common:sync.online", { defaultValue: "All synced" })

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        role="status"
        title={statusTitle}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-full transition-all duration-300",
          "bg-glass-subtle border border-border-subtle shadow-sm",
          !isOnline && "border-warning-border/40 bg-warning-bg/10"
        )}
      >
        {isOnline ? (
          <Cloud className="h-4 w-4 text-white/40" />
        ) : (
          <motion.div
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ repeat: Infinity, duration: 2 }}
          >
            <CloudUpload className="h-4 w-4 text-(--warning-text)" />
          </motion.div>
        )}
        {pendingCount > 0 && (
          <span className="z-(--z-deep) text-xs font-black uppercase tracking-tight text-(--text-primary)/80 tabular-nums sf-pro">
            {pendingCount}
          </span>
        )}
      </motion.div>
    </AnimatePresence>
  )
}
