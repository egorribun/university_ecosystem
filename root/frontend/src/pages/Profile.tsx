import { useAuth, currentUserQueryKey } from "../contexts/AuthContext";
import React, { useEffect, useMemo, useState, useRef, useCallback, memo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import api from "../api/client";
import type { User } from "@/types/User";
import profileBg from "../assets/background.jpg";
import guuLogo from "../assets/guu_logo.png";
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders";
const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL;
import PageFadeIn from "../components/PageFadeIn";
import {
  Avatar,
  Typography,
  Box,
  Paper,
  Stack,
  CircularProgress,
  IconButton,
  Snackbar,
  Chip,
  Alert,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Container,
  Divider,
  Fade,
  Grow
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EmailIcon from "@mui/icons-material/Email";
import TelegramIcon from "@mui/icons-material/Telegram";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha, useTheme } from "@mui/material/styles";
import { keyframes } from "@mui/system";
import { QRCodeSVG } from "qrcode.react";
import { motion, useReducedMotion } from "framer-motion";
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying";
import type { NowPlaying } from "@/types/spotify";
import { addVersionParam, resolveMediaUrl } from "@/utils/media";
import { useTranslation } from "react-i18next";

const auraPulse = keyframes`
  0% { box-shadow: 0 0 0 0 rgba(255,255,255,.18); }
  50% { box-shadow: 0 0 0 14px rgba(255,255,255,.03); }
  100% { box-shadow: 0 0 0 0 rgba(255,255,255,.02); }
`;
const chipHighlight = keyframes`
  0% { border-color: rgba(255,255,255,.18); }
  50% { border-color: rgba(255,255,255,.34); }
  100% { border-color: rgba(255,255,255,.18); }
`;
const onlinePulse = keyframes`
  0% { transform: scale(1); opacity: .6; }
  70% { transform: scale(1.8); opacity: 0; }
  100% { transform: scale(1.8); opacity: 0; }
`;

const MotionPaper = motion.create(Paper);
const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test";

type SnackKey = "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error";

type SnackState = {
  key?: SnackKey;
  message?: string;
  sev?: "success" | "info" | "warning" | "error";
};

export const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const theme = useTheme();
  const prefersReduce = useMediaQuery("(prefers-reduced-motion: reduce)");
  const reduced = useReducedMotion();
  const isDark = theme.palette.mode === "dark";
  const borderCol = isDark ? alpha(theme.palette.common.white, 0.14) : alpha(theme.palette.common.black, 0.12);
  const textSecondary = theme.palette.text.secondary;
  const duration = data.duration_ms ?? 0;
  const { t } = useTranslation(["profile"]);

  const clampProgress = useCallback(
    (value: number | null | undefined) => {
      if (value == null) return 0;
      if (!Number.isFinite(value)) return 0;
      if (!duration || duration <= 0) return Math.max(0, value);
      return Math.min(Math.max(0, value), duration);
    },
    [duration]
  );

  const initialProgress = clampProgress(data.progress_ms);
  const [progress, setProgress] = useState<number>(() => initialProgress);
  const startRef = useRef<number>(Date.now() - initialProgress);
  const rafRef = useRef<number | null>(null);
  const prevTrackIdRef = useRef<string | null>(data.track_id ?? null);
  const prevProgressRef = useRef<number>(initialProgress);
  const prevIsPlayingRef = useRef<boolean>(data.is_playing);

  useEffect(() => {
    const next = clampProgress(data.progress_ms);
    const trackChanged = (data.track_id ?? null) !== prevTrackIdRef.current;
    const progressChanged = next !== prevProgressRef.current;
    const resumed = data.is_playing && !prevIsPlayingRef.current;

    if (trackChanged) {
      prevTrackIdRef.current = data.track_id ?? null;
    }

    if (progressChanged) {
      prevProgressRef.current = next;
    }

    if (trackChanged || progressChanged || resumed) {
      startRef.current = Date.now() - next;
      setProgress(next);
    }

    prevIsPlayingRef.current = data.is_playing;
  }, [clampProgress, data.is_playing, data.progress_ms, data.track_id]);

  useEffect(() => {
    if (data.is_playing) return;
    const next = clampProgress(data.progress_ms);
    startRef.current = Date.now() - next;
    setProgress((prev) => (prev === next ? prev : next));
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, [clampProgress, data.is_playing, data.progress_ms]);

  const shouldAnimate = !isTest && data.is_playing && !prefersReduce && !reduced && duration > 0;

  useEffect(() => {
    if (!shouldAnimate) {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      return;
    }
    const loop = () => {
      const elapsed = Date.now() - startRef.current;
      setProgress(clampProgress(elapsed));
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [clampProgress, shouldAnimate]);

  const pct = duration > 0 ? Math.max(0, Math.min(100, (progress / duration) * 100)) : 0;
  const fmt = (ms: number | null | undefined) => {
    if (ms == null) return "0:00";
    const seconds = Math.max(0, Math.floor(ms / 1000));
    const minutes = Math.floor(seconds / 60);
    const rest = String(seconds % 60).padStart(2, "0");
    return `${minutes}:${rest}`;
  };

  const href = data.track_url || "https://open.spotify.com";

  return (
    <Box
      component="a"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={
        data.track_name
          ? t("profile:nowPlaying.openSpotifyWithTrack", { track: data.track_name })
          : t("profile:nowPlaying.openSpotify")
      }
      sx={{ display: "block", textDecoration: "none", width: "100%" }}
    >
      <MotionPaper
        elevation={0}
        className="nowplaying--spotify"
        initial={isTest || prefersReduce || reduced ? false : { y: 12, opacity: 0.94, scale: 1 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        whileHover={prefersReduce || reduced ? {} : { y: -1, scale: 1.002 }}
        whileTap={prefersReduce || reduced ? {} : { scale: 0.997 }}
        transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 36, mass: 0.9 }}
        sx={{
          width: "100%",
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          alignItems: "center",
          columnGap: 2,
          rowGap: 1,
          px: 2,
          py: 1.8,
          borderRadius: 3,
          position: "relative",
          overflow: "hidden",
          border: `1px solid ${borderCol}`,
          textDecoration: "none",
          ["--glass-alpha" as any]: ".018",
          ["--glass-highlight" as any]: "rgba(255,255,255,0)"
        }}
      >
        <Box
          sx={{
            position: "relative",
            width: 56,
            height: 56,
            borderRadius: 2,
            overflow: "hidden",
            boxShadow: `0 8px 20px ${alpha(theme.palette.common.black, isDark ? 0.35 : 0.18)}`
          }}
        >
        <Avatar
          src={data.album_image_url ?? ""}
          variant="rounded"
          alt={data.album_name || data.track_name || t("profile:nowPlaying.albumFallback")}
          imgProps={{ loading: "lazy", decoding: "async", referrerPolicy: "no-referrer" }}
          sx={{
            width: "100%",
            height: "100%",
            borderRadius: 2,
              transform: prefersReduce || reduced ? "none" : "scale(1.012)",
              transition:
                prefersReduce || reduced ? "none" : "transform 900ms cubic-bezier(.22,.61,.36,1)",
              "&:hover": prefersReduce || reduced ? undefined : { transform: "scale(1.02)" }
            }}
          />
        </Box>
        <Box sx={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 0.75 }} aria-live="polite">
          <Typography
            className="np-title"
            variant="body1"
            sx={{ fontWeight: 800, lineHeight: 1.2, letterSpacing: "-.01em" }}
          >
            {data.track_name || "—"}
          </Typography>
          <Typography className="np-art" variant="body2" sx={{ opacity: 0.9 }}>
            {data.artists.join(", ")}
          </Typography>
          {!data.is_playing && (
            <Chip
              size="small"
              label={t("profile:nowPlaying.paused")}
              color="default"
              sx={{ alignSelf: "flex-start", textTransform: "uppercase", fontWeight: 700 }}
              aria-hidden
            />
          )}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
            <LinearProgress
              className="progress"
              variant="determinate"
              value={pct}
              aria-label={t("profile:nowPlaying.progress")}
              sx={{ flex: 1, height: 6, borderRadius: 999 }}
            />
            <Typography className="np-time" variant="caption" sx={{ color: textSecondary, whiteSpace: "nowrap" }}>
              {fmt(progress)} / {fmt(duration)}
            </Typography>
          </Box>
        </Box>
      </MotionPaper>
    </Box>
  );
});


const DetailRow = ({ label, value }: { label: string; value?: React.ReactNode }) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  if (value == null || value === "") return null;
  return (
    <Box
      className="glass"
      sx={{
        display: "grid",
        gridTemplateColumns: "14px 1fr",
        alignItems: "center",
        gap: 1.2,
        px: 1.2,
        py: 1.1,
        minHeight: 44,
        borderRadius: 2,
        border: `1px solid ${isDark ? alpha(theme.palette.common.white, 0.12) : alpha(theme.palette.common.black, 0.1)}`,
        ["--glass-alpha" as any]: ".016",
        ["--glass-highlight" as any]: "rgba(255,255,255,0)"
      }}
    >
      <Box
        sx={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          bgcolor: theme.palette.info.main,
          boxShadow: `0 0 0 3px ${alpha(theme.palette.info.main, 0.22)}`,
          justifySelf: "center"
        }}
      />
      <Typography sx={{ lineHeight: 1.25 }}>
        <b>{label}:</b> {value}
      </Typography>
    </Box>
  );
};

export default function Profile() {
  const { user, loading, setUser } = useAuth();
  const theme = useTheme();
  const [snack, setSnack] = useState<SnackState | null>(null);
  const [avatarVersion, setAvatarVersion] = useState(Date.now());
  const [coverVersion, setCoverVersion] = useState(Date.now());
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const isTwoCol = useMediaQuery("(min-width:1400px)");
  const isMobile = useMediaQuery("(max-width:600px)");
  const reduced = useReducedMotion();
  const { t } = useTranslation(["profile", "common"]);
  const [scrollY, setScrollY] = useState(0);
  const [qrOpen, setQrOpen] = useState(false);
  const [achOpen, setAchOpen] = useState<{ name: string; issuer?: string; date?: string; url?: string } | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const confettiRef = useRef<HTMLCanvasElement | null>(null);
  const ldJsonRef = useRef<HTMLScriptElement | null>(null);
  const queryClient = useQueryClient();
  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected);
  const nowPlayingQuery = useNowPlaying(spotifyConnected);
  const { refetch: refetchNowPlaying } = nowPlayingQuery;
  const nowPlaying = nowPlayingQuery.data ?? null;
  const prevSpotifyConnectedRef = useRef(spotifyConnected);
  const showNowPlaying = Boolean(
    spotifyConnected &&
      nowPlaying &&
      (nowPlaying.track_id || nowPlaying.track_name || nowPlaying.artists.length > 0)
  );
  const location = useLocation();
  const navigate = useNavigate();

  const [edit, setEdit] = useState(false);
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [about, setAbout] = useState(user?.about || "");
  const [recordBookNumber, setRecordBookNumber] = useState(user?.record_book_number || "");
  const [status, setStatus] = useState(user?.status || "");
  const [institute, setInstitute] = useState(user?.institute || "");
  const [course, setCourse] = useState(user?.course || "");
  const [educationLevel, setEducationLevel] = useState(user?.education_level || "");
  const [track, setTrack] = useState(user?.track || "");
  const [program, setProgram] = useState(user?.program || "");
  const [telegram, setTelegram] = useState(user?.telegram || "");
  const [achievements, setAchievements] = useState(user?.achievements || "");
  const [department, setDepartment] = useState(user?.department || "");
  const [position, setPosition] = useState(user?.position || "");
  const [saving, setSaving] = useState(false);

  const initEditFields = useCallback(() => {
    setFullName(user?.full_name || "");
    setEmail(user?.email || "");
    setAbout(user?.about || "");
    setRecordBookNumber(user?.record_book_number || "");
    setStatus(user?.status || "");
    setInstitute(user?.institute || "");
    setCourse(user?.course || "");
    setEducationLevel(user?.education_level || "");
    setTrack(user?.track || "");
    setProgram(user?.program || "");
    setTelegram(user?.telegram || "");
    setAchievements(user?.achievements || "");
    setDepartment(user?.department || "");
    setPosition(user?.position || "");
  }, [user]);

  useEffect(() => {
    const sp = new URLSearchParams(location.search);
    const wantsEdit = sp.get("edit") === "1" || location.pathname.endsWith("/edit");
    if (wantsEdit && !edit) {
      initEditFields();
      setEdit(true);
    }
    if (!wantsEdit && edit) setEdit(false);
  }, [location.pathname, location.search, edit, initEditFields]);

  useEffect(() => {
    const onScroll = () => setScrollY(window.scrollY || 0);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const coverParallax = reduceMotion ? 0 : Math.min(scrollY * 0.1, 40);
  const coverScale = reduceMotion ? 1 : Math.min(1 + scrollY * 0.00014, 1.04);

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const s = sp.get("spotify");
    if (s !== null) {
      if (s !== "error") {
        void queryClient.invalidateQueries({ queryKey: currentUserQueryKey });
        void queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey });
        void refetchNowPlaying({ throwOnError: false });
        setSnack({ key: "spotifyConnected", sev: "success" });
      } else {
        setSnack({ key: "spotifyError", sev: "error" });
      }
      sp.delete("spotify");
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "");
      window.history.replaceState({}, "", next);
    }
  }, [queryClient, refetchNowPlaying]);

  useEffect(() => {
    if (spotifyConnected && !prevSpotifyConnectedRef.current) {
      void refetchNowPlaying({ throwOnError: false });
    }
    prevSpotifyConnectedRef.current = spotifyConnected;
  }, [spotifyConnected, refetchNowPlaying]);

  useEffect(() => {
    if (!user) return;
    const elPrev = ldJsonRef.current;
    if (elPrev && elPrev.parentNode) elPrev.parentNode.removeChild(elPrev);
    const el = document.createElement("script");
    el.type = "application/ld+json";
    el.setAttribute("data-profile-ldjson", "1");
    el.text = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Person",
      name: user.full_name || "",
      email: user.email || "",
      jobTitle: user.role === "teacher" ? user.position || "" : user.role === "student" ? "Student" : "Administrator",
      affiliation: user.institute || user.department || "",
      url: typeof window !== "undefined" ? window.location.href : "",
      image: (() => {
        const media = resolveMediaUrl(user.avatar_url ?? undefined);
        return media ? addVersionParam(media, avatarVersion) : "";
      })()
    });
    document.head.appendChild(el);
    ldJsonRef.current = el;
    return () => {
      const node = ldJsonRef.current;
      if (node && node.parentNode) node.parentNode.removeChild(node);
      ldJsonRef.current = null;
    };
  }, [user, avatarVersion]);

  if (loading)
    return (
      <Box minHeight="70vh" display="flex" alignItems="center" justifyContent="center">
        <CircularProgress />
      </Box>
    );

  const avatarImageUrl = useMemo(() => {
    const media = resolveMediaUrl(user?.avatar_url ?? undefined);
    return media ? addVersionParam(media, avatarVersion) : DEFAULT_AVATAR;
  }, [user?.avatar_url, avatarVersion]);

  const coverImageUrl = useMemo(() => {
    const media = resolveMediaUrl(user?.cover_url ?? undefined);
    return media ? addVersionParam(media, coverVersion) : profileBg;
  }, [user?.cover_url, coverVersion]);

  const handleAvatarImgError = useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    img.onerror = null;
    img.src = DEFAULT_AVATAR;
  }, []);

  const ensureConfettiSize = useCallback(() => {
    const canvas = confettiRef.current;
    if (!canvas) return { dpr: 1, w: window.innerWidth, h: window.innerHeight };
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const w = Math.max(1, window.innerWidth);
    const h = Math.max(1, window.innerHeight);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    return { dpr, w, h };
  }, []);

  useEffect(() => {
    const onResize = () => ensureConfettiSize();
    ensureConfettiSize();
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
    };
  }, [ensureConfettiSize]);

  const burstConfetti = useCallback(
    (x?: number, y?: number) => {
      const canvas = confettiRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const { dpr, w, h } = ensureConfettiSize();
      const cx = x != null ? x * dpr : (w * dpr) / 2;
      const cy = y != null ? y * dpr : (h * dpr) / 5;
      const count = 120;
      const parts = Array.from({ length: count }).map((_, i) => {
        const angle = Math.random() * Math.PI - Math.PI / 2;
        const speed = 3 + Math.random() * 6;
        const hue = Math.floor((i / count) * 360);
        return { x: cx, y: cy, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed - 2, life: 56 + Math.random() * 36, size: 2 + Math.random() * 3, color: `hsl(${hue} 90% 55%)` };
      });
      let raf = 0;
      const step = () => {
        const context = ctx;
        context.clearRect(0, 0, canvas.width, canvas.height);
        parts.forEach((p) => {
          p.vy += 0.12 * dpr;
          p.x += p.vx * dpr;
          p.y += p.vy * dpr;
          p.life -= 1;
          context.fillStyle = p.color;
          context.beginPath();
          context.arc(p.x, p.y, p.size * dpr, 0, Math.PI * 2);
          context.fill();
        });
        for (let i = parts.length - 1; i >= 0; i--) if (parts[i].life <= 0) parts.splice(i, 1);
        if (parts.length > 0) raf = requestAnimationFrame(step);
        else cancelAnimationFrame(raf);
      };
      step();
    },
    [ensureConfettiSize]
  );

  useEffect(() => {
    if (snack && snack.sev === "success" && snack.key !== "copied") burstConfetti();
  }, [snack, burstConfetti]);

  const copy = async (text: string, evt?: { clientX: number; clientY: number }) => {
    try {
      await navigator.clipboard?.writeText(text);
    } finally {
      setSnack({ key: "copied", sev: "success" });
      if (evt) burstConfetti(evt.clientX, evt.clientY);
    }
  };

  const buildVCard = useCallback(() => {
    const u = user!;
    const lines = [
      "BEGIN:VCARD",
      "VERSION:4.0",
      `FN:${u.full_name || ""}`,
      u.email ? `EMAIL:${u.email}` : "",
      u.institute || u.department ? `ORG:${u.institute || u.department}` : "",
      u.position || u.status ? `TITLE:${u.position || u.status}` : "",
      typeof window !== "undefined" ? `URL:${window.location.href}` : ""
    ].filter(Boolean);
    lines.push("END:VCARD");
    return lines.join("\r\n");
  }, [user]);

  const openQrModal = useCallback(() => setQrOpen(true), []);
  const closeQrModal = useCallback(() => setQrOpen(false), []);

  const telegramHref = useMemo(() => {
    const t = user?.telegram || "";
    if (!t) return "";
    let v = String(t).trim();
    if (v.startsWith("http")) return v;
    if (v.startsWith("@")) v = v.slice(1);
    return `https://t.me/${v}`;
  }, [user?.telegram]);

  const achievementsList = useMemo(
    () =>
      String(user?.achievements || "")
        .split(/[,;\n]/)
        .map((str) => String(str || "").trim())
        .filter(Boolean)
        .map((raw, index) => {
          const [name, issuer, date, url] = raw.split("|").map((s) => s.trim());
          return { key: `${raw}-${index}`, name, issuer, date, url };
        }),
    [user?.achievements]
  );

  const avatarPx = useMemo(() => {
    if (isMobile) return 132;
    return isTwoCol ? 188 : 168;
  }, [isMobile, isTwoCol]);
  const avatarSize = `${avatarPx}px`;
  const avatarFloat = Math.round(avatarPx * 0.55);
  const heroPaddingBottom = `${Math.max(avatarFloat - 12, 28)}px`;
  const heroTextPaddingTop = `${Math.round(avatarPx * 0.65)}px`;
  const isDark = theme.palette.mode === "dark";
  const textSecondary = theme.palette.text.secondary;
  const isOnline = ((user as any)?.is_online ?? (user as any)?.online ?? true) as boolean;
  const statusSize = useMemo(() => Math.max(12, Math.round(avatarPx * 0.16)), [avatarPx]);
  const statusOffset = useMemo(() => Math.max(6, Math.round(avatarPx * 0.08)), [avatarPx]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.put<User>("/users/me", {
        full_name: fullName,
        email,
        about,
        record_book_number: recordBookNumber,
        status,
        institute,
        course,
        education_level: educationLevel,
        track,
        program,
        telegram,
        achievements,
        department,
        position
      });
      setUser(res.data);
      setEdit(false);
      navigate("/profile", { replace: true });
      setSnack({ key: "profileUpdated", sev: "success" });
      setAvatarVersion(Date.now());
      setCoverVersion(Date.now());
    } catch (e: any) {
      let messageKey: SnackKey | undefined = "error";
      let messageText: string | undefined;
      if (e?.response?.data?.detail) {
        if (typeof e.response.data.detail === "string") {
          messageKey = undefined;
          messageText = e.response.data.detail;
        } else if (Array.isArray(e.response.data.detail)) {
          messageKey = undefined;
          messageText = e.response.data.detail.map((err: any) => err.msg).join("; ");
        }
      }
      setSnack({ key: messageKey, message: messageText, sev: "error" });
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEdit(false);
    navigate("/profile", { replace: true });
  };

  const snackMessage = snack?.key ? t(`profile:snackbar.${snack.key}`) : snack?.message || "";

  return (
    <>
      <Box
        sx={{
          position: "fixed",
          inset: 0,
          zIndex: -2,
          backgroundImage: `url(${profileBg})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundAttachment: "fixed",
          "&::before": {
            content: '""',
            position: "absolute",
            inset: 0,
            background: `linear-gradient(120deg, ${alpha(theme.palette.primary.dark, 0.66)}, ${alpha(theme.palette.secondary.dark, 0.6)})`,
            mixBlendMode: "multiply"
          },
          "&::after": {
            content: '""',
            position: "absolute",
            inset: 0,
            background: `radial-gradient(1600px 800px at 50% 0%, ${alpha(theme.palette.primary.light, 0.08)} 0%, transparent 60%)`,
            opacity: 0.6
          }
        }}
      />

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduceMotion ? 1 : 0.96, y: reduceMotion ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          <Box
            component="main"
            id="main"
            className="profile-page"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
            sx={{ position: "relative", minHeight: "100svh", display: "flex", flexDirection: "column", py: { xs: 8, sm: 9, md: 10 }, px: { xs: 1.5, sm: 2, md: 3 } }}
          >
          <Container maxWidth="xl" sx={{ position: "relative", zIndex: 0 }}>
            <MotionPaper
              ref={containerRef}
              className="glass profile-card"
              initial={isTest ? false : { opacity: reduced ? 1 : 0.98, y: reduced ? 0 : 10, scale: 1 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 34, mass: 0.9 }}
              sx={{
                px: { xs: 2.6, sm: 3.6, md: 4.6, lg: 5.6 },
                py: { xs: 3.6, sm: 4.2, md: 5 },
                borderRadius: { xs: 3, md: 4 },
                position: "relative",
                overflow: "hidden",
                ["--glass-alpha" as any]: ".02",
                ["--glass-highlight" as any]: "rgba(255,255,255,0)"
              }}
            >
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: { xs: "1fr", md: "minmax(360px, 420px) minmax(0, 1fr)" },
                  columnGap: { xs: 3, sm: 4, md: 6 },
                  rowGap: { xs: 4, md: 0 },
                  alignItems: "start"
                }}
              >
                <Stack spacing={{ xs: 3.2, md: 4 }} alignItems="stretch">
                  <Box
                    className="glass"
                    sx={{
                      position: "relative",
                      borderRadius: { xs: 3, md: 4 },
                      overflow: "hidden",
                      minHeight: { xs: 300, sm: 340, md: 360, lg: 400 },
                      display: "flex",
                      alignItems: "flex-end",
                      justifyContent: "center",
                      pb: heroPaddingBottom,
                      boxShadow: `0 28px 70px -44px ${alpha(theme.palette.common.black, isDark ? 0.58 : 0.2)}`,
                      ["--glass-alpha" as any]: ".018",
                      ["--glass-highlight" as any]: "rgba(255,255,255,0)"
                    }}
                  >
                    <Box
                      sx={{
                        position: "absolute",
                        inset: 0,
                        backgroundImage: coverImageUrl ? `url(${coverImageUrl})` : undefined,
                        backgroundPosition: "center",
                        backgroundSize: "cover",
                        transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                        transition: reduceMotion ? "none" : "transform 1200ms cubic-bezier(.33,1,.68,1)",
                        filter: "saturate(1) contrast(1.02) brightness(0.98)"
                      }}
                    />
                    <Box sx={{ position: "absolute", inset: 0, background: "linear-gradient(185deg, rgba(6,9,20,0) 40%, rgba(6,9,20,0.9) 100%)" }} />
                    <Box
                      sx={{
                        position: "absolute",
                        left: "50%",
                        top: { xs: theme.spacing(6), sm: theme.spacing(7) },
                        transform: "translateX(-50%)",
                        width: avatarSize,
                        height: avatarSize,
                        borderRadius: "50%",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        p: "4px",
                        animation: reduceMotion ? "none" : `${auraPulse} 14s ease-in-out infinite`
                      }}
                    >
                      <Box className="avatar-ring" sx={{ width: "100%", height: "100%" }}>
                        <Avatar
                          src={avatarImageUrl}
                          alt={user?.full_name ?? undefined}
                          imgProps={{
                            onError: handleAvatarImgError,
                            loading: "lazy",
                            decoding: "async",
                            referrerPolicy: "no-referrer",
                          }}
                          sx={{
                            width: "100%",
                            height: "100%",
                            borderRadius: "50%",
                            fontSize: "clamp(28px, 6vw, 64px)",
                            backgroundColor: alpha(theme.palette.common.white, 0.12),
                            color: alpha(theme.palette.common.white, 0.92)
                          }}
                        >
                          {user?.full_name?.[0]}
                        </Avatar>
                      </Box>

                      {isOnline && (
                        <Box
                          sx={{
                            position: "absolute",
                            right: `${statusOffset}px`,
                            bottom: `${statusOffset}px`,
                            width: `${statusSize}px`,
                            height: `${statusSize}px`,
                            borderRadius: "50%",
                            backgroundColor: "#22c55e",
                            boxShadow: `0 0 0 2px rgba(0,0,0,.18), 0 4px 10px rgba(34,197,94,.45)`,
                            zIndex: 3,
                            pointerEvents: "none"
                          }}
                        >
                          {!reduced && (
                            <Box
                              sx={{
                                position: "absolute",
                                inset: "-6px",
                                borderRadius: "50%",
                                border: `2px solid ${alpha("#22c55e", 0.45)}`,
                                animation: `${onlinePulse} 1.8s ease-in-out infinite`
                              }}
                            />
                          )}
                        </Box>
                      )}
                    </Box>
                    <Box
                      sx={{
                        position: "relative",
                        zIndex: 2,
                        width: "100%",
                        textAlign: { xs: "center", md: "left" },
                        px: { xs: 2.4, sm: 3, md: 3.4 },
                        pt: heroTextPaddingTop,
                        display: "flex",
                        flexDirection: "column",
                        gap: 2.4
                      }}
                    >
                      <Box>
                        <Typography
                          className="profile-name"
                          variant="h3"
                          component="h1"
                          data-testid="profile-name"
                          sx={{ fontSize: "clamp(1.7rem, 3.2vw, 2.9rem)", fontWeight: 900, lineHeight: 1.08 }}
                        >
                          {user!.full_name}
                        </Typography>
                        {!!user?.position && user?.role === "teacher" && (
                          <Typography className="profile-subtitle" variant="subtitle1" sx={{ mt: 0.9, fontWeight: 600 }}>
                            {user.position}
                          </Typography>
                        )}
                      </Box>
                      <Stack direction="row" spacing={1.2} useFlexGap flexWrap="wrap" sx={{ justifyContent: { xs: "center", md: "flex-start" } }}>
                        {[ 
                          user!.role === "teacher"
                            ? t("profile:chips.teacher")
                            : user!.role === "student"
                            ? t("profile:chips.student")
                            : t("profile:chips.admin"),
                          ...(user!.role === "student" && user!.course
                            ? [t("profile:chips.course", { value: user!.course })]
                            : []),
                          ...(user!.institute ? [user!.institute] : [])
                        ].map((chip, idx) => (
                          <Grow in key={`${chip}-${idx}`} timeout={isTest || reduced ? 0 : 560} style={{ transitionDelay: reduced ? "0ms" : `${idx * 90}ms` }}>
                            <Chip
                              size="small"
                              label={chip}
                              className="glass--chip"
                              sx={{
                                borderRadius: 999,
                                "& .MuiChip-label": { px: 1.6, py: 0.62, lineHeight: 1.28, fontWeight: 700, letterSpacing: ".01em" },
                                animation: reduced ? "none" : `${chipHighlight} 12s ease-in-out infinite`,
                                animationDelay: reduced ? "0ms" : `${idx * 90}ms`
                              }}
                            />
                          </Grow>
                        ))}
                      </Stack>
                    </Box>
                  </Box>

                  <Paper
                    elevation={0}
                    className="glass profile-card"
                    sx={{
                      p: { xs: 2.6, sm: 3 },
                      borderRadius: 3,
                      display: "flex",
                      flexDirection: "column",
                      gap: { xs: 2.6, md: 3 },
                      ["--glass-alpha" as any]: ".02",
                      ["--glass-highlight" as any]: "rgba(255,255,255,0)"
                    }}
                  >
                    <Stack spacing={1.3} alignItems="stretch">
                      <Button
                        size="large"
                        variant="contained"
                        color="secondary"
                        className="glass--btn"
                        onClick={openQrModal}
                        data-testid="open-qr"
                        sx={{ width: "100%", borderRadius: 2, py: 1.05, fontWeight: 800, letterSpacing: 0.24 }}
                      >
                        {t("profile:buttons.showQr")}
                      </Button>
                    </Stack>
                    <Divider />
                    <Stack spacing={1.8} className="contact-links">
                      <Stack direction="row" spacing={1.4} alignItems="center" sx={{ justifyContent: "space-between", flexWrap: "wrap" }}>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
                          <EmailIcon aria-hidden sx={{ fontSize: 22 }} />
                          <Typography sx={{ fontWeight: 800, wordBreak: "break-word", flex: 1 }}>
                            <a href={`mailto:${user!.email}`} style={{ color: "inherit", textDecoration: "none" }} data-testid="profile-email-link" title="Email">
                              {user!.email}
                            </a>
                          </Typography>
                        </Stack>
                        <IconButton
                          size="small"
                          className="glass--btn"
                          onClick={(e) => copy(user!.email, e)}
                          aria-label={t("profile:aria.copyEmail")}
                          title={t("profile:aria.copyEmail")}
                          data-testid="copy-email"
                          sx={{
                            transition: reduced ? "color 140ms ease" : "transform 200ms ease, box-shadow 200ms ease, color 200ms ease",
                            "&:hover": { transform: reduced ? "none" : "translateY(-1px) scale(1.05)" }
                          }}
                        >
                          <ContentCopyIcon fontSize="small" />
                        </IconButton>
                      </Stack>

                      {!!user!.telegram && (
                        <Stack direction="row" spacing={1.4} alignItems="center" sx={{ justifyContent: "space-between", flexWrap: "wrap" }}>
                          <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
                            <TelegramIcon aria-hidden sx={{ fontSize: 22 }} />
                            <Typography sx={{ fontWeight: 800, wordBreak: "break-word", flex: 1 }}>
                              <a href={telegramHref} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }} data-testid="profile-telegram-link" title="Telegram">
                                {user!.telegram}
                              </a>
                            </Typography>
                          </Stack>
                          <IconButton
                            size="small"
                            className="glass--btn"
                            onClick={(e) => copy(user!.telegram!, e)}
                            aria-label={t("profile:aria.copyTelegram")}
                            title={t("profile:aria.copyTelegram")}
                            data-testid="copy-telegram"
                            sx={{
                              transition: reduced ? "color 140ms ease" : "transform 200ms ease, box-shadow 200ms ease, color 200ms ease",
                              "&:hover": { transform: reduced ? "none" : "translateY(-1px) scale(1.05)" }
                            }}
                          >
                            <ContentCopyIcon fontSize="small" />
                          </IconButton>
                        </Stack>
                      )}
                    </Stack>
                  </Paper>

                  {showNowPlaying && nowPlaying && (
                    <Fade in timeout={isTest || reduced ? 0 : 720}>
                      <Stack spacing={1.4}>
                        <Typography variant="overline" sx={{ letterSpacing: 2.2, color: textSecondary }}>
                          {t("profile:sections.nowPlaying")}
                        </Typography>
                        <NowPlayingCard data={nowPlaying} />
                      </Stack>
                    </Fade>
                  )}
                </Stack>

                <Box sx={{ width: "100%", position: "relative", mt: { xs: `${Math.round(avatarPx * 0.55) + 36}px`, md: 0 } }}>
                  {edit ? (
                    <Paper
                      elevation={0}
                      className="glass profile-card profile-edit"
                      sx={{
                        width: "100%",
                        borderRadius: 3,
                        p: { xs: 2.6, sm: 3, md: 3.4 },
                        ["--glass-alpha" as any]: ".02",
                        ["--glass-highlight" as any]: "rgba(255,255,255,0)"
                      }}
                    >
                      <Stack spacing={2.2}>
                        <TextField label={t("profile:form.name")} value={fullName} onChange={(e) => setFullName(e.target.value)} fullWidth inputProps={{ maxLength: 120 }} />
                        <TextField label={t("profile:form.email")} value={email} onChange={(e) => setEmail(e.target.value)} fullWidth type="email" />
                        <TextField label={t("profile:form.telegram")} value={telegram} onChange={(e) => setTelegram(e.target.value)} fullWidth helperText={t("profile:form.telegramHint")} />
                        {user!.role === "teacher" && (
                          <>
                            <TextField label={t("profile:form.department")} value={department} onChange={(e) => setDepartment(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.position")} value={position} onChange={(e) => setPosition(e.target.value)} fullWidth />
                          </>
                        )}
                        {user!.role === "student" && (
                          <>
                            <TextField label={t("profile:form.about")} value={about} onChange={(e) => setAbout(e.target.value)} fullWidth multiline minRows={3} />
                            <TextField label={t("profile:form.recordBookNumber")} value={recordBookNumber} onChange={(e) => setRecordBookNumber(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.status")} value={status} onChange={(e) => setStatus(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.institute")} value={institute} onChange={(e) => setInstitute(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.course")} value={course} onChange={(e) => setCourse(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.educationLevel")} value={educationLevel} onChange={(e) => setEducationLevel(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.track")} value={track} onChange={(e) => setTrack(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.program")} value={program} onChange={(e) => setProgram(e.target.value)} fullWidth />
                            <TextField label={t("profile:form.achievements")} value={achievements} onChange={(e) => setAchievements(e.target.value)} fullWidth multiline minRows={2} />
                          </>
                        )}
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ alignItems: { xs: "stretch", sm: "center" } }}>
                          <Button onClick={handleSave} variant="contained" disabled={saving} className="glass--btn" sx={{ width: { xs: "100%", sm: "auto" }, fontWeight: 800 }}>
                            {saving ? t("profile:form.saving") : t("profile:form.save")}
                          </Button>
                          <Button onClick={handleCancel} variant="outlined" className="glass--btn" sx={{ width: { xs: "100%", sm: "auto" }, fontWeight: 800 }}>
                            {t("profile:form.cancel")}
                          </Button>
                        </Stack>
                      </Stack>
                    </Paper>
                  ) : (
                    <>
                      <Paper
                        elevation={0}
                        className="glass profile-card"
                        sx={{
                          width: "100%",
                          borderRadius: 3,
                          p: { xs: 2.6, sm: 3, md: 3.4 },
                          ["--glass-alpha" as any]: ".02",
                          ["--glass-highlight" as any]: "rgba(255,255,255,0)"
                        }}
                      >
                        <Typography variant="h5" component="h2" sx={{ fontWeight: 900, fontSize: "clamp(1.3rem, 2.3vw, 1.8rem)", mb: 2.2, letterSpacing: "-.01em" }}>
                          {t("profile:sections.details")}
                        </Typography>
                        <Accordion
                          disableGutters
                          defaultExpanded
                          className="glass"
                          sx={{
                            borderRadius: 3,
                            boxShadow: "none",
                            "&::before": { display: "none" },
                            ["--glass-alpha" as any]: ".016",
                            ["--glass-highlight" as any]: "rgba(255,255,255,0)"
                          }}
                        >
                          <AccordionSummary
                            expandIcon={<ExpandMoreIcon />}
                            sx={{ px: 2.2, py: 1.4, borderBottom: `1px solid ${isDark ? alpha(theme.palette.common.white, 0.1) : alpha(theme.palette.common.black, 0.08)}` }}
                          >
                            <Typography fontWeight={900}>{t("profile:sections.profileDetails")}</Typography>
                          </AccordionSummary>
                          <AccordionDetails sx={{ px: { xs: 1.6, sm: 2.2 }, py: { xs: 1.8, sm: 2 } }}>
                            {(() => {
                              const rows = [
                                { label: t("profile:form.about"), value: user!.about },
                                { label: t("profile:form.status"), value: user!.status },
                                { label: t("profile:form.recordBookNumber"), value: user!.record_book_number },
                                { label: t("profile:form.educationLevel"), value: user!.education_level },
                                { label: t("profile:form.track"), value: user!.track },
                                { label: t("profile:form.program"), value: user!.program },
                                { label: t("profile:form.department"), value: user!.department },
                                { label: t("profile:form.position"), value: user!.position }
                              ];
                              return (
                                <Box
                                  sx={{
                                    display: "grid",
                                    gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
                                    gap: { xs: 1.2, md: 1.6 }
                                  }}
                                >
                                  {rows.map((r) => (
                                    <DetailRow key={r.label} label={r.label} value={r.value} />
                                  ))}
                                </Box>
                              );
                            })()}
                            {achievementsList.length > 0 && (
                              <Box sx={{ mt: 2.4 }}>
                                <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 800, mb: 1.4 }}>
                                  {t("profile:sections.achievements")}
                                </Typography>
                                <Box
                                  sx={{
                                    display: "grid",
                                    gridTemplateColumns: { xs: "repeat(auto-fit, minmax(140px, 1fr))", sm: "repeat(auto-fit, minmax(160px, 1fr))" },
                                    gap: 1.2
                                  }}
                                >
                                  {achievementsList.map((ach, idx) => (
                                    <Grow in key={ach.key} timeout={isTest || reduced ? 0 : 500} style={{ transitionDelay: reduced ? "0ms" : `${idx * 90}ms` }}>
                                      <Chip
                                        label={ach.name}
                                        clickable
                                        onClick={() =>
                                          setAchOpen({
                                            name: ach.name,
                                            issuer: ach.issuer,
                                            date: ach.date,
                                            url: ach.url
                                          })
                                        }
                                        className="glass--chip"
                                        sx={{
                                          borderRadius: 2,
                                          alignSelf: "stretch",
                                          "& .MuiChip-label": { display: "block", whiteSpace: "normal", lineHeight: 1.3, px: 1.6, py: 1.1, fontWeight: 700 },
                                          animation: reduced ? "none" : `${chipHighlight} 14s ease-in-out infinite`,
                                          animationDelay: reduced ? "0ms" : `${idx * 110}ms`
                                        }}
                                      />
                                    </Grow>
                                  ))}
                                </Box>
                              </Box>
                            )}
                          </AccordionDetails>
                        </Accordion>
                      </Paper>
                    </>
                  )}
                </Box>
              </Box>
            </MotionPaper>
          </Container>

            <canvas ref={confettiRef} style={{ position: "fixed", left: 0, top: 0, width: "100vw", height: "100vh", pointerEvents: "none", zIndex: 2147483000 }} />
          </Box>
        </motion.div>
      </PageFadeIn>

      <Dialog
        open={qrOpen}
        onClose={closeQrModal}
        maxWidth="xs"
        fullWidth
        PaperProps={{
          className: "glass",
          sx: {
            borderRadius: 3,
            ["--glass-alpha" as any]: ".02",
            ["--glass-highlight" as any]: "rgba(255,255,255,0)"
          }
        }}
      >
        <DialogTitle sx={{ textAlign: "center", fontWeight: 900, letterSpacing: 0.4 }}>{t("profile:dialog.qr.title")}</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 1.2, minHeight: 320 }}>
          <Box
            sx={{
              background: "#fff",
              p: 2,
              borderRadius: 3,
              border: `1px solid ${alpha(theme.palette.primary.main, 0.15)}`,
              boxShadow: `0 18px 40px -28px ${alpha(theme.palette.common.black, 0.4)}`
            }}
          >
            <QRCodeSVG
              value={buildVCard()}
              size={300}
              level="H"
              includeMargin
              bgColor="#ffffff"
              fgColor={theme.palette.primary.dark}
              imageSettings={{
                src: typeof guuLogo === "string" ? guuLogo : String(guuLogo as any),
                height: 56,
                width: 56,
                excavate: true
              }}
            />
          </Box>
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
            {t("profile:dialog.qr.hint")}
          </Typography>
        </DialogContent>
        <DialogActions sx={{ justifyContent: "center", pb: 2 }}>
          <Button onClick={closeQrModal} className="glass--btn" variant="contained" sx={{ fontWeight: 800 }}>
            {t("common:buttons.done")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={!!achOpen}
        onClose={() => setAchOpen(null)}
        maxWidth="xs"
        fullWidth
        PaperProps={{
          className: "glass",
          sx: {
            borderRadius: 3,
            ["--glass-alpha" as any]: ".02",
            ["--glass-highlight" as any]: "rgba(255,255,255,0)"
          }
        }}
      >
        <DialogTitle sx={{ fontWeight: 900 }}>{achOpen?.name}</DialogTitle>
        <DialogContent sx={{ display: "grid", gap: 1.2 }}>
          {achOpen?.issuer && <Typography>{t("profile:dialog.achievement.organizer", { issuer: achOpen.issuer })}</Typography>}
          {achOpen?.date && <Typography>{t("profile:dialog.achievement.date", { date: achOpen.date })}</Typography>}
          {achOpen?.url && (
            <Button variant="outlined" className="glass--btn" href={achOpen.url} target="_blank" rel="noreferrer" sx={{ fontWeight: 800 }}>
              {t("profile:dialog.achievement.openLink")}
            </Button>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAchOpen(null)} className="glass--btn" variant="contained" sx={{ fontWeight: 800 }}>
            {t("profile:dialog.achievement.close")}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        autoHideDuration={2600}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        data-testid={snack?.key === "copied" ? "snackbar-copied" : undefined}
      >
        <Alert onClose={() => setSnack(null)} severity={snack?.sev || "info"} variant="filled" sx={{ width: "100%" }}>
          {snackMessage}
        </Alert>
      </Snackbar>
    </>
  );
}