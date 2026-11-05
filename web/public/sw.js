// RoadWatch BD service worker: makes the site installable and fast to reopen.
// Caches only the app shell. Never caches /api/ (videos, results, accounts are always fetched live).
const VERSION = "rw-v1";
const SHELL = ["/", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
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

  // Pages: always try the network (fresh content, current login state); fall back when offline.
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).catch(() =>
        caches.match(req).then((hit) => hit || caches.match("/")).then(
          (hit) => hit || new Response(OFFLINE, { headers: { "Content-Type": "text/html; charset=utf-8" } }),
        ),
      ),
    );
  }
});
