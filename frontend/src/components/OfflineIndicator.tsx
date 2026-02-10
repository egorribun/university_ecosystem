import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { WifiOff, Wifi } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

/**
 * Displays a toast notification when the user goes offline.
 * Uses the browser's online/offline events for detection.
 */
export function OfflineIndicator() {
  const [isOffline, setIsOffline] = useState(false)
  const [show, setShow] = useState(false)
  const { t } = useTranslation("system")

  useEffect(() => {
    // Check initial state
    const initialOffline = typeof navigator !== "undefined" && !navigator.onLine
    setIsOffline(initialOffline)
    if (initialOffline) {
      setShow(true)
    }

    const handleOnline = () => {
      setIsOffline(false)
      setShow(true) // Briefly show "back online" message
      const timer = setTimeout(() => setShow(false), 3000)
      return () => clearTimeout(timer)
    }

    const handleOffline = () => {
      setIsOffline(true)
      setShow(true)
    }

    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)

    return () => {
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
    }
  }, [])

  // Hide after showing online state
  useEffect(() => {
    if (!isOffline && show) {
      const timer = setTimeout(() => setShow(false), 3000)
      return () => clearTimeout(timer)
    }
  }, [isOffline, show])

  if (!show) return null

  const content = (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "fixed bottom-24 left-1/2 z-(--z-toast) -translate-x-1/2",
        "flex items-center gap-2 rounded-2xl px-5 py-3",
        "text-[13px] font-black uppercase tracking-widest shadow-2xl backdrop-blur-2xl border",
        "transition-all duration-500 ease-out animate-in fade-in slide-in-from-bottom-4",
        isOffline
          ? "bg-(--warning-bg) border-(--warning-text)/20 text-(--warning-text)"
          : "bg-(--success-bg) border-(--success-text)/20 text-(--success-text)"
      )}
    >
      {isOffline ? (
        <>
          <WifiOff className="h-4 w-4" />
          <span>{t("offlineIndicator.offline", "You're offline")}</span>
        </>
      ) : (
        <>
          <Wifi className="h-4 w-4" />
          <span>{t("offlineIndicator.online", "Back online")}</span>
        </>
      )}
    </div>
  )

  return typeof document !== "undefined" ? createPortal(content, document.body) : null
}

export default OfflineIndicator
