/**
 * campusPOI.ts — Verified points of interest around GUU campus.
 *
 * Core POIs are embedded for instant loading (no network required).
 * Additional POIs can be loaded on demand via Overpass API (useOverpassPOI).
 *
 * Wave 99 — initial; Wave 101 — all coordinates verified via 2GIS/Yandex Maps/Nominatim/Moovit.
 */

export type POICategory = "transport" | "food" | "shop" | "service" | "campus"

export interface CampusPOI {
  /** Unique identifier */
  id: string
  /** Category for filtering and icon selection */
  type: POICategory
  /** WGS84 coordinates [lat, lng] — verified April 2026 */
  coords: [number, number]
  /** Lucide icon name */
  icon: string
  /** i18n key suffix — resolved as map:poi.items.<id>.name */
  i18nKey: string
}

/**
 * Key POIs around GUU campus (Рязанский проспект, 99, Moscow).
 * All coordinates verified via 2GIS, Yandex Maps, Nominatim, Moovit.
 */
export const CAMPUS_POIS: readonly CampusPOI[] = [
  /* ── Transport ── */
  {
    id: "metro-vykhino",
    type: "transport",
    coords: [55.71570, 37.81642],
    icon: "TrainFront",
    i18nKey: "metro-vykhino",
  },
  {
    id: "bus-guu",
    type: "transport",
    coords: [55.71366, 37.81055],
    icon: "Bus",
    i18nKey: "bus-guu",
  },
  {
    id: "bus-sormovskaya",
    type: "transport",
    coords: [55.71155, 37.81342],
    icon: "Bus",
    i18nKey: "bus-sormovskaya",
  },
  /* ── Food ── */
  {
    id: "canteen-guu",
    type: "food",
    coords: [55.71387, 37.81585],
    icon: "UtensilsCrossed",
    i18nKey: "canteen-guu",
  },
  {
    id: "cafe-kletka",
    type: "food",
    coords: [55.71341, 37.81590],
    icon: "Coffee",
    i18nKey: "cafe-kletka",
  },
  {
    id: "library-guu",
    type: "campus",
    coords: [55.71385, 37.81673],
    icon: "BookOpen",
    i18nKey: "library-guu",
  },
  /* ── Services ── */
  {
    id: "atm-sber",
    type: "service",
    coords: [55.71410, 37.81190],
    icon: "Landmark",
    i18nKey: "atm-sber",
  },
  {
    id: "parking-guu",
    type: "campus",
    coords: [55.71359, 37.81388],
    icon: "ParkingCircle",
    i18nKey: "parking-guu",
  },
  /* ── Shops (ТЦ Маяк cluster — Рязанский пр-т, 99а стр.1) ── */
  {
    id: "pyaterochka",
    type: "shop",
    coords: [55.71250, 37.81640],
    icon: "ShoppingCart",
    i18nKey: "pyaterochka",
  },
  {
    id: "gorzdrav",
    type: "shop",
    coords: [55.71260, 37.81640],
    icon: "Pill",
    i18nKey: "gorzdrav",
  },
  {
    id: "fix-price",
    type: "shop",
    coords: [55.71260, 37.81640],
    icon: "ShoppingBag",
    i18nKey: "fix-price",
  },
] as const

/**
 * POI category → icon color CSS variable mapping.
 */
export const POI_CATEGORY_COLORS: Record<POICategory, string> = {
  transport: "var(--map-poi-transport)",
  food: "var(--map-poi-food)",
  shop: "var(--map-poi-shop)",
  service: "var(--map-poi-service)",
  campus: "var(--map-poi-campus)",
}
