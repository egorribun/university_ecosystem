import i18n from "@/i18n/config"

export type NotificationData = {
  url?: string
  actionUrls?: Record<string, string>
  reportUrl?: string
  reportPayload?: unknown
  // Allow arbitrary additional payload data from the server.
  [key: string]: unknown
}

export type NotificationActionPayload = {
  action: string
  title: string
  icon?: string
  url?: string
}

export type NotificationActionOption = {
  action: string
  title: string
  icon?: string
}

export type PushPayload = {
  title?: string
  body?: string
  icon?: string
  badge?: string
  tag?: string
  url?: string
  data?: Record<string, unknown>
  renotify?: boolean
  requireInteraction?: boolean
  silent?: boolean
  timestamp?: number
  vibrate?: number[]
  actions?: NotificationActionPayload[]
}

export const DEFAULT_ICON = "/maskable-icon-192.png"

const translateNotification = (key: string, options?: Record<string, unknown>) =>
  i18n.t(`notifications:${key}`, options)

export const getDefaultNotificationTitle = () => translateNotification("defaultTitle")

export const getDefaultNotificationBody = () => translateNotification("defaultBody")

export type ExtendedNotificationOptions = NotificationOptions & {
  renotify?: boolean
  timestamp?: number
  vibrate?: number[]
  actions?: NotificationActionOption[]
}

export function parsePushEventData(
  data: { json: () => unknown; text: () => string } | null | undefined
): PushPayload {
  if (!data) {
    return {}
  }

  try {
    const parsed = data.json()
    if (parsed && typeof parsed === "object") {
      return parsed as PushPayload
    }
    return {}
  } catch (error) {
    try {
      const text = data.text()
      if (!text) return {}
      return { body: text }
    } catch {
      return {}
    }
  }
}

export function buildNotificationDetails(payload: PushPayload): {
  title: string
  options: ExtendedNotificationOptions
  data: NotificationData
  payloadType?: string
} {
  const rawData =
    payload.data && typeof payload.data === "object"
      ? (payload.data as Record<string, unknown>)
      : undefined

  const rawTitle = typeof payload.title === "string" ? payload.title.trim() : ""
  const title = rawTitle || getDefaultNotificationTitle()

  const data: NotificationData = {
    url: payload.url || "/",
    ...(rawData ?? {}),
  }

  const rawBody = typeof payload.body === "string" ? payload.body.trim() : ""
  const body = rawBody || getDefaultNotificationBody()

  const options: ExtendedNotificationOptions = {
    body,
    icon: payload.icon || DEFAULT_ICON,
    badge: payload.badge || payload.icon || DEFAULT_ICON,
    tag: payload.tag,
    data,
    requireInteraction: payload.requireInteraction,
    silent: payload.silent,
  }

  if (payload.renotify !== undefined) {
    options.renotify = payload.renotify
  }

  if (payload.timestamp !== undefined) {
    options.timestamp = payload.timestamp
  }

  if (payload.vibrate) {
    options.vibrate = payload.vibrate
  }

  if (payload.actions?.length) {
    const actionUrls: Record<string, string> = {}
    const validActions: NotificationActionOption[] = []
    for (const action of payload.actions) {
      if (!action || typeof action !== "object") continue
      const key = typeof action.action === "string" ? action.action.trim() : ""
      const actionTitle = typeof action.title === "string" ? action.title.trim() : ""
      if (!key || !actionTitle) continue
      const entry: NotificationActionOption = { action: key, title: actionTitle }
      if (action.icon && typeof action.icon === "string") {
        entry.icon = action.icon
      }
      validActions.push(entry)
      if (action.url && typeof action.url === "string" && action.url.trim()) {
        actionUrls[key] = action.url
      }
    }
    if (validActions.length) {
      options.actions = validActions
      if (Object.keys(actionUrls).length) {
        data.actionUrls = actionUrls
      }
    }
  }

  const payloadType = (() => {
    const rawType = rawData && typeof rawData.type === "string" ? rawData.type.trim() : undefined
    return rawType || undefined
  })()

  return { title, options, data, payloadType }
}
