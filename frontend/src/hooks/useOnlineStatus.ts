import { useEffect, useState } from "react"

/**
 * A hook that tracks the browser's online/offline status.
 * Returns a boolean `isOnline` which is true when the browser reports connectivity.
 */
export function useOnlineStatus(): boolean {
  // Start optimistically online on both SSR and the first browser render.
  // Reading navigator.onLine during render makes an offline browser emit a
  // different tree from SSR; the effect below publishes the real status as
  // soon as hydration commits.
  const [isOnline, setIsOnline] = useState(true)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    setIsOnline(typeof navigator !== "undefined" ? navigator.onLine : true)
    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)

    return () => {
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
    }
  }, [])

  return isOnline
}
