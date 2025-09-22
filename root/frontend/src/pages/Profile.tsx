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
  TextField
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EmailIcon from "@mui/icons-material/Email";
import TelegramIcon from "@mui/icons-material/Telegram";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import useMediaQuery from "@mui/material/useMediaQuery";
import { resolveMediaUrl } from "@/utils/media";
import { jsPDF } from "jspdf";
import QRCode from "qrcode";

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || "";

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
  const [progress, setProgress] = useState<number>(data.progress_ms ?? 0);
  const startRef = useRef<number>(Date.now() - (data.progress_ms ?? 0));
  const rafRef = useRef<number | null>(null);

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

  const pct = data.duration_ms ? Math.max(0, Math.min(100, (progress / data.duration_ms) * 100)) : 0;
  const fmt = (ms?: number) => {
    if (ms == null) return "0:00";
    const s = Math.max(0, Math.floor(ms / 1000));
    const m = Math.floor(s / 60);
    const ss = String(s % 60).padStart(2, "0");
    return `${m}:${ss}`;
  };

  return (
    <Paper elevation={0} className="spotify-card nowplaying--spotify" sx={{ width: "100%" }}>
      <Avatar src={data.album_image_url || ""} variant="rounded" />
      <Box style={{ minWidth: 0 }}>
        <Typography className="spotify-title np-title" variant="body2">
          {data.track_name || "—"}
        </Typography>
        <Typography className="spotify-sub np-art" variant="caption">
          {(data.artists || []).join(", ")}
        </Typography>
        <Box sx={{ mt: 0.4 }}>
          <LinearProgress className="progress" variant="determinate" value={pct} />
        </Box>
      </Box>
      <Typography className="spotify-time np-time" variant="caption">
        {fmt(progress)} / {fmt(data.duration_ms)}
      </Typography>
    </Paper>
  );
});

export default function Profile() {
  const { user, loading, setUser } = useAuth();

  const [snack, setSnack] = useState<{ text: string; sev?: "success" | "info" | "warning" | "error" } | null>(null);
  const [avatarVersion, setAvatarVersion] = useState(Date.now());
  const [coverVersion, setCoverVersion] = useState(Date.now());
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const isTwoCol = useMediaQuery("(min-width:1400px)");
  const isMobile = useMediaQuery("(max-width:600px)");

  const [scrollY, setScrollY] = useState(0);

  const [qrOpen, setQrOpen] = useState(false);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [achOpen, setAchOpen] = useState<{ name: string; issuer?: string; date?: string; url?: string } | null>(null);

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
        api.get("/users/me").then(r => setUser(r.data)).catch(() => {});
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
        endTimerRef.current = window.setTimeout(() => { fetchNowPlaying(); }, Math.min(remain + 400, 20000));
      }
    } catch {} finally {
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

  const burstConfetti = useCallback((x?: number, y?: number) => {
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
      return { x: cx, y: cy, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed - 2, life: 60 + Math.random() * 40, size: 2 + Math.random() * 3, color: `hsl(${hue} 90% 55%)` };
    });
    let raf = 0;
    const step = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      parts.forEach(p => { p.vy += 0.12 * dpr; p.x += p.vx * dpr; p.y += p.vy * dpr; p.life -= 1; ctx.fillStyle = p.color; ctx.beginPath(); ctx.arc(p.x, p.y, p.size * dpr, 0, Math.PI * 2); ctx.fill(); });
      for (let i = parts.length - 1; i >= 0; i--) if (parts[i].life <= 0) parts.splice(i, 1);
      if (parts.length > 0) raf = requestAnimationFrame(step); else cancelAnimationFrame(raf);
    };
    step();
  }, [ensureConfettiSize]);

  useEffect(() => {
    if (snack && snack.sev === "success" && snack.text !== "Скопировано") burstConfetti();
  }, [snack, burstConfetti]);

  const copy = async (text: string, evt?: { clientX: number; clientY: number }) => {
    try { await navigator.clipboard?.writeText(text); }
    finally { setSnack({ text: "Скопировано", sev: "success" }); if (evt) burstConfetti(evt.clientX, evt.clientY); }
  };

  const buildVCard = () => {
    const u = user!;
    const lines = [
      "BEGIN:VCARD",
      "VERSION:4.0",
      `FN:${u.full_name || ""}`,
      u.email ? `EMAIL:${u.email}` : "",
      (u.institute || u.department) ? `ORG:${u.institute || u.department}` : "",
      (u.position || u.status) ? `TITLE:${u.position || u.status}` : "",
      (typeof window !== "undefined" ? `URL:${window.location.href}` : "")
    ].filter(Boolean);
    lines.push("END:VCARD");
    return lines.join("\n");
  };

  const openQrModal = useCallback(async () => {
    try {
      const dataUrl = await QRCode.toDataURL(buildVCard(), { width: 280, errorCorrectionLevel: "M" });
      setQrUrl(dataUrl);
    } catch {
      setQrUrl(null);
    } finally {
      setQrOpen(true);
    }
  }, [user]);

  const downloadPdfCard = () => {
    const u = user!;
    const makeCanvas = (w: number, h: number) => { const c = document.createElement("canvas"); c.width = w; c.height = h; const ctx = c.getContext("2d")!; return { c, ctx }; };
    const roundedRect = (ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) => {
      ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
      ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
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

    const { c, ctx } = makeCanvas(W, H) as { c: HTMLCanvasElement; ctx: CanvasRenderingContext2D };
    (ctx as any).imageSmoothingEnabled = true;
    (ctx as any).imageSmoothingQuality = "high";
    const g = (ctx as CanvasRenderingContext2D).createLinearGradient(0, 0, W, H);
    g.addColorStop(0, "#ffffff"); g.addColorStop(1, "#f2f6ff");
    (ctx as any).fillStyle = g; (ctx as any).fillRect(0, 0, W, H);

    (ctx as any).save(); (ctx as any).shadowColor = "rgba(0,0,0,.12)"; (ctx as any).shadowBlur = 28; (ctx as any).shadowOffsetY = 10; (ctx as any).fillStyle = "#ffffff";
    roundedRect(ctx as any, 22 * scale, 22 * scale, W - 44 * scale, H - 44 * scale, 22 * scale); (ctx as any).fill(); (ctx as any).restore();

    const padX = Math.round(42 * scale);
    const padY = Math.round(38 * scale);
    const contentW = W - padX * 2;
    const leftW = Math.round(contentW * 0.62);
    const rightX = padX + leftW;
    const family = "Inter, Manrope, Arial, sans-serif";

    const fitText = (text: string, maxWidth: number, weight: number, baseSize: number) => {
      let size = baseSize;
      while (size > 10) { (ctx as any).font = `${weight} ${size}px ${family}`; if ((ctx as any).measureText(text).width <= maxWidth) break; size -= 1; }
      return size;
    };

    const isStudent = user!.role === "student";
    const instituteLine = isStudent ? (user!.institute || "") : (user!.department || "");
    const programOrTitleLine = isStudent ? (user!.program || user!.track || user!.status || "Студент") : (user!.position || user!.status || "");
    const emailText = (user!.email || "");
    const tg = (user!.telegram || "");

    const avatarReserve = Math.round(72 * scale);
    const nameTop = padY + avatarReserve + Math.round(14 * scale);

    let nameSize = fitText(user!.full_name || "", leftW, 700, Math.round(34 * scale));
    (ctx as any).font = `700 ${nameSize}px ${family}`;
    (ctx as any).fillStyle = "#111";
    (ctx as any).textBaseline = "top";
    (ctx as any).fillText(user!.full_name || "", padX, nameTop);

    let y = nameTop + nameSize + Math.round(8 * scale);
    const lineHeight = Math.round(18 * scale);
    const blockGap = Math.round(8 * scale);

    if (isStudent) {
      (ctx as any).font = `400 ${Math.round(14 * scale)}px ${family}`;
      if (instituteLine) { (ctx as any).fillStyle = "#666"; (ctx as any).fillText(String(instituteLine), padX, y); y += lineHeight + blockGap; }
      const progSize = fitText(String(programOrTitleLine || ""), leftW, 400, Math.round(16 * scale));
      (ctx as any).font = `400 ${progSize}px ${family}`;
      if (programOrTitleLine) { (ctx as any).fillStyle = "#444"; (ctx as any).fillText(String(programOrTitleLine), padX, y); y += Math.round(progSize + 6) + blockGap; }
    } else {
      const titleSize = fitText(String(programOrTitleLine || ""), leftW, 400, Math.round(16 * scale));
      (ctx as any).font = `400 ${titleSize}px ${family}`;
      if (programOrTitleLine) { (ctx as any).fillStyle = "#444"; (ctx as any).fillText(String(programOrTitleLine), padX, y); y += Math.round(titleSize + 6) + blockGap; }
      (ctx as any).font = `400 ${Math.round(14 * scale)}px ${family}`;
      if (instituteLine) { (ctx as any).fillStyle = "#666"; (ctx as any).fillText(String(instituteLine), padX, y); y += lineHeight + blockGap; }
    }

    (ctx as any).fillStyle = "#333";
    if (emailText) { (ctx as any).fillText(String(emailText), padX, y); y += lineHeight + blockGap; }
    if (tg) { (ctx as any).fillText(String(tg), padX, y); y += lineHeight + blockGap; }

    const qrSide = Math.round(118 * scale);
    const qrX = rightX + Math.round((contentW - leftW - qrSide) / 2);
    const qrY = padY + Math.round(10 * scale);

    const drawAndSave = () => {
      const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: [cardPt.w, cardPt.h] });
      const data = (c as HTMLCanvasElement).toDataURL("image/jpeg", 0.95);
      const pageW = (doc as any).internal.pageSize.getWidth();
      const pageH = (doc as any).internal.pageSize.getHeight();
      doc.addImage(data, "JPEG", 0, 0, pageW, pageH);
      const fname = (user!.full_name || "contact").replace(/\s+/g, "_") + ".pdf";
      doc.save(fname);
    };

    QRCode.toDataURL(buildVCard(), { width: qrSide, margin: 1 })
      .then((qrData: string) => loadImg(qrData))
      .then(qrImg => { (ctx as CanvasRenderingContext2D).drawImage(qrImg, qrX, qrY, qrSide, qrSide); })
      .catch(() => { setSnack({ text: "Не удалось сгенерировать QR — сохраняю без QR", sev: "warning" }); })
      .then(async () => {
        const src = getAvatarSrc();
        if (!src) return null;
        try {
          const dataUrl = await fetchAsDataUrl(src);
          return await loadImg(dataUrl);
        } catch {
          return null;
        }
      })
      .then(img => {
        const size = avatarReserve;
        const ax = padX;
        const ay = padY;

        if (img) {
          (ctx as CanvasRenderingContext2D).save();
          (ctx as CanvasRenderingContext2D).beginPath();
          (ctx as CanvasRenderingContext2D).arc(ax + size / 2, ay + size / 2, size / 2, 0, Math.PI * 2);
          (ctx as CanvasRenderingContext2D).closePath();
          (ctx as CanvasRenderingContext2D).clip();
          (ctx as CanvasRenderingContext2D).drawImage(img as HTMLImageElement, ax, ay, size, size);
          (ctx as CanvasRenderingContext2D).restore();
        } else {
          (ctx as CanvasRenderingContext2D).save();
          (ctx as any).fillStyle = "#e5e7eb";
          (ctx as any).beginPath();
          (ctx as any).arc(ax + size / 2, ay + size / 2, size / 2, 0, Math.PI * 2);
          (ctx as any).fill();
          (ctx as any).fillStyle = "#111827";
          (ctx as any).font = `700 ${Math.round(size * 0.42)}px Inter, Arial, sans-serif`;
          (ctx as any).textAlign = "center";
          (ctx as any).textBaseline = "middle";
          (ctx as any).fillText((user?.full_name?.[0] || "").toUpperCase(), ax + size / 2, ay + size / 2 + 2);
          (ctx as CanvasRenderingContext2D).restore();
        }

        return loadImg((guuLogo as unknown as string)).catch(() => null);
      })
      .then(logoImg => {
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
          const ly = Math.min(lyTop, (H - 22 * scale) - lh - safeMargin);
          (ctx as CanvasRenderingContext2D).drawImage(imgEl, lx, ly, lw, lh);
        }
      })
      .finally(() => {
        try { drawAndSave(); } catch { setSnack({ text: "Ошибка при сохранении PDF", sev: "error" }); }
      });
  };

  const telegramHref = useMemo(() => {
    const t = user?.telegram || "";
    if (!t) return "";
    let v = String(t).trim();
    if (v.startsWith("http")) return v;
    if (v.startsWith("@")) v = v.slice(1);
    return `https://t.me/${v}`;
  }, [user?.telegram]);

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
        position
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
        else if (Array.isArray(e.response.data.detail)) message = e.response.data.detail.map((err: any) => err.msg).join("; ");
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
  const avatarBottom = isTwoCol ? `-${Math.round(avatarPx * 0.32)}px` : `-${Math.round(avatarPx * 0.5)}px`;
  const mtStacked = `${Math.round(avatarPx * 0.36)}px`;
  const mtRow = `${Math.max(24, Math.round(avatarPx * 0.3))}px`;

  return (
    <>
      <Box sx={{ position: "fixed", left: 0, top: 0, width: "100vw", height: "100vh", zIndex: -1, backgroundImage: `linear-gradient(120deg, var(--hero-grad-start), var(--hero-grad-end)), url(${profileBg})`, backgroundRepeat: "no-repeat, repeat", backgroundSize: "cover, 480px", backgroundAttachment: "fixed, fixed" }} />
      <Box maxWidth="100vw" mx="auto" mt={0} width="100vw" minHeight="100svh" px={0}>
        <Paper
          ref={containerRef}
          className="glass glass--panel profile-page"
          sx={{
            p: { xs: 1.6, sm: 2.4, md: 4, lg: 6 },
            borderRadius: 0,
            width: "100vw",
            minHeight: "100svh",
            display: "flex",
            flexDirection: { xs: "column", md: isTwoCol ? "row" : "column" },
            alignItems: { xs: "stretch", md: isTwoCol ? "flex-start" : "stretch" },
            rowGap: { xs: 2, md: 2 },
            columnGap: { xs: 2, sm: 2, md: 3, lg: 3, xl: 3 },
            position: "relative"
          }}
        >
          <Box
            width={{ xs: "100%", md: isTwoCol ? 430 : "100%" }}
            display="flex"
            flexDirection="column"
            minWidth={0}
            sx={{ mx: { xs: "auto", md: 0 } }}
          >
            <Box sx={{ position: "relative", width: "100%" }}>
              <Box
                sx={{
                  width: "100%",
                  height: { xs: 210, sm: 260, md: 300, lg: 320 },
                  minHeight: 60,
                  position: "relative",
                  borderRadius: { xs: 2, sm: 2.3, md: 3 },
                  mb: 0,
                  boxShadow: "var(--shadow-2)",
                  overflow: "visible"
                }}
              >
                <Box sx={{ position: "absolute", inset: 0, background: `url(${getCoverSrc()}?v=${coverVersion}) center/cover no-repeat`, transform: `translateY(${coverParallax}px) scale(${coverScale})`, transition: reduceMotion ? "none" : "transform var(--anim-med)", borderRadius: { xs: 2, sm: 2.3, md: 3 } }} />
                <Box sx={{ position: "absolute", inset: 0, borderRadius: { xs: 2, sm: 2.3, md: 3 }, background: "linear-gradient(180deg, rgba(0,0,0,0) 55%, rgba(0,0,0,.28) 100%)", pointerEvents: "none" }} />
              </Box>

              <Box
                sx={{
                  position: "absolute",
                  left: { xs: "50%", md: isTwoCol ? 28 : "50%" },
                  transform: { xs: "translateX(-50%)", md: isTwoCol ? "none" : "translateX(-50%)" } as any,
                  bottom: avatarBottom,
                  width: avatarSize,
                  height: avatarSize,
                  borderRadius: "50%",
                  p: 0,
                  background: "transparent",
                  boxShadow: "0 12px 36px rgba(0,0,0,.22)",
                  zIndex: 2
                }}
              >
                <Box sx={{ width: "100%", height: "100%", borderRadius: "50%", p: "6px", background: "var(--card-bg)" }}>
                  <Box>
                    <Avatar src={getAvatarSrc()} alt={user?.full_name} sx={{ width: "100%", height: "100%", fontSize: "clamp(28px, 6vw, 62px)" }}>
                      {user?.full_name?.[0]}
                    </Avatar>
                  </Box>
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
            sx={{ maxWidth: 1200, mx: { xs: "auto", md: 0 }, width: "100%", position: "relative", zIndex: 1, ml: { xl: -10 }, alignSelf: { md: "flex-start" } }}
          >
            {edit ? (
              <Box sx={{ maxWidth: 760, mx: "auto", width: "100%" }} className="profile-edit">
                <Stack spacing={2}>
                  <TextField label="Имя" value={fullName} onChange={e => setFullName(e.target.value)} fullWidth inputProps={{ maxLength: 120 }} />
                  <TextField label="Email" value={email} onChange={e => setEmail(e.target.value)} fullWidth type="email" />
                  <TextField label="Telegram" value={telegram} onChange={e => setTelegram(e.target.value)} fullWidth helperText="Можно ввести @username или ссылку" />
                  {user!.role === "teacher" && (
                    <>
                      <TextField label="Кафедра/отдел" value={department} onChange={e => setDepartment(e.target.value)} fullWidth />
                      <TextField label="Должность" value={position} onChange={e => setPosition(e.target.value)} fullWidth />
                    </>
                  )}
                  {user!.role === "student" && (
                    <>
                      <TextField label="О себе" value={about} onChange={e => setAbout(e.target.value)} fullWidth multiline minRows={3} />
                      <TextField label="Номер зачётной книжки" value={recordBookNumber} onChange={e => setRecordBookNumber(e.target.value)} fullWidth />
                      <TextField label="Статус" value={status} onChange={e => setStatus(e.target.value)} fullWidth />
                      <TextField label="Институт" value={institute} onChange={e => setInstitute(e.target.value)} fullWidth />
                      <TextField label="Курс" value={course} onChange={e => setCourse(e.target.value)} fullWidth />
                      <TextField label="Уровень образования" value={educationLevel} onChange={e => setEducationLevel(e.target.value)} fullWidth />
                      <TextField label="Направление" value={track} onChange={e => setTrack(e.target.value)} fullWidth />
                      <TextField label="Образовательная программа" value={program} onChange={e => setProgram(e.target.value)} fullWidth />
                      <TextField label="Достижения" value={achievements} onChange={e => setAchievements(e.target.value)} fullWidth multiline minRows={2} />
                    </>
                  )}
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ alignItems: { xs: "stretch", sm: "center" } }}>
                    <Button onClick={handleSave} variant="contained" disabled={saving} sx={{ width: { xs: "100%", sm: "auto" } }}>
                      {saving ? "СОХРАНЯЕМ..." : "СОХРАНИТЬ"}
                    </Button>
                    <Button onClick={handleCancel} variant="outlined" sx={{ width: { xs: "100%", sm: "auto" } }}>ОТМЕНА</Button>
                  </Stack>
                </Stack>
              </Box>
            ) : (
              <Box
                sx={{
                  maxWidth: 920,
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
                         "info  info"`
                  },
                  columnGap: { xs: 1, md: 1.2 },
                  rowGap: { xs: 1, md: 1.1 }
                }}
              >
                <Typography
                  variant="h3"
                  fontWeight={800}
                  fontSize="clamp(1.28rem, 3vw, 2.5rem)"
                  className="profile-name"
                  sx={{ gridArea: "name", textAlign: { xs: "center", md: "left" }, lineHeight: 1.15, mt: { xs: 0.25, md: 0 }, mb: 0.3 }}
                >
                  {user!.full_name}
                </Typography>

                <Stack
                  direction="row"
                  spacing={1}
                  useFlexGap
                  flexWrap="wrap"
                  sx={{ gridArea: "chips", mb: 1.1, justifyContent: { xs: "center", md: "flex-start" } }}
                >
                  <Chip size="small" className="glass--chip" label={user!.role === "teacher" ? "Преподаватель" : user!.role === "student" ? "Студент" : "Администратор"} />
                  {!!user!.course && user!.role === "student" && <Chip size="small" className="glass--chip" label={`Курс ${user!.course}`} />}
                  {!!user!.institute && <Chip size="small" className="glass--chip" label={user!.institute} />}
                </Stack>

                <Box sx={{ gridArea: "np" }}>
                  {spotifyConnected && nowPlaying ? <NowPlayingCard data={nowPlaying} /> : <Box />}
                </Box>

                <Stack
                  sx={{ gridArea: "acts", minWidth: { md: 180 } }}
                  direction={{ xs: "row", md: "column" }}
                  spacing={1}
                  alignItems={{ xs: "stretch", md: "stretch" }}
                  justifyContent={{ xs: "center", md: "flex-start" }}
                >
                  <Button size="small" variant="outlined" onClick={openQrModal} sx={{ width: { xs: "50%", sm: "auto" } }}>
                    Показать QR
                  </Button>
                  <Button size="small" variant="outlined" onClick={downloadPdfCard} sx={{ width: { xs: "50%", sm: "auto" } }}>
                    PDF визитка
                  </Button>
                </Stack>

                <Stack
                  className="contact-links"
                  sx={{ gridArea: "links", textAlign: { xs: "center", md: "left" }, mt: 0.3, mb: 1.8 }}
                  direction={{ xs: "column", md: "row" }}
                  alignItems={{ xs: "center", md: "center" }}
                  spacing={2}
                >
                  <Stack direction="row" alignItems="center" spacing={1.2}>
                    <EmailIcon color="primary" aria-hidden />
                    <Typography sx={{ fontWeight: 600 }}>
                      <a href={`mailto:${user!.email}`}>{user!.email}</a>
                    </Typography>
                    <Tooltip title="Скопировать email">
                      <IconButton size="small" onClick={(e) => copy(user!.email, e)} aria-label="Скопировать email">
                        <ContentCopyIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>

                  {user!.telegram && (
                    <Stack direction="row" alignItems="center" spacing={1.2}>
                      <TelegramIcon color="primary" aria-hidden />
                      <Typography sx={{ fontWeight: 600 }}>
                        <a href={telegramHref} target="_blank" rel="noreferrer">{user!.telegram}</a>
                      </Typography>
                      <Tooltip title="Скопировать ник">
                        <IconButton size="small" onClick={(e) => copy(user!.telegram!, e)} aria-label="Скопировать ник в Telegram">
                          <ContentCopyIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  )}
                </Stack>

                <Accordion
                  disableGutters
                  sx={{ gridArea: "info", background: "var(--card-bg)", borderRadius: 2, boxShadow: "var(--shadow-1)", width: "100%" }}
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: 1.5 }}>
                    <Typography fontWeight={800} sx={{ textAlign: { xs: "center", md: "left" }, width: "100%" }}>
                      Сведения
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <List sx={{ pl: 0 }}>
                      {!!user!.about && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>О себе:</b> {user!.about}</span>} /></ListItem>)}
                      {!!user!.status && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>Статус:</b> {user!.status}</span>} /></ListItem>)}
                      {!!user!.record_book_number && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>Номер зачётной книжки:</b> {user!.record_book_number}</span>} /></ListItem>)}
                      {!!user!.education_level && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>Уровень образования:</b> {user!.education_level}</span>} /></ListItem>)}
                      {!!user!.track && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>Направление:</b> {user!.track}</span>} /></ListItem>)}
                      {!!user!.program && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>Образовательная программа:</b> {user!.program}</span>} /></ListItem>)}
                      {!!user!.department && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>Кафедра/отдел:</b> {user!.department}</span>} /></ListItem>)}
                      {!!user!.position && (<ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}><ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon><ListItemText primary={<span><b>Должность:</b> {user!.position}</span>} /></ListItem>)}
                      {!!user!.achievements && (
                        <>
                          <ListItem sx={{ pl: 0, py: 0.5, alignItems: "flex-start", borderRadius: 2 }}>
                            <ListItemIcon sx={{ minWidth: 30, mt: 0.3 }}><FiberManualRecordIcon fontSize="small" /></ListItemIcon>
                            <ListItemText primary={<span><b>Достижения:</b></span>} />
                          </ListItem>
                          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ pl: 0, mt: 0.5, justifyContent: { xs: "center", md: "flex-start" } }}>
                            {String(user!.achievements || "").split(/[,;\n]/).map((str, i) => {
                              const raw = String(str || "").trim();
                              if (!raw) return null;
                              const [name, issuer, date, url] = raw.split("|").map(s => s.trim());
                              return (
                                <Chip key={i} className="chip-gradient" label={name} clickable onClick={() => setAchOpen({ name, issuer, date, url })} sx={{ "& .MuiChip-label": { whiteSpace: "normal", display: "block" } }} />
                              );
                            })}
                          </Stack>
                        </>
                      )}
                    </List>
                  </AccordionDetails>
                </Accordion>
              </Box>
            )}
          </Box>

          <canvas ref={confettiRef} style={{ position: "fixed", left: 0, top: 0, width: "100vw", height: "100vh", pointerEvents: "none", zIndex: 2147483000 }} />
        </Paper>

        <Dialog open={qrOpen} onClose={() => setQrOpen(false)} maxWidth="xs" fullWidth>
          <DialogTitle>QR визитки</DialogTitle>
          <DialogContent sx={{ display: "grid", placeItems: "center" }}>
            {qrUrl ? <img src={qrUrl} alt="QR" style={{ width: 280, height: 280 }} /> : <Typography>Установите пакет qrcode или скачайте .vcf</Typography>}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setQrOpen(false)}>Готово</Button>
          </DialogActions>
        </Dialog>

        <Dialog open={!!achOpen} onClose={() => setAchOpen(null)} maxWidth="sm" fullWidth>
          <DialogTitle>{achOpen?.name}</DialogTitle>
          <DialogContent>
            {!!achOpen?.issuer && <Typography sx={{ mb: 1 }}><b>Выдано:</b> {achOpen.issuer}</Typography>}
            {!!achOpen?.date && <Typography sx={{ mb: 1 }}><b>Дата:</b> {achOpen.date}</Typography>}
            {!!achOpen?.url && (
              <Typography sx={{ mb: 1 }}>
                <b>Подтверждение:</b> <a href={achOpen.url} target="_blank" rel="noreferrer">{achOpen.url}</a>
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setAchOpen(null)}>Закрыть</Button>
          </DialogActions>
        </Dialog>

        <Snackbar open={!!snack} autoHideDuration={2600} onClose={() => setSnack(null)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
          <Alert onClose={() => setSnack(null)} severity={snack?.sev || "info"} variant="filled" sx={{ width: "100%" }}>
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
              jobTitle: user?.role === "teacher" ? (user?.position || "") : (user?.role === "student" ? "Student" : "Administrator"),
              affiliation: user?.institute || user?.department || "",
              url: typeof window !== "undefined" ? window.location.href : "",
              image: getAvatarSrc() || ""
            })
          }}
        />
      </Box>
    </>
  );
}