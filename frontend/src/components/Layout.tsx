import { ReactNode } from "react"
import { m, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { WifiOff } from "lucide-react"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { cn } from "@/utils/cn"
import { fadeVariants } from "@/utils/animations"

type LayoutProps = {
  children: ReactNode
  className?: string
}

const Layout = ({ children, className }: LayoutProps) => {
  const isOnline = useOnlineStatus()
  const { t } = useTranslation("system")

  // Wave 120 SW3 (a11y/ARIA): switched `<m.main id="main">` to
  // `<m.div>` to fix duplicate main landmark — MainLayout already
  // provides `<main id="main-content">` at the page level. The inner
  // `id="main"` was orphan in production (only `tests/accessibility/skipLink.test.tsx`
  // referenced it via fixture HTML; production skip link points at
  // `#main-content`). Closes axe `landmark-no-duplicate-main` +
  // `landmark-main-is-top-level` + `landmark-unique` violations on /schedule
  // (and same global issue on every page using PageLayout — 10+ callsites).
  return (
    <m.div
      data-scroll-root
      tabIndex={-1}
      initial="hidden"
      animate="visible"
      exit="exit"
      variants={fadeVariants}
      className={cn("box-border min-h-screen w-full bg-page text-text-primary", className)}
    >
      <AnimatePresence>
        {!isOnline && (
          <m.div
            role="status"
            aria-live="polite"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="sticky top-0 z-sticky flex w-full items-center justify-center gap-2 bg-warning-bg/(--opacity-heavy) py-1 text-badge font-bold uppercase tracking-wider text-warning-text backdrop-blur-md"
          >
            <WifiOff className="size-(--size-icon-sm)" />
            <span>{t("offlineIndicator.offline")}</span>
          </m.div>
        )}
      </AnimatePresence>
      {children}
    </m.div>
  )
}

export default Layout
