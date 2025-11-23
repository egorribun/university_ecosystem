import { Link, useLocation } from "react-router-dom"
import { IconButton, Typography } from "@mui/material"
import TelegramIcon from "@mui/icons-material/Telegram"
import EmailIcon from "@mui/icons-material/Email"
import guuLogo from "@/assets/guu_logo.png"
import { useTranslation } from "react-i18next"

export default function Footer() {
  const year = new Date().getFullYear()
  const location = useLocation()
  const isAuthPage = ["/login", "/register", "/forgot-password"].some((p) =>
    location.pathname.startsWith(p)
  )
  if (isAuthPage) return null
  const { t } = useTranslation(["navigation"])

  return (
    <footer
      className="footer-root"
      role="contentinfo"
      style={{
        minHeight: location.pathname.startsWith("/messenger") ? "400px" : "150px",
        marginTop: location.pathname.startsWith("/messenger") ? "-64px" : undefined,
        borderTop: location.pathname.startsWith("/messenger") ? "none" : undefined,
        position: location.pathname.startsWith("/messenger") ? "relative" : undefined,
        zIndex: location.pathname.startsWith("/messenger") ? 10 : undefined,
      }}
    >
      <div className="footer-inner">
        <div className="footer-grid">
          <div className="footer-brand">
            <div className="footer-brand-head">
              <div className="footer-logo">
                <img
                  src={guuLogo}
                  alt={t("navigation:brandAlt")}
                  width={48}
                  height={48}
                  loading="lazy"
                  decoding="async"
                />
              </div>
              <Typography className="footer-brand-title">{t("navigation:brandName")}</Typography>
            </div>
            <Typography className="footer-text">{t("navigation:brandDescription")}</Typography>
            <div className="footer-social">
              <IconButton
                aria-label={t("navigation:footer.contactTelegram")}
                className="footer-social-btn"
                component="a"
                href="https://t.me/GUUmsk"
                target="_blank"
                rel="noopener noreferrer"
              >
                <TelegramIcon />
              </IconButton>
              <IconButton
                aria-label={t("navigation:footer.contactEmail")}
                className="footer-social-btn"
                component="a"
                href="https://mail.google.com/mail/?view=cm&fs=1&to=inf@guu.ru"
                target="_blank"
                rel="noopener noreferrer"
              >
                <EmailIcon />
              </IconButton>
            </div>
          </div>

          <div className="footer-col">
            <div className="footer-title">{t("navigation:footer.navigationTitle")}</div>
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
            <div className="footer-title">{t("navigation:footer.profileTitle")}</div>
            <Link to="/profile" className="footer-link">
              {t("navigation:footer.myProfile")}
            </Link>
            <Link to="/settings" className="footer-link">
              {t("navigation:menu.settings")}
            </Link>
          </div>
        </div>

        <div className="footer-bottom">
          <Typography className="footer-copy">
            {t("navigation:footer.copyright", { year })}
          </Typography>
          <Typography className="footer-note">{t("navigation:footer.careNote")}</Typography>
        </div>
      </div>
    </footer>
  )
}
