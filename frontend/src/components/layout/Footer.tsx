import { Link } from "@tanstack/react-router"
import { Mail } from "lucide-react"
// Keep the shared logo as a real immutable asset instead of an inline data URI.
// The source is just below Vite's default inline threshold, so importing it
// normally duplicates its base64 payload in every SSR logo/srcset occurrence
// (eight copies in the shell). `?url` emits one cacheable file and keeps the
// initial HTML small without changing the rendered image contract.
import guuLogo from "@/assets/guu_logo.png?url&no-inline"
import SmartImage from "@/components/media/SmartImage"
import { useTranslation } from "react-i18next"

// MainLayout owns route visibility. The footer itself stays deterministic
// between SSR and hydration: no viewport hooks, ambient canvas, or glow layer.
const ACTIVE_OPTIONS = { exact: false } as const

function TelegramIcon() {
  return (
    <svg
      aria-hidden="true"
      data-icon="telegram"
      focusable="false"
      viewBox="0 0 24 24"
      className="h-5 w-5"
    >
      <path
        fill="currentColor"
        d="M11.944 0A12 12 0 1 0 24 12 12.013 12.013 0 0 0 11.944 0Zm5.891 8.166-1.97 9.28c-.145.658-.537.818-1.084.51l-3-2.21-1.447 1.394a.759.759 0 0 1-.6.295l.213-3.05 5.56-5.022c.242-.213-.054-.334-.373-.121l-6.87 4.326-2.96-.924c-.642-.204-.657-.642.136-.953l11.57-4.458c.538-.194 1.006.131.825.933Z"
      />
    </svg>
  )
}

export default function Footer() {
  const { t } = useTranslation(["navigation"])
  const currentYear = new Date().getFullYear()

  return (
    <footer
      className="bg-footer @container relative overflow-hidden border-t border-border-subtle/(--opacity-medium) min-h-(--h-skeleton-row)"
      role="contentinfo"
    >
      <div className="footer-accent-stripe" aria-hidden="true" />
      <div className="relative z-surface mx-auto max-w-(--layout-max-wide) px-fluid-x py-(--space-8) @md:py-10">
        <div className="grid gap-6 @sm:grid-cols-2 @lg:grid-cols-4 @lg:gap-8">
          <div className="flex min-w-0 flex-col gap-3 @lg:col-span-2">
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
                className="footer-social-btn min-h-11 min-w-11"
                href="https://t.me/GUUmsk"
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`${t("navigation:footer.contactTelegram")} (${t("navigation:footer.opensNewTab")})`}
              >
                <TelegramIcon />
              </a>
              <a
                className="footer-social-btn min-h-11 min-w-11"
                href="mailto:inf@guu.ru"
                aria-label={t("navigation:footer.contactEmail")}
              >
                <Mail className="h-5 w-5" aria-hidden="true" />
              </a>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
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

          <div className="flex flex-col gap-1.5">
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
