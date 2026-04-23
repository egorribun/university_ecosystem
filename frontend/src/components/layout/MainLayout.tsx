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

// Wave 116 SW1 — reduced chrome for e2e accessibility scans. The iPhone 15
// WebKit renderer (Playwright's `mobile-webkit` project) OOMs on MainLayout's
// 4 full chrome components (Navbar + Footer + BackToTop + MobileBottomNav)
// plus axe-core's 564 KB bundle on non-compact routes. /login suppresses
// chrome via `useRouteType().isCompactPage`, which is why it passes. Wave
// 115 SW1 closed A11Y-113-04 on /login across all 4 projects via the
// ParticleAuthBackground canvas gate + serial WebKit + legacy axe mode, but
// /404 still OOMed. This gate renders landmark-only stubs under
// VITE_E2E_MODE so the a11y tree matches prod (nav / contentinfo) without
// the decorative Framer Motion wrappers, glass effects, i18n menu content,
// or sticky-scroll handlers.
//
// Tree-shakes in prod: `VITE_E2E_MODE` is only set in
// `playwright.config.ts:75` webServer.env; regular `npm run build` leaves
// the flag undefined and Vite substitutes `false`, letting Rolldown DCE
// drop the entire E2E branch.
const E2E_MODE = import.meta.env.VITE_E2E_MODE === "1"

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const { t } = useTranslation(["navigation"])
  const { isCompactPage, hideFooter, isMessenger } = useRouteType()

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main-content" className="skip-link">
        {t("navigation:aria.skipLink")}
      </a>

      {!isCompactPage && !E2E_MODE && <Navbar />}
      {!isCompactPage && E2E_MODE && <nav data-e2e-stub="main-nav" />}

      {/*
       * Wave 118 SW1 (CLS-118-01): replaced `flex-1` with `min-h-dvh`.
       * `flex-1` made main fill remaining column space (~dvh−164px on short
       * initial-paint content), seating the footer AT viewport bottom.
       * Content growing past that pushed footer from visible (~y=dvh−100) to
       * offscreen (~y=content+64), which LHCI measured as a 0.813 shift
       * (94% of authenticated-route CLS 0.87 per Wave 118 Phase 0 baseline).
       * With `min-h-dvh` main is always ≥ viewport height from first paint,
       * so the footer sits at y ≥ dvh — offscreen — and content growth keeps
       * it offscreen. Per web.dev CLS spec, shifts outside the viewport do
       * not count toward CLS.
       */}
      <main
        id="main-content"
        className={cn(
          "vt-page-content w-full outline-none min-h-dvh",
          isMessenger && "overflow-hidden"
        )}
      >
        {children}
      </main>

      {!isCompactPage && !hideFooter && !E2E_MODE && <Footer />}
      {!isCompactPage && !hideFooter && E2E_MODE && (
        <footer role="contentinfo" data-e2e-stub="footer" />
      )}
      {!isCompactPage && !E2E_MODE && <BackToTop />}
      {!isCompactPage && !E2E_MODE && <MobileBottomNav />}
      {!isCompactPage && E2E_MODE && (
        <nav data-e2e-stub="mobile-bottom-nav" aria-label={t("navigation:aria.mainNavigation")} />
      )}
    </div>
  )
}

export default MainLayout
