# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-15 UTC. Действующий порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Пауза и следующий приоритет

Работа приостановлена по поручению владельца на сохранённой контрольной точке. Начинать только после его явного сигнала. Следующий приоритет — полное закрытие октябрьского аудита: P1, P2, P3 и наблюдений ниже P3, включая ранее отложенные audit-пункты. Перепроверять каждую находку на текущем source; сохранять regression/runtime evidence либо обоснованный disposition для дубля, уже исправленного или неприменимого пункта. Приёмку и выпуск MVP продолжить после этого приоритета.

## Закрытие зависимостей (ограниченный checkpoint, 2026-10-15)

- Release-age cutoff 2026-10-07T12:16:13Z and version-selection/maturity freeze 2026-10-14T12:16:13Z remain unchanged; validation receipts retain their own dates. [Summary and holds](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15).
- npm union: 1,833 exact identities, 0 gaps / 0 findings; Python OSV: 228/228, 0; pip-audit: 224 installed distributions, 0; Rust OSV: 208/208, 0.
- HISTORICAL retained contract checkpoint: 2,341 PASS and one POSIX-only skip on the prior source; strict mypy: 347 files, 0 issues. The dependency compare guard now retries only transient HTTP 429/502/503/504 and explicit request-opening connection/timeouts; auth, schema, and identity failures remain fail-closed. Current focused license, startup, and Helm-staging checks pass; CI catalog validation passed for 59 workflows / 183 jobs; Ruff and pinned Hadolint 2.15.1 passed for all nine current Dockerfiles.
- Previously reviewed frontend source: 741 files / 8,965 PASS; production build, bundle, Storybook, and SSR health/login/missing-route 200/200/404 PASS. Broader browser acceptance remains in the paused MVP plan. Current-source post-source stages, client-prod, architecture, typecheck, ESLint, and bundle evidence remain source-bound in the [audit evidence](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15).
- Chart v3 semantic checks PASS: Redis chart pins 7.4.11 and NATS 2.15.0; rollout still requires a configured ExternalSecret and `store_dir`. Four actual service smokes PASS; Pyroscope retains its normal 15-second wait.
- Goldmark 1.8.6: affected Linux Go 1.26.9 race checks PASS, coverage 100%, lint 0; current-source Goldmark/JWKS rechecks PASS; govulncheck reachable/imported findings 0. GO-2026-5932 remains module-only with fixed version N/A; openpgp is not imported or called.
- Complete-source raw scan at this checkpoint: PASS, 4,384 files / 465 findings, with 0 unmatched against the exact 225-record overlay. The approved scope remains 225; `.secrets.baseline` remains byte-identical at 319 identities, with 78 required contexts unchanged. Ordinary hooks for [source commit ba59279c](https://github.com/egorribun/university_ecosystem/commit/ba59279c), including owner-225 detect-secrets, and pre-push TypeScript passed on source stable / owned=0; CodeQL #3514–#3517 owner-approved dismissal readback passed, and CodeQL remains blocking.
- Direct RustSec: seven lock graphs PASS, 0 advisories, exit 0; database HEAD unchanged. Backend build/OCI, Trivy 0.75.0, and runtime evidence for [source commit ba59279c](https://github.com/egorribun/university_ecosystem/commit/ba59279c) are detailed in the audit; later numeric `USER` updates require current-source image evidence. Local POSIX Redis AOF/RDB UID migration and disposable cleanup PASS; live PVC/CSI and protected backup/restore remain future rollout prerequisites. Three local Helm profiles passed strict lint/render, without hosted Checkov coverage. Required hosted checks remain a release prerequisite; [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306) is live current-head authority. SeaweedFS 4.48 / GHSA-99q7-x53r-6j4g remains OPEN; six compatibility holds and only the Ammonia 4.2.3 / Rclone 1.75.2 exceptions remain. The full MVP/platform audit remains paused; release readiness is not declared. Detailed proof is in the [audit supplement](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15).

## Источник и hosted CI

- Текущую dependency-source identity и hosted-check authority определяют Git и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Required hosted checks are a release prerequisite; use the current-head check list on that PR for live status. Local receipts do not replace hosted/final-source gates.

### HISTORICAL retained MVP checkpoint (not current dependency CI)

- HISTORICAL: source сохранённой контрольной точки — 99f8ddbe, tree 3bce78ea; это не текущая dependency-source identity.
- HISTORICAL hosted run [38548905717](https://github.com/egorribun/university_ecosystem/actions/runs/38548905717) завершился FAIL. Все четыре backend unit shards, backend aggregate, integration shard 0, migrations, frontend shards/full unit suite, lint/build, WASM и CodeQL прошли. Integration shards 1–3 пропущены конфигурацией matrix.
- HISTORICAL merge preview 8de6200e имеет тот же tree и родителей ac74e915 и 99f8ddbe. Coverage artifact связан с этим run/preview. Frontend global coverage: lines 99.939%, statements 99.856%, functions 99.936%, branches 99.562% при требовании 100%; не покрыты 11 lines, 29 statements, 3 functions и 64 branch arms в 18 файлах. Coverage normalization и CI Success — FAIL; следующий quality/Tier 0 validator пропущен, его PASS нет.
- HISTORICAL backend shard span — 37:48 при max-parallel=2, самый длинный shard — 19:27. Это не critical path всего workflow; цель 15 минут не достигнута.
- Сохраняются 78 required contexts, blocking CodeQL и Semgrep в pre-commit. Результаты этого historical source не переносятся на следующий SHA.

## HISTORICAL retained MVP checkpoint: подробности

- Обычные hooks и tracked-secrets scan прошли перед commit/push `99f8ddbe`. Clock adapter исправляет перевод Playwright deadline между процессами; MFA challenge сохраняет канонический Retry-After. Локально: 1678 parser tests, 217 live contracts, 22 session-cleanup tests; после regex narrowing — ещё 21 helper contract и полный TypeScript. Backend: 249 выбранных тестов PASS, изменённый MFA challenge — 100% statements/lines/branches.
- Свежий Core `run-d8b50263-c6e9-494d-a55f-e653e657f235` собран и поднят на `99f8ddbe`. Native CSP/Worker — 20 PASS; Enter — 1 native POST, query/canary в URL — 0, cleanup PASS. Это не доказывает отсутствие ошибок на authenticated Map/Schedule.
- Focused8: 28 PASS / 6 FAIL / 6 утверждённых skips. Это диагностика, а не приёмка. Три Map failures и desktop Schedule дают одинаковый EvalError: emitted `vendor-rxdb-CfXP_ufI.js:28:26053` соответствует Ajv `new Function` при RxDB validation в общем `useScheduleData`. CSP и validation не ослаблены.
- News: desktop RU/360 heading оказался выше viewport при scrollY=189; mobile прошёл все 10 language/width tuples. Источник вертикального смещения пока не установлен.
- Mobile MFA: финальный enabled-login вернул 429, Retry-After не принят строгим диапазоном 1–60. Совместные desktop/mobile flows запрашивают шесть кодов при общем IP-лимите 5/600 s; это ведущая гипотеза, но фактический header class и bucket ещё не подтверждены. Лимиты, deadline/reserve и assertions сохранены.
- Native mouse click дал 0 POST и TimeoutError: до клика hit target — active boot loader, после failed click — submit control при active state. CSS failsafe может оставить state active после снятия pointer interception. Причина полного тайм-аута не доказана; Enter security proof не заменяет mouse UX acceptance.
- RxDB/Z-Schema candidate сохранён приватно как непроверенный WIP: `rxdb-zschema-csp-private-v1-20261014`. Он не применён, не прошёл RED/GREEN, schema parity, build или browser acceptance. Native click classifier V3.1 сохранён отдельно; News staged diagnostic остаётся предложением.

## Сохранность и ресурсы

- Core остановлен штатным owner-checked `stop`: все 23 container IDs и 6 volumes сохранены, работающих контейнеров этого Core — 0. Core C1, C21, 532 и failed Core 81, их state/backups и volumes сохранены.
- Для устранения исчерпания Docker subnet pool удалены только 23 проверенных остановленных контейнера и 3 сети устаревшего source `7167b218`. Все его 6 volumes и state bytes, остальные container/network IDs и все volume identities сохранены. Global prune не применялся.
- Три точно идентифицированных старых процесса этой работы завершены по PID/birth/command hash: superseded validation shell/child и зацикленная одноразовая проверка пути. Runtime guards завершились без оставшихся recorded owned processes. Субагенты завершили checkpoint; новая работа не назначена.
- Действуют 225 owner-approved exact secret dispositions: прежние 135 без изменений плюс ровно 90 additions, одобренных 2026-10-15; baseline — 319 identities. Finite131 unchanged: только неизменённые migration blobs из base `ac74e915` до 2026-11-13; touched/new/unmatched migrations и весь прочий Tier 0 сохраняют 100%. Новых migration exceptions нет.
- Admission RAM ≤75% / free ≥8 GiB, stop ≥85% / free <4 GiB. Linux screenshots: утверждённое ограниченное исключение ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse — 75% / 8 GiB, cap 2 GiB / 2 CPU. Чужие процессы, env, volumes, Git history и private rescue bundle сохраняются.

## Приёмка MVP после аудита

Закрыть текущие quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security/audit review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`; новой визуальной приёмки не было.
