import React, { createContext, useContext, useEffect, useState } from "react"
import type { AppDatabase } from "./index"

const RxDBContext = createContext<AppDatabase | null>(null)

// IndexedDB/RxDB is an offline enhancement, not part of the first paint. A
// fixed quiet window keeps its sizeable bundle out of the critical rendering
// and Lighthouse Total Blocking Time windows. Do not use requestIdleCallback
// here: browsers may invoke an idle callback immediately while the page is
// still parsing/hydrating, defeating the performance boundary.
const RXDB_IDLE_TIMEOUT_MS = 10_000

export const RxDBProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [db, setDb] = useState<AppDatabase | null>(null)

  useEffect(() => {
    let mounted = true
    let timerHandle: number | null = null

    const initialize = () => {
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

    timerHandle = window.setTimeout(initialize, RXDB_IDLE_TIMEOUT_MS)

    return () => {
      mounted = false
      if (timerHandle !== null) window.clearTimeout(timerHandle)
    }
  }, [])

  return <RxDBContext.Provider value={db}>{children}</RxDBContext.Provider>
}

export const useRxDB = (): AppDatabase | null => useContext(RxDBContext)
