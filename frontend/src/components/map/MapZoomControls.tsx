import { Minus, Plus, RotateCcw } from "lucide-react"
import { useTranslation } from "react-i18next"

interface MapZoomControlsProps {
  onZoomIn: () => void
  onZoomOut: () => void
  onReset: () => void
  canZoomIn: boolean
  canZoomOut: boolean
  isZoomed: boolean
}

/**
 * Accessible zoom controls overlay — + / - / reset buttons.
 * Positioned bottom-right of the map viewport.
 */
export function MapZoomControls({
  onZoomIn,
  onZoomOut,
  onReset,
  canZoomIn,
  canZoomOut,
  isZoomed,
}: MapZoomControlsProps) {
  const { t } = useTranslation("map")

  return (
    <div
      className="map-zoom-controls flex flex-col gap-0.5 p-1"
      role="group"
      aria-label={t("zoom.ariaLabel")}
    >
      <button
        type="button"
        onClick={onZoomIn}
        disabled={!canZoomIn}
        className="map-zoom-btn h-9 w-9 flex items-center justify-center rounded-t-md disabled:opacity-30"
        aria-label={t("zoom.in")}
      >
        <Plus className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={onZoomOut}
        disabled={!canZoomOut}
        className="map-zoom-btn h-9 w-9 flex items-center justify-center disabled:opacity-30"
        aria-label={t("zoom.out")}
      >
        <Minus className="h-4 w-4" />
      </button>
      {isZoomed && (
        <button
          type="button"
          onClick={onReset}
          className="map-zoom-btn h-9 w-9 flex items-center justify-center rounded-b-md text-[var(--color-teal-500)]"
          aria-label={t("zoom.reset")}
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}
