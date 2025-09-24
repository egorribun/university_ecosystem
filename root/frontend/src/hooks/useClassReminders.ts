import { useEffect, useRef, useCallback } from "react"

export type RemindItem = {
  id: string | number
  title: string
  when: string
  url?: string
  minutesBefore?: number
  tag?: string
}

type Timer = { id: number; at: number; key: string }

function scheduleAt(ts: number, cb: () => void) {
  const delay = Math.max(0, ts - Date.now())
  return window.setTimeout(cb, delay)
}

function openUrl(u: string) {
  try {
    const absolute = new URL(u, location.origin).href
    window.open(absolute, "_blank")
  } catch {}
}

export function useClassReminders(items: RemindItem[] | undefined, opts?: { defaultMinutesBefore?: number }) {
  const timers = useRef<Timer[]>([])
  const defMins = Math.max(0, opts?.defaultMinutesBefore ?? 10)

  const clearAll = useCallback(() => {
    for (const t of timers.current) clearTimeout(t.id)
    timers.current = []
  }, [])

  const requestPermission = useCallback(async () => {
    if (!("Notification" in window)) return "unsupported"
    if (Notification.permission === "denied") return "denied"
    if (Notification.permission === "granted") return "granted"
    const res = await Notification.requestPermission()
    return res
  }, [])

  useEffect(() => {
    clearAll()
    if (!items || !items.length) return

    items.forEach(ev => {
      const mins = typeof ev.minutesBefore === "number" ? Math.max(0, ev.minutesBefore) : defMins
      const at = new Date(ev.when).getTime() - mins * 60000
      if (!Number.isFinite(at) || at <= Date.now()) return

      const key = String(ev.id) + ":" + at
      const cb = async () => {
        if (!("Notification" in window) || Notification.permission !== "granted") return
        const data = { url: ev.url || "/", id: ev.id, type: "reminder" }
        const title = ev.title
        const body = `Через ${mins} мин.`
        const tag = ev.tag || `reminder:${ev.id}`
        try {
          const reg = await navigator.serviceWorker?.getRegistration()
          if (reg && "showNotification" in reg) {
            const options: NotificationOptions & { renotify?: boolean } = {
              body,
              tag,
              data,
              icon: "/icons/icon-192.png",
              badge: "/icons/badge-72.png",
              renotify: true,
            }
            await reg.showNotification(title, options)
          } else {
            const n = new Notification(title, { body, tag, data })
            n.onclick = () => openUrl(data.url)
          }
        } catch {}
      }

      const id = scheduleAt(at, cb)
      timers.current.push({ id, at, key })
    })

    return clearAll
  }, [items, defMins, clearAll])

  return { requestPermission, clear: clearAll }
}
