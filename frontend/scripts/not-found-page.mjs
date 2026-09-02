/**
 * Product 404 document used before the React application is booted.
 *
 * The fallback deliberately has no application bundle or data fetches. It is
 * generated from trusted, localized strings and progressively enhanced by the
 * tiny static-shell i18n module in `public/not-found-i18n.js`.
 */

const NOT_FOUND_STRINGS = Object.freeze({
  ru: Object.freeze({
    pageTitle: "Страница не найдена — Экосистема ГУУ",
    title: "Страница не найдена",
    description:
      "Похоже, такой страницы нет. Вернитесь в экосистему ГУУ или войдите в личный кабинет.",
    home: "Вернуться на главную",
    login: "Войти в систему",
  }),
  en: Object.freeze({
    pageTitle: "Page not found — GUU Ecosystem",
    title: "Page not found",
    description:
      "This page does not exist. Return to the GUU ecosystem or sign in to your dashboard.",
    home: "Return to dashboard",
    login: "Sign in",
  }),
})

const HTML_ESCAPE_MAP = Object.freeze({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
})

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/gu, (character) => HTML_ESCAPE_MAP[character])
}

export function normalizeNotFoundLanguage(language) {
  if (language === "en" || language === "ru") return language
  if (typeof language === "string") {
    const normalized = language.toLowerCase()
    if (normalized.startsWith("en")) return "en"
    if (normalized.startsWith("ru")) return "ru"
  }
  return "ru"
}

export function renderNotFoundPage(language = "ru") {
  const normalizedLanguage = normalizeNotFoundLanguage(language)
  const strings = NOT_FOUND_STRINGS[normalizedLanguage]
  const safeLanguage = escapeHtml(normalizedLanguage)

  return `<!doctype html>
<html lang="${safeLanguage}" data-not-found-page>
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="description" content="${escapeHtml(strings.description)}">
    <meta name="theme-color" content="#f7f8fc">
    <title>${escapeHtml(strings.pageTitle)}</title>
    <style>
      :root {
        color-scheme: light;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #f7f8fc;
        color: #172033;
      }
      * { box-sizing: border-box; }
      body {
        min-width: 320px;
        min-height: 100svh;
        margin: 0;
        background: #f7f8fc;
      }
      .not-found-shell {
        display: grid;
        min-height: 100svh;
        place-items: center;
        padding: max(24px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right)) max(24px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left));
      }
      .not-found-card {
        width: min(100%, 560px);
        padding: clamp(28px, 7vw, 56px);
        border: 1px solid #e1e5ef;
        border-radius: 24px;
        background: #fff;
        box-shadow: 0 18px 48px rgb(27 38 72 / 10%);
        text-align: center;
      }
      .not-found-code {
        margin: 0 0 12px;
        color: #4b5fc3;
        font-size: clamp(3.5rem, 17vw, 6.5rem);
        font-weight: 760;
        letter-spacing: -.07em;
        line-height: .9;
      }
      h1 {
        margin: 0;
        color: #172033;
        font-size: clamp(1.45rem, 5vw, 2rem);
        line-height: 1.2;
      }
      .not-found-description {
        max-width: 42ch;
        margin: 16px auto 0;
        color: #556176;
        font-size: 1rem;
        line-height: 1.6;
      }
      .not-found-actions {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 12px;
        margin-top: 28px;
      }
      .not-found-action {
        display: inline-flex;
        min-height: 44px;
        align-items: center;
        justify-content: center;
        padding: 10px 18px;
        border: 1px solid #4b5fc3;
        border-radius: 12px;
        color: #fff;
        background: #4b5fc3;
        font-size: .95rem;
        font-weight: 650;
        line-height: 1.25;
        text-decoration: none;
        transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
      }
      .not-found-action.secondary {
        color: #35436f;
        background: #fff;
      }
      .not-found-action:hover { transform: translateY(-1px); }
      .not-found-action:focus-visible {
        outline: 3px solid rgb(75 95 195 / 35%);
        outline-offset: 3px;
      }
      @media (prefers-reduced-motion: reduce) {
        .not-found-action { transition: none; }
        .not-found-action:hover { transform: none; }
      }
    </style>
  </head>
  <body>
    <main class="not-found-shell" id="main-content" aria-labelledby="not-found-title">
      <section class="not-found-card">
        <p class="not-found-code" aria-hidden="true">404</p>
        <h1 id="not-found-title" data-i18n="notFound.title">${escapeHtml(strings.title)}</h1>
        <p class="not-found-description" data-i18n="notFound.description">${escapeHtml(strings.description)}</p>
        <nav class="not-found-actions">
          <a class="not-found-action" href="/dashboard" data-i18n="notFound.home">${escapeHtml(strings.home)}</a>
          <a class="not-found-action secondary" href="/login" data-i18n="notFound.login">${escapeHtml(strings.login)}</a>
        </nav>
      </section>
    </main>
    <script type="module" src="/not-found-i18n.js" defer></script>
  </body>
</html>
`
}

export { NOT_FOUND_STRINGS }
