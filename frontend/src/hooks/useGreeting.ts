import { useMemo } from "react"
import { useTranslation } from "react-i18next"

export type GreetingKey = "morning" | "afternoon" | "evening" | "night"

/** Wave 47: Calendar-based special greeting keys */
export type SpecialGreetingKey = "newYear" | "newYearEve" | "knowledgeDay" | null

/** Wave 48: Contextual emoji based on time-of-day + day-of-week */
const GREETING_EMOJI: Record<GreetingKey, Record<number | "default", string>> = {
  morning: { 1: "😴", 5: "🎉", default: "☀️" }, // Monday=sleepy, Friday=party
  afternoon: { 5: "🎉", default: "🌤️" },
  evening: { 5: "🎉", default: "🌆" },
  night: { default: "🌙" },
}

const SPECIAL_EMOJI: Record<Exclude<SpecialGreetingKey, null>, string> = {
  newYear: "🎄",
  newYearEve: "🎄",
  knowledgeDay: "🎓",
}

export function getContextualEmoji(
  greetingKey: GreetingKey,
  dayOfWeek: number,
  specialKey: SpecialGreetingKey
): string {
  if (specialKey) return SPECIAL_EMOJI[specialKey]
  const dayMap = GREETING_EMOJI[greetingKey]
  return dayMap[dayOfWeek] ?? dayMap.default
}

export function getGreetingKey(hour: number): GreetingKey {
  if (hour >= 4 && hour < 12) return "morning"
  if (hour >= 12 && hour < 17) return "afternoon"
  if (hour >= 17 && hour <= 23) return "evening"
  return "night"
}

/** Wave 47: Check for special calendar dates */
export function getSpecialGreeting(date: Date): SpecialGreetingKey {
  const month = date.getMonth() // 0-indexed
  const day = date.getDate()

  if (month === 0 && day === 1) return "newYear" // Jan 1
  if (month === 11 && day === 31) return "newYearEve" // Dec 31
  if (month === 8 && day === 1) return "knowledgeDay" // Sep 1
  return null
}

export function useGreeting(time: Date) {
  const { t } = useTranslation(["dashboard"])

  const hour = time.getHours()
  const greetingKey = useMemo(() => getGreetingKey(hour), [hour])

  const specialKey = useMemo(() => getSpecialGreeting(time), [time])

  // Special greeting overrides time-of-day greeting text, but keeps palette
  const greeting = specialKey
    ? t(`dashboard:greeting.special.${specialKey}`, {
        defaultValue: t(`dashboard:greeting.${greetingKey}`),
      })
    : t(`dashboard:greeting.${greetingKey}`)

  // Wave 48: Contextual emoji
  const dayOfWeek = time.getDay()
  const emoji = useMemo(
    () => getContextualEmoji(greetingKey, dayOfWeek, specialKey),
    [greetingKey, dayOfWeek, specialKey]
  )

  return { greeting, greetingKey, specialKey, emoji }
}
