const storageKey = "ue:language";
const fallbackLanguage = "ru";
const supportedLanguages = ["ru", "en"];

const translations = {
  ru: {
    meta: {
      title: "Экосистема ГУУ",
      description:
        "Всё необходимое — профиль, расписание, новости и события кампуса — в одном месте.",
      ogTitle: "Экосистема ГУУ",
      ogDescription:
        "Личный кабинет: профиль, расписание, новости и события кампуса.",
      twitterTitle: "Экосистема ГУУ",
      twitterDescription:
        "Личный кабинет: профиль, расписание, новости и события кампуса.",
      ogLocale: "ru_RU",
    },
    offline: {
      pageTitle: "Экосистема ГУУ — офлайн режим",
      title: "Нет подключения к сети",
      description:
        "Экосистема ГУУ автоматически синхронизирует расписание, новости и карту кампуса, как только вы вернётесь в сеть.",
      hints: [
        "Расписание и новости, просмотренные ранее, останутся доступными офлайн.",
        "Карта кампуса обновится автоматически после восстановления подключения.",
      ],
      retry: "Повторить попытку",
      footer: "Проверьте подключение или попробуйте открыть приложение позднее.",
    },
    notFound: {
      pageTitle: "Страница не найдена — Экосистема ГУУ",
      title: "Страница не найдена",
      description:
        "Похоже, такой страницы нет. Вернитесь в экосистему ГУУ или войдите в личный кабинет.",
      home: "Вернуться на главную",
      login: "Войти в систему",
    },
    manifest: {
      name: "Экосистема ГУУ — всё необходимое в одном месте",
      short_name: "Экосистема ГУУ",
      description:
        "Профиль, расписание, новости и карта кампуса — доступны даже офлайн.",
      shortcuts: [
        { name: "Расписание", description: "Открыть расписание занятий" },
        { name: "Новости", description: "Читать свежие новости кампуса" },
        { name: "Карта кампуса", description: "Найти корпуса и маршруты на карте ГУУ" },
      ],
    },
  },
  en: {
    meta: {
      title: "GUU Ecosystem",
      description:
        "Everything you need—profile, schedule, news, and campus events—in one place.",
      ogTitle: "GUU Ecosystem",
      ogDescription:
        "Dashboard: profile, schedule, news, and campus events.",
      twitterTitle: "GUU Ecosystem",
      twitterDescription:
        "Dashboard: profile, schedule, news, and campus events.",
      ogLocale: "en_US",
    },
    offline: {
      pageTitle: "GUU Ecosystem — offline mode",
      title: "No network connection",
      description:
        "GUU Ecosystem automatically syncs your schedule, news, and campus map as soon as you're back online.",
      hints: [
        "Schedule and news you've already opened stay available offline.",
        "The campus map refreshes automatically when the connection is restored.",
      ],
      retry: "Try again",
      footer: "Check your connection or open the app again later.",
    },
    notFound: {
      pageTitle: "Page not found — GUU Ecosystem",
      title: "Page not found",
      description:
        "This page does not exist. Return to the GUU ecosystem or sign in to your dashboard.",
      home: "Return to dashboard",
      login: "Sign in",
    },
    manifest: {
      name: "GUU Ecosystem — everything in one place",
      short_name: "GUU Ecosystem",
      description:
        "Profile, schedule, news, and the campus map stay available even when you're offline.",
      shortcuts: [
        { name: "Schedule", description: "Open today's class schedule" },
        { name: "News", description: "Read the latest campus updates" },
        { name: "Campus map", description: "Find buildings and routes on the GUU map" },
      ],
    },
  },
};

function normalizeLanguage(language) {
  if (language === "en" || language === "ru") {
    return language;
  }
  if (typeof language === "string") {
    const lower = language.toLowerCase();
    if (lower.startsWith("en")) {
      return "en";
    }
    if (lower.startsWith("ru")) {
      return "ru";
    }
  }
  return fallbackLanguage;
}

export function detectLanguage(options = {}) {
  const { storedLanguage, navigatorLanguage } = options;
  if (storedLanguage && supportedLanguages.includes(storedLanguage)) {
    return storedLanguage;
  }
  return normalizeLanguage(navigatorLanguage);
}

export function getPreferredLanguage(win = typeof window !== "undefined" ? window : undefined) {
  let stored;
  if (win && win.localStorage) {
    try {
      stored = win.localStorage.getItem(storageKey);
    } catch (error) {
      // Ignore storage access errors (e.g. privacy mode)
    }
  }
  const navigatorLanguage = win && win.navigator ? win.navigator.language : undefined;
  return detectLanguage({ storedLanguage: stored, navigatorLanguage });
}

function getLanguageBundle(language) {
  const normalized = normalizeLanguage(language);
  return translations[normalized] ?? translations[fallbackLanguage];
}

export function getStrings(language) {
  return getLanguageBundle(language);
}

export function getManifestStrings(language) {
  const bundle = getLanguageBundle(language);
  return bundle.manifest;
}

export function getManifestPath(language) {
  return normalizeLanguage(language) === "en" ? "/manifest.en.webmanifest" : "/manifest.webmanifest";
}

export function applyDocumentLanguage(doc, language) {
  if (!doc || !doc.documentElement) return;
  const normalized = normalizeLanguage(language);
  doc.documentElement.setAttribute("lang", normalized);
}

function setMetaContent(doc, selector, attribute, value) {
  if (!value) return;
  const element = doc.querySelector(selector);
  if (element) {
    element.setAttribute(attribute, value);
  }
}

export function applyMetaTranslations(doc, language) {
  if (!doc) return;
  const bundle = getLanguageBundle(language);
  const meta = bundle.meta;
  if (!meta) return;

  doc.title = meta.title;
  setMetaContent(doc, 'meta[name="description"]', "content", meta.description);
  setMetaContent(doc, 'meta[property="og:title"]', "content", meta.ogTitle || meta.title);
  setMetaContent(doc, 'meta[property="og:description"]', "content", meta.ogDescription || meta.description);
  setMetaContent(doc, 'meta[property="og:locale"]', "content", meta.ogLocale);
  setMetaContent(doc, 'meta[name="twitter:title"]', "content", meta.twitterTitle || meta.title);
  setMetaContent(
    doc,
    'meta[name="twitter:description"]',
    "content",
    meta.twitterDescription || meta.description,
  );

  const manifest = doc.querySelector('link[rel="manifest"]');
  if (manifest) {
    manifest.setAttribute("href", getManifestPath(language));
    if (!manifest.hasAttribute("crossorigin")) {
      manifest.setAttribute("crossorigin", "use-credentials");
    }
  }
}

function setTextContent(doc, key, value) {
  if (!value) return;
  const target = doc.querySelector(`[data-i18n="${key}"]`);
  if (target) {
    target.textContent = value;
  }
}

export function applyOfflineTranslations(doc, language) {
  if (!doc) return;
  const bundle = getLanguageBundle(language);
  const offline = bundle.offline;
  if (!offline) return;

  doc.title = offline.pageTitle;
  setTextContent(doc, "offline.title", offline.title);
  setTextContent(doc, "offline.description", offline.description);
  const hints = Array.isArray(offline.hints) ? offline.hints : [];
  hints.forEach((hint, index) => {
    setTextContent(doc, `offline.hints.${index}`, hint);
  });
  setTextContent(doc, "offline.retry", offline.retry);
  setTextContent(doc, "offline.footer", offline.footer);
}

export function applyNotFoundTranslations(doc, language) {
  if (!doc) return;
  const bundle = getLanguageBundle(language);
  const notFound = bundle.notFound;
  if (!notFound) return;

  doc.title = notFound.pageTitle;
  setTextContent(doc, "notFound.title", notFound.title);
  setTextContent(doc, "notFound.description", notFound.description);
  setTextContent(doc, "notFound.home", notFound.home);
  setTextContent(doc, "notFound.login", notFound.login);
}

export { storageKey, fallbackLanguage, supportedLanguages, translations };
