import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { fetchCampusTimezone } from "@/api/hooks/campusConfig"

const CampusTimezoneContext = createContext<string | null>(null)

type ClientTimezoneRefresh = {
  loaderValue: string | null
  refreshedValue: string | null
}

export function CampusTimezoneProvider({
  children,
  timeZone,
}: {
  children: ReactNode
  timeZone: string | null
}) {
  const [clientRefresh, setClientRefresh] = useState<ClientTimezoneRefresh>(() => ({
    loaderValue: timeZone,
    refreshedValue: null,
  }))

  const effectiveTimeZone =
    timeZone ?? (clientRefresh.loaderValue === null ? clientRefresh.refreshedValue : null)

  useEffect(() => {
    if (timeZone !== null) {
      setClientRefresh({ loaderValue: timeZone, refreshedValue: null })
      return
    }

    let active = true
    setClientRefresh({ loaderValue: null, refreshedValue: null })

    void fetchCampusTimezone().then(
      (refreshedValue) => {
        if (active) {
          setClientRefresh({ loaderValue: null, refreshedValue })
        }
      },
      () => {
        if (active) {
          setClientRefresh({ loaderValue: null, refreshedValue: null })
        }
      }
    )

    return () => {
      active = false
    }
  }, [timeZone])

  return (
    <CampusTimezoneContext.Provider value={effectiveTimeZone}>
      {children}
    </CampusTimezoneContext.Provider>
  )
}

/** Returns the server-configured campus zone, or null while it is unavailable. */
export function useCampusTimezone(): string | null {
  return useContext(CampusTimezoneContext)
}
