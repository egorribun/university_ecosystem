import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

import {
  scanBackendCatalog,
  scanBackendSource,
  scanBackendRepository,
  parsePythonTranslationCatalog,
  scanLanguagePersistence,
  scanLocaleCatalogs,
  scanScopeContract,
  scanSource,
  machineReadableReport,
  scanRepository,
  validateDynamicRegistry,
} from "./i18n-scanner.mjs"

const FIXTURE_ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "i18n")

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

test("camelCase accessibility props are treated as user-facing literals", () => {
  const report = scanSource('<Skeleton ariaLabel="Loading profile" />', {
    filePath: "src/components/Skeleton.tsx",
    catalogs,
  })

  assert.ok(report.errors.some((error) => error.code === "RAW_USER_FACING_LITERAL"))
})

test("default values for user-facing labels are treated as raw literals", () => {
  const report = scanSource(
    'function ActionMenu({ ariaLabel = "Open menu" }) { return <button aria-label={ariaLabel} /> }',
    { filePath: "src/components/ActionMenu.tsx", catalogs }
  )

  assert.ok(report.errors.some((error) => error.code === "RAW_USER_FACING_LITERAL"))
})

test("translation fallback literals are detected in nested call arguments", () => {
  const report = scanSource(
    'export const View = ({ t }) => <><span>{t("common:save", "Save")}</span><span>{t("common:save", { defaultValue: "Save" })}</span></>',
    { filePath: "src/View.tsx", catalogs }
  )

  assert.equal(report.errors.filter((error) => error.code === "RAW_USER_FACING_LITERAL").length, 2)
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

test("catalog fixture exercises interpolation, plural, date, and number failures", async () => {
  const fixture = JSON.parse(
    await readFile(path.join(FIXTURE_ROOT, "catalog-mismatch.json"), "utf8")
  )
  const report = scanLocaleCatalogs(fixture)

  assert.ok(report.errors.some((entry) => entry.code === "PLACEHOLDER_MISMATCH"))
  assert.ok(report.errors.some((entry) => entry.code === "PLURAL_VARIANTS_MISMATCH"))
  assert.ok(report.errors.some((entry) => entry.code === "FORMAT_SPEC_MISMATCH"))
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

test("formatter fixture keeps locale-less date and number constructors red", async () => {
  const source = await readFile(path.join(FIXTURE_ROOT, "formatters.tsx.txt"), "utf8")
  const report = scanSource(source, { filePath: "fixture/formatters.tsx", catalogs })
  assert.equal(report.errors.filter((entry) => entry.code === "FORMATTER_LOCALE_MISSING").length, 2)
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

test("contract fixtures keep the scanner fail-closed for static keys and raw literals", async () => {
  const missingStatic = await readFile(path.join(FIXTURE_ROOT, "missing-static.tsx.txt"), "utf8")
  const rawLiteral = await readFile(path.join(FIXTURE_ROOT, "raw-literal.tsx.txt"), "utf8")

  const missingReport = scanSource(missingStatic, {
    filePath: "fixture/missing-static.tsx",
    catalogs,
  })
  assert.ok(missingReport.errors.some((entry) => entry.code === "TRANSLATION_KEY_MISSING"))

  const rawReport = scanSource(rawLiteral, { filePath: "fixture/raw-literal.tsx", catalogs })
  assert.ok(rawReport.errors.some((entry) => entry.code === "RAW_USER_FACING_LITERAL"))
})

test("dynamic registry rejects wildcard and empty entries instead of becoming an allow-all", () => {
  const report = validateDynamicRegistry({
    "events:${kind}": ["events:*"],
    "*": ["events:created"],
    empty: [],
    malformed: ["events:created", 42],
  })

  assert.ok(report.errors.some((entry) => entry.code === "DYNAMIC_REGISTRY_WILDCARD"))
  assert.ok(report.errors.some((entry) => entry.code === "DYNAMIC_REGISTRY_EMPTY"))
  assert.ok(report.errors.some((entry) => entry.code === "DYNAMIC_REGISTRY_VALUE_INVALID"))
})

test("scope contract explicitly excludes tests, generated sources, and vendors", () => {
  const report = scanScopeContract([
    "src/App.tsx",
    "src/components/Button.tsx",
    "src/components/Button.test.tsx",
    "src/generated/client.ts",
    "src/vendor/widget.ts",
    "tests/fixtures/intentional-raw.tsx",
  ])

  assert.equal(report.errors.length, 0)
  assert.deepEqual(report.excluded.sort(), [
    "src/components/Button.test.tsx",
    "src/generated/client.ts",
    "src/vendor/widget.ts",
    "tests/fixtures/intentional-raw.tsx",
  ])
  assert.deepEqual(report.included, ["src/App.tsx", "src/components/Button.tsx"])
})

test("backend email and notification template keys resolve in both locales", () => {
  const backendCatalog = {
    "email.reset.subject": { en: "Password reset", ru: "Сброс пароля" },
    "notifications.events.title_with_name": {
      en: "New event: {title}",
      ru: "Новое мероприятие: {title}",
    },
  }
  const report = scanBackendSource(
    `
from app.core.localization import translate

subject = translate("email.reset.subject", locale=locale)
title = translate("notifications.events.title_with_name", locale=locale, title=name)
`,
    { filePath: "app/services/notification_templates.py", catalog: backendCatalog }
  )

  assert.equal(report.errors.length, 0)
  assert.equal(report.references.length, 2)
})

test("backend repository scan rejects a missing key outside template modules", () => {
  const report = scanBackendSource(
    'detail = translate("errors.backendOnlyMissing", locale=locale)',
    {
      filePath: "app/services/account_service.py",
      catalog: { "errors.not_found": { en: "Not found", ru: "Не найдено" } },
    }
  )

  assert.ok(report.errors.some((entry) => entry.code === "TRANSLATION_KEY_MISSING"))
})

test("backend Python-format placeholders must match between RU and EN", () => {
  const report = scanBackendSource('translate("email.reset.greeting", locale=locale, name=name)', {
    filePath: "app/utils/email.py",
    catalog: {
      "email.reset.greeting": { en: "Hello{name}!", ru: "Здравствуйте{other}!" },
    },
  })

  assert.ok(report.errors.some((entry) => entry.code === "PLACEHOLDER_MISMATCH"))
})

test("backend Python date and number format specs must match", () => {
  const report = scanBackendCatalog({
    "report.generated": { en: "Generated {value:.2f}", ru: "Создано {value:d}" },
  })

  assert.ok(report.errors.some((entry) => entry.code === "FORMAT_SPEC_MISMATCH"))
})

test("backend source checks format specs and does not truncate computed string expressions", () => {
  const sourceReport = scanBackendSource('translate("report.generated", locale=locale)', {
    filePath: "app/services/report_service.py",
    catalog: {
      "report.generated": { en: "Generated {value:.2f}", ru: "Создано {value:d}" },
    },
  })
  assert.ok(sourceReport.errors.some((entry) => entry.code === "FORMAT_SPEC_MISMATCH"))

  const dynamicReport = scanBackendSource('translate("report.one" if enabled else "report.two")', {
    filePath: "app/services/report_service.py",
    catalog: {
      "report.one": { en: "One", ru: "Один" },
      "report.two": { en: "Two", ru: "Два" },
    },
    dynamicRegistry: {
      '"report.one" if enabled else "report.two"': ["report.one", "report.two"],
    },
  })
  assert.equal(dynamicReport.errors.length, 0)
  assert.equal(dynamicReport.dynamicReferences[0]?.registered, true)
})

test("backend catalog rejects unsupported locale entries", () => {
  const report = scanBackendCatalog({
    "report.title": { en: "Report", ru: "Отчёт", de: "Bericht" },
  })

  assert.ok(report.errors.some((entry) => entry.code === "BACKEND_LOCALE_ORPHAN"))
})

test("backend catalog parser decodes Python escapes exactly once for keys and values", () => {
  const source = String.raw`TRANSLATIONS = {
    "literal\\nkey": {
        "en": "literal\\nvalue",
        "ru": "literal\\nvalue",
    },
    "decoded": {
        "en": "line\nvalue and \"quotes\"",
        "ru": "line\nvalue and \"quotes\"",
    },
}`

  assert.deepEqual(parsePythonTranslationCatalog(source), {
    "literal\\nkey": {
      en: "literal\\nvalue",
      ru: "literal\\nvalue",
    },
    decoded: {
      en: 'line\nvalue and "quotes"',
      ru: 'line\nvalue and "quotes"',
    },
  })
})

test("backend raw user-facing assignments are rejected", () => {
  const report = scanBackendSource('title = "Save changes"', {
    filePath: "app/services/account_service.py",
    catalog: {},
  })

  assert.ok(report.errors.some((entry) => entry.code === "RAW_USER_FACING_LITERAL"))
})

test("backend dynamic translation keys require a finite backend registry", () => {
  const report = scanBackendSource(
    'return translate(f"notifications.{topic}.title", locale=locale)',
    {
      filePath: "app/services/notification_templates.py",
      catalog: { "notifications.news.title": { en: "News", ru: "Новости" } },
    }
  )

  assert.ok(report.errors.some((entry) => entry.code === "DYNAMIC_KEY_UNREGISTERED"))
})

test("repository backend scope has terminal RU/EN evidence", async () => {
  const report = await scanBackendRepository()
  assert.equal(report.ok, true)
  const basenames = report.files.map((filePath) => path.basename(filePath))
  assert.ok(basenames.includes("email.py"))
  assert.ok(basenames.includes("notification_templates.py"))
  assert.ok(report.files.length >= 20)
  assert.ok(report.references.length > 0)
  assert.equal(report.catalogReport.errors.length, 0)
})

test("repository report retains a stable machine-readable contract", async () => {
  const report = await scanRepository({ includeBackend: false })
  const machine = machineReadableReport(report)
  assert.equal(machine.ok, true)
  assert.ok(Array.isArray(machine.errors))
  assert.ok(Array.isArray(machine.references))
  assert.equal(machine.backend.references.length, 0)
  assert.ok(machine.registry.entries > 0)
  assert.ok(
    machine.scope.excluded.some((filePath) =>
      /(?:^|\/)(?:test|tests|__tests__)(?:\/|$)/u.test(filePath)
    ),
    "scope report must enumerate excluded test sources"
  )
  assert.doesNotThrow(() => JSON.stringify(machine))
})
