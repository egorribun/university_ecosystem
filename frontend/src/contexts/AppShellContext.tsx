import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react"

interface OverlayState {
  blurred: boolean
  scrollLocked: boolean
}

type OverlayMap = Map<string, OverlayState>

type ScrollBehaviorOption = "auto" | "smooth"

interface AppShellContextValue {
  setOverlayState: (id: string, state: OverlayState | null) => void
  scrollToTop: (behavior?: ScrollBehaviorOption) => void
  markScrollSnapshot: () => void
  restoreScrollIfNeeded: () => void
}

const AppShellContext = createContext<AppShellContextValue | undefined>(undefined)

const isBrowser = () => typeof window !== "undefined"

const prefersReducedMotionGlobal = () => {
  if (!isBrowser() || typeof window.matchMedia !== "function") return false
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
  } catch {
    return false
  }
}

const getScrollRoot = (): HTMLElement | null => {
  if (!isBrowser()) return null
  const candidates: (Element | Document | null | undefined)[] = [
    document.querySelector("[data-scroll-root]"),
    document.querySelector("main[role='main']"),
    document.querySelector("main"),
    document.getElementById("scroll-root"),
    document.querySelector("#root"),
    (document as unknown as { scrollingElement?: Element }).scrollingElement,
    document.documentElement,
    document.body,
  ]

  for (const candidate of candidates) {
    if (!candidate) continue
    const element = candidate as HTMLElement
    const overflowY = window.getComputedStyle(element).overflowY
    const scrollable =
      (overflowY === "auto" || overflowY === "scroll") &&
      element.scrollHeight > element.clientHeight
    if (scrollable) return element
  }

  return (document.scrollingElement || document.documentElement || null) as HTMLElement | null
}

const smoothScrollToTop = (target: HTMLElement, behavior: ScrollBehaviorOption) => {
  if (behavior === "auto") {
    try {
      target.scrollTo({ top: 0, behavior: "auto" })
    } catch {
      target.scrollTop = 0
    }
    return
  }

  try {
    target.scrollTo({ top: 0, behavior: "smooth" })
  } catch {
    const start = target.scrollTop
    const duration = 420
    let startTimestamp = 0
    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp
      const progress = Math.min(1, (timestamp - startTimestamp) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      target.scrollTop = Math.round(start * (1 - eased))
      if (progress < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }
}

const markScrollTopNext = () => {
  try {
    window.sessionStorage.setItem("__scrollTopNext", "1")
  } catch {
    /* noop */
  }
}

const consumeScrollTopNext = (): boolean => {
  if (!isBrowser()) return false
  try {
    const value = window.sessionStorage.getItem("__scrollTopNext")
    if (value === "1") {
      window.sessionStorage.removeItem("__scrollTopNext")
      return true
    }
  } catch {
    return false
  }
  return false
}

export const AppShellProvider = ({ children }: PropsWithChildren) => {
  const overlaysRef = useRef<OverlayMap>(new Map())
  const previousOverflowRef = useRef<string>("")

  const [overlayStatus, setOverlayStatus] = useState({ blurred: false, scrollLocked: false })

  useEffect(() => {
    const { blurred, scrollLocked } = overlayStatus

    if (blurred) {
      document.body.classList.add("blurred")
    } else {
      document.body.classList.remove("blurred")
    }

    if (scrollLocked) {
      previousOverflowRef.current = document.body.style.overflow
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = previousOverflowRef.current || ""
    }
  }, [overlayStatus])

  const setOverlayState = useCallback((id: string, state: OverlayState | null) => {
    const map = overlaysRef.current
    if (state) {
      map.set(id, state)
    } else {
      map.delete(id)
    }

    const values = Array.from(map.values())
    setOverlayStatus({
      blurred: values.some((s) => s.blurred),
      scrollLocked: values.some((s) => s.scrollLocked),
    })
  }, [])

  useEffect(
    () => () => {
      document.body.classList.remove("blurred")
      document.body.style.overflow = ""
    },
    []
  )

  const scrollToTop = useCallback((behavior?: ScrollBehaviorOption) => {
    const target = getScrollRoot()
    if (!target) return
    const resolvedBehavior = behavior ?? (prefersReducedMotionGlobal() ? "auto" : "smooth")
    smoothScrollToTop(target, resolvedBehavior)
  }, [])

  const markScrollSnapshot = useCallback(() => {
    const target = getScrollRoot()
    if (!target) return
    const nearBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 24
    if (nearBottom) {
      markScrollTopNext()
    }
  }, [])

  const restoreScrollIfNeeded = useCallback(() => {
    if (!consumeScrollTopNext()) return
    const target = getScrollRoot()
    if (!target) return
    requestAnimationFrame(() =>
      requestAnimationFrame(() =>
        smoothScrollToTop(target, prefersReducedMotionGlobal() ? "auto" : "smooth")
      )
    )
  }, [])

  const value = useMemo<AppShellContextValue>(
    () => ({ setOverlayState, scrollToTop, markScrollSnapshot, restoreScrollIfNeeded }),
    [markScrollSnapshot, restoreScrollIfNeeded, scrollToTop, setOverlayState]
  )

  return <AppShellContext.Provider value={value}>{children}</AppShellContext.Provider>
}

export const useAppShell = () => {
  const context = useContext(AppShellContext)
  if (!context) {
    throw new Error("useAppShell must be used within an AppShellProvider")
  }
  return context
}

export type { AppShellContextValue }
