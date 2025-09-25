import { Link, useNavigate, useLocation } from "react-router-dom";
import { useState, useEffect, useRef, useMemo, useCallback, useLayoutEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import guuLogo from "../assets/guu_logo.png";
import defaultAvatar from "../assets/default_avatar.png";
import { resolveMediaUrl } from "@/utils/media";
import NotificationsBell from "@/components/NotificationsBell";
import "@/push/register-sw";

const navTextColor = "var(--nav-text)";
const navBgColor = "var(--nav-bg)";
const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || "";

function useIsMobile() {
  const getMatch = useCallback(() => {
    if (typeof window === "undefined" || !("matchMedia" in window)) return false;
    return window.matchMedia("(max-width: 1350px)").matches;
  }, []);
  const [match, setMatch] = useState(getMatch);
  useEffect(() => {
    if (typeof window === "undefined" || !("matchMedia" in window)) return;
    const mql = window.matchMedia("(max-width: 1350px)");
    const onChange = (e: MediaQueryListEvent | MediaQueryList) => {
      setMatch("matches" in e ? e.matches : (e as MediaQueryList).matches);
    };
    if (mql.addEventListener) mql.addEventListener("change", onChange as EventListener);
    else mql.addListener(onChange as (this: MediaQueryList, ev: MediaQueryListEvent) => any);
    setMatch(mql.matches);
    return () => {
      if (mql.removeEventListener) mql.removeEventListener("change", onChange as EventListener);
      else mql.removeListener(onChange as (this: MediaQueryList, ev: MediaQueryListEvent) => any);
    };
  }, [getMatch]);
  return match;
}

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
  const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
  if (nearBottom) sessionStorage.setItem("__scrollTopNext", "1");
}

function samePath(a: string, b: string) {
  const na = a.replace(/\/+$/, "") || "/";
  const nb = b.replace(/\/+$/, "") || "/";
  return na === nb;
}

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuth, loading } = useAuth();

  const [mobileMenu, setMobileMenu] = useState(false);

  const isMobile = useIsMobile();
  const prevIsMobile = useRef(isMobile);
  const navRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (prevIsMobile.current !== isMobile && !isMobile) setMobileMenu(false);
    prevIsMobile.current = isMobile;
  }, [isMobile]);

  useEffect(() => {
    document.body.style.overflow = mobileMenu ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileMenu]);

  useEffect(() => { setMobileMenu(false); }, [location.pathname]);

  useEffect(() => {
    const opened = mobileMenu && isMobile;
    document.body.classList.toggle("blurred", opened);
    return () => { document.body.classList.remove("blurred"); };
  }, [mobileMenu, isMobile]);

  useEffect(() => { navRef.current?.classList.add("navbar-animate-in"); }, []);

  useLayoutEffect(() => {
    if (sessionStorage.getItem("__scrollTopNext") === "1") {
      sessionStorage.removeItem("__scrollTopNext");
      const el = getScrollRoot();
      requestAnimationFrame(() => requestAnimationFrame(() => smoothToTop(el)));
    }
  }, [location.pathname]);

  const getAvatarSrc = () => {
    if (user?.avatar_url) {
      const url = resolveMediaUrl(user.avatar_url, BACKEND_ORIGIN);
      const ver = (user as any).avatar_updated_at || Date.now();
      return `${url}?v=${ver}`;
    }
    return defaultAvatar;
  };

  const menuLinks = useMemo(() => {
    const base = [
      { to: "/dashboard", label: "Главная" },
      { to: "/news", label: "Новости" },
      { to: "/schedule", label: "Расписание" },
      { to: "/events", label: "Мероприятия" },
      { to: "/activity", label: "Активность" },
      { to: "/map", label: "Карта" }
    ];
    if (user?.role === "admin") base.push({ to: "/admin/users", label: "Пользователи" });
    return base;
  }, [user?.role]);

  const isActive = (to: string) => {
    if (to === "/dashboard" && location.pathname === "/") return true;
    return location.pathname === to || location.pathname.startsWith(to + "/");
  };

  const isSameTarget = (to: string) => {
    if (to === "/dashboard") return location.pathname === "/" || samePath(location.pathname, "/dashboard");
    return samePath(location.pathname, to);
  };

  const go = (to: string) => {
    if (isSameTarget(to)) {
      const el = getScrollRoot();
      smoothToTop(el);
    } else {
      markIfFromBottom();
      navigate(to);
    }
  };

  const logoWrapSize = isMobile ? 44 : 52;
  const logoImgSize = isMobile ? 34 : 42;
  const titleFont = isMobile ? "clamp(16px, 5.2vw, 20px)" : "clamp(18px, 1.6vw, 22px)";
  const rightNameFont = isMobile ? "clamp(14px, 4.5vw, 16px)" : "1.01rem";
  const avatarSize = isMobile ? "clamp(30px, 8vw, 36px)" : "36px";
  const burgerBtnSize = isMobile ? "clamp(44px, 10.5vw, 48px)" : "40px";
  const burgerIcon = isMobile ? 26 : 28;

  return (
    <>
      <nav
        ref={navRef}
        className="navbar-root"
        style={{
          minHeight: isMobile ? "56px" : "64px",
          width: "100%",
          overflowX: "hidden",
          position: "sticky",
          top: "env(safe-area-inset-top, 0px)",
          zIndex: "var(--ue-z-index-nav)"
        }}
      >
        <div
          style={{ display: "flex", alignItems: "center", justifyContent: "flex-start", width: "100%", padding: isMobile ? "0 10px" : "0 16px", boxSizing: "border-box", minWidth: 0, gap: "0" }}
        >
          <Link
            to="/dashboard"
            aria-label="На главную"
            className="brand"
            onPointerDown={markIfFromBottom}
            onClick={(e) => {
              if (isSameTarget("/dashboard")) {
                e.preventDefault();
                const el = getScrollRoot();
                smoothToTop(el);
              }
            }}
            style={{ display: "inline-flex", alignItems: "center", gap: isMobile ? "8px" : "10px", minWidth: 0, padding: "6px 6px", borderRadius: 12, textDecoration: "none" }}
          >
            <div style={{ width: `${logoWrapSize}px`, height: `${logoWrapSize}px`, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "50%", background: "#fff", boxShadow: "0 0 8px rgba(0,0,0,0.13)" }}>
              <img src={guuLogo} alt="ГУУ" width={logoImgSize} height={logoImgSize} style={{ objectFit: "contain" }} />
            </div>
            <span style={{ color: "#fff", fontWeight: 800, fontSize: titleFont, whiteSpace: "nowrap", letterSpacing: ".2px" }}>
              Экосистема ГУУ
            </span>
          </Link>

          {isMobile ? (
            <div style={{ display: "flex", alignItems: "center", marginLeft: "auto", gap: "6px" }}>
              <NotificationsBell iconColor="#fff" />
              {isAuth && user && (
                <img
                  src={getAvatarSrc()}
                  alt="avatar"
                  style={{ width: avatarSize, height: avatarSize, borderRadius: "50%", objectFit: "cover", border: "1px solid #d7d7d7", background: "#fff", cursor: "pointer" }}
                  onClick={() => go("/profile")}
                  onError={(e) => { (e.currentTarget as HTMLImageElement).src = defaultAvatar; }}
                />
              )}
              <button
                type="button"
                className="burger-btn"
                style={{ background: "none", border: "none", padding: 0, width: burgerBtnSize, height: burgerBtnSize, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#fff", borderRadius: 10 }}
                onClick={() => setMobileMenu(v => !v)}
                aria-label="Меню"
                aria-expanded={mobileMenu}
                aria-controls="mobile-drawer"
              >
                <svg width={burgerIcon} height={burgerIcon} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="4" y1="7" x2="22" y2="7"/>
                  <line x1="4" y1="13" x2="22" y2="13"/>
                  <line x1="4" y1="19" x2="22" y2="19"/>
                </svg>
              </button>
            </div>
          ) : (
            <ul
              style={{ display: "flex", flexDirection: "row", flexWrap: "wrap", alignItems: "center", fontWeight: 500, listStyle: "none", gap: "8px", margin: 0, padding: 0, minWidth: 0, marginLeft: "36px", flex: 1, fontSize: "1.03rem" }}
            >
              {menuLinks.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={`menu-link${isActive(item.to) ? " active" : ""}`}
                    onPointerDown={markIfFromBottom}
                    onClick={(e) => {
                      if (isSameTarget(item.to)) {
                        e.preventDefault();
                        const el = getScrollRoot();
                        smoothToTop(el);
                      }
                    }}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {!isMobile && loading ? null : (!isMobile && isAuth && user && (
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginLeft: "8px", minWidth: 0, whiteSpace: "nowrap" }}>
              <NotificationsBell iconColor="#fff" />
              <img
                src={getAvatarSrc()}
                alt="avatar"
                style={{ width: "36px", height: "36px", borderRadius: "50%", objectFit: "cover", border: "1.5px solid #ccc", background: "#fff", cursor: "pointer" }}
                onClick={() => go("/profile")}
                onError={(e) => { (e.currentTarget as HTMLImageElement).src = defaultAvatar; }}
              />
              <button
                type="button"
                onClick={() => go("/profile")}
                style={{
                  background: "none",
                  border: "none",
                  padding: 0,
                  margin: 0,
                  color: "#fff",
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                  cursor: "pointer",
                  fontSize: rightNameFont,
                  fontFamily: "var(--font-ui)",
                  letterSpacing: "var(--ls-ui)",
                  lineHeight: "var(--lh-ui)"
                }}
              >
                {user.full_name}
              </button>
              <button
                type="button"
                className="menu-btn-settings"
                style={{ background: "none", border: "none", padding: 0, width: 32, height: 32, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 22 }}
                onClick={() => go("/settings")}
                aria-label="Настройки"
                title="Настройки"
              >
                <span role="img" aria-label="Настройки">⚙️</span>
              </button>
            </div>
          ))}
        </div>
      </nav>

      {isMobile && (
        <div
          id="mobile-drawer"
          className="mobile-drawer"
          style={{ position: "fixed", top: 0, left: 0, width: "100vw", height: "100vh", zIndex: "var(--ue-z-index-overlay)", pointerEvents: mobileMenu ? "auto" : "none", background: mobileMenu ? "rgba(0,0,0,0.23)" : "transparent", transition: "background 0.28s", display: "flex" }}
          onClick={() => setMobileMenu(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Мобильное меню"
        >
          <nav
            style={{ width: 270, maxWidth: "88vw", background: navBgColor, height: "100vh", boxShadow: "2px 0 22px #0003", padding: 0, display: "flex", flexDirection: "column", alignItems: "flex-start", transition: "transform 0.35s cubic-bezier(.52,1.29,.47,.97)", transform: mobileMenu ? "translateX(0)" : "translateX(-120%)", justifyContent: "flex-start", position: "relative" }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ width: "100%", padding: "18px 0 10px 22px", display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #ede2d2" }}>
              <div style={{ width: 32, height: 32, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: "#fff", boxShadow: "0 0 6px rgba(0,0,0,0.10)" }}>
                <img src={guuLogo} alt="ГУУ" width={24} height={24} style={{ objectFit: "contain" }} />
              </div>
              <span style={{ color: navTextColor, fontWeight: 800, fontSize: "clamp(15px, 4.5vw, 18px)", whiteSpace: "nowrap" }}>
                Экосистема ГУУ
              </span>
            </div>
            <button
              type="button"
              style={{ position: "absolute", top: 9, right: 10, background: "none", border: "none", fontSize: 27, color: navTextColor, cursor: "pointer" }}
              aria-label="Закрыть"
              onClick={() => setMobileMenu(false)}
            >
              ×
            </button>
            <ul
              style={{ display: "flex", flexDirection: "column", listStyle: "none", gap: "10px", margin: 0, padding: "16px 0 0 24px", flex: 1, width: "100%" }}
            >
              {menuLinks.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={`menu-link${isActive(item.to) ? " active" : ""}`}
                    onPointerDown={markIfFromBottom}
                    onClick={(e) => {
                      setMobileMenu(false);
                      if (isSameTarget(item.to)) {
                        e.preventDefault();
                        const el = getScrollRoot();
                        smoothToTop(el);
                      }
                    }}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
              {isAuth && user && (
                <li>
                  <button
                    type="button"
                    className="menu-link settings"
                    onPointerDown={markIfFromBottom}
                    onClick={e => { e.stopPropagation(); setMobileMenu(false); go("/settings"); }}
                    aria-label="Настройки"
                    title="Настройки"
                  >
                    Настройки
                  </button>
                </li>
              )}
            </ul>
          </nav>
        </div>
      )}
    </>
  );
};

export default Navbar;