import { useCallback, useLayoutEffect } from "react"
import { useAppShell } from "@/contexts/AppShellContext"

const normalizePath = (input: string) => input.replace(/\/+$/, "") || "/"

export interface ScrollRestorationApi {
  scrollToTop: (behavior?: ScrollBehavior) => void
  markScrollFromBottom: () => void
  isSamePath: (target: string) => boolean
}

type ScrollBehavior = "auto" | "smooth"

export default function useScrollRestoration(currentPath: string): ScrollRestorationApi {
  const {
    scrollToTop: scrollToTopGlobal,
    markScrollSnapshot,
    restoreScrollIfNeeded,
  } = useAppShell()

  useLayoutEffect(() => {
    restoreScrollIfNeeded()
  }, [restoreScrollIfNeeded, currentPath])

  const scrollToTop = useCallback(
    (behavior?: ScrollBehavior) => {
      scrollToTopGlobal(behavior)
    },
    [scrollToTopGlobal]
  )

  const markScrollFromBottom = useCallback(() => {
    markScrollSnapshot()
  }, [markScrollSnapshot])

  const isSamePath = useCallback(
    (target: string) => {
      if (target === "/dashboard") {
        const normalized = normalizePath(currentPath)
        return normalized === "/" || normalized === normalizePath(target)
      }
      return normalizePath(currentPath) === normalizePath(target)
    },
    [currentPath]
  )

  return { scrollToTop, markScrollFromBottom, isSamePath }
}
