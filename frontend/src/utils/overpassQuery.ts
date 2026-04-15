/**
 * overpassQuery.ts — Build and parse Overpass API queries for POI data.
 *
 * Wave 99 — campus map Leaflet integration.
 */

import type { CampusPOI, POICategory, POIIconName } from "@/data/campusPOI"

const OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

/**
 * Build an Overpass QL query for amenities/shops/transport around a point.
 */
export function buildOverpassQuery(
  center: [number, number],
  radiusMeters: number = 500,
): string {
  const [lat, lng] = center
  return `
[out:json][timeout:10];
(
  node["amenity"~"cafe|restaurant|fast_food|atm|pharmacy|bank"](around:${radiusMeters},${lat},${lng});
  node["shop"](around:${radiusMeters},${lat},${lng});
  node["highway"="bus_stop"](around:${Math.round(radiusMeters * 0.6)},${lat},${lng});
);
out body;
`.trim()
}

interface OverpassElement {
  type: string
  id: number
  lat: number
  lon: number
  tags?: Record<string, string>
}

interface OverpassResponse {
  elements: OverpassElement[]
}

function categorizeElement(tags: Record<string, string>): POICategory {
  if (tags.highway === "bus_stop") return "transport"
  if (tags.amenity && /cafe|restaurant|fast_food/.test(tags.amenity)) return "food"
  if (tags.amenity && /atm|bank/.test(tags.amenity)) return "service"
  if (tags.amenity === "pharmacy") return "shop"
  if (tags.shop) return "shop"
  return "service"
}

function elementIcon(tags: Record<string, string>): POIIconName {
  if (tags.highway === "bus_stop") return "Bus"
  if (tags.amenity === "cafe" || tags.amenity === "fast_food") return "Coffee"
  if (tags.amenity === "restaurant") return "UtensilsCrossed"
  if (tags.amenity === "atm" || tags.amenity === "bank") return "Landmark"
  if (tags.amenity === "pharmacy") return "Pill"
  if (tags.shop) return "ShoppingBag"
  return "MapPin"
}

/**
 * Parse raw Overpass JSON response into CampusPOI items.
 */
export function parseOverpassResponse(json: OverpassResponse): CampusPOI[] {
  return json.elements
    .filter((el): el is OverpassElement & { lat: number; lon: number } =>
      el.type === "node" && typeof el.lat === "number" && typeof el.lon === "number",
    )
    .map((el) => {
      const tags = el.tags ?? {}
      return {
        id: `osm-${el.id}`,
        type: categorizeElement(tags),
        coords: [el.lat, el.lon] as [number, number],
        icon: elementIcon(tags),
        i18nKey: "",
        osmName: tags.name ?? tags["name:en"] ?? tags["name:ru"],
      } satisfies CampusPOI & { osmName?: string }
    })
}

/**
 * Fetch POI data from Overpass API.
 */
export async function fetchOverpassPOIs(
  center: [number, number],
  radius?: number,
): Promise<CampusPOI[]> {
  const query = buildOverpassQuery(center, radius)
  const response = await fetch(OVERPASS_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `data=${encodeURIComponent(query)}`,
  })
  if (!response.ok) {
    throw new Error(`Overpass API error: ${response.status}`)
  }
  const json = (await response.json()) as OverpassResponse
  return parseOverpassResponse(json)
}
