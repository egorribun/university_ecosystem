export type Season = "spring" | "summer" | "autumn" | "winter"

/**
 * Current season based on month. Pure computation — no reactivity needed.
 * spring=Mar-May, summer=Jun-Aug, autumn=Sep-Nov, winter=Dec-Feb.
 * Wave 108
 */
export function useSeason(): Season {
  const month = new Date().getMonth()
  if (month >= 2 && month <= 4) return "spring"
  if (month >= 5 && month <= 7) return "summer"
  if (month >= 8 && month <= 10) return "autumn"
  return "winter"
}
