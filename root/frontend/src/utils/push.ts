import api from "@/api/axios";
import { registerServiceWorker } from "@/push/register-sw";

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

export async function ensurePushSubscription(vapidPublicKey: string) {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || typeof Notification === "undefined") return null;
  const reg = await registerServiceWorker();
  if (!reg) return null;

  if (Notification.permission === "denied") return null;
  if (Notification.permission === "default") {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return null;
  }

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    try {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey.trim())
      });
    } catch {
      return null;
    }
  }

  const info = sub.toJSON() as any;
  await api.post("/push/subscribe", {
    endpoint: info.endpoint,
    keys: { p256dh: info.keys?.p256dh, auth: info.keys?.auth }
  });

  return sub;
}

export async function unsubscribePush() {
  if (!("serviceWorker" in navigator)) return false;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return true;
  const info = sub.toJSON() as any;
  try { await api.post("/push/unsubscribe", { endpoint: info.endpoint, keys: info.keys || {} }); } catch {}
  return sub.unsubscribe();
}