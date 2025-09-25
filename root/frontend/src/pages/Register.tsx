import { useActionState, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../api/axios";
import { Box, Paper, Typography, TextField, Button, Stack, Select, MenuItem, InputLabel, FormControl, useMediaQuery, CircularProgress, InputAdornment, IconButton, LinearProgress, Chip, Tooltip } from "@mui/material";
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";

function levenshtein(a: string, b: string) {
  const m = a.length, n = b.length;
  if (!m) return n;
  if (!n) return m;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  return dp[m][n];
}

const COMMON_EMAIL_DOMAINS = ["gmail.com","googlemail.com","yahoo.com","outlook.com","hotmail.com","live.com","icloud.com","mail.ru","bk.ru","list.ru","inbox.ru","yandex.ru","yandex.com","rambler.ru","proton.me"];

function suggestEmailDomain(email: string) {
  const at = email.indexOf("@");
  if (at < 0) return null;
  const local = email.slice(0, at).trim();
  const dom = email.slice(at + 1).trim().toLowerCase();
  if (!local || !dom) return null;
  if (COMMON_EMAIL_DOMAINS.includes(dom)) return null;
  let best: { d: string; dist: number } | null = null;
  for (const cand of COMMON_EMAIL_DOMAINS) {
    const dist = levenshtein(dom, cand);
    if (dist <= 2 && (!best || dist < best.dist)) best = { d: cand, dist };
  }
  return best ? `${local}@${best.d}` : null;
}

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type RegisterState = {
  status: "idle" | "success" | "error";
  error?: string;
  field?: "full_name" | "email" | "password" | "confirm" | "invite_code";
};

const Register = () => {
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm: "", role: "student", invite_code: "" });
  const [showPass, setShowPass] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [capsPass, setCapsPass] = useState(false);
  const [capsConfirm, setCapsConfirm] = useState(false);
  const [strength, setStrength] = useState<number | null>(null);
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null);

  const isMobile = useMediaQuery("(max-width:600px)");
  const fullNameRef = useRef<HTMLInputElement | null>(null);
  const emailRef = useRef<HTMLInputElement | null>(null);
  const inviteRef = useRef<HTMLInputElement | null>(null);
  const passwordRef = useRef<HTMLInputElement | null>(null);
  const confirmRef = useRef<HTMLInputElement | null>(null);
  const needsInvite = form.role === "teacher" || form.role === "admin";
  const minLenOk = form.password.length >= 8;
  const matchOk = form.confirm.length > 0 && form.password === form.confirm;
  const emailValid = form.email.length === 0 || emailRe.test(form.email);
  const isValid = form.full_name.trim().length > 1 && emailRe.test(form.email) && minLenOk && matchOk && (!needsInvite || form.invite_code.trim().length > 0);

  const handleChange = (e: any) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleEmailBlur = () => {
    const s = suggestEmailDomain(form.email);
    setEmailSuggestion(s && s !== form.email ? s : null);
  };

  const handlePass = async (v: string) => {
    setForm((f) => ({ ...f, password: v }));
    if (!v) {
      setStrength(null);
      return;
    }
    try {
      const { default: zxcvbn } = await import("zxcvbn");
      const score = zxcvbn(v).score;
      setStrength(score);
    } catch {
      setStrength(null);
    }
  };

  const [registerState, registerAction, registerPending] = useActionState(async (_prev: RegisterState, formData: FormData) => {
    const fullName = String(formData.get("full_name") ?? "").trim();
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    const confirm = String(formData.get("confirm") ?? "");
    const role = String(formData.get("role") ?? "student");
    const inviteCode = String(formData.get("invite_code") ?? "").trim();

    if (!fullName || !email || !password) {
      const field: RegisterState["field"] = !fullName ? "full_name" : !email ? "email" : "password";
      return { status: "error" as const, error: "Пожалуйста, заполните все поля.", field };
    }

    if (!emailRe.test(email)) {
      return { status: "error" as const, error: "Неверный формат email", field: "email" };
    }

    if (password !== confirm) {
      return { status: "error" as const, error: "Пароли не совпадают.", field: "confirm" };
    }

    if ((role === "teacher" || role === "admin") && !inviteCode) {
      return { status: "error" as const, error: "Необходим код приглашения для выбранной роли.", field: "invite_code" };
    }

    try {
      await api.post("/users", {
        full_name: fullName,
        email,
        password,
        role,
        invite_code: inviteCode,
      });
      navigate("/login");
      return { status: "success" as const };
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "Ошибка регистрации";
      const text = typeof msg === "string" ? msg : Array.isArray(msg) ? msg.join("; ") : "Ошибка регистрации";
      return { status: "error" as const, error: text };
    }
  }, { status: "idle" as const });

  const registerStatus = registerState.status;
  const registerErrorField = registerState.field;
  const registerErrorMessage = registerStatus === "error" ? registerState.error ?? "" : "";

  useEffect(() => {
    if (!registerPending && registerStatus === "error" && registerErrorField) {
      if (registerErrorField === "full_name") fullNameRef.current?.focus();
      else if (registerErrorField === "email") emailRef.current?.focus();
      else if (registerErrorField === "password") passwordRef.current?.focus();
      else if (registerErrorField === "confirm") confirmRef.current?.focus();
      else if (registerErrorField === "invite_code") inviteRef.current?.focus();
    }
  }, [registerPending, registerStatus, registerErrorField]);

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "var(--page-bg)", color: "var(--page-text)", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", px: 1, width: "100vw", overflow: "visible" }}>
      <Paper elevation={7} sx={{ width: "100%", minWidth: 0, maxWidth: 460, p: { xs: 2, sm: 4 }, borderRadius: { xs: 3, sm: 5 }, boxShadow: 8, bgcolor: "var(--card-bg)", mx: "auto" }}>
        <form action={registerAction} autoComplete="off">
          <Typography variant={isMobile ? "h5" : "h4"} fontWeight={700} align="center" mb={3}>Регистрация</Typography>
          <Stack spacing={2}>
            <TextField name="full_name" label="Имя" value={form.full_name} onChange={handleChange} fullWidth variant="outlined" autoComplete="name" autoFocus inputRef={fullNameRef} disabled={registerPending} inputProps={{ autoCapitalize: "words", spellCheck: "false" }} />
            <TextField name="email" label="E-mail" type="email" value={form.email} onChange={handleChange} onBlur={handleEmailBlur} fullWidth variant="outlined" autoComplete="email" error={!emailValid} helperText={!emailValid ? "Неверный формат email" : " "} inputRef={emailRef} disabled={registerPending} inputProps={{ inputMode: "email", autoCapitalize: "none", autoCorrect: "off", spellCheck: "false" }} />
            {emailSuggestion && (
              <Box sx={{ mt: -1.5 }}>
                <Chip size="small" variant="outlined" color="primary" label={`Исправить на ${emailSuggestion}`} onClick={() => { setForm(f => ({ ...f, email: emailSuggestion })); setEmailSuggestion(null); }} />
              </Box>
            )}
            <FormControl fullWidth>
              <InputLabel id="role-label">Роль</InputLabel>
              <Select labelId="role-label" name="role" label="Роль" value={form.role} onChange={handleChange} variant="outlined" disabled={registerPending} MenuProps={{ PaperProps: { sx: { maxHeight: 220, borderRadius: 2 } }, anchorOrigin: { vertical: "bottom", horizontal: "left" }, transformOrigin: { vertical: "top", horizontal: "left" }, sx: { zIndex: 3000 } }}>
                <MenuItem value="student">Студент</MenuItem>
                <MenuItem value="teacher">Преподаватель</MenuItem>
                <MenuItem value="admin">Админ</MenuItem>
              </Select>
            </FormControl>
            {(form.role === "teacher" || form.role === "admin") && (
              <TextField name="invite_code" label="Код приглашения" value={form.invite_code} onChange={handleChange} fullWidth variant="outlined" autoComplete="one-time-code" inputRef={inviteRef} disabled={registerPending} inputProps={{ autoCapitalize: "characters", spellCheck: "false" }} />
            )}
            <TextField
              name="password"
              label="Пароль"
              type={showPass ? "text" : "password"}
              value={form.password}
              onChange={(e) => handlePass(e.target.value)}
              onKeyUp={(e) => setCapsPass((e as any).getModifierState?.("CapsLock"))}
              onKeyDown={(e) => setCapsPass((e as any).getModifierState?.("CapsLock"))}
              fullWidth
              variant="outlined"
              autoComplete="new-password"
              inputRef={passwordRef}
              disabled={registerPending}
              helperText="Минимум 8 символов"
              FormHelperTextProps={{ sx: { mt: 0.5 } }}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title="Удерживайте, чтобы показать пароль">
                      <IconButton aria-label="Показать пароль" onMouseDown={() => setShowPass(true)} onMouseUp={() => setShowPass(false)} onMouseLeave={() => setShowPass(false)} onClick={() => setShowPass((v) => !v)} edge="end" tabIndex={-1}>
                        {showPass ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                )
              }}
            />
            {strength !== null && (
              <LinearProgress variant="determinate" value={[10, 30, 55, 75, 100][strength]} sx={{ mt: -0.5, height: 8, borderRadius: 1 }} aria-label="Надёжность пароля" />
            )}
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mt: 0.5 }}>
              <Chip size="small" label="≥ 8 символов" color={minLenOk ? "success" : "default"} variant={minLenOk ? "filled" : "outlined"} />
              <Chip size="small" label="Пароли совпадают" color={matchOk ? "success" : "default"} variant={matchOk ? "filled" : "outlined"} />
            </Box>
            <Box sx={{ minHeight: 20, textAlign: "left" }}>{capsPass && <Typography color="warning.main" fontSize={13}>Включён Caps Lock</Typography>}</Box>
            <TextField
              name="confirm"
              label="Повторите пароль"
              type={showConfirm ? "text" : "password"}
              value={form.confirm}
              onChange={handleChange}
              onKeyUp={(e) => setCapsConfirm((e as any).getModifierState?.("CapsLock"))}
              onKeyDown={(e) => setCapsConfirm((e as any).getModifierState?.("CapsLock"))}
              fullWidth
              variant="outlined"
              autoComplete="new-password"
              inputRef={confirmRef}
              disabled={registerPending}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title="Удерживайте, чтобы показать пароль">
                      <IconButton aria-label="Показать пароль" onMouseDown={() => setShowConfirm(true)} onMouseUp={() => setShowConfirm(false)} onMouseLeave={() => setShowConfirm(false)} onClick={() => setShowConfirm((v) => !v)} edge="end" tabIndex={-1}>
                        {showConfirm ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                )
              }}
            />
            <Box sx={{ minHeight: 20 }}>{capsConfirm && <Typography color="warning.main" fontSize={13}>Включён Caps Lock</Typography>}</Box>
            <Box sx={{ minHeight: 22, display: "flex", alignItems: "center", justifyContent: "center" }} aria-live="assertive">{registerErrorMessage && <Typography color="error" fontSize={15}>{registerErrorMessage}</Typography>}</Box>
            <Button type="submit" variant="contained" size="large" fullWidth sx={{ mt: 1, fontWeight: 600, borderRadius: 2, fontSize: 17, py: 1.2 }} disabled={registerPending || !isValid}>{registerPending ? <CircularProgress size={26} color="inherit" /> : "Зарегистрироваться"}</Button>
          </Stack>
          <Box mt={4} textAlign="center" fontSize={15}>
            Уже есть аккаунт? <Link to="/login" style={{ color: "var(--nav-link)", textDecoration: "underline" }}>Войти</Link>
          </Box>
        </form>
      </Paper>
    </Box>
  );
};

export default Register;