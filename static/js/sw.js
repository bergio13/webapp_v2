/**
 * Kineto PWA Service Worker
 * Version: 1.0.0
 * 
 * Provides offline resilience, static asset caching, and fast navigation.
 */

const CACHE_NAME_STATIC = "kineto-static-v1.0.0";
const CACHE_NAME_RUNTIME = "kineto-runtime-v1.0.0";
const CACHE_NAME_IMAGES = "kineto-images-v1.0.0";

const PRECACHE_ASSETS = [
  "/",
  "/offline",
  "/manifest.json",
  "/static/css/style.css?v=5.3",
  "/static/css/partials/_tokens.css",
  "/static/css/partials/_base.css",
  "/static/css/partials/_nav.css",
  "/static/css/partials/_components.css",
  "/static/css/partials/_pages.css",
  "/static/css/partials/_themes.css",
  "/static/icons/icon-192x192.png",
  "/static/icons/icon-512x512.png",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/favicon-32x32.png",
  "/static/icons/favicon-16x16.png",
  "/static/js/movie_drawer.js",
  "/static/icona1.png?v=2"
];

// Install Event: Precache core shell assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME_STATIC).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn("[Kineto SW] Precache warning:", err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate Event: Clean up stale cache versions
self.addEventListener("activate", (event) => {
  const currentCaches = [CACHE_NAME_STATIC, CACHE_NAME_RUNTIME, CACHE_NAME_IMAGES];
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (!currentCaches.includes(cacheName)) {
            console.log("[Kineto SW] Removing outdated cache:", cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Event: Intelligent routing
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests and browser extensions
  if (request.method !== "GET" || !url.protocol.startsWith("http")) {
    return;
  }

  // 1. Navigation (HTML Pages) -> Network First with Offline Fallback
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const responseToCache = response.clone();
            caches.open(CACHE_NAME_RUNTIME).then((cache) => {
              cache.put(request, responseToCache);
            });
          }
          return response;
        })
        .catch(async () => {
          const cachedResponse = await caches.match(request);
          if (cachedResponse) {
            return cachedResponse;
          }
          const offlinePage = await caches.match("/offline");
          return offlinePage || new Response("Offline - Signal Lost", {
            status: 503,
            headers: { "Content-Type": "text/html" }
          });
        })
    );
    return;
  }

  // 2. TMDB Images / Poster Assets -> Stale While Revalidate
  if (url.hostname.includes("tmdb.org") || url.pathname.match(/\.(png|jpg|jpeg|webp|gif|svg)$/)) {
    event.respondWith(
      caches.open(CACHE_NAME_IMAGES).then(async (cache) => {
        const cachedResponse = await cache.match(request);
        const networkFetchPromise = fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            cache.put(request, networkResponse.clone());
          }
          return networkResponse;
        }).catch(() => null);

        return cachedResponse || networkFetchPromise;
      })
    );
    return;
  }

  // 3. Static Assets (CSS, JS, Fonts) -> Stale While Revalidate / Cache First
  if (
    url.origin === location.origin &&
    (url.pathname.startsWith("/static/") || url.hostname.includes("googleapis.com") || url.hostname.includes("gstatic.com") || url.hostname.includes("cdnjs.cloudflare.com"))
  ) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        const fetchPromise = fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME_STATIC).then((cache) => {
              cache.put(request, networkResponse.clone());
            });
          }
          return networkResponse;
        }).catch(() => null);

        return cachedResponse || fetchPromise;
      })
    );
    return;
  }

  // 4. Default -> Network with Cache Fallback
  event.respondWith(
    fetch(request)
      .then((response) => response)
      .catch(() => caches.match(request))
  );
});
