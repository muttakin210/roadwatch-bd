// RoadWatch BD service worker: makes the site installable and fast to reopen.
// Caches only the app shell. Never caches /api/ (videos, results, accounts are always fetched live).
// The road map and traffic rules work offline: their pages and the place-name list are kept, and the map pack
// the user chose to save lives in its own cache ("rw-offline-map", written by the map page) that updates keep.
const VERSION = "rw-v2";
const KEEP = ["rw-offline-map"];
const SHELL = ["/", "/map", "/rules", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"];
// public pages with no personal data in their HTML (login state is fetched separately), safe to keep offline
const OFFLINE_PAGES = ["/", "/map", "/rules"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && !KEEP.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

const OFFLINE = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RoadWatch BD</title><body style="font-family:system-ui,sans-serif;padding:2rem;color:#18181b;background:#f6f7f6">
<h1 style="color:#0b6e4f">RoadWatch BD</h1><p>You are offline. Connect to the internet and try again.</p>
<p lang="bn">আপনি অফলাইনে আছেন। ইন্টারনেটে যুক্ত হয়ে আবার চেষ্টা করুন।</p></body>`;

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  // Hashed build files and icons never change: cache first.
  if (url.pathname.startsWith("/_next/static/") || /\.(png|ico|woff2?)$/.test(url.pathname)) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return res;
      })),
    );
    return;
  }

  // The place-name list (for offline search): network first so it stays current, the copy when offline.
  if (url.pathname.startsWith("/geo/")) {
    e.respondWith(
      fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || Response.error())),
    );
    return;
  }

  // Pages: always try the network (fresh content, current login state); fall back when offline.
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).then((res) => {
        if (res.ok && OFFLINE_PAGES.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(url.pathname, copy));
        }
        return res;
      }).catch(() =>
        caches.match(url.pathname).then((hit) => hit || caches.match("/")).then(
          (hit) => hit || new Response(OFFLINE, { headers: { "Content-Type": "text/html; charset=utf-8" } }),
        ),
      ),
    );
  }
});
