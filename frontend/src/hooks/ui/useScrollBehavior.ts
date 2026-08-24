import { useEffect, useState } from "react"
import { NAVBAR_SCROLL_THRESHOLD } from "@/constants/scroll"

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

  useEffect(() => {
    const handleScroll = () => {
      const scrolled = window.scrollY > NAVBAR_SCROLL_THRESHOLD
      setIsScrolled((prev) => (prev !== scrolled ? scrolled : prev))
    }
    handleScroll()
    window.addEventListener("scroll", handleScroll, { passive: true })
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  return { isScrolled }
}
