import { useEffect, useState } from "react";
import axios from "../api/axios";
import { Box, Paper, Typography, TextField, Button, Stack, InputAdornment, IconButton, LinearProgress, Tooltip } from "@mui/material";
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";
import { useParams, useSearchParams, Link } from "react-router-dom";

const RESET_URL = "/password/reset";

async function sha1Hex(str: string) {
  const buf = new TextEncoder().encode(str);
  const hash = await crypto.subtle.digest("SHA-1", buf);
  return Array.from(new Uint8Array(hash)).map(b=>b.toString(16).padStart(2,"0")).join("").toUpperCase();
}
async function isPwnedPassword(pwd: string) {
  if (!pwd) return false;
  const hash = await sha1Hex(pwd);
  const prefix = hash.slice(0,5);
  const suffix = hash.slice(5);
  const resp = await fetch(`https://api.pwnedpasswords.com/range/${prefix}`);
  if (!resp.ok) return false;
  const text = await resp.text();
  return text.split("\n").some(line => line.split(":")[0] === suffix);
}

export default function ResetPassword() {
  const params = useParams<{ token?: string }>();
  const [sp] = useSearchParams();
  const token = params.token || sp.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [capsPass, setCapsPass] = useState(false);
  const [capsConfirm, setCapsConfirm] = useState(false);
  const [showPass, setShowPass] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [strength, setStrength] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<string>("");
  const [pwned, setPwned] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) setError("Некорректная ссылка сброса пароля.");
  }, [token]);

  const minLenOk = password.length >= 8;
  const matchOk = confirm.length > 0 && password === confirm;
  const canSubmit = token && minLenOk && matchOk && !submitting;

  const onPass = async (v: string) => {
    setPassword(v);
    setError("");
    setFeedback("");
    if (!v) {
      setStrength(null);
      setPwned(false);
      return;
    }
    try {
      const { default: zxcvbn } = await import("zxcvbn");
      const res = zxcvbn(v);
      setStrength(res.score);
      const tips = (res.feedback?.warning || "") + (res.feedback?.suggestions?.length ? (" · " + res.feedback.suggestions.join(" · ")) : "");
      setFeedback(tips);
    } catch {
      setStrength(null);
    }
    try {
      const bad = await isPwnedPassword(v);
      if (v === password) setPwned(bad);
    } catch {}
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError("");
    try {
      await axios.post(RESET_URL, { token, password });
      setDone(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Не удалось сбросить пароль. Ссылка могла устареть.");
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <Box sx={{ minHeight: "100vh", bgcolor: "var(--page-bg)", color: "var(--page-text)", display: "flex", alignItems: "center", justifyContent: "center", px: 1 }}>
        <Paper elevation={7} sx={{ width: "100%", maxWidth: 460, p: { xs: 2, sm: 4 }, borderRadius: { xs: 3, sm: 5 }, bgcolor: "var(--card-bg)" }}>
          <Typography variant="h5" fontWeight={800} align="center" mb={1.5}>Пароль обновлён</Typography>
          <Stack alignItems="center" spacing={1}>
            <Typography color="text.secondary" align="center">Теперь вы можете войти с новым паролем.</Typography>
            <Button component={Link} to="/login" variant="contained" sx={{ mt: 1 }}>Перейти ко входу</Button>
          </Stack>
        </Paper>
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "var(--page-bg)", color: "var(--page-text)", display: "flex", alignItems: "center", justifyContent: "center", px: 1 }}>
      <Paper elevation={7} sx={{ width: "100%", maxWidth: 460, p: { xs: 2, sm: 4 }, borderRadius: { xs: 3, sm: 5 }, bgcolor: "var(--card-bg)" }}>
        <Typography variant="h5" fontWeight={800} align="center" mb={1.5}>Новый пароль</Typography>
        <Typography color="text.secondary" align="center" sx={{ mb: 2 }}>Придумайте новый пароль для вашей учётной записи.</Typography>
        <form onSubmit={submit} autoComplete="off">
          <Stack spacing={2}>
            <TextField
              label="Пароль"
              type={showPass ? "text" : "password"}
              value={password}
              onChange={(e)=>onPass(e.target.value)}
              onKeyUp={(e)=>setCapsPass((e as any).getModifierState?.("CapsLock"))}
              onKeyDown={(e)=>setCapsPass((e as any).getModifierState?.("CapsLock"))}
              fullWidth
              autoFocus
              autoComplete="new-password"
              helperText="Минимум 8 символов"
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title="Удерживайте, чтобы показать пароль">
                      <IconButton
                        aria-label="Показать пароль"
                        onMouseDown={() => setShowPass(true)}
                        onMouseUp={() => setShowPass(false)}
                        onMouseLeave={() => setShowPass(false)}
                        onClick={() => setShowPass(v => !v)}
                        edge="end"
                        tabIndex={-1}
                      >
                        {showPass ? <VisibilityOff/> : <Visibility/>}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                )
              }}
            />
            {strength !== null && (
              <LinearProgress variant="determinate" value={[10, 30, 55, 75, 100][strength]} sx={{ mt: -0.5, height: 8, borderRadius: 1 }} aria-label="Надёжность пароля" />
            )}
            {!!feedback && <Typography fontSize={13} color="text.secondary">{feedback}</Typography>}
            {capsPass && <Typography color="warning.main" fontSize={13}>Включён Caps Lock</Typography>}
            {pwned && <Typography color="warning.main" fontSize={13}>Этот пароль встречался в утечках — лучше выберите другой.</Typography>}
            <TextField
              label="Повторите пароль"
              type={showConfirm ? "text" : "password"}
              value={confirm}
              onChange={(e)=>setConfirm(e.target.value)}
              onKeyUp={(e)=>setCapsConfirm((e as any).getModifierState?.("CapsLock"))}
              onKeyDown={(e)=>setCapsConfirm((e as any).getModifierState?.("CapsLock"))}
              fullWidth
              autoComplete="new-password"
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title="Удерживайте, чтобы показать пароль">
                      <IconButton
                        aria-label="Показать пароль"
                        onMouseDown={() => setShowConfirm(true)}
                        onMouseUp={() => setShowConfirm(false)}
                        onMouseLeave={() => setShowConfirm(false)}
                        onClick={() => setShowConfirm(v => !v)}
                        edge="end"
                        tabIndex={-1}
                      >
                        {showConfirm ? <VisibilityOff/> : <Visibility/>}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                )
              }}
            />
            {capsConfirm && <Typography color="warning.main" fontSize={13}>Включён Caps Lock</Typography>}
            <Box sx={{ minHeight: 22, textAlign: "center" }} aria-live="assertive">
              {!!error && <Typography color="error" fontSize={15}>{error}</Typography>}
            </Box>
            <Button type="submit" variant="contained" size="large" fullWidth disabled={!canSubmit}>{submitting ? "Сохраняю…" : "Сохранить пароль"}</Button>
            <Button component={Link} to="/forgot-password" variant="text">Не пришло письмо?</Button>
          </Stack>
        </form>
      </Paper>
    </Box>
  );
}