import React from "react"
import { useRouteType } from "@/hooks/useRouteType"
import Navbar from "@/components/navbar"
import Footer from "@/components/layout/Footer"
import BackToTop from "@/components/motion/BackToTop"
import MobileBottomNav from "@/components/layout/MobileBottomNav"
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
      <a href="#main-content" className="skip-link">
        {t("navigation:aria.skipLink")}
      </a>

      {!isCompactPage && <Navbar />}

      <main
        id="main-content"
        className={cn(
          "vt-page-content flex-1 w-full outline-none",
          isMessenger && "overflow-hidden"
        )}
      >
        {children}
      </main>

      {!isCompactPage && !hideFooter && <Footer />}
      {!isCompactPage && <BackToTop />}
      {!isCompactPage && <MobileBottomNav />}
    </div>
  )
}

export default MainLayout
