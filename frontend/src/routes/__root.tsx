import {
  createRootRouteWithContext,
  HeadContent,
  Outlet,
  Scripts,
  useRouteContext,
} from "@tanstack/react-router"
import type { RouterContext } from "@/router"
import MainLayout from "@/components/layout/MainLayout"
import InstallPrompt from "@/components/pwa/InstallPrompt"
import LivePushToasts from "@/components/feedback/LivePushToasts"
import OfflineIndicator from "@/components/feedback/OfflineIndicator"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"
import { SearchDialog } from "@/components/search/SearchDialog"
import { AppProviders } from "@/AppProviders"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { QueryClientProvider } from "@tanstack/react-query"
// W149 SW2 — PersistQueryClientProvider + singleton queryClient + idbPersister
// moved here from main.tsx so the client RootComponent provider tree matches
// SsrRoot's structurally for hydrateRoot reconciliation. SsrRoot (line 305)
// continues to use per-request QueryClient from routerContext — IndexedDB is
// browser-only, so server CANNOT use PersistQueryClientProvider regardless.
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client"
import { queryClient, idbPersister } from "@/app/queryClient"

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

  // 2. Language Detection — MUST match SSR's extractLangFromRequest (ssrTheme.ts:resolveLang)
  // which reads only the "ue:language" cookie (or localStorage mirror) and defaults to "ru".
  // W150 polish-followup: REMOVED navigator.language fallback. SSR cannot read
  // navigator.language (server-side), so if client did and switched to "en" while
  // SSR stayed "ru", every i18n string mismatched -> React error #418 hydration
  // failure -> renderer hang. Per W127 SW4 design: cookie-mirror + localStorage
  // are the canonical sources; explicit language toggle in UI is the only way
  // to switch from default Russian.
  var lang = "ru"
  try {
    var storedLang = localStorage.getItem("ue:language")
    if (storedLang === "en" || storedLang === "ru") {
      lang = storedLang
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
}

/* LHCI_CSS_PLACEHOLDER */`

export const Route = createRootRouteWithContext<RouterContext>()({
  // W150 polish-followup — root flipped to `ssr: false` to immediately resolve
  // React error #418 hydration mismatch that blocks ALL routes (including /login
  // with `_public.tsx ssr:false`) on local Docker stack. Hydration mismatch root
  // cause not isolatable from production-minified bundle without source maps;
  // suspected candidates: useId() reconciliation, MainLayout SSR-vs-client
  // provider tree subtle differences, ParticleAuthBackground canvas ref timing.
  //
  // SSR opt-in is W128-W133 work. With `ssr: false` here, EVERY route renders
  // client-side regardless of per-route `ssr: true` annotations (TanStack Start
  // inheritance: child can only be MORE restrictive). The SSR LCP win for
  // /dashboard + /events + /news + /schedule + /profile + /settings + /events.$id
  // + /news.$id (W128-W133 enabled) is bypassed in this dev config. Production
  // deploys should re-enable `ssr: true` here once the hydration mismatch is
  // root-caused via dev build with source maps (W151+ structural investigation).
  ssr: false,
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
  // Wave 127 SW5 — read per-request theme + language cookies via globalThis
  // getters populated by server.ts (W127 SW4). Renders `<html lang={lang}
  // class={isDark ? "dark" : undefined}>` server-side so cookie-bearing
  // returning users see SSR-rendered HTML matching their pre-paint state —
  // no more hardcoded `<html lang="ru">` mismatch on dark-mode + English.
  //
  // On the client, RootShell only runs during SSR — client hydration reuses
  // the server-emitted `<html>` and never re-executes RootShell, so the
  // getters being undefined client-side is irrelevant.
  //
  // `suppressHydrationWarning` on `<html>` is defense-in-depth for edge
  // cases the server cannot detect:
  //   - New users with no cookie but system-pref dark: THEME_INIT_SCRIPT
  //     mutates `<html class="dark">` after parse, before React hydrates
  //   - Browsers that block cookies but allow localStorage
  // React 19 skips the hydration comparison on `<html>` only (not children).
  //
  // `<HeadContent />` injects all `head:()` registrations from this
  // route + any nested routes (via TanStack Router's head merging).
  // `<Scripts />` injects the bundle entry script tags + modulepreload
  // links produced by Vite + tanstackStart.
  const ssrTheme = typeof globalThis !== "undefined" ? globalThis.__ssrThemeGetter__?.() : undefined
  const ssrLang = typeof globalThis !== "undefined" ? globalThis.__ssrLangGetter__?.() : undefined
  const isDark = ssrTheme === "dark"
  const lang = ssrLang ?? "ru"

  return (
    <html lang={lang} className={isDark ? "dark" : undefined} suppressHydrationWarning>
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
  // Wave 127 SW1 — provider hoisting. Both SSR and client paths now mount
  // the full provider chain via __root.tsx instead of via main.tsx → App.tsx
  // → AppProviders. AppShellProvider, AuthProvider, LanguageProvider,
  // LazyMotion, MotionConfig, LiveRegionProvider, WebSocketProvider,
  // MessengerProvider, ErrorBoundary, GlobalHapticsListener, ThemeProvider
  // are all available at server render time.
  //
  // Wave 128 SW3 — both branches now mount MainLayout so /dashboard SSR
  // renders the same tree as client hydration. Pre-W128, SSR branch was
  // a minimal-shell pattern (no MainLayout) that worked because no
  // authenticated route opted into ssr:true. With W128 SW2 flipping
  // _auth.tsx to ssr:true and SW3 adding ssr:true on /dashboard, server
  // emits HTML with Navbar + Footer + content; client hydrates the same.
  // AuthProvider's W128 SW1 ssrAuthHint bridge populates a role-only
  // stub User on SSR so Navbar renders without crashing on useAuth()
  // returning null.
  if (import.meta.env.SSR) {
    return <SsrRoot />
  }
  // W149 SW2 — PersistQueryClientProvider wraps RootComponent so the client
  // tree matches SsrRoot's structure (QueryClientProvider wraps everything)
  // for hydrateRoot reconciliation. SsrRoot uses per-request QueryClient
  // from routerContext (W128 SW3); RootComponent uses the singleton from
  // @/app/queryClient + idbPersister which hydrates the cache from
  // IndexedDB post-mount asynchronously. The provider itself emits no DOM
  // so the SSR HTML doesn't carry it — hydration compares only the
  // rendered children, which ARE identical between SsrRoot + RootComponent.
  return (
    <PersistQueryClientProvider client={queryClient} persistOptions={{ persister: idbPersister }}>
      <ThemeProvider>
        <AppProviders>
          <MainLayout>
            <PageErrorBoundary>
              <Outlet />
            </PageErrorBoundary>

            <SearchDialog />
            <LivePushToasts />
            <OfflineIndicator />
            <InstallPrompt />
          </MainLayout>
        </AppProviders>
      </ThemeProvider>
    </PersistQueryClientProvider>
  )
}

function SsrRoot() {
  // Wave 128 SW3 — SSR-only mount tree. Reads RouterContext for the
  // per-request `queryClient` instance (created by router.ts:createAppRouter
  // for THIS request) and wraps with QueryClientProvider so that:
  //   1. AuthProvider's useProfileSync `useQueryClient()` resolves to the
  //      same per-request instance the loader.ensureQueryData populates
  //      (W128 SW3 + future W129+ loaders). Pre-W128 SW3, SSR wrapped the
  //      `@/app/queryClient` singleton — separate cache from
  //      routerContext.queryClient → loader-prefetched data invisible to
  //      AuthProvider/components at render time.
  //   2. Dashboard's queries (useDashboardEvents/Stories/Schedule) hit
  //      the same cache the loader pre-populated — no refetch needed
  //      server-side (suspense / placeholderData paths use cached data).
  //
  // Mirrors the W127 SW1 client branch tree (ThemeProvider → AppProviders →
  // MainLayout → PageErrorBoundary → Outlet) plus the post-Outlet siblings
  // (SearchDialog, LivePushToasts, OfflineIndicator, InstallPrompt) so
  // hydration trees match exactly. Mid-tree mismatch (server emits Outlet
  // without MainLayout, client wraps with MainLayout) would cause full
  // subtree re-render per CLAUDE.md gotcha "React 19 hydration mismatch".
  const { queryClient } = useRouteContext({ from: "__root__" })
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AppProviders>
          <MainLayout>
            <PageErrorBoundary>
              <Outlet />
            </PageErrorBoundary>

            <SearchDialog />
            <LivePushToasts />
            <OfflineIndicator />
            <InstallPrompt />
          </MainLayout>
        </AppProviders>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
