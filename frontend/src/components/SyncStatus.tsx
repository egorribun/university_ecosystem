import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import CloudUploadIcon from "@mui/icons-material/CloudUpload"
import CloudQueueIcon from "@mui/icons-material/CloudQueue"
import CloudOffIcon from "@mui/icons-material/CloudOff"
import { Tooltip } from "@mui/material"
import { useTranslation } from "react-i18next"

const CLICK_DB_NAME = "notification-interactions"
const CLICK_DB_VERSION = 1
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

  return (
    <AnimatePresence>
      <Tooltip
        title={
          !isOnline
            ? t("common:sync.offline", { count: pendingCount, defaultValue: `Offline (${pendingCount} queued)` })
            : t("common:sync.online", { defaultValue: "All synced" })
        }
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.8 }}
          role="status"
          className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-glass/20 backdrop-blur-sm border border-white/10"
        >
          {isOnline ? (
            <CloudQueueIcon className="text-white/60 text-[1.1rem]" />
          ) : (
            <motion.div
              animate={{ opacity: [1, 0.5, 1] }}
              transition={{ repeat: Infinity, duration: 2 }}
            >
              <CloudUploadIcon className="text-amber-400 text-[1.1rem]" />
            </motion.div>
          )}
          {pendingCount > 0 && (
            <span className="text-[0.75rem] font-bold text-white/90 tabular-nums">
              {pendingCount}
            </span>
          )}
        </motion.div>
      </Tooltip>
    </AnimatePresence>
  )
}
