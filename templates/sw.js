// static/sw.js
// Service Worker — gère les notifications push en arrière-plan

self.addEventListener("push", function(event) {
  if (!event.data) return;

  let data = {};
  try { data = event.data.json(); } catch(e) { data = { title: "KP Kids Studio", body: event.data.text() }; }

  const options = {
    body: data.body || "",
    icon: data.icon || "/static/img/logo.png",
    badge: "/static/img/badge.png",
    vibrate: [200, 100, 200],
    tag: "kp-notification",
    renotify: true,
    data: { url: data.url || "/" },
    actions: [
      { action: "open", title: "Open Dashboard" },
      { action: "dismiss", title: "Dismiss" },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(data.title || "KP Kids Studio", options)
  );
});

self.addEventListener("notificationclick", function(event) {
  event.notification.close();

  if (event.action === "dismiss") return;

  const url = event.notification.data?.url || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(function(clientList) {
      // Si le dashboard est déjà ouvert → focus
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          return client.focus();
        }
      }
      // Sinon ouvrir un nouvel onglet
      if (clients.openWindow) {
        return clients.openWindow(self.location.origin + url);
      }
    })
  );
});