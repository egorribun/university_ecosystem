import { useEffect, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowUp } from "lucide-react"
import Magnetic from "./Magnetic"
import { cn } from "@/utils/cn"

export default function BackToTop() {
  const { t } = useTranslation(["common"])
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
          className="fixed bottom-6 right-6 z-(--z-tooltip)"
          style={{ pointerEvents: show ? "auto" : "none" }}
        >
          <Magnetic strength={0.3}>
            <motion.button
              type="button"
              initial={{ opacity: 0, scale: 0.5, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.5, y: 20 }}
              className={cn(
                "group relative flex h-12 w-12 items-center justify-center rounded-full border border-white/20 bg-primary shadow-lg transition-transform active:scale-95",
                "before:absolute before:inset-0 before:rounded-full before:bg-white/10 before:opacity-0 before:transition-opacity hover:before:opacity-100"
              )}
              aria-label={t("common:buttons.backToTop")}
              onClick={onClick}
            >
              <ArrowUp className="text-white transition-transform group-hover:-translate-y-1" />
            </motion.button>
          </Magnetic>
        </div>
      )}
    </AnimatePresence>
  )
}
