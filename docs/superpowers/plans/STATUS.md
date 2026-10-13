# Статус MVP v1.0.0

Обновлено: 2026-10-13 (Europe/Istanbul). Единственный действующий план —
[MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), редакция 7; продукт —
[ТЗ MVP](University_Ecosystem_MVP.md), качество —
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Git, опубликованный source и CI

- Один checkout, ветка egorribun, существующий
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Отправная точка локального пакета и CI-снимка ниже: 627337a9cb196c2c5f02a37c79e734a20844c452.
  Origin/main: ac74e915ae539f098f0fa1e7c83b355703069984.
  Read-only fetch 2026-10-13 02:34 UTC подтвердил прежние remote refs;
  PR snapshot остаётся OPEN/BLOCKED.
  Основной пакет сохранён обычным commit c5384ce7; следующий пакет ещё локальный.
  Локальные PASS ниже требуют отдельного published-source CI после публикации.
- Действуют 78 обязательных пар context/integration и CodeQL code_scanning.
  Q1/Q4 внедрены; CodeQL blocking, Semgrep в pre-commit.
  Coverage floors и 100% patch coverage сохранены; Q3 не внедрён.
- Strict78 snapshot опубликованного 627337 повторно сверён 2026-10-13 в 00:07:
  53 SUCCESS / 15 FAILURE / 1 SKIPPED / 9 ABSENT — без изменения к снимку
  2026-10-12 21:04 UTC. Сохранённый защищённый receipt и его SHA-256 ниже
  относятся к прежнему снимку; новый receipt здесь не заявляется:
  ci78-627337-current-1791839062030.json,
  461EDBD8FFC5F773AE8D0C21C7A36962D3CD59FFAD091C1898D283728C7DCE03.
  Локальные исправления не меняют опубликованный source; требуются новый SHA и CI.
- В объём входят [October audit](../../audits/AUDIT-2026-10.md) и
  [dependency report](../../audits/dependency-updates-2026-10/README.md).
  Их исходные OPEN/версии не являются текущей классификацией всех находок.

## Проверенный локальный пакет и границы доказательств

- Сохранены исправления AUD-005/008, 025/026/028, 164/167, 165, 166/458,
  168/169, 170/171/172, 173/174; durable outbox для news/events/comments,
  trusted proxy/IP, ownership загрузок и безопасное сохранение legacy media.
  Нужна свежая Core-приёмка; старый live smoke её не заменяет.
- Campus timezone и семантика времени событий интегрированы:
  250 frontend tests в 18 файлах и 163 Python tests прошли.
  Gateway разрешает анонимный GET только точного /api/v1/campus/config;
  Linux Go 1.26.9: шесть packages с race, exact 100% coverage и lint без issues.
  Соседние пути, неподдерживаемые методы и malformed JWT сохраняют защиту.
- Backend GraphQL исключён из публичного MVP surface; внутренние resolvers
  и file-processor GraphQL сохранены. Ограниченный Gateway egress интегрирован.
  Совместная проверка GraphQL/Helm: 578 Python PASS; internal resolvers: 4 PASS.
  NetworkPolicy render не доказывает реальное CNI enforcement.
- News media ownership/retention: реальный PostgreSQL 17 дал 12 PASS и отдельный
  upgrade-to-head PASS. Чужие и недоказанно принадлежащие файлы сохраняются;
  повторное использование, claim и rollback проверены.
  AUD-181 comments используют существующие sanitizer/trim/limit 1000;
  missing news сохраняет 404, пустой результат — 400, overlong — 422 без input.
  RED: четыре поведенческих FAIL и один сохранённый 404 PASS; GREEN после
  исправления ownership fixture: весь news-набор 93 PASS, Ruff/format PASS.
  Строгий mypy для всех 347 backend source files прошёл в 23:56.
- Миграции: исторические данные/UUID/PK/FK/routing проверены на PG17;
  outbox: 4 integration PASS; tenant preservation AUD-230: 10 PASS,
  включая реальный alembic check. ADR-036 rollback barrier сохраняется.
  Эти проверки не сертифицируют production downgrade или lock budgets.
- AUD-228: PostgreSQL transaction advisory lock сериализует create/update/seed;
  conflict reads обходят кеш/лимит, PATCH перечитывает строку после ожидания.
  Реальный RED воспроизвёл два успешных конфликтных create/update; GREEN:
  7 PG17 PASS, включая partial PATCH, >500 rows, commit/rollback и seed/API lock.
  SQLite suite после точечного datetime fixture fix: 187 PASS.
- AUD-231: native SSR nonce/no-store интегрированы. Production build,
  concurrent SSR probe с caps 2048 MiB RSS / 1536 MiB heap, Node SSR,
  TypeScript и ESLint прошли. Новая браузерная приёмка ещё требуется.
- WS AUD-462/463: membership/replay epoch, derived context, bounded drain и
  Stop join/admission интегрированы. Владение write/session locks локализовано
  в одном helper без передачи удерживаемых блокировок вызывающему коду.
  Повторная локальная проверка Linux Go 1.26.9 в 01:01 UTC: четыре race
  packages PASS, lint 0 issues, exact coverage 100% без zero blocks;
  cancellation/revocation regressions прошли 20 повторов.
  Stop gauge fixture учитывает завершённый limiter GC; bounded join сохранён.
  Это ограниченное локальное evidence: published-source CI и product live-сценарии
  остаются pending.
- AUD-460: server/SW/bus/native preview связывают доставку с доверенным получателем;
  публичные topic-only рассылки сохранены. Независимый review пройден;
  финальный frontend-набор: 140 PASS, TypeScript/ESLint PASS.
  Backend notification/auth: 114 PASS; Ruff/format и полный app mypy PASS.
- Auth/session finding о sibling tombstones отозван: проверка фактического DI
  показала, что UoW связывает ActiveSessionRepository; он фиксирует MFA sibling
  revocations до commit смены пароля. Восемь failure-path cases прошли на
  неизменённом auth_service.py; production auth fix не требуется. Gateway v1.2
  прошёл Linux race во всех шести пакетах, lint 0 и exact coverage 100% в 00:28;
  kid primary/custom принимаются только в конечном окне PEM bootstrap LKG.
- Stale CI contracts/fixtures (events/user cleanup/resource ownership): 54 Python и Ruff PASS.
- Secret mechanism интегрирован: 166 Python PASS и Ruff PASS; 34 literal
  findings заменены генерацией синтетических тестовых данных.
  Владелец утвердил ровно 85 exact dispositions, затем отдельно один публичный
  NATS digest: активны 86 finite path/type/digest entries. Прежние 85 сохранены;
  baseline содержит прежние 319 identities, required contexts — 78.
  Полный scan staged source: 384 findings, из них 299 совпадают с baseline,
  85 — с approved dispositions; unreviewed — 0. Исторические baseline identities
  (319) и approved entries (86) сохранены: 20 и 1 соответственно больше не
  обнаруживаются в текущем source. Hosted proof остаётся pending.
  Дополнительные синтетические literals в ASan/TSan и трёх тестах заменены
  генерацией; backup/seed/CI contracts: 381 PASS, historical migrations на
  PostgreSQL 17: 6 PASS. Scanner policy и approved identities не расширены.
  Gitleaks rules, запрет новых inline pragmas и baseline identities сохранены.
  Overlay wrapper: два RED воспроизвели повторный отказ и stale self-filter;
  GREEN: 132 tests и Ruff/format PASS. Временные строки approved findings больше
  не меняют canonical baseline; реальные updates сохраняют status 3, concurrent
  external edit останавливает hook. Штатный pre-commit PASS: baseline и index
  неизменны при повторном запуске; обычный commit PASS, push/hosted proof pending.
- AUD-224: hook guard интегрирован; RED подтверждён, GREEN 78 tests / Ruff / harness 28/28 PASS.
  AUD-225: три RED, strict EXPLAIN GREEN 44 tests / Ruff PASS; optional mode сохранён.
- AUD-226: Alembic включён в coverage/provenance; TESTING/CONTRIBUTING отражают
  штатный aggregate четырёх backend shards и PG migration artifact.
  Диагностическая выборка дала 59,53% statements / 29,98% branches:
  это частичное покрытие, действующий 100% floor не пройден и не снижен.
  Нужен current-source aggregate в штатной lane.
- urllib3/Werkzeug lock синхронизирован. Ammonia 4.2.3 в двух Cargo.lock имеет
  точное owner cooldown exception; Rust 1.97.1 rebuild, ensure-wasm/provenance
  и три Node WASM smoke PASS; Linux parity pending.
  NATS 2.12.15: 7 ws-hub, 6 file-processor и Python DLQ PASS на реальном брокере;
  лимиты 1 GiB / 2 CPU и очистка проверены; Core pending.
  Node 24.21.0, Helm 3.22.0, Kyverno 1.19.1, Nuclei 3.11.1, Prometheus 3.15.0
  и flagd 0.16.3 интегрированы локально; published-source checks pending.
  Caddy source — 2.11.4; 2.11.7 допускается с 2026-10-13 05:52:45 UTC.
  Остальной dependency report остаётся на перепроверке.
- Developer harness --repo-only: 28/28 PASS. Это не product/release certification.

## Следующие контрольные точки

1. Опубликовать проверенный локальный пакет обычным commit/push в том же PR.
   Полный final-source secret scan, ссылки и обычные hooks; повторно stage
   .secrets.baseline, commit/push в тот же PR. Получить свежие 78 results и CodeQL.
2. На чистом опубликованном source поднять один новый Core (23 сервиса), затем два
   последовательных полных прогона: 59 live specs, desktop/mobile, один worker;
   seed и stop/start. Старый Core 8295b807 остановлен; данные сохраняются.
3. News/Events/Schedule: 36 captures RU/EN, light/dark, 390/768/1440;
   360/1024 risk/a11y/reduced motion, main JS <500 KB; Lighthouse: home/login/news/
   events/profile/settings/fixture messenger, по три измерения (21).
   Утверждён только Home12 ddbbc84d; следующие pixels/baselines pending.
4. Один paired DB/S3 restore в изолированную цель с чтением объекта по restored
   DB reference; final-source SEC-07/RUST-P3-03, auth/session/data review,
   revalidation 63 ledger IDs и оставшиеся audit/dependency findings.
5. Frozen RC, full smoke, ordinary merge, свежие resulting-main checks,
   producer ровно шести образов, tag/release v1.0.0.

## Ресурсы и сохранность

Root управляет Git/интеграцией; максимум три GPT-6 Luna Max работают в раздельных
private candidates. Тяжёлые проверки root запускает последовательно.
RAM admission ≤75% / free ≥8 GiB, runtime stop ≥85% / <4 GiB.
Исключение только для serial Linux screenshots: admission ≤80% / ≥6 GiB,
browser ≤1 GiB / 2 CPU. Нужный owned Linux Go cache сохраняется до проверок.
Удалять только доказанно owned ресурсы; Core data, чужие env/тома/backups,
migration/Git history и приватный rescue bundle сохраняются.
Q2/Q3, global mutation, kind certification, три comparable CI и RPO/RTO — v1.1.
