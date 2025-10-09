import { useEffect, useRef, useState, useCallback, useMemo, ChangeEvent, FocusEvent } from "react";
import { isAxiosError } from "axios";
import { useAuth, currentUserQueryKey, fetchCurrentUser } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useNotifications } from "@/hooks/useNotifications";
import { usePushPreferences, NOTIFICATION_TOPIC_LABELS } from "@/hooks/usePushPreferences";
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
  Switch,
  FormGroup,
  FormControl,
  FormHelperText,
  Link
} from "@mui/material";
import { useColorScheme } from "@mui/material/styles";
import TextField from "@mui/material/TextField";
import SettingsIcon from "@mui/icons-material/Settings";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows";
import LogoutIcon from "@mui/icons-material/Logout";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ImageIcon from "@mui/icons-material/Image";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import NotificationsOffIcon from "@mui/icons-material/NotificationsOff";
import DoNotDisturbOnIcon from "@mui/icons-material/DoNotDisturbOn";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import defaultAvatar from "@/assets/default_avatar.png";
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
  if (/^\d{2}:\d{2}$/.test(trimmed)) {
    return `${trimmed}:00`;
  }
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) {
    return trimmed;
  }
  return trimmed;
};

export default function Settings() {
  const navigate = useNavigate();
  const { user, setUser, logout } = useAuth();
  const queryClient = useQueryClient();
  const { unreadCount } = useNotifications();
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState<{ text: string; sev?: "success" | "info" | "warning" | "error" } | null>(null);

  const { mode: storedMode, setMode } = useColorScheme();
  const theme = (storedMode ?? "system") as ThemeMode;

  const {
    topicKeys,
    topicState,
    pushSupported,
    notificationPermission,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    selectedTopicsDescription,
    enableNotifications,
    disableNotifications,
    handleTopicToggle,
    safariIOS,
    safariGuideUrl
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
      console.error("Failed to initiate Spotify auth", error);
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
      } catch (error) {
        console.warn("Failed to refresh user after Spotify disconnect", error);
        setUser((prev) =>
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
    } catch (error) {
      console.error("Failed to disconnect Spotify", error);
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
    return resolved ? addVersionParam(resolved, avatarVersion) : defaultAvatar;
  }, [avatarUrl, avatarVersion]);

  const coverSrc = useMemo(() => {
    const resolved = resolveMediaUrl(coverUrl);
    return resolved ? addVersionParam(resolved, coverVersion) : "";
  }, [coverUrl, coverVersion]);

  const handleAvatarError = useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    img.onerror = null;
    img.src = defaultAvatar;
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
      await api.post("/users/me/avatar", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
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
      await api.post("/users/me/cover", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
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
                  label={
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                      <DesktopWindowsIcon /> <span>Система</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="light"
                  control={<Radio />}
                  label={
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                      <LightModeIcon /> <span>Светлая</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="dark"
                  control={<Radio />}
                  label={
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                      <DarkModeIcon /> <span>Тёмная</span>
                    </Stack>
                  }
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
                        Уведомления запрещены в браузере. Откройте настройки сайта и включите уведомления для
                        «Экосистема ГУУ».
                      </Alert>
                      <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                        После изменения настроек браузера нажмите «Проверить разрешение», чтобы обновить статус.
                      </Typography>
                      {safariIOS && (
                        <Alert severity="info" variant="outlined">
                          Установите приложение на Домой, затем разрешите уведомления.{" "}
                          <Link href={safariGuideUrl} target="_blank" rel="noreferrer noopener">
                            Инструкция
                          </Link>
                          .
                        </Alert>
                      )}
                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.2} alignItems={{ sm: "center" }}>
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy}
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
                        Включите уведомления, чтобы первым узнавать о расписании, новостях и важных изменениях.
                      </Typography>
                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.2} alignItems={{ sm: "center" }}>
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy || pushInitializing}
                        >
                          Разрешить уведомления
                        </Button>
                        <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                          Текущее состояние: {permissionText}.
                        </Typography>
                      </Stack>
                      {safariIOS && (
                        <Alert severity="info" variant="outlined">
                          Установите приложение на Домой, затем разрешите уведомления.{" "}
                          <Link href={safariGuideUrl} target="_blank" rel="noreferrer noopener">
                            Инструкция
                          </Link>
                          .
                        </Alert>
                      )}
                    </Stack>
                  ) : (
                    <>
                      <FormControl component="fieldset" variant="standard">
                        <FormGroup>
                          <FormControlLabel
                            control={
                              <Switch
                                checked={notificationsEnabled}
                                onChange={handleNotificationsToggle}
                                disabled={pushBusy || pushInitializing}
                              />
                            }
                            label={
                              <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                                {notificationsEnabled ? <NotificationsActiveIcon /> : <NotificationsOffIcon />}
                                <span>Включить уведомления</span>
                              </Stack>
                            }
                          />
                        </FormGroup>
                        <FormHelperText sx={{ ml: 0, color: "var(--page-text)", mt: 0.5 }}>
                          Разрешение браузера: {permissionText}
                        </FormHelperText>
                      </FormControl>

                      <FormControl
                        component="fieldset"
                        variant="standard"
                        disabled={!notificationsEnabled || pushBusy || pushInitializing}
                        sx={{ opacity: notificationsEnabled ? 1 : 0.6 }}
                      >
                        <FormGroup>
                          {topicKeys.map(key => (
                            <FormControlLabel
                              key={key}
                              control={
                                <Switch
                                  checked={topicState[key]}
                                  onChange={handleTopicToggle(key)}
                                  disabled={!notificationsEnabled || pushBusy || pushInitializing}
                                />
                              }
                              label={
                                <span style={{ color: "var(--page-text)" }}>{NOTIFICATION_TOPIC_LABELS[key]}</span>
                              }
                            />
                          ))}
                        </FormGroup>
                        <FormHelperText sx={{ ml: 0, color: "var(--page-text)", mt: 0.5 }}>
                          Активные темы: {selectedTopicsDescription}
                        </FormHelperText>
                      </FormControl>

                      <Divider sx={{ my: 1.2 }} />

                      <Stack spacing={1.2}>
                        <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                          <DoNotDisturbOnIcon fontSize="small" />
                          <Typography variant="subtitle1" sx={{ color: "var(--page-text)" }}>
                            Режим «Не беспокоить»
                          </Typography>
                        </Stack>

                        <FormControl component="fieldset" variant="standard">
                          <FormGroup>
                            <FormControlLabel
                              control={
                                <Switch checked={dndEnabled} onChange={handleDndToggle} disabled={dndSaving} />
                              }
                              label={<span style={{ color: "var(--page-text)" }}>Включить тихий период</span>}
                            />
                          </FormGroup>
                          <FormHelperText sx={{ ml: 0, color: "var(--page-text)", mt: 0.5 }}>
                            Уведомления будут доставляться без звука в указанный интервал.
                          </FormHelperText>
                        </FormControl>

                        <Stack
                          direction={{ xs: "column", sm: "row" }}
                          spacing={1.5}
                          alignItems={{ sm: "center" }}
                        >
                          <TextField
                            type="time"
                            label="С"
                            value={dndStart}
                            onChange={handleDndStartChange}
                            onBlur={handleDndStartBlur}
                            disabled={!dndEnabled || dndSaving}
                            size="small"
                            InputLabelProps={{ shrink: true }}
                            sx={{ maxWidth: { xs: "100%", sm: 200 } }}
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
                            sx={{ maxWidth: { xs: "100%", sm: 200 } }}
                          />
                        </Stack>

                        <FormHelperText sx={{ ml: 0, color: "var(--page-text)" }}>
                          Интервал задаётся в часовом поясе устройства и может пересекать полночь.
                        </FormHelperText>

                        <Stack direction="row" spacing={1} alignItems="flex-start" sx={{ color: "var(--page-text)" }}>
                          <InfoOutlinedIcon fontSize="small" sx={{ mt: 0.3 }} />
                          <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                            На iOS при установке веб-приложения как PWA уведомления часто приходят без звука — это
                            ограничение системы.
                          </Typography>
                        </Stack>
                      </Stack>

                      <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                        {notificationsEnabled
                          ? `Непрочитанные: ${unreadCount}.`
                          : "Уведомления сейчас отключены."}
                      </Typography>
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
                    imgProps={{
                      onError: handleAvatarError,
                      loading: "lazy",
                      decoding: "async",
                      referrerPolicy: "no-referrer",
                    }}
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