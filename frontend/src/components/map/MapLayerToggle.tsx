import { motion, useReducedMotion } from "framer-motion"
import { Map as MapIcon, Layers } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { MapViewMode } from "@/features/map/MapFeature"

interface MapLayerToggleProps {
  viewMode: MapViewMode
  onToggle: (mode: MapViewMode) => void
  buildingName?: string
}

/**
 * Campus/floor-plan toggle pills — Framer Motion layoutId for smooth indicator.
 * Mirrors the layer toggle pattern from old MapContent.
 */
export function MapLayerToggle({ viewMode, onToggle, buildingName }: MapLayerToggleProps) {
  const { t } = useTranslation("map")
  const prefersReduced = useReducedMotion() ?? false

  const modes: Array<{ key: MapViewMode; label: string; icon: typeof MapIcon }> = [
    { key: "campus", label: t("layers.campus"), icon: MapIcon },
    { key: "floorplan", label: buildingName ?? t("layers.floorplan"), icon: Layers },
  ]

  return (
    <div
      role="radiogroup"
      aria-label={t("layers.ariaLabel")}
      className="map-layer-toggle inline-flex items-center gap-0.5"
    >
      {modes.map(({ key, label, icon: Icon }) => {
        const isActive = viewMode === key
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onToggle(key)}
            className="relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-bold transition-colors"
            style={{ color: isActive ? "var(--map-layer-active-text)" : "var(--text-secondary)" }}
          >
            {isActive && (
              <motion.div
                layoutId="map-layer-indicator"
                className="absolute inset-0 rounded-full"
                style={{ backgroundColor: "var(--map-layer-active-bg)" }}
                transition={
                  prefersReduced
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 400, damping: 30 }
                }
              />
            )}
            <span className="relative z-[1] flex items-center gap-2">
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{label}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
