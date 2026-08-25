import React, { createContext, useContext, useEffect, useState } from "react"
import type { AppDatabase } from "./index"

const RxDBContext = createContext<AppDatabase | null>(null)

export const RxDBProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [db, setDb] = useState<AppDatabase | null>(null)

  useEffect(() => {
    let mounted = true
    let idleHandle: number | null = null
    let timerHandle: number | null = null

    const initialize = () => {
      idleHandle = null
      timerHandle = null
      if (!mounted) return

      void import("./index")
        .then(({ getDatabase }) => getDatabase())
        .then((database) => {
          if (mounted) setDb(database)
        })
        .catch((err: unknown) => {
          if (mounted) console.error("[RxDB] Initialization failed:", err)
        })
    }

    if (typeof globalThis.requestIdleCallback === "function") {
      idleHandle = globalThis.requestIdleCallback(initialize, { timeout: 2000 })
    } else {
      timerHandle = window.setTimeout(initialize, 0)
    }

    return () => {
      mounted = false
      if (idleHandle !== null && typeof globalThis.cancelIdleCallback === "function") {
        globalThis.cancelIdleCallback(idleHandle)
      }
      if (timerHandle !== null) window.clearTimeout(timerHandle)
    }
  }, [])

  return <RxDBContext.Provider value={db}>{children}</RxDBContext.Provider>
}

export const useRxDB = (): AppDatabase | null => useContext(RxDBContext)
