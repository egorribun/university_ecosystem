import { Link, useLocation } from "react-router-dom"
import { Send, Mail } from "lucide-react"
import guuLogo from "@/assets/guu_logo.png"
import SmartImage from "@/components/SmartImage"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

export default function Footer() {
  const year = new Date().getFullYear()
  const location = useLocation()
  const isAuthPage = ["/login", "/register", "/forgot-password", "/messenger"].some((p) =>
    location.pathname.startsWith(p)
  )
  if (isAuthPage) return null
  const { t } = useTranslation(["navigation"])

  return (
    <footer
      className="footer-root relative overflow-hidden"
      role="contentinfo"
      style={{
        minHeight: "150px",
      }}
    >
      <div className="footer-inner relative z-10">
        <div className="footer-grid">
          <div className="footer-brand">
            <div className="footer-brand-head">
              <div className="footer-logo">
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
              <h2 className="footer-brand-title">{t("navigation:brandName")}</h2>
            </div>
            <p className="footer-text">{t("navigation:brandDescription")}</p>
            <div className="footer-social flex gap-3 mt-4">
              <a
                aria-label={t("navigation:footer.contactTelegram")}
                className="footer-social-btn flex items-center justify-center w-10 h-10 rounded-xl bg-surface-raised border border-glass-border hover:bg-surface-hover hover:text-brand transition-all shadow-sm"
                href="https://t.me/GUUmsk"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Send className="w-5 h-5" />
              </a>
              <a
                aria-label={t("navigation:footer.contactEmail")}
                className="footer-social-btn flex items-center justify-center w-10 h-10 rounded-xl bg-surface-raised border border-glass-border hover:bg-surface-hover hover:text-brand transition-all shadow-sm"
                href="https://mail.google.com/mail/?view=cm&fs=1&to=inf@guu.ru"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Mail className="w-5 h-5" />
              </a>
            </div>
          </div>

          <div className="footer-col">
            <h3 className="footer-title">{t("navigation:footer.navigationTitle")}</h3>
            <Link to="/dashboard" className="footer-link">
              {t("navigation:menu.dashboard")}
            </Link>
            <Link to="/news" className="footer-link">
              {t("navigation:menu.news")}
            </Link>
            <Link to="/schedule" className="footer-link">
              {t("navigation:menu.schedule")}
            </Link>
            <Link to="/events" className="footer-link">
              {t("navigation:menu.events")}
            </Link>
            <Link to="/map" className="footer-link">
              {t("navigation:menu.map")}
            </Link>
          </div>

          <div className="footer-col">
            <h3 className="footer-title">{t("navigation:footer.profileTitle")}</h3>
            <Link to="/profile" className="footer-link">
              {t("navigation:footer.myProfile")}
            </Link>
            <Link to="/settings" className="footer-link">
              {t("navigation:menu.settings")}
            </Link>
          </div>
        </div>

        <div className="footer-bottom mt-12 pt-8 border-t border-glass-border/10">
          <p className="footer-copy text-sm opacity-60">
            {t("navigation:footer.copyright", { year })}
          </p>
          <p className="footer-note text-xs opacity-40 mt-1">{t("navigation:footer.careNote")}</p>
        </div>
      </div>
    </footer>
  )
}
