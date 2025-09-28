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
  Skeleton,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EmailIcon from "@mui/icons-material/Email";
import TelegramIcon from "@mui/icons-material/Telegram";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ShareIcon from "@mui/icons-material/IosShare";
import DownloadIcon from "@mui/icons-material/Download";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import QrCodeIcon from "@mui/icons-material/QrCode2";
import useMediaQuery from "@mui/material/useMediaQuery";
import { resolveMediaUrl } from "@/utils/media";
import { alpha, useTheme } from "@mui/material/styles";

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

const NowPlayingCard = memo(function NowPlayingCard({ data }: { data: NowPlaying }) {
  const theme = useTheme();
  const [progress, setProgress] = useState<number>(data.progress_ms ?? 0);
  const startRef = useRef<number>(Date.now() - (data.progress_ms ?? 0));
  const rafRef = useRef<number | null>(null);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgError, setImgError] = useState(false);

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

  const clickable = Boolean(data.track_url);

  return (
    <Paper
      elevation={0}
      className="spotify-card nowplaying--spotify"
      sx={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: theme.spacing(2),
        px: theme.spacing(2),
        py: theme.spacing(1.5),
        borderRadius: theme.shape.borderRadius * 1.4,
        backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.4 : 0.7),
        backdropFilter: "blur(12px)",
        boxShadow: theme.shadows[1],
      }}
    >
      <Box
        sx={{
          position: "relative",
          width: 64,
          height: 64,
          flexShrink: 0,
          borderRadius: theme.shape.borderRadius,
          overflow: "hidden",
          boxShadow: theme.shadows[1],
        }}
      >
        {!imgLoaded && !imgError && (
          <Skeleton variant="rounded" width="100%" height="100%" animation="wave" />
        )}
        <Avatar
          variant="rounded"
          src={!imgError ? data.album_image_url || "" : undefined}
          alt={data.album_name || data.track_name || "Spotify cover"}
          imgProps={{
            loading: "lazy",
            onLoad: () => setImgLoaded(true),
            onError: () => setImgError(true),
            style: { objectFit: "cover" },
          }}
          sx={{
            width: "100%",
            height: "100%",
            opacity: imgLoaded && !imgError ? 1 : 0,
            transition: "opacity 240ms ease",
            backgroundColor: alpha(theme.palette.text.primary, 0.08),
          }}
        >
          {data.track_name?.[0] ?? ""}
        </Avatar>
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Tooltip title={data.track_name || ""} disableHoverListener={!data.track_name} arrow>
          <Typography
            className="spotify-title np-title"
            variant="subtitle2"
            noWrap
            component={clickable ? "a" : "p"}
            href={clickable ? data.track_url : undefined}
            target={clickable ? "_blank" : undefined}
            rel={clickable ? "noreferrer" : undefined}
            aria-label={clickable ? `Открыть трек ${data.track_name}` : undefined}
            sx={{
              color: theme.palette.text.primary,
              fontWeight: 600,
              textDecoration: "none",
              display: "block",
              transition: "color 160ms ease",
              '&:hover, &:focus-visible': clickable
                ? {
                    color: theme.palette.primary.main,
                    outline: "none",
                  }
                : undefined,
            }}
          >
            {data.track_name || "—"}
          </Typography>
        </Tooltip>
        <Tooltip
          title={(data.artists || []).join(", ")}
          disableHoverListener={!data.artists?.length}
          arrow
        >
          <Typography
            className="spotify-sub np-art"
            variant="body2"
            color="text.secondary"
            noWrap
            sx={{ mt: 0.2 }}
          >
            {(data.artists || []).join(", ") || "—"}
          </Typography>
        </Tooltip>
        <Box sx={{ mt: 1 }}>
          <LinearProgress
            className="progress"
            variant="determinate"
            value={pct}
            sx={{
              height: 4,
              borderRadius: theme.shape.borderRadius,
              backgroundColor: alpha(theme.palette.text.primary, 0.08),
              '& .MuiLinearProgress-bar': {
                borderRadius: theme.shape.borderRadius,
              },
            }}
          />
        </Box>
      </Box>
      <Typography
        className="spotify-time np-time"
        variant="caption"
        color="text.secondary"
        sx={{
          fontFamily: theme.typography.fontFamilyMonospace,
          whiteSpace: "nowrap",
        }}
      >
        {fmt(progress)} / {fmt(data.duration_ms)}
      </Typography>
    </Paper>
  );
});

const NowPlayingCardSkel = memo(function NowPlayingCardSkel() {
  const theme = useTheme();
  return (
    <Paper
      elevation={0}
      className="spotify-card nowplaying--spotify"
      sx={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: theme.spacing(2),
        px: theme.spacing(2),
        py: theme.spacing(1.5),
        borderRadius: theme.shape.borderRadius * 1.4,
        backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.35 : 0.65),
        backdropFilter: "blur(12px)",
        boxShadow: theme.shadows[1],
      }}
    >
      <Skeleton variant="rounded" width={64} height={64} animation="wave" />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Skeleton variant="text" width="70%" sx={{ fontSize: theme.typography.subtitle2.fontSize }} />
        <Skeleton variant="text" width="50%" sx={{ fontSize: theme.typography.body2.fontSize }} />
        <Skeleton variant="rectangular" height={4} sx={{ mt: 1, borderRadius: theme.shape.borderRadius }} />
      </Box>
      <Skeleton variant="text" width={72} sx={{ fontSize: theme.typography.caption.fontSize }} />
    </Paper>
  );
});

const NowPlayingEmpty = memo(function NowPlayingEmpty() {
  const theme = useTheme();
  return (
    <Paper
      elevation={0}
      className="spotify-card nowplaying--spotify"
      sx={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: theme.spacing(2),
        px: theme.spacing(2),
        py: theme.spacing(1.5),
        borderRadius: theme.shape.borderRadius * 1.4,
        backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.35 : 0.65),
        backdropFilter: "blur(12px)",
        boxShadow: theme.shadows[1],
        color: theme.palette.text.secondary,
      }}
    >
      <Avatar
        variant="rounded"
        sx={{
          width: 56,
          height: 56,
          backgroundColor: alpha(theme.palette.text.primary, 0.08),
          color: theme.palette.text.secondary,
          fontWeight: 600,
        }}
      >
        ♫
      </Avatar>
      <Typography variant="body2" color="text.secondary">
        Сейчас ничего не играет
      </Typography>
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
  const [avatarLoaded, setAvatarLoaded] = useState(false);
  const [avatarError, setAvatarError] = useState(false);
  const [coverLoaded, setCoverLoaded] = useState(false);
  const [coverError, setCoverError] = useState(false);
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
  const [shareAvailable, setShareAvailable] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const confettiRef = useRef<HTMLCanvasElement | null>(null);

  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const [nowPlayingLoading, setNowPlayingLoading] = useState(false);
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

  useEffect(() => {
    setAvatarLoaded(false);
    setAvatarError(false);
  }, [avatarVersion, user?.avatar_url]);

  useEffect(() => {
    setCoverLoaded(false);
    setCoverError(false);
  }, [coverVersion, user?.cover_url]);

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
    setNowPlayingLoading(true);
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
      setNowPlayingLoading(false);
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
    if (resolved) return `${resolved}?v=${coverVersion}`;
    return "https://mui.com/static/images/cards/cover1.jpg";
  };

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

  useEffect(() => {
    if (typeof navigator === "undefined") return;
    const hasShare = typeof navigator.share === "function" || typeof navigator.canShare === "function";
    if (hasShare) setShareAvailable(true);
  }, []);

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

  const downloadVcf = useCallback(() => {
    if (!user) return;
    try {
      const card = buildVCard();
      const blob = new Blob([card], { type: "text/vcard;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const fname = (user.full_name || "contact").replace(/\s+/g, "_") + ".vcf";
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      requestAnimationFrame(() => URL.revokeObjectURL(url));
      setSnack({ text: ".vcf сохранён", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось сохранить .vcf", sev: "error" });
    }
  }, [buildVCard, user]);

  const shareProfile = useCallback(async () => {
    if (!shareAvailable || typeof navigator === "undefined") return;
    try {
      const shareData: ShareData = {
        title: user?.full_name || "Профиль",
        text: user?.about || undefined,
        url: typeof window !== "undefined" ? window.location.href : undefined,
      };
      if (navigator.canShare && !navigator.canShare(shareData)) {
        throw new Error("Нельзя поделиться этими данными");
      }
      await navigator.share?.(shareData);
      setSnack({ text: "Ссылка отправлена", sev: "success" });
    } catch (error: any) {
      if (error?.name === "AbortError") return;
      setSnack({ text: "Не удалось поделиться", sev: "error" });
    }
  }, [shareAvailable, user?.full_name, user?.about]);

  const telegramHref = useMemo(() => {
    const t = user?.telegram || "";
    if (!t) return "";
    let v = String(t).trim();
    if (v.startsWith("http")) return v;
    if (v.startsWith("@")) v = v.slice(1);
    return `https://t.me/${v}`;
  }, [user?.telegram]);

  const infoItems = useMemo(() => {
    if (!user) return [] as { label: string; value: string }[];
    return [
      { label: "О себе", value: user.about || "" },
      { label: "Статус", value: user.status || "" },
      { label: "Номер зачётной книжки", value: user.record_book_number || "" },
      { label: "Уровень образования", value: user.education_level || "" },
      { label: "Направление", value: user.track || "" },
      { label: "Образовательная программа", value: user.program || "" },
      { label: "Кафедра/отдел", value: user.department || "" },
      { label: "Должность", value: user.position || "" },
    ].filter((item) => item.value);
  }, [user]);

  const achievementsList = useMemo(
    () =>
      String(user?.achievements || "")
        .split(/[,;\n]/)
        .map((str) => {
          const raw = String(str || "").trim();
          if (!raw) return null;
          const [name, issuer, date, url] = raw.split("|").map((s) => s.trim());
          if (!name) return null;
          return { name, issuer, date, url };
        })
        .filter((item): item is { name: string; issuer?: string; date?: string; url?: string } => Boolean(item)),
    [user?.achievements]
  );

  const contactItems = useMemo(
    () =>
      !user
        ? []
        : (
            [
              user.email
                ? {
                    type: "email" as const,
                    value: user.email,
                    href: `mailto:${user.email}`,
                  }
                : null,
              user.telegram
                ? {
                    type: "telegram" as const,
                    value: user.telegram,
                    href: telegramHref || undefined,
                  }
                : null,
            ].filter(Boolean) as { type: "email" | "telegram"; value: string; href?: string }[]
          ),
    [telegramHref, user]
  );
  const displayFullName = user?.full_name || "";

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
    if (isMobile) return 128;
    return isTwoCol ? 168 : 156;
  }, [isMobile, isTwoCol]);
  const avatarSize = `${avatarPx}px`;
  const avatarBottom = isTwoCol
    ? `-${Math.round(avatarPx * 0.32)}px`
    : `-${Math.round(avatarPx * 0.5)}px`;
  const mtStacked = `${Math.round(avatarPx * 0.36)}px`;
  const fieldSx = useMemo(
    () => ({
      "& .MuiInputBase-root": {
        borderRadius: theme.shape.borderRadius * 1.2,
        minHeight: theme.spacing(6),
      },
      "& .MuiFormHelperText-root": {
        marginLeft: 0,
        marginRight: 0,
      },
    }),
    [theme]
  );

  return (
    <>
      <Box
        sx={{
          position: "fixed",
          left: 0,
          top: 0,
          width: "100vw",
          height: "100vh",
          zIndex: -1,
          backgroundImage: `linear-gradient(120deg, var(--hero-grad-start), var(--hero-grad-end)), url(${profileBg})`,
          backgroundRepeat: "no-repeat, repeat",
          backgroundSize: "cover, 480px",
          backgroundAttachment: reduceMotion ? "scroll, scroll" : "fixed, fixed",
          filter: "saturate(1.05)",
          transition: reduceMotion ? "none" : "opacity 600ms ease",
        }}
      />
      <Box maxWidth="100vw" mx="auto" mt={0} width="100vw" minHeight="100svh" px={0}>
        <Paper
          ref={containerRef}
          className="glass glass--panel profile-page"
          sx={{
            p: { xs: theme.spacing(2), sm: theme.spacing(3), md: theme.spacing(4.5), lg: theme.spacing(6) },
            borderRadius: 0,
            width: "100vw",
            minHeight: "100svh",
            display: "flex",
            flexDirection: { xs: "column", md: isTwoCol ? "row" : "column" },
            alignItems: { xs: "stretch", md: isTwoCol ? "flex-start" : "stretch" },
            gap: {
              xs: theme.spacing(4),
              md: isTwoCol ? theme.spacing(5) : theme.spacing(4),
            },
            position: "relative",
            backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.55 : 0.7),
            backdropFilter: "blur(14px)",
            boxShadow: theme.shadows[2],
            border: `1px solid ${alpha(theme.palette.common.white, theme.palette.mode === "dark" ? 0.08 : 0.18)}`,
          }}
        >
          <Box
            width={{ xs: "100%", md: isTwoCol ? 420 : "100%" }}
            display="flex"
            flexDirection="column"
            minWidth={0}
            sx={{ mx: { xs: "auto", md: 0 }, gap: theme.spacing(3) }}
          >
            <Box sx={{ position: "relative", width: "100%" }}>
              <Box
                sx={{
                  width: "100%",
                  height: { xs: 220, sm: 260, md: 300, lg: 320 },
                  minHeight: 140,
                  position: "relative",
                  borderRadius: { xs: 3, sm: 3.2, md: 4 },
                  overflow: "hidden",
                  boxShadow: theme.shadows[3],
                  backgroundColor: alpha(theme.palette.background.default, 0.3),
                }}
              >
                {!coverLoaded && !coverError && (
                  <Skeleton
                    variant="rectangular"
                    width="100%"
                    height="100%"
                    animation="wave"
                    sx={{ position: "absolute", inset: 0 }}
                  />
                )}
                <Box
                  component="img"
                  src={!coverError ? getCoverSrc() : profileBg}
                  alt="Обложка профиля"
                  onLoad={() => setCoverLoaded(true)}
                  onError={() => setCoverError(true)}
                  sx={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    transform: `translateY(${coverParallax}px) scale(${coverScale})`,
                    transition: reduceMotion ? "none" : "transform 600ms ease, opacity 320ms ease",
                    opacity: coverLoaded && !coverError ? 1 : 0,
                  }}
                />
                <Box
                  sx={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: { xs: 3, sm: 3.2, md: 4 },
                    background: `linear-gradient(180deg, ${alpha(theme.palette.background.paper, 0)} 45%, ${alpha(
                      theme.palette.background.paper,
                      theme.palette.mode === "dark" ? 0.76 : 0.52
                    )} 100%)`,
                    pointerEvents: "none",
                  }}
                />
              </Box>

              <Box
                sx={{
                  position: "absolute",
                  left: { xs: "50%", md: isTwoCol ? theme.spacing(3) : "50%" },
                  transform: {
                    xs: "translateX(-50%)",
                    md: isTwoCol ? "none" : "translateX(-50%)",
                  } as any,
                  bottom: avatarBottom,
                  width: avatarSize,
                  height: avatarSize,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  zIndex: 2,
                }}
              >
                <Box
                  sx={{
                    position: "relative",
                    width: "100%",
                    height: "100%",
                    borderRadius: "50%",
                    p: theme.spacing(0.75),
                    backgroundColor: alpha(
                      theme.palette.background.paper,
                      theme.palette.mode === "dark" ? 0.92 : 0.96
                    ),
                    boxShadow: theme.shadows[3],
                    transition: "transform 200ms ease",
                  }}
                >
                  {!avatarLoaded && !avatarError && (
                    <Skeleton variant="circular" width="100%" height="100%" animation="wave" />
                  )}
                  <Avatar
                    src={!avatarError ? getAvatarSrc() : undefined}
                    alt={user?.full_name || "Аватар"}
                    imgProps={{
                      onLoad: () => setAvatarLoaded(true),
                      onError: () => setAvatarError(true),
                      style: { objectFit: "cover" },
                    }}
                    tabIndex={0}
                    aria-label="Аватар профиля"
                    sx={{
                      width: "100%",
                      height: "100%",
                      borderRadius: "50%",
                      fontSize: "clamp(32px, 6vw, 62px)",
                      border: `3px solid ${alpha(
                        theme.palette.common.white,
                        theme.palette.mode === "dark" ? 0.24 : 0.7
                      )}`,
                      boxShadow: theme.shadows[2],
                      opacity: avatarLoaded && !avatarError ? 1 : 0,
                      transition: "opacity 240ms ease, transform 240ms ease, box-shadow 240ms ease",
                      backgroundColor: alpha(theme.palette.text.primary, 0.12),
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      '&:hover, &:focus-visible': {
                        boxShadow: theme.shadows[3],
                        transform: "translateY(-2px)",
                        outline: "none",
                      },
                    }}
                  >
                    {user?.full_name?.[0] || user?.email?.[0] || "?"}
                  </Avatar>
                </Box>
              </Box>
            </Box>
          </Box>

          <Box
            flex={1}
            minWidth={0}
            display="flex"
            flexDirection="column"
            justifyContent="flex-start"
            mt={{ xs: mtStacked, md: 0 }}
            sx={{
              maxWidth: 1200,
              mx: { xs: "auto", md: 0 },
              width: "100%",
              position: "relative",
              zIndex: 1,
            }}
          >
            {edit ? (
              <Box
                className="profile-edit"
                sx={{
                  maxWidth: 760,
                  mx: "auto",
                  width: "100%",
                  pb: { xs: theme.spacing(6), md: theme.spacing(4) },
                }}
                aria-busy={saving}
              >
                <Stack spacing={3}>
                  <Stack spacing={1.5}>
                    <Typography
                      variant="overline"
                      color="text.secondary"
                      sx={{ letterSpacing: ".12em" }}
                    >
                      Основное
                    </Typography>
                    <Stack spacing={1.5}>
                      <TextField
                        label="Имя"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        fullWidth
                        inputProps={{ maxLength: 120 }}
                        disabled={saving}
                        sx={fieldSx}
                      />
                      <TextField
                        label="Email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        fullWidth
                        type="email"
                        disabled={saving}
                        sx={fieldSx}
                      />
                      <TextField
                        label="Telegram"
                        value={telegram}
                        onChange={(e) => setTelegram(e.target.value)}
                        fullWidth
                        helperText="Можно ввести @username или ссылку"
                        disabled={saving}
                        sx={fieldSx}
                      />
                    </Stack>
                  </Stack>

                  <Stack spacing={1.5}>
                    <Typography
                      variant="overline"
                      color="text.secondary"
                      sx={{ letterSpacing: ".12em" }}
                    >
                      Дополнительно
                    </Typography>
                    <Stack spacing={1.5}>
                      <TextField
                        label="О себе"
                        value={about}
                        onChange={(e) => setAbout(e.target.value)}
                        fullWidth
                        multiline
                        minRows={3}
                        disabled={saving}
                        sx={fieldSx}
                      />
                      <TextField
                        label="Достижения"
                        value={achievements}
                        onChange={(e) => setAchievements(e.target.value)}
                        fullWidth
                        multiline
                        minRows={2}
                        disabled={saving}
                        sx={fieldSx}
                      />
                    </Stack>
                  </Stack>

                  {user!.role === "teacher" && (
                    <Stack spacing={1.5}>
                      <Typography
                        variant="overline"
                        color="text.secondary"
                        sx={{ letterSpacing: ".12em" }}
                      >
                        Работа
                      </Typography>
                      <Stack spacing={1.5}>
                        <TextField
                          label="Кафедра/отдел"
                          value={department}
                          onChange={(e) => setDepartment(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Должность"
                          value={position}
                          onChange={(e) => setPosition(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                      </Stack>
                    </Stack>
                  )}

                  {user!.role === "student" && (
                    <Stack spacing={1.5}>
                      <Typography
                        variant="overline"
                        color="text.secondary"
                        sx={{ letterSpacing: ".12em" }}
                      >
                        Учёба
                      </Typography>
                      <Stack spacing={1.5}>
                        <TextField
                          label="Номер зачётной книжки"
                          value={recordBookNumber}
                          onChange={(e) => setRecordBookNumber(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Статус"
                          value={status}
                          onChange={(e) => setStatus(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Институт"
                          value={institute}
                          onChange={(e) => setInstitute(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Курс"
                          value={course}
                          onChange={(e) => setCourse(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Уровень образования"
                          value={educationLevel}
                          onChange={(e) => setEducationLevel(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Направление"
                          value={track}
                          onChange={(e) => setTrack(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Образовательная программа"
                          value={program}
                          onChange={(e) => setProgram(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                      </Stack>
                    </Stack>
                  )}

                  {user!.role !== "student" && user!.role !== "teacher" && (
                    <Stack spacing={1.5}>
                      <Typography
                        variant="overline"
                        color="text.secondary"
                        sx={{ letterSpacing: ".12em" }}
                      >
                        Профиль
                      </Typography>
                      <Stack spacing={1.5}>
                        <TextField
                          label="Статус"
                          value={status}
                          onChange={(e) => setStatus(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Кафедра/отдел"
                          value={department}
                          onChange={(e) => setDepartment(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                        <TextField
                          label="Должность"
                          value={position}
                          onChange={(e) => setPosition(e.target.value)}
                          fullWidth
                          disabled={saving}
                          sx={fieldSx}
                        />
                      </Stack>
                    </Stack>
                  )}
                </Stack>

                <Box
                  sx={{
                    position: { xs: "sticky", md: "static" },
                    bottom: { xs: 0, md: "auto" },
                    left: 0,
                    mt: theme.spacing(3),
                    backgroundColor: {
                      xs: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.9 : 0.95),
                      md: "transparent",
                    },
                    backdropFilter: { xs: "blur(14px)", md: "none" },
                    borderRadius: { xs: theme.shape.borderRadius * 1.5, md: 0 },
                    boxShadow: { xs: theme.shadows[2], md: "none" },
                    px: { xs: theme.spacing(2), md: 0 },
                    py: { xs: theme.spacing(2), md: 0 },
                    border: {
                      xs: `1px solid ${alpha(theme.palette.divider, 0.25)}`,
                      md: "none",
                    },
                  }}
                >
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={2}
                    sx={{ alignItems: { xs: "stretch", sm: "center" } }}
                  >
                    <Button
                      onClick={handleSave}
                      variant="contained"
                      disabled={saving}
                      startIcon={saving ? <CircularProgress size={18} /> : undefined}
                      sx={{ width: { xs: "100%", sm: "auto" } }}
                    >
                      {saving ? "Сохраняем…" : "Сохранить"}
                    </Button>
                    <Button
                      onClick={handleCancel}
                      variant="outlined"
                      disabled={saving}
                      sx={{ width: { xs: "100%", sm: "auto" } }}
                    >
                      Отмена
                    </Button>
                  </Stack>
                </Box>
              </Box>
            ) : (
              <Box
                sx={{
                  maxWidth: 960,
                  mx: "auto",
                  width: "100%",
                  display: "grid",
                  gridTemplateColumns: { xs: "1fr", md: "minmax(0,1fr) auto" },
                  gridTemplateAreas: {
                    xs: `"name"
                         "chips"
                         "np"
                         "acts"
                         "links"
                         "info"`,
                    md: `"name  name"
                         "chips chips"
                         "np    acts"
                         "links links"
                         "info  info"`,
                  },
                  columnGap: { xs: theme.spacing(2), md: theme.spacing(3) },
                  rowGap: { xs: theme.spacing(2.5), md: theme.spacing(3) },
                }}
              >
                <Tooltip
                  title={displayFullName}
                  disableHoverListener={!displayFullName || displayFullName.length < 18}
                >
                  <Typography
                    variant="h3"
                    fontWeight={800}
                    className="profile-name"
                    sx={{
                      gridArea: "name",
                      textAlign: { xs: "center", md: "left" },
                      lineHeight: 1.15,
                      fontSize: "clamp(1.3rem, 3vw, 2.6rem)",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      wordBreak: "break-word",
                    }}
                  >
                    {user!.full_name}
                  </Typography>
                </Tooltip>

                <Stack
                  direction="row"
                  spacing={1}
                  useFlexGap
                  flexWrap="wrap"
                  sx={{
                    gridArea: "chips",
                    justifyContent: { xs: "center", md: "flex-start" },
                    mb: { xs: 0, md: 0.5 },
                  }}
                >
                  <Chip
                    size="small"
                    className="glass--chip"
                    label={
                      user!.role === "teacher"
                        ? "Преподаватель"
                        : user!.role === "student"
                        ? "Студент"
                        : "Администратор"
                    }
                  />
                  {!!user!.course && user!.role === "student" && (
                    <Chip size="small" className="glass--chip" label={`Курс ${user!.course}`} />
                  )}
                  {!!user!.institute && (
                    <Chip size="small" className="glass--chip" label={user!.institute} />
                  )}
                </Stack>

                <Box sx={{ gridArea: "np" }}>
                  {spotifyConnected ? (
                    nowPlayingLoading && !nowPlaying ? (
                      <NowPlayingCardSkel />
                    ) : nowPlaying ? (
                      nowPlaying.is_playing ? (
                        <NowPlayingCard data={nowPlaying} />
                      ) : (
                        <NowPlayingEmpty />
                      )
                    ) : (
                      <NowPlayingEmpty />
                    )
                  ) : null}
                </Box>

                <Stack
                  sx={{ gridArea: "acts", minWidth: { md: 220 } }}
                  direction={{ xs: "row", sm: "row", md: "column" }}
                  spacing={{ xs: 1.5, md: 1.5 }}
                  alignItems="stretch"
                  justifyContent={{ xs: "center", md: "flex-start" }}
                  flexWrap={{ xs: "wrap", md: "nowrap" }}
                >
                  <Button
                    variant="outlined"
                    onClick={openQrModal}
                    startIcon={<QrCodeIcon />}
                    sx={{ flexBasis: { xs: "48%", md: "auto" }, minWidth: 140 }}
                  >
                    Показать QR
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={downloadPdfCard}
                    startIcon={<PictureAsPdfIcon />}
                    sx={{ flexBasis: { xs: "48%", md: "auto" }, minWidth: 140 }}
                  >
                    PDF визитка
                  </Button>
                  {shareAvailable && (
                    <Button
                      variant="outlined"
                      onClick={shareProfile}
                      startIcon={<ShareIcon />}
                      sx={{ flexBasis: { xs: "48%", md: "auto" }, minWidth: 140 }}
                      aria-label="Поделиться ссылкой на профиль"
                    >
                      Поделиться
                    </Button>
                  )}
                  <Button
                    variant="outlined"
                    onClick={downloadVcf}
                    startIcon={<DownloadIcon />}
                    sx={{ flexBasis: { xs: "48%", md: "auto" }, minWidth: 140 }}
                  >
                    Скачать .vcf
                  </Button>
                </Stack>

                {contactItems.length > 0 && (
                  <Stack
                    className="contact-links"
                    sx={{
                      gridArea: "links",
                      textAlign: { xs: "center", md: "left" },
                      mt: { xs: 0, md: 0.5 },
                      mb: theme.spacing(2),
                    }}
                    spacing={1.5}
                  >
                    {contactItems.map((item) => {
                      const isEmail = item.type === "email";
                      const icon = isEmail ? (
                        <EmailIcon color="primary" aria-hidden={false} fontSize="small" />
                      ) : (
                        <TelegramIcon color="primary" aria-hidden={false} fontSize="small" />
                      );
                      const copyLabel = isEmail ? "Скопировать email" : "Скопировать ник в Telegram";
                      const href = item.href;
                      const target = item.type === "telegram" ? "_blank" : undefined;
                      const rel = item.type === "telegram" ? "noreferrer" : undefined;
                      return (
                        <Stack
                          key={item.type}
                          direction="row"
                          alignItems="center"
                          spacing={1.2}
                          sx={{ width: "100%", maxWidth: "100%" }}
                        >
                          <Box aria-hidden sx={{ display: "flex", alignItems: "center" }}>
                            {icon}
                          </Box>
                          <Tooltip title={item.value} arrow disableInteractive>
                            <Typography
                              component={href ? "a" : "span"}
                              href={href}
                              target={target}
                              rel={rel}
                              sx={{
                                fontWeight: 600,
                                color: "inherit",
                                textDecoration: "none",
                                maxWidth: { xs: "70vw", md: "100%" },
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {item.value}
                            </Typography>
                          </Tooltip>
                          <Tooltip title={copyLabel} arrow>
                            <IconButton
                              size="small"
                              onClick={(e) => copy(item.value, e)}
                              aria-label={copyLabel}
                              sx={{
                                '&:focus-visible': {
                                  outline: `2px solid ${theme.palette.primary.main}`,
                                  outlineOffset: 2,
                                },
                              }}
                            >
                              <ContentCopyIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      );
                    })}
                  </Stack>
                )}

                <Accordion
                  disableGutters
                  sx={{
                    gridArea: "info",
                    backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.82 : 0.94),
                    borderRadius: theme.shape.borderRadius * 1.6,
                    boxShadow: theme.shadows[1],
                    border: `1px solid ${alpha(theme.palette.divider, 0.25)}`,
                    width: "100%",
                  }}
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: { xs: 2, md: 2.5 } }}>
                    <Typography fontWeight={800} sx={{ textAlign: { xs: "center", md: "left" }, width: "100%" }}>
                      Сведения
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: { xs: 2, md: 2.5 }, pb: { xs: 2.5, md: 3 } }}>
                    <Stack spacing={2.5}>
                      {infoItems.length > 0 && (
                        <Box
                          sx={{
                            display: "grid",
                            gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                            gap: { xs: theme.spacing(2), md: theme.spacing(2.5) },
                          }}
                        >
                          {infoItems.map((item) => (
                            <Box key={item.label}>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{
                                  textTransform: "uppercase",
                                  letterSpacing: ".08em",
                                  fontWeight: 600,
                                  display: "block",
                                }}
                              >
                                {item.label}
                              </Typography>
                              <Tooltip title={item.value} arrow disableInteractive>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    mt: 0.5,
                                    display: "-webkit-box",
                                    WebkitLineClamp: 3,
                                    WebkitBoxOrient: "vertical",
                                    overflow: "hidden",
                                  }}
                                >
                                  {item.value}
                                </Typography>
                              </Tooltip>
                            </Box>
                          ))}
                        </Box>
                      )}

                      {achievementsList.length > 0 && (
                        <Box>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              textTransform: "uppercase",
                              letterSpacing: ".08em",
                              fontWeight: 600,
                              display: "block",
                              mb: 1,
                            }}
                          >
                            Достижения
                          </Typography>
                          <Stack
                            direction="row"
                            spacing={1}
                            useFlexGap
                            flexWrap="wrap"
                            sx={{ justifyContent: { xs: "center", md: "flex-start" } }}
                          >
                            {achievementsList.map(({ name, issuer, date, url }, idx) => (
                              <Tooltip key={`${name}-${idx}`} title={name} arrow>
                                <Chip
                                  className="chip-gradient"
                                  label={name}
                                  clickable
                                  onClick={() => setAchOpen({ name, issuer, date, url })}
                                  sx={{
                                    '& .MuiChip-label': {
                                      whiteSpace: "normal",
                                      display: "block",
                                      textAlign: "left",
                                      lineHeight: 1.25,
                                    },
                                    '&:focus-visible': {
                                      outline: `2px solid ${theme.palette.primary.main}`,
                                      outlineOffset: 2,
                                    },
                                  }}
                                  aria-label={`Подробнее о достижении ${name}`}
                                />
                              </Tooltip>
                            ))}
                          </Stack>
                        </Box>
                      )}
                    </Stack>
                  </AccordionDetails>
                </Accordion>
              </Box>
            )}

  
              </Box>
            ) : (
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
        </Paper>

        <Dialog open={qrOpen} onClose={closeQrModal} maxWidth="xs" fullWidth>
          <DialogTitle>QR визитки</DialogTitle>
          <DialogContent
            sx={{ display: "grid", placeItems: "center", minHeight: 280 }}
            role="status"
            aria-live="polite"
          >
            {qrUrl && <img src={qrUrl} alt="QR-код визитки" style={{ width: 280, height: 280 }} />}
            {!qrUrl && !qrError && <CircularProgress aria-label="Генерация QR-кода" />}
            {!!qrError && (
              <Typography role="alert" sx={{ textAlign: "center" }}>
                {qrError}
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={closeQrModal}>Готово</Button>
          </DialogActions>
        </Dialog>

        <Dialog open={!!achOpen} onClose={() => setAchOpen(null)} maxWidth="sm" fullWidth>
          <DialogTitle>{achOpen?.name}</DialogTitle>
          <DialogContent>
            {!!achOpen?.issuer && (
              <Typography sx={{ mb: 1 }}>
                <b>Выдано:</b> {achOpen.issuer}
              </Typography>
            )}
            {!!achOpen?.date && (
              <Typography sx={{ mb: 1 }}>
                <b>Дата:</b> {achOpen.date}
              </Typography>
            )}
            {!!achOpen?.url && (
              <Typography sx={{ mb: 1 }}>
                <b>Подтверждение:</b>{" "}
                <a href={achOpen.url} target="_blank" rel="noreferrer">
                  {achOpen.url}
                </a>
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
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

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Person",
              name: user?.full_name || "",
              email: user?.email || "",
              jobTitle:
                user?.role === "teacher"
                  ? user?.position || ""
                  : user?.role === "student"
                    ? "Student"
                    : "Administrator",
              affiliation: user?.institute || user?.department || "",
              url: typeof window !== "undefined" ? window.location.href : "",
              image: getAvatarSrc() || "",
            }),
          }}
        />
      </Box>
    </>
  );
}
