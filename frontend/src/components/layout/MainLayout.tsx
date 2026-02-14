import React from "react"
import { useRouteType } from "@/hooks/useRouteType"
import Navbar from "@/components/navbar"
import Footer from "@/components/Footer"
import MobileBottomNav from "@/components/MobileBottomNav"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

interface MainLayoutProps {
  children: React.ReactNode
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const { t } = useTranslation(["navigation"])
  const { isCompactPage, hideFooter, isMessenger } = useRouteType()

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
          isMessenger ? "overflow-hidden" : "overflow-y-auto"
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
