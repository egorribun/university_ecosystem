import { MapPin } from "lucide-react"
import { useTranslation } from "react-i18next"
import FadeSection from "@/components/motion/FadeSection"

interface MapHeaderProps {
  buildingCount: number
}

/**
 * Premium page header — news-style layout with FadeSection stagger.
 * Icon hidden on mobile (<sm). Badge inline in h1.
 */
export function MapHeader({ buildingCount }: MapHeaderProps) {
  const { t } = useTranslation("map")

  return (
    <header className="mb-8">
      <FadeSection delay="60ms" className="flex items-center gap-4">
        <div className="map-badge-matte hidden sm:flex items-center justify-center h-14 w-14 rounded-xl bg-[color-mix(in_srgb,var(--color-teal-500)_12%,var(--bg-surface))]">
          <MapPin className="h-7 w-7 text-[var(--color-teal-500)]" />
        </div>
        <div>
          <h1
            className="font-black tracking-tight text-text-primary"
            style={{ fontSize: "var(--fs-map-hero)" }}
          >
            {t("page.title")}{" "}
            <span
              className="align-middle inline-flex items-center gap-1 rounded-full bg-[color-mix(in_srgb,var(--color-teal-500)_12%,var(--bg-surface))] px-2.5 py-0.5 font-bold text-[var(--color-teal-500)]"
              style={{ fontSize: "0.45em" }}
            >
              {t("page.badge")}
            </span>
          </h1>
          <p
            className="text-[var(--text-secondary)] font-medium mt-1"
            style={{ fontSize: "var(--fs-map-subtitle)" }}
          >
            {t("page.subtitle")}
          </p>
        </div>
      </FadeSection>

      {/* Building count summary */}
      <FadeSection delay="120ms" className="mt-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-tertiary)]">
          <span>{buildingCount} {t("tooltip.clickToExplore").toLowerCase()}</span>
        </div>
      </FadeSection>
    </header>
  )
}
