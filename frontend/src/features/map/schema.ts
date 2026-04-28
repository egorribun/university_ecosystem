import * as v from "valibot"

/**
 * Map route search-param schema — Wave 120 SW5 URL-sync.
 *
 * URL form: `?z=16.5&lat=55.71440&lng=37.81800&p=45&b=120` (numbers, not
 * JSON-quoted strings). TanStack Router's default `stringifySearch`
 * JSON-quotes string values that LOOK like numbers (to preserve string type
 * vs ambiguous parsing); Map state must therefore round-trip through actual
 * numbers to keep URLs clean.
 *
 * `v.fallback(..., undefined)` makes invalid values silently drop to undefined
 * instead of throwing — important so a bad URL like `?z=abc` doesn't crash
 * the route, it just falls back to the default cinematic-intro behavior.
 *
 *   z   — zoom level (8 ≤ z ≤ 20, ~1 decimal precision)
 *   lat — latitude (Moscow campus area: 55.6 ≤ lat ≤ 55.8, ~5 decimals)
 *   lng — longitude (37.7 ≤ lng ≤ 37.9, ~5 decimals)
 *   p   — pitch (0 ≤ p ≤ 70, integer — matches MapLibreMap maxPitch={70})
 *   b   — bearing (0 ≤ b < 360, integer)
 *
 * All five must be present together for the consumer to apply URL state
 * (partial state would jumpTo a center without zoom or pitch — confusing UX).
 */

/**
 * Number-or-numeric-string → number coercion.
 *
 * TanStack's default parser preserves number type when URL has a bare numeric
 * value (`?z=16`). Browser-set URLs from setSearch with a number value also
 * arrive as numbers. But manually-constructed URLs (e.g. `?z="16"`) or
 * legacy strings need string→number transform.
 */
const numericField = (min: number, max: number) =>
  v.fallback(
    v.optional(
      v.pipe(
        v.union([
          v.number(),
          v.pipe(
            v.string(),
            v.transform((s) => Number.parseFloat(s))
          ),
        ]),
        v.number(),
        // Reject NaN (Number.parseFloat returns NaN for non-numeric strings).
        v.check((n) => Number.isFinite(n), "must be finite"),
        v.minValue(min),
        v.maxValue(max)
      )
    ),
    undefined
  )

export const mapSearchSchema = v.object({
  z: numericField(8, 20),
  lat: numericField(55.6, 55.8),
  lng: numericField(37.7, 37.9),
  p: numericField(0, 70),
  b: numericField(0, 360),
})

export type MapSearch = v.InferOutput<typeof mapSearchSchema>

/** Parsed numeric viewport state — all-or-nothing per plan rationale. */
export interface MapViewport {
  zoom: number
  latitude: number
  longitude: number
  pitch: number
  bearing: number
}

/**
 * Convert URL search params into a numeric viewport.
 *
 * Returns null if any required field is missing — the consumer falls back
 * to MapLibre's default cinematic intro in that case. Range/finite checks
 * already happened at schema parse time; values here are guaranteed valid.
 */
export function parseMapViewport(params: MapSearch): MapViewport | null {
  if (
    params.z === undefined ||
    params.lat === undefined ||
    params.lng === undefined ||
    params.p === undefined ||
    params.b === undefined
  ) {
    return null
  }
  return {
    zoom: params.z,
    latitude: params.lat,
    longitude: params.lng,
    pitch: params.p,
    bearing: ((params.b % 360) + 360) % 360,
  }
}

/**
 * Convert numeric viewport state to URL-friendly numbers with rounded precision.
 *
 *   - lat/lng: 5 decimals (~1.1 m at this latitude — sub-meter would be noise)
 *   - zoom: 1 decimal (MapLibre's smallest meaningful zoom step is ~0.1)
 *   - pitch: 0 decimals (MapLibre keyboard pitch step is 10°)
 *   - bearing: 0 decimals (MapLibre keyboard rotate step is 15°)
 *
 * Returns numbers (not strings) so TanStack's stringifier emits clean URLs
 * like `?z=16&lat=55.71440` instead of `?z=%2216%22&lat=%2255.71440%22`.
 */
export function serializeMapViewport(state: {
  zoom: number
  latitude: number
  longitude: number
  pitch: number
  bearing: number
}): MapSearch {
  return {
    z: Number(state.zoom.toFixed(1)),
    lat: Number(state.latitude.toFixed(5)),
    lng: Number(state.longitude.toFixed(5)),
    p: Math.round(state.pitch),
    b: Math.round(((state.bearing % 360) + 360) % 360),
  }
}
