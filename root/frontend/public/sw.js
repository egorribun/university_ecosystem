self.addEventListener("install", (event) => { self.skipWaiting?.() });
self.addEventListener("activate", (event) => { event.waitUntil(self.clients.claim()) });

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {} } catch {
    try { data = { title: "Уведомление", body: event.data ? event.data.text() : "" } } catch { data = { title: "Уведомление" } }
  }
  const idTag = data.id != null ? `app:id:${data.id}` : undefined;
  const typeTag = data.type ? `app:${data.type}` : undefined;
  const title = data.title || "Уведомление";
  const options = {
    body: data.body || "",
    tag: data.tag || idTag || typeTag,
    renotify: !!data.renotify,
    requireInteraction: !!data.requireInteraction,
    icon: data.icon || "/icons/icon-192.png",
    badge: data.badge || "/icons/badge-72.png",
    timestamp: data.timestamp || Date.now(),
    data: { url: data.url || data.click_action || "/", id: data.id ?? null, type: data.type ?? null, raw: data },
    actions: Array.isArray(data.actions) ? data.actions.slice(0, 2) : []
  };

  if (self.navigator && self.navigator.setAppBadge && typeof data.unreadCount === "number") {
    event.waitUntil((async () => {
      try { if (data.unreadCount > 0) await self.navigator.setAppBadge(data.unreadCount); else await self.navigator.clearAppBadge?.() } catch {}
    })());
  }

  event.waitUntil((async () => {
    await self.registration.showNotification(title, options);
    try {
      const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const c of clientList) c.postMessage({ type: "PUSH_NOTIFICATION", payload: { title, ...options } });
    } catch {}
  })());
});

self.addEventListener("notificationclick", (event) => {
  const n = event.notification;
  const action = event.action;
  const targetUrl = (n && n.data && (n.data.url || n.data.raw?.url)) || "/";
  n.close();

  event.waitUntil((async () => {
    const focusOrOpen = async (url) => {
      const absolute = new URL(url, self.location.origin).href;
      const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of all) {
        try {
          const href = new URL(client.url, self.location.origin).href;
          if (href.startsWith(self.location.origin)) {
            if ("navigate" in client) { await client.navigate(absolute) }
            if ("focus" in client) return client.focus();
          }
        } catch {}
      }
      return self.clients.openWindow(absolute);
    };

    if (action) {
      if (action === "open" || action === "view") return focusOrOpen(targetUrl);
      if (action === "mark_read") {
        try {
          const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
          for (const c of all) c.postMessage({ type: "NOTIFICATION_MARK_READ", id: n.data?.id });
        } catch {}
        return;
      }
      return focusOrOpen(targetUrl);
    } else {
      return focusOrOpen(targetUrl);
    }
  })());
});

self.addEventListener("notificationclose", (event) => {
  const n = event.notification;
  (async () => {
    try {
      const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const c of all) c.postMessage({ type: "NOTIFICATION_CLOSED", id: n?.data?.id ?? null });
    } catch {}
  })();
});

self.addEventListener("message", (event) => {
  const msg = event.data;
  if (msg && msg.type === "SKIP_WAITING" && self.skipWaiting) self.skipWaiting();
});