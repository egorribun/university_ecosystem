import api from "@/api/axios"
import { registerServiceWorker } from "./register-sw"

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/")
  const rawData = atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i)
  return outputArray
}

async function sendSubToServer(sub: PushSubscription) {
  const data = sub.toJSON() as any
  await api.post("/push/subscribe", { endpoint: data.endpoint, keys: data.keys })
}

export async function ensurePushSubscription(vapidPublicKey: string) {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null
  const reg = await registerServiceWorker()
  if (!reg) return null
  if (Notification.permission !== "granted") {
    const perm = await Notification.requestPermission()
    if (perm !== "granted") return null
  }
  const storedKey = localStorage.getItem("vapid:pub") || ""
  let sub = await reg.pushManager.getSubscription()
  if (sub && storedKey && storedKey !== vapidPublicKey) {
    try { await sub.unsubscribe() } catch {}
    sub = null
  }
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
    })
    localStorage.setItem("vapid:pub", vapidPublicKey)
    await sendSubToServer(sub)
  } else {
    if (!storedKey) localStorage.setItem("vapid:pub", vapidPublicKey)
    await sendSubToServer(sub)
  }
  return sub
}

export async function unsubscribePush() {
  if (!("serviceWorker" in navigator)) return false
  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.getSubscription()
  if (!sub) return true
  const data = sub.toJSON() as any
  try { await api.post("/push/unsubscribe", { endpoint: data.endpoint, keys: data.keys }) } catch {}
  const ok = await sub.unsubscribe()
  try { localStorage.removeItem("vapid:pub") } catch {}
  return ok
}