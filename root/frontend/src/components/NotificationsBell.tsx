import { useEffect, useMemo, useRef, useState, memo, useCallback } from "react";
import { Badge, Box, Button, Divider, IconButton, List, ListItemButton, ListItemIcon, ListItemText, Popover, Stack, Typography, Avatar, Tooltip, Skeleton } from "@mui/material";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import EventNoteIcon from "@mui/icons-material/EventNote";
import ArticleIcon from "@mui/icons-material/Article";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import { useNotifications } from "@/hooks/useNotifications";
import { useNavigate } from "react-router-dom";

const rtf = new Intl.RelativeTimeFormat("ru-RU", { numeric: "auto" });
function formatRelTime(iso: string, nowMs: number) {
  const ts = new Date(iso).getTime();
  const diffSec = Math.round((ts - nowMs) / 1000);
  const abs = Math.abs(diffSec);
  if (abs < 60) return rtf.format(Math.sign(diffSec) * Math.round(abs), "second");
  if (abs < 3600) return rtf.format(Math.sign(diffSec) * Math.round(abs / 60), "minute");
  if (abs < 86400) return rtf.format(Math.sign(diffSec) * Math.round(abs / 3600), "hour");
  return rtf.format(Math.sign(diffSec) * Math.round(abs / 86400), "day");
}

function pickIcon(t?: string) {
  if (t === "event") return <EventNoteIcon fontSize="small" />;
  if (t === "news") return <ArticleIcon fontSize="small" />;
  return <InfoOutlinedIcon fontSize="small" />;
}

type Notif = { id: string | number; title: string; body?: string; type?: string; url?: string; created_at: string; read?: boolean; avatar_url?: string; icon?: string; };

const TimeAgo = memo(function TimeAgo({ date }: { date: string }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 30000);
    return () => clearInterval(id);
  }, []);
  const now = Date.now();
  return <>{formatRelTime(date, now)}</>;
});

const NotificationItem = memo(function NotificationItem({ n, onOpen }: { n: Notif; onOpen: (n: Notif, e: React.MouseEvent | React.KeyboardEvent) => void; }) {
  const unreadDot = !n.read ? <FiberManualRecordIcon sx={{ fontSize: 10, color: "var(--nav-link)" }} /> : null;
  const leading = n.avatar_url ? <Avatar src={n.avatar_url} alt="" imgProps={{ loading: "lazy", referrerPolicy: "no-referrer" }} sx={{ width: 28, height: 28 }} /> : pickIcon(n.type);
  return (
    <ListItemButton
      role="listitem"
      onClick={(e) => onOpen(n, e)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(n, e); } }}
      selected={!n.read}
      sx={{ alignItems: "flex-start", gap: 1, py: 1, opacity: n.read ? 0.75 : 1, "&:hover": { opacity: 1 } }}
      aria-label={n.title}
    >
      <ListItemIcon sx={{ minWidth: 34, mt: 0.2 }}>{leading}</ListItemIcon>
      <ListItemText
        primary={
          <Stack direction="row" alignItems="center" spacing={0.8}>
            {!n.read && unreadDot}
            <Typography sx={{ fontWeight: n.read ? 600 : 800, lineHeight: 1.2 }}>{n.title}</Typography>
          </Stack>
        }
        secondary={
          <Stack direction="row" spacing={1} alignItems="center">
            {n.body && <Typography variant="body2" color="text.secondary" sx={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{n.body}</Typography>}
            {n.url && <OpenInNewIcon fontSize="inherit" />}
          </Stack>
        }
      />
      <Typography variant="caption" sx={{ whiteSpace: "nowrap", ml: 1 }} title={new Date(n.created_at).toLocaleString()}><TimeAgo date={n.created_at} /></Typography>
    </ListItemButton>
  );
});

export default function NotificationsBell({ iconColor = "inherit" }: { iconColor?: string }) {
  const { items, loading, unreadCount, hasMore, loadMore, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);
  const scrollBoxRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();
  const [loadingMore, setLoadingMore] = useState(false);
  const popoverId = "notifications-popover";
  const titleId = "notifications-title";
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    if (!hasMore) return;
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        const vis = entries.some((e) => e.isIntersecting);
        if (vis && !loadingMore) {
          setLoadingMore(true);
          Promise.resolve(loadMore()).finally(() => setLoadingMore(false));
        }
      },
      { root: scrollBoxRef.current, rootMargin: "100px 0px", threshold: 0.01 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [open, hasMore, loadMore, loadingMore]);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      const first = listRef.current?.querySelector<HTMLElement>('[role="button"],[tabindex],button,a,[href],input,select,textarea');
      first?.focus();
    }, 10);
    return () => clearTimeout(t);
  }, [open]);

  useEffect(() => {
    const sw = navigator.serviceWorker;
    if (!sw) return;
    const onMsg = (e: MessageEvent) => {
      const data = e.data || {};
      if (data.type === "NOTIFICATION_MARK_READ" && data.id != null) {
        try { markRead(data.id); } catch {}
      }
      if (data.type === "PUSH_NOTIFICATION") {
        try { if ("setAppBadge" in navigator && typeof (navigator as any).setAppBadge === "function") {} } catch {}
      }
    };
    sw.addEventListener("message", onMsg);
    return () => sw.removeEventListener("message", onMsg);
  }, [markRead]);

  const handleOpenItem = useCallback((n: Notif, e: React.MouseEvent | React.KeyboardEvent) => {
    markRead(n.id);
    if (!n.url) { setOpen(false); return; }
    const isExternal = /^https?:\/\//i.test(n.url);
    const mouse = e as React.MouseEvent;
    const kb = e as React.KeyboardEvent;
    const isMiddle = (mouse as any).button === 1;
    const newTab = mouse.ctrlKey || mouse.metaKey || isMiddle;
    if (isExternal) {
      if (newTab) window.open(n.url, "_blank", "noopener,noreferrer");
      else window.open(n.url, "_self");
    } else {
      if (newTab) window.open(n.url, "_blank");
      else navigate(n.url);
    }
    setOpen(false);
  }, [markRead, navigate]);

  const content = useMemo(() => {
    if (loading && !items.length) {
      return (
        <Stack spacing={1.6} sx={{ py: 2.5, px: 1.6 }} role="status" aria-live="polite">
          {Array.from({ length: 4 }).map((_, idx) => (
            <Stack key={idx} direction="row" spacing={1.4} alignItems="flex-start">
              <Skeleton variant="circular" width={32} height={32} />
              <Box sx={{ flex: 1 }}>
                <Skeleton variant="text" height={20} width={idx % 2 === 0 ? "94%" : "82%"} />
                <Skeleton variant="text" height={16} width={idx % 2 === 0 ? "72%" : "64%"} sx={{ mt: 0.4 }} />
              </Box>
            </Stack>
          ))}
        </Stack>
      );
    }
    if (items.length === 0) {
      return (
        <Stack alignItems="center" justifyContent="center" sx={{ py: 4, color: "text.secondary" }} role="status" aria-live="polite">
          <NotificationsNoneIcon />
          <Typography mt={1}>Здесь пока пусто</Typography>
        </Stack>
      );
    }
    return (
      <>
        <List ref={listRef} disablePadding role="list" aria-labelledby={titleId} sx={{ py: 0 }}>
          {items.map((n) => (
            <NotificationItem key={n.id} n={n} onOpen={handleOpenItem} />
          ))}
        </List>
        {(hasMore || loadingMore) && (
          <Box sx={{ p: 1.2 }}>
            {loadingMore ? (
              <Stack spacing={0.8} sx={{ py: 1 }}>
                <Skeleton variant="text" height={18} width="60%" />
                <Skeleton variant="text" height={18} width="48%" />
              </Stack>
            ) : (
              <Button fullWidth variant="outlined" onClick={loadMore} aria-busy={loadingMore}>Показать ещё</Button>
            )}
            <div ref={sentinelRef} aria-hidden="true" style={{ height: 1 }} />
          </Box>
        )}
      </>
    );
  }, [items, loading, hasMore, loadingMore, loadMore, handleOpenItem]);

  return (
    <>
      <IconButton
        ref={anchorRef}
        onClick={() => setOpen((v) => !v)}
        aria-label={`Открыть уведомления${unreadCount > 0 ? `, непрочитанных: ${unreadCount}` : ", непрочитанных нет"}`}
        aria-haspopup="dialog"
        aria-controls={open ? popoverId : undefined}
        aria-expanded={open ? "true" : "false"}
        sx={{ ml: { xs: 0.5, sm: 1 }, color: iconColor }}
      >
        <Badge color="error" badgeContent={unreadCount} max={99} overlap="circular">
          <NotificationsNoneIcon />
        </Badge>
      </IconButton>

      <Popover
        id={popoverId}
        open={open}
        onClose={() => setOpen(false)}
        anchorEl={anchorRef.current}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        transformOrigin={{ vertical: "top", horizontal: "center" }}
        PaperProps={{ role: "dialog", "aria-modal": "true", "aria-labelledby": titleId, sx: { width: 380, maxWidth: "92vw", bgcolor: "var(--card-bg)" } }}
        disableRestoreFocus={false}
      >
        <Box sx={{ p: 1.2 }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Typography id={titleId} fontWeight={800}>Уведомления</Typography>
            <Tooltip title="Отметить все как прочитанные">
              <span>
                <Button size="small" startIcon={<DoneAllIcon />} onClick={markAllRead} disabled={!unreadCount} aria-disabled={!unreadCount}>
                  Прочитаны
                </Button>
              </span>
            </Tooltip>
          </Stack>
        </Box>
        <Divider />
        <Box ref={scrollBoxRef} sx={{ maxHeight: 444, overflow: "auto" }}>{content}</Box>
      </Popover>
    </>
  );
}