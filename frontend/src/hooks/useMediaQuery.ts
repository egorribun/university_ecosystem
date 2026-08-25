import { useCallback, useMemo, useSyncExternalStore } from "react"

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

class MediaQueryStore {
  private current: boolean

  constructor(initialValue: boolean) {
    this.current = initialValue
  }

  readonly getSnapshot = (): boolean => this.current

  update(nextValue: boolean): void {
    this.current = nextValue
  }
}

export default function useMediaQuery(
  query: string,
  { defaultValue = false }: UseMediaQueryOptions = {}
): boolean {
  const mediaQueryList = useMemo(() => toMediaQueryList(query), [query])
  const store = useMemo(
    () => new MediaQueryStore(mediaQueryList?.matches ?? defaultValue),
    [defaultValue, mediaQueryList]
  )

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (!mediaQueryList) return () => undefined

      const handleChange: MediaQueryCallback = (event) => {
        store.update(event.matches)
        onStoreChange()
      }
      if (typeof mediaQueryList.addEventListener === "function") {
        mediaQueryList.addEventListener("change", handleChange)
      } else if (typeof mediaQueryList.addListener === "function") {
        mediaQueryList.addListener(handleChange)
      }

      return () => {
        if (typeof mediaQueryList.removeEventListener === "function") {
          mediaQueryList.removeEventListener("change", handleChange)
        } else if (typeof mediaQueryList.removeListener === "function") {
          mediaQueryList.removeListener(handleChange)
        }
      }
    },
    [mediaQueryList, store]
  )

  const getServerSnapshot = useCallback(() => defaultValue, [defaultValue])

  return useSyncExternalStore(subscribe, store.getSnapshot, getServerSnapshot)
}
