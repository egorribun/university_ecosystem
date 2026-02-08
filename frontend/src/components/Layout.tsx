import { ReactNode } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { WifiOff } from "lucide-react"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { cn } from "../utils/cn"
import { fadeVariants } from "@/utils/animations"

type LayoutProps = {
  children: ReactNode
  className?: string
}

const Layout = ({ children, className }: LayoutProps) => {
  const isOnline = useOnlineStatus()
  const { t } = useTranslation("system")

  return (
    <motion.main
      id="main"
      role="main"
      tabIndex={-1}
      initial="hidden"
      animate="visible"
      exit="exit"
      variants={fadeVariants}
      className={cn(
        "box-border min-h-screen w-full bg-[var(--page-bg)] text-[var(--page-foreground)]",
        className
      )}
    >
      <AnimatePresence>
        {!isOnline && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="sticky top-0 z-[100] flex w-full items-center justify-center gap-2 bg-amber-500/90 py-1 text-[0.7rem] font-bold uppercase tracking-wider text-amber-950 backdrop-blur-md dark:bg-amber-600/90 dark:text-amber-50"
          >
            <WifiOff size={14} />
            <span>{t("offlineIndicator.offline")}</span>
          </motion.div>
        )}
      </AnimatePresence>
      {children}
    </motion.main>
  )
}

export default Layout
