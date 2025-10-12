import {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
  ChangeEvent,
  FocusEvent,
} from "react";
import { isAxiosError } from "axios";
import { useAuth, currentUserQueryKey, fetchCurrentUser } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { usePushPreferences } from "@/hooks/usePushPreferences";
import { nowPlayingQueryKey } from "@/hooks/useNowPlaying";
import api from "../api/client";
import {
  Box,
  Paper,
  Tabs,
  Tab,
  Stack,
  Typography,
  Button,
  Chip,
  Snackbar,
  Alert,
  RadioGroup,
  FormControlLabel,
  Radio,
  Divider,
  Avatar,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress
} from "@mui/material";
import { useColorScheme, styled, alpha, darken, lighten } from "@mui/material/styles";
import SettingsIcon from "@mui/icons-material/Settings";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows";
import LogoutIcon from "@mui/icons-material/Logout";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ImageIcon from "@mui/icons-material/Image";
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders";
const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL;
import spotifyLogo from "@/assets/spotify_icon.png";
import { addVersionParam, resolveMediaUrl } from "@/utils/media";
import { sanitizeSpotifyAuthorizeUrl } from "@/utils/spotify";

type ThemeMode = "system" | "light" | "dark";

const DEFAULT_DND_START = "22:00";
const DEFAULT_DND_END = "07:00";

const toInputTime = (value: unknown): string => {
  if (!value) return "";
  const str = String(value);
  const match = str.match(/^(\d{2}:\d{2})/);
  return match ? match[1] : "";
};

const toServerTime = (value: string | null): string | null => {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^\d{2}:\d{2}$/.test(trimmed)) return `${trimmed}:00`;
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) return trimmed;
  return trimmed;
};

const ModernSwitch = styled("span")(({ theme }) => {
  const on = theme.palette.primary.main;
  const trackBg = theme.palette.mode === "dark"
    ? alpha("#fff", 0.12)
    : alpha("#000", 0.08);
  const trackBorder = theme.palette.mode === "dark"
    ? alpha("#fff", 0.24)
    : alpha("#000", 0.12);
  const ring = alpha(on, 0.35);

  return {
    position: "relative",
    display: "inline-flex",
    alignItems: "center",
    width: 52,
    height: 28,
    padding: 2,
    borderRadius: 999,
    cursor: "pointer",
    touchAction: "manipulation",
    WebkitTapHighlightColor: "transparent",
    "& input": {
      opacity: 0,
      width: 0,
      height: 0,
      position: "absolute",
    },
    "& .ms-track": {
      position: "absolute",
      inset: 0,
      borderRadius: 999,
      background: trackBg,
      border: `1px solid ${trackBorder}`,
      transition: "background-color .2s ease, border-color .2s ease",
      boxSizing: "border-box",
    },
    "& .ms-thumb": {
      position: "relative",
      zIndex: 1,
      width: 22,
      height: 22,
      borderRadius: "50%",
      background: theme.palette.common.white,
      boxShadow:
        theme.palette.mode === "dark"
          ? "0 1px 2px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08) inset"
          : "0 1px 2px rgba(0,0,0,.25), 0 0 0 1px rgba(0,0,0,.06) inset",
      transform: "translateX(0)",
      transition: "transform .18s cubic-bezier(.2,.9,.22,1), box-shadow .18s ease",
    },
    "&.ms-checked .ms-track": {
      background: alpha(on, theme.palette.mode === "dark" ? 0.55 : 0.2),
      borderColor: alpha(on, 0.6),
    },
    "&.ms-checked .ms-thumb": {
      transform: "translateX(24px)",
      boxShadow:
        theme.palette.mode === "dark"
          ? "0 1px 2px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08) inset"
          : "0 1px 2px rgba(0,0,0,.25), 0 0 0 1px rgba(0,0,0,.06) inset",
    },
    "&.ms-hover .ms-track": {
      background: theme.palette.mode === "dark"
        ? alpha("#fff", 0.16)
        : alpha("#000", 0.1),
    },
    "&.ms-focus .ms-ring": {
      boxShadow: `0 0 0 3px ${ring}`,
      opacity: 1,
      transform: "scale(1)",
    },
    "& .ms-ring": {
      position: "absolute",
      inset: -2,
      borderRadius: 999,
      boxShadow: "0 0 0 0px transparent",
      transition: "box-shadow .18s ease, transform .18s ease, opacity .18s ease",
      pointerEvents: "none",
      opacity: 0,
      transform: "scale(.98)",
    },
    "&.ms-disabled": {
      cursor: "not-allowed",
      opacity: 0.6,
    },
  };
});

function SwitchControl({
  checked,
  disabled,
  onChange,
  inputId,
  "aria-label": ariaLabel,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (e: ChangeEvent<HTMLInputElement>, checked: boolean) => void;
  inputId?: string;
  "aria-label"?: string;
}) {
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  return (
    <ModernSwitch
      className={[
        checked ? "ms-checked" : "",
        disabled ? "ms-disabled" : "",
        hover ? "ms-hover" : "",
        focus ? "ms-focus" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="ms-ring" />
      <span className="ms-track" />
      <span className="ms-thumb" />
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e, e.target.checked)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
      />
    </ModernSwitch>
  );
}

export default function Settings() {
  const navigate = useNavigate();
  const { user, setUser, logout } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState<{ text: string; sev?: "success" | "info" | "warning" | "error" } | null>(null);

  const { mode: storedMode, setMode } = useColorScheme();
  const theme = (storedMode ?? "system") as ThemeMode;

  const timeFieldSx = useMemo(
    () => ({
      maxWidth: { xs: "100%", sm: 200 },
      "& .MuiOutlinedInput-root": {
        borderRadius: 2.5,
        overflow: "hidden",
        backgroundColor: "var(--card-bg)",
        "& fieldset": {
          borderColor: "color-mix(in srgb, var(--page-text) 24%, transparent)",
          borderWidth: 1,
        },
        "&:hover fieldset": {
          borderColor: "color-mix(in srgb, var(--page-text) 32%, transparent)",
        },
        "&.Mui-focused": {
          boxShadow: "0 0 0 3px color-mix(in srgb, var(--link-color) 22%, transparent)",
        },
        "&.Mui-focused fieldset": {
          borderColor: "var(--link-color)",
        },
        "&.Mui-disabled": {
          backgroundColor: "color-mix(in srgb, var(--page-text) 6%, transparent)",
        },
        "&.Mui-disabled fieldset": {
          borderColor: "color-mix(in srgb, var(--page-text) 18%, transparent)",
        },
      },
      "& .MuiInputBase-input": {
        textAlign: "center",
        fontVariantNumeric: "tabular-nums",
      },
      "& .MuiInputLabel-root": {
        px: 0.75,
        backgroundColor: "var(--card-bg)",
        color: "var(--page-text)",
      },
    }),
    []
  );

  const {
    pushSupported,
    notificationPermission,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    enableNotifications,
    disableNotifications,
  } = usePushPreferences({ onNotify: setSnack });

  const [dndEnabled, setDndEnabled] = useState(false);
  const [dndStart, setDndStart] = useState("");
  const [dndEnd, setDndEnd] = useState("");
  const [dndSaving, setDndSaving] = useState(false);

  const [avatarVersion, setAvatarVersion] = useState(Date.now());
  const [coverVersion, setCoverVersion] = useState(Date.now());

  const syncDndFromUser = useCallback((value: any) => {
    const enabled = Boolean(value?.dnd_enabled);
    const start = toInputTime(value?.dnd_start);
    const end = toInputTime(value?.dnd_end);
    setDndEnabled(enabled);
    setDndStart(start || (enabled ? DEFAULT_DND_START : ""));
    setDndEnd(end || (enabled ? DEFAULT_DND_END : ""));
  }, []);

  const persistDnd = useCallback(
    async (nextEnabled: boolean, nextStart: string | null, nextEnd: string | null) => {
      if (dndSaving) return;
      const normalizedStart = nextStart ? nextStart.trim() : null;
      const normalizedEnd = nextEnd ? nextEnd.trim() : null;
      const prevEnabled = Boolean((user as any)?.dnd_enabled);
      const prevStart = toInputTime((user as any)?.dnd_start);
      const prevEnd = toInputTime((user as any)?.dnd_end);
      if (
        nextEnabled === prevEnabled &&
        (!nextEnabled ||
          (normalizedStart && normalizedEnd && normalizedStart === prevStart && normalizedEnd === prevEnd))
      ) {
        return;
      }
      if (nextEnabled && (!normalizedStart || !normalizedEnd)) {
        setSnack({ text: "Укажите время начала и окончания режима \"Не беспокоить\"", sev: "warning" });
        syncDndFromUser(user);
        return;
      }
      setDndSaving(true);
      try {
        const payload: Record<string, any> = { dnd_enabled: nextEnabled };
        if (nextEnabled) {
          payload.dnd_start = toServerTime(normalizedStart);
          payload.dnd_end = toServerTime(normalizedEnd);
        } else {
          payload.dnd_start = null;
          payload.dnd_end = null;
        }
        const res = await api.put("/users/me", payload);
        setUser(res.data);
        syncDndFromUser(res.data);
        const wasEnabled = prevEnabled;
        let message: string;
        if (nextEnabled && !wasEnabled) message = 'Режим "Не беспокоить" включён';
        else if (!nextEnabled && wasEnabled) message = 'Режим "Не беспокоить" выключен';
        else message = 'Настройки режима "Не беспокоить" обновлены';
        setSnack({ text: message, sev: "success" });
      } catch (error: any) {
        let message = 'Не удалось обновить настройки режима "Не беспокоить"';
        const detail = error?.response?.data?.detail;
        if (typeof detail === "string") message = detail;
        else if (Array.isArray(detail)) {
          const collected = detail
            .map((item: any) => (item?.msg ? String(item.msg) : ""))
            .filter(Boolean)
            .join("; ");
          if (collected) message = collected;
        }
        setSnack({ text: message, sev: "error" });
        syncDndFromUser(user);
      } finally {
        setDndSaving(false);
      }
    },
    [dndSaving, setUser, setSnack, syncDndFromUser, user]
  );

  const handleDndToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (dndSaving) return;
      const nextStart = checked ? dndStart || DEFAULT_DND_START : dndStart;
      const nextEnd = checked ? dndEnd || DEFAULT_DND_END : dndEnd;
      if (checked) {
        setDndStart(nextStart);
        setDndEnd(nextEnd);
      }
      setDndEnabled(checked);
      void persistDnd(checked, checked ? nextStart : null, checked ? nextEnd : null);
    },
    [dndSaving, dndEnd, dndStart, persistDnd]
  );

  const handleDndStartChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndStart(event.target.value);
  }, []);

  const handleDndStartBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return;
      const value = (event.currentTarget.value || "").trim();
      setDndStart(value);
      void persistDnd(true, value || null, dndEnd || null);
    },
    [dndEnabled, dndEnd, dndSaving, persistDnd]
  );

  const handleDndEndChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndEnd(event.target.value);
  }, []);

  const handleDndEndBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return;
      const value = (event.currentTarget.value || "").trim();
      setDndEnd(value);
      void persistDnd(true, dndStart || null, value || null);
    },
    [dndEnabled, dndSaving, dndStart, persistDnd]
  );

  useEffect(() => {
    syncDndFromUser(user);
  }, [syncDndFromUser, user]);

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const s = sp.get("spotify");
    if (s) {
      if (s === "connected") setSnack({ text: "Spotify подключён", sev: "success" });
      if (s === "error") setSnack({ text: "Ошибка подключения Spotify", sev: "error" });
      sp.delete("spotify");
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "");
      window.history.replaceState({}, "", next);
    }
  }, []);

  const handleThemeChange = useCallback(
    (_: ChangeEvent<HTMLInputElement>, value: string) => {
      setMode(value as ThemeMode);
    },
    [setMode]
  );

  const handleNotificationsToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (pushBusy || pushInitializing) return;
      if (checked) void enableNotifications();
      else void disableNotifications();
    },
    [disableNotifications, enableNotifications, pushBusy, pushInitializing]
  );

  const spotifyConnected = Boolean((user as any)?.spotify_connected || (user as any)?.spotify_is_connected);
  const spotifyName = (user as any)?.spotify_display_name || "";

  const connectSpotify = async () => {
    try {
      const { data } = await api.get<{ url?: string }>("/spotify/auth-url");
      const safeUrl = sanitizeSpotifyAuthorizeUrl(data?.url);
      if (!safeUrl) throw new Error("Received unsafe Spotify authorization URL");
      window.location.assign(safeUrl);
    } catch (error) {
      setSnack({ text: "Не удалось открыть авторизацию Spotify", sev: "error" });
    }
  };

  const disconnectSpotify = async () => {
    try {
      await api.post("/spotify/disconnect");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: currentUserQueryKey }),
        queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey }),
      ]);
      try {
        const profile = await fetchCurrentUser();
        setUser(profile ?? null);
      } catch {
        setUser((prev: ReturnType<typeof useAuth>["user"]) =>
          prev
            ? {
                ...prev,
                spotify_connected: false,
                spotify_is_connected: false,
                spotify_display_name: null,
              }
            : prev,
        );
      }
      setSnack({ text: "Spotify отключён", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось отключить Spotify", sev: "error" });
    }
  };

  const isImage = (f: File) => /^image\/(png|jpe?g|webp|gif|avif)$/i.test(f.type);
  const withinSize = (f: File, maxMB = 12) => f.size / (1024 * 1024) <= maxMB;

  const avatarInputRef = useRef<HTMLInputElement | null>(null);
  const coverInputRef = useRef<HTMLInputElement | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [coverBusy, setCoverBusy] = useState(false);

  const avatarUrl = (user as any)?.avatar_url as string | undefined;
  const coverUrl = (user as any)?.cover_url as string | undefined;

  const avatarSrc = useMemo(() => {
    const resolved = resolveMediaUrl(avatarUrl);
    return resolved ? addVersionParam(resolved, avatarVersion) : DEFAULT_AVATAR;
  }, [avatarUrl, avatarVersion]);

  const coverSrc = useMemo(() => {
    const resolved = resolveMediaUrl(coverUrl);
    return resolved ? addVersionParam(resolved, coverVersion) : "";
  }, [coverUrl, coverVersion]);

  const handleAvatarError = useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    img.onerror = null;
    img.src = DEFAULT_AVATAR;
  }, []);

  const triggerAvatarPick = () => avatarInputRef.current?.click();
  const triggerCoverPick = () => coverInputRef.current?.click();

  const refreshMe = useCallback(async () => {
    const fresh = await queryClient.fetchQuery({
      queryKey: currentUserQueryKey,
      queryFn: fetchCurrentUser,
      staleTime: 0,
    });
    setUser(fresh);
    return fresh;
  }, [queryClient, setUser]);

  const resolveDetailMessage = useCallback((error: unknown, fallback: string) => {
    if (isAxiosError(error)) {
      const detail = (error.response?.data as any)?.detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        const combined = detail
          .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
          .filter(Boolean)
          .join("; ");
        if (combined) return combined;
      }
    }
    return fallback;
  }, []);

  const uploadAvatar = async (file: File) => {
    if (!isImage(file)) return setSnack({ text: "Поддерживаются PNG/JPG/WebP/AVIF/GIF", sev: "warning" });
    if (!withinSize(file)) return setSnack({ text: "Файл слишком большой (>12 МБ)", sev: "warning" });
    try {
      setAvatarBusy(true);
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/users/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } });
      await refreshMe();
      setAvatarVersion(Date.now());
      setSnack({ text: "Аватар обновлён", sev: "success" });
    } catch (error) {
      setSnack({ text: resolveDetailMessage(error, "Не удалось загрузить аватар"), sev: "error" });
    } finally {
      setAvatarBusy(false);
      if (avatarInputRef.current) avatarInputRef.current.value = "";
    }
  };

  const removeAvatar = async () => {
    try {
      setAvatarBusy(true);
      await api.delete("/users/me/avatar");
      await refreshMe();
      setAvatarVersion(Date.now());
      setSnack({ text: "Аватар удалён", sev: "success" });
    } catch (error) {
      setSnack({ text: resolveDetailMessage(error, "Не удалось удалить аватар"), sev: "error" });
    } finally {
      setAvatarBusy(false);
    }
  };

  const uploadCover = async (file: File) => {
    if (!isImage(file)) return setSnack({ text: "Поддерживаются PNG/JPG/WebP/AVIF/GIF", sev: "warning" });
    if (!withinSize(file)) return setSnack({ text: "Файл слишком большой (>12 МБ)", sev: "warning" });
    try {
      setCoverBusy(true);
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/users/me/cover", fd, { headers: { "Content-Type": "multipart/form-data" } });
      await refreshMe();
      setCoverVersion(Date.now());
      setSnack({ text: "Обложка обновлена", sev: "success" });
    } catch (error) {
      setSnack({ text: resolveDetailMessage(error, "Не удалось загрузить обложку"), sev: "error" });
    } finally {
      setCoverBusy(false);
      if (coverInputRef.current) coverInputRef.current.value = "";
    }
  };

  const [confirmLogout, setConfirmLogout] = useState(false);

  return (
    <Box maxWidth="100vw" mx={0} mt={0} width="100vw" minHeight="100svh" px={0}>
      <Paper
        className="glass glass--panel"
        sx={{
          p: { xs: 2, md: 4, lg: 6 },
          borderRadius: 0,
          width: "100%",
          minHeight: "100svh",
          color: "var(--page-text)",
          bgcolor: "var(--card-bg)"
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: { xs: 1.5, md: 2 } }}>
          <SettingsIcon />
          <Typography variant="h4" fontWeight={800} sx={{ color: "var(--page-text)" }}>
            Настройки
          </Typography>
        </Stack>

        <Paper variant="outlined" className="glass--segmented" sx={{ mb: 3, bgcolor: "var(--card-bg)" }}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              "& .MuiTab-root": {
                color: "var(--page-text)",
                textTransform: "none",
                fontWeight: 700,
                minHeight: 42
              },
              "& .Mui-selected": { color: "var(--link-color)" }
            }}
          >
            <Tab label="Общее" />
            <Tab label="Аккаунт" />
            <Tab label="Интеграции" />
          </Tabs>
        </Paper>

        {tab === 0 && (
          <Stack spacing={3}>
            <Box>
              <Typography variant="h6" sx={{ mb: 1.2, color: "var(--page-text)" }}>
                Тема
              </Typography>
              <RadioGroup row value={theme} onChange={handleThemeChange}>
                <FormControlLabel
                  value="system"
                  control={<Radio />}
                  label={<Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}><DesktopWindowsIcon /> <span>Система</span></Stack>}
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="light"
                  control={<Radio />}
                  label={<Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}><LightModeIcon /> <span>Светлая</span></Stack>}
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="dark"
                  control={<Radio />}
                  label={<Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}><DarkModeIcon /> <span>Тёмная</span></Stack>}
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
              </RadioGroup>
            </Box>

            <Divider />

            <Box>
              <Typography variant="h6" sx={{ mb: 1.2, color: "var(--page-text)" }}>
                Уведомления
              </Typography>
              {!pushSupported ? (
                <Alert severity="warning" variant="outlined">
                  Веб push-уведомления недоступны в вашем браузере.
                </Alert>
              ) : (
                <Stack spacing={1.8}>
                  {notificationPermission === "denied" ? (
                    <Stack spacing={1.5}>
                      <Alert severity="error" variant="outlined">
                        Уведомления запрещены в браузере. Откройте настройки сайта и включите уведомления для «Экосистема ГУУ».
                      </Alert>
                      <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                        После изменения настроек браузера нажмите «Проверить разрешение», чтобы обновить статус.
                      </Typography>
                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.2} alignItems={{ sm: "center" }}>
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy}
                          startIcon={pushBusy ? <CircularProgress size={18} color="inherit" /> : undefined}
                        >
                          Проверить разрешение
                        </Button>
                        <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                          Текущее состояние: {permissionText}.
                        </Typography>
                      </Stack>
                    </Stack>
                  ) : notificationPermission === "default" ? (
                    <Stack spacing={1.5}>
                      <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                        Включите уведомления, чтобы первым узнавать о расписании, мероприятиях и важных новостях.
                      </Typography>
                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.2} alignItems={{ sm: "center" }}>
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy || pushInitializing}
                          startIcon={pushBusy || pushInitializing ? <CircularProgress size={18} color="inherit" /> : undefined}
                        >
                          Разрешить уведомления
                        </Button>
                        <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                          Текущее состояние: {permissionText}.
                        </Typography>
                      </Stack>
                    </Stack>
                  ) : (
                    <>
                      <FormControlLabel
                        sx={{
                          minHeight: 44,
                          alignItems: "center",
                          columnGap: 1.25,
                          m: 0
                        }}
                        control={
                          <SwitchControl
                            checked={notificationsEnabled}
                            onChange={handleNotificationsToggle}
                            disabled={pushBusy || pushInitializing}
                            aria-label="Включить уведомления"
                          />
                        }
                        label={<span style={{ color: "var(--page-text)", fontWeight: 700 }}>Включить уведомления</span>}
                      />

                      <FormControlLabel
                        sx={{
                          minHeight: 44,
                          alignItems: "center",
                          columnGap: 1.25,
                          m: 0
                        }}
                        control={
                          <SwitchControl
                            checked={dndEnabled}
                            onChange={handleDndToggle}
                            disabled={dndSaving}
                            aria-label="Включить тихий период"
                          />
                        }
                        label={<span style={{ color: "var(--page-text)", fontWeight: 700 }}>Включить тихий период</span>}
                      />

                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "center" }}>
                        <TextField
                          type="time"
                          label="С"
                          value={dndStart}
                          onChange={handleDndStartChange}
                          onBlur={handleDndStartBlur}
                          disabled={!dndEnabled || dndSaving}
                          size="small"
                          InputLabelProps={{ shrink: true }}
                          sx={timeFieldSx}
                        />
                        <TextField
                          type="time"
                          label="До"
                          value={dndEnd}
                          onChange={handleDndEndChange}
                          onBlur={handleDndEndBlur}
                          disabled={!dndEnabled || dndSaving}
                          size="small"
                          InputLabelProps={{ shrink: true }}
                          sx={timeFieldSx}
                        />
                      </Stack>
                    </>
                  )}
                </Stack>
              )}
            </Box>
          </Stack>
        )}

        {tab === 1 && (
          <Box sx={{ width: "100%", maxWidth: { xs: "100%", sm: 640, md: 760, lg: 880 } }}>
            <List dense disablePadding>
              <ListItem
                divider
                secondaryAction={
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="text" startIcon={<PhotoCameraIcon />} onClick={triggerAvatarPick} disabled={avatarBusy}>
                      Сменить
                    </Button>
                    <Button size="small" variant="text" color="error" startIcon={<DeleteOutlineIcon />} onClick={removeAvatar} disabled={avatarBusy}>
                      Удалить
                    </Button>
                  </Stack>
                }
              >
                <ListItemAvatar>
                  <Avatar
                    src={avatarSrc}
                    alt={(user as any)?.full_name || "avatar"}
                    sx={{ width: 48, height: 48 }}
                    imgProps={{ onError: handleAvatarError, loading: "lazy", decoding: "async", referrerPolicy: "no-referrer" }}
                  />
                </ListItemAvatar>
                <ListItemText primary="Фото профиля" secondary="PNG/JPG/WebP/AVIF/GIF, до 12 МБ" />
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.currentTarget.files?.[0];
                    if (f) uploadAvatar(f);
                  }}
                />
              </ListItem>

              <ListItem
                divider
                secondaryAction={
                  <Button size="small" variant="text" startIcon={<ImageIcon />} onClick={triggerCoverPick} disabled={coverBusy}>
                    Сменить
                  </Button>
                }
              >
                <ListItemAvatar sx={{ mr: 1.25 }}>
                  <Box
                    data-testid="settings-cover-preview"
                    sx={{
                      width: 120,
                      height: 52,
                      borderRadius: 1.5,
                      border: "1px solid var(--glass-border)",
                      background: coverSrc ? `url(${coverSrc}) center/cover no-repeat` : "var(--card-bg)"
                    }}
                  />
                </ListItemAvatar>
                <ListItemText primary="Обложка профиля" secondary="Рекомендация: 1600×400+" />
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.currentTarget.files?.[0];
                    if (f) uploadCover(f);
                  }}
                />
              </ListItem>

              <ListItem
                divider
                secondaryAction={
                  <Button size="small" variant="text" onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}>
                    Редактировать
                  </Button>
                }
              >
                <ListItemText primary="Профиль" secondary="Имя, контакты, соцсети" />
              </ListItem>
            </List>

            <Box sx={{ pt: 1.5, mt: 0.5, borderTop: "1px solid var(--glass-border)" }}>
              <List dense disablePadding>
                <ListItem>
                  <Button
                    size="small"
                    variant="text"
                    color="error"
                    startIcon={<LogoutIcon />}
                    onClick={async () => {
                      setConfirmLogout(false);
                      await logout();
                    }}
                    sx={{ px: 0 }}
                  >
                    Выйти
                  </Button>
                </ListItem>
              </List>
            </Box>
          </Box>
        )}

        {tab === 2 && (
          <Stack spacing={3}>
            <Stack spacing={2}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <img
                  src={spotifyLogo}
                  alt="Spotify"
                  width={22}
                  height={22}
                  style={{ display: "block", borderRadius: "50%" }}
                  loading="lazy"
                  decoding="async"
                />
                <Typography variant="h6" sx={{ color: "var(--page-text)" }}>Spotify</Typography>
              </Stack>
              <Stack direction="row" alignItems="center" spacing={1.2} flexWrap="wrap">
                <Chip size="small" className="glass--chip" label={spotifyConnected ? "Подключено" : "Не подключено"} color={spotifyConnected ? "success" : "default"} variant="outlined" />
                {spotifyConnected && !!spotifyName && <Chip size="small" variant="outlined" label={spotifyName} />}
              </Stack>
              {!spotifyConnected ? (
                <Button variant="contained" onClick={connectSpotify} sx={{ alignSelf: "lex-start" }}>
                  Подключить Spotify
                </Button>
              ) : (
                <Button variant="outlined" color="error" onClick={disconnectSpotify} sx={{ alignSelf: "flex-start" }}>
                  Отключить Spotify
                </Button>
              )}
            </Stack>
          </Stack>
        )}
      </Paper>

      <Dialog open={confirmLogout} onClose={() => setConfirmLogout(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Выйти из аккаунта?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">Вы сможете войти снова. Данные не удаляются.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmLogout(false)}>Отмена</Button>
          <Button
            color="error"
            onClick={async () => {
              setConfirmLogout(false);
              await logout();
            }}
          >
            Выйти
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!snack} autoHideDuration={2600} onClose={() => setSnack(null)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        <Alert onClose={() => setSnack(null)} severity={snack?.sev || "info"} variant="filled" sx={{ width: "100%" }}>
          {snack?.text}
        </Alert>
      </Snackbar>
    </Box>
  );
}
