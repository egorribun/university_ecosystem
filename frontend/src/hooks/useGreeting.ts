import { useMemo } from "react"
import { useTranslation } from "react-i18next"

export type GreetingKey = "morning" | "afternoon" | "evening" | "night"

export function getGreetingKey(hour: number): GreetingKey {
  if (hour >= 4 && hour < 12) return "morning"
  if (hour >= 12 && hour < 17) return "afternoon"
  if (hour >= 17 && hour <= 23) return "evening"
  return "night"
}

export function useGreeting(time: Date) {
  const { t } = useTranslation(["dashboard"])

  const hour = time.getHours()
  const greetingKey = useMemo(() => getGreetingKey(hour), [hour])
  const greeting = t(`dashboard:greeting.${greetingKey}`)

  return { greeting, greetingKey }
}
