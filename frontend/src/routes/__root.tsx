import {
  createRootRouteWithContext,
  HeadContent,
  Outlet,
  Scripts,
} from "@tanstack/react-router"
import type { RouterContext } from "@/router"
import MainLayout from "@/components/layout/MainLayout"
import InstallPrompt from "@/components/pwa/InstallPrompt"
import LivePushToasts from "@/components/feedback/LivePushToasts"
import OfflineIndicator from "@/components/feedback/OfflineIndicator"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"
import { SearchDialog } from "@/components/search/SearchDialog"

// Wave 125 Phase 2 — pre-paint inline scripts. These run in the document
// scaffold BEFORE any React code or bundle JS evaluates, so they avoid
// FOUC: theme is set as `<html class="dark">` synchronously, language
// is read from localStorage and applied to `<html lang>` + a global
// hint, and the static-shell-i18n module applies meta translations
// without waiting for the React tree.
//
// Pre-W125 these lived inline in `frontend/index.html`. With TanStack
// Start v1 SPA mode the React tree generates the HTML scaffold via
// `shellComponent` (see RootShell below), so we move the bodies here
// as `dangerouslySetInnerHTML` strings on `head: { scripts }` route
// metadata. Browser executes them at parse time exactly like before.
const THEME_INIT_SCRIPT = `;(function () {
  // 1. Theme Initialization
  var s = null
  try { s = localStorage.getItem("ue-mode") } catch (e) {}
  var m = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
  var dark = s ? s === "dark" : m
  var html = document.documentElement
  if (dark) html.classList.add("dark")

  // 2. Language Detection
  var lang = "ru"
  try {
    var storedLang = localStorage.getItem("ue:language")
    if (storedLang === "en" || storedLang === "ru") {
      lang = storedLang
    } else {
      var browser = (navigator.language || "").toLowerCase()
      if (browser.indexOf("en") === 0) lang = "en"
    }
  } catch (error) {}
  html.setAttribute("lang", lang)
  window.__UE_SELECTED_LANG__ = lang

  // 3. Static Shell Hooks
  import("/static-shell-i18n.js")
    .then(function (mod) {
      mod.applyDocumentLanguage(document, lang)
      mod.applyMetaTranslations(document, lang)
    })
    .catch(function () {})
})()`

// Inline CSS that ran in <head> via index.html — preserved verbatim so
// the initial paint background + visibility behavior matches pre-W125.
const INITIAL_PAINT_CSS = `:root {
  --initial-bg: #f8fafc;
  --z-debug: 999999;
}

.dark {
  --initial-bg: #020617;
}

html {
  background: var(--initial-bg, #060b14) !important;
  background-color: var(--initial-bg, #060b14) !important;
  min-height: 100vh;
  min-height: 100svh;
  min-height: 100dvh;
  height: auto;
  scrollbar-gutter: stable;
  visibility: visible;
  overflow-y: auto;
}

body {
  background: var(--initial-bg, #060b14) !important;
  background-color: var(--initial-bg, #060b14) !important;
  margin: 0;
  overscroll-behavior-y: none;
  min-height: 100vh;
  min-height: 100svh;
  min-height: 100dvh;
  height: auto;
  opacity: 1;
  visibility: visible;
}

#root {
  background: var(--initial-bg, #060b14) !important;
  background-color: var(--initial-bg, #060b14) !important;
  min-height: 100dvh;
  height: auto;
  opacity: 0;
  transition: opacity 0.15s ease-in;
}

#root.ready,
.lhci-mode #root {
  opacity: 1;
}

html::before,
html::after,
body::before,
body::after {
  display: none !important;
}`

export const Route = createRootRouteWithContext<RouterContext>()({
  // Wave 126 polish — root opts INTO SSR so per-route SSR enablement
  // can override more restrictively (per TanStack Start v1 docs:
  // "Child routes inherit the Selective SSR configuration from their
  // parent routes. However, an inherited SSR value can only be made
  // MORE restrictive."). With `ssr: true` here, child layouts under
  // `_auth.tsx` + `_admin.tsx` set `ssr: false` to preserve their
  // client-only behavior (provider chain not yet hoisted for SSR);
  // routes under `_public.tsx` inherit `ssr: true` which means
  // `/login` can render server-side via `RootComponent`'s
  // `import.meta.env.SSR` branch (returns minimal `<Outlet />` on
  // SSR — Phase 5 will hoist providers so MainLayout becomes
  // SSR-safe and full route SSR delivers the LCP win).
  ssr: true,
  // Wave 125 Phase 2 — head() registers metadata that TanStack Router's
  // `<HeadContent />` injects into `<head>` during SSR + client. Mirrors
  // the meta + link tags that lived in `frontend/index.html` pre-W125.
  // The picsum preconnect (W117 SW5) stays here so cold-cache 3G LCP
  // savings are preserved. Critical font preload (W124 SW2) still ships
  // via the `withFontPreload()` Vite plugin which transforms the HTML
  // post-build by scanning the bundle for font hashes.
  head: () => ({
    meta: [
      { charSet: "UTF-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
      { name: "color-scheme", content: "light dark" },
      { name: "theme-color", media: "(prefers-color-scheme: light)", content: "#f8fafc" },
      { name: "theme-color", media: "(prefers-color-scheme: dark)", content: "#020617" },
      {
        name: "description",
        content:
          "Всё необходимое — профиль, расписание, новости и события кампуса — в одном месте.",
      },
      { property: "og:type", content: "website" },
      { property: "og:title", content: "Экосистема ГУУ" },
      {
        property: "og:description",
        content: "Личный кабинет: профиль, расписание, новости и события кампуса.",
      },
      { property: "og:url", content: "/" },
      { property: "og:image", content: "/og-image.png" },
      { property: "og:locale", content: "ru_RU" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:title", content: "Экосистема ГУУ" },
      {
        name: "twitter:description",
        content: "Личный кабинет: профиль, расписание, новости и события кампуса.",
      },
      { name: "twitter:image", content: "/og-image.png" },
      { name: "google-site-verification", content: "not-applicable" },
      { name: "mobile-web-app-capable", content: "yes" },
      { name: "apple-mobile-web-app-status-bar-style", content: "black-translucent" },
      { title: "Экосистема ГУУ" },
    ],
    links: [
      { rel: "icon", href: "/favicon.ico", sizes: "any" },
      { rel: "icon", type: "image/png", sizes: "32x32", href: "/favicon-32x32.png" },
      { rel: "icon", type: "image/png", sizes: "16x16", href: "/favicon-16x16.png" },
      { rel: "apple-touch-icon", href: "/apple-touch-icon.png" },
      {
        rel: "manifest",
        href: "/manifest.webmanifest",
        crossOrigin: "use-credentials",
      },
      // Wave 117 SW5 — preconnect + dns-prefetch to picsum.photos
      // (placeholder image CDN used by NewsCard + EventCard heroes).
      // Saves ~150-300ms on mobile 3G LCP.
      { rel: "preconnect", href: "https://picsum.photos", crossOrigin: "" },
      { rel: "dns-prefetch", href: "https://picsum.photos" },
    ],
    scripts: [
      // Pre-paint theme + language detection — runs synchronously
      // before bundle parses so users never see light-flash before
      // dark theme kicks in (or vice versa).
      { children: THEME_INIT_SCRIPT },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
})

function RootShell({ children }: { children: React.ReactNode }) {
  // Wave 125 Phase 2 — minimal SSR-rendered HTML scaffold.
  //
  // With `defaultSsr: false` on the router (see src/router.ts), route
  // `component`s do NOT execute during SSR — only this `shellComponent`
  // does. The `children` prop is the empty `<Outlet />` placeholder
  // during SSR and the full client tree post-hydration. The result:
  // shell HTML = `<html><head>(meta+title+scripts)</head><body><div
  // id="root"></div><Scripts/></body></html>` with no provider
  // dependencies executed server-side, so no AppShellProvider /
  // AuthProvider / etc. errors during shell prerender.
  //
  // `<HeadContent />` injects all `head:()` registrations from this
  // route + any nested routes (via TanStack Router's head merging).
  // `<Scripts />` injects the bundle entry script tags + modulepreload
  // links produced by Vite + tanstackStart.
  return (
    <html lang="ru">
      <head>
        <HeadContent />
        <style dangerouslySetInnerHTML={{ __html: INITIAL_PAINT_CSS }} />
      </head>
      <body>
        <div
          id="lhci-marker"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "white",
            color: "black",
            display: "none",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "1.5rem",
            zIndex: "var(--z-debug)" as unknown as number,
          }}
        >
          LHCI RENDER START
        </div>
        <div id="root">{children}</div>
        <noscript>
          <style>{`#root { display: block !important; }`}</style>
        </noscript>
        <Scripts />
      </body>
    </html>
  )
}

function RootComponent() {
  // Wave 126 polish — SSR branch returns minimal `<Outlet />` so child
  // routes that opt into SSR (e.g. `/login` under `_public.tsx`) have
  // a place to mount their server-rendered content. MainLayout (which
  // uses `useAppShell` from `AppShellProvider`) is client-only because
  // its provider chain is mounted via `main.tsx` → `<App>` →
  // `<AppProviders>` (not yet hoisted above `<StartClient />`).
  // Hydration: server emits `<div id="root"><Outlet content/></div>`,
  // client mounts `<div id="root"><MainLayout>...<Outlet content/>...</MainLayout></div>`.
  // React 19 falls back to client render at the wrapper-mismatch
  // boundary; SSR'd content paints first (LCP win for /login), then
  // client takes over with full chrome. Phase 5 will hoist providers
  // above `<StartClient />` so MainLayout becomes SSR-safe and the
  // hydration mismatch goes away.
  //
  // `_auth.tsx` + `_admin.tsx` set `ssr: false` to preserve client-only
  // behavior on authenticated routes (more restrictive override of
  // root's `ssr: true` — TanStack Start v1 SSR inheritance contract).
  if (import.meta.env.SSR) {
    return (
      <PageErrorBoundary>
        <Outlet />
      </PageErrorBoundary>
    )
  }
  return (
    <MainLayout>
      <PageErrorBoundary>
        <Outlet />
      </PageErrorBoundary>

      <SearchDialog />
      <LivePushToasts />
      <OfflineIndicator />
      <InstallPrompt />
    </MainLayout>
  )
}
