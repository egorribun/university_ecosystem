import { useEffect, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowUp } from "lucide-react"
import Magnetic from "./Magnetic"
import { useTheme } from "@/contexts/ThemeContext"

export default function BackToTop() {
  const { t } = useTranslation(["common"])
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === "dark"

  const [show, setShow] = useState(false)
  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 420)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
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
          className="fixed bottom-6 right-6 z-tooltip"
          style={{ pointerEvents: "auto" }}
        >
          <Magnetic strength={0.3}>
            <motion.button
              type="button"
              initial={{ opacity: 0, scale: 0.5, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.5, y: 20 }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              style={{
                width: 52,
                height: 52,
                borderRadius: "50%",
                border: "none",
                backgroundColor: isDark ? "#f0f0f0" : "#1a1a1a",
                color: isDark ? "#1a1a1a" : "#ffffff",
                boxShadow: isDark
                  ? "0 4px 16px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)"
                  : "0 4px 14px rgba(0,0,0,0.25), 0 2px 4px rgba(0,0,0,0.12), inset 0 1px 0 rgba(255,255,255,0.15)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
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
