import React, { createContext, useContext, useEffect, useState } from "react"
import type { AppDatabase } from "./index"
import { getDatabase } from "./index"

const RxDBContext = createContext<AppDatabase | null>(null)

export const RxDBProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [db, setDb] = useState<AppDatabase | null>(null)

  useEffect(() => {
    let mounted = true
    getDatabase()
      .then((database) => {
        if (mounted) setDb(database)
      })
      .catch((err) => {
        console.error("[RxDB] Initialization failed:", err)
      })
    return () => {
      mounted = false
    }
  }, [])

  return <RxDBContext.Provider value={db}>{children}</RxDBContext.Provider>
}

export const useRxDB = (): AppDatabase | null => useContext(RxDBContext)
