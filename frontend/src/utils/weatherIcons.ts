export type WeatherAnimationVariant = "none" | "glow" | "breeze" | "drizzle" | "snow" | "storm"

export interface WeatherIconMeta {
  /** Provider-specific condition identifier. */
  icon: string
  /** Translation key suffix appended to the weather namespace. */
  translationKeySuffix: string
  /** Short English label for quick fallbacks. */
  label: string
  /** Suggested animation style for expressive widgets. */
  animation: WeatherAnimationVariant
}

const createMeta = (
  label: string,
  translationKeySuffix: string,
  icon: string,
  animation: WeatherAnimationVariant
): WeatherIconMeta =>
  Object.freeze({
    label,
    translationKeySuffix,
    icon,
    animation,
  })

const FALLBACK_META = createMeta("Unknown conditions", "unknown", "🌡️", "none")

const CODE_GROUPS: Array<{ codes: number[]; meta: WeatherIconMeta }> = [
  { codes: [0], meta: createMeta("Clear sky", "clear", "☀️", "glow") },
  { codes: [1, 2], meta: createMeta("Mostly clear", "mostlyClear", "🌤️", "glow") },
  { codes: [3], meta: createMeta("Overcast", "cloudy", "☁️", "breeze") },
  { codes: [45, 48], meta: createMeta("Fog", "fog", "🌫️", "none") },
  { codes: [51, 53, 55], meta: createMeta("Drizzle", "drizzle", "🌦️", "drizzle") },
  { codes: [56, 57], meta: createMeta("Freezing drizzle", "freezingDrizzle", "🌧️", "drizzle") },
  { codes: [61, 63, 65], meta: createMeta("Rain", "rain", "🌧️", "drizzle") },
  { codes: [66, 67], meta: createMeta("Freezing rain", "freezingRain", "🌧️", "drizzle") },
  { codes: [71, 73, 75], meta: createMeta("Snowfall", "snow", "🌨️", "snow") },
  { codes: [77], meta: createMeta("Snow grains", "snowGrains", "❄️", "snow") },
  { codes: [80, 81, 82], meta: createMeta("Rain showers", "rainShowers", "🌦️", "drizzle") },
  { codes: [85, 86], meta: createMeta("Snow showers", "snowShowers", "🌨️", "snow") },
  { codes: [95], meta: createMeta("Thunderstorm", "thunderstorm", "⛈️", "storm") },
  {
    codes: [96, 99],
    meta: createMeta("Thunderstorm with hail", "thunderstormHail", "⛈️", "storm"),
  },
]

const WEATHER_CODE_META: Record<number, WeatherIconMeta> = {}
for (const { codes, meta } of CODE_GROUPS) {
  for (const code of codes) {
    WEATHER_CODE_META[code] = meta
  }
}

export const getWeatherIconMeta = (code: number | null | undefined): WeatherIconMeta => {
  if (code == null || !Number.isFinite(code)) return FALLBACK_META
  const key = Math.trunc(code)
  return WEATHER_CODE_META[key] ?? FALLBACK_META
}

export const getWeatherLabel = (code: number | null | undefined): string =>
  getWeatherIconMeta(code).label

export const WEATHER_ICON_FALLBACK = FALLBACK_META




