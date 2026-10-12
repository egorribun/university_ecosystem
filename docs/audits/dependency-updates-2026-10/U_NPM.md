# U_NPM

Снимок: origin/egorribun 04fdd84c2 (git archive). Дата проверки: 2026-10-12 07:29Z. Рабочий репозиторий не трогался, ничего не устанавливалось, команды не выполнялись.

## Политика
- Cooldown 7 дней: Renovate `minimumReleaseAge: "7 days"` для npm (minor автомёрджится через `:automergeMinor`, major с `automerge: false`), Dependabot `cooldown.default-days: 7`, `frontend/.npmrc` `min-release-age=7`. Отсечка публикации 2026-10-05T07:29Z; более новые версии помечены «рано». Security-алерты: `vulnerabilityAlerts.minimumReleaseAge: null`, `prCreation: immediate`, без automerge. Нужна запись одобрения по `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md` (процедура описана только для uv, для npm по аналогии). `security/audit-allowlist.yaml`: npm-исключений нет, кроме glob 13.0.6 до 2026-12-31.
- Toolchain: Node 24 (`engines` >=24.0.0, `node:24-alpine` по digest, CI `node-version: "24"`), npm 11.17.0 (`packageManager`). `frontend/.npmrc`: `legacy-peer-deps=true`, `engine-strict=true`, `min-release-age=7`. Корневого `.npmrc` нет. frontend/AGENTS.md: React 19.2+, TS 5.7+ strict, Vite 8 + Rolldown, TanStack Router 1.168+ и Query 5.90+, Zustand 5.0+, только Valibot.
- Exact-pin (меняется только правкой package.json): vitest, @vitest/coverage-v8, @vitest/utils 4.1.11; @playwright/test и playwright 1.63.0; knip 6.37.0; globals 17.12.0; axe-core 4.13.0; @stryker-mutator/instrumenter, typescript-checker, util 10.0.0; @tanstack/router-core 1.171.32; eslint-plugin-boundaries 7.2.0; glob 13.0.6; overrides `@opentelemetry/core` 2.8.0, `handlebars` 4.7.10 (frontend), `chrome-launcher` 1.2.1; picomatch 2.3.2 в boundary-адаптере (тест ассертит версию).
- Запрещено обновлять без отдельного решения: все major (отдельные PR с ручной проверкой); TypeScript 7 и picomatch 4 пока блокеры. Наблюдения: peer `eslint-plugin-react` 7.37.5 и `eslint-plugin-jsx-a11y` 6.10.2 объявляют `eslint <=9`, при ESLint 10 конфликт скрыт `legacy-peer-deps`. `zod 4.6.5` попадает в prod-дерево транзитивно (импортов в коде нет).

## Patch/minor — можно обновить
Итого 32 записи: 30 прямых зависимостей, override `@opentelemetry/core`, транзитивный security-фикс `handlebars`.

| Пакет | Где (манифест) | Сейчас (lock) | → Версия | Дата | Cooldown | Security | Риск |
|---|---|---|---|---|---|---|---|
| handlebars | корневой lock, транзитивно (conventional-changelog-writer 8.4.0, `^4.7.7`), dev | 4.7.9 | 4.7.10 | 2026-10-05 | рано до 2026-10-12 22:37Z; security-исключение | **да**: GHSA-8r5x-fm3f-whwj, GHSA-p8wg-vrv2-v86f, GHSA-xw65-4hp5-5hc7 (CVE-2026-106444/-106445/-106446) | низкий (dev). В frontend lock уже 4.7.10. В корневом package.json нужен override: 8.x фикса нет |
| @opentelemetry/core | frontend overrides `2.8.0` (exact) | 2.8.0 | 2.11.0 | 2026-08-31 | ок | нет | средний: sdk-trace-base/web и resources 2.11.0 требуют точно core 2.11.0, сейчас рассогласование |
| @sentry/react | frontend deps `^10.20.0` | 10.75.2 | 10.76.0 | 2026-10-02 | ок | нет | низкий |
| @tanstack/react-query | frontend deps `^5.90.21` | 5.103.2 | 5.104.1 | 2026-10-02 | ок | нет | низкий |
| @tanstack/react-query-persist-client | frontend deps `^5.90.23` | 5.103.2 | 5.104.1 | 2026-10-02 | ок | нет | низкий; вместе с react-query |
| @tanstack/react-router | frontend deps `^1.168.8` | 1.170.38 | 1.170.41 | 2026-09-30 | ок | нет | низкий; тянет router-core 1.171.34, обновлять вместе с router-core |
| @tanstack/react-start | frontend deps `^1.167.62` | 1.168.57 | 1.168.60 | 2026-09-30 | ок | нет | средний: SSR, требует react-router 1.170.41 |
| @tanstack/router-core | frontend deps `1.171.32` (exact) | 1.171.32 | 1.171.34 | 2026-09-30 | ок | нет | низкий; менять одновременно с react-router |
| @tanstack/react-table | frontend deps `^9.1.2` | 9.2.4 | 9.2.6 | 2026-10-04 | ок | нет | низкий |
| focus-trap | frontend deps `^8.2.2` | 8.2.2 | 8.2.3 | 2026-10-04 | ок | нет | низкий; проверить модалки (a11y e2e) |
| framer-motion | frontend deps `^13.1.0` | 13.4.1 | 13.5.1 | 2026-10-02 | ок | нет | низкий; шаг перед major 14 |
| lucide-react | frontend deps `^1.31.0` | 1.47.0 | 1.52.0 | 2026-10-04 | ок | нет | низкий; снапшоты иконок |
| maplibre-gl | frontend deps `^6.4.0` | 6.10.0 | 6.12.0 | 2026-10-03 | ок | нет | средний: карта, worker-ассеты |
| react-hook-form | frontend deps `^7.71.1` | 7.88.0 | 7.89.0 | 2026-09-26 | ок | нет | низкий |
| @chromatic-com/storybook | devDeps `^5.1.2` | 5.3.1 | 5.4.0 | 2026-10-01 | ок | нет | низкий |
| @storybook/addon-a11y | devDeps `^10.2.13` | 10.6.0 | 10.6.1 | 2026-09-29 | ок | нет | низкий; все @storybook/* и storybook одной версией |
| @storybook/addon-docs | devDeps `^10.2.13` | 10.6.0 | 10.6.1 | 2026-09-29 | ок | нет | низкий |
| @storybook/addon-onboarding | devDeps `^10.2.13` | 10.6.0 | 10.6.1 | 2026-09-29 | ок | нет | низкий |
| @storybook/addon-vitest | devDeps `^10.2.13` | 10.6.0 | 10.6.1 | 2026-09-29 | ок | нет | низкий; 10.6.1 первый с peer vitest ^5, нужен для vitest 5 |
| @storybook/react-vite | devDeps `^10.2.13` | 10.6.0 | 10.6.1 | 2026-09-29 | ок | нет | низкий |
| storybook | devDeps `^10.2.13` | 10.6.0 | 10.6.1 | 2026-09-29 | ок | нет | низкий |
| eslint-plugin-storybook | devDeps `^10.2.10` | 10.6.0 | 10.6.1 | 2026-09-29 | ок | нет | низкий |
| eslint | devDeps `^10.10.0` | 10.11.0 | 10.12.0 | 2026-10-02 | ок | нет | средний: lint с `--max-warnings=0`; peer-конфликт плагинов (см. Политику) |
| eslint-plugin-security | devDeps `^4.0.1` | 4.0.1 | 4.2.0 | 2026-10-01 | ок | нет | средний: новые правила дают warnings, падает `--max-warnings=0` |
| typescript-eslint | devDeps `^8.52.0` | 8.70.1 | 8.71.0 | 2026-09-28 | ок | нет | средний; peer `typescript <6.1.0`, TS 7 не поддерживается |
| vite | devDeps `^8.0.0` | 8.3.0 | 8.3.2 | 2026-10-01 | ок | нет | средний: сборка; тянет rolldown ~1.2.11 (1.2.12, 2026-09-30, ок) |
| globals | devDeps `17.12.0` (exact) | 17.12.0 | 17.13.0 | 2026-10-01 | ок | нет | низкий |
| knip | devDeps `6.37.0` (exact) | 6.37.0 | 6.39.0 | 2026-09-30 | ок | нет | низкий; lint:knip может найти новые unused |
| prettier | devDeps `^3.3.3` | 3.9.8 | 3.9.9 | 2026-09-23 | ок | нет | низкий; format:check |
| lint-staged | devDeps `^17.3.0` | 17.5.1 | 17.6.0 | 2026-09-26 | ок | нет | низкий |
| jsdom | devDeps `^30.0.1` | 30.1.1 | 30.1.2 | 2026-10-04 | ок | нет | низкий |
| @types/node | devDeps `^26.4.1` | 26.6.2 | 26.6.4 | 2026-10-01 | ок | нет | низкий; типы Node 26 при runtime Node 24, рассмотреть @types/node 24.x |

## Major — отдельно
Итого 12 записей: 11 из реестра и TypeScript 6 → 7.

| Пакет | Где (манифест) | Сейчас | Последний major | Дата | Breaking changes (кратко) | Затронутый код | Оценка |
|---|---|---|---|---|---|---|---|
| vitest | devDeps `4.1.11` (exact) | 4.1.11 | 5.0.3 | 2026-09-30 | Node >=22.12 и Vite >=6.4; удалены `sequential`-опции (заменены на concurrent) и deprecated entry points; `@vitest/runner` и `expect` инлайнятся; конфиг не ищется в родительских каталогах; `expect.poll` падает, если функция не резолвится; hoisting вне top-level даёт ошибку; coverage include/exclude строже; blob/json/junit по умолчанию в `.vitest/` | `describe.sequential` в `frontend/src/api/__tests__/client.instance.test.ts:395`; `expect.poll` в 21 файле; coverage-пороги (`vitest.config.ts:56-68`, Tier0 100%); `clearMocks: true` уже задан (без эффекта); `toHaveTextContent` идёт из `@testing-library/jest-dom/vitest` (`setupTests.ts:2`), не затронут | средняя-высокая; один PR вместе с @storybook/addon-vitest 10.6.1 и парой @vitest/* |
| @vitest/coverage-v8 | devDeps `4.1.11` (exact) | 4.1.11 | 5.0.3 | 2026-09-30 | peer = точная версия vitest | нет | только вместе с vitest |
| @vitest/utils | devDeps `4.1.11` (exact) | 4.1.11 | 5.0.3 | 2026-09-30 | то же | нет | только вместе с vitest |
| msw | devDeps `^2.12.7` | 2.15.0 | 3.0.2 | 2026-10-03 | ESM-only; Node >=22.12; TS >=5.9; `onUnhandledRequest` переименован в `onUnhandledFrame`; `msw/native` удалён (вынесен в @msw/react-native); graphql через `msw/graphql`; `handleRequest` заменён на `defineNetwork`; `worker.stop()` возвращает Promise; cookies в Node не управляются; событие `websocket:connection` | `frontend/src/setupTests.ts:89` (`onUnhandledRequest: "warn"`); `frontend/src/tests/mocks/generated/native.ts` (`msw/native`, попадает в tsconfig `src`); генератор msw-auto-mock 0.32.1 (peer msw >=2, совместим) | средняя; 3.0.3 рано до 2026-10-17 |
| vite-plugin-pwa | devDeps `^1.3.0` | 1.3.0 | 2.0.0 | 2026-10-03 | Node >=20.19 (README); peer vite ^8 ок; workbox ^7.4.1, в проекте 7.4.1; официального списка breaking-опций не найдено | `frontend/vite.config.mts:238-300` (`injectManifest`, `filename: sw.ts`, `registerType`, `workbox.runtimeCaching`, `devOptions`) | средняя: проверить сборку SW и dev-SW |
| framer-motion | deps `^13.1.0` | 13.4.1 | 14.0.0 | 2026-10-02 | Удалены внутренние API, восстановленные в 13.5.1; peer react ^18 и ^19 ок | 124 импорта из корня `framer-motion`, подпутей и внутренних API нет | низкая; сначала 13.5.1 |
| @sentry/react | deps `^10.20.0` | 10.75.2 | 11.4.0 | 2026-10-02 | Удалён legacy `profilesSampleRate`; `bfcacheIntegration` переименован в `bfcacheMetricsIntegration`; interaction и user-timing spans вынесены в отдельные интеграции; console-breadcrumbs через `consoleIntegration`; React 16 не поддерживается; Node >=23.2 в engines (Node 24 ок) | `frontend/src/app/observability.ts:51,58` (`profilesSampleRate`); 6 prod-файлов импортируют пакет (`logger.ts`, `observability.ts`, 4 ErrorBoundary), `captureException` и `init` без изменений | средняя: правка init-конфига и проверка трейсинга; 11.6.0 рано до 2026-10-15 |
| js-yaml | devDeps `^4.3.2` | 4.3.2 | 5.4.2 | 2026-09-13 | `load` по умолчанию CORE_SCHEMA без `!!merge`; удалены `safeLoad`/`safeLoadAll`/`safeDump`, `DEFAULT_SCHEMA`, loader-опции `onWarning`/`legacy`/`listener`, часть dumper-опций; импорт из `lib/` удалён | `frontend/scripts/run-stryker.test.mjs:5235` (`yaml.load`); merge-ключей `<<:` в `.github/workflows` нет. Override `js-yaml ^4.3.2` (frontend и root) надо переписать, иначе конфликт с direct ^5 | низкая |
| idb | devDeps `^7.1.1` | 7.1.1 | 8.0.3 | 2025-05-07 | 8.x: убрана поддержка браузеров без `cursor.request`; отдельная сборка async-итераторов удалена | `frontend/src/sw/offline.ts:4` (openDB, IDBPDatabase, prod-код SW); `frontend/src/sw/__tests__/offlineUpgrade.test.ts:1`; `frontend/src/__tests__/m1_offline_stress.test.ts:3` | низкая; пакет стоит в devDependencies, но импортируется из prod-кода: перенести в dependencies |
| @babel/parser | devDeps `^7.29.9` | 7.29.9 | 8.0.6 | 2026-09-18 | Удалена опция `locations: "packed"`; engines: Node ^22.18 или >=24.11 (с `engine-strict=true` установка упадёт на более старом Node 24); `@babel/core` 8.0.6 уже тянет parser 8 вложенно, переход убирает дубль | `frontend/scripts/i18n-scanner.mjs:17,307-320` (`babelParse` с sourceType/plugins/errorRecovery); опция `locations` не используется | низкая-средняя: нужен Node >=24.11, проверить patch-версию в `node:24-alpine` и CI |
| typescript | devDeps alias `npm:@typescript/typescript6@^6.0.2` | 6.0.2 | 7.0.2 (npm `typescript`, уже стоит как `@typescript/native`) | 2026-07-08 | По devblog TS 7.0: нет программного JS API (`createSourceFile`/`createProgram`; новый API обещан в 7.1); удалены `target: es5`, `moduleResolution` node/node10/classic, `baseUrl`, module amd/umd/systemjs; новые дефолты (strict, module, `types: []`); typescript-eslint 8.70.1-8.71.1 имеет peer `typescript <6.1.0` | `frontend/scripts/ui-barrel-boundary.test.mjs:5` и `frontend/tests/e2e-live/push-opt-in.contract.test.mjs:5` (`import ts`, compiler API); `frontend/scripts/run-stryker.mjs:3176` и `frontend/scripts/verify-stryker-evidence.mjs:1031` (`require("typescript").version`); tsconfig: `types` задан явно, `baseUrl` нет | блокер: не обновлять; `@typescript/native` 7.0.2 установлен, но в скриптах не вызывается |
| picomatch | `frontend/scripts/boundary-micromatch-compat` `2.3.2` (exact) | 2.3.2 | 4.0.7 | 2026-08-24 | 4.0.0: публичный matcher API на поддерживаемых Node не меняется; убрана проверка lookbehind для старых Node; убрана зависимость `os`; 2.3.2 содержит фикс CVE-2026-33672 | `frontend/scripts/boundary-micromatch-compat/index.cjs:8-23` (`picomatch/lib/utils`, makeRe, isMatch); `frontend/scripts/boundary-micromatch-compat.test.mjs:17,118` (ассерт версии 2.3.2) | блокер: адаптер эмулирует micromatch на 2.3.2, обновлять только с переработкой адаптера. У 2.3.2 уязвимостей по OSV нет |

## Уже актуально
Новее нет (версия lock, pin помечен): @dnd-kit/core@6.3.1, @dnd-kit/sortable@10.0.0, @dnd-kit/utilities@3.2.2, @floating-ui/react@0.27.20, @fontsource-variable/inter@5.3.0, @fontsource-variable/outfit@5.3.0, @hookform/resolvers@5.9.1, @noble/hashes@2.4.0, @opentelemetry/api@1.9.1, @opentelemetry/semantic-conventions@1.43.0, @zxcvbn-ts/core@4.2.0, @zxcvbn-ts/language-common@4.1.3, @zxcvbn-ts/language-en@4.1.1, @zxcvbn-ts/language-ru@4.1.0, axios@1.20.0, class-variance-authority@0.7.1, clsx@2.1.1, html-to-image@1.11.13, idb-keyval@6.3.0, jose@6.2.12, jspdf@4.2.1, qrcode.react@4.2.0, react@19.3.0, react-dom@19.3.0, react-map-gl@8.1.3, rxjs@7.8.2, tailwind-merge@3.7.0, valibot@1.5.0, zustand@5.0.15, @axe-core/playwright@4.13.0, @eslint/js@10.0.1, @faker-js/faker@10.6.0, @hey-api/openapi-ts@0.99.0, @lhci/cli@0.15.1, @rolldown/plugin-babel@0.2.4, @stryker-mutator/api@10.0.0, @stryker-mutator/core@10.0.0, @stryker-mutator/instrumenter@10.0.0 (pin), @stryker-mutator/typescript-checker@10.0.0 (pin), @stryker-mutator/util@10.0.0 (pin), @stryker-mutator/vitest-runner@10.0.0, @tailwindcss/postcss@4.3.3, tailwindcss@4.3.3, @testing-library/jest-dom@7.0.1, @testing-library/react@16.3.3, @testing-library/user-event@14.6.7, @types/jest-axe@3.5.9, @types/jsdom@30.0.0, @types/react@19.3.0, @types/react-dom@19.3.0, @types/trusted-types@2.0.7, @typescript/native@7.0.2, typescript@6.0.2 (alias, ветка 6.x), ajv@8.20.0, ajv-formats@3.0.1, autoprefixer@10.6.1, babel-plugin-react-compiler@1.0.0, cross-env@10.1.0, eslint-config-prettier@10.1.8, eslint-plugin-boundaries@7.2.0 (pin), eslint-plugin-i18next@6.1.5, eslint-plugin-jsx-a11y@6.10.2 (peer <=9), eslint-plugin-react@7.37.5 (peer <=9.7), eslint-plugin-react-compiler@19.1.0-rc.2 (только RC), eslint-plugin-react-hooks@7.1.1, fake-indexeddb@6.2.5, fast-check@4.10.2, glob@13.0.6 (pin), istanbul-lib-coverage@3.2.2, istanbul-lib-report@3.0.1, istanbul-reports@3.2.0, jest-axe@11.0.0, msw-auto-mock@0.32.1, openapi-types@12.1.3, rollup-plugin-visualizer@7.1.1, sharp@0.35.5, typed-inject@5.0.0, v8-to-istanbul@9.3.0, vite-plugin-wasm@3.6.0, workbox-build, workbox-cacheable-response, workbox-core, workbox-expiration, workbox-precaching, workbox-routing, workbox-strategies, workbox-window (все 7.4.1), корень: @semantic-release/changelog@7.0.0, @semantic-release/commit-analyzer@13.0.1, @semantic-release/exec@7.1.0, @semantic-release/github@12.0.10, @semantic-release/release-notes-generator@14.1.1, semantic-release@25.0.9.

Рано (новее есть, cooldown ещё не прошёл; дата публикации, дата когда пройдёт cooldown): @opentelemetry/core 2.11.0→2.12.0 (10-06, 10-13); @opentelemetry/sdk-trace-base, sdk-trace-web, resources 2.11.0→2.12.0 (10-06, 10-13); @opentelemetry/exporter-trace-otlp-http, instrumentation-fetch, instrumentation-xml-http-request, instrumentation 0.222→0.223 (10-06, 10-13); @opentelemetry/instrumentation-user-interaction 0.66→0.67 (10-06, 10-13); @sentry/react 10.75.2→10.76.2 (10-08, 10-15) и 11.6.0 (10-08, 10-15); @tanstack/react-query и persist-client 5.103.2→5.104.2 (10-11, 10-18); @tanstack/react-router 1.170.38→1.170.42 (10-10, 10-17); @tanstack/react-start 1.168.57→1.168.61 (10-10, 10-17); @tanstack/react-table 9.2.4→9.2.8 (10-08, 10-15); @tanstack/react-virtual 3.14.13→3.14.15 (10-11, 10-18); @tanstack/router-core 1.171.32→1.171.35 (10-10, 10-17); framer-motion 13.4.1→14.1.0 (10-09, 10-16); i18next 26.4.2→26.4.4 (10-12, 10-19); lucide-react 1.47.0→1.55.0 (10-10, 10-17); maplibre-gl 6.10.0→6.14.0 (10-11, 10-18); marked 18.0.14→18.1.0 (10-05, 10-12 15:40Z); react-hook-form 7.88.0→7.90.0 (10-11, 10-18); react-i18next 17.0.15→17.0.16 (10-06, 10-13); rxdb 17.5.0→17.6.0 (10-05, 10-12 15:19Z); web-vitals 6.2.2→6.2.3 (10-05, 10-12 10:03Z); @babel/core 8.0.6→8.0.7 (10-07, 10-14); @babel/parser 7.29.9→8.0.7 (10-07, 10-14); @playwright/test и playwright 1.63.0→1.64.0 (10-07, 10-14); @types/node 26.6.2→26.6.5 (10-09, 10-16); @vitejs/plugin-react 6.1.1→6.1.2 (10-05, 10-12 10:08Z); axe-core 4.13.0→4.14.0 (10-05, 10-12 17:43Z); idb 7.1.1→8.0.4 (10-06, 10-13); js-yaml 4.3.2→5.4.3 (10-05, 10-12 22:13Z); knip 6.37.0→6.41.0 (10-09, 10-16); msw 2.15.0→3.0.3 (10-10, 10-17); postcss 8.5.28→8.5.29 (10-05, 10-12 09:28Z); prettier 3.9.8→3.9.10 (10-10, 10-17); typescript-eslint 8.70.1→8.71.1 (10-05, 10-12 17:08Z); vite 8.3.0→8.3.4 (10-08, 10-15).

## Не удалось проверить
- braces 3.0.3 (корневой lock, dev, через micromatch 4.0.8): GHSA-vfj7-8cjw-p6xm (CVE-2026-93687), фикса нет, последняя версия 3.0.3 от 2024-05-21. Уже описано в `frontend/scripts/boundary-micromatch-compat/README.md`.
- playwright в `.agents/skills/playwright-skill` (`^1.57.0`): нет lock-файла, фактическая версия не определена.
- eslint-plugin-react-compiler `^19.1.0-rc.2`: стабильного релиза нет (dist-tag latest = RC от 2025-05-14).
- vite-plugin-pwa 2.0.0: официального списка breaking нет (README: только Node >=20.19; migration-страница сайта для v2 не найдена).
- picomatch 4.x: GitHub-релиза для тега 4.0.0 нет, breaking взят из CHANGELOG (ветка master).
- Тело GitHub-релиза пустое (@tanstack/query 5.104.1, @tanstack/router 1.170.41, jsdom 30.1.2, eslint-plugin-security 4.2.0): риск оценён по semver, changelog не прочитан.
- Не применимо: локальные file:-пакеты (wasm-sanitizer, micromatch -> boundary-micromatch-compat, runner-npm-cli-bridge); пакеты без зависимостей (rust-crypto/pkg, wasm-sanitizer/pkg, tools/npm-cli-shim).
- Транзитивные без security-фикса не разбирались (по правилу задачи). Rolldown (через vite, lock 1.2.9): 1.2.12 (2026-09-30) подтянется с vite 8.3.2, 1.2.13 рано до 2026-10-14. OSV уязвимостей не находит.

## Команды (не выполнены)
Frontend (`cd frontend`; `.npmrc` задаёт legacy-peer-deps и min-release-age=7):
1. Patch/minor в диапазонах манифеста: `npm update @sentry/react @tanstack/react-query @tanstack/react-query-persist-client @tanstack/react-router @tanstack/react-start @tanstack/react-table focus-trap framer-motion lucide-react maplibre-gl react-hook-form @chromatic-com/storybook @storybook/addon-a11y @storybook/addon-docs @storybook/addon-onboarding @storybook/addon-vitest @storybook/react-vite storybook eslint-plugin-storybook eslint eslint-plugin-security typescript-eslint vite prettier lint-staged jsdom @types/node`
2. Exact-pin (правка manifest): `npm install -E -D globals@17.13.0 knip@6.39.0`; `npm install -E @tanstack/router-core@1.171.34` (вместе с react-router из п.1).
3. Override `@opentelemetry/core`: в `frontend/package.json` поменять `"@opentelemetry/core": "2.8.0"` на `"2.11.0"`, затем `npm install`.
4. Проверка: `npm run typecheck && npm run lint && npm run lint:knip && npm run test && npm run build`.

Корень репозитория:
5. Security: в корневом `package.json` в `overrides` добавить `"handlebars": "4.7.10"`, затем `npm install --package-lock-only`. До этого нужна запись одобрения и PR без automerge.

Major (отдельные PR, по одному):
6. vitest 5: `npm update @storybook/addon-vitest`, затем `npm install -E -D vitest@5.0.3 @vitest/coverage-v8@5.0.3 @vitest/utils@5.0.3`.
7. msw 3: `npm install -D msw@^3.0.2` (после правок `setupTests.ts:89` и `generated/native.ts`).
8. vite-plugin-pwa 2: `npm install -D vite-plugin-pwa@^2.0.0`.
9. framer-motion 14: `npm install framer-motion@^14.0.0` (после 13.5.1).
10. @sentry/react 11: `npm install @sentry/react@^11.4.0` (после правки `observability.ts`).
11. js-yaml 5: `npm install -D js-yaml@^5.4.2`, плюс переписать override `js-yaml` во frontend и корне.
12. idb 8: `npm install idb@^8.0.3` (перенос в dependencies).
13. @babel/parser 8: `npm install -D @babel/parser@^8.0.6` (нужен Node >=24.11).
14. typescript 7 и picomatch 4: не выполнять, блокеры.
