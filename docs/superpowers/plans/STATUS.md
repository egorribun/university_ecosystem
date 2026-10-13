# Статус MVP v1.0.0

Обновлено: 2026-10-13 (Europe/Istanbul). Единственный действующий план —
[MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), редакция 7; продукт —
[ТЗ MVP](University_Ecosystem_MVP.md), качество —
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Source и CI

- Один checkout, ветка egorribun, существующий
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  База текущего пакета — 976de540; точный head определяется Git и PR.
  PR snapshot 2026-10-13 11:18 UTC: OPEN/BLOCKED, head 976de540,
  100 SUCCESS / 10 FAILURE / 26 SKIPPED; main — ac74e915.
  Пакет 976de540 сохранён обычными commit/push с hooks.
- Действуют 78 обязательных пар context/integration и CodeQL code_scanning.
  Q1/Q4 внедрены; CodeQL blocking, Semgrep в pre-commit.
  До Q3 текущие coverage floors и 100% patch coverage сохраняются.
- Hosted CI 976de540 выявил frontend fixtures/i18n, backend seed fixture,
  утечку offline Alembic shim, CSP shadow mismatch, browser Trusted Types
  и NATS startup в advisory Core. Aggregate failures учитывают эти же сбои.
  Локальные PASS ниже не заменяют published-source CI нового head:
  нужны свежие результаты всех 78 contexts и CodeQL.
- В объём входят [October audit](../../audits/AUDIT-2026-10.md) и
  [dependency report](../../audits/dependency-updates-2026-10/README.md).
  Исторические OPEN и версии в исходных отчётах требуют текущей классификации.

## Текущая контрольная точка

- Текущий пакет исправляет frontend providers/loader stubs, конечный i18n
  registry и loading key: 30 целевых tests, i18n и TypeScript PASS.
  Offline Alembic shims ограничены try/finally: 3 regression tests PASS.
  На PG17 AUD197/198 → AUD226 в одном процессе: 7 PASS, owned cleanup — 0.
  Seed double согласован с insert-time UUID defaults: 14 tests PASS.
  CSP shadow сохраняет enforcement/Trusted Types и убирает только неприменимый
  upgrade directive; custom/configured report-uri не дублируются: 44 tests и Ruff PASS.
  Frontend CSP/static bootstrap: 68 tests, TypeScript, ESLint и production build
  с canonical WASM PASS. После реального entrypoint/createRoot сохраняются
  dark/en, nonce и ровно один theme-init script; SSR hydration не менялась.
  Эти исправления пока не опубликованы; реальные browser checks pending.
- Ambiguous COMMIT: cleanup проверяет ссылки Attachment на primary после
  rollback; ошибки rollback/cleanup сохраняют исходную ошибку. Pending lease
  того же владельца продлевается на 300 секунд; durable DB idempotency не
  заявляется. RED: пять regressions; GREEN: 97 chat tests, Ruff PASS;
  все 42 изменённые исполняемые строки выполнены. Частичная file coverage
  диагностическая и не заменяет обязательный aggregate.
- Profile media: сначала durable COMMIT, затем удаление только unreferenced
  owner-scoped файла; rollback/query uncertainty сохраняет объект и исходную ошибку.
  RED: 27 regressions; GREEN: 126 tests, Ruff, 100% file line/branch coverage.
  Primary-session и shared-reference checks проверены; свежий Core ещё pending.
- Предыдущие пакеты сохраняют ownership/retention news media, durable outbox,
  campus timezone, advisory schedule locks, trusted proxy/IP, ограниченный
  Gateway egress, MFA/session guards, WS membership/replay epochs, recipient
  isolation уведомлений и SSR nonce/no-store. Нужна свежая Core-приёмка.
- Generated OpenAPI/client/MSW синхронизированы штатными генераторами с
  GET /api/v1/campus/config; пять файлов совпадают с generated CI output.
  Live contracts: 179 PASS; TypeScript PASS.
  Backend OpenAPI snapshot также синхронизирован; три shard-3 failures
  воспроизведены на Helm 3.22.0. После исправления диагностических assertions
  и snapshot: 40 OpenAPI/proxy contracts PASS, Ruff PASS. Ещё 266 затронутых
  Helm contracts отдельно проверены на 3.22.0: PASS.
- Strict DB gate использует planner-only EXPLAIN: не исполняет logged DML/CTE,
  сохраняет cost/scan checks и fail-closed поведение. Это не runtime benchmark.
  RED воспроизведён; combined live-stand/DB/S3 suite: 1827 PASS, Ruff PASS.
  Необязательный count-only log, вызвавший CodeQL alert 3505, удалён;
  dismissal не применялся, свежий CodeQL pending.
- News-media DDL выделен в общий emitter для online migration и Squawk.
  Offline/PG/schema guards сохранены; 17 contract tests PASS.
  На реальном PostgreSQL 17: 12 ownership/migration integration PASS;
  отдельный полный migration cycle до head PASS. Контейнеры удалены.
  Actual hosted Squawk для нового source ещё pending.
- Backend fixtures: 328 PASS; отдельно исправленные Helm CIDR assertions —
  8 PASS, S3 parametrization в двух xdist workers — 6 PASS.
  Обновлены проверенные activation/workflow fingerprints, сохранены provenance
  guards. Source inventory/anti-pattern validation PASS.
- SSR сохраняет Request до abort при timeout; forced-GC RED и 15 Node checks PASS.
  Worker/CSP/bootstrap проверены текущим пакетом выше; реальные browser checks pending.
  Бюджет предыдущего published пакета: main JS 168,06 KiB, initial JS gzip 373,83 KiB,
  initial CSS gzip 38,58 KiB. Реальные browser console/hydration/Worker checks
  остаются pending до свежего Core.
- Go fixes для Nilaway, file-processor Close и Gateway keyFunc интегрированы
  после review. Linux race, exact 100% block/statement coverage, lint и Nilaway
  PASS для всех трёх сервисов; WS stress: 20 repetitions PASS.
  FP contextcheck fix проверен повторными race/coverage/lint. FP/Gateway Nilaway
  прошли последовательный полный analysis в 6 GiB cgroup после OOM в 4 GiB;
  область анализа не менялась. Owned containers/processes после прогонов — 0.
- Политика detect-secrets: 118 owner-approved exact dispositions, baseline319.
  Сохранены 113; отдельно Caddy1 и четыре Fakeredis/NATS/imgproxy до 2027-01-10.
  Private validator: 103 PASS; canonical validator: 102 PASS.
  Последний published scan113: 387 findings/0 unreviewed; новый full scan pending.
  Новых inline allowlist pragmas нет; новые подавления без решения запрещены.
- Ammonia 4.2.3 имеет точное owner cooldown exception в двух Cargo.lock.
  Linux Rust 1.97.1 / wasm-pack 0.13.1 / wasm-opt 117 build и 3 runtime smoke PASS.
  Две дополнительные чистые Linux build совпали с первой по всем 12 package
  outputs; provenance и 3 runtime smoke PASS. Два бинарника и metadata приняты;
  свежий hosted parity для нового published source ещё pending.
- NATS 2.12.15 проверен на реальном брокере; Node 24.21.0, Helm 3.22.0,
  Kyverno 1.19.1, Nuclei 3.11.1, Prometheus 3.15.0 и flagd 0.16.3 опубликованы.
  Новый literal-safe renderer проверен с полным production entrypoint и
  JetStream template: startup/auth PASS для обычных и сложных синтетических
  credentials; source contracts PASS. Причина прежнего hosted Core failure
  не установлена; нужен новый CI/Core. После прогонов owned resources — 0.
  Caddy source — 2.11.4; cooldown 2.11.7 истёк. Official metadata/pins
  перепроверены; private 2.11.7 custom-plugin build, version/module и обе
  конфигурации PASS на Buildx 0.37.2. Owned builder удалён; проверенный image
  сохранён для приёмки. Отдельная Caddy digest disposition уже включена
  в политику118; dependency candidate пока не интегрирован.
  реальные маршруты/JWKS/WS требуют свежего Core.
  Test/sandbox Redis 7.4.2: проверен candidate 7.4.11 (CVE floor 7.4.6).
  Imgproxy: четыре применимых advisory исправлены в candidate 4.0.17;
  cooldown и static compatibility проверены, runtime и интеграция pending.
  SeaweedFS: TUS не опубликован; upstream metadata/source discrepancy сохраняется.
- AUD-226: Alembic включён в coverage/provenance; нужен штатный aggregate
  четырёх backend shards и PG migration artifact нового source.
  Частичная диагностическая coverage не проходит действующие floors.
  Developer harness --repo-only: 28/28 PASS в предыдущем пакете.

## Ближайшие шаги

Работа возобновлена владельцем; root готовит обычный commit/push.
Source на базе976de540; точное staged/unstaged состояние задаёт Git.
Владелец утвердил ещё четыре FP: с отдельной Caddy записью policy118; baseline319.
Profile-media RED/GREEN закрыт локально; imgproxy runtime и свежий CI pending.

1. Закрыть текущие CI/browser/startup failures, проверить auth/data finding,
   сохранить исправления обычным commit/push; Caddy — отдельным dependency
   commit. Получить свежие 78 contexts и CodeQL нового head.
2. На чистом опубликованном source поднять один новый Core (23 сервиса).
   Два полных прогона 59 live specs desktop/mobile с одним worker, seed и
   stop/start; persistence сравнить до повторного seed. Старый Core остановлен,
   данные сохранены.
3. News/Events/Schedule: 36 captures RU/EN, light/dark, 390/768/1440;
   360/1024 risk/a11y/reduced motion, main JS <500 KB; Lighthouse: семь routes,
   по три измерения. Утверждён только Home12 ddbbc84d.
4. Один paired DB/S3 restore в изолированную цель с чтением объекта по restored
   DB reference; final-source security/data review, revalidation 63 ledger IDs
   и закрытие оставшихся audit/dependency findings.
5. Frozen RC, full smoke, ordinary merge, resulting-main checks,
   producer ровно шести образов, tag/release v1.0.0.

## Ресурсы и сохранность

Root управляет Git/интеграцией; три GPT-6 Luna Max ведут private tasks/review.
Core data и приватные candidates сохранены; тяжёлые проверки последовательны.
Owned Docker-ресурсы очищаются после прогонов; чужие ресурсы сохраняются.
RAM admission ≤75% / free ≥8 GiB, runtime stop ≥85% / <4 GiB.
Исключение только для serial Linux screenshots: admission ≤80% / ≥6 GiB,
browser ≤1 GiB / 2 CPU. Удалять только доказанно owned ресурсы; Core data,
чужие env/тома/backups, migration/Git history и приватный rescue bundle сохраняются.
Q2/Q3, global mutation, kind certification, три comparable CI и RPO/RTO — v1.1.
