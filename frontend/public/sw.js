// Service worker push notification handlers.
// The Vite PWA plugin generates the actual implementation at build time.

self.addEventListener('push', (event) => {
  event.waitUntil(
    (async () => {
      let payload;
      try {
        payload = event.data?.json();
      } catch (error) {
        console.error('Failed to parse push event data', error);
        return;
      }

      const notification = payload?.notification;
      if (!notification) {
        return;
      }

      const {
        title = '',
        body,
        icon,
        badge,
        tag,
        timestamp,
        requireInteraction,
        data: notificationData = {},
      } = notification;

      const options = {
        body,
        icon,
        badge,
        tag,
        timestamp,
        requireInteraction,
        data: {
          url: notificationData?.url,
          entityId: notificationData?.entityId,
        },
      };

      await self.registration.showNotification(title, options);
    })()
  );
});

self.addEventListener('notificationclick', (event) => {
  event.waitUntil(
    (async () => {
      event.notification.close();
      const notificationData = event.notification.data || {};
      const targetUrl = notificationData.url;

      const windowClients = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      });

      for (const client of windowClients) {
        if (client.url === targetUrl && 'focus' in client) {
          await client.focus();
          return;
        }
      }

      if (targetUrl) {
        await self.clients.openWindow(targetUrl);
      } else if (windowClients.length > 0 && 'focus' in windowClients[0]) {
        await windowClients[0].focus();
      }
    })()
  );
});

self.addEventListener('notificationclose', (event) => {
  event.waitUntil(Promise.resolve());
});
