export const CANONICAL_NOTIFICATION_TOPICS = [
  "news.published",
  "schedule.changed",
  "events.published",
  "chat.message.created",
  "system.release",
] as const

export type NotificationTopic = (typeof CANONICAL_NOTIFICATION_TOPICS)[number]

const TOPIC_SET = new Set<string>(CANONICAL_NOTIFICATION_TOPICS)

const LEGACY_TOPIC_ALIASES: Readonly<Record<string, NotificationTopic>> = {
  news: "news.published",
  schedule: "schedule.changed",
  events: "events.published",
  chat: "chat.message.created",
  system: "system.release",
}

export const NOTIFICATION_TOPIC_LABEL_KEYS: Readonly<Record<NotificationTopic, string>> = {
  "news.published": "newsPublished",
  "schedule.changed": "scheduleChanged",
  "events.published": "eventsPublished",
  "chat.message.created": "chatMessageCreated",
  "system.release": "systemRelease",
}

export function normalizeNotificationTopic(value: unknown): NotificationTopic | null {
  if (typeof value !== "string") return null
  const normalized = value.trim().toLowerCase()
  if (!normalized) return null
  const migrated = LEGACY_TOPIC_ALIASES[normalized] ?? normalized
  return TOPIC_SET.has(migrated) ? (migrated as NotificationTopic) : null
}

export function normalizeNotificationTopics(values: unknown): NotificationTopic[] {
  if (!Array.isArray(values)) return []
  const result: NotificationTopic[] = []
  const seen = new Set<NotificationTopic>()
  for (const value of values) {
    const topic = normalizeNotificationTopic(value)
    if (topic && !seen.has(topic)) {
      seen.add(topic)
      result.push(topic)
    }
  }
  return result
}

export function resolveNotificationDeepLink(value: unknown, origin: string): string {
  const fallback = new URL("/", origin).toString()
  return resolveOptionalSameOriginUrl(value, origin) ?? fallback
}

export function resolveOptionalSameOriginUrl(value: unknown, origin: string): string | null {
  if (typeof value !== "string" || !value.trim()) return null
  try {
    const resolved = new URL(value, origin)
    if (
      resolved.origin !== new URL(origin).origin ||
      !["http:", "https:"].includes(resolved.protocol)
    ) {
      return null
    }
    return resolved.toString()
  } catch {
    return null
  }
}

export function resolveNotificationAppPath(value: unknown): string | undefined {
  const sentinelOrigin = "https://notification.invalid"
  const resolved = resolveOptionalSameOriginUrl(value, sentinelOrigin)
  if (!resolved) return undefined
  const parsed = new URL(resolved)
  return `${parsed.pathname}${parsed.search}${parsed.hash}`
}
