import { MapPin } from "lucide-react"
import { useTranslation } from "react-i18next"
import FadeSection from "@/components/motion/FadeSection"

/**
 * MapHeader — unified page header matching News/Schedule/Events/Activity pattern.
 * Icon: h-11 w-11, hidden on mobile. Badge: inline in h1 at 0.45em.
 * FIX-109-05: aligned to cross-page header standard (Wave 73 pattern).
 */
export function MapHeader() {
  const { t } = useTranslation("map")

  return (
    <header className="mb-6 sm:mb-8">
      <FadeSection delay="60ms" className="flex items-center gap-2 sm:gap-3">
        <div className="map-badge-matte hidden sm:flex h-11 w-11 items-center justify-center rounded-xl text-text-primary shrink-0">
          <MapPin size={20} strokeWidth={2.2} />
        </div>
        <h1 className="text-fluid-h1 font-extrabold tracking-tight text-text-primary">
          {t("page.title")}
          <span
            className="map-badge-matte ml-2 inline-flex items-center justify-center rounded-full px-2 py-0.5 align-middle font-bold text-[var(--map-accent-icon)] leading-none"
            style={{ fontSize: "0.45em" }}
          >
            {t("page.badge")}
          </span>
        </h1>
      </FadeSection>
    </header>
  )
}
