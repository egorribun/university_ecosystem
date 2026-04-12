/**
 * campusPOI.ts — Hardcoded key points of interest around GUU campus.
 *
 * Core POIs are embedded for instant loading (no network required).
 * Additional POIs can be loaded on demand via Overpass API (useOverpassPOI).
 *
 * Wave 99 — campus map Leaflet integration.
 */

export type POICategory = "transport" | "food" | "shop" | "service" | "campus"

export interface CampusPOI {
  /** Unique identifier */
  id: string
  /** Category for filtering and icon selection */
  type: POICategory
  /** WGS84 coordinates [lat, lng] */
  coords: [number, number]
  /** Lucide icon name */
  icon: string
  /** i18n key suffix — resolved as map:poi.items.<id>.name */
  i18nKey: string
}

/**
 * Key POIs around GUU campus (Рязанский проспект, 99, Moscow).
 * Coordinates are approximate — sufficient for Leaflet marker placement.
 */
export const CAMPUS_POIS: readonly CampusPOI[] = [
  /* ── Transport ── */
  {
    id: "metro-vykhino",
    type: "transport",
    coords: [55.7156, 37.8172],
    icon: "TrainFront",
    i18nKey: "metro-vykhino",
  },
  {
    id: "bus-guu",
    type: "transport",
    coords: [55.7142, 37.8135],
    icon: "Bus",
    i18nKey: "bus-guu",
  },
  {
    id: "bus-ryazansky",
    type: "transport",
    coords: [55.7130, 37.8160],
    icon: "Bus",
    i18nKey: "bus-ryazansky",
  },
  /* ── Food ── */
  {
    id: "canteen-guu",
    type: "food",
    coords: [55.7140, 37.8148],
    icon: "UtensilsCrossed",
    i18nKey: "canteen-guu",
  },
  {
    id: "cafe-nearby-1",
    type: "food",
    coords: [55.7135, 37.8120],
    icon: "Coffee",
    i18nKey: "cafe-nearby-1",
  },
  {
    id: "cafe-nearby-2",
    type: "food",
    coords: [55.7148, 37.8165],
    icon: "Coffee",
    i18nKey: "cafe-nearby-2",
  },
  /* ── Services ── */
  {
    id: "atm-guu",
    type: "service",
    coords: [55.7141, 37.8150],
    icon: "Landmark",
    i18nKey: "atm-guu",
  },
  {
    id: "parking-guu",
    type: "campus",
    coords: [55.7133, 37.8142],
    icon: "ParkingCircle",
    i18nKey: "parking-guu",
  },
  /* ── Shops ── */
  {
    id: "shop-nearby",
    type: "shop",
    coords: [55.7127, 37.8155],
    icon: "ShoppingBag",
    i18nKey: "shop-nearby",
  },
  {
    id: "pharmacy-nearby",
    type: "shop",
    coords: [55.7150, 37.8130],
    icon: "Pill",
    i18nKey: "pharmacy-nearby",
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
