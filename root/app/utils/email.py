import ssl, smtplib
from email.message import EmailMessage
from app.core.config import settings

def _build_html(link: str, full_name: str) -> str:
  name = f", {full_name}" if full_name else ""
  return f"""
  <div style="font-family:Inter,Arial,sans-serif">
    <h2>Сброс пароля</h2>
    <p>Здравствуйте{name}!</p>
    <p>Вы запросили сброс пароля в Экосистеме ГУУ. Ссылка действует 45 минут.</p>
    <p><a href="{link}" style="display:inline-block;padding:10px 16px;background:#1d5fff;color:#fff;border-radius:8px;text-decoration:none">Сбросить пароль</a></p>
    <p>Если вы не запрашивали сброс, проигнорируйте это письмо.</p>
  </div>
  """

def send_reset_email(to_email: str, link: str, full_name: str = "") -> None:
  host = settings.smtp_host
  port = settings.smtp_port
  user = settings.smtp_user
  password = settings.smtp_password
  starttls = settings.smtp_starttls
  mail_from = settings.mail_from

  msg = EmailMessage()
  msg["Subject"] = "Сброс пароля — Экосистема ГУУ"
  msg["From"] = mail_from
  msg["To"] = to_email
  msg.set_content(f"Ссылка для сброса пароля: {link}\nОна действует 45 минут.")
  msg.add_alternative(_build_html(link, full_name), subtype="html")

  context = ssl.create_default_context()
  if starttls:
    with smtplib.SMTP(host, port) as s:
      s.starttls(context=context)
      if user:
        s.login(user, password)
      s.send_message(msg)
  else:
    with smtplib.SMTP_SSL(host, port, context=context) as s:
      if user:
        s.login(user, password)
      s.send_message(msg)