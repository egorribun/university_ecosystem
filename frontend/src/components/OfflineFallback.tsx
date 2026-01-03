import { motion } from "framer-motion"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"
import WifiOffIcon from "@mui/icons-material/WifiOff"
import HomeIcon from "@mui/icons-material/Home"
import RefreshIcon from "@mui/icons-material/Refresh"
import { Button } from "@/components/ui"

interface OfflineFallbackProps {
  onRetry?: () => void
}

export function OfflineFallback({ onRetry }: OfflineFallbackProps) {
  const { t } = useTranslation("system")
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-center px-4 py-20 text-center">
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 20 }}
        className="mb-8 flex h-24 w-24 items-center justify-center rounded-full bg-amber-500/10 text-amber-500"
      >
        <WifiOffIcon sx={{ fontSize: 48 }} />
      </motion.div>

      <motion.h1
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="mb-4 text-2xl font-bold tracking-tight text-[color:var(--page-text)] sm:text-3xl"
      >
        {t("offlineFallback.title")}
      </motion.h1>

      <motion.p
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="mb-10 max-w-md leading-relaxed text-[color:var(--secondary-text)]"
      >
        {t("offlineFallback.description")}
      </motion.p>

      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <Button
          variant="solid"
          onClick={() => onRetry ? onRetry() : window.location.reload()}
          leadingIcon={<RefreshIcon />}
        >
          {t("offlineFallback.retry")}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate("/")}
          leadingIcon={<HomeIcon />}
          className="border-white/10"
        >
          {t("offlineFallback.backHome")}
        </Button>
      </motion.div>
    </div>
  )
}

export default OfflineFallback
