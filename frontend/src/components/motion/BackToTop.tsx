import { useEffect, useState, useCallback, useRef } from "react"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowUp } from "lucide-react"
import Magnetic from "./Magnetic"

const BASE_BOTTOM = 24 // px — default distance from viewport bottom
const FOOTER_GAP = 16 // px — gap between FAB and footer top edge

export default function BackToTop() {
  const { t } = useTranslation(["common"])

  const [show, setShow] = useState(false)
  const [footerOffset, setFooterOffset] = useState(0)
  const observerRef = useRef<IntersectionObserver | null>(null)

  // Show/hide based on scroll position
  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 420)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  // Observe footer to shift FAB above it
  useEffect(() => {
    const footer = document.querySelector<HTMLElement>('[role="contentinfo"]')
    if (!footer) return

    const thresholds = Array.from({ length: 21 }, (_, i) => i / 20)

    observerRef.current = new IntersectionObserver(
      ([entry]) => {
        if (!entry || !entry.isIntersecting) {
          setFooterOffset(0)
          return
        }
        // How many px of footer are visible in the viewport
        const visiblePx = window.innerHeight - entry.boundingClientRect.top
        setFooterOffset(Math.max(0, visiblePx + FOOTER_GAP))
      },
      { threshold: thresholds }
    )

    observerRef.current.observe(footer)
    return () => observerRef.current?.disconnect()
  }, [])

  const onClick = useCallback(() => {
    try {
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch {
      window.scrollTo(0, 0)
    }
  }, [])

  return (
    <AnimatePresence>
      {show && (
        <div
          className="fixed right-6 z-tooltip back-to-top-wrap"
          style={{
            bottom: BASE_BOTTOM + footerOffset,
            pointerEvents: "auto",
          }}
        >
          <Magnetic strength={0.3}>
            <motion.button
              type="button"
              initial={{ opacity: 0, scale: 0.5, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.5, y: 20 }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              className="back-to-top-fab"
              whileHover={{ scale: 1.1, y: -3 }}
              whileTap={{ scale: 0.92 }}
              aria-label={t("common:buttons.backToTop")}
              onClick={onClick}
            >
              <ArrowUp size={22} strokeWidth={2.5} />
            </motion.button>
          </Magnetic>
        </div>
      )}
    </AnimatePresence>
  )
}
