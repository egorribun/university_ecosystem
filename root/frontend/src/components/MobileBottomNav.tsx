import { NavLink, useLocation } from "react-router-dom";
import { useLayoutEffect, useMemo } from "react";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ArticleIcon from "@mui/icons-material/Article";
import EventNoteIcon from "@mui/icons-material/EventNote";
import TodayIcon from "@mui/icons-material/Today";
import PersonIcon from "@mui/icons-material/Person";

function getScrollRoot(): HTMLElement {
  const cands: (Element | null | Document | HTMLElement)[] = [
    document.querySelector("[data-scroll-root]"),
    document.querySelector("main[role='main']"),
    document.querySelector("main"),
    document.getElementById("scroll-root"),
    document.querySelector("#root"),
    (document as any).scrollingElement,
    document.documentElement,
    document.body
  ];
  for (const el of cands) {
    if (!el) continue;
    const e = el as HTMLElement;
    const oy = getComputedStyle(e).overflowY;
    const scrollable = (oy === "auto" || oy === "scroll") && e.scrollHeight > e.clientHeight;
    if (scrollable) return e;
  }
  return (document.scrollingElement || document.documentElement) as HTMLElement;
}

function smoothToTop(target: HTMLElement) {
  try {
    (target as any).scrollTo({ top: 0, behavior: "smooth" });
  } catch {
    const start = target.scrollTop;
    const duration = 420;
    let t0 = 0;
    const step = (ts: number) => {
      if (!t0) t0 = ts;
      const p = Math.min(1, (ts - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      target.scrollTop = Math.round(start * (1 - eased));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}

function markIfFromBottom() {
  const el = getScrollRoot();
  const threshold = 24;
  const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - threshold;
  if (nearBottom) sessionStorage.setItem("__scrollTopNext", "1");
}

function samePath(a: string, b: string) {
  const na = a.replace(/\/+$/, "") || "/";
  const nb = b.replace(/\/+$/, "") || "/";
  return na === nb;
}

export default function MobileBottomNav() {
  const { pathname } = useLocation();

  useLayoutEffect(() => {
    if (sessionStorage.getItem("__scrollTopNext") === "1") {
      sessionStorage.removeItem("__scrollTopNext");
      const el = getScrollRoot();
      requestAnimationFrame(() => requestAnimationFrame(() => smoothToTop(el)));
    }
  }, [pathname]);

  const items = useMemo(
    () => [
      { to: "/dashboard", label: "Главная", icon: <DashboardIcon /> },
      { to: "/news", label: "Новости", icon: <ArticleIcon /> },
      { to: "/events", label: "События", icon: <EventNoteIcon /> },
      { to: "/schedule", label: "Расписание", icon: <TodayIcon /> },
      { to: "/profile", label: "Профиль", icon: <PersonIcon /> }
    ],
    []
  );

  const hideOn = ["/login", "/register", "/forgot-password", "/reset-password"];
  const hidden = hideOn.some((p) => pathname.startsWith(p));
  if (hidden) return null;

  return (
    <>
      <nav className="bottom-nav glass" role="navigation" aria-label="Основная навигация">
        {items.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            onPointerDown={markIfFromBottom}
            onClick={(e) => {
              if (samePath(pathname, it.to)) {
                e.preventDefault();
                const el = getScrollRoot();
                requestAnimationFrame(() => smoothToTop(el));
              }
            }}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && samePath(pathname, it.to)) {
                e.preventDefault();
                const el = getScrollRoot();
                requestAnimationFrame(() => smoothToTop(el));
              }
            }}
            className={({ isActive }) => "bottom-nav__item" + (isActive ? " active" : "")}
            aria-label={it.label}
          >
            <span className="bottom-nav__icon">{it.icon}</span>
            <span className="bottom-nav__label">{it.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="bottom-nav-spacer" aria-hidden="true" />
    </>
  );
}