import { useEffect, useMemo, useState } from "react";
import axios from "../api/axios";
import { Box, Paper, Typography, TextField, Button, Stack, Chip, useMediaQuery } from "@mui/material";
import { Link } from "react-router-dom";

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const COMMON_EMAIL_DOMAINS = ["gmail.com","googlemail.com","yahoo.com","outlook.com","hotmail.com","live.com","icloud.com","mail.ru","bk.ru","list.ru","inbox.ru","yandex.ru","yandex.com","rambler.ru","proton.me"];

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

const FORGOT_URL = "/password/forgot";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const isMobile = useMediaQuery("(max-width:600px)");
  const emailValid = useMemo(() => email.length === 0 || emailRe.test(email), [email]);
  const canSubmit = emailRe.test(email) && !submitting && cooldown === 0;

  useEffect(() => {
    if (!cooldown) return;
    const id = setInterval(() => setCooldown(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [cooldown]);

  const onBlurEmail = () => {
    const s = suggestEmailDomain(email);
    setEmailSuggestion(s && s !== email ? s : null);
  };

  const applySuggestion = () => {
    if (emailSuggestion) {
      setEmail(emailSuggestion);
      setEmailSuggestion(null);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await axios.post(FORGOT_URL, { email: email.trim() });
      setSent(true);
      setCooldown(30);
    } catch {
      setSent(true);
      setCooldown(30);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "var(--page-bg)", color: "var(--page-text)", display: "flex", alignItems: "center", justifyContent: "center", px: 1 }}>
      <Paper elevation={7} sx={{ width: "100%", maxWidth: 440, p: { xs: 2, sm: 4 }, borderRadius: { xs: 3, sm: 5 }, bgcolor: "var(--card-bg)" }}>
        <Typography variant={isMobile ? "h5" : "h4"} fontWeight={700} align="center" mb={3}>Восстановление пароля</Typography>
        {sent ? (
          <Stack spacing={2} alignItems="center">
            <Typography align="center">Если аккаунт с адресом <b>{email}</b> существует, мы отправили письмо со ссылкой для сброса пароля.</Typography>
            <Typography color="text.secondary" align="center" sx={{ mt: -1 }}>Ссылка действует ограниченное время. Проверьте «Спам», если письма нет.</Typography>
            <Button component={Link} to="/login" variant="outlined" sx={{ mt: 1 }}>Вернуться ко входу</Button>
            <Button onClick={(e)=>{ setSent(false); e.preventDefault(); }} disabled={cooldown>0}>Ввести другой адрес {cooldown>0 ? `(${cooldown}s)` : ""}</Button>
          </Stack>
        ) : (
          <form onSubmit={submit} autoComplete="off">
            <Stack spacing={2}>
              <TextField
                label="E-mail"
                type="email"
                value={email}
                onChange={(e)=>setEmail(e.target.value)}
                onBlur={onBlurEmail}
                autoFocus
                fullWidth
                autoComplete="email"
                error={!emailValid}
                helperText={!emailValid ? "Неверный формат email" : " "}
                inputProps={{ inputMode: "email", autoCapitalize: "none", autoCorrect: "off", spellCheck: "false" }}
              />
              {emailSuggestion && (
                <Chip size="small" variant="outlined" color="primary" label={`Исправить на ${emailSuggestion}`} onClick={applySuggestion} />
              )}
              <Button type="submit" variant="contained" size="large" fullWidth disabled={!canSubmit}>{submitting ? "Отправляю…" : "Отправить ссылку"}</Button>
              <Button component={Link} to="/login" variant="text">Назад ко входу</Button>
            </Stack>
          </form>
        )}
      </Paper>
    </Box>
  );
}