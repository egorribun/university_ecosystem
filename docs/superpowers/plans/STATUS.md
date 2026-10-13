# Статус MVP v1.0.0

Обновлено: 2026-10-13 (Europe/Istanbul). Единственный действующий план —
[MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), редакция 7; продукт —
[ТЗ MVP](University_Ecosystem_MVP.md), качество —
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Source и CI

- Один checkout, ветка egorribun, существующий
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  База текущего пакета — cd8daacb; точный head определяется Git и PR.
  PR snapshot до сохранения пакета, 2026-10-13 09:33 UTC: OPEN/BLOCKED,
  head cd8daacb; последний проверенный main — ac74e915.
  Пакеты c5384ce7 и cd8daacb сохранены обычными commit/push с hooks.
- Действуют 78 обязательных пар context/integration и CodeQL code_scanning.
  Q1/Q4 внедрены; CodeQL blocking, Semgrep в pre-commit.
  До Q3 текущие coverage floors и 100% patch coverage сохраняются.
- Hosted CI опубликованного cd8daacb выявил ошибки generated OpenAPI, WASM
  parity, Squawk, fixtures backend shards, Go lint/Nilaway, secret integrity,
  SSR/CSP и strict DB EXPLAIN. Локальные PASS текущего пакета ниже не являются
  результатами published-source CI. Для нового head после обычного commit/push
  нужны свежие результаты всех 78 contexts и CodeQL.
- В объём входят [October audit](../../audits/AUDIT-2026-10.md) и
  [dependency report](../../audits/dependency-updates-2026-10/README.md).
  Исторические OPEN и версии в исходных отчётах требуют текущей классификации.

## Текущая контрольная точка

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
- SSR сохраняет Request до abort при timeout; RED под forced GC воспроизведён,
  GREEN: 15 Node SSR checks. Worker asset проходит существующую Trusted Types
  policy; report-only CSP исключает только неприменимый upgrade directive.
  Worker/Trusted Types: 33 PASS; TypeScript и ESLint PASS.
  Production build PASS; emitted crypto Worker asset присутствует.
  Bundle budget PASS: main JS 168,06 KiB, initial JS gzip 373,83 KiB,
  initial CSS gzip 38,58 KiB. Реальные browser console/hydration/Worker checks
  остаются pending до свежего Core.
- Go fixes для Nilaway, file-processor Close и Gateway keyFunc интегрированы
  после review. Linux race, exact 100% block/statement coverage, lint и Nilaway
  PASS для всех трёх сервисов; WS stress: 20 repetitions PASS.
  FP contextcheck fix проверен повторными race/coverage/lint. FP/Gateway Nilaway
  прошли последовательный полный analysis в 6 GiB cgroup после OOM в 4 GiB;
  область анализа не менялась. Owned containers/processes после прогонов — 0.
- Политика detect-secrets: 113 owner-approved exact dispositions; прежние
  86 записей и 319 baseline identities сохранены. Владелец 2026-10-13 разрешил
  ровно 27 дополнительных записей до 2027-01-10. Финальная проверка:
  132 tests PASS; полный tracked scan — 387 findings, 0 unreviewed,
  25 approved entries сейчас отсутствуют. Source stability PASS.
  Новых inline allowlist pragmas нет; новые подавления без решения запрещены.
- Ammonia 4.2.3 имеет точное owner cooldown exception в двух Cargo.lock.
  Linux Rust 1.97.1 / wasm-pack 0.13.1 / wasm-opt 117 build и 3 runtime smoke PASS.
  Две дополнительные чистые Linux build совпали с первой по всем 12 package
  outputs; provenance и 3 runtime smoke PASS. Два бинарника и metadata приняты;
  свежий hosted parity для нового published source ещё pending.
- NATS 2.12.15 проверен на реальном брокере; Node 24.21.0, Helm 3.22.0,
  Kyverno 1.19.1, Nuclei 3.11.1, Prometheus 3.15.0 и flagd 0.16.3 опубликованы.
  Caddy source — 2.11.4; cooldown 2.11.7 истёк. Official metadata/pins
  перепроверены; custom-plugin build/config proof pending, обновление не принято.
  Private v5 phase helper: 3/3 fake-process regressions PASS. Перед повтором
  runner нужно переименовать четыре bare docker и два bare tag metadata refs,
  а cleanup inventory дедуплицировать только по идентичным JSON-строкам.
  Доказанно owned builder неудачного прогона удалён; Core не запускался.
- AUD-226: Alembic включён в coverage/provenance; нужен штатный aggregate
  четырёх backend shards и PG migration artifact нового source.
  Частичная диагностическая coverage не проходит действующие floors.
  Developer harness --repo-only: 28/28 PASS в предыдущем пакете.

## Ближайшие шаги

Пауза запрошена владельцем после сохранения текущего пакета. Новый Core,
Caddy build и наблюдение за следующим CI продолжать только после возобновления.

1. Проверить свежие 78 contexts и CodeQL нового head, затем завершить
   custom Caddy build/config и обычный отдельный dependency commit.
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

Root управляет Git/интеграцией; максимум три GPT-6 Luna Max работают в раздельных
private candidates. На контрольной точке все субагенты завершили задания.
Тяжёлые проверки выполняются последовательно.
RAM admission ≤75% / free ≥8 GiB, runtime stop ≥85% / <4 GiB.
Исключение только для serial Linux screenshots: admission ≤80% / ≥6 GiB,
browser ≤1 GiB / 2 CPU. Удалять только доказанно owned ресурсы; Core data,
чужие env/тома/backups, migration/Git history и приватный rescue bundle сохраняются.
Q2/Q3, global mutation, kind certification, три comparable CI и RPO/RTO — v1.1.
