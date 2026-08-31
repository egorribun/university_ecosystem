import assert from "node:assert/strict"
import test from "node:test"

import { scanSource, scanLocaleCatalogs, scanLanguagePersistence } from "./i18n-scanner.mjs"

const catalogs = {
  en: {
    common: {
      save: "Save {{name}}",
      count_one: "{{count}} item",
      count_other: "{{count}} items",
    },
    events: { created: "Created" },
  },
  ru: {
    common: {
      save: "Сохранить {{name}}",
      count_one: "{{count}} элемент",
      count_other: "{{count}} элемента",
    },
    events: { created: "Создано" },
  },
}

test("static keys must exist in both locale catalogs and interpolate the same variables", () => {
  const report = scanSource(
    'import { useTranslation } from "react-i18next"; export function View(){ const { t } = useTranslation("common"); return <button>{t("save", { name: "Ada" })}</button> }',
    { filePath: "src/View.tsx", catalogs }
  )

  assert.equal(report.errors.length, 0)
  assert.equal(report.references[0].key, "common:save")
})

test("dynamic keys require an explicit finite registry entry", () => {
  const source =
    'const key = Math.random() > 0.5 ? "created" : "missing"; export const View = ({t}) => <span>{t(`events:${key}`)}</span>'
  const missing = scanSource(source, { filePath: "src/View.tsx", catalogs })
  assert.ok(missing.errors.some((error) => error.code === "DYNAMIC_KEY_UNREGISTERED"))

  const registered = scanSource(source, {
    filePath: "src/View.tsx",
    catalogs,
    dynamicRegistry: { "events:${key}": ["events:created"] },
  })
  assert.equal(registered.errors.length, 0)
})

test("raw user-facing literals are rejected while technical attributes are ignored", () => {
  const report = scanSource(
    '<button aria-label="Save" data-testid="save-button" className="primary">Save</button>',
    { filePath: "src/View.tsx", catalogs }
  )
  assert.ok(report.errors.filter((error) => error.code === "RAW_USER_FACING_LITERAL").length >= 2)
})

test("locale scanner detects missing keys, orphan keys, plural variants, and placeholders", () => {
  const report = scanLocaleCatalogs({
    en: { common: { save: "Save {{name}}", orphan: "Orphan", count_one: "one" } },
    ru: { common: { save: "Сохранить {{other}}", count_other: "many" } },
  })

  assert.ok(report.errors.some((error) => error.code === "LOCALE_KEY_MISSING"))
  assert.ok(report.errors.some((error) => error.code === "LOCALE_KEY_ORPHAN"))
  assert.ok(report.errors.some((error) => error.code === "PLACEHOLDER_MISMATCH"))
  assert.ok(report.errors.some((error) => error.code === "PLURAL_VARIANTS_MISMATCH"))
})

test("locale scanner keeps date and number interpolation formats consistent", () => {
  const report = scanLocaleCatalogs({
    en: { common: { published: "{{value, date}}", score: "{{value, number}}" } },
    ru: { common: { published: "{{value, number}}", score: "{{value, number}}" } },
  })
  assert.ok(report.errors.some((error) => error.code === "FORMAT_SPEC_MISMATCH"))
})

test("plural translation calls provide a count option", () => {
  const report = scanSource('export const View = ({t}) => <span>{t("common:count")}</span>', {
    filePath: "src/View.tsx",
    catalogs,
  })
  assert.ok(report.errors.some((error) => error.code === "PLURAL_COUNT_MISSING"))
})

test("date and number constructors must receive an explicit locale", () => {
  const report = scanSource(
    "const date = new Intl.DateTimeFormat().format(value); const number = new Intl.NumberFormat().format(value)",
    { filePath: "src/View.ts", catalogs }
  )
  assert.equal(report.errors.filter((error) => error.code === "FORMATTER_LOCALE_MISSING").length, 2)
})

test("language persistence is browser-only and hydration-safe", () => {
  const valid = scanLanguagePersistence(`
    const [language] = useState(() => resolveInitialLanguage());
    useEffect(() => { localStorage.setItem("ue:language", language); }, [language]);
  `)
  assert.equal(valid.errors.length, 0)

  const invalid = scanLanguagePersistence(`
    const [language] = useState(() => navigator.language);
    const saved = localStorage.getItem("ue:language");
  `)
  assert.ok(invalid.errors.some((error) => error.code === "HYDRATION_UNSAFE_LANGUAGE_READ"))
  assert.ok(invalid.errors.some((error) => error.code === "LANGUAGE_STORAGE_DURING_RENDER"))
})
