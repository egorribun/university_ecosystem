import {
  applyDocumentLanguage,
  applyNotFoundTranslations,
  getPreferredLanguage,
} from "./static-shell-i18n.js"

const language = getPreferredLanguage()
applyDocumentLanguage(document, language)
applyNotFoundTranslations(document, language)
