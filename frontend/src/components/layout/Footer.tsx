import { Link } from "@tanstack/react-router"
import { Send, Mail } from "lucide-react"
import type { CSSProperties } from "react"
import guuLogo from "@/assets/guu_logo.png"
import SmartImage from "@/components/media/SmartImage"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import FooterBackdrop from "@/components/layout/FooterBackdrop"

// Wave 176 SW1 — `isAuthPage` early-return removed. Footer rendering is
// already gated by `MainLayout` via `useRouteType()` (`hideFooter` covers
// /map + /schedule + /messenger; `isCompactPage` covers /login + /register +
// /forgot-password + /reset-password). Maintaining a second list inside
// Footer.tsx duplicated logic + drifted from the source of truth (e.g., the
// old list omitted /reset-password). Footer.tsx is now a "trust the parent"
// component — it always renders when mounted.
//
// Wave 176 SW2 — `FooterBackdrop` decorative orb layer + `useReducedMotion` +
// `useMediaQuery` hooks added. Pattern mirrors EventsFeature/EventsBackdrop
// (Wave 118 SW3 CLS-118-03 pixel-sizing lesson preserved).
//
// Wave 176 SW3 — Premium visual polish:
//   • `@container` on <footer> + `@sm:` / `@lg:` / `@md:` modifiers — inner
//     grid responds to footer's OWN width (future-proof for narrow embeds).
//   • `footer-accent-stripe` ::utility on a sibling <div> — soft gradient
//     bar at top of footer to ease visual transition from page content.
//   • Entrance animation on <footer> via Tailwind v4 `starting:` variant
//     (CSS @starting-style) — zero JS, fires on mount, motion-reduce-aware.
//   • Per-column `footer-stagger-item` utility with inline `--stagger-i`
//     CSS variable — 0/1/2 indexed cascade (0ms / 80ms / 160ms).
//   • Social buttons migrated from `<Button variant="glass" size="icon">` to
//     plain `<a className="footer-social-btn">` — glass-on-glass had poor
//     contrast on the dark footer surface.
//
// Wave 176 SW4 — `activeOptions={{ exact: false }}` on each <Link> turns
// on prefix-match active-state (e.g. /news/article-123 → /news link shows
// active dot). TanStack Router auto-applies `data-status="active"` to
// matching links — no `activeProps` needed. CSS for the accent dot lives
// in `tailwind.css` `@utility footer-link-premium` (`&[data-status="active"]`).
const ACTIVE_OPTIONS = { exact: false } as const
export default function Footer() {
  const { t } = useTranslation(["navigation"])
  const currentYear = new Date().getFullYear()
  // Wave 189 SW3 — migrated from framer-motion's `useReducedMotion()` (jsdom-
  // incompat per W184 SW6 Gotcha) to project's `useMediaQuery` DEFAULT export.
  // Removes hidden dependency on framer-motion's `initPrefersReducedMotion`
  // listener-registration code path which crashes under jsdom's matchMedia
  // polyfill. Behaviour preserved: returns boolean (was `boolean | null`
  // requiring `?? false`).
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)

  const staggerStyle = (index: number): CSSProperties => ({ "--stagger-i": index }) as CSSProperties

  return (
    <footer
      className="bg-footer @container relative overflow-hidden border-t border-border-subtle/(--opacity-medium) min-h-(--h-skeleton-row) starting:opacity-0 starting:translate-y-2 transition-all duration-500 ease-[var(--ease-premium)] motion-reduce:transition-none motion-reduce:starting:opacity-100 motion-reduce:starting:translate-y-0"
      role="contentinfo"
    >
      <FooterBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
      <div className="footer-accent-stripe" aria-hidden="true" />
      <div className="relative z-surface mx-auto max-w-(--layout-max-wide) px-fluid-x py-(--space-8) @md:py-10">
        <div className="grid gap-6 @sm:grid-cols-2 @lg:grid-cols-5 @lg:gap-8">
          <div
            className="footer-stagger-item flex min-w-0 flex-col gap-3 @lg:col-span-2"
            style={staggerStyle(0)}
          >
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-(--bg-surface-raised) border border-border-subtle">
                <SmartImage
                  srcRaw={guuLogo}
                  alt={t("navigation:brandAlt")}
                  width={48}
                  height={48}
                  loading="lazy"
                  sizes="48px"
                  responsiveWidths={[48, 64, 96]}
                  decoding="async"
                  className="h-12 w-12"
                />
              </div>
              <h2 className="text-xl font-extrabold tracking-tight text-[var(--text-on-footer)]">
                {t("navigation:brandName")}
              </h2>
            </div>
            <p className="max-w-(--w-label-xl) text-[var(--text-on-footer)] opacity-hover">
              {t("navigation:brandDescription")}
            </p>
            <div className="mt-4 flex gap-3">
              <a
                className="footer-social-btn"
                href="https://t.me/GUUmsk"
                target="_blank"
                rel="noopener noreferrer"
                aria-label={t("navigation:footer.contactTelegram")}
              >
                <Send className="h-5 w-5" aria-hidden="true" />
              </a>
              <a
                className="footer-social-btn"
                href="https://mail.google.com/mail/?view=cm&fs=1&to=inf@guu.ru"
                target="_blank"
                rel="noopener noreferrer"
                aria-label={t("navigation:footer.contactEmail")}
              >
                <Mail className="h-5 w-5" aria-hidden="true" />
              </a>
            </div>
          </div>

          <div className="footer-stagger-item flex flex-col gap-1.5" style={staggerStyle(1)}>
            <h3 className="mb-1.5 text-sm font-extrabold tracking-widest text-[var(--text-on-footer)] uppercase opacity-heavy">
              {t("navigation:footer.navigationTitle")}
            </h3>
            <Link to="/dashboard" className="footer-link-premium" activeOptions={ACTIVE_OPTIONS}>
              {t("navigation:menu.dashboard")}
            </Link>
            <Link to="/news" className="footer-link-premium" activeOptions={ACTIVE_OPTIONS}>
              {t("navigation:menu.news")}
            </Link>
            <Link to="/schedule" className="footer-link-premium" activeOptions={ACTIVE_OPTIONS}>
              {t("navigation:menu.schedule")}
            </Link>
            <Link to="/events" className="footer-link-premium" activeOptions={ACTIVE_OPTIONS}>
              {t("navigation:menu.events")}
            </Link>
            <Link to="/map" className="footer-link-premium" activeOptions={ACTIVE_OPTIONS}>
              {t("navigation:menu.map")}
            </Link>
          </div>

          <div className="footer-stagger-item flex flex-col gap-1.5" style={staggerStyle(2)}>
            <h3 className="mb-1.5 text-sm font-extrabold tracking-widest text-[var(--text-on-footer)] uppercase opacity-heavy">
              {t("navigation:footer.profileTitle")}
            </h3>
            <Link to="/profile" className="footer-link-premium" activeOptions={ACTIVE_OPTIONS}>
              {t("navigation:footer.myProfile")}
            </Link>
            <Link to="/settings" className="footer-link-premium" activeOptions={ACTIVE_OPTIONS}>
              {t("navigation:menu.settings")}
            </Link>
          </div>
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle/(--opacity-medium) pt-8">
          <p className="text-sm font-medium text-[var(--text-on-footer)] opacity-medium">
            {t("navigation:footer.copyright", { year: currentYear })}
          </p>
          <p className="text-xs text-[var(--text-on-footer)] opacity-dim">
            {t("navigation:footer.careNote")}
          </p>
        </div>
      </div>
    </footer>
  )
}
