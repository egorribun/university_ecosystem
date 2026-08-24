import { useCallback, useEffect, useMemo, useState } from "react"

type MediaQueryCallback = (event: MediaQueryListEvent | MediaQueryList) => void

export interface UseMediaQueryOptions {
  /** Value used before the first client render when matchMedia is unavailable. */
  defaultValue?: boolean
}

const getMatchMedia = (): ((query: string) => MediaQueryList) | undefined => {
  if (typeof window === "undefined") return undefined
  const matchMedia = window.matchMedia
  if (typeof matchMedia !== "function") return undefined
  return matchMedia.bind(window)
}

const toMediaQueryList = (query: string): MediaQueryList | null => {
  const matchMedia = getMatchMedia()
  if (!matchMedia) return null
  try {
    return matchMedia(query)
  } catch {
    return null
  }
}

export default function useMediaQuery(
  query: string,
  { defaultValue = false }: UseMediaQueryOptions = {}
): boolean {
  const getMatch = useCallback(() => {
    const mql = toMediaQueryList(query)
    return mql ? mql.matches : defaultValue
  }, [defaultValue, query])

  const [matches, setMatches] = useState<boolean>(() => getMatch())

  useEffect(() => {
    const mql = toMediaQueryList(query)
    if (!mql) {
      setMatches(defaultValue)
      return
    }

    const handleChange: MediaQueryCallback = (event) => {
      setMatches(event.matches)
    }

    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", handleChange)
    } else if (typeof mql.addListener === "function") {
      mql.addListener(handleChange)
    }

    setMatches(mql.matches)

    return () => {
      if (typeof mql.removeEventListener === "function") {
        mql.removeEventListener("change", handleChange)
      } else if (typeof mql.removeListener === "function") {
        mql.removeListener(handleChange)
      }
    }
  }, [defaultValue, query])

  return useMemo(() => matches, [matches])
}
