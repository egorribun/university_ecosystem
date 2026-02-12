import React from "react"
import { useLocation } from "react-router-dom"
import Navbar from "@/components/Navbar"
import Footer from "@/components/Footer"
import MobileBottomNav from "@/components/MobileBottomNav"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

interface MainLayoutProps {
  children: React.ReactNode
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const { t } = useTranslation(["navigation"])
  const location = useLocation()
  const path = location.pathname

  // Pages that should not show the main navigation/footer
  const isCompactPage = ["/login", "/register", "/forgot-password", "/messenger"].some((p) =>
    path.startsWith(p)
  )

  // Specific pages that might hide certain elements
  const hideFooter = path.startsWith("/map") || path.startsWith("/schedule")

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-(--z-tooltip) focus:rounded-2xl focus:bg-primary-main focus:px-6 focus:py-3 focus:text-white focus:shadow-premium-lift focus:outline-none focus:ring-4 focus:ring-primary-main/(--opacity-dim)"
      >
        {t("navigation:aria.skipLink")}
      </a>

      {!isCompactPage && <Navbar />}

      <main
        id="main-content"
        className={cn(
          "flex-1 w-full outline-none",
          path.startsWith("/messenger") ? "overflow-hidden" : "overflow-y-auto"
        )}
      >
        {children}
      </main>

      {!isCompactPage && !hideFooter && <Footer />}
      {!isCompactPage && <MobileBottomNav />}
    </div>
  )
}

export default MainLayout
