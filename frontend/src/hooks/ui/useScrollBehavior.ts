import { useEffect, useRef, useState } from "react"
import { NAVBAR_SCROLL_ENTER_THRESHOLD, NAVBAR_SCROLL_EXIT_THRESHOLD } from "@/constants/scroll"

// Wave 124 SW1 — Refactored from framer-motion useScroll/useMotionValueEvent
// to native scroll listener so this hook (used in navbar morph + scroll
// restoration) can run under LazyMotion+domAnimation strict mode. Window
// scroll is the source of truth (matches framer's default useScroll() with
// no args). Listener attaches once + uses passive: true for jank-free
// scrolling. Equivalent behavior — no UX change.
export const useScrollBehavior = () => {
  // The browser may restore a non-zero scroll position before hydration.
  // Always match the server's first render, then read the real position in
  // the effect below; otherwise the navbar changes element structure while
  // React is hydrating a reloaded, scrolled page.
  const [isScrolled, setIsScrolled] = useState(false)
  const frameRef = useRef<number | null>(null)

  useEffect(() => {
    const commitScrollState = () => {
      frameRef.current = null
      const scrollY = window.scrollY
      setIsScrolled((previous) => {
        const next = previous
          ? scrollY > NAVBAR_SCROLL_EXIT_THRESHOLD
          : scrollY > NAVBAR_SCROLL_ENTER_THRESHOLD
        return previous === next ? previous : next
      })
    }
    const handleScroll = () => {
      if (frameRef.current !== null) return
      frameRef.current = window.requestAnimationFrame(commitScrollState)
    }
    handleScroll()
    window.addEventListener("scroll", handleScroll, { passive: true })
    return () => {
      window.removeEventListener("scroll", handleScroll)
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current)
      frameRef.current = null
    }
  }, [])

  return { isScrolled }
}
