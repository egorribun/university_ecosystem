import { Link, useLocation } from "react-router-dom";
import { IconButton, Typography } from "@mui/material";
import TelegramIcon from "@mui/icons-material/Telegram";
import EmailIcon from "@mui/icons-material/Email";
import guuLogo from "@/assets/guu_logo.png";

export default function Footer() {
  const year = new Date().getFullYear();
  const location = useLocation();
  const isAuthPage = ["/login", "/register", "/forgot-password"].some((p) => location.pathname.startsWith(p));
  if (isAuthPage) return null;

  return (
    <footer className="footer-root" role="contentinfo">
      <div className="footer-inner">
        <div className="footer-grid">
          <div className="footer-brand">
            <div className="footer-brand-head">
              <div className="footer-logo">
                <img src={guuLogo} alt="ГУУ" />
              </div>
              <Typography className="footer-brand-title">Экосистема ГУУ</Typography>
            </div>
            <Typography className="footer-text">Профиль, расписание, новости и события университета в одном месте.</Typography>
            <div className="footer-social">
              <IconButton
                aria-label="Написать в Telegram"
                className="footer-social-btn"
                component="a"
                href="https://t.me/GUUmsk"
                target="_blank"
                rel="noopener noreferrer"
              >
                <TelegramIcon />
              </IconButton>
              <IconButton
                aria-label="Написать на email через Gmail"
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
            <div className="footer-title">Навигация</div>
            <Link to="/dashboard" className="footer-link">Главная</Link>
            <Link to="/news" className="footer-link">Новости</Link>
            <Link to="/schedule" className="footer-link">Расписание</Link>
            <Link to="/events" className="footer-link">Мероприятия</Link>
            <Link to="/map" className="footer-link">Карта</Link>
          </div>

          <div className="footer-col">
            <div className="footer-title">Профиль</div>
            <Link to="/profile" className="footer-link">Мой профиль</Link>
            <Link to="/settings" className="footer-link">Настройки</Link>
          </div>
        </div>

        <div className="footer-bottom">
          <Typography className="footer-copy">© {year} Экосистема ГУУ</Typography>
          <Typography className="footer-note">Сделано с заботой о студентах и преподавателях</Typography>
        </div>
      </div>
    </footer>
  );
}