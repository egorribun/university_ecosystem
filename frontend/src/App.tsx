import { useTranslation } from "react-i18next"
import { AppProviders } from "./AppProviders"
import { AppRoutes } from "./AppRoutes"



/**
 * World-Class Modular App Registry
 */
function AppShell() {
  const { t } = useTranslation("common")

  // Check for forced bootstrap error (used in E2E tests)
  if (
    typeof window !== "undefined" &&
    (window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean })
      .__APP_BOOTSTRAP_FORCE_ERROR__
  ) {
    throw new Error("Bootstrap failed")
  }

  return (
    <>
      <a href="#main" className="skip-link">
        {t("skipToContent")}
      </a>
      <AppRoutes />
    </>
  )
}

export default function App() {
  return (
    <AppProviders>
      <AppShell />
    </AppProviders>
  )
}
