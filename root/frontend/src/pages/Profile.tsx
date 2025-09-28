import { useAuth } from "../contexts/AuthContext";
import React, { useEffect, useMemo, useState, useRef, useCallback, memo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../api/axios";
import profileBg from "../assets/background.jpg";
import guuLogo from "../assets/guu_logo.png";
import {
  Avatar,
  Typography,
  Box,
  Paper,
  Stack,
  CircularProgress,
  IconButton,
  Snackbar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Tooltip,
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
  Grow,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EmailIcon from "@mui/icons-material/Email";
import TelegramIcon from "@mui/icons-material/Telegram";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import useMediaQuery from "@mui/material/useMediaQuery";
import { resolveMediaUrl } from "@/utils/media";
import { alpha, useTheme } from "@mui/material/styles";
import { keyframes } from "@mui/system";

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || "";

type QRCodeModule = {
  toDataURL: (
    text: string,
    options?: { width?: number; errorCorrectionLevel?: string; margin?: number }
  ) => Promise<string>;
};

let qrModulePromise: Promise<QRCodeModule> | null = null;
const loadQrModule = async (): Promise<QRCodeModule> => {
  if (!qrModulePromise) {
    qrModulePromise = import("qrcode")
      .then((mod) => (mod as { default?: QRCodeModule }).default ?? (mod as QRCodeModule))
      .catch((error) => {
        qrModulePromise = null;
        throw error;
      });
  }
  return qrModulePromise;
};

let jsPdfModulePromise: Promise<typeof import("jspdf")> | null = null;
const loadJsPdfModule = async () => {
  if (!jsPdfModulePromise) {
    jsPdfModulePromise = import("jspdf").catch((error) => {
      jsPdfModulePromise = null;
      throw error;
    });
  }
  return jsPdfModulePromise;
};

type NowPlaying = {
  is_playing: boolean;
  progress_ms?: number;
  duration_ms?: number;
  track_id?: string;
  track_name?: string;
  artists?: string[];
  album_name?: string;
  album_image_url?: string;
  track_url?: string;
  preview_url?: string;
  fetched_at: string | number | Date;
};

const auraPulse = keyframes`
  0% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.35); }
  50% { box-shadow: 0 0 0 18px rgba(255, 255, 255, 0.04); }
  100% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.02); }
`;

const chipHighlight = keyframes`
  0% { border-color: rgba(255, 255, 255, 0.28); }
  50% { border-color: rgba(255, 255, 255, 0.52); }
  100% { border-color: rgba(255, 255, 255, 0.28); }
`;

const shimmerEdge = keyframes`
  0% { transform: translateX(-120%); opacity: 0; }
  50% { opacity: 0.6; }
  100% { transform: translateX(140%); opacity: 0; }
`;

const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const [progress, setProgress] = useState<number>(data.progress_ms ?? 0);
  const startRef = useRef<number>(Date.now() - (data.progress_ms ?? 0));
  const rafRef = useRef<number | null>(null);
  const theme = useTheme();
  const prefersReduce = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => {
    startRef.current = Date.now() - (data.progress_ms ?? 0);
    setProgress(data.progress_ms ?? 0);
  }, [data.track_id, data.progress_ms, data.duration_ms, data.is_playing]);

  useEffect(() => {
    if (!data.is_playing || !data.duration_ms) return;
    const loop = () => {
      const p = Math.min(data.duration_ms!, Date.now() - startRef.current);
      setProgress(p);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [data.is_playing, data.duration_ms, data.track_id]);

  const pct = data.duration_ms
    ? Math.max(0, Math.min(100, (progress / data.duration_ms) * 100))
    : 0;
  const fmt = (ms?: number) => {
    if (ms == null) return "0:00";
    const s = Math.max(0, Math.floor(ms / 1000));
    const m = Math.floor(s / 60);
    const ss = String(s % 60).padStart(2, "0");
    return `${m}:${ss}`;
  };

  return (
    <Paper
      elevation={0}
      className="spotify-card nowplaying--spotify"
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
        backdropFilter: "blur(18px)",
        background: alpha(theme.palette.background.paper, 0.22),
        border: `1px solid ${alpha(theme.palette.common.white, 0.22)}`,
        boxShadow: `0 18px 32px -24px ${alpha(theme.palette.common.black, 0.6)}`,
        transition: "transform 320ms ease, box-shadow 320ms ease, border-color 320ms ease",
        willChange: "transform",
        "&:hover": prefersReduce
          ? undefined
          : {
              transform: "translateY(-4px)",
              boxShadow: `0 24px 36px -20px ${alpha(theme.palette.common.black, 0.65)}`,
              borderColor: alpha(theme.palette.primary.light, 0.45),
            },
      }}
    >
      <Box
        sx={{
          position: "relative",
          width: 64,
          height: 64,
          borderRadius: 2,
          overflow: "hidden",
          boxShadow: `0 10px 22px ${alpha(theme.palette.common.black, 0.36)}`,
        }}
      >
        <Avatar
          src={data.album_image_url || ""}
          variant="rounded"
          alt={data.album_name || data.track_name || "Обложка альбома"}
          sx={{
            width: "100%",
            height: "100%",
            borderRadius: 2,
            transform: prefersReduce ? "none" : "scale(1.02)",
            transition: prefersReduce ? "none" : "transform 1.4s ease",
            "&:hover": prefersReduce ? undefined : { transform: "scale(1.06)" },
          }}
        />
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            background: prefersReduce
              ? "transparent"
              : "linear-gradient(140deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0) 60%)",
            mixBlendMode: "screen",
          }}
        />
      </Box>
      <Box sx={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 0.75 }}>
        <Typography
          className="spotify-title np-title"
          variant="body1"
          sx={{
            fontWeight: 600,
            color: alpha(theme.palette.common.white, 0.96),
            letterSpacing: 0.2,
            lineHeight: 1.2,
          }}
        >
          {data.track_name || "—"}
        </Typography>
        <Typography
          className="spotify-sub np-art"
          variant="body2"
          sx={{
            color: alpha(theme.palette.common.white, 0.7),
            letterSpacing: 0.15,
            display: "block",
          }}
        >
          {(data.artists || []).join(", ")}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
          <LinearProgress
            className="progress"
            variant="determinate"
            value={pct}
            sx={{
              flex: 1,
              height: 6,
              borderRadius: 999,
              backgroundColor: alpha(theme.palette.common.white, 0.12),
              "& .MuiLinearProgress-bar": {
                borderRadius: 999,
                background: `linear-gradient(90deg, ${alpha(
                  theme.palette.primary.light,
                  0.8
                )}, ${alpha(theme.palette.secondary.light, 0.9)})`,
                transition: prefersReduce ? "none" : undefined,
              },
            }}
          />
          <Typography
            className="spotify-time np-time"
            variant="caption"
            sx={{
              color: alpha(theme.palette.common.white, 0.72),
              letterSpacing: 0.6,
              whiteSpace: "nowrap",
            }}
          >
            {fmt(progress)} / {fmt(data.duration_ms)}
          </Typography>
        </Box>
      </Box>
      {!prefersReduce && (
        <Box
          aria-hidden
          sx={{
            position: "absolute",
            inset: 0,
            overflow: "hidden",
            pointerEvents: "none",
            "&::before": {
              content: '""',
              position: "absolute",
              top: 0,
              left: 0,
              width: "45%",
              height: "200%",
              background: "linear-gradient(120deg, rgba(255,255,255,0) 30%, rgba(255,255,255,0.25) 50%, rgba(255,255,255,0) 70%)",
              animation: `${shimmerEdge} 6s ease-in-out infinite`,
            },
          }}
        />
      )}
    </Paper>
  );
});

export default function Profile() {
  const { user, loading, setUser } = useAuth();
  const theme = useTheme();

  const [snack, setSnack] = useState<{
    text: string;
    sev?: "success" | "info" | "warning" | "error";
  } | null>(null);
  const [avatarVersion, setAvatarVersion] = useState(Date.now());
  const [coverVersion, setCoverVersion] = useState(Date.now());
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const isTwoCol = useMediaQuery("(min-width:1400px)");
  const isMobile = useMediaQuery("(max-width:600px)");

  const [scrollY, setScrollY] = useState(0);

  const [qrOpen, setQrOpen] = useState(false);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);
  const [achOpen, setAchOpen] = useState<{
    name: string;
    issuer?: string;
    date?: string;
    url?: string;
  } | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const confettiRef = useRef<HTMLCanvasElement | null>(null);

  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const endTimerRef = useRef<number | null>(null);
  const pollRef = useRef<number | null>(null);
  const fetchingRef = useRef(false);

  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected);

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
  const coverParallax = reduceMotion ? 0 : Math.min(scrollY * 0.12, 48);
  const coverScale = reduceMotion ? 1 : Math.min(1 + scrollY * 0.00018, 1.05);

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const s = sp.get("spotify");
    if (s !== null) {
      if (s !== "error") {
        api
          .get("/users/me")
          .then((r) => setUser(r.data))
          .catch(() => {});
        setSnack({ text: "Spotify подключён", sev: "success" });
      } else {
        setSnack({ text: "Ошибка подключения Spotify", sev: "error" });
      }
      sp.delete("spotify");
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "");
      window.history.replaceState({}, "", next);
    }
  }, [setUser]);

  const fetchNowPlaying = useCallback(async () => {
    if (!spotifyConnected || fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const r = await api.get<NowPlaying>("/spotify/now-playing");
      setNowPlaying(r.data);
      if (endTimerRef.current) {
        window.clearTimeout(endTimerRef.current);
        endTimerRef.current = null;
      }
      if (r.data?.is_playing && r.data.duration_ms && r.data.progress_ms != null) {
        const remain = Math.max(0, r.data.duration_ms - r.data.progress_ms);
        endTimerRef.current = window.setTimeout(
          () => {
            fetchNowPlaying();
          },
          Math.min(remain + 400, 20000)
        );
      }
    } catch {
    } finally {
      fetchingRef.current = false;
    }
  }, [spotifyConnected]);

  useEffect(() => {
    if (!spotifyConnected) return;
    fetchNowPlaying();
    const startPoll = () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(fetchNowPlaying, 15000);
    };
    startPoll();
    const onVis = () => {
      if (document.hidden) {
        if (pollRef.current) window.clearInterval(pollRef.current);
      } else {
        fetchNowPlaying();
        startPoll();
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      if (endTimerRef.current) window.clearTimeout(endTimerRef.current);
      document.removeEventListener("visibilitychange", onVis);
      pollRef.current = null;
      endTimerRef.current = null;
    };
  }, [spotifyConnected, fetchNowPlaying]);

  if (loading)
    return (
      <Box minHeight="70vh" display="flex" alignItems="center" justifyContent="center">
        <CircularProgress />
      </Box>
    );

  const getAvatarSrc = () => {
    const url = user?.avatar_url || "";
    const resolved = resolveMediaUrl(url, BACKEND_ORIGIN);
    return resolved ? `${resolved}?v=${avatarVersion}` : undefined;
  };

  const getCoverSrc = () => {
    const url = user?.cover_url || "";
    const resolved = resolveMediaUrl(url, BACKEND_ORIGIN);
    return resolved || "https://mui.com/static/images/cards/cover1.jpg";
  };

  const structuredDataJson = useMemo(() => {
    const role = user?.role;
    const jobTitle =
      role === "teacher"
        ? user?.position || ""
        : role === "student"
        ? "Student"
        : "Administrator";
    const affiliation = user?.institute || user?.department || "";
    const avatarUrl = user?.avatar_url || "";
    const resolvedAvatar = resolveMediaUrl(avatarUrl, BACKEND_ORIGIN);
    const image = resolvedAvatar ? `${resolvedAvatar}?v=${avatarVersion}` : "";

    return JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Person",
      name: user?.full_name || "",
      email: user?.email || "",
      jobTitle,
      affiliation,
      url: typeof window !== "undefined" ? window.location.href : "",
      image,
    });
  }, [
    user?.role,
    user?.position,
    user?.institute,
    user?.department,
    user?.avatar_url,
    user?.full_name,
    user?.email,
    avatarVersion,
  ]);

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
      const count = 140;
      const parts = Array.from({ length: count }).map((_, i) => {
        const angle = Math.random() * Math.PI - Math.PI / 2;
        const speed = 3 + Math.random() * 6;
        const hue = Math.floor((i / count) * 360);
        return {
          x: cx,
          y: cy,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - 2,
          life: 60 + Math.random() * 40,
          size: 2 + Math.random() * 3,
          color: `hsl(${hue} 90% 55%)`,
        };
      });
      let raf = 0;
      const step = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        parts.forEach((p) => {
          p.vy += 0.12 * dpr;
          p.x += p.vx * dpr;
          p.y += p.vy * dpr;
          p.life -= 1;
          ctx.fillStyle = p.color;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.size * dpr, 0, Math.PI * 2);
          ctx.fill();
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
    if (snack && snack.sev === "success" && snack.text !== "Скопировано") burstConfetti();
  }, [snack, burstConfetti]);

  const copy = async (text: string, evt?: { clientX: number; clientY: number }) => {
    try {
      await navigator.clipboard?.writeText(text);
    } finally {
      setSnack({ text: "Скопировано", sev: "success" });
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
      typeof window !== "undefined" ? `URL:${window.location.href}` : "",
    ].filter(Boolean);
    lines.push("END:VCARD");
    return lines.join("\n");
  }, [user]);

  const openQrModal = useCallback(async () => {
    setQrError(null);
    setQrUrl(null);
    setQrOpen(true);
    try {
      const qr = await loadQrModule();
      const dataUrl = await qr.toDataURL(buildVCard(), { width: 280, errorCorrectionLevel: "M" });
      setQrUrl(dataUrl);
    } catch {
      setQrError("Не удалось сгенерировать QR-код. Попробуйте позже.");
    }
  }, [buildVCard]);

  const closeQrModal = useCallback(() => {
    setQrOpen(false);
    setQrError(null);
    setQrUrl(null);
  }, []);

  const downloadPdfCard = async () => {
    if (!user) return;
    try {
      const [jsPdfModule, qrMaybe] = await Promise.all([
        loadJsPdfModule(),
        loadQrModule().catch(() => null),
      ]);
      const { jsPDF } = jsPdfModule;
      const makeCanvas = (w: number, h: number) => {
        const c = document.createElement("canvas");
        c.width = w;
        c.height = h;
        const ctx = c.getContext("2d")!;
        return { c, ctx };
      };
      const roundedRect = (
        ctx: CanvasRenderingContext2D,
        x: number,
        y: number,
        w: number,
        h: number,
        r: number
      ) => {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
      };

      const loadImg = (src: string) =>
        new Promise<HTMLImageElement>((resolve, reject) => {
          const img = new Image();
          if (!src.startsWith("data:")) img.crossOrigin = "anonymous";
          img.onload = () => resolve(img);
          img.onerror = reject;
          img.src = src;
        });

      const fetchAsDataUrl = async (url: string) => {
        try {
          const r = await api.get(url, { responseType: "blob", withCredentials: true } as any);
          const blob: Blob = r.data;
          return await new Promise<string>((res) => {
            const fr = new FileReader();
            fr.onload = () => res(fr.result as string);
            fr.readAsDataURL(blob);
          });
        } catch {
          const r = await fetch(url, { credentials: "include", cache: "no-store" });
          const blob = await r.blob();
          return await new Promise<string>((res) => {
            const fr = new FileReader();
            fr.onload = () => res(fr.result as string);
            fr.readAsDataURL(blob);
          });
        }
      };

      const cardPt = { w: 360, h: 210 };
      const scale = 4;
      const pxPerPt = 96 / 72;
      const W = Math.round(cardPt.w * scale * pxPerPt);
      const H = Math.round(cardPt.h * scale * pxPerPt);

      const { c, ctx } = makeCanvas(W, H) as {
        c: HTMLCanvasElement;
        ctx: CanvasRenderingContext2D;
      };
      (ctx as any).imageSmoothingEnabled = true;
      (ctx as any).imageSmoothingQuality = "high";
      const g = ctx.createLinearGradient(0, 0, W, H);
      g.addColorStop(0, "#ffffff");
      g.addColorStop(1, "#f2f6ff");
      ctx.fillStyle = g as CanvasGradient;
      ctx.fillRect(0, 0, W, H);

      ctx.save();
      ctx.shadowColor = "rgba(0,0,0,.12)";
      ctx.shadowBlur = 28;
      ctx.shadowOffsetY = 10;
      ctx.fillStyle = "#ffffff";
      roundedRect(ctx, 22 * scale, 22 * scale, W - 44 * scale, H - 44 * scale, 22 * scale);
      ctx.fill();
      ctx.restore();

      const padX = Math.round(42 * scale);
      const padY = Math.round(38 * scale);
      const contentW = W - padX * 2;
      const leftW = Math.round(contentW * 0.62);
      const rightX = padX + leftW;
      const family = "Inter, Manrope, Arial, sans-serif";

      const fitText = (text: string, maxWidth: number, weight: number, baseSize: number) => {
        let size = baseSize;
        while (size > 10) {
          ctx.font = `${weight} ${size}px ${family}`;
          if (ctx.measureText(text).width <= maxWidth) break;
          size -= 1;
        }
        return size;
      };

      const isStudent = user.role === "student";
      const instituteLine = isStudent ? user.institute || "" : user.department || "";
      const programOrTitleLine = isStudent
        ? user.program || user.track || user.status || "Студент"
        : user.position || user.status || "";
      const emailText = user.email || "";
      const tg = user.telegram || "";

      const avatarReserve = Math.round(72 * scale);
      const nameTop = padY + avatarReserve + Math.round(14 * scale);

      const nameSize = fitText(user.full_name || "", leftW, 700, Math.round(34 * scale));
      ctx.font = `700 ${nameSize}px ${family}`;
      ctx.fillStyle = "#111";
      ctx.textBaseline = "top";
      ctx.fillText(user.full_name || "", padX, nameTop);

      let y = nameTop + nameSize + Math.round(8 * scale);
      const lineHeight = Math.round(18 * scale);
      const blockGap = Math.round(8 * scale);

      if (isStudent) {
        ctx.font = `400 ${Math.round(14 * scale)}px ${family}`;
        if (instituteLine) {
          ctx.fillStyle = "#666";
          ctx.fillText(String(instituteLine), padX, y);
          y += lineHeight + blockGap;
        }
        const progSize = fitText(
          String(programOrTitleLine || ""),
          leftW,
          400,
          Math.round(16 * scale)
        );
        ctx.font = `400 ${progSize}px ${family}`;
        if (programOrTitleLine) {
          ctx.fillStyle = "#444";
          ctx.fillText(String(programOrTitleLine), padX, y);
          y += Math.round(progSize + 6) + blockGap;
        }
      } else {
        const titleSize = fitText(
          String(programOrTitleLine || ""),
          leftW,
          400,
          Math.round(16 * scale)
        );
        ctx.font = `400 ${titleSize}px ${family}`;
        if (programOrTitleLine) {
          ctx.fillStyle = "#444";
          ctx.fillText(String(programOrTitleLine), padX, y);
          y += Math.round(titleSize + 6) + blockGap;
        }
        ctx.font = `400 ${Math.round(14 * scale)}px ${family}`;
        if (instituteLine) {
          ctx.fillStyle = "#666";
          ctx.fillText(String(instituteLine), padX, y);
          y += lineHeight + blockGap;
        }
      }

      ctx.fillStyle = "#333";
      if (emailText) {
        ctx.fillText(String(emailText), padX, y);
        y += lineHeight + blockGap;
      }
      if (tg) {
        ctx.fillText(String(tg), padX, y);
        y += lineHeight + blockGap;
      }

      const qrSide = Math.round(118 * scale);
      const qrX = rightX + Math.round((contentW - leftW - qrSide) / 2);
      const qrY = padY + Math.round(10 * scale);

      let qrImg: HTMLImageElement | null = null;
      if (qrMaybe) {
        try {
          const qrData = await qrMaybe.toDataURL(buildVCard(), { width: qrSide, margin: 1 });
          qrImg = await loadImg(qrData);
        } catch {
          setSnack({ text: "Не удалось сгенерировать QR — сохраняю без QR", sev: "warning" });
        }
      } else {
        setSnack({ text: "Не удалось сгенерировать QR — сохраняю без QR", sev: "warning" });
      }

      if (qrImg) {
        ctx.drawImage(qrImg, qrX, qrY, qrSide, qrSide);
      }

      const avatarResolved = resolveMediaUrl(user.avatar_url || "", BACKEND_ORIGIN);
      const avatarSrc = avatarResolved ? `${avatarResolved}?v=${avatarVersion}` : null;
      let avatarImg: HTMLImageElement | null = null;
      if (avatarSrc) {
        try {
          const dataUrl = await fetchAsDataUrl(avatarSrc);
          avatarImg = await loadImg(dataUrl);
        } catch {
          avatarImg = null;
        }
      }

      const size = avatarReserve;
      const ax = padX;
      const ay = padY;

      if (avatarImg) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(ax + size / 2, ay + size / 2, size / 2, 0, Math.PI * 2);
        ctx.closePath();
        ctx.clip();
        ctx.drawImage(avatarImg, ax, ay, size, size);
        ctx.restore();
      } else {
        ctx.save();
        ctx.fillStyle = "#e5e7eb";
        ctx.beginPath();
        ctx.arc(ax + size / 2, ay + size / 2, size / 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#111827";
        ctx.font = `700 ${Math.round(size * 0.42)}px Inter, Arial, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText((user.full_name?.[0] || "").toUpperCase(), ax + size / 2, ay + size / 2 + 2);
        ctx.restore();
      }

      const logoImg = await loadImg(guuLogo as unknown as string).catch(() => null);
      if (logoImg) {
        const imgEl = logoImg as HTMLImageElement;
        const natW = imgEl.naturalWidth || imgEl.width || 1;
        const natH = imgEl.naturalHeight || imgEl.height || 1;
        const maxW = Math.round((contentW - leftW) * 0.95);
        const maxH = Math.round(80 * scale);
        const k = Math.min(maxW / natW, maxH / natH);
        const lw = Math.max(1, Math.round(natW * k));
        const lh = Math.max(1, Math.round(natH * k));
        const safeMargin = Math.round(12 * scale);
        const lx = rightX + Math.round((contentW - leftW - lw) / 2);
        const lyTop = padY + Math.round(160 * scale);
        const ly = Math.min(lyTop, H - 22 * scale - lh - safeMargin);
        ctx.drawImage(imgEl, lx, ly, lw, lh);
      }

      const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: [cardPt.w, cardPt.h] });
      const data = c.toDataURL("image/jpeg", 0.95);
      const pageW = doc.internal.pageSize.getWidth();
      const pageH = doc.internal.pageSize.getHeight();
      doc.addImage(data, "JPEG", 0, 0, pageW, pageH);
      const fname = (user.full_name || "contact").replace(/\s+/g, "_") + ".pdf";
      doc.save(fname);
    } catch (error) {
      setSnack({ text: "Не удалось подготовить PDF визитку", sev: "error" });
    }
  };

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

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.put("/users/me", {
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
        position,
      });
      setUser(res.data);
      setEdit(false);
      navigate("/profile", { replace: true });
      setSnack({ text: "Профиль обновлён", sev: "success" });
      setAvatarVersion(Date.now());
      setCoverVersion(Date.now());
    } catch (e: any) {
      let message = "Ошибка";
      if (e?.response?.data?.detail) {
        if (typeof e.response.data.detail === "string") message = e.response.data.detail;
        else if (Array.isArray(e.response.data.detail))
          message = e.response.data.detail.map((err: any) => err.msg).join("; ");
      }
      setSnack({ text: message, sev: "error" });
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEdit(false);
    navigate("/profile", { replace: true });
  };

  const avatarPx = useMemo(() => {
    if (isMobile) return 132;
    return isTwoCol ? 188 : 168;
  }, [isMobile, isTwoCol]);
  const avatarSize = `${avatarPx}px`;
  const avatarFloat = Math.round(avatarPx * 0.55);
  const heroPaddingBottom = `${Math.max(avatarFloat - 12, 28)}px`;
  const heroTextPaddingTop = `${Math.round(avatarPx * 0.65)}px`;
  const infoOffsetMargin = `${avatarFloat + 36}px`;
  const glassPanelBg = alpha(theme.palette.background.paper, 0.28);
  const glassRaisedBg = alpha(theme.palette.background.paper, 0.18);
  const glassBorder = alpha(theme.palette.common.white, 0.24);
  const surfaceShadow = `0 40px 72px -38px ${alpha(theme.palette.common.black, 0.7)}`;
  const subtleRing = alpha(theme.palette.primary.light, 0.2);

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
            background: `linear-gradient(120deg, ${alpha(
              theme.palette.primary.dark,
              0.82
            )}, ${alpha(theme.palette.secondary.dark, 0.78)})`,
            mixBlendMode: "multiply",
          },
          "&::after": {
            content: '""',
            position: "absolute",
            inset: 0,
            background: `radial-gradient(circle at 25% 20%, ${alpha(
              theme.palette.primary.light,
              0.22
            )}, transparent 60%), radial-gradient(circle at 80% 25%, ${alpha(
              theme.palette.secondary.light,
              0.18
            )}, transparent 55%), radial-gradient(circle at 50% 85%, ${alpha(
              theme.palette.info.light,
              0.16
            )}, transparent 65%)`,
            opacity: 0.9,
          },
        }}
      />
      <Box
        component="main"
        sx={{
          position: "relative",
          minHeight: "100svh",
          display: "flex",
          flexDirection: "column",
          py: { xs: 8, sm: 9, md: 10 },
          px: { xs: 1.5, sm: 2, md: 3 },
        }}
      >
        <Container maxWidth="xl" sx={{ position: "relative", zIndex: 0 }}>
          <Fade in timeout={reduceMotion ? 0 : 900}>
            <Paper
              ref={containerRef}
              className="glass glass--panel profile-page"
              sx={{
                px: { xs: 2.6, sm: 3.6, md: 4.6, lg: 5.6 },
                py: { xs: 3.6, sm: 4.2, md: 5 },
                borderRadius: { xs: 3, md: 4 },
                border: `1px solid ${glassBorder}`,
                background: glassPanelBg,
                backdropFilter: "blur(34px)",
                boxShadow: surfaceShadow,
                position: "relative",
                overflow: "hidden",
              }}
            >
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: {
                    xs: "1fr",
                    md: "minmax(320px, 360px) minmax(0, 1fr)",
                    xl: "minmax(360px, 420px) minmax(0, 1fr)",
                  },
                  columnGap: { xs: 3, sm: 4, md: 5, xl: 6 },
                  rowGap: { xs: 4, md: 0 },
                  alignItems: "start",
                }}
              >
                <Stack spacing={{ xs: 3.2, md: 4 }} alignItems="stretch">
                  <Box
                    sx={{
                      position: "relative",
                      borderRadius: { xs: 3, md: 4 },
                      overflow: "hidden",
                      minHeight: { xs: 300, sm: 340, md: 360, lg: 400 },
                      display: "flex",
                      alignItems: "flex-end",
                      justifyContent: "center",
                      pb: heroPaddingBottom,
                      background: `linear-gradient(140deg, ${alpha(
                        theme.palette.primary.dark,
                        0.1
                      )}, ${alpha(theme.palette.secondary.dark, 0.08)})`,
                      boxShadow: `0 36px 80px -44px ${alpha(theme.palette.common.black, 0.72)}`,
                    }}
                  >
                    <Box
                      sx={{
                        position: "absolute",
                        inset: 0,
                        backgroundImage: `url(${getCoverSrc()}?v=${coverVersion})`,
                        backgroundPosition: "center",
                        backgroundSize: "cover",
                        transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                        transition: reduceMotion
                          ? "none"
                          : "transform 1400ms cubic-bezier(0.33, 1, 0.68, 1)",
                        willChange: "transform",
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        inset: 0,
                        background: "linear-gradient(185deg, rgba(6,9,20,0) 45%, rgba(6,9,20,0.92) 100%)",
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        inset: "-25% -25% 35%",
                        background: "radial-gradient(circle at 50% 0%, rgba(255,255,255,0.18), transparent 60%)",
                        opacity: 0.6,
                      }}
                    />
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
                        background: `linear-gradient(140deg, ${alpha(
                          theme.palette.primary.light,
                          0.72
                        )}, ${alpha(theme.palette.secondary.light, 0.62)})`,
                        padding: "4px",
                        boxShadow: `0 28px 64px -26px ${alpha(theme.palette.common.black, 0.76)}`,
                        animation: reduceMotion ? "none" : `${auraPulse} 12s ease-in-out infinite`,
                      }}
                    >
                      <Box
                        sx={{
                          width: "100%",
                          height: "100%",
                          borderRadius: "50%",
                          padding: "4px",
                          background: alpha(theme.palette.common.white, 0.16),
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          position: "relative",
                          overflow: "hidden",
                          boxShadow: `inset 0 0 0 1px ${subtleRing}`,
                        }}
                      >
                        <Avatar
                          src={getAvatarSrc()}
                          alt={user?.full_name}
                          sx={{
                            width: "100%",
                            height: "100%",
                            borderRadius: "50%",
                            fontSize: "clamp(28px, 6vw, 64px)",
                            border: `1px solid ${alpha(theme.palette.common.white, 0.38)}`,
                            backgroundColor: alpha(theme.palette.common.white, 0.12),
                            color: alpha(theme.palette.common.white, 0.92),
                          }}
                        >
                          {user?.full_name?.[0]}
                        </Avatar>
                      </Box>
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
                        gap: 2.4,
                      }}
                    >
                      <Box>
                        <Typography
                          variant="h3"
                          sx={{
                            fontSize: "clamp(1.7rem, 3.2vw, 2.9rem)",
                            fontWeight: 800,
                            lineHeight: 1.1,
                            color: alpha(theme.palette.common.white, 0.96),
                            textShadow: `0 6px 18px ${alpha(theme.palette.common.black, 0.52)}`,
                          }}
                        >
                          {user!.full_name}
                        </Typography>
                        {!!user?.position && user?.role === "teacher" && (
                          <Typography
                            variant="subtitle1"
                            sx={{
                              mt: 0.9,
                              color: alpha(theme.palette.common.white, 0.78),
                              fontWeight: 500,
                              letterSpacing: 0.3,
                            }}
                          >
                            {user.position}
                          </Typography>
                        )}
                        {!!user?.status && user?.role !== "teacher" && (
                          <Typography
                            variant="subtitle1"
                            sx={{
                              mt: 0.9,
                              color: alpha(theme.palette.common.white, 0.78),
                              fontWeight: 500,
                              letterSpacing: 0.3,
                            }}
                          >
                            {user.status}
                          </Typography>
                        )}
                      </Box>
                      <Stack
                        direction="row"
                        spacing={1.2}
                        useFlexGap
                        flexWrap="wrap"
                        sx={{
                          justifyContent: { xs: "center", md: "flex-start" },
                        }}
                      >
                        {[
                          user!.role === "teacher"
                            ? "Преподаватель"
                            : user!.role === "student"
                            ? "Студент"
                            : "Администратор",
                          ...(user!.role === "student" && user!.course ? [`Курс ${user!.course}`] : []),
                          ...(user!.institute ? [user!.institute] : []),
                        ].map((chip, idx) => (
                          <Grow
                            in
                            key={`${chip}-${idx}`}
                            timeout={reduceMotion ? 0 : 620}
                            style={{ transitionDelay: reduceMotion ? "0ms" : `${idx * 110}ms` }}
                          >
                            <Chip
                              size="small"
                              className="glass--chip"
                              label={chip}
                              sx={{
                                borderRadius: 999,
                                px: 0,
                                border: `1px solid ${alpha(theme.palette.common.white, 0.28)}`,
                                background: alpha(theme.palette.background.paper, 0.18),
                                backdropFilter: "blur(18px)",
                                color: alpha(theme.palette.common.white, 0.92),
                                transition: "transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease",
                                animation: reduceMotion
                                  ? "none"
                                  : `${chipHighlight} 12s ease-in-out infinite`,
                                animationDelay: reduceMotion ? "0ms" : `${idx * 90}ms`,
                                "& .MuiChip-label": {
                                  px: 1.6,
                                  py: 0.62,
                                  whiteSpace: "normal",
                                  lineHeight: 1.28,
                                },
                                "&:hover": {
                                  borderColor: alpha(theme.palette.primary.light, 0.6),
                                  boxShadow: `0 12px 24px -14px ${alpha(theme.palette.common.black, 0.64)}`,
                                  transform: reduceMotion ? "none" : "translateY(-2px)",
                                },
                              }}
                            />
                          </Grow>
                        ))}
                      </Stack>
                    </Box>
                  </Box>

                  <Paper
                    elevation={0}
                    sx={{
                      p: { xs: 2.6, sm: 3 },
                      borderRadius: 3,
                      border: `1px solid ${glassBorder}`,
                      background: glassRaisedBg,
                      backdropFilter: "blur(22px)",
                      boxShadow: `0 26px 52px -36px ${alpha(theme.palette.common.black, 0.66)}`,
                      display: "flex",
                      flexDirection: "column",
                      gap: { xs: 2.6, md: 3 },
                    }}
                  >
                    <Stack direction={{ xs: "column", md: "column" }} spacing={1.3} alignItems="stretch">
                      <Button
                        size="large"
                        variant="contained"
                        color="secondary"
                        onClick={openQrModal}
                        sx={{
                          width: "100%",
                          borderRadius: 2,
                          py: 1.05,
                          fontWeight: 600,
                          letterSpacing: 0.24,
                        }}
                      >
                        Показать QR
                      </Button>
                      <Button
                        size="large"
                        variant="outlined"
                        onClick={downloadPdfCard}
                        sx={{
                          width: "100%",
                          borderRadius: 2,
                          py: 1.05,
                          fontWeight: 600,
                          letterSpacing: 0.24,
                          borderColor: alpha(theme.palette.common.white, 0.34),
                          color: alpha(theme.palette.common.white, 0.92),
                          "&:hover": {
                            borderColor: alpha(theme.palette.primary.light, 0.7),
                            backgroundColor: alpha(theme.palette.primary.light, 0.12),
                          },
                        }}
                      >
                        PDF визитка
                      </Button>
                    </Stack>
                    <Divider sx={{ borderColor: alpha(theme.palette.common.white, 0.12) }} />
                    <Stack spacing={1.8}>
                      <Stack
                        direction="row"
                        spacing={1.4}
                        alignItems="center"
                        sx={{ justifyContent: "space-between", flexWrap: "wrap" }}
                      >
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
                          <EmailIcon
                            aria-hidden
                            sx={{ fontSize: 22, color: alpha(theme.palette.primary.light, 0.9) }}
                          />
                          <Typography
                            sx={{
                              fontWeight: 600,
                              color: alpha(theme.palette.common.white, 0.92),
                              wordBreak: "break-word",
                              flex: 1,
                            }}
                          >
                            <a href={`mailto:${user!.email}`} style={{ color: "inherit", textDecoration: "none" }}>
                              {user!.email}
                            </a>
                          </Typography>
                        </Stack>
                        <Tooltip title="Скопировать email">
                          <IconButton
                            size="small"
                            onClick={(e) => copy(user!.email, e)}
                            aria-label="Скопировать email"
                            sx={{
                              color: alpha(theme.palette.common.white, 0.8),
                              transition: reduceMotion
                                ? "color 140ms ease"
                                : "transform 200ms ease, box-shadow 200ms ease, color 200ms ease",
                              "&:hover": {
                                transform: reduceMotion ? "none" : "translateY(-1px) scale(1.05)",
                                boxShadow: `0 8px 16px -12px ${alpha(theme.palette.common.black, 0.6)}`,
                                color: alpha(theme.palette.primary.light, 0.95),
                              },
                              "&:focus-visible": {
                                outline: `2px solid ${alpha(theme.palette.primary.light, 0.8)}`,
                                outlineOffset: 2,
                              },
                            }}
                          >
                            <ContentCopyIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Stack>

                      {user!.telegram && (
                        <Stack
                          direction="row"
                          spacing={1.4}
                          alignItems="center"
                          sx={{ justifyContent: "space-between", flexWrap: "wrap" }}
                        >
                          <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
                            <TelegramIcon
                              aria-hidden
                              sx={{ fontSize: 22, color: alpha(theme.palette.secondary.light, 0.88) }}
                            />
                            <Typography
                              sx={{
                                fontWeight: 600,
                                color: alpha(theme.palette.common.white, 0.92),
                                wordBreak: "break-word",
                                flex: 1,
                              }}
                            >
                              <a
                                href={telegramHref}
                                target="_blank"
                                rel="noreferrer"
                                style={{ color: "inherit", textDecoration: "none" }}
                              >
                                {user!.telegram}
                              </a>
                            </Typography>
                          </Stack>
                          <Tooltip title="Скопировать ник">
                            <IconButton
                              size="small"
                              onClick={(e) => copy(user!.telegram!, e)}
                              aria-label="Скопировать ник в Telegram"
                              sx={{
                                color: alpha(theme.palette.common.white, 0.8),
                                transition: reduceMotion
                                  ? "color 140ms ease"
                                  : "transform 200ms ease, box-shadow 200ms ease, color 200ms ease",
                                "&:hover": {
                                  transform: reduceMotion ? "none" : "translateY(-1px) scale(1.05)",
                                  boxShadow: `0 8px 16px -12px ${alpha(theme.palette.common.black, 0.6)}`,
                                  color: alpha(theme.palette.secondary.light, 0.95),
                                },
                                "&:focus-visible": {
                                  outline: `2px solid ${alpha(theme.palette.secondary.light, 0.8)}`,
                                  outlineOffset: 2,
                                },
                              }}
                            >
                              <ContentCopyIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      )}
                    </Stack>
                  </Paper>

                  {spotifyConnected && nowPlaying && (
                    <Fade in timeout={reduceMotion ? 0 : 720}>
                      <Stack spacing={1.4}>
                        <Typography
                          variant="overline"
                          sx={{
                            letterSpacing: 2.2,
                            color: alpha(theme.palette.common.white, 0.72),
                          }}
                        >
                          Сейчас играет
                        </Typography>
                        <NowPlayingCard data={nowPlaying} />
                      </Stack>
                    </Fade>
                  )}
                </Stack>

                <Box sx={{ width: "100%", position: "relative", mt: { xs: infoOffsetMargin, md: 0 } }}>
                  {edit ? (
                    <Paper
                      elevation={0}
                      sx={{
                        width: "100%",
                        borderRadius: 3,
                        border: `1px solid ${glassBorder}`,
                        background: glassPanelBg,
                        backdropFilter: "blur(26px)",
                        boxShadow: `0 32px 64px -42px ${alpha(theme.palette.common.black, 0.68)}`,
                        p: { xs: 2.6, sm: 3, md: 3.4 },
                      }}
                      className="profile-edit"
                    >
                      <Stack spacing={2.2}>
                        <TextField
                          label="Имя"
                          value={fullName}
                          onChange={(e) => setFullName(e.target.value)}
                          fullWidth
                          inputProps={{ maxLength: 120 }}
                        />
                        <TextField
                          label="Email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          fullWidth
                          type="email"
                        />
                        <TextField
                          label="Telegram"
                          value={telegram}
                          onChange={(e) => setTelegram(e.target.value)}
                          fullWidth
                          helperText="Можно ввести @username или ссылку"
                        />
                        {user!.role === "teacher" && (
                          <>
                            <TextField
                              label="Кафедра/отдел"
                              value={department}
                              onChange={(e) => setDepartment(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Должность"
                              value={position}
                              onChange={(e) => setPosition(e.target.value)}
                              fullWidth
                            />
                          </>
                        )}
                        {user!.role === "student" && (
                          <>
                            <TextField
                              label="О себе"
                              value={about}
                              onChange={(e) => setAbout(e.target.value)}
                              fullWidth
                              multiline
                              minRows={3}
                            />
                            <TextField
                              label="Номер зачётной книжки"
                              value={recordBookNumber}
                              onChange={(e) => setRecordBookNumber(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Статус"
                              value={status}
                              onChange={(e) => setStatus(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Институт"
                              value={institute}
                              onChange={(e) => setInstitute(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Курс"
                              value={course}
                              onChange={(e) => setCourse(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Уровень образования"
                              value={educationLevel}
                              onChange={(e) => setEducationLevel(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Направление"
                              value={track}
                              onChange={(e) => setTrack(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Образовательная программа"
                              value={program}
                              onChange={(e) => setProgram(e.target.value)}
                              fullWidth
                            />
                            <TextField
                              label="Достижения"
                              value={achievements}
                              onChange={(e) => setAchievements(e.target.value)}
                              fullWidth
                              multiline
                              minRows={2}
                            />
                          </>
                        )}
                        <Stack
                          direction={{ xs: "column", sm: "row" }}
                          spacing={2}
                          sx={{ alignItems: { xs: "stretch", sm: "center" } }}
                        >
                          <Button
                            onClick={handleSave}
                            variant="contained"
                            disabled={saving}
                            sx={{ width: { xs: "100%", sm: "auto" } }}
                          >
                            {saving ? "СОХРАНЯЕМ..." : "СОХРАНИТЬ"}
                          </Button>
                          <Button
                            onClick={handleCancel}
                            variant="outlined"
                            sx={{ width: { xs: "100%", sm: "auto" } }}
                          >
                            ОТМЕНА
                          </Button>
                        </Stack>
                      </Stack>
                    </Paper>
                  ) : (
                    <Paper
                      elevation={0}
                      sx={{
                        width: "100%",
                        borderRadius: 3,
                        border: `1px solid ${glassBorder}`,
                        background: glassPanelBg,
                        backdropFilter: "blur(26px)",
                        boxShadow: `0 32px 64px -42px ${alpha(theme.palette.common.black, 0.68)}`,
                        p: { xs: 2.6, sm: 3, md: 3.4 },
                      }}
                    >
                      <Typography
                        variant="h5"
                        sx={{
                          fontWeight: 700,
                          fontSize: "clamp(1.3rem, 2.3vw, 1.8rem)",
                          mb: 2.2,
                          color: alpha(theme.palette.common.white, 0.92),
                        }}
                      >
                        Сведения
                      </Typography>
                      <Accordion
                        disableGutters
                        defaultExpanded
                        sx={{
                          background: "transparent",
                          border: `1px solid ${alpha(theme.palette.common.white, 0.16)}`,
                          borderRadius: 3,
                          boxShadow: "none",
                          "&::before": { display: "none" },
                        }}
                      >
                        <AccordionSummary
                          expandIcon={<ExpandMoreIcon />}
                          sx={{
                            px: 2.2,
                            py: 1.4,
                            borderBottom: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                            color: alpha(theme.palette.common.white, 0.82),
                          }}
                        >
                          <Typography fontWeight={700}>Детали профиля</Typography>
                        </AccordionSummary>
                        <AccordionDetails sx={{ px: { xs: 1.6, sm: 2.2 }, py: { xs: 1.8, sm: 2 } }}>
                          <List
                            sx={{
                              display: "grid",
                              gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                              columnGap: { xs: 1.6, md: 2.4 },
                              rowGap: 1.6,
                              p: 0,
                            }}
                          >
                            {!!user!.about && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.info.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>О себе:</b> {user!.about}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                            {!!user!.status && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.success.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>Статус:</b> {user!.status}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                            {!!user!.record_book_number && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.warning.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>Номер зачётной книжки:</b> {user!.record_book_number}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                            {!!user!.education_level && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.primary.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>Уровень образования:</b> {user!.education_level}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                            {!!user!.track && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.secondary.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>Направление:</b> {user!.track}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                            {!!user!.program && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.info.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>Образовательная программа:</b> {user!.program}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                            {!!user!.department && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.success.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>Кафедра/отдел:</b> {user!.department}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                            {!!user!.position && (
                              <ListItem
                                sx={{
                                  m: 0,
                                  px: 0,
                                  py: 0,
                                  borderRadius: 2,
                                  background: alpha(theme.palette.common.black, 0.18),
                                  border: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
                                  alignItems: "flex-start",
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 30, mt: 0.3, color: alpha(theme.palette.secondary.light, 0.9) }}>
                                  <FiberManualRecordIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={
                                    <span>
                                      <b>Должность:</b> {user!.position}
                                    </span>
                                  }
                                />
                              </ListItem>
                            )}
                          </List>
                          {achievementsList.length > 0 && (
                            <Box sx={{ mt: 2.4 }}>
                              <Typography
                                variant="subtitle1"
                                sx={{
                                  fontWeight: 600,
                                  mb: 1.4,
                                  color: alpha(theme.palette.common.white, 0.86),
                                }}
                              >
                                Достижения
                              </Typography>
                              <Box
                                sx={{
                                  display: "grid",
                                  gridTemplateColumns: {
                                    xs: "repeat(auto-fit, minmax(140px, 1fr))",
                                    sm: "repeat(auto-fit, minmax(160px, 1fr))",
                                  },
                                  gap: 1.2,
                                }}
                              >
                                {achievementsList.map((ach, idx) => (
                                  <Grow
                                    in
                                    key={ach.key}
                                    timeout={reduceMotion ? 0 : 520}
                                    style={{ transitionDelay: reduceMotion ? "0ms" : `${idx * 90}ms` }}
                                  >
                                    <Chip
                                      className="chip-gradient"
                                      label={ach.name}
                                      clickable
                                    onClick={() => setAchOpen({
                                      name: ach.name,
                                      issuer: ach.issuer,
                                      date: ach.date,
                                      url: ach.url,
                                    })}
                                    sx={{
                                      borderRadius: 2,
                                      textAlign: "left",
                                      background: alpha(theme.palette.background.paper, 0.22),
                                      border: `1px solid ${alpha(theme.palette.common.white, 0.28)}`,
                                      backdropFilter: "blur(18px)",
                                      color: alpha(theme.palette.common.white, 0.92),
                                      alignSelf: "stretch",
                                      transition: "transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease",
                                      animation: reduceMotion
                                        ? "none"
                                        : `${chipHighlight} 14s ease-in-out infinite`,
                                      animationDelay: reduceMotion ? "0ms" : `${idx * 120}ms`,
                                      "& .MuiChip-label": {
                                        display: "block",
                                        whiteSpace: "normal",
                                        lineHeight: 1.3,
                                        px: 1.6,
                                          py: 1.1,
                                        },
                                        "&:hover": {
                                          borderColor: alpha(theme.palette.primary.light, 0.7),
                                          boxShadow: `0 12px 28px -16px ${alpha(theme.palette.common.black, 0.62)}`,
                                          transform: reduceMotion ? "none" : "translateY(-2px)",
                                        },
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
                  )}
                </Box>
              </Box>
            </Paper>
          </Fade>
        </Container>
        <canvas
          ref={confettiRef}
          style={{
            position: "fixed",
            left: 0,
            top: 0,
            width: "100vw",
            height: "100vh",
            pointerEvents: "none",
            zIndex: 2147483000,
          }}
        />
      </Box>

      <Dialog
        open={qrOpen}
        onClose={closeQrModal}
        maxWidth="xs"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 3,
            border: `1px solid ${glassBorder}`,
            background: glassPanelBg,
            backdropFilter: "blur(18px)",
            boxShadow: `0 26px 52px -36px ${alpha(theme.palette.common.black, 0.66)}`,
          },
        }}
      >
        <DialogTitle sx={{ textAlign: "center", fontWeight: 700 }}>QR визитки</DialogTitle>
        <DialogContent
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minHeight: 280,
            gap: 2,
          }}
          role="status"
          aria-live="polite"
        >
          {qrUrl && (
            <Box
              component="img"
              src={qrUrl}
              alt="QR-код визитки"
              sx={{ width: "min(100%, 280px)", height: "auto" }}
            />
          )}
          {!qrUrl && !qrError && <CircularProgress aria-label="Генерация QR-кода" />}
          {!!qrError && (
            <Typography role="alert" sx={{ textAlign: "center" }}>
              {qrError}
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ justifyContent: "center", pb: 2 }}>
          <Button onClick={closeQrModal}>Готово</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={!!achOpen}
        onClose={() => setAchOpen(null)}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 3,
            border: `1px solid ${glassBorder}`,
            background: glassPanelBg,
            backdropFilter: "blur(18px)",
            boxShadow: `0 26px 52px -36px ${alpha(theme.palette.common.black, 0.66)}`,
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, textAlign: "center" }}>{achOpen?.name}</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1.4 }}>
          {!!achOpen?.issuer && (
            <Typography>
              <b>Выдано:</b> {achOpen.issuer}
            </Typography>
          )}
          {!!achOpen?.date && (
            <Typography>
              <b>Дата:</b> {achOpen.date}
            </Typography>
          )}
          {!!achOpen?.url && (
            <Typography>
              <b>Подтверждение:</b>{" "}
              <a href={achOpen.url} target="_blank" rel="noreferrer">
                {achOpen.url}
              </a>
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ justifyContent: "center", pb: 2 }}>
          <Button onClick={() => setAchOpen(null)}>Закрыть</Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        autoHideDuration={2600}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          onClose={() => setSnack(null)}
          severity={snack?.sev || "info"}
          variant="filled"
          sx={{ width: "100%" }}
        >
          {snack?.text}
        </Alert>
      </Snackbar>

      <script type="application/ld+json">{structuredDataJson}</script>
    </>
  );
}
