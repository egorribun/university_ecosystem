import { ReactNode } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import WifiOffIcon from "@mui/icons-material/WifiOff"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { cn } from "../utils/cn"

type LayoutProps = {
  children: ReactNode
  className?: string
}

const Layout = ({ children, className }: LayoutProps) => {
  const isOnline = useOnlineStatus()
  const { t } = useTranslation("system")

  return (
    <main
      id="main"
      role="main"
      tabIndex={-1}
      className={cn(
        "box-border min-h-screen w-full bg-[var(--page-bg)] text-[var(--page-text)]",
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
            <WifiOffIcon sx={{ fontSize: 14 }} />
            <span>{t("offlineIndicator.offline")}</span>
          </motion.div>
        )}
      </AnimatePresence>
      {children}
    </main>
  )
}

export default Layout
