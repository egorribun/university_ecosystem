;(function () {
  if (window.__UE_THEME_INIT_SCRIPT_RAN__) return
  window.__UE_THEME_INIT_SCRIPT_RAN__ = true
  // 1. Theme Initialization
  var s = null
  try {
    s = localStorage.getItem("ue-mode")
  } catch (e) {}
  var m = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
  var dark = s ? s === "dark" : m
  var html = document.documentElement
  if (dark) html.classList.add("dark")

  // 2. Language Detection — MUST match SSR's extractLangFromRequest (ssrTheme.ts:resolveLang)
  // which reads the "ue:language" cookie and defaults to "ru". Prefer that
  // cookie before the localStorage mirror so the pre-paint and SSR languages
  // remain identical even when one browser storage was manually cleared.
  var lang = "ru"
  try {
    var cookieMatch = document.cookie.match(/(?:^|;\s*)ue:language=(ru|en)(?:;|$)/)
    if (cookieMatch) {
      lang = cookieMatch[1]
    } else {
      var storedLang = localStorage.getItem("ue:language")
      if (storedLang === "en" || storedLang === "ru") {
        lang = storedLang
      }
    }
  } catch (error) {}
  html.setAttribute("lang", lang)
  window.__UE_SELECTED_LANG__ = lang

  // 3. Static Shell Hooks
  import("/static-shell-i18n.js")
    .then(function (mod) {
      mod.applyDocumentLanguage(document, lang)
      mod.applyMetaTranslations(document, lang)
    })
    .catch(function () {})
})()
