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

const CLEAR = createMeta("Clear sky", "clear", "☀️", "glow")
const MOSTLY_CLEAR = createMeta("Mostly clear", "mostlyClear", "🌤️", "glow")
const OVERCAST = createMeta("Overcast", "cloudy", "☁️", "breeze")
const FOG = createMeta("Fog", "fog", "🌫️", "none")
const DRIZZLE = createMeta("Drizzle", "drizzle", "🌦️", "drizzle")
const FREEZING_DRIZZLE = createMeta("Freezing drizzle", "freezingDrizzle", "🌧️", "drizzle")
const RAIN = createMeta("Rain", "rain", "🌧️", "drizzle")
const FREEZING_RAIN = createMeta("Freezing rain", "freezingRain", "🌧️", "drizzle")
const SNOWFALL = createMeta("Snowfall", "snow", "🌨️", "snow")
const SNOW_GRAINS = createMeta("Snow grains", "snowGrains", "❄️", "snow")
const RAIN_SHOWERS = createMeta("Rain showers", "rainShowers", "🌦️", "drizzle")
const SNOW_SHOWERS = createMeta("Snow showers", "snowShowers", "🌨️", "snow")
const THUNDERSTORM = createMeta("Thunderstorm", "thunderstorm", "⛈️", "storm")
const THUNDERSTORM_HAIL = createMeta("Thunderstorm with hail", "thunderstormHail", "⛈️", "storm")

// WMO weather interpretation codes used by the provider.
const WEATHER_CODE_META: Readonly<Record<number, WeatherIconMeta>> = {
  0: CLEAR,
  1: MOSTLY_CLEAR,
  2: MOSTLY_CLEAR,
  3: OVERCAST,
  45: FOG,
  48: FOG,
  51: DRIZZLE,
  53: DRIZZLE,
  55: DRIZZLE,
  56: FREEZING_DRIZZLE,
  57: FREEZING_DRIZZLE,
  61: RAIN,
  63: RAIN,
  65: RAIN,
  66: FREEZING_RAIN,
  67: FREEZING_RAIN,
  71: SNOWFALL,
  73: SNOWFALL,
  75: SNOWFALL,
  77: SNOW_GRAINS,
  80: RAIN_SHOWERS,
  81: RAIN_SHOWERS,
  82: RAIN_SHOWERS,
  85: SNOW_SHOWERS,
  86: SNOW_SHOWERS,
  95: THUNDERSTORM,
  96: THUNDERSTORM_HAIL,
  99: THUNDERSTORM_HAIL,
}

// A missing, NaN or infinite code truncates to a key the table never holds.
export const getWeatherIconMeta = (code: number | null | undefined): WeatherIconMeta =>
  WEATHER_CODE_META[Math.trunc(code ?? Number.NaN)] ?? FALLBACK_META

export const getWeatherLabel = (code: number | null | undefined): string =>
  getWeatherIconMeta(code).label

export const WEATHER_ICON_FALLBACK = FALLBACK_META
