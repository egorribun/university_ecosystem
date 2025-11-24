import { Link, useNavigate, useLocation } from "react-router-dom";
import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import Skeleton from "@mui/material/Skeleton";
import { useAuth } from "../contexts/AuthContext";
import guuLogo from "../assets/guu_logo.png";
import SmartImage from "@/components/SmartImage";
import NotificationsBell from "@/components/NotificationsBell";
import MessengerButton from "@/components/MessengerButton";
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders";
import { useTranslation } from "react-i18next";
import useMediaQuery from "@/hooks/useMediaQuery";
import useFocusTrap from "@/hooks/useFocusTrap";
import useScrollRestoration from "@/hooks/useScrollRestoration";
import { useAppShell } from "@/contexts/AppShellContext";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ArticleIcon from "@mui/icons-material/Article";
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth";
import EventNoteIcon from "@mui/icons-material/EventNote";
import TimelineIcon from "@mui/icons-material/Timeline";
import MapIcon from "@mui/icons-material/Map";
import NotificationsIcon from "@mui/icons-material/Notifications";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import PeopleIcon from "@mui/icons-material/People";
import SettingsIcon from "@mui/icons-material/Settings";
import { cn } from "@/utils/cn";
import { MobileMenu } from "@/components/navbar/MobileMenu";

const AVATAR_FALLBACK = AVATAR_PLACEHOLDER_URL;

function parseCacheVersion(input: unknown): number | undefined {
  if (typeof input === "number" && Number.isFinite(input)) return input;
  if (typeof input === "string") {
    const numeric = Number(input);
    if (!Number.isNaN(numeric)) return numeric;
    const parsed = Date.parse(input);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return undefined;
}

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const pathname = location.pathname;
  const { user, isAuth, loading } = useAuth();
  const { t } = useTranslation(["navigation"]);
  const { setOverlayState } = useAppShell();

  const [mobileMenu, setMobileMenu] = useState(false);

  const isMobile = useMediaQuery("(max-width: 1350px)");
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const { scrollToTop, markScrollFromBottom, isSamePath } = useScrollRestoration(
    location.pathname
  );
  const prevIsMobile = useRef(isMobile);
  const navRef = useRef<HTMLElement | null>(null);
  const burgerBtnRef = useRef<HTMLButtonElement | null>(null);
  const drawerTrapRef = useFocusTrap<HTMLDivElement>({
    active: mobileMenu && isMobile,
    onDeactivate: () => setMobileMenu(false),
  });

  useEffect(() => {
    if (prevIsMobile.current !== isMobile && !isMobile) setMobileMenu(false);
    prevIsMobile.current = isMobile;
  }, [isMobile]);

  useEffect(() => {
    setMobileMenu(false);
  }, [location.pathname]);

  useEffect(() => {
    if (mobileMenu && isMobile) {
      setOverlayState("mobile-drawer", {
        scrollLocked: true,
        blurred: !prefersReducedMotion,
      });
    } else {
      setOverlayState("mobile-drawer", null);
    }
    return () => {
      setOverlayState("mobile-drawer", null);
    };
  }, [isMobile, mobileMenu, prefersReducedMotion, setOverlayState]);

  useEffect(() => {
    if (prefersReducedMotion) return;
    navRef.current?.classList.add("navbar-animate-in");
  }, [prefersReducedMotion]);

  const avatarCacheV = useMemo(() => {
    const raw =
      (user as any)?.avatar_updated_at ??
      (user as any)?.avatar_version ??
      (user as any)?.updated_at ??
      undefined;
    return parseCacheVersion(raw);
  }, [user]);

  const avatarFallback = AVATAR_FALLBACK;

  const avatarSource = user?.avatar_url || "";
  const hasAvatar = Boolean(avatarSource);

  const menuLinks = useMemo(() => {
    const base = [
      { to: "/dashboard", label: t("navigation:menu.dashboard"), icon: DashboardIcon },
      { to: "/news", label: t("navigation:menu.news"), icon: ArticleIcon },
      { to: "/schedule", label: t("navigation:menu.schedule"), icon: CalendarMonthIcon },
      { to: "/events", label: t("navigation:menu.events"), icon: EventNoteIcon },
      { to: "/activity", label: t("navigation:menu.activity"), icon: TimelineIcon },
      { to: "/map", label: t("navigation:menu.map"), icon: MapIcon },
    ];
    if (user?.role === "admin") {
      base.push({
        to: "/admin/notifications",
        label: t("navigation:menu.notificationsAdmin"),
        icon: NotificationsIcon,
      });
      base.push({
        to: "/admin/stories",
        label: t("navigation:menu.stories"),
        icon: AutoStoriesIcon,
      });
      base.push({
        to: "/admin/users",
        label: t("navigation:menu.users"),
        icon: PeopleIcon,
      });
    }
    return base;
  }, [t, user?.role]);

  const profileAlt = user?.full_name
    ? t("navigation:aria.profileAvatarNamed", { name: user.full_name })
    : t("navigation:aria.profileAvatar");
  const profileTitle = t("navigation:aria.openProfile");

  const isActive = useCallback(
    (to: string) => {
      if (to === "/dashboard") {
        return (
          pathname === "/" ||
          pathname === "/dashboard" ||
          pathname.startsWith("/dashboard/")
        );
      }
      return pathname === to;
    },
    [pathname]
  );

  const isSameTarget = useCallback((to: string) => isSamePath(to), [isSamePath]);

  const go = useCallback(
    (to: string) => {
      if (isSameTarget(to)) {
        scrollToTop(prefersReducedMotion ? "auto" : "smooth");
      } else {
        markScrollFromBottom();
        navigate(to);
      }
    },
    [isSameTarget, markScrollFromBottom, navigate, prefersReducedMotion, scrollToTop]
  );

  const logoWrapSize = isMobile ? 44 : 52;
  const logoImgSize = isMobile ? 34 : 42;
  const titleFont = isMobile ? "clamp(16px, 5.2vw, 20px)" : "clamp(18px, 1.6vw, 22px)";
  const rightNameFont = isMobile ? "clamp(14px, 4.5vw, 16px)" : "1.01rem";
  const avatarSize = isMobile ? "clamp(30px, 8vw, 36px)" : "36px";
  const burgerBtnSize = isMobile ? "clamp(44px, 10.5vw, 48px)" : "40px";

  return (
    <>
      <nav
        ref={navRef}
        className={cn(
          "navbar-root sticky top-[env(safe-area-inset-top,0px)] z-[var(--ue-z-index-nav)] w-full overflow-x-hidden",
          isMobile ? "min-h-[56px]" : "min-h-[64px]",
          prefersReducedMotion && "transition-none animate-none"
        )}
      >
        <div
          className={cn(
            "flex w-full min-w-0 items-center justify-start gap-0 box-border",
            isMobile ? "px-2.5" : "px-4"
          )}
        >
          <Link
            to="/dashboard"
            aria-label={t("navigation:aria.homeLink")}
            className="brand inline-flex min-w-0 items-center rounded-xl p-1.5 no-underline"
            onPointerDown={markScrollFromBottom}
            onClick={(e) => {
              if (isSameTarget("/dashboard")) {
                e.preventDefault();
                scrollToTop(prefersReducedMotion ? "auto" : "smooth");
              }
            }}
            style={{ gap: isMobile ? "8px" : "10px" }}
          >
            <div
              className="flex items-center justify-center rounded-full bg-white shadow-[0_0_8px_rgba(0,0,0,0.13)]"
              style={{
                width: `${logoWrapSize}px`,
                height: `${logoWrapSize}px`,
              }}
            >
              <img
                src={guuLogo}
                alt={t("navigation:brandAlt")}
                width={logoImgSize}
                height={logoImgSize}
                className="object-contain"
                loading="eager"
                decoding="async"
              />
            </div>
            <span
              className="whitespace-nowrap font-extrabold tracking-wide text-white"
              style={{ fontSize: titleFont }}
            >
              {t("navigation:brandName")}
            </span>
          </Link>

          {isMobile ? (
            <div className="ml-auto flex items-center gap-1.5">
              <MessengerButton />
              <NotificationsBell />
              {isAuth && user && !loading ? (
                <SmartImage
                  srcRaw={hasAvatar ? avatarSource : avatarFallback}
                  cacheV={hasAvatar ? avatarCacheV : undefined}
                  fallback={avatarFallback}
                  alt={profileAlt}
                  title={profileTitle}
                  className="block cursor-pointer rounded-full border border-[#d7d7d7] bg-white object-cover"
                  style={{
                    width: avatarSize,
                    height: avatarSize,
                  }}
                  onClick={() => go("/profile")}
                />
              ) : (
                <Skeleton
                  variant="circular"
                  width={avatarSize}
                  height={avatarSize}
                  sx={{ bgcolor: "rgba(255,255,255,0.32)" }}
                  aria-hidden="true"
                />
              )}
              <button
                type="button"
                className="burger-btn flex shrink-0 cursor-pointer items-center justify-center rounded-xl border border-white/18 bg-gradient-to-b from-white/12 to-white/5 p-0 text-white/92 shadow-[inset_0_1px_0_rgba(255,255,255,0.24)] backdrop-blur-md backdrop-saturate-150"
                style={{
                  width: burgerBtnSize,
                  height: burgerBtnSize,
                  minWidth: burgerBtnSize,
                  minHeight: burgerBtnSize,
                }}
                onClick={() => setMobileMenu((v) => !v)}
                aria-label={
                  mobileMenu
                    ? t("navigation:aria.closeMenu")
                    : t("navigation:aria.openMenu")
                }
                aria-expanded={mobileMenu}
                aria-controls="mobile-drawer"
                ref={burgerBtnRef}
              >
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  className="overflow-visible"
                >
                  <line
                    x1="4"
                    y1="8"
                    x2="20"
                    y2="8"
                    style={{
                      transformOrigin: "12px 8px",
                      transform: mobileMenu
                        ? "translateY(4px) rotate(45deg)"
                        : "translateY(0) rotate(0)",
                      transition: "transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                    }}
                  />
                  <line
                    x1="4"
                    y1="12"
                    x2="20"
                    y2="12"
                    style={{
                      opacity: mobileMenu ? 0 : 1,
                      transition: "opacity 0.2s ease-in-out",
                    }}
                  />
                  <line
                    x1="4"
                    y1="16"
                    x2="20"
                    y2="16"
                    style={{
                      transformOrigin: "12px 16px",
                      transform: mobileMenu
                        ? "translateY(-4px) rotate(-45deg)"
                        : "translateY(0) rotate(0)",
                      transition: "transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                    }}
                  />
                </svg>
              </button>
            </div>
          ) : (
            <ul className="ml-9 flex flex-1 flex-row flex-wrap items-center gap-2 m-0 p-0 min-w-0 list-none text-[1.03rem] font-medium">
              {menuLinks.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={`menu-link${isActive(item.to) ? " active" : ""}`}
                    onPointerDown={markScrollFromBottom}
                    onClick={(e) => {
                      if (isSameTarget(item.to)) {
                        e.preventDefault();
                        scrollToTop(prefersReducedMotion ? "auto" : "smooth");
                      }
                    }}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {!isMobile && loading ? (
            <div className="ml-2 flex items-center gap-2.5" aria-hidden="true">
              <Skeleton
                variant="circular"
                width={36}
                height={36}
                sx={{ bgcolor: "rgba(255,255,255,0.25)" }}
              />
              <Skeleton
                variant="rectangular"
                width={96}
                height={18}
                sx={{ borderRadius: 1, bgcolor: "rgba(255,255,255,0.25)" }}
              />
              <Skeleton
                variant="circular"
                width={32}
                height={32}
                sx={{ bgcolor: "rgba(255,255,255,0.25)" }}
              />
            </div>
          ) : (
            !isMobile &&
            isAuth &&
            user && (
              <div className="ml-2 flex min-w-0 items-center gap-2.5 whitespace-nowrap">
                <MessengerButton />
                <NotificationsBell />
                <SmartImage
                  srcRaw={hasAvatar ? avatarSource : avatarFallback}
                  cacheV={hasAvatar ? avatarCacheV : undefined}
                  fallback={avatarFallback}
                  alt={profileAlt}
                  title={profileTitle}
                  className="block h-9 w-9 cursor-pointer rounded-full border-[1.5px] border-[#ccc] bg-white object-cover"
                  onClick={() => go("/profile")}
                />
                <button
                  type="button"
                  onClick={() => go("/profile")}
                  aria-label={profileTitle}
                  title={profileTitle}
                  className="cursor-pointer border-none bg-transparent p-0 m-0 font-semibold text-white font-[family-name:var(--font-ui)] tracking-[var(--ls-ui)] leading-[var(--lh-ui)]"
                  style={{ fontSize: rightNameFont }}
                >
                  {user.full_name}
                </button>
                <button
                  type="button"
                  className="menu-btn-settings"
                  onClick={() => go("/settings")}
                  aria-label={t("navigation:menu.settings")}
                  title={t("navigation:menu.settings")}
                >
                  <SettingsIcon
                    style={{
                      fontSize: "20px",
                      opacity: 0.9,
                    }}
                  />
                </button>
              </div>
            )
          )}
        </div>
      </nav>

      {isMobile && (
        <MobileMenu
          isOpen={mobileMenu}
          onClose={() => setMobileMenu(false)}
          menuLinks={menuLinks}
          isActive={isActive}
          go={go}
          user={user}
          isAuth={!!isAuth}
          prefersReducedMotion={prefersReducedMotion}
          drawerTrapRef={drawerTrapRef}
        />
      )}
    </>
  );
};

export default Navbar;
