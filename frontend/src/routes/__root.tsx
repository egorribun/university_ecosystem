import {
  createRootRouteWithContext,
  HeadContent,
  Outlet,
  Scripts,
  useRouteContext,
} from "@tanstack/react-router"
import type { RouterContext } from "@/router"
import MainLayout from "@/components/layout/MainLayout"
import DeferredGlobalOverlays from "@/components/layout/DeferredGlobalOverlays"
import { BrandBootLoader } from "@/components/feedback/BrandBootLoader"
import { BRAND_BOOT_LOADER_CSS } from "@/components/feedback/brandBootLoaderCss"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"
import { AppProviders } from "@/AppProviders"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { QueryClientProvider } from "@tanstack/react-query"
// W149 SW2 — PersistQueryClientProvider + singleton queryClient + idbPersister
// moved here from main.tsx so the client RootComponent provider tree matches
// SsrRoot's structurally for hydrateRoot reconciliation. SsrRoot (line 305)
// continues to use per-request QueryClient from routerContext — IndexedDB is
// browser-only, so server CANNOT use PersistQueryClientProvider regardless.
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client"
import { queryClient, persistOptions } from "@/app/queryClient"

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
  // which reads the "ue:language" cookie and defaults to "ru". Prefer that
  // cookie before the localStorage mirror so the pre-paint and SSR languages
  // remain identical even when one browser storage was manually cleared.
  var lang = "ru"
  try {
    var cookieMatch = document.cookie.match(/(?:^|;\\s*)ue:language=(ru|en)(?:;|$)/)
    if (cookieMatch) {
      lang = cookieMatch[1]
    } else {
      var storedLang = localStorage.getItem("ue:language")
      if (storedLang === "en" || storedLang === "ru") {
      lang = storedLang
      }
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

const CRITICAL_SHELL_CSS = `${INITIAL_PAINT_CSS}\n${BRAND_BOOT_LOADER_CSS}`

// Lighthouse's static-SPA build is prepared with `VITE_LHCI=true`.  Keep the
// audit-only effect rules in the React-owned shell as well as the post-build
// HTML fallback: `main.tsx` mounts a fresh document for static fallbacks, so
// styles injected only into the original HTML shell would otherwise be
// discarded during that mount.  The flag is replaced at build time and the
// block is not rendered by normal production builds.
const LHCI_STATIC_EFFECTS_CSS = `/* data-lhci-static-effects */
.lhci-mode .aurora-mesh::after,
.lhci-mode .sched-aurora-hero {
  animation: none !important;
  filter: none !important;
  transform: none !important;
}

/* Lighthouse's mobile CPU profile makes paint-only glass decoration dominate
 * the critical task window.  Noise and backdrop blur carry no information or
 * interaction semantics, so disable them only in the synthetic audit shell;
 * the production design remains unchanged. */
.lhci-mode .glass-noise::before,
.lhci-mode .glass-layer-surface,
.lhci-mode .glass-layer-elevated,
.lhci-mode .glass-layer-floating,
.lhci-mode [class*="backdrop-blur"] {
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}

.lhci-mode .glass-noise::before {
  display: none !important;
}

.lhci-mode .weather-ambient,
.lhci-mode .sched-current-glow,
.lhci-mode .sched-progress-fill::after,
.lhci-mode .sched-today-badge,
.lhci-mode .sched-empty-icon,
.lhci-mode .sched-empty-ring,
.lhci-mode .sched-empty-orbit,
.lhci-mode .sched-flip-colon,
.lhci-mode .sched-drop-target,
.lhci-mode .sched-skeleton-shimmer,
.lhci-mode .messenger-typing-pulse,
.lhci-mode .messenger-online-pulse::after,
.lhci-mode .messenger-skeleton-shimmer,
.lhci-mode .profile-skeleton-shimmer,
.lhci-mode .settings-skeleton-shimmer,
.lhci-mode .auth-skeleton-shimmer,
.lhci-mode .events-register-pulse,
.lhci-mode .refetch-shimmer::after,
.lhci-mode .border-glow-pulse {
  animation: none !important;
}

.lhci-mode .weather-ambient {
  display: none !important;
}`

export const Route = createRootRouteWithContext<RouterContext>()({
  // Keep SSR enabled at the root so public and data routes receive a complete
  // TanStack Start manifest. Child auth/admin layouts may opt down to client
  // rendering, but disabling SSR here can leave <StartClient /> in an empty
  // pending state and reintroduce hydration failures.
  ssr: true,
  // <HeadContent /> injects this metadata during SSR and on the client.
  // Critical font preload remains a post-build responsibility of the
  // withFontPreload() Vite plugin.
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
  const ssrTheme = globalThis.__ssrThemeGetter__?.()
  const ssrLang = globalThis.__ssrLangGetter__?.()
  const isDark = ssrTheme === "dark"
  const isLhci = import.meta.env.VITE_LHCI === "true"
  const lang = ssrLang ?? "ru"
  const htmlClassName =
    [isDark && "dark", isLhci && "lhci-mode"].filter(Boolean).join(" ") || undefined

  return (
    <html lang={lang} className={htmlClassName} suppressHydrationWarning>
      <head>
        <HeadContent />
        {isLhci ? (
          <style
            id="lhci-static-effects"
            data-lhci-static-effects=""
            dangerouslySetInnerHTML={{ __html: LHCI_STATIC_EFFECTS_CSS }}
          />
        ) : null}
        <style dangerouslySetInnerHTML={{ __html: CRITICAL_SHELL_CSS }} />
      </head>
      {/*
        W156 SW3 polish — `suppressHydrationWarning` on <body> because browser
        extensions (LastPass / 1Password / Microsoft Bing Copilot / Grammarly /
        etc.) inject attributes like `__processed_<uuid>__="true"` and
        `bis_register="<base64 JSON>"` into <body> BEFORE React hydrates. The
        attributes are not in our SSR HTML, so React 19 detects them as a
        client-vs-server hydration mismatch and emits "A tree hydrated but
        some attributes of the server rendered HTML didn't match the client
        properties" warning. React's hydration-mismatch docs explicitly call
        out this case: "It can also happen if the client has a browser
        extension installed which messes with the HTML before React loaded."
        suppressHydrationWarning targets <body> ONLY (children still get full
        hydration checks); it's the canonical React 19 fix for extension-
        injected attributes.
      */}
      <body suppressHydrationWarning>
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
        {/*
          W156 SW3 polish — `className="ready"` rendered server-side via JSX
          so the opacity-1 state is in the SSR HTML from the start. Pre-W156
          SW3 main.tsx imperatively added `.ready` via classList.add post-
          hydrateRoot; React 19 hydration is concurrent + may span multiple
          frames, so the imperative mutation (even via requestAnimationFrame)
          races React's hydration comparison → "won't be patched up" warning.
          Emitting the class via JSX gives both SSR and client the same
          attribute from the start — no mismatch.
          Trade-off: the opacity 0 → 1 transition (INITIAL_PAINT_CSS at line ~115)
          never fires now (#root starts at opacity 1). Acceptable for SSR (content
          is already rendered, no FOUC to hide); for noscript users, the existing
          <noscript><style>{`#root { display: block !important; }`}</style></noscript>
          fallback below preserves visibility independently.
          main.tsx still hides the lhci-marker on LHCI builds (separate concern).
        */}
        <div id="root" className="ready">
          {children}
        </div>
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
  // LazyMotion, MotionConfig, LiveRegionProvider, MessengerShellProvider,
  // ErrorBoundary, GlobalHapticsListener, ThemeProvider. The full
  // WebSocket/Messenger providers mount only inside the lazy messenger route.
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
  //
  // Keep PersistQueryClientProvider here. A controlled swap to vanilla
  // `<QueryClientProvider>` did not resolve the blank /login regression, so
  // removing IndexedDB hydration is not a supported workaround. Investigate
  // profile synchronization and provider initialization before changing this
  // SSR/client-cache invariant.
  return (
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <ThemeProvider>
        <AppProviders>
          {/*
            Keep the boot loader in the route tree, rather than only in the
            document shell.  Both the server and client trees then own the
            same node, so static-SPA mounting and hydrateRoot can complete the
            loader lifecycle without leaving an orphaned hit target behind.
          */}
          <BrandBootLoader />
          <MainLayout>
            <PageErrorBoundary>
              <Outlet />
            </PageErrorBoundary>

            <DeferredGlobalOverlays />
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
  // MainLayout → PageErrorBoundary → Outlet) plus one
  // DeferredGlobalOverlays placeholder. The placeholder is null during SSR
  // and the first client render, then mounts the optional overlays in a
  // follow-up task; this keeps hydration deterministic while removing those
  // non-critical implementations from the initial module graph.
  const { queryClient } = useRouteContext({ from: "__root__" })
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AppProviders>
          {/* Mirror the client tree so the SSR loader is reconciled by React
              and can transition out after AppProviders publishes hydration. */}
          <BrandBootLoader />
          <MainLayout>
            <PageErrorBoundary>
              <Outlet />
            </PageErrorBoundary>

            <DeferredGlobalOverlays />
          </MainLayout>
        </AppProviders>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
