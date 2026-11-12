// Service worker for the web app at /learn: the app shell works offline, so lessons and quizzes the
// learner already synced (kept in IndexedDB by the app) open without a connection.
//
// Network first for the page, so a new build is picked up as soon as there is a connection; the
// built files have hashed names and are kept once fetched. API calls are never cached here: the
// app keeps what it needs itself.
const CACHE = "cbc-learn-v1";
const SHELL = ["/learn", "/assets/cbc_ai_tutor/learn/manifest.webmanifest", "/assets/cbc_ai_tutor/learn/logo.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate" && url.pathname.startsWith("/learn")) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put("/learn", copy));
          }
          return res;
        })
        .catch(() => caches.match("/learn").then((r) => r || Response.error()))
    );
    return;
  }

  if (url.pathname.startsWith("/assets/cbc_ai_tutor/learn/")) {
    e.respondWith(
      caches.match(req).then((hit) => {
        const fresh = fetch(req).then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        });
        return hit || fresh;
      })
    );
  }
});
