import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import WifiOffIcon from "@mui/icons-material/WifiOff"
import { useTranslation } from "react-i18next"

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
            className={`
        fixed bottom-20 left-1/2 z-[9999] -translate-x-1/2
        flex items-center gap-2 rounded-full px-4 py-2.5
        text-sm font-medium shadow-lg backdrop-blur-md
        transition-all duration-300 ease-out
        ${isOffline
                    ? "bg-amber-500/90 text-amber-950 dark:bg-amber-600/90 dark:text-amber-50"
                    : "bg-emerald-500/90 text-emerald-950 dark:bg-emerald-600/90 dark:text-emerald-50"
                }
      `}
        >
            {isOffline ? (
                <>
                    <WifiOffIcon className="h-4 w-4" />
                    <span>{t("offlineIndicator.offline", "You're offline")}</span>
                </>
            ) : (
                <span>{t("offlineIndicator.online", "Back online")}</span>
            )}
        </div>
    )

    return typeof document !== "undefined" ? createPortal(content, document.body) : null
}

export default OfflineIndicator
