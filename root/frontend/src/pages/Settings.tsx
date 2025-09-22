import { useEffect, useRef, useState, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import api from "@/api/axios";
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
  DialogActions
} from "@mui/material";
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
import defaultAvatar from "@/assets/default_avatar.png";
import spotifyLogo from "@/assets/spotify_icon.png";
import { resolveMediaUrl } from "@/utils/media";
import { ensurePushSubscription, unsubscribePush } from "@/utils/push";

type ThemeMode = "system" | "light" | "dark";

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || "";

export default function Settings() {
  const navigate = useNavigate();
  const { user, setUser, logout } = useAuth();
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState<{ text: string; sev?: "success" | "info" | "warning" | "error" } | null>(null);

  const sysPref = window.matchMedia("(prefers-color-scheme: dark)");
  const readStored = () => (localStorage.getItem("theme") as ThemeMode | null) || "system";
  const [theme, setTheme] = useState<ThemeMode>(readStored());

  const applyTheme = useCallback(
    (mode: ThemeMode) => {
      const dark = mode === "dark" || (mode === "system" && sysPref.matches);
      document.body.classList.toggle("dark", dark);
    },
    [sysPref.matches]
  );

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("theme", theme);
  }, [theme, applyTheme]);

  useEffect(() => {
    const onChange = () => {
      if (theme === "system") applyTheme("system");
    };
    sysPref.addEventListener?.("change", onChange);
    return () => sysPref.removeEventListener?.("change", onChange);
  }, [theme, applyTheme, sysPref]);

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

  const spotifyConnected = Boolean((user as any)?.spotify_connected || (user as any)?.spotify_is_connected);
  const spotifyName = (user as any)?.spotify_display_name || "";

  const connectSpotify = async () => {
    try {
      const r = await api.get<{ url: string }>("/spotify/auth-url");
      if (r.data?.url) window.location.assign(r.data.url);
    } catch {
      setSnack({ text: "Не удалось открыть авторизацию Spotify", sev: "error" });
    }
  };

  const disconnectSpotify = async () => {
    try {
      await api.post("/spotify/disconnect");
      const me = await api.get("/users/me");
      setUser(me.data);
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

  const getAvatarSrc = useCallback(() => {
    if ((user as any)?.avatar_url) {
      const url = resolveMediaUrl((user as any).avatar_url, BACKEND_ORIGIN);
      return url;
    }
    return defaultAvatar;
  }, [user]);

  const getCoverSrc = useCallback(() => {
    if ((user as any)?.cover_url) {
      const url = resolveMediaUrl((user as any).cover_url, BACKEND_ORIGIN);
      return url;
    }
    return "";
  }, [user]);

  const triggerAvatarPick = () => avatarInputRef.current?.click();
  const triggerCoverPick = () => coverInputRef.current?.click();

  const uploadAvatar = async (file: File) => {
    if (!isImage(file)) return setSnack({ text: "Поддерживаются PNG/JPG/WebP/AVIF/GIF", sev: "warning" });
    if (!withinSize(file)) return setSnack({ text: "Файл слишком большой (>12 МБ)", sev: "warning" });
    try {
      setAvatarBusy(true);
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/users/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const me = await api.get("/users/me");
      setUser(me.data);
      setSnack({ text: "Аватар обновлён", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось загрузить аватар", sev: "error" });
    } finally {
      setAvatarBusy(false);
    }
  };

  const removeAvatar = async () => {
    try {
      setAvatarBusy(true);
      await api.delete("/users/me/avatar");
      const me = await api.get("/users/me");
      setUser(me.data);
      setSnack({ text: "Аватар удалён", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось удалить аватар", sev: "error" });
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
      const me = await api.get("/users/me");
      setUser(me.data);
      setSnack({ text: "Обложка обновлена", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось загрузить обложку", sev: "error" });
    } finally {
      setCoverBusy(false);
    }
  };

  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    const detect = async () => {
      try {
        if (!("serviceWorker" in navigator)) return;
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (!mounted) return;
        setPushEnabled(!!sub);
      } catch {}
    };
    detect();
    return () => {
      mounted = false;
    };
  }, []);

  const enablePush = async () => {
    try {
      setPushBusy(true);
      const r = await api.get<{ key: string }>("/push/public-key");
      const key = r.data?.key || "";
      if (!key) throw new Error("no key");
      const sub = await ensurePushSubscription(key);
      if (sub) {
        setPushEnabled(true);
        setSnack({ text: "Уведомления включены", sev: "success" });
      } else {
        setSnack({ text: "Не удалось включить уведомления", sev: "error" });
      }
    } catch {
      setSnack({ text: "Ошибка включения уведомлений", sev: "error" });
    } finally {
      setPushBusy(false);
    }
  };

  const disablePush = async () => {
    try {
      setPushBusy(true);
      const ok = await unsubscribePush();
      if (ok) {
        setPushEnabled(false);
        setSnack({ text: "Уведомления выключены", sev: "success" });
      } else {
        setSnack({ text: "Не удалось выключить уведомления", sev: "error" });
      }
    } catch {
      setSnack({ text: "Ошибка выключения уведомлений", sev: "error" });
    } finally {
      setPushBusy(false);
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
              <RadioGroup row value={theme} onChange={(e) => setTheme(e.target.value as ThemeMode)}>
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
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.2}>
                <Button
                  startIcon={<NotificationsActiveIcon />}
                  disabled={pushBusy || pushEnabled}
                  variant="contained"
                  onClick={enablePush}
                  sx={{ width: { xs: "100%", sm: "auto" } }}
                >
                  Включить уведомления
                </Button>
                <Button
                  startIcon={<NotificationsOffIcon />}
                  disabled={pushBusy || !pushEnabled}
                  variant="outlined"
                  color="error"
                  onClick={disablePush}
                  sx={{ width: { xs: "100%", sm: "auto" } }}
                >
                  Выключить уведомления
                </Button>
              </Stack>
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
                    src={getAvatarSrc()}
                    alt={(user as any)?.full_name || "avatar"}
                    sx={{ width: 48, height: 48 }}
                    imgProps={{
                      onError: (e) => {
                        (e.currentTarget as HTMLImageElement).src = defaultAvatar;
                      }
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
                    sx={{
                      width: 120,
                      height: 52,
                      borderRadius: 1.5,
                      border: "1px solid var(--glass-border)",
                      background: getCoverSrc() ? `url(${getCoverSrc()}) center/cover no-repeat` : "var(--card-bg)"
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
                    onClick={() => setConfirmLogout(true)}
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
                <img src={spotifyLogo} alt="Spotify" width={22} height={22} style={{ display: "block", borderRadius: "50%" }} />
                <Typography variant="h6" sx={{ color: "var(--page-text)" }}>Spotify</Typography>
              </Stack>
              <Stack direction="row" alignItems="center" spacing={1.2} flexWrap="wrap">
                <Chip size="small" className="glass--chip" label={spotifyConnected ? "Подключено" : "Не подключено"} color={spotifyConnected ? "success" : "default"} variant="outlined" />
                {spotifyConnected && !!spotifyName && <Chip size="small" variant="outlined" label={spotifyName} />}
              </Stack>
              {!spotifyConnected ? (
                <Button variant="contained" onClick={connectSpotify} sx={{ alignSelf: "flex-start" }}>
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
          <Button color="error" onClick={() => { setConfirmLogout(false); logout(); }}>Выйти</Button>
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