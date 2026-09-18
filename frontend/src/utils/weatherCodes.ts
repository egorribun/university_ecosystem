export type WeatherCondition = "clear" | "cloudy" | "rain" | "snow" | "fog" | "storm"

export const WEATHER_CONDITION_CLEAR: WeatherCondition = "clear"

const WMO_MAP: Record<number, WeatherCondition> = {
  0: WEATHER_CONDITION_CLEAR,
  1: WEATHER_CONDITION_CLEAR,
  2: "cloudy",
  3: "cloudy",
  45: "fog",
  48: "fog",
  51: "rain",
  53: "rain",
  55: "rain",
  56: "rain",
  57: "rain",
  61: "rain",
  63: "rain",
  65: "rain",
  66: "rain",
  67: "rain",
  71: "snow",
  73: "snow",
  75: "snow",
  77: "snow",
  80: "rain",
  81: "rain",
  82: "rain",
  85: "snow",
  86: "snow",
  95: "storm",
  96: "storm",
  99: "storm",
}

export function wmoToCondition(code: number): WeatherCondition {
  return WMO_MAP[code] ?? WEATHER_CONDITION_CLEAR
}
