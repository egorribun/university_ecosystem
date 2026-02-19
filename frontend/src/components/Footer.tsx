import { Link, useLocation } from "react-router-dom"
import { Send, Mail } from "lucide-react"
import guuLogo from "@/assets/guu_logo.png"
import SmartImage from "@/components/SmartImage"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui"

export default function Footer() {
  const { t } = useTranslation(["navigation"])
  const currentYear = new Date().getFullYear()
  const location = useLocation()
  const isAuthPage = ["/login", "/register", "/forgot-password", "/messenger"].some((p) =>
    location.pathname.startsWith(p)
  )
  if (isAuthPage) return null

  return (
    <footer
      className="bg-footer relative overflow-hidden border-t border-border-subtle/(--opacity-medium) min-h-(--h-skeleton-row)"
      role="contentinfo"
    >
      <div className="relative z-surface mx-auto max-w-(--layout-max-wide) px-fluid-x py-(--space-8) md:py-10">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-5 lg:gap-8">
          <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
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
              <h2 className="text-xl font-extrabold tracking-tight text-white">
                {t("navigation:brandName")}
              </h2>
            </div>
            <p className="max-w-(--w-label-xl) text-white opacity-hover">
              {t("navigation:brandDescription")}
            </p>
            <div className="mt-4 flex gap-3">
              <Button
                as="a"
                variant="glass"
                size="icon"
                aria-label={t("navigation:footer.contactTelegram")}
                className="rounded-sm"
                href="https://t.me/GUUmsk"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Send className="w-5 h-5" />
              </Button>
              <Button
                as="a"
                variant="glass"
                size="icon"
                aria-label={t("navigation:footer.contactEmail")}
                className="rounded-sm"
                href="https://mail.google.com/mail/?view=cm&fs=1&to=inf@guu.ru"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Mail className="w-5 h-5" />
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <h3 className="mb-1.5 text-sm font-extrabold tracking-widest text-white uppercase opacity-heavy">
              {t("navigation:footer.navigationTitle")}
            </h3>
            <Link to="/dashboard" className="footer-link-premium">
              {t("navigation:menu.dashboard")}
            </Link>
            <Link to="/news" className="footer-link-premium">
              {t("navigation:menu.news")}
            </Link>
            <Link to="/schedule" className="footer-link-premium">
              {t("navigation:menu.schedule")}
            </Link>
            <Link to="/events" className="footer-link-premium">
              {t("navigation:menu.events")}
            </Link>
            <Link to="/map" className="footer-link-premium">
              {t("navigation:menu.map")}
            </Link>
          </div>

          <div className="flex flex-col gap-1.5">
            <h3 className="mb-1.5 text-sm font-extrabold tracking-widest text-white uppercase opacity-heavy">
              {t("navigation:footer.profileTitle")}
            </h3>
            <Link to="/profile" className="footer-link-premium">
              {t("navigation:footer.myProfile")}
            </Link>
            <Link to="/settings" className="footer-link-premium">
              {t("navigation:menu.settings")}
            </Link>
          </div>
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle/(--opacity-medium) pt-8">
          <p className="text-sm font-medium text-white opacity-medium">
            {t("navigation:footer.copyright", { year: currentYear })}
          </p>
          <p className="text-xs text-white opacity-dim">{t("navigation:footer.careNote")}</p>
        </div>
      </div>
    </footer>
  )
}
