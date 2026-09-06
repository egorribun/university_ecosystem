import { useCallback, useMemo, useSyncExternalStore } from "react"

type MediaQueryCallback = (event: MediaQueryListEvent | MediaQueryList) => void

const TRUE_SERVER_SNAPSHOT = () => true
const FALSE_SERVER_SNAPSHOT = () => false

export interface UseMediaQueryOptions {
  /** Value used before the first client render when matchMedia is unavailable. */
  defaultValue?: boolean
}

type MatchMediaResolver = (query: string) => MediaQueryList | null

const getMatchMedia = (): MatchMediaResolver => {
  if (typeof window === "undefined") return () => null
  const matchMedia = window.matchMedia
  if (typeof matchMedia !== "function") return () => null
  return matchMedia.bind(window)
}

export const toMediaQueryList = (query: string): MediaQueryList | null => {
  const matchMedia = getMatchMedia()
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

  const getServerSnapshot = defaultValue ? TRUE_SERVER_SNAPSHOT : FALSE_SERVER_SNAPSHOT

  return useSyncExternalStore(subscribe, store.getSnapshot, getServerSnapshot)
}
