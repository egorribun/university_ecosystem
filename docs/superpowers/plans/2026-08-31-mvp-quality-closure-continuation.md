# University Ecosystem MVP Quality Closure Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** продолжить работу на ветке `egorribun` от исторической контрольной точки `e0989e29cfca88ee9a650eb264d6fa7674031c9a`, сохранить уже реализованные основные вертикали MVP, закрыть подтверждённые инфраструктурные и mutation-дефекты текущего PR, получить полный current-SHA набор quality/mutation/security evidence и довести тот же immutable build через Docker и production-like staging до доказуемо готового к релизу состояния. Исторические SHA/run из baseline ниже не являются текущей сертификацией; authoritative overlay находится в §32.

**Architecture:** репозиторий рассматривается как единая fail-closed система качества. Каждая технологическая область формирует нативные отчёты, а SHA-bound агрегатор принимает только полные, свежие и хешированные артефакты одного workflow run/attempt, отдельно фиксируя source head SHA и tested merge SHA. Уже реализованные продуктовые вертикали проходят evidence-first gap-аудит и меняются только при воспроизведённом дефекте; CI закрывается root-cause группами через RED → GREEN → REFACTOR и оптимизируется по измеренному критическому пути при лимите 20 одновременно исполняемых jobs без ослабления coverage, mutation, security или browser matrix.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, Dishka, PostgreSQL, Redis/Valkey, NATS, transactional outbox, pytest/coverage.py/mutmut; React 19, TypeScript 7, TanStack Router/Query, Zustand, Valibot, Vite 8/Rolldown, Vitest/Stryker, Playwright, Storybook, Lighthouse; Go 1.26 modules, race detector, golangci-lint; Rust, cargo-llvm-cov, WASM, PyO3; Docker Compose, Caddy, Helm/Kubernetes, Kyverno, ExternalSecrets, Prometheus/Grafana/Tempo/Loki; GitHub Actions, CodeQL, Semgrep, Bandit, detect-secrets, gitleaks, Trivy, SBOM и provenance.

**Historical audit refresh:** `2026-08-31T13:37:11+03:00`; live PR `#1257`, source head `e0989e29cfca88ee9a650eb264d6fa7674031c9a`, matrix run `33349026009`. Это superseded baseline, сохранённый для причинного и regression-аудита. Текущий identity/status snapshot находится в §32 и должен обновляться через paginated GitHub Jobs API перед каждым утверждением о закрытии.

**Spec:** [`AGENTS.md`](../../../AGENTS.md), [`app/AGENTS.md`](../../../app/AGENTS.md), [`frontend/AGENTS.md`](../../../frontend/AGENTS.md), [`services/AGENTS.md`](../../../services/AGENTS.md), [`quality/quality-contract.json`](../../../quality/quality-contract.json), [`University_Ecosystem_MVP.md`](University_Ecosystem_MVP.md), [`2026-08-25-quality-closure-foundation.md`](2026-08-25-quality-closure-foundation.md), [`prompt.md`](prompt.md), PR [#1257](https://github.com/egorribun/university_ecosystem/pull/1257).

## Global Constraints

- [ ] Интеграционная ветка остаётся `egorribun`; не создавать заменяющую продуктовую ветку и не force-push.
- [ ] Не изменять, не применять и не удалять пользовательские stash entries.
- [ ] Не использовать `git reset --hard`, массовый checkout, массовое удаление или очистку workspace.
- [ ] Перед любым staging выполнить `git status --short`, инвентаризировать untracked-файлы и добавлять только явно перечисленные пути.
- [ ] Никогда не добавлять `Co-Authored-By`.
- [ ] Коммиты testing, coverage, quality, CI и документации не связывать с waves.
- [ ] После запуска detect-secrets заново stage `.secrets.baseline`, но только после ручной проверки её diff.
- [ ] Сохранять 100% floor для всех применимых метрик, 100% viable mutation score, пустые `exclusions` и `quarantines`.
- [ ] Неподдерживаемая нативным toolchain метрика обозначается проверяемым `N/A`; её нельзя превращать в вымышленные 100%.
- [ ] Не добавлять suppressions, allowlists, exclusions или retry для продуктовой ошибки. Исключение допустимо только для воспроизведённого false positive с доказательством, узким scope и regression test.
- [ ] Любой отчёт без exact tested commit SHA, а для PR также source head/base identities, run ID, run attempt, source roots, tool versions, hash и timestamp считается недействительным.
- [ ] Targeted-тест или targeted mutation run подтверждает только затронутый scope и не заменяет полный gate.
- [ ] Skipped job считается допустимым только после проверки его `if:` guard и доказательства, что он не required для данного event.
- [ ] Cancelled, timed out, missing, empty, partial и stale artifacts остаются failure.
- [ ] Изменения trust boundaries требуют отдельного security review после реализации.
- [ ] P0/P1, data-loss и high/critical security findings блокируют дальнейший релизный путь.
- [ ] Внешние операции — merge в `main`, production release, Kubernetes deployment, изменение GitHub plan/runner quota и работа с реальными секретами — выполнять только при наличии соответствующего доступа и явной релизной стадии.

## Fixed Product Decisions and Scope Boundaries

- [ ] Scope ограничен существующими доменами и утверждёнными дополнениями: email MFA, завершение Activity, унификация notifications и quality/operational closure.
- [ ] Полный ребрендинг не выполнять; эволюционировать существующие design tokens и университетскую идентичность.
- [ ] Целевые языки — только RU и EN.
- [ ] Целевые роли — student, staff/teacher и admin.
- [ ] Mobile scope — responsive web/PWA; native iOS/Android apps не создавать.
- [ ] Общие уведомления используют in-app center и Web Push; email остаётся transactional каналом для MFA.
- [ ] Общую backend/microservice архитектуру сохранять; менять trust boundaries только для утверждённых контрактов и подтверждённых дефектов.
- [ ] WebAuthn удаляется без compatibility period, но destructive cutover возможен только после успешного migration preflight/remediation.
- [ ] Браузерный release scope — последние две версии Chrome, Edge, Firefox, Safari, плюс iOS Safari и Android Chrome.
- [ ] Новые крупные продуктовые домены, новые языки и native clients не добавлять в этот MVP plan.

---

## 1. Зафиксированный baseline продолжения

### 1.1 Репозиторий (historical baseline; superseded 2026-09-01)

| Поле | Значение на момент подготовки плана |
|---|---|
| Рабочая ветка | `egorribun` |
| Локальный HEAD | `e0989e29cfca88ee9a650eb264d6fa7674031c9a` |
| `origin/egorribun` | тот же SHA |
| Контрольный коммит | `fix: checkpoint MVP quality closure` |
| PR | `#1257`, `egorribun` → `main`, открыт |
| Merge state | `BLOCKED`, пока fresh required checks не зелёные |
| Tracked worktree | без незакоммиченных tracked-изменений |
| Untracked | весь `docs/superpowers/`; нельзя выполнять `git add docs/superpowers` без пофайловой инвентаризации |

Текущий план также находится в untracked-каталоге до отдельного осознанного staging. При будущем коммите документации допустим только явный список:

    git add -- docs/superpowers/plans/University_Ecosystem_MVP.md
    git add -- docs/superpowers/plans/2026-08-25-quality-closure-foundation.md
    git add -- docs/superpowers/plans/prompt.md
    git add -- docs/superpowers/plans/2026-08-31-mvp-quality-closure-continuation.md

Перед этим каждый файл повторно просмотреть; не предполагать, что весь каталог состоит только из этих четырёх документов.

### 1.2 Live PR и workflow snapshot (historical run `33349026009`; see §32)

Основной fresh run для checkpoint SHA: [GitHub Actions run 33349026009](https://github.com/egorribun/university_ecosystem/actions/runs/33349026009).

Snapshot `2026-08-31T13:37:11+03:00` получен через все страницы Jobs API, а не из первых 100 карточек:

- PR `#1257` открыт, `MERGEABLE`, но `BLOCKED` required checks;
- source head PR и `origin/egorribun`: `e0989e29cfca88ee9a650eb264d6fa7674031c9a`;
- для этого source SHA зарегистрировано 25 workflow runs: 22 завершились success, 2 skipped по отдельным guards, основной matrix run остаётся активным;
- основной run содержит 292 jobs: 108 success, 13 skipped, 132 failure, 8 cancelled, 19 in progress и 12 queued;
- GitHub Run API может показывать весь matrix run как `queued`, пока внутри одновременно имеются `in_progress` jobs; источником истины для triage служат paginated job records;
- 132 красных job не означают 132 независимых product defects: 126 из них — mutation execution shards, остальные относятся к двум инфраструктурным причинам и каскадным агрегаторам.

Распределение terminal failures в основном run:

| Группа | Количество | Интерпретация |
|---|---:|---|
| Python `mutmut` execution shards | 69 | реальные survivors/timeouts на уже завершившихся shards; 28 shards success, 19 ещё исполняются и 12 стоят в очереди |
| Frontend Stryker shards | 57 | все terminal shards failed либо cancelled; одновременно присутствуют incomplete-evidence defects и реальные survivors/timeouts/no-coverage |
| Frontend/WASM/aggregate jobs | 5 | WASM producer race и четыре каскадных aggregate/evidence failures |
| detect-secrets | 1 | четыре конкретные findings; mypy в том же job прошёл |

### 1.3 Root-cause ledger (historical snapshot for run `33349026009`)

| ID | Состояние | Доказанная причина | Следующий доказуемый gate |
|---|---|---|---|
| `RC-WASM-01` | `OPEN-DEFECT` | два параллельных `wasm-pack build` одновременно выполняют `rustup target add`, один процесс теряет общий partial rename | serial target install contract, оба crate build success, exact-run artifact |
| `RC-SEC-01` | `OPEN-DEFECT` | detect-secrets находит три credential-like примера в `docs/DEPLOY.md` и deterministic digest fixture в campus test | безопасно переписанные docs; отдельно доказанный narrow false-positive disposition digest; zero findings |
| `RC-STRYKER-01` | `OPEN-DEFECT` | preflight создал 40 800 mutants в 587 files, но runtime range reports не покрывают exact expected signatures | TDD на boundary/range equivalence; каждый shard создаёт complete `SHARD_EVIDENCE.json` |
| `RC-STRYKER-02` | `OPEN-QUALITY` | terminal shards показывают viable score примерно 45.17–85.56%; есть survivors, errors, timeouts и no-coverage | exact forensic ledger, RED tests/refactor для каждого viable mutant, 40 800/актуальный regenerated universe classified без survivor/timeout/no-coverage |
| `RC-MUTMUT-01` | `OPEN-QUALITY` | central Python universe artifact `9743771416` планирует 5 341 exact mutants; representative shards имеют survivors и timeout | terminal ledger из всех selected-results artifacts; RED tests/refactor; zero non-killed/non-type-checked statuses |
| `RC-MUTMUT-02` | `OPEN-DEFECT` | mutation workers печатают OpenTelemetry `atfork` callback errors даже при `OTEL_SDK_DISABLED=true` | исключить provider/fork initialization до app import в mutation environment; deterministic clean worker teardown |
| `RC-GO-MUT-01` | `OPEN-GOVERNANCE` | ws-hub coverage/race прошли, затем 2-hour Go mutation step отменил весь job; текущий step не доказывает mutation score и не публикует полный report | отделить contracted Go evidence от bounded mutation diagnostic; формально определить enforceable semantics или advisory/nightly status без потери contract-owned gates |
| `RC-PROV-01` | `OPEN-DEFECT` | Stryker preflight artifact называет GitHub PR merge SHA `3e4d8f89e56ad2fd12e6529433aa4175f7048687` полем source/head, хотя source head — `e0989e29...` | во всех manifests хранить отдельно PR source head, tested merge SHA, base SHA/ref и проверять их назначение |
| `RC-SCHED-01` | `OPEN-PERF` | Stryker и mutmut независимо запрашивают до 20 slots, дорогой fan-out стартует при красном frontend qualification, очередь голодает | qualification barrier, явные lane budgets, duration-aware bin packing и три comparable green runs |

Ключевые количественные факты, которые нельзя терять при оптимизации:

- Stryker preflight digest: `4464906756c446654a1afbea6825dcb91a5b5f7cc6fbbfd3df8e17fc2fdadaf6`;
- Stryker: 64 shards, 40 800 mutants, от 617 до 657 mutants на shard; семь shards отменены ровно на 2-hour timeout;
- Python mutmut: 5 341 exact mutants по producer log (`Planned all 128 mutmut shards`); равное число mutants на shard не равно равной стоимости;
- общий current mutation universe — 46 141 mutants до следующей детерминированной регенерации;
- повышение timeout или исключение исходников не является исправлением.
- Исключение для устранения конфигурационного рассинхрона: при сохранении
  шестичасового job envelope hard cap mutmut выровнен с доказуемым пределом
  `21 600 - 600 post-run - 30 KILL = 20 970` секунд; live deadline, записанный
  до setup, по-прежнему fail-closed отказывает при нехватке фактического
  headroom. Это не снимает требования duration-aware bin-packing и не
  разрешает обрезать incomplete mutation evidence.

### 1.4 Fresh successes на historical source SHA `e0989e29...`

Отдельные workflow runs, завершившиеся success: Cargo Deny, Checkov, CodeQL Advanced, Continuous Performance Benchmarking, Pact boundaries, OpenAPI/Spectral contracts, DB Performance, Dependency Review, Generate OpenAPI, Gitleaks, Go Fuzz, Go Lint & SBOM, Nilaway, Python Fuzz, Renovate validation, Rust Fuzz, semantic title, SonarCloud, SQLMap, TruffleHog, unauthenticated light/dark smoke и Zizmor.

Внутри main matrix run уже подтверждены:

- backend unit shards 0–3, integration shard 0 и backend aggregate;
- Alembic migrations;
- Schemathesis shards 1–4 и aggregate (предыдущая конфигурация; после fan-out изменения требуется rerun shards 1–8);
- Chromium E2E shards 1–4, Firefox, WebKit и mobile-WebKit;
- Go integration для ws-hub/file-processor/gateway;
- Go tests/lint для gateway, file-processor, uni-cli, SPIFFE и SpiceDB;
- Rust tests, WASM tests, coverage, lint, ASan/LSan и TSan;
- Semgrep, dependency audit, container scan, Go vulnerability scan, SBOM и baseline integrity;
- OpenAPI types, Dockerfile lint и Helm validation;
- Frontend Mutation Preflight Universe;
- mutmut stats shards 0–7;
- E2E coverage artifact uploads.

Fresh E2E всех пяти browser projects означает, что исторические sessions accordion, MFA recovery field, offline indicator, ambiguous selector и News/Events navigation failures на этом SHA не воспроизводятся. Это сильное доказательство regression closure, но не заменяет заблокированные unit/build/Lighthouse/coverage gates.

### 1.5 Skipped и cancelled jobs (historical run `33349026009`)

| Класс | Jobs | Решение |
|---|---|---|
| intentional guard | `Trusted Codecov Upload` на PR; integration shards 1–3, если reusable workflow назначает integration только shard 0; WebSocket 10k advisory по его явному guard | сохранить guard и contract-test его область |
| upstream-blocked, недопустимы как final evidence | frontend unit shards, lint/format, production build, Lighthouse shards, bundle analysis, performance gate, Coverage & Quality Policy Gate, Frontend Mutation Artifact Round-trip | автоматически разблокировать после `RC-WASM-01` и повторить на новом SHA |
| timeout/cancel defect | ws-hub Go mutation job и семь Stryker shards | исправить стоимость/DAG/evidence; не считать intentional skip |
| separate workflow guard | Chromatic и Dependabot auto-merge | проверить `if:` против event/actor; документировать, но не превращать в required PR blockers без contract change |

Каждая запись проверяется повторно в terminal snapshot: таблица не разрешает blanket-утверждение, что «все skipped нормальны».

### 1.6 Что уже находилось в historical checkpoint `e0989e29...`

Следующие изменения присутствуют в `e0989e29c`, но требуют fresh full-matrix подтверждения:

- fail-closed coverage/retry/provenance paths;
- единый frontend WASM producer и reuse same-run artifact;
- Stryker preflight universe, retry и manual/nightly evidence;
- bounded workflow timeouts и stale-run concurrency;
- изолированный Go mutation workspace с local replace modules;
- frontend тесты и fixes для API client, MapLibre, ChatWindow, NewsDetailBody, messenger controller, `useChatWebSocket`, Profile и root route;
- Python тесты/fixes для email OTP, CWV, observability, outbox, notifications и quality workflow contracts;
- targeted Stryker closure для отдельных файлов и targeted mutmut closure для отдельных mutants;
- локально ранее проходили typecheck, actionlint, pre-commit, workflow/quality pytest subset и focused Go test.

Эти результаты имеют класс evidence ниже, чем fresh full CI, и не должны использоваться как финальная сертификация.

### 1.7 Исторический handoff: статус каждой группы

Таблица ниже описывает состояние на старом checkpoint/run и сохраняется для
causal lineage. Для текущей оценки после `db6824789`, `785160201`, `07cdbd0c1`
и `c3ee034ed` использовать authoritative overlay в §32.

| Исторический пункт из `prompt.md` | Текущее чтение репозитория | Что ещё требуется |
|---|---|---|
| Privileged `release.yml` checkout input SHA | checkout сейчас привязан к `github.sha`; release input используется как data, publish job сравнивает event SHA, input и `origin/main` | независимый security review, contract tests и текущий CodeQL/Zizmor |
| Migration `148642dd1207` | migration и PostgreSQL/safety tests существуют; fresh Alembic job green | сохранить green migration contract; отдельно подтвердить Squawk и PostgreSQL upgrade/downgrade evidence в финальном run |
| Dead-letter duplicate UUID test | closure test существует | focused schema test и backend shards |
| mutmut sandbox без `security/audit-allowlist.yaml` | copy-contract и universe inventory существуют | все stats/execution shards должны подтвердить exact `also_copy_inventory` |
| Profile save/snackbar race | тест теперь ждёт committed success state | full Vitest shards после устранения WASM race; не переписывать компонент без нового RED |
| E2E sessions/MFA/offline/navigation/ambiguous selectors | fresh Chromium/Firefox/WebKit/mobile-WebKit green | сохранить сценарии и повторить на final SHA |
| Stryker initial dry run | preflight universe fresh run прошёл | исправить range completeness и закрыть реальные survivors/timeouts/no-coverage во всех 64 shards |
| Dark unauthenticated smoke | fresh light/dark workflows green | повторить на final SHA |
| Полный inventory CI failures | run ещё выполняется; текущие terminal failures сгруппированы в root-cause ledger | дождаться terminal state и добавить каждый поздний non-success без повторного счёта агрегаторов |

### 1.8 Таксономия статуса master-plan вертикалей

В дальнейшем использовать пять статусов:

- `FRESH-GREEN` — реализация и её required current-SHA evidence зелёные;
- `IMPLEMENTED-IN-CODE` — реализация найдена, focused или browser evidence зелёное, но полный gate заблокирован другой причиной;
- `EVIDENCE-BLOCKED` — новый product defect не доказан, однако required evidence не произведено;
- `OPEN-DEFECT` — дефект воспроизведён;
- `EXTERNAL-ONLY` — закрытие требует main/registry/Docker/staging/device/production среды.

Главный принцип продолжения: этапы 1–8 не переписываются повторно. Для них выполняется gap-аудит и recertification; product code меняется только после нового RED evidence. Открытый критический путь сейчас находится в этапах 0, 9 и 10: CI foundation, mutation/coverage provenance и внешняя release certification.

| Этап master plan | Актуальный статус | Доказательства current checkout/merge run | Точный остаток |
|---|---|---|---|
| 0. Baseline/foundation | `EVIDENCE-BLOCKED` | HEAD совпадает с remote; contracts и harness infrastructure присутствуют | исправить CI/provenance roots, получить terminal green current-SHA evidence; явно stage только утверждённые docs |
| 1. Design/performance foundation | `IMPLEMENTED-IN-CODE` | tokens/motion/budgets и тестовый corpus существуют; local typecheck green | frontend unit/build/Lighthouse/coverage разблокировать после WASM; field CWV external |
| 2. Auth/registration/MFA | `IMPLEMENTED-IN-CODE` | email OTP/TOTP/recovery, retirement migrations и tombstone/OpenAPI tests; fresh Alembic и auth browser journeys green | final full CI; не менять runtime без нового RED; исторические migration references разрешены только tombstone contract |
| 3. App shell/mobile navigation | `IMPLEMENTED-IN-CODE` | shell components/tests; fresh Firefox/WebKit/mobile-WebKit journeys green | frontend unit/a11y/visual/performance recertification |
| 4. Scroll/filters/campus map | `IMPLEMENTED-IN-CODE` | router restoration, URL state и lazy MapLibre реализованы; browser matrix green | explicit touch/pinch/memory/long-task evidence |
| 5. Dashboard/Stories/News/Events | `IMPLEMENTED-IN-CODE` | CRUD/content implementation и широкий unit/E2E corpus | final unit/build/Lighthouse, role/state/visual matrix |
| 6. Messenger/ws-hub | `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED` | message-length, admin capability, 44px hit targets и REST-owned read contract исправлены; Go integration/lint/fuzz и local `go test ./...` green | повторить race/coverage/mutation и full browser evidence на final SHA |
| 7. Profile/Settings/Activity/i18n | `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED` | profile/activity/settings implementation; AST static/dynamic/raw-key scanner и `i18n:check` green (2096 static, 68 dynamic, parity 18/18) | final frontend matrix и SHA-bound manifest |
| 8. Notifications/Web Push | `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED` | canonical topics, delivery/retry, SSRF/same-origin defenses; admin test/broadcast use canonical result processing with endpoint-bound stale-result protection | final backend/notification matrix, idempotency and delivery evidence |
| 9. Full quality closure | `OPEN-QUALITY` | contracts, migrations, security workflows, cross-browser E2E частично fresh-green | WASM, secrets, mutation, ws-hub evidence, final normalizer/manifest и zero-warning closure |
| 10. Docker/staging/release | `EXTERNAL-ONLY` + `EVIDENCE-BLOCKED` | release/exact-six validators и существующие `-Core`/`-Lean` launch modes | immutable images, Docker smoke, main, registry attestations, staging/TLS/observability/CWV/devices/chaos/rollback/production |

### 1.9 Подтверждённые продуктовые gaps

1. `P1 / MSG-CONTRACT-01` — **CODE-FIXED**: один предел `32 768` используется backend/frontend/OpenAPI/WS guards; boundary contracts покрывают limit-1/limit/limit+1. Требуется только final-SHA evidence.
2. `P2 / MSG-AUTHZ-01` — **CODE-FIXED**: `ChatArea` вычисляет `canManageChat`, а backend 403 остаётся защитой; regression tests проверяют student/staff/admin.
3. `P2 / MSG-A11Y-01` — **CODE-FIXED**: messenger controls и attachment actions имеют минимум 44×44 hit area с keyboard/focus contracts; нужен final browser/a11y recertification.
4. `P2 / PUSH-CLEANUP-01` — **CODE-FIXED**: `/push/test` и `/push/broadcast` используют `deliver_and_process_push_results`; 404/410 и success обновляются только при совпадении subscription id + endpoint, включая stale gone/sent regression tests (785160201, c3ee034ed).
5. `P2 / I18N-GATE-01` — **CODE-FIXED**: AST static/dynamic/raw-key scanner, typed registry и RU/EN parity gate включены в `npm run i18n:check`; final matrix остаётся обязательной.
6. `P3 / WS-CONTRACT-01` — **CODE-FIXED**: REST является owning read-receipt path, актуальные edited/deleted/reaction/checkpoint types и ws-hub allowlist покрыты contract tests; final generated-contract rerun обязателен.

Эти gaps были единственными основаниями для product changes в bounded аудите и теперь имеют focused code/test closure. Они не являются текущими OPEN-DEFECT, но остаются `EVIDENCE-BLOCKED` до свежего required CI; остальные checklist-пункты этапов 1–8 используются как recertification, а не как разрешение на перепись.

### 1.10 Focused evidence аудита (historical checkpoint)

- `uv run pytest -q tests/contracts/test_ws_message_contract.py tests/test_mfa_openapi_artifacts_contract.py tests/test_mfa_webauthn_tombstone.py` → `26 passed`;
- `frontend: npm run typecheck` → success;
- `frontend: npm run i18n:check` → `18 passed`, при этом suite проверяет parity, а не полный raw/dynamic-key contract;
- `services/ws-hub: go test ./...` → success;
- `services/ws-hub: CGO_ENABLED=1 go test -race ./...` → local evidence unavailable из-за отсутствующего GCC, поэтому race остаётся CI-owned gate;
- local и `origin/egorribun` HEAD совпадали; субагенты не меняли git/worktree/external state.

Focused evidence имеет класс C и не повышается до release evidence из-за успешного exit code одного subset.

### 1.11 Evidence index и граница полноты (historical run `33349026009`)

Подтверждённые current-run anchors:

| Контур | Job / artifact ID | Роль в диагнозе |
|---|---|---|
| WASM producer | job `99358653631` | первичный `rustup target add` race; frontend aggregate failures downstream |
| detect-secrets | job `99358653495` | четыре findings; mypy в этом job green |
| Stryker aggregate | job `99438910765` | получает `0/64` release-valid shard evidence из-за incomplete/exception paths |
| Frontend mutation required context | job `99441529771` | каскадный required-context failure, не отдельный mutant defect |
| ws-hub required job | job `99359416105` | coverage/race прошли, job отменён на Go mutation tail до upload/provenance |
| Stryker preflight | artifact digest `4464906756c446654a1afbea6825dcb91a5b5f7cc6fbbfd3df8e17fc2fdadaf6` | 587 files, 40 800 mutants, 64 shards |
| Python universe | artifact `9743771416` | 5 341 exact mutants, 128 shards |

Stryker shards, отменённые ровно на 120-minute job timeout: `0:99359453824`, `2:99359453914`, `25:99359454050`, `26:99359453886`, `29:99359453991`, `38:99359454875`, `63:99359457053`.

Дополнительный performance baseline:

- 64 повторных `npm ci` заняли около 26.9 runner-minutes setup;
- setup первых 77 mutmut jobs занял около 47.5 runner-minutes;
- Stryker aggregate появился примерно через 7h27m после старта run;
- обе mutation matrices независимо просили до 20 parallel jobs, хотя account cap общий;
- шесть внешних SARIF/check contexts являются status views загрузивших scans, а не шестью дополнительными compute workloads.

Исторические runs используются только для regression lineage:

- run `33338819426` на SHA `a9843eb9` superseded новым push, но уже показывал ws-hub/mutmut classes;
- run `33274790338` на SHA `cc3fb47a` имел backend shard-2, container scan и mutmut-stats failures; эти конкретные classes на current SHA green и не являются текущими blockers.

Ожидаемые guards, которые должны остаться документированными: Dependabot auto-merge actor guard, Chromatic quota/config guard, `publish-performance-history` main-only, Go SBOM publish main-only, backend integration только на shard 0, WebSocket 10k advisory main-only и Trusted Codecov OIDC main-only. Upstream-blocked frontend/coverage jobs из §1.5 не входят в эту категорию.

**Граница абсолютной полноты:** план хранит все подтверждённые root causes, product gaps, status decisions, dependencies, acceptance criteria, evidence anchors и external boundaries. Он намеренно не дублирует полный многотысячестрочный log и изменяющийся список всех 128 mutmut job IDs. Их каноническая форма — terminal machine-readable artifact из Task 1. Historical run `33349026009` superseded текущим run; для current-SHA run `33543238962` до terminal state запрещено утверждать, что «абсолютно вся финальная CI-информация собрана». После terminal state current artifact и итоговые totals должны быть добавлены в audit без изменения причинной структуры плана.

---

## 2. Уровни доказательств

Использовать четыре класса:

- **A — release evidence:** fresh CI/staging artifact для exact tested commit, с отдельными source head/base identities, exact run attempt, schema-valid и hash-verified.
- **B — current-SHA local full gate:** полный локальный gate на том же SHA с сохранённой командой, exit code и tool versions.
- **C — current-SHA focused evidence:** targeted test/mutation/security check, достаточный для конкретного исправления, но не для всей системы.
- **D — historical evidence:** старый CI run, прошлый SHA, архивный audit или рассказ о результате.

Правила:

- [ ] Задача считается локально исправленной при наличии C и пропорционального regression gate.
- [ ] Вертикаль считается закрытой при B плюс свежий CI для её required jobs.
- [ ] MVP считается готовым только при A для полной матрицы и внешнего staging/release scope.
- [ ] В финальном audit явно маркировать класс каждого evidence item.

---

## 3. Критический путь и порядок зависимостей

    flowchart TD
        A["Historical checkpoint e0989e29c и terminal CI inventory"] --> B["WASM race + detect-secrets"]
        A --> C["Provenance: source head != tested merge SHA"]
        B --> D["Qualification: frontend/backend/Go/Rust/API core"]
        C --> D
        D --> E["Stryker range completeness и shard evidence"]
        D --> F["mutmut worker isolation и exact artifact ledger"]
        D --> G["Go mutation governance и bounded diagnostic"]
        E --> H["Закрыть 40 800 frontend mutants"]
        F --> I["Закрыть 5 341 Python mutants"]
        G --> J["Contracted Go evidence сохранено"]
        H --> K["100% quality manifest exact SHA/run/attempt"]
        I --> K
        J --> K
        K --> L["Recertification этапов 1-8; gap-only fixes"]
        L --> M["Docker immutable smoke и resource profile"]
        M --> N["Kubernetes staging, TLS, observability, CWV"]
        N --> O["Main-only exact-six image producer"]
        O --> P["Release audit и production decision"]

Принцип выполнения:

1. Получить terminal failure inventory текущего run и сохранить причинную группировку.
2. Немедленно закрыть WASM race, detect-secrets и source/merge provenance defect.
3. На новом SHA выполнить дешёвую qualification-матрицу; дорогой fan-out разрешён только после green readiness.
4. Сначала доказать полноту mutation runner/evidence, затем закрывать реальные survivors, timeouts и no-coverage.
5. Сохранить все 46 141 current mutants либо детерминированно объяснить новый полный universe; exclusions не добавлять.
6. Получить полный quality manifest, затем recertify уже реализованные этапы 1–8 и исправлять только доказанные gaps.
7. Повторить полный quality closure после последнего изменения product/CI code.
8. Только затем выполнять immutable Docker smoke, staging, main-only producer и release audit.

---

## 4. Модель аудита, исполнения и делегирования

Для refresh этого документа использованы три параллельных read-only аудита: live PR/CI, master-plan verticals и quality/release. Субагенты не получали права редактировать, stage, commit, push или изменять внешнее состояние; итоговая классификация и правка канонического плана остаются у интегратора.

При исполнении плана делегирование применяется только к независимым scopes с явно непересекающимся file ownership. Один root cause — один владелец; интегратор сам повторяет ключевые проверки и не принимает устный статус вместо артефакта.

### 4.1 Интеграционный владелец

Основной агент:

- держит канонический task ledger;
- читает все применимые `AGENTS.md`;
- назначает непересекающиеся file ownership scopes;
- принимает изменения только после focused verification;
- выполняет итоговый diff/security review;
- создаёт небольшие когерентные commits на `egorribun`;
- не позволяет агентам независимо push/merge;
- обновляет current blocker list только по live evidence.

### 4.2 Доступные профили

| Профиль | Разрешённый scope | Рекомендуемые задачи | Запрещено |
|---|---|---|---|
| `lead_architect` | read-only/inherit | CI DAG, quality contract, ADR и dependency review | менять файлы параллельно с интегратором |
| `tdd_developer` | isolated branch | один конкретный root cause через RED → GREEN → REFACTOR | смешивать несколько доменов, push/merge |
| `qa_e2e_tester` | shared/read-mostly | Playwright reproduction, artifacts, ARIA/browser matrix | менять product code одновременно с другим писателем |
| `security_auditor` | read-only/inherit | release trust boundary, MFA, secrets, supply chain | самостоятельно suppress findings |
| `perf_optimizer` | read-only/inherit | CI timing, Docker resources, CWV, map/messenger memory | менять budgets без baseline |

Текущие audited workstreams:

| Workstream | Результат аудита | Следующее допустимое делегирование |
|---|---|---|
| Live PR/CI | paginated snapshot, job/root-cause/skip/cancel inventory | read-only terminal refresh и artifact aggregation |
| Master verticals | code/test/evidence mapping этапов 0–10 | gap-only focused reproduction по одной вертикали |
| Quality/release | contract, provenance, mutation, Docker/staging boundary | независимый security review или bounded performance experiment |

### 4.3 Параллельная схема при лимите четырёх agent slots

Если делегирование снова разрешено:

- slot 1: интегратор;
- slot 2: один TDD implementation scope;
- slot 3: QA/reproduction или второй полностью непересекающийся implementation scope;
- slot 4: read-only security/performance review.

Нельзя параллельно редактировать:

- `.github/workflows/ci.yml`;
- `.github/workflows/reusable-frontend-tests.yml`;
- `.secrets.baseline`;
- `quality/quality-contract.json`;
- один и тот же frontend test file;
- один и тот же Alembic revision;
- generated OpenAPI/TypeScript/MSW artifacts.

Можно параллельно:

- читать разные CI logs;
- выполнять focused Python и frontend tests при достаточных ресурсах;
- проводить read-only security review;
- анализировать Docker stats без запуска дополнительных тяжёлых stacks;
- исследовать разные продуктовые вертикали без записи.

### 4.4 Шаблон задания будущему субагенту

Каждое задание обязано содержать:

1. exact baseline SHA;
2. один root cause или один bounded audit scope;
3. exact file ownership;
4. запрещённые соседние файлы;
5. RED-команду и ожидаемый failure;
6. GREEN-команду и ожидаемый success;
7. полный список изменённых файлов;
8. доказательство отсутствия suppressions/quarantines;
9. запрет commit/push без отдельного разрешения;
10. финальную передачу с командами, exit codes и нерешёнными рисками.

### 4.5 Skills, MCP, plugins и локальные инструменты при будущем исполнении

Использовать только capability, которая помогает текущему bounded scope:

| Этап | Обязательный или предпочтительный skill/tool | Назначение |
|---|---|---|
| Любой новый failure | `superpowers:systematic-debugging` | воспроизведение, гипотеза, root cause, проверка |
| Любое исправление | `superpowers:test-driven-development` | RED → GREEN → REFACTOR |
| Выполнение этого документа | `superpowers:executing-plans` либо после разрешения `superpowers:subagent-driven-development` | последовательное ведение checkboxes |
| GitHub Actions | `github-workflow-automation`, `deployment-pipeline-design` | DAG, permissions, artifact provenance |
| Frontend/browser | `playwright-skill`, `e2e-testing-patterns`, `react-best-practices` | deterministic cross-browser/a11y/performance |
| Security | `codex-security:security-diff-scan`, затем `codex-security:verify-fix` | независимый review trust boundary и MFA |
| Docker/CI performance | `docker-expert`, `performance-profiling`, `performance-optimizer` | измерение ресурсов и критического пути |
| Финальное утверждение | `superpowers:verification-before-completion` | запрет claims без fresh evidence |

Инструментальные правила:

- [ ] `gh` CLI или GitHub MCP использовать для live jobs/logs/artifacts, всегда с run ID и attempt.
- [ ] Context7 использовать только когда поведение версии библиотеки или action могло измениться; итоговое решение сверять с primary official documentation и pinned version.
- [ ] Playwright/browser tooling использовать для реального DOM, screenshots, traces и browser-specific reproduction.
- [ ] Docker CLI использовать сначала read-only; mutations контейнеров ограничивать project-owned resources.
- [ ] Repo scripts и generated machine-readable artifacts предпочтительнее ручного копирования данных из UI.
- [ ] ClickUp не является каноническим источником: при доступном connector утверждённые tasks можно зеркалировать после обновления repo plan, но отсутствие ClickUp не блокирует работу.
- [ ] Не устанавливать нерелевантный plugin только ради формального использования; новый plugin допускается, только если он закрывает конкретный недоступный capability.
- [ ] Не передавать secrets, tokens, private logs или PII во внешние MCP/connectors.

---

## 5. Рабочий протокол для каждой задачи

### 5.1 Systematic debugging

- [ ] Зафиксировать failing job, run ID, attempt, source head SHA и merge SHA.
- [ ] Получить log через GitHub API или artifact; не полагаться на название check.
- [ ] Отделить root failure от aggregate/downstream failure.
- [ ] Воспроизвести минимальную команду локально или в hermetic test.
- [ ] Сформулировать одну проверяемую гипотезу.
- [ ] Добавить regression test, который падает по этой причине.
- [ ] Внести минимальное исправление.
- [ ] Повторить focused test три раза, если дефект связан с race/flakiness.
- [ ] Запустить соседний regression scope.
- [ ] Проверить diff на случайные generated/cached файлы.

### 5.2 TDD

Для каждой реализации:

- **RED:** тест воспроизводит точный дефект и падает по ожидаемой причине.
- **GREEN:** минимальная production/workflow правка делает тест зелёным.
- **REFACTOR:** убрать дублирование и улучшить диагностику без изменения контракта.
- **VERIFY:** focused → domain → full applicable gate.
- **COMMIT:** один логический change set, без wave для quality/testing.

### 5.3 Stop-the-line

Немедленно приостановить текущую вертикаль и исправить:

- утечку секрета или PII;
- destructive migration без remediation;
- privilege escalation;
- потерю/дублирование сообщений или notification events;
- необратимую порчу пользовательских данных;
- artifact reuse между SHA/runs;
- false-green coverage/mutation result;
- production code, исполняемый из dispatch-controlled revision.

---

## 6. Task 0 — безопасное возобновление

**Files to inspect:**

- `AGENTS.md`
- `app/AGENTS.md`
- `frontend/AGENTS.md`
- `services/AGENTS.md`
- `quality/quality-contract.json`
- `.agents/subagents.json`
- четыре документа в `docs/superpowers/plans/`

**Steps:**

- [ ] Проверить `git branch --show-current`; ожидать `egorribun`.
- [ ] Проверить `git rev-parse HEAD` и `git rev-parse origin/egorribun`; они должны совпадать до начала изменений.
- [ ] Выполнить `git status --short --branch`.
- [ ] Выполнить `git stash list --date=local` только для инвентаризации; ничего не применять.
- [ ] Выполнить `git diff --check`.
- [ ] Зафиксировать версии `python`, `uv`, `node`, `npm`, `go`, `rustc`, `cargo`, `docker`, `gh`.
- [ ] Проверить доступ `gh auth status` без вывода tokens.
- [ ] Проверить live PR head SHA и не анализировать старый run как current.
- [ ] Убедиться, что Docker stack не стартует автоматически.
- [ ] Если tracked worktree неожиданно dirty, определить владельца каждого изменения и не перезаписывать его.

**Verification:**

    git status --short --branch
    git rev-parse HEAD
    git rev-parse origin/egorribun
    git diff --check
    gh pr view 1257 --json headRefOid,mergeStateStatus,statusCheckRollup

**Acceptance:** baseline однозначен, пользовательские изменения и stash сохранены, дальнейшие артефакты привязаны к правильному SHA.

---

## 7. Task 1 — terminal inventory и artifact ledger run 33349026009 (historical)

> Run `33349026009` и его 292-job inventory относятся к superseded SHA
> `e0989e29...`. Для продолжения выполнить тот же paginated inventory для
> current run `33543238962` после его terminal state; текущий pending snapshot
> зафиксирован в §32.3.

**Relevant files:**

- `.github/workflows/ci.yml`
- `.github/workflows/reusable-frontend-tests.yml`
- `.github/workflows/reusable-backend-tests.yml`
- `.github/workflows/reusable-go-tests.yml`
- `.github/workflows/reusable-e2e-tests.yml`
- `.github/workflows/reusable-security-audit.yml`

**Steps:**

- [ ] Не перезапускать и не отменять current run: получить его terminal state один раз, потому что поздние mutmut shards расширяют реальный survivor/timeout inventory.
- [ ] Получить все страницы jobs API, а не первые 100.
- [ ] Для каждого non-success записать: job ID, display name, conclusion, started/completed time, dependencies, root log excerpt и artifact names.
- [ ] Для skipped job открыть workflow `if:` и классифицировать `intentional`, `upstream-blocked` или `defect`.
- [ ] Для cancelled job определить: stale-run concurrency, manual cancellation, fail-fast или infrastructure cancellation.
- [ ] Для timeout отделить command timeout от workflow timeout и runner eviction.
- [ ] Сгруппировать aggregate failures под одну root cause, чтобы не считать их отдельными дефектами.
- [ ] Сохранить machine-readable triage в `artifacts/quality/ci-triage/run-33543238962.json` после terminal state; не коммитить runtime artifact.
- [ ] Отдельно скачать Stryker preflight/shard artifacts и mutmut selected-results artifacts, не принимая partial reports как release evidence.
- [ ] Для каждого mutation family построить таблицу `expected / observed / missing / duplicate / survivor / timeout / error / no-coverage / killed`.
- [ ] Проверить current source head `c3ee034ed...`, tested merge SHA, run ID и attempt во всех metadata; старые `e0989e29...`/`3e4d8f89...` — historical fixtures, неправильное название merge SHA как head — defect, даже если hash сам по себе верен.
- [ ] Составить ordered fix queue: security/data-loss → core build → unit/contracts → browser → mutation → performance.

**Предлагаемый новый анализатор:**

- Add: `scripts/quality/analyze_ci_critical_path.py`
- Add tests: `tests/test_ci_critical_path_analysis.py`
- Generated fixture: `tests/fixtures/quality/github-actions-jobs.json`

Интерфейс:

    uv run python scripts/quality/analyze_ci_critical_path.py --repository egorribun/university_ecosystem --run-id 33543238962 --concurrency-cap 20 --diagnostic-lower-bound --output artifacts/quality/ci-critical-path.json

Отчёт должен содержать:

- dependency wait;
- GitHub queue wait;
- setup/install time;
- actual test time;
- artifact upload/download time;
- critical path;
- peak and average slot utilization;
- duplicate setup/download work;
- jobs, заблокированные upstream failure;
- jobs, которые продолжили тратить quota после необратимого core failure.

**Acceptance:** каждый final failure/cancel/skip всех 292 jobs имеет одну проверенную классификацию; mutation ledger покрывает полный expected universe; aggregate failures не дублируют roots; старые runs больше не смешиваются с current SHA.

---

## 8. Task 2 — устранить WASM rustup race (`CODE-FIXED`; fresh evidence pending)

**Files:**

- Modify: `.github/workflows/reusable-frontend-tests.yml`
- Test: `tests/test_frontend_ci_performance_contracts.py`
- Test: `frontend/scripts/build-wasm.test.mjs`
- Test: `frontend/scripts/verify-wasm-artifacts.test.mjs`
- Inspect: `frontend/scripts/build-wasm.mjs`
- Inspect: `frontend/scripts/verify-wasm-artifacts.mjs`

### RED

- [ ] Добавить workflow contract test: target `wasm32-unknown-unknown` устанавливается ровно один раз до появления background PIDs.
- [ ] Добавить test, запрещающий параллельный вызов `rustup target add` из двух `wasm-pack` процессов.
- [ ] Добавить test, что failure одного crate возвращает non-zero и не публикует partial artifact.
- [ ] Запустить focused tests и подтвердить, что current workflow fails new ordering assertion.

### GREEN

- [ ] Перед параллельными builds выполнить serial `rustup target add wasm32-unknown-unknown`.
- [ ] Проверить установленный target через `rustup target list --installed`.
- [ ] Только после этого запускать два независимых `wasm-pack build`.
- [ ] Сохранить parallel compilation двух crate: они имеют разные project/target directories и не должны сериализоваться без измеренной необходимости.
- [ ] При failure удалить или не upload incomplete `pkg` directories.
- [ ] Сохранить `node scripts/verify-wasm-artifacts.mjs` как обязательный postcondition.
- [ ] Не обновлять `wasm-pack` одновременно с race fix; dependency upgrade — отдельная задача.

### REFACTOR

- [ ] Вынести подготовку target в один именованный step с понятной диагностикой.
- [ ] Убедиться, что install action и остальные third-party actions SHA-pinned.
- [ ] Сохранить 15-minute timeout либо изменить его только по измеренному p95.

**Verification:**

    uv run pytest tests/test_frontend_ci_performance_contracts.py -q
    cd frontend
    npm run test:wasm
    npm run typecheck
    npm run build
    cd ..
    actionlint .github/workflows/reusable-frontend-tests.yml
    git diff --check

**Acceptance:** hermetic test доказывает отсутствие concurrent rustup installation; fresh Linux WASM producer строит оба package и публикует один exact-run artifact.

**Commit:** `fix(ci): serialize WASM target installation`

---

## 9. Task 3 — закрыть detect-secrets findings без слепого suppression (`CODE-FIXED`; fresh evidence pending)

**Files:**

- Modify: `docs/DEPLOY.md`
- Modify only if proven false positive: `.secrets.baseline`
- Modify/test: `frontend/src/data/__tests__/campusBuildings.closure.test.ts`
- Inspect: `.pre-commit-config.yaml`
- Add/modify tests: `tests/test_quality_configuration.py`, `tests/test_quality_workflow_contract.py`

### Classification

- [ ] `docs/DEPLOY.md:30`: заменить literal basic-auth Redis URL на безопасную параметризованную форму, например URL из named environment variables.
- [ ] `docs/DEPLOY.md:132`: заменить `user:password` на environment-variable example без credential-like literal.
- [ ] `docs/DEPLOY.md:238`: переписать rotation example так, чтобы документация объясняла порядок ключей, но не содержала assignment с secret-looking values.
- [ ] `campusBuildings.closure.test.ts:52`: подтвердить, что строка — SHA-256 deterministic fixture, а не secret.
- [ ] Для deterministic digest выбрать один прозрачный вариант:
  - узкая baseline entry с exact file/type после доказанного false positive; либо
  - test helper, который получает ожидаемый digest из нескольких понятных частей и остаётся читаемым.
- [ ] Не добавлять inline allowlist к документации, если безопасное переписывание примера решает проблему.
- [ ] Если baseline меняется, проверить, что она не маскирует соседние строки и другие secret types.

### RED

- [ ] Запустить Linux-equivalent detect-secrets version из lock/pre-commit.
- [ ] Сохранить четыре текущие findings как expected RED evidence.
- [ ] Добавить contract test, что docs examples не содержат credential URL literals.

### GREEN

- [ ] Внести минимальные правки.
- [ ] Выполнить detect-secrets.
- [ ] Повторно stage `.secrets.baseline` после review.

**Verification:**

    pre-commit run detect-secrets --all-files --show-diff-on-failure
    pre-commit run mypy --all-files --show-diff-on-failure
    uv run pytest tests/test_quality_configuration.py tests/test_quality_workflow_contract.py -q
    cd frontend
    npm run test -- src/data/__tests__/campusBuildings.closure.test.ts
    cd ..
    git diff --check

**Acceptance:** zero secret findings; документация не учит помещать literal credentials в shell history; deterministic digest test сохраняет назначение; baseline diff узкий и проверенный.

**Commit:** `fix(security): remove credential-like deployment examples`

---

## 10. Task 4 — перепроверить исторические blockers как contracts

### 10.1 Release trust boundary

**Статус:** `CODE-COMPLETE / EXTERNAL-PROOF-PENDING`. Current workflow выполняет trusted-main equality checks; не переписывать trust boundary без failing contract/security evidence. Сохранить независимый review и реальный post-merge release proof.

**Files:**

- `.github/workflows/release.yml`
- `.github/workflows/build-release-images.yml`
- `tests/test_release_certification_contract.py`
- `tests/test_single_producer_image_pipeline.py`
- `tests/test_quality_workflow_contract.py`
- `scripts/quality/validate_release_artifact_evidence.py`
- `scripts/quality/verify_release_image_manifest.py`

**Checklist:**

- [ ] Privileged workflow code checkout использует только immutable event/default-main SHA.
- [ ] `inputs.release-sha` никогда не выбирает выполняемые scripts/actions.
- [ ] Перед publish сравниваются `GITHUB_SHA`, input SHA, checked-out HEAD и fetched `origin/main`.
- [ ] Run metadata проверяет repository, workflow path, event, head branch, head SHA, run attempt и conclusion.
- [ ] Artifact name, manifest contents, attestation subject и image digests согласованы.
- [ ] Cache namespace privileged workflow не восстанавливает PR-controlled cache.
- [ ] Permissions минимальны на уровне workflow и jobs.
- [ ] `persist-credentials: false` используется до явного release step.
- [ ] Независимо выполнить Zizmor, actionlint, CodeQL и security diff review.

**Acceptance:** dispatch-controlled value может только выбрать уже attestированный artifact; ни один его байт не влияет на исполняемый privileged source.

### 10.2 Migration `148642dd1207`

**Статус:** `FRESH-GREEN` на historical tested merge; current exact-SHA migration/Squawk evidence pending in run `33543238962`. Checklist сохраняется для final-SHA rerun.

**Files:**

- `alembic/versions/148642dd1207_fix_missing_tables.py`
- `tests/test_migration_148642dd1207_safety.py`
- `tests/integration/test_migration_148642dd1207.py`
- `scripts/quality/alembic_schema_drift.py`
- `scripts/quality/migration_downgrade_policy.py`

**Checklist:**

- [ ] Upgrade использует phased conversion для `groups.id`.
- [ ] Backfill выполняется до enforced conversion/constraint.
- [ ] Conversion имеет явное `USING`.
- [ ] Для `active_sessions.signing_key` сначала nullable/add, затем deterministic backfill, затем validated constraint/NOT NULL.
- [ ] Preflight блокирует неустранимые строки с диагностикой, не теряя данные.
- [ ] Downgrade policy явно указывает обратимые и необратимые части.
- [ ] PostgreSQL test выполняет upgrade с legacy data, проверяет IDs/FKs/session keys, затем допустимый downgrade.
- [ ] Squawk zero-warning или каждое remaining warning устранено конструкцией migration, а не ignore.
- [ ] Alembic heads ровно один; schema drift отсутствует.

**Verification:**

    uv run pytest tests/test_migration_148642dd1207_safety.py -q
    uv run pytest tests/integration/test_migration_148642dd1207.py -q
    uv run alembic heads
    uv run alembic upgrade head
    uv run python scripts/quality/alembic_schema_drift.py

### 10.3 Dead-letter UUID schema

**Статус:** `CODE-COMPLETE / FRESH-BACKEND-GREEN` на historical run; current backend shard rerun pending. Сохранить отдельные duplicate-valid, invalid-format и empty/mixed cases; final-SHA rerun обязателен.

**Files:**

- `tests/test_schemas_closure.py`
- owning schema under `app/schemas/`
- `tests/test_notification_dead_letter_api.py`

**Checklist:**

- [ ] Test использует два одинаковых валидных UUID и ожидает duplicate rejection.
- [ ] Invalid UUID test остаётся отдельным и проверяет формат.
- [ ] Empty IDs и mixed valid/invalid inputs имеют отдельные assertions.
- [ ] Production schema не ослабляется ради старого теста.

### 10.4 mutmut isolated copy

**Статус:** `CODE-COMPLETE`. Current `also_copy` уже включает `security`, exact audit allowlist, `quality`, generated inputs, `alembic` и `alembic.ini`; universe v2 проверяет inventory/hash/symlink/traversal. Не повторять старое исправление, а сохранить contract при mutation-runner changes; current exact mutation artifacts pending.

**Files:**

- `scripts/mutmut_universe.py`
- `tests/test_mutmut_copy_contract.py`
- `.github/workflows/ci.yml`
- `.github/workflows/nightly-full-gate.yml`
- `security/audit-allowlist.yaml`

**Checklist:**

- [ ] `security/audit-allowlist.yaml` входит в `also_copy_inventory`.
- [ ] Manifest содержит path, hash и config fingerprint.
- [ ] Missing/mutated/stale copy вызывает fail-closed.
- [ ] Все stats и execution shards используют один exact universe contract.
- [ ] Никакой test не skipped из-за отсутствующей копии.

### 10.5 Profile save

**Статус:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`; bounded audit не нашёл нового product RED. Повторить full Vitest после WASM fix и менять только при воспроизведении.

**Files:**

- `frontend/src/pages/Profile.tsx`
- `frontend/src/pages/__tests__/Profile.behavior.test.tsx`
- `frontend/src/components/profile/ProfileEditor.tsx`

**Checklist:**

- [ ] Test ждёт committed state, а не только resolved mock promise.
- [ ] `saving=true` видим только во время pending request.
- [ ] Success обновляет auth/query cache, закрывает edit mode и показывает snackbar.
- [ ] Failure сохраняет edit state, возвращает `saving=false` и показывает localized error.
- [ ] Double submit блокируется.

### 10.6 E2E regressions

**Статус:** `FRESH-GREEN` для Chromium 4/4, Firefox, WebKit и mobile-WebKit на historical tested merge. Current Matrix browser jobs pending; checklist остаётся final-SHA regression contract.

**Files:**

- `frontend/tests/e2e/profile-settings.spec.ts`
- `frontend/tests/e2e/mfa_recovery.spec.ts`
- `frontend/tests/e2e/mfa-backup-codes.spec.ts`
- `frontend/tests/e2e/offline.spec.ts`
- `frontend/tests/e2e/offline_behavior.spec.ts`
- `frontend/tests/e2e/url-state-persistence.spec.ts`
- `frontend/tests/e2e/utils/navigation.ts`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/pages/settings/SettingsSecurity.tsx`
- `frontend/src/pages/settings/SettingsSessions.tsx`

**Checklist:**

- [ ] Sessions accordion имеет уникальное accessible name, expanded state и stable test contract.
- [ ] Recovery-code factor имеет явное поле и label.
- [ ] На странице один ожидаемый top-level heading; nested headings имеют корректные levels/names.
- [ ] Settings buttons различимы accessible name без `.nth()`.
- [ ] Offline indicator является продуктовым состоянием, а не test-only marker.
- [ ] `gotoWithTransientRetry` повторяет только browser-level transient cancellation и не скрывает HTTP/app errors.
- [ ] Firefox/WebKit failures воспроизводятся отдельно; arbitrary sleep запрещён.
- [ ] Каждый selector основан на role/name/state либо устойчивом contract test ID, а не на визуальном DOM порядке.

### 10.7 Dark smoke

**Статус:** `FRESH-GREEN` для light и dark unauthenticated workflows на historical source SHA; current run `33543238031` ещё in progress.

- [ ] Считать current success промежуточным.
- [ ] Повторить light/dark unauthenticated routes на final SHA.
- [ ] Проверить hydration, console errors, CSP, theme persistence и screenshot artifact.

---

## 11. Task 5 — оптимизировать CI под лимит 20 jobs

### 11.1 Цель оптимизации

Ускорение допустимо только за счёт:

- устранения повторной работы;
- выравнивания shard cost;
- безопасного caching third-party dependencies;
- правильного DAG;
- раннего выявления blockers;
- предотвращения дорогих downstream jobs после core failure;
- контролируемой внутренней параллельности внутри runner;
- отмены superseded runs.

Нельзя ускорять за счёт:

- уменьшения test/mutant/source inventory;
- пропуска браузера;
- снижения coverage/mutation threshold;
- `continue-on-error` на blocking gate;
- превращения required job в advisory;
- reuse artifact от другого SHA/run/attempt;
- снятия security scans;
- неконтролируемого batch, превышающего timeout.

### 11.2 Измерить реальный критический путь

- [ ] Реализовать анализатор из Task 1 и проверить его на сохранённом fixture без GitHub write operations.
- [ ] Зафиксировать текущий baseline: 292 jobs, 20-slot cap, одновременно конкурирующие Python и frontend mutation matrices.
- [ ] Для каждого job вычислить dependency wait, GitHub queue wait, setup/install, actual test, artifact и teardown time.
- [ ] Отдельно посчитать 64 Stryker shards, 8 mutmut stats shards, 128 mutmut execution shards и Go mutation diagnostic.
- [ ] Сохранить current performance baseline: run >8 hours; Stryker queue до 5h10m и около 44.8 runner-hours; для первых 77 mutmut jobs средняя очередь 2h57m, max 7h17m и уже около 77.7 runner-hours.
- [ ] Считать cancelled-at-timeout shard отдельным цензурированным duration observation, а не выбрасывать из статистики.
- [ ] Обновлять `quality/test-durations.json` только из trusted exact-input evidence; runtime triage хранить под `artifacts/`, не коммитить.
- [ ] Сравнивать wall clock, billed runner-minutes, p95 shard time, queue starvation и time-to-first-actionable-failure.
- [ ] Собрать минимум три comparable green runs после стабилизации core, прежде чем объявлять оптимизацию доказанной.

### 11.3 Qualification barrier и новый DAG

Предлагаемая последовательность:

1. **Fast qualification:** workflow syntax, lock/config integrity, detect-secrets/mypy, WASM target producer, OpenAPI drift.
2. **Core readiness:** backend unit/integration, frontend unit/lint/build, Go race/coverage/static, Rust, migrations/contracts, короткий E2E smoke.
3. **Mutation preflight:** exact source/test/config hashes, universe generation, range/copy-contract validation.
4. **Mutation fan-out:** Python и frontend получают явные lane budgets только после green owning-core readiness.
5. **Full browser/performance/security:** параллельно mutation только в зарезервированных slots; ни один required diagnostic не голодает.
6. **Aggregation:** coverage, mutation, security, provenance и `CI Success` проверяют полный child manifest.

**Required changes:**

- [ ] `frontend-mutation-preflight` и shards зависят от green WASM + frontend unit/build readiness.
- [ ] mutmut execution зависит от green backend tests/type/static readiness.
- [ ] При failure qualification mutation fan-out не создаёт сотни queued jobs.
- [ ] Aggregators используют `always()` только для полной диагностики и fail-closed проверяют каждое required conclusion/artifact.
- [ ] Stale PR runs отменяются по source ref concurrency group; release/main jobs имеют отдельные trusted groups.
- [ ] Main/release workflows не разделяют untrusted PR cache namespace.
- [ ] Состояние `skipped because upstream failed` отличается от intentional guarded skip в machine-readable summary.

### 11.4 Frontend Stryker: сначала доказать полноту runner

**Files:**

- `.github/workflows/ci.yml`
- `frontend/scripts/run-stryker.mjs`
- `frontend/stryker.config.mjs`
- tests рядом с runner/config и quality workflow contract tests

**RED:**

- [ ] Добавить fixture с boundary mutants на первой/последней строке и нескольких columns одного line range.
- [ ] Воспроизвести current defect: preflight expected signatures присутствуют, runtime `mutation.json` их не возвращает.
- [ ] Проверить точную семантику Stryker `mutate` ranges по line/column; не предполагать, что source-line grouping эквивалентен runtime selection.
- [ ] Добавить test, что missing, duplicate, out-of-range или wrong-file mutant делает shard invalid.
- [ ] Добавить test, что exception до evidence creation всё равно оставляет diagnostic artifact, но никогда не release-valid evidence.

**GREEN:**

- [ ] Сделать preflight и runtime planner одной канонической функцией либо одним exact mutant-ID inventory с проверяемым mapping.
- [ ] Каждый shard получает disjoint exact inventory; union всех 64 shards равен universe 40 800/актуальному regenerated count.
- [ ] Каждый успешный shard публикует `mutation.json`, `SHARD_EVIDENCE.json`, config/source hashes, source head SHA, tested merge SHA, run ID и attempt.
- [ ] Добавить non-release forensic aggregator для текущих partial artifacts; он маркирует отчёт `diagnostic-only` и не может удовлетворить quality gate.
- [ ] Merge rejects incomplete shard до вычисления общего score.

**Acceptance:** все 64 dry-run/evidence contracts полны и попарно непересекаются; ни один range defect не маскирует реальный mutation result.

### 11.5 Frontend Stryker: закрыть реальные mutants и стоимость

- [ ] Построить exact ledger по file, mutant ID, mutator, location, status, duration и owning tests.
- [ ] Сначала классифицировать все current survivors, errors, timeout examples и no-coverage; observed shard scores 45.17–85.56% считать доказательством незакрытого качества.
- [ ] Для каждого viable survivor: RED test → GREEN → refactor; equivalent/unobservable code упрощать в production source, а не исключать из inventory.
- [ ] No-coverage исправлять тестом либо удалением недостижимого production code с отдельным доказательством.
- [ ] Timeout исследовать как зависание/слишком широкий test selection; простое увеличение 2-hour limit запрещено.
- [ ] Построить mutant-to-test dependency map из deterministic coverage/input hashes, сохранив sentinel/global contract suite для shared boundaries.
- [ ] Измерить внутреннюю `concurrency` 1/2/4: на 2-vCPU runner значение 4 не принимать без throughput evidence.
- [ ] Использовать per-mutant durations для LPT/bin packing; целевой p95 shard выбирается после benchmark и должен иметь запас до job timeout.
- [ ] Сохранить `incremental: false`, полный production scope и пустые ignore/exclusion lists.

**Acceptance:** каждый mutant текущего полного universe имеет terminal allowed status `Killed` или доказанный toolchain-equivalent status, разрешённый contract; survivor, timeout, no-coverage, runtime error, pending и missing равны нулю; viable score 100%.

### 11.6 Python mutmut: exact ledger, worker isolation и survivor closure

**Files:**

- `scripts/mutmut_universe.py`
- mutmut runner/aggregation scripts и `.github/workflows/ci.yml`
- `tests/test_mutmut_copy_contract.py`
- tests owning survivors в MFA/notifications/schedule/observability domains

- [ ] Дождаться terminal run и скачать все selected-results artifacts для exact current universe 5 341.
- [ ] Свести каждый mutant ровно один раз; reject missing, duplicate, wrong source hash, wrong run/attempt и partial result.
- [ ] Зафиксировать initial survivor families, включая `EmailOtpService.consume_recovery_opaque`, `notifications.delivery.redeliver_notifications`, `schedule_reminders.generate_schedule_reminders` и новые terminal findings.
- [ ] Воспроизвести `_shutdown_otel_providers_bounded` timeout отдельно.
- [ ] До импорта app отключить создание OpenTelemetry exporters/readers и `atfork` callbacks в mutation worker; не suppress stderr и не скрывать exception.
- [ ] Для каждого viable survivor применить RED → GREEN → REFACTOR; equivalent code упрощать, не allowlist.
- [ ] Построить dependency/per-test coverage mapping, чтобы каждый mutant не запускал неоправданно широкий union; сохранить fail-closed global sentinels.
- [ ] Bin-pack по фактическим mutant durations, а не по 37–42 равным counts; неизвестным назначать conservative cost.
- [ ] Timeout job оставить measured и bounded; увеличение с текущих 360 minutes не является решением.
- [ ] Все 5 341 mutants должны остаться в exact inventory либо актуальном детерминированно regenerated universe.

**Acceptance:** complete universe classified; killed/type-checked составляют 100% contract-allowed outcomes; survivor, timeout, no-test, suspicious, skipped, unclassified и worker error равны нулю.

### 11.7 Go mutation governance и сохранение contracted evidence

- [ ] Разделить ws-hub race/coverage producer и mutation diagnostic, чтобы долгий diagnostic не удалял уже валидный Go report.
- [ ] Зафиксировать, что current quality contract требует Go statements 100%, race/static/security behavior, а не вымышленную branch/function coverage.
- [ ] Не удалять Go mutation молча: принять одно из двух формальных решений с tests/docs:
  - bounded content-addressed incremental diagnostic остаётся advisory PR/nightly с полным report и нулевым влиянием на contract-owned Go evidence; или
  - Go mutation добавляется в quality contract с точной viable/equivalent semantics и 100% enforceable score.
- [ ] Предпочтительный текущему master contract вариант — первый; он не ослабляет ни один утверждённый required gate и устраняет вводящий в заблуждение 2-hour pseudo-gate.
- [ ] Для diagnostic shard по package/file/range cost, upload complete report и fail самого diagnostic на tool/runtime error.
- [ ] Добавить workflow contract tests, что coverage artifact публикуется независимо от diagnostic outcome и required aggregate использует contract-owned status.

**Acceptance:** ws-hub 100% statements + race/static/security evidence всегда доступно; mutation diagnostic bounded, честно классифицирован и не изображает несуществующий score.

### 11.8 Разделить 20 slots без starvation

Первый benchmark после qualification:

- зарезервировать минимум 4 slots для required non-mutation diagnostics/aggregates;
- оставшиеся 16 slots начать с lane budget 8 Stryker + 8 mutmut;
- если mutation запускается после полного core, benchmark 9/7, 8/8 и 7/9 по фактическому throughput;
- не позволять двум независимым matrices одновременно выставлять `max-parallel: 20`.

Для каждого изменения lane count:

- [ ] Сравнить total CPU-minutes и wall-clock critical path.
- [ ] Проверить queue latency, timeout probability и runner throttling.
- [ ] Убедиться, что fast failure/aggregate не ждёт за mutation wall.
- [ ] Доказать три comparable runs без reliability regression.

### 11.9 Duration-aware sharding

Общие правила:

- [ ] Universe каждого tool генерируется один раз на exact source/config/test hashes.
- [ ] Inventory содержит exact mutant IDs, source hashes и provenance.
- [ ] Cost model использует предыдущие successful per-mutant durations, а не только file/count.
- [ ] Bin packing минимизирует максимальную сумму cost; неизвестный mutant получает conservative default.
- [ ] Retry меняет attempt metadata, но не universe; первый outcome не стирается.
- [ ] Ни один batching change не принимается, если union/uniqueness/completeness tests не проходят.

### 11.10 Уменьшить setup overhead

- [ ] Один WASM producer на workflow attempt.
- [ ] Один frontend dependency cache key на exact lockfile/Node/runtime.
- [ ] Один Python lock-verified environment cache namespace на exact lock/config.
- [ ] Cargo cache разделять по crate/toolchain/lockfile без cross-trust reuse.
- [ ] Go cache разделять по module/go.sum/version.
- [ ] Не upload/download `node_modules` как quality evidence.
- [ ] Compression level выбирать по размеру/CPU: уже сжатые packages передавать без повторной дорогой компрессии.
- [ ] Короткие static checks объединить в несколько lane jobs только после измерения, сохранив отдельную диагностику и required aggregate.

### 11.11 Устранить дубли

- [ ] Typecheck запускается один раз как owner gate.
- [ ] WASM build запускается один раз.
- [ ] OpenAPI generation имеет одного producer; consumers проверяют drift.
- [ ] Docker image для scan/smoke/release строится один раз на stage, затем проверяется по digest.
- [ ] Coverage merge не перезапускает tests.
- [ ] Lighthouse routes используют один LHCI-specific immutable build.
- [ ] E2E browser install не повторяется в одном job без причины.

### 11.12 Надёжность workflow

- [ ] Все runner jobs имеют measured timeout.
- [ ] `fail-fast: false` используется там, где нужен полный inventory.
- [ ] Retry разрешён только для классифицированного transient dependency/network failure.
- [ ] Retry artifact хранит first-attempt outcome и не стирает его.
- [ ] `if: always()` aggregates валидируют все child conclusions.
- [ ] Action refs SHA-pinned.
- [ ] Workflow permissions read-only по умолчанию.
- [ ] Shell blocks используют strict mode.
- [ ] Artifact selection reject duplicate candidates и wrong attempts.

### 11.13 CI performance acceptance

- [ ] Time-to-first-actionable-failure уменьшен относительно baseline.
- [ ] При core failure mutation jobs не стартуют.
- [ ] 20-slot utilization высокая после core readiness и не блокирует diagnostics.
- [ ] Нет job timeout и starvation.
- [ ] Полный source/test/mutant inventory неизменен либо расширен.
- [ ] Total wall-clock и total billed minutes записаны до/после.
- [ ] Изменение считается улучшением только при трёх последовательных comparable runs без reliability regression.

---

## 12. Task 6 — Auth, registration, MFA и окончательное удаление WebAuthn

**Статус аудита:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Email OTP, TOTP, recovery и retirement migrations присутствуют; fresh Alembic/E2E и focused tombstone/OpenAPI tests зелёные. Этот раздел является recertification checklist. Менять auth runtime только при новом failing security/contract test; исторические migration fixtures не считать runtime WebAuthn.

**Backend files:**

- `app/api/auth/login.py`
- `app/api/auth/mfa.py`
- `app/api/deps/auth.py`
- `app/auth/constants.py`
- `app/auth/schemas.py`
- `app/auth/mfa/challenge.py`
- `app/auth/mfa/email_otp.py`
- `app/auth/mfa/lifecycle.py`
- `app/auth/mfa/recovery.py`
- `app/auth/mfa/trusted_device.py`
- `app/services/auth/login_service.py`
- `app/services/auth/mfa_coordinator.py`
- `app/repositories/auth_repository.py`
- `app/models/auth.py`
- `app/core/config/mixins/mfa_settings.py`

**Migration/contract files:**

- `alembic/versions/202608250002_contract_retire_webauthn.py`
- `alembic/versions/202608270001_reconcile_mfa_schema.py`
- legacy WebAuthn revisions retained only as migration history
- `frontend/openapi.json`
- `frontend/src/api/generated/types.gen.ts`
- `frontend/src/tests/mocks/generated/handlers.ts`

**Frontend files:**

- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/Register.tsx`
- `frontend/src/components/auth/MfaChallengeView.tsx`
- `frontend/src/components/mfa/OtpEntry.tsx`
- `frontend/src/components/mfa/StepUpDialog.tsx`
- `frontend/src/pages/settings/SettingsSecurity.tsx`
- `frontend/src/pages/settings/hooks/useEmailMfa.ts`
- `frontend/src/hooks/auth/useLoginFlow.ts`
- RU/EN `auth.json` и `settings.json`

### 12.1 Contract audit

- [ ] Public ordinary factor union только `totp | email_otp`.
- [ ] Emergency factor `recovery_code` отдельный.
- [ ] `webauthn` отсутствует в current runtime, OpenAPI, generated SDK, UI и active schema.
- [ ] WebAuthn допускается только в immutable migration history, archive docs и tombstone tests.
- [ ] `MfaMethodChallengeOut` содержит method, delivery hint, resend timestamp, token, expiry и attempts.
- [ ] `POST /api/v1/auth/mfa/verify` обрабатывает email OTP.
- [ ] `POST /api/v1/auth/mfa/email/resend` атомарно ротирует code/expiry.

### 12.2 Email OTP security

- [ ] 6 digits from CSPRNG.
- [ ] TTL 10 minutes.
- [ ] 5 attempts maximum.
- [ ] 60-second resend cooldown.
- [ ] One-time atomic consumption.
- [ ] HMAC/digest at rest; plaintext отсутствует в БД, log, trace и metric labels.
- [ ] Binding к user, challenge, session и client fingerprint.
- [ ] Rate limits по IP и user.
- [ ] Delivery через transactional outbox/email worker.
- [ ] RU/EN templates.
- [ ] External responses не раскрывают existence/account state.
- [ ] Resend инвалидирует старый code немедленно.
- [ ] Concurrent verify/resend имеет deterministic winner и no replay.

### 12.3 Migration preflight

- [ ] TOTP users остаются TOTP.
- [ ] Verified-email users получают email OTP path.
- [ ] WebAuthn-only account без verified email/TOTP/recovery блокирует destructive migration.
- [ ] Remediation output перечисляет affected IDs безопасно, без PII.
- [ ] Upgrade/downgrade policy tested на PostgreSQL.

### 12.4 Tests

- [ ] TOTP happy/error/replay.
- [ ] Email OTP happy/expired/wrong/replayed/rotated.
- [ ] Attempt exhaustion.
- [ ] Cooldown.
- [ ] Concurrent verify/resend.
- [ ] Fingerprint mismatch.
- [ ] SMTP/outbox failure.
- [ ] Recovery code one-time flow.
- [ ] Session revocation/trusted device.
- [ ] WebAuthn-only migration cases.
- [ ] Secret/PII log redaction.
- [ ] Student, staff и admin.
- [ ] RU и EN.
- [ ] Accessible auth fields/password managers/autocomplete.
- [ ] Safe redirects, CSRF, offline/lockout/loading.

**Focused commands:**

    uv run pytest tests/test_mfa_email_otp_domain.py tests/test_mfa_security_regressions.py tests/test_mfa_email_otp_migrations.py tests/integration/test_mfa_email_otp_postgres.py -q
    uv run pytest tests/test_mfa_openapi_artifacts_contract.py tests/test_mfa_webauthn_tombstone.py -q
    cd frontend
    npm run test -- src/components/auth/MfaChallengeView.test.tsx
    npm run test -- src/pages/settings/__tests__/SettingsSecurity.behavior.test.tsx
    npm run typecheck

**Acceptance:** runtime/API/schema/UI не содержат WebAuthn; TOTP, email OTP и recovery работают end-to-end в трёх ролях и двух языках.

---

## 13. Task 7 — Design system, UX и performance foundation

**Статус аудита:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Tokens, motion, UI states, budgets и test corpus присутствуют; TypeScript typecheck green. Не выполнять повторный redesign. Required unit/build/Lighthouse/coverage evidence сейчас заблокировано `RC-WASM-01`, а field CWV относится к external certification.

**Files:**

- `frontend/src/components/ui/`
- `frontend/src/components/feedback/`
- `frontend/src/components/motion/`
- `frontend/src/styles/tokens/`
- `frontend/src/styles/globals.css`
- Storybook stories рядом с components
- `frontend/scripts/run-lhci.mjs`
- `.lighthouserc` или active Lighthouse config

**Inventory:**

- [ ] Typography scale.
- [ ] Spacing.
- [ ] Radii.
- [ ] Elevation.
- [ ] Focus rings.
- [ ] Motion durations/easing.
- [ ] Buttons, fields, tabs, cards, dialogs, popovers.
- [ ] Skeleton, empty, error, offline, partial states.
- [ ] Touch targets minimum 44×44.
- [ ] Contrast and themes.

**Implementation:**

- [ ] Удалить glow и тяжёлые нефункциональные hover effects.
- [ ] Frequent animations ограничить `transform` и `opacity`.
- [ ] Использовать central reduced-motion contract.
- [ ] Запретить layout-triggering animation.
- [ ] Cleanup timers, observers, portals и object URLs.
- [ ] Унифицировать focus visible, focus trap, restore и obscured focus.
- [ ] Не резервировать высоту для отсутствующего content.
- [ ] Skeleton geometry должна совпадать с content geometry.

**Gates:**

- [ ] Storybook visual baseline на компоненты и состояния.
- [ ] axe: zero serious/critical.
- [ ] WCAG 2.2 AA, включая Accessible Authentication, Focus Not Obscured и Target Size.
- [ ] LCP p75 ≤ 2.5 s.
- [ ] INP p75 ≤ 200 ms.
- [ ] CLS ≤ 0.1.
- [ ] LHCI key routes ≥ 95.
- [ ] Main JS chunk < 500 KB.
- [ ] Repeated interaction memory plateau.

**Acceptance:** одна визуальная система без accessibility/performance regressions.

---

## 14. Task 8 — App shell: Navbar, Footer и mobile navigation

**Статус аудита:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Fresh Firefox/WebKit/mobile-WebKit journeys зелёные. Checklist ниже — bounded regression audit; менять shell только после воспроизводимого a11y/visual/performance gap.

**Files:**

- `frontend/src/components/navbar/Navbar.tsx`
- `frontend/src/components/navbar/useNavbarMorph.ts`
- `frontend/src/components/navbar/useNavbarLogic.ts`
- `frontend/src/components/navbar/MobileMenu.tsx`
- `frontend/src/components/layout/Footer.tsx`
- `frontend/src/components/layout/MobileBottomNav.tsx`
- corresponding stories/tests

**Checklist:**

- [ ] Passive scroll listener + one `requestAnimationFrame`.
- [ ] Hysteresis prevents rapid morph oscillation.
- [ ] Stable layout height prevents CLS.
- [ ] No bottom glow.
- [ ] Desktop/mobile share one state model.
- [ ] Reduced-motion fallback.
- [ ] Footer link groups, official Telegram SVG, external link labels.
- [ ] MobileMenu focus trap, Escape/backdrop close, scroll lock, safe areas.
- [ ] No rapid-tap mount/animation race.
- [ ] Bottom nav equal hit sectors, centered icons, one active state, ARIA semantics.
- [ ] Virtual keyboard/browser chrome do not cover nav.

**Matrix:** 360, 390, 768, 1024, 1440 widths; keyboard; 200% zoom; rapid transitions.

**Acceptance:** visual regression, keyboard and stress tests green without CLS/jank.

---

## 15. Task 9 — Scroll ownership, filters и campus map

**Статус аудита:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Native router restoration, URL-state и lazy MapLibre найдены; cross-browser E2E green. Остаток — dedicated touch/pinch, memory plateau и long-task evidence, а не повторная архитектура маршрутов.

**Files:**

- `frontend/src/routes/__root.tsx`
- `frontend/src/pages/News.tsx`
- `frontend/src/pages/Events.tsx`
- `frontend/src/pages/Map.tsx`
- `frontend/src/components/map/MapLibreMap.tsx`
- map components/tests
- `frontend/tests/e2e/url-state-persistence.spec.ts`

**Scroll contract:**

- [ ] New route restores position by route key.
- [ ] Filter/search params on same route preserve viewport.
- [ ] Modal/detail returns to previous anchor/offset.
- [ ] News/Events category changes do not remount route root.
- [ ] No unconditional `scrollTo(0, 0)` on filter change.
- [ ] Activity period slider and Events status tabs centered; visual/control hitboxes match.

**Map contract:**

- [ ] MapLibre stays dynamic/lazy.
- [ ] Prefetch only on idle or user intent.
- [ ] One map instance per mounted route.
- [ ] Marker/layer data memoized.
- [ ] Large data clustered.
- [ ] Weather/particles disabled for reduced motion and weak device profile.
- [ ] Local gesture/overscroll containment does not block whole page.
- [ ] wheel/touch/pinch ownership deterministic.
- [ ] Listeners/workers/map resources released on unmount.

**Tests:**

- [ ] Unit tests for route key and scroll restoration.
- [ ] Playwright wheel/touch/pinch isolation.
- [ ] Repeated mount/unmount memory plateau.
- [ ] Long-task observation under map interaction.

**Acceptance:** filters do not throw page to top; map never drives external scroll and leaves no resource leak.

---

## 16. Task 10 — Dashboard, Stories, News и Events

**Статус аудита:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Реализация и широкий unit/E2E corpus существуют. Изменения допустимы только для gaps, обнаруженных final unit/build/Lighthouse/role/state/visual matrix.

**Files:**

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/components/stories/`
- `frontend/src/pages/News.tsx`
- `frontend/src/pages/NewsDetail.tsx`
- `frontend/src/pages/Events.tsx`
- `frontend/src/pages/EventDetail.tsx`
- `frontend/src/components/news/`
- `frontend/src/components/events/`
- backend routers/services/repositories for stories/news/events

**Dashboard:**

- [ ] Schedule/news/events cards share sizing/state semantics.
- [ ] Empty cards do not reserve unused height.
- [ ] Remove decorative wobble.
- [ ] Skeleton-to-content geometry predictable.

**Stories:**

- [ ] Open only from interactive avatar/circle.
- [ ] Preload only next story.
- [ ] Pause/resume on visibility and interaction.
- [ ] Keyboard and swipe navigation.
- [ ] Focus enters/restores correctly.
- [ ] ARIA names and progress available.
- [ ] Cleanup timers/media/listeners.
- [ ] Portrait/landscape/mobile.
- [ ] Cyclic open/close memory plateau.

**News/Events:**

- [ ] Preserve CRUD, detail, bookmark/registration and admin flows.
- [ ] Loading, empty, partial, error, offline, pagination.
- [ ] Stable query keys and no duplicate fetch.
- [ ] Optimistic updates with rollback.
- [ ] Authorization for student/staff/admin.
- [ ] Localized dates, plurals and status.

**Acceptance:** content routes match design system; CRUD remains complete; repeated Stories use does not grow memory.

---

## 17. Task 11 — Messenger и ws-hub

**Статус аудита:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Message-length, admin capability, 44px targets и REST-owned WS receipt contracts закрыты focused tests; fresh Go integration/lint/fuzz и local `go test ./...` green. `go test -race` локально не считается выполненным без доступного CGO/GCC; current CI evidence должен быть сохранён отдельно от Go mutation diagnostic.

**Frontend files:**

- `frontend/src/pages/Messenger.tsx`
- `frontend/src/components/messenger/`
- `frontend/src/hooks/features/useMessengerController.ts`
- `frontend/src/hooks/useChatWebSocket.ts`
- messenger API/hooks

**Go files:**

- `services/ws-hub/`
- shared auth/signature packages under `services/pkg/`

**Checklist:**

- [ ] Desktop: dialogs + active chat + context panel.
- [ ] Mobile: sequential navigation and correct Back behavior.
- [ ] Clear unread, typing, sent, delivered, read, edited, reply and attachment states.
- [ ] Virtualizer keys/measurements stable.
- [ ] History prepend preserves anchor.
- [ ] Auto-scroll only when user near end.
- [ ] Reconnect/backoff and online/offline banner.
- [ ] REST hydration and WebSocket events deduplicated.
- [ ] `role="log"` and `aria-live="polite"`.
- [ ] Keyboard composer and accessible attachments/reactions.
- [ ] Group, DM, edit/delete, reply, forward, reactions, receipts, files.
- [ ] Oversized frames and permission failures fail safely.
- [ ] Hub goroutines/listeners cleaned.
- [ ] Race/load tests and latency evidence.

### 17.1 `MSG-CONTRACT-01`: единый message-length contract

**Files:** `app/core/config/storage.py`, `app/models/chat.py`, `app/api/chat.py`, `app/schemas/chat.py`, `frontend/src/api/schemas/wsMessage.ts`, generated OpenAPI/client artifacts и owning tests.

- [ ] RED: доказать boundary mismatch для 2 000, 2 001, 10 000 и 32 768 characters во входе, persistence, response DTO, edit и WebSocket.
- [ ] Зафиксировать один канонический предел. Предпочтение текущей совместимости — 32 768, поскольку DB/edit/WS уже допускают его; до изменения проверить abuse/frame/memory budget.
- [ ] Хранить backend constant в одном owning module; Pydantic/OpenAPI/frontend generated contract получают то же значение без ручного drift.
- [ ] Проверить legacy rows длиной 2 001–32 768: list/detail/edit не должны падать на response validation.
- [ ] Проверить `limit-1`, `limit`, `limit+1`, Unicode code points/bytes и oversized WebSocket frame.
- [ ] Если выбран меньший предел, сначала определить data remediation; silent truncation запрещён.

### 17.2 `MSG-AUTHZ-01`: capability-driven destructive actions

- [ ] RED: student/staff participant не видит Clear/Delete Chat; admin видит; прямой non-admin API call остаётся 403.
- [ ] Вычислять UI capability из канонической роли/permissions, а не только скрывать кнопку CSS.
- [ ] Заменить `ChatArea.test.tsx`, который закрепляет текущее неверное поведение.
- [ ] Проверить keyboard/screen-reader menu и stale-role/cache transition.

### 17.3 `MSG-A11Y-01`: 44×44 touch targets

- [ ] Инвентаризировать 28px/36px controls в `ChatWindow.tsx` и отделить visual glyph от interactive hit area.
- [ ] RED visual/DOM test измеряет minimum hitbox 44×44 на 360×800 и 390×844.
- [ ] Исправить hit areas без изменения message measurement, scroll anchoring и composer height.
- [ ] Проверить keyboard focus, pointer overlap, safe area и 200% zoom.

### 17.4 `WS-CONTRACT-01`: актуальный event/receipt surface

- [ ] Сравнить backend/ws-hub/frontend event catalog: created/edited/deleted/reaction/checkpoint/read/typing.
- [ ] Определить единственный owning read-receipt path. Если REST является каноническим, удалить dead `sendRead`; иначе добавить ws-hub handler и end-to-end contract.
- [ ] Обновить `tests/contracts/test_ws_message_contract.py`, чтобы он проверял generated/current catalog, а не старые Python dispatchers.
- [ ] Contract test reject unknown direction/type и проверяет backward-compatible payload fields.

**Verification:**

    cd services/ws-hub
    go test -race ./...
    golangci-lint run
    cd ../../frontend
    npm run test -- src/components/messenger
    npm run test -- src/hooks/__tests__/useChatWebSocket.test.tsx
    npm run typecheck

**Acceptance:** no loss/order error/duplicates/scroll jumps/leaks; ws-hub passes race/security/load gates.

---

## 18. Task 12 — Profile, Settings, Activity и i18n

**Статус аудита:** profile/settings/activity/i18n — `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Local typecheck и AST static/dynamic/raw-key scanner/RU/EN parity (2096/68 references, 18/18 parity) green; current full frontend matrix и SHA-bound manifest pending.

**Files:**

- `frontend/src/pages/Profile.tsx`
- `frontend/src/components/profile/`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/pages/settings/`
- `frontend/src/pages/Activity.tsx`
- activity components/hooks
- `frontend/src/i18n/`
- backend localized notification/email templates

**Profile:**

- [ ] Gap audit Header, Details, Editor, Achievements, NowPlaying.
- [ ] Stable query cache keys.
- [ ] Local preview state.
- [ ] Memoize only measured heavy sections.
- [ ] Avatar/cover upload cleanup.
- [ ] Error rollback and user feedback.

**Settings:**

- [ ] IA: General, Profile, Security, Notifications, Sessions, Integrations.
- [ ] Save/validation/rollback/error for every setting.
- [ ] Email MFA included, WebAuthn absent.
- [ ] Responsive navigation preserves dirty state.
- [ ] Sessions accordion accessible and deterministic.

**Activity:**

- [ ] Reuse heatmap, trends, grades, participation, attendance, timeline.
- [ ] Remove duplicate visual noise.
- [ ] One period state feeds all widgets.
- [ ] Hidden tabular alternatives for charts.
- [ ] Empty/partial/error data.

**i18n:**

- [ ] RU/EN key parity.
- [ ] No raw keys.
- [ ] Interpolation/plural/date/number tests.
- [ ] Backend email/notification templates localized.
- [ ] Static and dynamic key scanner.
- [ ] Browser language switching persists without hydration mismatch.

### 18.1 `I18N-GATE-01`: repository-wide key/raw-text scanner

- [ ] RED fixtures: missing static key, computed/dynamic key без typed registry, raw user-facing literal, broken interpolation, plural и locale formatting.
- [ ] Реализовать AST-aware scan production frontend source; не сканировать tests/generated/vendor как product strings, но проверять их отдельным scope contract.
- [ ] Dynamic keys регистрировать типизированным исчерпывающим mapping, а не blanket allowlist.
- [ ] Сопоставить каждый referenced key с RU и EN; reject orphaned/raw keys и placeholder mismatch.
- [ ] Проверить `Intl` date/number/plural behavior и localized backend email/notification templates.
- [ ] Включить scanner в `npm run i18n:check`, qualification и final quality aggregate.

**Acceptance:** all three roles complete profile/settings/activity in RU/EN; parity and raw-key gates green.

---

## 19. Task 13 — единая notification system

**Статус аудита:** `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`. Канонические topics, Web Push delivery/retry и security defenses реализованы; admin test/broadcast paths используют canonical post-delivery result cleanup, а endpoint-bound stale-result regression tests покрывают 404/410 и late success. Current full backend/notification evidence pending.

**Canonical topics:**

- `news.published`
- `schedule.changed`
- `events.published`
- `chat.message.created`
- `system.release`

**Backend scope:**

- notification schemas/models/repositories/services/routers;
- outbox worker;
- Web Push service;
- quiet hours/topic preferences;
- dead-letter and cleanup paths.

**Frontend scope:**

- notification center/bell;
- live updates;
- service worker;
- push preferences;
- permission prompt;
- deep links.

**Checklist:**

- [ ] One canonical notification ID and metadata contract per event.
- [ ] In-app/live/Web Push dedupe by ID.
- [ ] Unread count converges after reconnect.
- [ ] Topic opt-in, quiet hours and permission state consistent.
- [ ] No permission prompt on first render.
- [ ] Prompt only after clear user action.
- [ ] Handle default/granted/denied/unsupported.
- [ ] Denial not repeatedly prompted.
- [ ] Deep links open correct context.
- [ ] Offline delivery/reconnect.
- [ ] Stale/invalid subscriptions cleaned.
- [ ] Admin publication flows.
- [ ] Email remains MFA channel, not general notification channel.

### 19.1 `PUSH-CLEANUP-01`: canonical post-delivery processing

**Files:** `app/routers/notifications.py`, `app/services/webpush.py`, `app/services/notifications/delivery.py` и admin Web Push tests.

- [ ] RED: admin test/broadcast с 404/410 оставляет stale row; success не обновляет `last_seen_at`.
- [ ] Вынести единый orchestration method `deliver + process results`, используемый обычным delivery, admin test и broadcast.
- [ ] 404/410 атомарно удаляют/деактивируют subscription по действующей policy; success обновляет `last_seen_at`; transient failure сохраняет subscription для bounded retry.
- [ ] Проверить partial batch, duplicate result, concurrent broadcast/cleanup и idempotent retry.
- [ ] Не логировать endpoint/auth secret/PII; metrics используют только агрегированные статусы.
- [ ] Проверить transaction boundary: failure post-processing не должен ложно маркировать notification delivered.

**Acceptance:** five categories deliver exactly once and open correct context; denied/unsupported never break UI.

---

## 20. Task 14 — полное quality closure

**Статус аудита:** `OPEN-QUALITY`. Несколько producer/shard групп fresh-green, но canonical Coverage & Quality Policy Gate upstream-skipped, обе required mutation системы красные, ws-hub report не загружен и final manifest отсутствует. Ни одна partial success не заменяет aggregate.

### 20.1 Python

**Commands:**

    uv sync --frozen --group dev
    uv run ruff check app tests scripts
    uv run ruff format --check app tests scripts
    uv run mypy --config-file pyproject.toml app
    uv run python scripts/custom_ast_linter.py app
    uv run python scripts/check_no_python2_except.py
    uv run pytest --cov=app --cov-branch --cov-report=xml:coverage.xml --cov-report=json:artifacts/coverage/python/coverage.json

**Requirements:**

- [ ] Fresh lines/statements/branches 100%.
- [ ] Python functions обозначены `N/A (unsupported by contracted producer)`, floor 0; если producer начинает реально измерять их, результат обязан быть 100%.
- [ ] Tier-0 applicable metrics 100%.
- [ ] Complete mutmut universe.
- [ ] Zero survived, timeout, no-test, suspicious, skipped или unclassified.
- [ ] Manifest source roots exactly match contract.

### 20.2 Frontend

**Commands:**

    cd frontend
    npm ci
    npm run typecheck
    npm run lint
    npm run lint:all
    npm run i18n:check
    npm run test:wasm
    npm run test:ci
    npm run build
    npm run test:e2e
    npm run test:e2e:coverage-tool
    npm run test:mutation
    npm run test:mutation:verify

**Requirements:**

- [ ] Merged statements/branches/functions/lines 100%.
- [ ] Whole declared production scope in Stryker inventory.
- [ ] 100% viable mutants.
- [ ] SSR/hydration, a11y, visual and browser matrix.
- [ ] Bundle/CWV budgets.

### 20.3 Go

For:

- `services/gateway`
- `services/ws-hub`
- `services/file-processor`
- `services/cmd/uni-cli`
- `services/pkg/spiffe`
- `services/pkg/spicedb`

**Requirements:**

- [ ] gofmt.
- [ ] go vet.
- [ ] golangci-lint.
- [ ] `go test -race`.
- [ ] 100% statements.
- [ ] Unsupported lines/branches/functions explicitly `N/A`.
- [ ] Security behavior tests for SpiceDB/SPIFFE/JWT/HMAC/path traversal/frame limits.

### 20.4 Rust

For:

- `native/rust_ext`
- `crates/pyo3-sanitizer`
- `frontend/wasm-sanitizer`
- `frontend/rust-crypto`

**Requirements:**

- [ ] cargo fmt/clippy.
- [ ] all-target tests.
- [ ] cargo-llvm-cov line/function/branch.
- [ ] Rust statements обозначены `N/A (unsupported by contracted producer)`, floor 0; lines/functions/branches остаются 100%.
- [ ] Zero-branch derivation only after source inventory proves denominator zero.
- [ ] cargo deny.
- [ ] Bounded fuzz smoke.
- [ ] Current paths and SHA in every report.

### 20.5 API/contracts

**Current evidence:** предыдущий четырёхшардовый Schemathesis run/aggregate, OpenAPI/Spectral/backward compatibility, TypeScript/MSW/GraphQL drift и Pact boundaries зелёные на tested merge SHA. Workflow теперь закрепляет восемь shards для сокращения per-job lifecycle overhead; требуется final-SHA rerun всех восьми и aggregate.

- [ ] Eight Schemathesis shards.
- [ ] Aggregate rejects missing/cancelled shard.
- [ ] OpenAPI generated deterministically.
- [ ] TypeScript SDK drift zero.
- [ ] MSW mocks drift zero.
- [ ] Pact and snapshots current.
- [ ] GraphQL schema drift zero.

### 20.6 Security/supply chain

**Current evidence:** отдельные CodeQL, Zizmor, Checkov, Gitleaks, TruffleHog, dependency/container/SBOM workflows были зелёными на historical/current associated runs; detect-secrets findings устранены в code/docs и baseline reviewed. Current full security aggregate и final-SHA reports остаются pending до terminal Matrix.

- [ ] Full pre-commit.
- [ ] detect-secrets.
- [ ] gitleaks.
- [ ] TruffleHog.
- [ ] Bandit.
- [ ] Semgrep.
- [ ] CodeQL.
- [ ] Zizmor.
- [ ] actionlint.
- [ ] Checkov.
- [ ] dependency audits.
- [ ] Trivy.
- [ ] SBOM.
- [ ] provenance.
- [ ] No untriaged high/critical.

### 20.7 Infrastructure

- [ ] All Compose config matrices.
- [ ] Helm lint/template.
- [ ] envsubst for required variables.
- [ ] Kyverno image policy.
- [ ] ExternalSecrets.
- [ ] TLS.
- [ ] HPA/resources.
- [ ] Caddy routing and headers.

### 20.8 Harness/docs

- [ ] `python verify_harness.py --repo-only`.
- [ ] Exact passing count recorded; не хардкодить старые 29, если suite вырос.
- [ ] One active continuation roadmap.
- [ ] Archive only after reference scan.
- [ ] Markdown links and JSON/YAML valid.

### 20.9 Quality manifest

**Files:**

- `scripts/quality/normalize_coverage_reports.py`
- `scripts/quality/validate_quality_contract.py`
- `quality/coverage-manifest.schema.json`
- `quality/quality-contract.json`

**Must contain:**

- schema v3 fields `source_head_sha`, `tested_commit_sha`, `base_sha` и `base_ref` с однозначной семантикой;
- для PR: `source_head_sha=<event.pull_request.head.sha>`, `tested_commit_sha=<tested merge SHA>`; merge SHA запрещено называть source/head. Значения `e0989e29...` и `3e4d8f89...` из historical baseline не являются шаблоном current manifest;
- для push/main: source и tested commit могут совпадать, но оба поля остаются явными;
- workflow run ID/attempt;
- source roots;
- tool versions;
- report hashes;
- timestamp;
- workflow provenance;
- applicable metrics and explicit `N/A`;
- no missing reports;
- `validation.valid: true`.

**Schema migration steps:**

- [ ] Одновременно обновить `coverage-manifest.schema.json`, quality contract, normalizer, validator, workflow producers, fixtures, tests и docs.
- [ ] Schema v2 artifact без новых provenance fields fail-closed отклоняется final v3 validator либо проходит только explicit diagnostic migration path, который не удовлетворяет release gate.
- [ ] Добавить tests для swapped head/merge, wrong base, wrong run attempt, artifact hash mismatch, duplicate producer и PR/push semantics.
- [ ] Не получать source head из `github.sha` на `pull_request`; использовать `github.event.pull_request.head.sha`, а tested checkout сверять с `git rev-parse HEAD`.

### 20.10 Zero-warning toolchain configuration

**Finding:** fresh Linux CI сообщает warning для `pyproject.toml` `[tool.uv] exclude-newer = "7 days"`. Local uv 0.11.28 CLI описывает friendly durations, поэтому сначала нужен exact Linux/action reproduction; warning нельзя ни игнорировать, ни исправлять предположением.

- [ ] Получить точный warning, parser/version/source step и regression fixture.
- [ ] Проверить pinned uv `0.11.28` и setup-uv config parser на Linux.
- [ ] Если friendly form не принимается в project config path, заменить на эквивалентный однозначный `P7D` и доказать тот же resolver cutoff behavior.
- [ ] Не менять lockfile вместе с syntactic fix, если dependency set не должен измениться; `uv lock --check`/`uv sync --frozen` обязаны быть warning-free.
- [ ] Классифицировать third-party action deprecation warnings отдельно; project-owned zero-warning gate не скрывает их, а pin/update action выполняется отдельным supply-chain change.

---

## 21. Task 15 — Docker resource optimization и immutable smoke

**Статус аудита:** launch code/resource limits существуют; runtime evidence pending. Эта задача измеряет full и existing `-Core`/`-Lean`, не проектирует новую topology заранее.

### 21.1 Safe read-only inventory

    docker context show
    docker compose ls
    docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Labels}}"
    docker stats --no-stream
    docker system df -v

- [ ] Определить project ownership по Compose labels.
- [ ] Не останавливать чужие containers.
- [ ] Не удалять volumes/images/build cache без точного ownership и необходимости.
- [ ] Сохранить before snapshot CPU, memory, disk и container count.

### 21.2 Сначала измерить существующие `-Core` / `-Lean` modes

`start-docker.ps1` уже использует `docker-compose.full.yml` как single source of truth и имеет fail-closed core allowlist. `-Lean` — alias `-Core`; он сохраняет gateway, ws-hub и Caddy, но останавливает search, file processor, Temporal и observability без удаления volumes. Новые Compose profiles не добавлять до доказанного gap: параллельная topology может дрейфовать и сломать dependency graph.

**Rules:**

- [ ] Проверить contract tests existing core allowlist, duplicates и forbidden optional overlap.
- [ ] Сравнить full default с `./start-docker.ps1 -Core`; `-Lean` отдельно не benchmark, потому что это alias.
- [ ] Security-state `revocation-redis` остаётся отдельным от cache/rate-limit Redis.
- [ ] Gateway/ws-hub/Caddy остаются в core, потому что frontend/runtime routes зависят от них.
- [ ] File-processor journey выполняется только full profile либо явным audited extension, а не считается core success.
- [ ] Observability stack называется Prometheus/Grafana/Tempo/Loki/**Alloy**/Pyroscope; устаревший Fluent Bit не использовать в local Compose plan.
- [ ] Существующие CPU/memory/PID/log rotation/healthcheck limits проверить машинно для каждого declared service; новые лимиты добавлять только при измеренном пробеле.
- [ ] BuildKit cache не дублирует giant layers; no orphan containers.
- [ ] `start-docker.ps1` выводит выбранный mode, включённые/исключённые services и estimated resource class.

### 21.3 Resource measurements

- [ ] Idle 10 minutes.
- [ ] Auth/login workload.
- [ ] Map workload.
- [ ] Messenger workload.
- [ ] Full smoke.
- [ ] Record per-container CPU/memory, disk I/O, network, restart count.
- [ ] Compare `-Core` vs full.
- [ ] Define budgets from measured host capacity; не скрывать OOM через unlimited swap.

### 21.4 Compose validation

Проверить:

- `docker-compose.yml`
- `docker-compose.go.yml`
- `docker-compose.infra.yml`
- `docker-compose.observability.yml`
- `docker-compose.full.yml`
- `docker-compose.test.yml`
- `docker-compose.prod.yml`
- `docker-compose.sandbox.yml`
- `docker-compose.ci-loadtest.yml`

### 21.5 Immutable smoke

- [ ] Build exact commit.
- [ ] Record image digests.
- [ ] Backend `/health/ready`.
- [ ] Frontend SSR.
- [ ] Caddy.
- [ ] gRPC file processor health.
- [ ] WebSocket.
- [ ] PostgreSQL.
- [ ] Redis separation.
- [ ] NATS.
- [ ] Prometheus/Grafana/Tempo/Loki where profile requires.
- [ ] Run auth + MFA, dashboard/content/map, chat, profile/settings/activity, push и admin publication.
- [ ] Stop only project-owned stack.
- [ ] Verify no orphan resources or tracked generated secrets.

**Acceptance:** existing `-Core` materially reduces idle resources без нарушения core routes/security isolation; full stack остаётся функциональным; immutable smoke проходит по digest. Новый profile допустим только если измеренный gap невозможно закрыть existing allowlist.

---

## 22. Task 16 — staging Kubernetes и release

**Статус аудита:** validators/workflows `CODE-COMPLETE`, но canonical main producer, registry attestations, immutable Docker smoke, staging и production evidence — `EXTERNAL-ONLY`. Выполненность кода не означает выполненность релиза.

### 22.1 Canonical images

**Files:**

- `.github/workflows/build-release-images.yml`
- `.github/workflows/reusable-build-and-sign.yml`
- `scripts/quality/publish_immutable_image.py`
- `scripts/quality/aggregate_release_image_evidence.py`
- `scripts/quality/verify_release_image_manifest.py`

**Checklist:**

- [ ] Exactly six required runtime images from one canonical main-only producer: `backend`, `frontend`, `ws-hub`, `gateway`, `file-processor`, `caddy`.
- [ ] Every image pinned by immutable digest.
- [ ] SBOM and provenance attached.
- [ ] Manifest binds source SHA, workflow SHA, run ID/attempt and digests.
- [ ] No manual substitute artifact.
- [ ] Не смешивать понятия promotion и deployment: либо staging реально deploy/health-check Caddy, либо manifest явно хранит `promoted_images=6` и `deployed_images=5`; six-image producer при этом остаётся полным.

### 22.2 Staging

- [ ] Deploy the same digests.
- [ ] TLS: chain, hostname, expiry, protocol/cipher policy и HSTS, а не только HTTP 200.
- [ ] ExternalSecrets: Ready condition, refresh age и secret rollout без вывода values.
- [ ] Kyverno policies enforced.
- [ ] HPA/resources active.
- [ ] Readiness/liveness correct.
- [ ] Observability: Prometheus targets/rules/alerts, Grafana datasource, Loki ingestion/redaction, Tempo cross-service trace и alert delivery end-to-end.
- [ ] Logs redact PII/secrets на backend, gateway, ws-hub, Caddy и workers.
- [ ] Traces correlate across Caddy/gateway/backend/ws-hub/file processor.
- [ ] CWV field certification: p75 LCP ≤2 500 ms, INP ≤200 ms, CLS ≤0.1 для mobile и desktop; ≥100 observations на metric/device, ≥20 на обязательную route group, ≥25 sessions и collectors/device; окно ≥24h, ≥6 active hours/device, evidence age ≤72h.
- [ ] HPA scale-up/down, resource requests/limits и readiness under load.
- [ ] Chaos/restart.
- [ ] Rollback.

### 22.3 Cross-browser staging matrix

- latest two Chrome;
- latest two Edge;
- latest two Firefox;
- latest two Safari;
- iOS Safari;
- Android Chrome.

### 22.4 Release workflow

- [ ] Merge to `main` only after PR required checks green.
- [ ] Re-run full matrix on resulting main SHA.
- [ ] Produce canonical images from exact main SHA.
- [ ] Deploy exact digests to staging.
- [ ] Obtain field certification.
- [ ] Release workflow revalidates main SHA and all artifact attestations.
- [ ] No P0/P1 or high/critical findings.
- [ ] Rollback target and procedure tested.

**External boundary:** merge, registry signing, staging cluster, DNS/TLS, field traffic and production release cannot be declared complete from local repository evidence alone.

---

## 23. Сквозная acceptance matrix

### Roles

- [ ] student;
- [ ] staff/teacher;
- [ ] admin.

### Languages

- [ ] Russian;
- [ ] English.

### Viewports

- [ ] 360×800;
- [ ] 390×844;
- [ ] 768×1024;
- [ ] 1024×768;
- [ ] 1440×900.

### States

- [ ] loading;
- [ ] empty;
- [ ] partial;
- [ ] success;
- [ ] validation error;
- [ ] 401;
- [ ] 403;
- [ ] 404;
- [ ] 409;
- [ ] 422;
- [ ] 429;
- [ ] 5xx;
- [ ] offline;
- [ ] reconnect;
- [ ] timeout.

### Accessibility

- [ ] keyboard only;
- [ ] focus order/trap/restore;
- [ ] zoom 200%;
- [ ] reduced motion;
- [ ] contrast;
- [ ] axe;
- [ ] screen-reader smoke;
- [ ] accessible authentication;
- [ ] touch targets.

### Performance

- [ ] cold/warm navigation;
- [ ] slow network/CPU;
- [ ] repeated animation;
- [ ] large chat history;
- [ ] large map/data sets;
- [ ] memory plateau;
- [ ] CWV.

### Reliability

- [ ] duplicate events;
- [ ] retries;
- [ ] idempotency;
- [ ] concurrent mutation;
- [ ] service restart;
- [ ] stale cache;
- [ ] failed dependency;
- [ ] artifact retry/duplicate selection.

### Security

- [ ] CSRF;
- [ ] open redirect;
- [ ] XSS sanitization;
- [ ] session fixation/revocation;
- [ ] MFA replay/race;
- [ ] path traversal;
- [ ] oversized WebSocket/file inputs;
- [ ] secret/PII leakage;
- [ ] workflow dispatch trust boundary;
- [ ] cache poisoning;
- [ ] artifact provenance.

### Visual

- [ ] auth;
- [ ] shell;
- [ ] dashboard;
- [ ] news;
- [ ] events;
- [ ] map;
- [ ] messenger;
- [ ] profile;
- [ ] settings;
- [ ] activity;
- [ ] notification center;
- [ ] admin.

---

## 24. Commit, push и CI cadence

### 24.1 Small coherent commits

Рекомендуемая первая серия:

1. `fix(ci): serialize WASM target installation`
2. `fix(security): remove credential-like deployment examples`
3. `fix(tooling): make uv cutoff configuration warning-free`
4. `fix(quality): distinguish source and tested commit provenance`
5. `fix(messenger): unify message length contract`
6. `fix(messenger): enforce destructive action capabilities`
7. `fix(frontend): restore messenger touch target minimums`
8. `fix(notifications): process admin push delivery results`
9. `feat(i18n): enforce referenced and raw key contracts`
10. `fix(testing): align Stryker preflight and runtime inventory`
11. focused Stryker survivor-closure commits по owning domain, без waves
12. `fix(testing): isolate mutation workers from telemetry forks`
13. focused mutmut survivor-closure commits по owning domain, без waves
14. `fix(ci): gate mutation fan-out on core readiness`
15. `perf(ci): balance mutation lanes by measured duration`
16. `docs: record audited source SHA and external remainder`

Не объединять product defects, runner correctness и CI performance в один commit: каждый должен иметь самостоятельный RED/GREEN evidence и безопасный revert boundary.

### 24.2 Перед каждым commit

    git status --short
    git diff --check
    git diff --staged

- [ ] Focused tests.
- [ ] Domain regression.
- [ ] No unexpected generated/cached files.
- [ ] No Co-Authored-By.
- [ ] `.secrets.baseline` re-staged after detect-secrets.

### 24.3 Push policy

- [ ] Push только coherent verified batch.
- [ ] Не push каждый эксперимент: это создаёт дорогие superseded runs.
- [ ] Перед push проверить, что previous run inventory уже сохранён либо он явно superseded.
- [ ] После push записать new head SHA и run IDs.
- [ ] Не force-push.
- [ ] Не merge PR.

---

## 25. Safe pause/resume protocol

### Pause

- [ ] Остановить только собственные foreground test processes.
- [ ] Не удалять artifacts, worktrees или containers без ownership check.
- [ ] Выполнить `git status --short --branch`.
- [ ] Выполнить `git diff --check`.
- [ ] Сохранить exact running CI state и active commands.
- [ ] Если изменения verified и пользователь потребовал checkpoint, сделать coherent commit и push.
- [ ] Если изменения не verified, оставить их unstaged с точным handoff.
- [ ] Не помечать goal complete.

### Resume

- [ ] Перечитать root/domain AGENTS и quality contract.
- [ ] Сравнить current HEAD с last checkpoint.
- [ ] Проверить PR head и новые CI runs.
- [ ] Не повторять уже завершённую работу без evidence of regression.
- [ ] Возобновить с первого незакрытого checkbox критического пути.

---

## 26. Risk register

| Риск | Severity | Mitigation | Release block |
|---|---|---|---|
| Rustup race повторяется в другом workflow | High | repository-wide search, serial target preinstall contract | Да |
| detect-secrets baseline скрывает real secret | Critical | per-finding classification и narrow diff review | Да |
| Mutation jobs съедают 20 slots до core failure | High | stack readiness dependencies и lane budgets | Да |
| Shard batching создаёт timeout/false incomplete evidence | High | p99 cost proof и exact inventory | Да |
| PR merge SHA путается с source head SHA | High | manifest хранит оба и явно выбирает source revision | Да |
| Artifact от другого attempt принят aggregate | Critical | exact run/attempt/name/hash validation | Да |
| Release dispatch input исполняет untrusted code | Critical | trusted event/main checkout и equality checks | Да |
| WebAuthn остался в runtime/generated contract | High | allowlisted tombstone-only repository scan | Да |
| Email OTP plaintext попадает в telemetry | Critical | log/trace tests и HMAC at rest | Да |
| Migration блокирует/теряет legacy accounts | Critical | preflight, remediation, PostgreSQL fixtures | Да |
| E2E retry скрывает app error | High | transient-error allowlist и negative tests | Да |
| Несогласованный chat length принимает данные, которые response DTO не сериализует | High | один generated boundary contract + legacy-row tests | Да |
| Destructive chat actions видимы не-admin | Medium | capability-driven UI + backend 403 tests | Да для vertical closure |
| Admin Web Push не очищает 404/410 subscriptions | Medium | canonical deliver/process orchestration + idempotency tests | Да для vertical closure |
| i18n parity зелёный, но raw/missing dynamic keys не сканируются | Medium | AST-aware static/dynamic/raw-key gate | Да для vertical closure |
| Docker resource optimization объединяет security Redis | Critical | topology contract запрещает объединение | Да |
| Local 100% не соответствует CI source roots | High | contract-owned roots и SHA-bound manifest | Да |
| `exclude-newer` warning делает zero-warning claim ложным | Medium | exact Linux reproduction и supported equivalent syntax | Да для quality closure |
| Audit commit меняет SHA после сертификации | High | audited source X и optional audit-only commit Y имеют разные явные identities | Да |
| External staging недоступен | High | код закрыть, статус `external-only`, completion не заявлять | Да для release |

---

## 27. Финальный SHA-bound audit без SHA-парадокса

Канонический audit сначала создаётся как immutable workflow artifact, подписанный и attestированный к проверенному source/main SHA `X`. Опциональный repository document называется `docs/audits/AUDIT_QUALITY_CLOSURE_<X>.md`, но его commit `Y` является audit-only commit и не может называться проверенным release SHA без отдельной повторной матрицы.

Обязательные identity fields:

- `audited_source_sha: X`;
- `tested_commit_sha`/tested merge SHA;
- `audit_artifact_sha256` и provenance run;
- `audit_commit_sha: Y | null`;
- `release_image_source_sha: X`;
- явное утверждение, что `Y` не меняет runtime artifacts, если документ зеркалируется в repo.

Документ обязан содержать:

- branch, source SHA, merge/main SHA;
- PR и workflow run IDs/attempts;
- toolchain/runner versions;
- commands, exit codes и durations;
- test counts;
- line/statement/branch/function coverage per component;
- applicable/unsupported metric semantics;
- mutation universe size и result totals;
- report paths, hashes и timestamps;
- skipped/cancelled job reasons;
- security findings/disposition;
- SBOM/provenance/attestations;
- exact image digests;
- Docker health/resource measurements;
- staging endpoints without secrets;
- CWV/a11y/browser results;
- chaos/rollback evidence;
- remaining external-only work;
- explicit P0/P1/high/critical count;
- clean-worktree proof.

Фразы `complete`, `green`, `100%`, `безупречно` и `готово к релизу` допустимы только рядом с воспроизводимым fresh evidence. Коммит audit-документа никогда не ретроспективно меняет identity уже протестированного `X`.

---

## 28. Definition of Done

### Code and product

- [ ] Все master-plan verticals реализованы или gap-audited с доказательством отсутствия gap.
- [ ] TOTP, email OTP и recovery complete; WebAuthn отсутствует в runtime.
- [ ] RU/EN parity.
- [ ] Static/dynamic/raw-key i18n scanner green.
- [ ] Student/staff/admin journeys.
- [ ] Messenger length/authorization/touch-target/WS contract gaps closed.
- [ ] Admin Web Push cleanup/result processing closed.
- [ ] Responsive/PWA scope.
- [ ] WCAG 2.2 AA.
- [ ] Performance budgets.
- [ ] No P0/P1/data-loss/high/critical findings.

### CI and quality

- [ ] Fresh PR run terminal и required matrix green.
- [ ] No unexplained skip/cancel/timeout.
- [ ] Python applicable metrics 100%.
- [ ] Frontend four metrics 100%.
- [ ] Go native statements 100%.
- [ ] Rust line/function/branch 100%.
- [ ] Tier-0 semantics correct.
- [ ] mutmut 100% viable.
- [ ] Stryker 100% viable.
- [ ] Security/supply-chain gates green.
- [ ] Harness green.
- [ ] Current-SHA manifest valid.
- [ ] CI performance improvement proven across comparable runs.

### Docker and staging

- [ ] All Compose configs valid.
- [ ] Existing `-Core` and full resource modes measured.
- [ ] Immutable digest Docker smoke.
- [ ] Same digests on staging.
- [ ] TLS/observability/CWV/browser/chaos/rollback.

### Release and repository

- [ ] Final changes committed on `egorribun`.
- [ ] PR points to final verified SHA.
- [ ] Merge to main completed only after approval/gates.
- [ ] Main SHA reverified.
- [ ] Exact-six images built and attestations verified.
- [ ] Final audit artifact signed for audited source SHA; optional audit-only commit has separate SHA identity.
- [ ] Worktree clean.
- [ ] Untracked user files preserved.

---

## 29. External-only remainder after repository closure

Даже после полностью зелёного PR следующие пункты остаются отдельными обязательными действиями:

1. merge `egorribun` в `main`;
2. fresh full matrix на resulting main SHA;
3. canonical exact-six image producer;
4. registry signing/attestation verification;
5. immutable-digest Docker smoke;
6. production-like Kubernetes staging;
7. DNS/TLS/ExternalSecrets;
8. observability and alert validation;
9. field CWV certification;
10. real cross-device Safari/iOS/Android evidence;
11. chaos and rollback;
12. production release;
13. post-release monitoring and rollback window.

Отсутствие доступа к любому из этих внешних ресурсов не позволяет пометить весь master goal complete; в audit это обозначается как blocking `external-only`, а не как допустимый skip.

---

## 30. Самопроверка этого плана перед исполнением

- [ ] Все исходные master-plan этапы 0–10 отображены в задачах 6–22.
- [ ] Все пункты historical `prompt.md` отображены в Task 4.
- [ ] Все fresh failures latest terminal run отображены в Tasks 2–5 и CI inventory; historical run `33349026009` и pending current run `33543238962` не смешиваются, aggregates не посчитаны как отдельные roots.
- [ ] Все найденные product gaps отображены в Tasks 11–13 с RED/GREEN acceptance.
- [ ] CI speed/reliability под 20-job cap имеет отдельный измеримый workstream.
- [ ] Docker resource optimization не нарушает security topology.
- [ ] Read-only subagent audit scopes и future implementation ownership описаны; edits остаются у интегратора.
- [ ] Нет placeholders или неограниченных формулировок без acceptance.
- [ ] Unsupported metrics не названы измеренными.
- [ ] Python denominator равен exact universe artifact (current: 5 341), а не приблизительной оценке.
- [ ] Source head и tested merge SHA нигде не смешаны.
- [ ] External-only work не выдан за завершённое.
- [ ] Final completion требует clean current-SHA evidence после последнего commit.

---

## 31. Resumption execution ledger (2026-08-31)

Этот раздел добавлен во время фактического продолжения работ и намеренно отделён
от исторического baseline выше. Он фиксирует только наблюдаемое состояние текущего
рабочего дерева; ни один локальный targeted-run не считается заменой полного
current-SHA CI или внешнего release evidence.

### 31.1 Identity и сохранность рабочей области (historical ledger; superseded by §32)

- Рабочая ветка: `egorribun`.
- Локальный и remote checkpoint до следующего push: `e0989e29cfca88ee9a650eb264d6fa7674031c9a`.
- PR #1257 и run `33349026009`, описанные в baseline, являются историческим
  snapshot; после push любого нового коммита их нельзя выдавать за fresh result.
- Пользовательские stash entries не изменяются. Перед staging требуется повторный
  `git status --short` и явная инвентаризация всех untracked paths.
- В `docs/superpowers/` обнаружены только четыре ожидаемых плана; staging
  разрешён только по явным путям, перечисленным в разделе 1.1.

### 31.2 Подтверждённые изменения и локальные evidence (historical pre-commit ledger)

Ниже перечислены изменения, для которых уже получен focused evidence; итоговый
commit и fresh CI ещё не созданы:

1. **Coverage provenance v3.** Schema, normalizer, validator и regression tests
   разделяют `source_head_sha`, `tested_commit_sha`, `base_sha/base_ref`, run
   identity, report hashes и timestamps; stale/empty/partial identity проверяется
   fail-closed.
2. **CI scheduling.** Stryker и mutmut получили qualification barriers и
   `max-parallel: 8`, оставляя четыре слота до общего лимита 20; coverage и
   security gates не ослаблены. Frontend qualification намеренно не сериализован
   через pre-commit, как требует workflow contract.
3. **WASM setup.** Установка `wasm32-unknown-unknown` выполняется отдельным
   последовательным шагом до parallel `wasm-pack` builds.
4. **Messenger/WebSocket.** Канонический лимит сообщения 32 768 code points,
   Valibot/OpenAPI/HTTP/legacy-WS guards, admin authorization, доступные hit-targets,
   REST-канонический read receipt, обновлённые message contracts и regression
   tests. Некорректные Web Push provider statuses нормализуются в `error` без
   `TypeError`; добавлен regression test.
5. **Web Push.** Cleanup/result processing использует keyset pagination,
   deterministic coalescing и bounded provider-result handling.
6. **RU/EN i18n.** Добавлены AST/static+dynamic scanner, typed registry и
   `i18n:check`; последнее локальное evidence: 1 872 static references,
   58 dynamic references, parity 18/18, scanner tests 8/8.
7. **Secrets hygiene.** Credential-like deployment examples переписаны
   безопасно, deterministic digest fixture разбит на scanner-safe части,
   baseline обновлена после проверки findings. После любого последующего
   detect-secrets запуска `.secrets.baseline` необходимо проверить и заново
   stage.
8. **Go mutation governance.** Контрактная работа отделяет advisory bounded
   mutation diagnostic от contract-owned coverage/race job; окончательная
   security-проверка provenance, per-shard outcomes, failure finalization и
   collision-resistant shard paths выполняется перед staging.

Последние локальные результаты до следующего изменения файлов:

- Python manifest/provenance suite: `140 passed` (`tests/test_coverage_manifest.py`);
- combined quality/provenance/chat/push suite: `85 passed`;
- workflow/mutation governance contracts: `32 passed` до финального follow-up;
- Docker resource/startup/image contracts: `130 passed`;
- mutation contracts: `105 passed`;
- backend strict mypy: `349 files`, success;
- Ruff check и format check: success (`1164 files` format check);
- frontend typecheck, lint/lint:all, format check и build: success;
- frontend i18n scanner tests: `8 passed`;
- WASM suite: `182 passed`;
- frontend messenger/WebSocket suite: `360 passed`;
- Go ws-hub `go test ./...` и `gofmt`: success;
- targeted E2E Chromium checks for sessions/recovery/offline: `1/1` each;
- `git diff --check`: success.

Локальные environment-only ограничения, которые нельзя маскировать исправлением
продукта: два lifecycle и четырнадцать notification API fixture тестов требуют
`REVOCATION_REDIS_URL`; `go test -race` на Windows требует доступного CGO/GCC.
Это не является evidence зелёного full gate и должно быть перепроверено на CI.

### 31.3 CI critical-path и Docker observations (historical fixture/run)

- Добавлен детерминированный `scripts/quality/analyze_ci_critical_path.py` с
  fixture и пятью regression tests; fixture run `33349026009` обработан с
  concurrency cap 20. Generated JSON остаётся runtime artifact и не stage-ится.
- Docker read-only inventory показал `docker context desktop-linux`, отсутствие
  запущенных и остановленных контейнеров и только существующие images/volumes.
  Prune/remove не выполняется без явного подтверждения владельца ресурсов.
- Compose matrix (`docker-compose.yml`, `docker-compose.infra.yml`,
  `docker-compose.go.yml`, `docker-compose.ci-loadtest.yml`) прошла
  `docker compose ... config --quiet` с development-only placeholders.
  Реальный `start-docker.ps1 -Build`, immutable-digest smoke и resource
  measurements остаются отдельными gates.

### 31.4 Открытые gates после этого ledger

- Завершить и независимо проверить Go mutation-diagnostic governance; затем
  прогнать все workflow/actionlint/security contracts.
- Запустить full local harness и свежую полную PR matrix на новом SHA после
  когерентных commits; скачать все paginated job/artifact records и разобрать
  каждый terminal failure.
- Получить fresh 100% applicable coverage и 100% viable mutmut/Stryker evidence,
  current-SHA manifest/report hashes, без stale/empty/partial artifacts.
- Проверить полный browser/E2E, Lighthouse/CWV, accessibility, Rust/Go race,
  Schemathesis, security/supply-chain и infrastructure gates.
- Выполнить только при наличии внешнего доступа: merge в `main`, resulting-main
  rerun, exact-six immutable images, SBOM/provenance/attestations, Docker digest
  smoke, Kubernetes staging/TLS/ExternalSecrets/observability, real-device
  evidence, chaos/rollback и production release.

До закрытия всех пунктов 31.4 этот ledger не разрешает формулировки
«полностью завершено», «100%» или «готово к релизу».

### 31.5 Security review disposition

Независимый read-only review после Go governance follow-up зафиксировал пять
P2 hardening items. Кодовое исправление всех пяти уже находится в ancestors:
`2d7072e074cd07f82bc839038a46adbd6abd4e61` добавляет checksum-verified
actionlint/Hadolint/ShellCheck bootstrap и `persist-credentials: false`,
`de702c7b7327a842a3269827fd59a16f58008a3a` добавляет finding-level и trusted
base проверку `.secrets.baseline`, а guard для `CONFIG_SHA256` присутствует в
Go workflow. Поэтому эти записи больше не являются открытыми code defects:
их current status — `CODE-COMPLETE / FRESH-EVIDENCE-PENDING` до полного
current-SHA security aggregate.

| ID | Severity/owner | Reproduction and disposition |
|---|---|---|
| `SEC-GO-DIAG-01` | P2 / CI security owner — `CODE-COMPLETE / FRESH-EVIDENCE-PENDING` | `CONFIG_SHA256` больше не следует PR-controlled symlink: guard `git ls-files --error-unmatch` + `-f && ! -L` выполняется до чтения; workflow contract и actionlint tests pass. Требуется current-SHA workflow evidence. |
| `SEC-CI-DL-01` | P2 / CI security owner — `CODE-COMPLETE / FRESH-EVIDENCE-PENDING` | `ci.yml` actionlint bootstrap использует pinned release asset, HTTPS/TLS flags и strict SHA-256 verification; regression contract запрещает mutable `raw.githubusercontent.com/.../main`. Требуется current runner execution. |
| `SEC-CI-DL-02` | P2 / CI security owner — `CODE-COMPLETE / FRESH-EVIDENCE-PENDING` | Hadolint/ShellCheck binary downloads version- and checksum-pinned, verified before chmod/execute; regression contract проверяет ordering. Требуется current runner execution. |
| `SEC-AUDIT-DL-01` | P2 / security owner — `CODE-COMPLETE / FRESH-EVIDENCE-PENDING` | Security-audit checkouts задают `persist-credentials: false`; detect-secrets installation uses hash-locked binary-only requirements. Contract tests pass; требуется current reusable-security-audit run. |
| `SEC-BASELINE-01` | P2 / security owner — `CODE-COMPLETE / FRESH-EVIDENCE-PENDING` | `verify_secrets_baseline.py` сравнивает finding-level identity и immutable trusted-base baseline; malformed/missing/changed-hash cases fail closed. Contract suite pass; требуется current PR security aggregate. |

Эти P2 не являются P0/P1 или high/critical findings, не добавляют
exclusions/quarantines и не требуют отдельной code-hardening вертикали. Они
должны оставаться явно перечисленными в audit до получения свежего evidence;
`CODE-COMPLETE` не следует трактовать как current security aggregate green.

---

## 32. Current execution overlay (2026-09-01; authoritative)

Этот overlay является текущим источником истины для продолжения работ после
исторического baseline (§§1–31). Он не удаляет старые run/commit IDs: значения
`e0989e29cfca88ee9a650eb264d6fa7674031c9a`, `33349026009` и
`3e4d8f89e56ad2fd12e6529433aa4175f7048687` в предыдущих разделах относятся
только к superseded snapshot и не могут использоваться как current-SHA или
release evidence.

Snapshot в этом overlay снят до отдельного audit-only commit с его собственным
SHA. Поэтому поля HEAD/run в §§32.1–32.3 описывают source snapshot
`c3ee034ed`; после публикации документа следующая required matrix обязана быть
привязана к post-audit SHA, а не ретроспективно переиспользовать run
`33543238962`. Это намеренное разделение source evidence и документа аудита.

### 32.1 Identity, сохранность и commit ledger

| Поле | Наблюдаемое значение |
|---|---|
| Branch | `egorribun` |
| Local/remote HEAD | `c3ee034ed8ededa46572aaeed825fec3750b4378` (совпадают) |
| PR | `#1257`, `egorribun` → `main`, open/non-draft |
| Base SHA | `4bb85c67e30d224c276e07fa4a0bff0249787571` |
| Merge state | `BLOCKED` до fresh required checks |
| Worktree | clean; пользовательские stash/untracked files не изменены |
| `docs/superpowers/` | ровно четыре ожидаемых plan-файла tracked; массовый `git add` не выполнялся |

Последовательность изменений после старого checkpoint:

1. `db68247890e4b75ccbca3f44eadbc8d06e7b0fe1` — добавлена locked `pip-audit`
   dependency для backend CI, fail-closed исторический-duration step,
   repository-wide RU/EN i18n scanner и fallback cleanup, messenger attachment
   keyboard contract, а также восемь Schemathesis shards с тем же aggregate и
   без уменьшения example universe.
2. `78516020110c869d3a12a97ef59e6f45e510733c` — admin push test/broadcast
   orchestration закреплена через canonical delivery/result-processing path;
   cleanup/update привязаны одновременно к subscription id и observed endpoint.
3. `07cdbd0c1fcb9fb07077258b85f0ccd9decb76f1` — `ChatArea` unit suite
   изолирована от нерелевантных barrel/WASM/browser dependencies, сохраняя
   production behavior и делая shard setup детерминированным.
4. `c3ee034ed8ededa46572aaeed825fec3750b4378` — regression test для late
   stale-success push result; повторное использование row id другим endpoint не
   меняет и не удаляет актуальную subscription.

### 32.2 Local evidence (class C; не заменяет full current-SHA CI)

- `python verify_harness.py --repo-only`: `29/29`;
- frontend typecheck, lint, format/build и focused changed-component suites:
  `279` тестов passed; `npm run i18n:check`: `2 096` static + `68` dynamic
  references, RU/EN parity `18/18`;
- workflow/quality regression suites: `225` passed; последующий финальный
  workflow contract subset после fan-out изменения: `184` passed;
- backend Ruff/format, frontend typecheck/lint/Prettier и pre-commit hooks
  (включая detect-secrets, gitleaks, Semgrep и workflow lint) завершились
  успешно; `.secrets.baseline` после проверки повторно staged;
- `git diff --check` и `uv lock --check` успешны.

Эти результаты подтверждают код и локальные contracts только. Full coverage,
mutation, Go race, browser/Lighthouse, complete report provenance, Docker и
staging по-прежнему требуют свежего workflow evidence.

### 32.3 Fresh CI snapshot (получен 2026-09-01T21:29:13+03:00)

Основной exact-SHA matrix run:
[33543238962](https://github.com/egorribun/university_ecosystem/actions/runs/33543238962),
head `c3ee034ed8ededa46572aaeed825fec3750b4378`, created
`2026-09-01T18:22:25Z`, API status `queued`.

На момент снимка paginated Jobs API материализовал `92` jobs:

| Состояние | Количество |
|---|---:|
| success | 22 |
| skipped | 10 |
| in progress | 14 |
| queued | 46 |
| terminal failure/cancel/timeout | 0 |

Связанные workflow runs того же head SHA: `25` total — `17` success,
`2` skipped (Chromatic и Dependabot auto-merge guards), `5` in progress и
`1` queued (основной Matrix). Ни один из этих snapshots не является финальным
green claim, пока Matrix и required artifacts не достигли terminal state.

Current run IDs, которые должны войти в итоговый artifact ledger:

- Matrix `33543238962`;
- CodeQL `33543238046`;
- Continuous Performance `33543238244`;
- Contract Tests `33543238074` и Contract Validation `33543238260`;
- Go Fuzz `33543238410`, Go Lint/SBOM `33543238093`;
- Python Fuzz `33543238242`, Rust Fuzz `33543238054`;
- Unauthenticated Routes Smoke (light/dark) `33543238031`;
- completed security/contract runs: Zizmor `33543238406`, Checkov `33543238067`,
  Gitleaks `33543238219`, TruffleHog `33543238225`, Dependency Review
  `33543238379`, Cargo Deny `33543238161`, Nilaway `33543238132`, SQLMap
  `33543238168`, OpenAPI `33543238354`, SonarCloud `33543238352` и другие
  записи из paginated run list.

Единственный текущий skip внутри Matrix — advisory WebSocket 10k job
`99974434068`; его guard остаётся non-required. Внешние Chromatic и Dependabot
auto-merge skips классифицируются по собственным `if:` guards и не считаются
product failure. Pending/queued jobs нельзя считать skipped или успешными.

### 32.4 Current root-cause and product status

| Область | Current status | Следующее доказательство |
|---|---|---|
| WASM `rustup target add` race | `CODE-FIXED / FRESH-EVIDENCE-PENDING`; serial target setup уже в workflow | current Linux WASM producer + artifact integrity |
| detect-secrets examples | `CODE-FIXED / FRESH-EVIDENCE-PENDING`; docs/fixture переписаны, baseline reviewed | current detect-secrets and secret-quality aggregate |
| MSG-CONTRACT/AUTHZ/A11Y | `CODE-FIXED / FRESH-EVIDENCE-PENDING`; 32 768 limit, capability UI и 44px hit areas покрыты contracts | complete frontend, a11y и browser matrix |
| WS-CONTRACT | `CODE-FIXED / FRESH-EVIDENCE-PENDING`; REST owns read receipt, generated types/allowlist aligned | final API/WS contract and Go race evidence |
| PUSH-CLEANUP-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING`; admin test/broadcast canonical processing + endpoint binding + stale gone/sent tests | backend full shard, idempotency/concurrency and notification aggregate |
| I18N-GATE-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING`; AST static/dynamic/raw scanner and parity gate green locally | final frontend matrix and SHA-bound manifest |
| Profile save | `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`; no new RED после focused audit | all Vitest shards after WASM/build readiness |
| Stryker/mutmut | `EVIDENCE-BLOCKED`; inventory/governance changes exist, no final survivor/timeout/no-coverage totals yet | complete exact-universe artifacts and 100% viable score |
| CI scheduling/Schemathesis | `CODE-CHANGED / EVIDENCE-BLOCKED`; API fan-out 4→8 with same total examples, mutation lanes capped | terminal matrix plus three comparable green runs |
| Provenance/manifest | `CODE-FIXED / EVIDENCE-BLOCKED`; current SHA/run artifacts not yet complete | current-SHA manifest with hashes and provenance |
| Go mutation diagnostic | `GOVERNANCE-CODE-COMPLETE / EVIDENCE-BLOCKED`; contracted Go gates stay required | bounded diagnostic and race/security evidence |

### 32.5 Definition-of-Done interpretation at this snapshot

The Definition-of-Done checkboxes in §28 remain intentionally unchecked for
any item whose required evidence is only historical, local, queued or
in-progress. Code-fixed rows above may be marked complete only for the code
subtask; they do not satisfy the corresponding `FRESH-GREEN` or release gate.
No `complete`, `green`, `100%` or `готово к релизу` claim is allowed until:

1. run `33543238962` and every required same-SHA workflow are terminal with
   complete non-empty reports, valid hashes and no unexplained failures;
2. full applicable coverage/mutation/security/API/browser/performance evidence
   is aggregated under current SHA;
3. Docker immutable smoke and all external-only staging/release evidence in
   §29 are obtained or explicitly recorded as blocking `EXTERNAL-ONLY`.

The external boundary is unchanged: merge to `main`, resulting-main rerun,
canonical exact-six image producer, registry attestations, immutable-digest
Docker smoke, Kubernetes/TLS/ExternalSecrets/observability, field CWV,
real-device Safari/iOS/Android, chaos/rollback and production release remain
outside local repository authority. The five P2 hardening records in §31.5 are
code-complete but remain `FRESH-EVIDENCE-PENDING`; they must not be promoted to
security-aggregate green until current workflow reports are complete.

---

## 33. Independent full-platform audit overlay (2026-09-03; authoritative)

`docs/audits/AUDIT_PLATFORM_FULL.md` — это отдельный пользовательский
read-only synthesis-аудит, а не сертификат production readiness. Он был
проанализирован после snapshot из §32 и поэтому не должен переиспользовать
старые SHA, coverage reports или CI runs. Сам файл остаётся пользовательским
untracked-артефактом и не добавляется массовым `git add`; в этот план перенесён
его полный triage, чтобы ни один finding не потерялся и чтобы status каждого
finding был проверяемым.

### 33.1 Identity и правила доказательств

| Поле | Значение/правило |
|---|---|
| Audit ID/date | `AUDIT-PLATFORM-FULL-2026-09-03`; synthesis завершён, production не сертифицирован |
| Рабочая ветка | `egorribun` |
| Audited source snapshot | `36ff58509` (`fix: close MVP quality and security blockers`); этот commit содержит все проверенные code/CI/test/infra изменения из overlay |
| Audit-plan state | План обновляется отдельным docs-only commit после source commit; его SHA не является audited source SHA |
| User audit artifact | `docs/audits/AUDIT_PLATFORM_FULL.md`, сохранён отдельно; секретоподобные примеры не становятся baseline/exclusion |
| Evidence class | локальные тесты и diff — class C; только свежий exact-SHA CI/registry/staging — release evidence |
| Reuse policy | run `33681502277` (OtpEntry coverage barrier) и старые §32 runs не переиспользуются; после commit обязателен новый SHA-bound matrix |

Каждая запись `CODE-FIXED / FRESH-EVIDENCE-PENDING` означает, что исправление
видно в текущем diff и есть focused test, но соответствующий aggregate ещё не
доказан. `BACKLOG / NON-BLOCKING` означает воспроизводимый P2/P3 или широкую
архитектурную эволюцию, не являющуюся блокером текущего MVP; она не скрывается
из аудита и получает owner/следующую проверку. `EXTERNAL-ONLY` нельзя закрыть
локальным тестом.

### 33.2 Backend findings (BE)

| Finding | Current disposition | Evidence / follow-up |
|---|---|---|
| BE-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Migration 148642dd1207 больше не импортирует runtime encryption/config и использует native SQLAlchemy types; проверить `alembic upgrade/downgrade`, offline SQL и PostgreSQL в fresh CI. |
| BE-02 | `DECISION-RECORDED / MIGRATION-EVIDENCE-PENDING` | ADR-036 заменяет устаревшие 92 на текущий measured inventory (45 tables; 134 effective defaults: 26 dual, 91 Python-only and 17 server-only; one `Computed` expression is tracked separately; source AST 65 Python-only and 17 server-only). Candidate selection still requires PostgreSQL catalog preflight plus phased migrations; no blanket rewrite. Live schema/upgrade/downgrade evidence remains required. |
| BE-03 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | `User.chats` и `Chat.participants` получили явные `back_populates`/`lazy="noload"`; прогнать async serialization/MissingGreenlet suite. |
| BE-04 | `BACKLOG / ARCHITECTURE` | Dishka и legacy `Depends` coexistence требует отдельного ADR и постепенной миграции, не меняется в quality-closure commit. |
| BE-05 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Backend call sites используют central logger/ProcessorFormatter; совместимый stdlib bridge оставлен для AuditService. Проверить full log redaction и отсутствие PII в aggregate. |
| BE-06 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | `_redact_nested` обходит dict/list/tuple/cycles и sensitive transport keys; focused logging tests green, повторить detect-secrets/logging aggregate. |
| BE-07 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | NATS disconnect теперь warning + `nats_publish_core_skipped_total`; проверить reconnect/failure telemetry. |
| BE-08 | `BACKLOG / ARCHITECTURE` | Orphan `CdcOutboxWorker` требует отдельного lifecycle/DI решения и integration test; не объявлять fixed по одному import. |
| BE-09 | `FALSE POSITIVE / VERIFIED IN CODE` | Existing event gather/cancellation propagates task cancellation; сохранить regression test и не добавлять suppression. |
| BE-10 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Loopback revocation URL разрешён только local/dev/testing, production fails closed; проверить settings matrix. |
| BE-11 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Exception justification typo/comments исправлены; повторить AST gate. |
| BE-12 | `BACKLOG / P3` | Monolithic schemas/config/docs — плановая декомпозиция, не блокирует текущие gates; завести reproducible backlog entries. |

### 33.3 Frontend findings (FE)

| Finding | Current disposition | Evidence / follow-up |
|---|---|---|
| FE-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | `server-static.mjs` и production wrapper fail closed на malformed URI/path boundary; node server tests green. |
| FE-02 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Router получает shared QueryClient; typecheck/unit/SSR build green. |
| FE-03 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Redirect helper rejects backslash/open redirect и сохраняет query/hash; focused tests green. |
| FE-04 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | ClockWidget SSR placeholder устраняет hydration drift; component tests green. |
| FE-05 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | wasm-pack/build failure обрабатывается детерминированно; build-wasm tests и orchestrated build green. |
| FE-06 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Call sites используют canonical `leadingIcon`; compatibility mock принимает/удаляет legacy `startIcon`; lint/React console checks обязательны. |
| FE-07 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | `useAuthStore` экспортирован из barrel и покрыт store tests. |
| FE-08 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Duplicate Tailwind class удалён; lint/visual baseline обязателен. |
| FE-09 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Sessions test mock больше не leaking DOM props; run full settings/E2E selectors. |

### 33.4 Go findings (GO; duplicate aliases are intentionally retained)

| Finding | Current disposition | Evidence / follow-up |
|---|---|---|
| GO-01 / FP-FP-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | File-processor rejects Unix/Windows absolute and traversal keys before workflow; normal Go tests pass, race/security tests required. |
| GO-02 / GW-AUTH-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Gateway atomically indexes all RSA JWKS `kid`s, supports dual-key window and blocks HS confusion; dual-key tests pass. |
| GO-03 / GW-RL-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | `/health/*` bypasses Redis rate limiter while application routes remain protected; tests pass. |
| GO-04 / WSH-CFG-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | WS defaults include localhost and port 80 with explicit origin tests. |
| GO-05 / CLI-REDIS-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | `uni-cli` uses cursor SCAN and bounded DEL batches; tests pass. |
| GO-06 / DOC-AGENTS-01 | `BACKLOG / P3 DOCS` | `services/AGENTS.md` event claims need source-of-truth review; no runtime behavior change inferred. |
| GO-07 / ENV-TOOL-01 | `EXTERNAL-ONLY / FRESH-EVIDENCE-PENDING` | Local Windows lacks CGO/GCC/golangci-lint; Linux runner must provide `go test -race`, vet/lint/SBOM evidence. |

### 33.5 Rust findings

| Finding | Current disposition | Evidence / follow-up |
|---|---|---|
| RUST-P1-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Native pointer paths fail closed; WASM uses checked arithmetic/bounds; all-target tests pass locally. |
| RUST-P1-02 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | NUL/BOM sanitization is aligned across WASM/native paths; parity tests pass. |
| RUST-P2-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Rayon conflict batch releases Python GIL through `py.detach`; native tests pass. |
| RUST-P2-02 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | PBKDF2 iteration/key-size bounds and `Result` contract enforced; generated bindings regenerated and tested. |
| RUST-P2-03 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Sensitive HMAC/scrypt/PBKDF2 buffers zeroized; dependency pinned and lock/pkg artifacts regenerated. |
| RUST-P2-04 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Cargo-deny workflow now enumerates all four crates in a fail-closed matrix; no scan omission is hidden by an exclusion. Current Linux runner evidence remains required. |
| RUST-P2-05 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Rust fuzz workflow now includes `crates/pyo3-sanitizer/fuzz` with bounded smoke; current runner artifact inventory remains required. |
| RUST-P3-01 | `BACKLOG / P3` | Root workspace absence is tooling ergonomics, not a runtime defect; add workspace only with complete member inventory. |
| RUST-P3-02 | `BACKLOG / P3` | Root fuzz target ownership needs ADR before move/delete. |
| RUST-P3-03 | `BACKLOG / P3` | Hex→base64 worker allocation optimization is non-blocking; benchmark before changing. |
| RUST-P3-04 | `BACKLOG / P3` | Unused deps/features require cargo-deny/clippy inventory and a dedicated cleanup commit. |

### 33.6 Infrastructure findings (INFRA)

| Finding | Current disposition | Evidence / follow-up |
|---|---|---|
| INFRA-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Standalone ExternalSecret/deployment now carries revocation/cache/HMAC/RSA material with explicit mounts/env refs; K8s contract tests pass. |
| INFRA-02 | `DECISION-RECORDED / FRESH-EVIDENCE-PENDING` | ADR-034 and `k8s/README.md` make Helm the sole canonical producer for all six application workloads; raw manifests intentionally do not duplicate Go services. Fresh Helm render, policy validation and one-release staging smoke remain required. |
| INFRA-03 | `FRESH-EVIDENCE-PENDING` | Deploy workflows validate SHA/digest image identity; current Kyverno/Helm render must prove no mutable `IMAGE_TAG`. |
| INFRA-04 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Frontend HPA template, values/schema and staging validation added; Helm lint/template required. |
| INFRA-05 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Frontend SSR memory request/limit raised to 128Mi/512Mi; verify rendered resources and budget rationale. |
| INFRA-06 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Reusable backend workflow passes inputs through typed environment variables; actionlint/contract tests green. |
| INFRA-07 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Backend Docker healthcheck uses `/health/ready`. |
| INFRA-08 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | File-processor Compose probe uses `grpc_health_probe`. |
| INFRA-09 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Observability override supplies pinned curl healthprobe sidecar; Compose merge must be validated. |
| INFRA-10 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Gateway HPA template/values/schema added with KEDA ownership guard. |
| INFRA-11 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Standalone issuer is envsubst-parameterized; render contract required. |
| INFRA-12 | `BACKLOG / INTENTIONAL SCHEDULE GUARD` | Weekly cleanup intentionally fails closed without configured DB secret; document operator setup and test both guarded/valid paths. |

### 33.7 Security and supply-chain findings (SEC)

| Finding | Current disposition | Evidence / follow-up |
|---|---|---|
| SEC-01 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | GraphQL now verifies gateway `X-Internal-Signature` HMAC over bound identity/session/tenant and fails closed in production; focused tests pass. |
| SEC-02 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Same dual-key JWKS implementation as GO-02; retain duplicate label for traceability. |
| SEC-03 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Production rejects repository-known audit secret sentinel; scanner must verify no plaintext secret/PII enters logs or baseline. |
| SEC-04 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Shared Go slog redacting handler is implemented and wired to gateway/ws-hub/file-processor with recursive key/value, URL and panic-safe redaction; package coverage is 100%. Require current service logging evidence. |
| SEC-05 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Quality contract/normalizer/validator now use explicit metric applicability and machine-readable `N/A`; unsupported metrics cannot be silently converted to 100%. Require current aggregate manifest. |
| SEC-06 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Current `.gitleaks.toml` allowlists only existing lockfiles and the workflow covers protected `main` pushes plus PRs into `main` without duplicate source-branch scans; fresh Linux scan and current-SHA artifact remain required. |
| SEC-07 | `FRESH-EVIDENCE-PENDING` | Baseline finding identities/hashes must be revalidated by current detect-secrets; stale or unexplained entries fail closed. |
| SEC-08 | `EXTERNAL-ONLY / TOOLING` | Bandit target/Windows encoding is runner/tooling hygiene; keep production scan scope explicit and reproduce on Linux. |
| SEC-09 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | ADR-035 and the fail-closed dependency policy add upper bounds to all 32 previously unbounded external production requirements; current-SHA frozen install, vulnerability, SBOM and compatibility evidence remain required. |
| SEC-10 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Same cursor-SCAN fix as GO-05. |
| SEC-11 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Same readiness healthcheck fix as INFRA-07. |
| SEC-12 | `CODE-FIXED / FRESH-EVIDENCE-PENDING` | Pre-commit mypy now uses the complete anchored `^app/` scope and declares the locked CLI imports required by that scope; the hook and 351-file run are green. Fresh current-SHA pre-commit/security aggregate remains required. |

### 33.8 Current local evidence and next required gates

После overlay зафиксированы следующие воспроизводимые class-C результаты
(audited source SHA `36ff58509`; плановый docs-only commit и внешний audit
artifact не смешиваются с source evidence):

- `uv run python verify_harness.py --repo-only`: `29/29`;
- backend `ruff`, `mypy`, `compileall` и focused suites — green;
- frontend `npm run typecheck`, `npm run lint`, `npm run i18n:check`,
  `npm run build` и `npm run test:wasm`: `190/190` WASM tests green, i18n
  scanner `2096` static/`68` dynamic references and `18/18` parity; build
  завершает client+SSR/prerender;
- Go обычные `go test ./...` для gateway/ws-hub/file-processor/uni-cli и Rust
  all-target suites — green; shared Go logging package has `100.0%` statement
  coverage;
- quality/manifest/normalizer/coverage suite: `267 passed, 1 skipped`; the one
  skip is the documented Windows case-sensitive-checkout limitation, not a
  relaxed gate;
- focused detect-secrets `1.5.0` scans of changed security/config/logging and
  Kubernetes/Compose files contain no new findings and pass the committed
  baseline verifier; the full all-files scan is delegated to the Linux CI
  runner because Windows multiprocessing did not terminate deterministically;
- actionlint and focused workflow/security contracts pass, including the
  Semgrep push/no-diff regression: PRs retain diff baseline mode while default
  branch pushes run a full scan and must emit real SARIF;
- all supported merged Docker Compose matrices parse successfully, Docker
  currently has zero running containers, and Squawk `v2.44.0` reports zero
  migration issues for the target revision;
- `git diff --check` — green;
- source commit `36ff58509` прошёл локальные pre-commit hooks (ruff,
  detect-secrets, gitleaks, Bandit, mypy, no-python2-except, actionlint,
  Semgrep и frontend lint-staged); audit-plan commit будет зафиксирован
  отдельно после этой записи;
- Windows `go test -race` блокируется отсутствием CGO/GCC и остаётся
  `EXTERNAL-ONLY`, а Windows full Vitest run ранее превысил практический
  timeout при worker churn; это не основание ослаблять gates или добавлять
  retries/suppressions.

Обязательная последовательность после завершения SEC-04/SEC-05:

1. Удалить только tool-generated coverage/temp files из новых shared Go
   packages; пользовательские untracked files, включая внешний audit, не
   трогать.
2. Повторить focused logging/quality-contract tests, полный `ruff`/`mypy`,
   frontend typecheck/lint/build/WASM и Go/Rust tests; выполнить actionlint,
   detect-secrets, gitleaks, Semgrep, Helm/Compose contracts.
3. Создать небольшие coherent commits без wave IDs и `Co-Authored-By`, затем
   безопасно перенести их на актуальный `origin/egorribun` fast-forward-путём
   без force-push и без изменения stash.
4. Дождаться нового exact-SHA CI matrix: coverage gate должен пройти прежде
   mutation lanes; затем собрать все 8 Schemathesis shards, full frontend
   mutation inventory, Go race/security/load, Lighthouse/CWV, dark smoke и
   provenance-bound manifest. Каждый failure разбирается по логу, а не
   маскируется таймаутом.
5. Только после terminal green CI обновить audit ledger; затем отдельно
   зафиксировать внешние блокеры §29: merge/resulting-main rerun, canonical
   exact-six immutable images, registry SBOM/provenance/attestations,
   digest Docker smoke, Kubernetes staging/TLS/observability, real-device CWV,
   chaos/restart/rollback и production release.

Эта секция закрывает информационный пробел независимого аудита, но не меняет
Definition-of-Done: пока отсутствуют current-SHA CI и внешние staging/release
доказательства, цель остаётся активной и нельзя заявлять полное завершение.

## 34. Current continuation checkpoint (2026-09-04; source-of-truth refresh)

Этот checkpoint добавлен после повторной сверки рабочей ветки с origin и не
перезаписывает исторические evidence из §§32–33. Он является актуальным
операционным входом для следующего автономного цикла.

### 34.1 Identity and worktree

| Поле | Текущее значение |
|---|---|
| Branch | `egorribun` (tracking `origin/egorribun`) |
| Source SHA | `d909673d1402637f042c0bc78e9f2cbf784a50b1` |
| Previous source SHA | `a579943eae065866b0d750178d66243f2c3f6fc8` |
| Latest source commits | `3991dc72f` mutmut isolated-input closure; `5c37f955c` Spinner mutation contract; `f65dadef9` messenger/push edge-contract tests; `387966a48` cgroup quota-first sizing; `9773bed4e` stable logging-record assertions; `ab3ea68d1` cgroup edge coverage; `a579943ea` Semgrep ledger realignment; `1cc51419d` BuildKit WASM caches; `d909673d1` architecture-scoped cache IDs |
| Open user artifact | `docs/audits/AUDIT_PLATFORM_FULL.md` remains deliberately untracked and untouched |
| Stash | No stash entries were present during the checkpoint; no user files were removed or staged |
| Last push | `d909673d1` pushed successfully; the frontend typecheck push hook passed |

The Spinner change is a focused RED→GREEN mutation contract: the component
test now asserts the semantic `animate-spin` class, and a seven-mutant local
run produced `7/7 Killed`. It does not certify the full frontend mutation
universe. The mutmut change adds the two root Kubernetes manifests required by
the isolated copy inventory and its focused regression suite is green.
The current source also adds deterministic branch contracts for messenger
`clearChat` cache isolation and Web Push subscription edge cases (primitive and
malformed user IDs, VAPID normalization, URL-safe key decoding, exact key
comparison, permission options and expiry boundaries). The focused Vitest
selection is `138/138`, and the same source passes frontend typecheck, lint and
production client+SSR build locally. The cgroup fix makes finite cgroups v2/v1
quotas authoritative before affinity (19 focused database/auth tests plus 18
database settings tests pass), while the frontend Dockerfile now uses locked,
architecture-scoped BuildKit caches; `docker buildx build --call=check` and the
Docker resource contract pass. Semgrep's existing reviewed suppressions were
realigned to the post-refactor source lines and the fresh Semgrep gate is green.

### 34.2 Fresh CI and runner-cap evidence

The fresh PR matrix for this source is
[run 33854837526](https://github.com/egorribun/university_ecosystem/actions/runs/33854837526),
created at `2026-09-04T08:43:48Z`, with `head_sha` exactly equal to the Source
SHA above. At the time of this refresh it was still non-terminal; no result is
promoted to release evidence until every required child job and aggregate is
terminal. The superseded predecessor
[33854426925](https://github.com/egorribun/university_ecosystem/actions/runs/33854426925)
on `a579943e` was cancelled after the next push, preserving its history but not
its partial evidence.

The prior run `33846790732` on `3991dc72f` was superseded by the Spinner push.
The old scheduled nightly run `33840031905` on `d654e3f6` held 16 hosted
runners in a long Stryker tail and was cancelled only after verifying it was a
stale main-SHA run unrelated to the current PR. Cancellation preserves its
history and is not evidence for either source SHA. This was an operational
queue action, not a gate bypass.

The repository ruleset requires both the Matrix contexts and standalone
security/contract contexts. Therefore deleting duplicate-looking workflows or
adding broad path filters would leave required contexts pending. Any future
capacity change must retain the complete 64-way Stryker, 8-way mutmut-stats,
128-way mutmut execution, API shards, browser matrix and all security scans.
The current measured safe budget remains 8 Stryker plus 12 mutmut execution
workers (and 8 mutmut-stats fan-out); changing it requires three comparable
green runs with queue, timeout and billed-minute evidence, as required by
§11.13. The measured Stryker tail is a cost-balancing problem, not a reason to
raise the 120-minute timeout or weaken viable-mutant semantics.
The live run has not yet reached the mutation phase. Its first 90 observed
jobs show `0` failures, `18` successes and `11` intentional skips; completed
non-skipped jobs have a median duration near `0.9` minutes and a p90 near
`4.0` minutes, while the current queue-start delay is a measured consequence of
the observed 20-runner account ceiling and concurrent standalone security/fuzzing
workflows; this was an observation, not a repository-enforced global semaphore.
Historical comparable runs are either failed or cancelled, so the three-green
rebalancing threshold is not met.

### 34.3 Open root causes after the checkpoint

1. **Stryker quality and cost remain open.** Historical artifacts contained
   `8,557 Survived`, `300 Timeout`, `36 RuntimeError` and `16 NoCoverage`
   statuses among 35,316 completed mutants. The validator correctly rejects
   every non-`Killed`/`CompileError` status. The next step is a complete,
   source-bound survivor ledger and owning RED tests/refactors; no exclusions,
   `ignoreStatic`, related-mode relaxation, threshold change or timeout
   inflation is allowed.
2. **Stryker tail balancing remains open.** The 64-way preflight contains
   approximately 40,841 mutants and historical producer p90 was about 56
   minutes with a 100-minute maximum. Rebalance only through deterministic,
   tested cost-aware planning that preserves exact assignments, provenance and
   all mutants; do not move hotspots based on intuition alone.
3. **Fresh mutmut validation is required.** The isolated copy contract now
   includes `k8s/ingress.yaml` and `k8s/secrets-example.yaml`; all stats and
   execution artifacts must prove the exact copy inventory on the new SHA.
4. **External-audit architecture debt remains explicit and scoped.** BE-04
   (Dishka/Depends coexistence) and BE-08 (CDC worker lifecycle) need separate
   ADRs or measured phased work. BE-02 is now recorded in ADR-036 with a
   measured inventory and safe migration policy, but live PostgreSQL
   migration/upgrade evidence is still required. SEC-06 is now
   contract-verified and code-fixed, while SEC-09 is recorded in ADR-035 and
   code-fixed, but
   its fresh current-SHA compatibility evidence is still required. INFRA-02's
   scope decision is now recorded in ADR-034; current-SHA Helm/staging
   evidence is still required and it is not silently treated as runtime proof.
5. **Release evidence is still external.** Merge-to-main recertification,
   exact-six immutable images, registry SBOM/provenance/attestations,
   digest-pinned Docker smoke, Kubernetes/TLS/ExternalSecrets/observability,
   real-device CWV, chaos/rollback and production release remain blocked until
   the authority and evidence described in §§29 and 33.8 exist.
6. **Docker CPU quota sizing is fixed and must be recertified.** A measured
   cgroup-v2 container with `--cpus=0.50` exposed host affinity `16` while
   `/sys/fs/cgroup/cpu.max` reported the 0.5 quota; `387966a48` now makes finite
   v2/v1 quotas authoritative, caps pathological values and falls back safely
   for malformed/unlimited files. Focused database/auth tests are green. The
   remaining work is fresh-run and immutable-image recertification, not another
   unbounded pool rewrite.
7. **Semgrep line-bound provenance was repaired.** The `ab3ea68d` run exposed a
   stale SHA-1 suppression range after the security module's import cleanup.
   `a579943ea` updates only that exact policy key (127–129), retains the
   reviewed HIBP rationale and passes the validator/pre-commit; run
   `33854837526` is the required fresh-SHA confirmation.
8. **External audit P0/P1 triage is complete for current ancestry.** The
   independent audit's listed GraphQL HMAC, ExternalSecret/revocation, migration,
   SSR boundary, Go path/JWKS/health/origin, Rust memory/sanitization, Helm and
   service-log findings are already fixed and test-backed. BE-02/BE-04 remain
   explicit architecture debt; INFRA-02 has an accepted scope decision in
   ADR-034 but remains evidence-pending until a complete Helm/staging run.

### 34.4 Required next cycle

1. Poll run `33854837526` to terminal state and inventory every non-success,
   cancellation, skip and timeout exactly once; separate root failures from
   aggregate cascades.
2. Confirm the fresh mutmut stats shards no longer reproduce the missing-root
   manifest error or the circuit-breaker timing race.
3. Confirm frontend qualification, E2E/browser and dark smoke outcomes before
   accepting any Stryker artifact. Re-run the narrow Spinner mutation contract
   only as a regression, not as aggregate evidence.
4. If Stryker producers fail, download the exact preflight and shard reports,
   classify the complete inventory, then implement one owning-domain RED→GREEN
   slice at a time. Keep a machine-readable ledger with report hashes and
   tested/source/base identities.
5. After a terminal-green source SHA, run the full local/harness/security/API/
   infrastructure matrix, update this plan with immutable report hashes, and
   only then perform the external release/staging sequence.

Until those steps produce terminal current-SHA artifacts, this plan and goal
remain active; `CODE-FIXED`, local green or historical success is never
substituted for full quality closure.

## 35. Current live checkpoint (2026-09-05; source `73203ac5d`)

This section records the currently running recertification without promoting
partial evidence to a release decision. It supersedes the operational values
in §34 while preserving that section's historical evidence.

### 35.1 Source identity and worktree

| Field | Value |
|---|---|
| Branch | `egorribun` (tracking `origin/egorribun`) |
| Source head SHA | `73203ac5d15b66fb536a814a6d07fbc6b985bb4f` |
| PR | [#1266](https://github.com/egorribun/university_ecosystem/pull/1266), base `main` |
| Current source fix | `test: include k8s contract docs in mutmut copy` (isolated mutmut input closure) |
| User artifact | `docs/audits/AUDIT_PLATFORM_FULL.md` remains untracked and untouched |
| Stash | no stash entries; no user files staged or removed |
| Worktree | only this plan overlay is modified; external audit remains untracked |

The preceding run `33978875062` was intentionally cancelled after its exact
primary failure was captured: mutmut stats shard 5 could not read
`mutants/k8s/README.md` while collecting
`tests/test_infra_audit_contract.py`. Commit `73203ac5d` adds that file to the
tested `also_copy` inventory and its regression tests; no skip, exclusion or
mutation threshold change was used.

### 35.2 Fresh current-SHA evidence (non-terminal)

The active matrix is
[run 33981030258](https://github.com/egorribun/university_ecosystem/actions/runs/33981030258),
whose source head is exactly the SHA above. Its coverage-policy artifact
`quality-evidence-63103b97a5036f50524b6c2042c5b5e000652b68` (artifact id
`9974115481`) is internally valid and records the necessary two-identity
pair:

- `source_head_sha` = `73203ac5d15b66fb536a814a6d07fbc6b985bb4f`;
- `tested_commit_sha` (the pull-request merge ref) =
  `63103b97a5036f50524b6c2042c5b5e000652b68`;
- `validation.valid` = `true`, with no missing reports;
- frontend, Python, Go applicable/derived, Rust applicable/derived and Tier-0
  coverage metrics are 100%; unsupported native counters are explicitly
  represented as `N/A` with reason codes rather than fabricated percentages;
- provenance binds repository, workflow path/ref, run id `33981030258`,
  attempt `1`, source head and tested merge identity.

At the latest observation (21:25 MSK) the matrix had 309 materialized jobs:
114 success, 12 intentional skips, 20 running, 163 queued and zero failures.
Stryker had 9 completed shards, 8 running and 47 queued; all eight mutmut
stats shards and central universe generation were successful, while the
mutmut execution groups were still running/queued. These counts are progress
only; no mutation score or release status is accepted until every required
job and aggregate is terminal.

All standalone companion workflows for this source were already terminal:
20 successes (security, contracts, fuzz, performance, OpenAPI, Docker/Helm
and dark/light unauthenticated smoke) and two documented intentional skips
(Dependabot auto-merge and Chromatic). The active matrix remains the only
non-terminal workflow.

### 35.3 Required continuation

1. Keep polling `33981030258` without cancelling while it makes progress; on
   any failure retrieve the exact job log, classify the primary root cause and
   make one RED→GREEN fix on a new SHA.
2. When terminal, download every mutation/coverage/evidence artifact, verify
   source head + tested merge SHA, report hashes, complete inventories and
   aggregate conclusions. A green coverage gate alone is insufficient.
3. Re-run local harness, frontend typecheck/lint/build/WASM and focused
   contract/security checks after any new fix; keep generated artifacts out of
   the worktree and never stage the external audit implicitly.
4. Only after a terminal-green current source SHA update this checkpoint with
   final counts and hashes. Merge-to-main recertification, exact-six immutable
   images, digest Docker smoke, Kubernetes/TLS/observability, real-device CWV,
   chaos/rollback and production release remain external-only gates in §29.

## 36. Read-only Stryker/CI bottleneck audit (2026-09-05; source `31ab24fcf`)

Этот раздел фиксирует измеренный bottleneck без изменения workflow, threshold,
mutation semantics или release gates. Он является диагностическим отчётом, а
не current-SHA mutation evidence: матрица `33989628759` ещё не terminal и
результаты Stryker для `31ab24fcf00789a0149b9bf0d833f8b5c49089c8` пока не
принимаются в manifest.

### 36.1 Что проверено

- `frontend/stryker.config.mjs` строит полный `mutate` scope из
  `quality/coverage-source-policy.json`; `coverageAnalysis` остаётся
  `perTest`, `incremental` выключен, `excludedMutations` и `ignorers` пусты,
  а concurrency ограничен контрактом диапазоном 1–4.
- `frontend/scripts/run-stryker.mjs` fail-closed проверяет полный denominator,
  попарно непересекающиеся shard assignments, source/policy/config hashes,
  preflight identity и `SHARD_EVIDENCE.json`. Ни один из этих контрактов не
  разрешает скрыть survivor, timeout, runtime error или no-coverage.
- В текущем CI run `33989628759` (создан `2026-09-05T20:16:51Z`, `head_sha`
  совпадает с `31ab24fcf`) API в момент аудита показывал `queued`, при этом
  уже материализованные child jobs выполнялись. На наблюдении около 20:20 MSK
  девять jobs завершились success, failures не было; frontend Lighthouse и
  backend unit jobs ещё выполнялись, а Stryker preflight не стартовал. Эти
  числа — progress snapshot, а не итоговый gate.

Старые временные артефакты использованы только для оценки вариативности и
явно не считаются evidence текущего SHA:

| Артефакт | Source head | Наблюдение | Статус |
|---|---|---|---|
| `C:\\Temp\\stryker-shards-338637-current` | `3e54ca9b` | 42 отчёта; `10.1–96.1 min` на shard, среднее `26.5 min`, суммарно около `18.52 h`; длинный хвост — shard 009 (`96.1 min`) | stale, только performance baseline |
| `C:\\Temp\\frontend-mutation-338084-artifacts` | `564bcd57` | 56 отчётов; `7.3–100.7 min`, среднее `30.1 min`; shard 040 — `100.7 min` | stale, только performance baseline |
| `C:\\Temp\\stryker-audit-338637-bac5e61a4d914d4795733a785faf9954\\PREFLIGHT_ARTIFACT.json` | `3e54ca9b` | 589 файлов, 40 841 mutant, 64 shards | stale denominator |
| `C:\\Temp\\stryker-preflight-338968\\PREFLIGHT_ARTIFACT.json` | `5c83aa46` | 589 файлов, 40 830 mutant, 64 shards; план `45–1037` mutant/shard | stale planning sample |

### 36.2 Доказанный критический путь

1. В `.github/workflows/ci.yml` `stryker-preflight` ждёт не только
   `pre-commit-check`, но и весь reusable `frontend-tests` и
   `coverage-policy-gate`. Последний, в свою очередь, ждёт backend, frontend,
   Go и Rust coverage producers.
2. Reusable frontend tests включают unit shards и aggregate, lint, production
   build, bundle analysis и четыре Lighthouse shards с aggregate. Поэтому
   дорогая mutation qualification не может начать подготовку, пока не
   завершатся Lighthouse и остальные core producers; это подтверждено
   текущим snapshot, где Lighthouse/backend ещё выполнялись, а Stryker был
   заблокирован upstream barrier.
3. После preflight запускается фиксированная матрица из 64 Stryker jobs с
   `max-parallel: 8`; каждый job повторяет `npm ci`, валидирует preflight и
   выполняет один свежий shard с `STRYKER_CONCURRENCY=4` (до 32 внутренних
   worker-процессов при восьми hosted jobs). Это ограничивает throughput и
   одновременно создаёт CPU/RSS contention на runner.
4. Aggregate и independent round-trip verifier повторяют checkout/setup и
   `npm ci`, затем заново проверяют shard evidence. Повторная установка —
   намеренная defense-in-depth; удалять её без hash-equivalent manifest и
   regression contracts нельзя.

Отдельный Python mutation lane также вызывает до 128 логических assignments
при `target-groups=128`; это даёт до 128 физических consumers с повторным
setup. Общий лимит остаётся 20 hosted jobs (текущая безопасная раскладка —
8 Stryker + 12 mutmut execution, а mutmut stats используют отдельный fan-out).
Manual/nightly mutation workflows на PR не дублируют эту матрицу.

### 36.3 Безопасный план оптимизации (не выполнен в этом аудите)

1. Ввести подписанный `frontend-coverage-ready` context после unit shards,
   merged frontend coverage и проверки exact source/policy/config hashes.
   Разрешить Stryker preflight зависеть от этого контекста, а не от финального
   Lighthouse/build aggregate; при этом оставить неизменными
   `coverage-policy-gate`, final `CI Success`, полный browser/performance gate
   и SHA-bound manifest. Добавить workflow-contract tests на DAG, hash
   identity, fail-closed missing/partial artifacts и отсутствие fan-out при
   красном qualification.
2. После producer barrier сравнить только сопоставимые зелёные runs для
   `STRYKER_CONCURRENCY=2/4` и `max-parallel=8/10/12`, измеряя wall-clock
   critical path, queue delay, timeout/error rate, CPU/RSS и billed runner
   minutes. До трёх comparable green runs нельзя менять текущий lane budget.
3. Для mutmut отдельно рассмотреть physical groups `32` или `64`, сохранив
   полный логический 128-way plan, exact assignment/group digests и
   regression tests на inventory/completeness. Это эксперимент по setup cost,
   а не разрешение уменьшить denominator.
4. Aggregate и round-trip оставить до появления эквивалентного подписанного
   evidence protocol; любые изменения должны пройти независимый security
   review и текущий SHA full-matrix rerun.

**Acceptance для будущей реализации:** каждый current-SHA mutant ровно один
раз попадает в ожидаемый assignment; отсутствуют missing/duplicate/stale
reports; сохраняются пустые exclusions/quarantines и `100% viable` semantics;
aggregate принимает только полный manifest; а измеренное сокращение
critical-path подтверждено тремя comparable green runs. До этих условий
текущая стоимость Stryker и задержка preflight считаются открытым
`OPEN-PERF/EVIDENCE-BLOCKED`, а не основанием для ослабления quality gates.

## 37. Pre-push checkpoint (2026-09-06; parent source `0d16eee9e`)

Этот checkpoint фиксирует изменения, подготовленные после §36, до запуска
новой SHA-bound матрицы. Сам коммит этого раздела станет частью следующего
source SHA и поэтому не является evidence для перечисленных проверок.

### 37.1 Подготовленные изменения

- `51c28739b` добавляет единый same-run producer WASM для всех E2E callers;
  consumers используют server-issued artifact id, provenance, inventory и
  per-file hashes без cross-run fallback.
- `3b7c09757` разделяет WebSocket transport limit (полные UTF-8 bytes) и
  message-content limit (Unicode code points), сохраняя legacy `read` только в
  Python fallback. Focused route/contract tests закрывают ASCII, Unicode,
  JSON-overhead, malformed/non-object и connection-limit paths.
- `4601d6452` добавляет server-side artifact metadata digest verification;
  `5ae7aabb7` передаёт `actions: read` только caller jobs, реально выполняющим
  эту проверку; `cc6bee33a` закрепляет эти permissions contract tests.
- `c5b046e98` нормализует bare `upload-artifact` digest в canonical
  `sha256:<64 hex>` форму; `5cc0614b8` нормализует API response defensively.
  Любая неожиданная форма digest завершается ошибкой, а не fallback.
- `482cc3f88` добавляет WebSocket audit-context и connection-rejection
  coverage. Все коммиты без `Co-Authored-By`; quality/testing commits не
  используют фиктивные wave identifiers.
- `0d16eee9e` обновляет workflow contract assertions для нового минимального
  `actions: read` разрешения E2E consumers, не расширяя permissions других
  reusable workflows.

### 37.2 Локальная evidence до push

- `python verify_harness.py --repo-only`: **29/29**, exit 0.
- Frontend `npm run typecheck`, `npm run lint`: зелёные.
- Backend Ruff (`app/`, `tests/`), strict mypy (349 files), custom AST и
  no-python2-except: зелёные; actionlint и gitleaks: зелёные; Bandit targeted
  WebSocket scan: без findings.
- WebSocket focused regression: 79+ tests зелёные; расширенная выборка 111
  tests даёт для `app/api/websocket.py` 100% lines/branches.
- WASM workflow contract: 4/4; relevant pre-commit, semgrep, detect-secrets
  и diff checks зелёные. `.secrets.baseline` обновлён и staged в последнем
  workflow commit согласно repository policy.

### 37.3 Что не является evidence этого source

Старый PR matrix `33989628759` относится к SHA `31ab24fcf`, не к локальному
parent `0d16eee9e`; на момент checkpoint он оставался non-terminal (135
success, 12 intentional skips, 20 running, 142 queued, zero observed
failures). Его mutation/coverage results не переносятся на новый SHA. После
публикации следующего SHA требуется дождаться terminal matrix и companions,
загрузить все artifacts, проверить source/tested merge identities, report
hashes, full mutant inventory и aggregate conclusions.

Пользовательский `docs/audits/AUDIT_PLATFORM_FULL.md` и каталоги
`.tmp_preflight/`, `.tmp_stryker_18/`, `.tmp_stryker_22/` остаются untracked и
не входят в source commits. Merge-to-main, exact-six immutable images,
registry SBOM/provenance/attestations, digest Docker smoke, Kubernetes/TLS/
ExternalSecrets/observability, real-device CWV, chaos/rollback и production
release остаются внешними gates из §§29, 33 и 36 до получения их прямых
доказательств.

## 38. Current-SHA frontend and pre-push closure checkpoint (2026-09-09; source `752dabf9f`)

This checkpoint supersedes the pending local frontend evidence note in §37. It
records only reproducible local evidence and does not import results from the
older PR runs or from the still-running remote matrix.

### 38.1 Closed locally

- The async React diagnostic owners identified by the previous full run are
  closed by `d25707a46` (login/OTP), `3c5c0a3d8` (News interactions),
  `694e0af83` (MapControls fullscreen/rejection), `25d72e30d`
  (NewsCardEditDialog mounts), and `46619e2cb` (Dashboard skip-link). These
  changes use scoped `act`/`waitFor` contracts and expected-console matchers;
  they do not suppress unexpected diagnostics or change production behavior.
- The exact canonical frontend command (`npm run test:ci`, whose runner
  executes the WASM producer then Vitest with coverage/JUnit reporters) was
  reproduced from the post-fix source. It completed **651/651 test files,
  6656/6656 tests, zero unhandled errors**, JUnit output, and 100% for every
  applicable metric: statements 18724/18724, branches 13241/13241, functions
  4505/4505, lines 16874/16874. Duration was 881.71 seconds on the local
  Windows host; the duration is a diagnostic baseline, not a release SLO.
- `78f79d032` keeps the Python workflow contract fixture formatter-clean.
  `ec7654283` makes Stryker execution and aggregate fail closed behind the
  independent security/type qualification while preserving the complete
  64-shard plan, empty exclusions/ignorers and viable-mutant denominator.
  An independent review found 59 valid jobs, no missing dependencies/cycles,
  unchanged mutation inventories and no permission broadening in that patch.
- Full pre-commit was run with an isolated `PRE_COMMIT_HOME` after the
  detect-secrets baseline was staged. Ruff check/import/format, detect-secrets,
  strong-env-secrets, no-Python2-except, Bandit, mypy, actionlint, Docker
  Semgrep and Renovate validation all passed. The only baseline delta is the
  line number and timestamp metadata for an existing `Login.test.tsx` fixture;
  it is committed separately as `752dabf9f` per repository policy.

### 38.2 Fresh remote verification in progress

- Source `752dabf9fd165084df0d897eef39fe93095e0ebb` is pushed to
  `origin/egorribun`; PR 1266 currently points to this SHA. Fresh matrix run
  `34287653082` and companion workflows were created at the same SHA. At the
  time of writing they are non-terminal, so no remote test, mutation,
  coverage, security or performance result is accepted as current evidence.
- The matrix currently shows the observed account-wide hosted-runner ceiling in
  action: companion workflows occupy the active slots while the 59-job CI
  matrix waits. This is an observed queue snapshot, not yet the required
  three-comparable-green-run proof for changing fan-out. Continue collecting
  start/end times, queue delay, timeout/error rate and billed minutes before
  modifying the lane budgets.

### 38.3 Remaining blockers and boundaries

1. Wait for all fresh current-SHA workflows, download every artifact, and
   verify manifest source/tested-merge SHA, report hashes, complete coverage
   and mutation inventories. Investigate each final failure by exact log, not
   by stale PR screenshots.
2. Close the two currently reported high Dependabot alerts in Go only after
   compatibility and test evidence: gRPC-Go `<=1.83.0` (CVE-2026-84304) and
   transitive `moby/go-archive <0.3.0` (CVE-2026-17106). Do not suppress or
   mark either alert as accepted without a documented, verified reason.
3. Backend full-domain pytest remains incomplete on Windows because the prior
   xdist run stalled near 99% without a final nodeid inventory. Use the bounded
   agent/CI evidence to obtain a deterministic terminal result; do not infer
   green status from the partial run.
4. Stryker/mutmut 100% viable scores, fresh current-SHA coverage manifests,
   Go race tests and Linux sanitizer/fuzz evidence remain CI-owned until
   terminal artifacts are verified. The `frontend-coverage-ready` context and
   measured three-run CI critical-path optimization are still open; current
   fail-closed qualification is not a denominator reduction.
5. External release gates remain open: merge-to-main recertification,
   canonical exact-six immutable image producer, digest-pinned Docker smoke,
   Kubernetes/TLS/ExternalSecrets/observability staging, real-device/browser
   CWV, chaos/restart/rollback, production release and the final
   SHA-bound `AUDIT_QUALITY_CLOSURE_<sha>.md`.

User-owned `docs/audits/AUDIT_PLATFORM_FULL.md`, `.tmp_preflight/`,
`.tmp_stryker_18/` and `.tmp_stryker_22/` remain untracked, untouched and
excluded from all source commits.

## 46. Frontend interceptor survivor closure and fresh-SHA boundary (2026-09-10; source `f5f23a026`)

### 46.1 Terminal stale-run evidence

- PR #1266 run `34486140554` is terminal and remains historical evidence only:
  it tested remote SHA `78d03e1379a0c428ae509039d4942677ed89a7d9`, not the current
  `egorribun` source. Its aggregate mutation failure was fail-closed fallout
  from isolated survivors; the `digest-mismatch` lines in the aggregate log
  were validation fallout, not an additional source defect.
- The downloaded frontend shard-018 artifact (`10162914088`) contained two
  exact survivors in `src/api/client.ts`:
  - mutant 55 replaced the idempotency-key guard with `true` at the unsafe
    mutation tracking branch (line 284); no prior test exercised a POST without
    an `Idempotency-Key`.
  - mutant 102 replaced the SSR forwarding metadata guard with `true` at line
    339; the existing suite tested the pure predicate and positive forwarding
    path but not the allocation-preserving negative path.
- Both findings were reproduced from the artifact's `mutation.json`; no
  production behavior was changed to conceal a mutant.

### 46.2 RED → GREEN regression coverage

- Added `does not track unsafe requests that omit an idempotency key` to
  `frontend/src/api/__tests__/client.closure.test.ts`. It sends two POSTs
  without a key, asserts both reach the adapter and verifies that the
  `BroadcastChannel` ledger remains empty. This kills the unconditional
  tracking mutant and protects duplicate suppression boundaries.
- Added `preserves the request headers object when SSR metadata is absent`.
  The test isolates the language interceptor, invokes the real Axios request
  interceptor with no cookie/fingerprint metadata and asserts that the
  original headers object is preserved. This directly protects the
  `hasSsrForwardingHeaders` allocation guard against an unconditional branch.
  The temporary module mock is removed in `finally`, preventing cross-test
  pollution.
- Focused Vitest result: **43/43 passed**. Frontend typecheck and ESLint for
  the changed file pass. Isolated pre-commit passes detect-secrets,
  hardcoded-secrets, no-Python2-except, actionlint, Semgrep and all applicable
  hooks. The default Windows pre-commit cache ACL failure is avoided by the
  previously documented isolated cache; no hook is bypassed.
- Source commit: `f5f23a026` (`test: cover api client interceptor branches`).
  Only the intentional tracked test file was staged; all user-owned
  untracked paths remain untouched and unstaged.

### 46.3 Fresh-CI acceptance and remaining boundary

1. Run `git diff --check`, the harness, frontend typecheck/lint/build and the
   focused API client suite after this documentation checkpoint. Push the
   resulting `egorribun` SHA non-force only after confirming the worktree
   contains no accidental staged artifacts.
2. Treat only the new current-SHA PR matrix as evidence. Require shard-018
   (and every other Stryker shard) to report `Killed`/`NoCoverage` according to
   the contract, aggregate/evidence roundtrip success, and a complete
   denominator; do not infer a 100% score from the stale artifact.
3. Re-run the full mutmut matrix after the two earlier CLI survivors and
   download all terminal artifacts. Any new survivor, timeout, cancellation,
   digest mismatch or missing report is a blocker and receives the same
   exact-artifact TDD treatment.
4. Keep all remaining gates open until current-SHA Python/frontend/Go/Rust,
   API/Schemathesis, security/supply-chain, Lighthouse/E2E, infrastructure,
   performance and harness evidence is complete. Merge-to-main
   recertification, exact-six immutable image/SBOM/provenance, digest Docker
   smoke, Kubernetes/TLS/ExternalSecrets/observability staging, real-device
   CWV, chaos/rollback, production release and the final SHA-bound audit are
   external release gates and are not implied by this local test commit.

## 41. Current stale-PR mutation evidence and bounded remediation (2026-09-10; local HEAD `5a04b3e34`)

### 41.1 Exact stale-run findings

- PR #1266 run `34486140554` is based on the old remote SHA
  `78d03e1379a0c428ae509039d4942677ed89a7d9` and is not evidence for the
  current branch. At the latest inspection it had 355 completed checks, 8
  active mutation jobs and two failures: the previously fixed group-91
  survivor and a newly terminal group-123 survivor.
- Group 123 artifact `mutmut-exact-evidence-34486140554-1-group-123`
  (`10168759110`) selected 19 mutants and recorded exactly one survivor:
  `app.cli.migrate_passwords.x__report_bcrypt_users__mutmut_1`.
  The isolated mutant changed only `_report_bcrypt_users`' default sample
  limit from 50 to 51; no test asserted that documented safety bound.

### 41.2 RED → GREEN remediation

- Added `test_report_bcrypt_users_default_sample_limit_is_fifty` to
  `tests/test_cli_migrate_passwords_closure.py`. It executes the real query
  path with ID opt-in and asserts the compiled PostgreSQL statement contains
  `LIMIT 50`, killing the exact default-value mutant without changing
  production behavior.
- Focused closure suite: **14 passed**; Ruff check/format pass for the changed
  test. The fix is committed as `5a04b3e34` (`test: cover bcrypt sample limit
  contract`). The prior exact error-message survivor remains covered by
  commit `5b5473320`.
- The full isolated pre-commit run completed successfully (Ruff, secrets,
  Bandit, mypy, no-Python2-except, actionlint, Semgrep and Renovate checks).
  The default Windows pre-commit cache ACL failure remains an environment
  limitation; no hook was bypassed.

### 41.3 Fresh-SHA boundary

1. Do not push while stale run `34486140554` is still active because the CI
   concurrency group would cancel expensive mutation evidence. After its
   terminal state, re-query every failed/cancelled job and artifact; any new
   survivor is handled with the same exact-evidence TDD loop.
2. Re-run the full local inventory after the final source commit, then push
   current SHA `5a04b3e34` (and any subsequent evidence-only commit) and treat
   only the resulting current-SHA matrix as merge evidence.
3. Keep all product/release/staging gates open until current-SHA CI and the
   post-merge exact-six image, digest smoke, Kubernetes/TLS/observability,
   device-CWV, chaos/rollback and SHA-bound audit evidence are captured.

The user-owned `docs/audits/AUDIT_PLATFORM_FULL.md`, `.tmp_preflight/`,
`.tmp_stryker_18/` and `.tmp_stryker_22/` remain untracked, untouched and
excluded from source commits.

## 42. Stryker runtime and CI fan-out audit (2026-09-10; read-only)

### 42.1 Evidence and diagnosis

- A bounded independent audit of stale run `34486140554` found no proven
  deadlock. The six remaining jobs were executing `Run fresh Stryker shard`
  and each was still within the configured `timeout-minutes: 120` envelope;
  the apparent multi-hour delay was the age of the whole run plus matrix
  queueing, not six jobs running for multiple hours.
- `.github/workflows/ci.yml` keeps 64 frontend shards but caps the matrix at
  `max-parallel: 6`. Shards 0–5 started near `14:26Z`; the final queue wave
  (54, 59–63) started between `18:35Z` and `19:23Z`. This explains the
  observed wall-clock latency without weakening any quality gate.
- `frontend/stryker.config.mjs` intentionally retains `vitest.related: true`,
  `coverageAnalysis: "perTest"` and `incremental: false`. Completed same-run
  evidence shows test-graph size, not mutant count alone, controls duration:
  shard 18 had 123 mutants and 238.80 tests/mutant (~101.8 min), shard 40 had
  995 mutants and 34.70 tests/mutant (~90.8 min), while shard 52 had 1098
  mutants and 9.03 tests/mutant (~51.4 min).

### 42.2 Safe optimization boundary

1. Preserve all 64 shards, full mutant/source/test inventory,
   `vitest.related`, per-test coverage analysis, non-incremental release
   evidence and the observed 20-runner account ceiling (not enforced by this
   repository's workflow files).
2. Do not increase fan-out on this stale run. After **three comparable green
   current-SHA runs**, use the recorded queue time, per-shard duration,
   tests-per-mutant and reserved mutmut/aggregation capacity to trial
   `max-parallel: 7`, then 8 only when the evidence proves the under-20-job
   budget remains safe. Roll back on any queue starvation, resource pressure,
   timeout or evidence-integrity regression.
3. Optimize only proven test-graph/setup hotspots; do not disable `related`,
   lower thresholds, reuse stale reports or hide timeout/cancelled targets.
   Keep per-shard telemetry as a required diagnostic artifact so future runs
   distinguish queue latency from a genuine execution stall.

The Stryker audit was read-only; no source, workflow or user-owned file was
changed by the audit.

## 44. Current bounded closure checkpoint (2026-09-10; local HEAD `6679aa3b`)

This checkpoint records new evidence and bounded fixes without promoting the
still-running historical PR matrix to current-SHA release evidence.

### 44.1 Identity and preservation boundary

| Field | Value |
|---|---|
| Branch | `egorribun` |
| Local source head | `6679aa3b9` (`fix: align injected routes with Dishka sessions`) |
| Remote source head | `78d03e1379a0c428ae509039d4942677ed89a7d9` |
| Local delta | 15 commits ahead; no uncommitted tracked changes |
| Stash | Empty; no stash mutation performed |
| User-owned untracked paths | `.tmp_preflight/`, `.tmp_stryker_18/`, `.tmp_stryker_22/`, `docs/audits/AUDIT_PLATFORM_FULL.md` — untouched and unstaged |

### 44.2 Bounded fixes and focused evidence

- `44ef05a60` hardens `CdcOutboxWorker` lifecycle ownership: active
  replication connections and fallback workers are tracked and closed on
  shutdown, including connect/stop races. Three lifecycle regressions are
  green; CDC unit/closure is **39/39** and CDC+outbox closure is **48/48**.
  ADR-037 explicitly defers production CDC wiring until DI/lifespan,
  PostgreSQL/NATS, ordering/idempotency and staging evidence exist.
- `6679aa3b` migrates the affected injected MFA, schedule and search routes to
  canonical Dishka request-session adapters and adds an ownership contract.
  The collection-order RED caused by the schedule import-isolation suite is
  fixed; the combined focused set is **73/73**, Ruff and mypy pass.
- Old run `34486140554` exposed one exact mutmut survivor in execution group
  91: `app.cli.migrate_passwords.x__report_bcrypt_users__mutmut_6`. The
  mutant only changed the negative-limit error text; the former regex asserted
  a substring and let it survive. `5b5473320` asserts the exact error string;
  focused CLI tests are green (**20/20**). This fix still requires a fresh
  current-SHA mutmut run.
- `python verify_harness.py --repo-only` remains **29/29**. Frontend
  client+SSR/PWA production build completed successfully; generated WASM
  provenance/binaries were restored after inspection and are not part of the
  source delta. `git diff --check` passes.

### 44.3 Remote-run boundary and next actions

- Run `34486140554` is still based on remote SHA `78d03e137`; its run-level API
  remains stale while Jobs/PR checks show mutation execution in progress. The
  current historical failure is the single group-91 survivor above; all other
  observed terminal checks are success or intentional skip so far. This run
  contributes no current-SHA release evidence.
- Continue polling until the run is terminal and inventory every failure,
  cancellation, timeout, artifact and annotation exactly once. Do not push
  while it is active because `ci.yml` uses `cancel-in-progress: true`.
- After terminal state, run final local inventory/pre-commit checks and push
  the current `egorribun` head non-force. Require a fresh matrix to prove the
  exact mutmut survivor fix, BE-04 session ownership, BE-08 lifecycle tests,
  hidden JUnit artifacts, complete Stryker/mutmut ledgers and current-SHA
  provenance before any release claim.
- BE-04 legacy domains, BE-08 production integration, live BE-02 PostgreSQL
  migration evidence, current INFRA/SEC reports and all merge/staging/release
  gates remain open.

## 45. Go mutation diagnostic governance checkpoint (2026-09-10; `1104739ba`)

- `1104739ba` implements ADR-038's fail-closed advisory boundary for Go
  mutation diagnostics. The required PR Go coverage/race/security producer is
  independent; diagnostic execution is schedule/manual-only and no longer
  uses job-level `continue-on-error` to hide tool failures.
- Every changed non-generated Go source target is written to an exact
  `expected-targets.txt` ledger before workers start. Finalization materializes
  an outcome for each target; missing or failed targets are explicitly
  `unreported`/`failed`, report and source hashes are retained, and a
  `complete` summary is rejected unless all expected targets succeeded.
- Governance contracts and workflow fail-closed tests are green (**38/38**);
  isolated hooks including actionlint, detect-secrets, Semgrep and mypy pass.
  This is not a Go mutation score claim: the diagnostic remains non-contract
  evidence and cannot replace required native coverage, race or security
  checks.

## 43. Current local audit-policy checkpoint (2026-09-10; snapshot HEAD `a9be722e5`)

This checkpoint is a pre-push source snapshot. It records local changes and
evidence only; the old remote matrix remains non-terminal and cannot certify
this snapshot.

### 43.1 Source and preservation boundary

- Branch: `egorribun`; snapshot `HEAD`:
  `a9be722e51f876a0030cdec65692b2a78f861e16`.
- Remote `origin/egorribun` remains
  `78d03e1379a0c428ae509039d4942677ed89a7d9`; local delta is 11 commits,
  with no tracked worktree changes.
- User-owned untracked files remain exactly the six inventoried paths under
  `.tmp_preflight/`, `.tmp_stryker_18/shard-018/`,
  `.tmp_stryker_22/shard-022/` and `docs/audits/AUDIT_PLATFORM_FULL.md`;
  stash is empty and no cleanup was performed.

### 43.2 Bounded audit closure work

- ADR-034 formalizes Helm as the sole canonical application deployment
  producer; infrastructure/Helm contracts are green (**211/211**).
- ADR-035 plus `pyproject.toml`/`uv.lock` add upper bounds to all 32
  previously unbounded external production requirements; dependency-policy
  and gitleaks contracts are green (**16/16 combined**), and `uv lock --check`
  passes.
- ADR-036 records the measured BE-02 defaults inventory (45 tables; 134
  effective defaults: 26 dual, 91 Python-only and 17 server-only, with source AST
  cross-checks) and a PostgreSQL catalog/preflight migration policy; no unsafe
  blanket DDL rewrite was attempted.
- `app/AGENTS.md` now uses the same scoped invariant: applicable defaults are
  dual-declared, while UUIDv7 IDs, signing keys, JSON topic defaults,
  `Computed`, and `default=None` require explicit ADR-036 inventory entries.
- Isolated pre-commit hooks pass (Ruff, detect-secrets, hardcoded-secrets,
  Bandit, mypy, strong-env-secrets, no-Python2-except, actionlint, Semgrep and
  Renovate); harness is **29/29** and frontend typecheck pre-push dry-run is
  green.

### 43.3 CI and remaining boundary

- Old run `34486140554` is bound to remote SHA `78d03e137` and remains
  non-terminal. Latest Jobs API snapshot: **230 success**, **12 skipped**,
  **16 in progress**, **52 queued**, with no failure/cancellation/timeout.
- Read-only scheduler analysis measured current PR mutation usage at
  `6 + 10 = 16` runners (Stryker plus mutmut), leaving four of the 20-job
  budget; manual/nightly workflows can overlap and must not be raised until
  three comparable green runs justify a change.
- Next safe action is to await terminal old-run classification, perform the
  final diff/pre-push inventory, push this complete delta without force, and
  require a fresh current-SHA matrix. BE-04/BE-08, live BE-02 PostgreSQL
  migration evidence, and all merge/main, immutable-image, staging,
  real-device and release gates remain open.

## 42. Current local verification checkpoint (2026-09-10; local HEAD `f5bb93655`)

This checkpoint records a fresh read-only verification pass while the old
remote matrix is still running. It does not promote that remote run to
current-SHA evidence and does not close the release boundary.

### 42.1 Identity and preservation

- Active branch is `egorribun`; local `HEAD` is `f5bb936559ca13196571ea5ee83008b23bce07be`.
- `origin/egorribun` remains `78d03e1379a0c428ae509039d4942677ed89a7d9`; local
  branch is five commits ahead and has no tracked worktree changes.
- `git stash list` is empty and no stash operation was performed.
- The six user-owned untracked files remain untouched and unstaged:
  `.tmp_preflight/PREFLIGHT_ARTIFACT.json`, the two files under
  `.tmp_stryker_18/shard-018/`, the two files under
  `.tmp_stryker_22/shard-022/`, and `docs/audits/AUDIT_PLATFORM_FULL.md`.
- `git diff --check` passes; `git fsck --full --no-progress` exits zero with
  no missing, corrupt or error objects. No files, Docker resources or user
  state were deleted or overwritten.

### 42.2 Fresh local evidence

- `python verify_harness.py --repo-only`: **29/29 passed**.
- `frontend/npm run typecheck`: exit **0**.
- Isolated `pre-commit run --all-files`: **Passed** for Ruff check/import/format,
  detect-secrets, hardcoded-secrets, Bandit, mypy, strong-env-secrets,
  no-Python2-except, actionlint, Semgrep and Renovate validation. The manual
  Trivy hook is not part of the default stage and was not misclassified as a
  pass.
- The user-owned artifact SHA-256 prefixes remain stable (`47F859B3FEFE`,
  `05102C77E54A`, `8D9DAE6BCA70`, `336349DB0D4B`, `40FA747094EC`,
  `E3E5F87AA93C`), matching the prior preservation inventory.

### 42.3 Remote-run boundary

- Run `34486140554` is still tied to the old remote source SHA
  `78d03e1379a0c428ae509039d4942677ed89a7d9`; it is not evidence for local
  `f5bb93655` and remains non-terminal.
- Latest Jobs API snapshot: **204 completed-success**, **12 completed-skipped**,
  **16 in progress**, **78 queued**, with no failure, cancellation or timeout.
- Because `.github/workflows/ci.yml` uses `cancel-in-progress: true`, the five
  local commits remain intentionally unpushed until this old run reaches a
  terminal state. The next action is a non-force push followed by a fresh
  current-SHA matrix and complete artifact/annotation inventory.

## 41. Current local and remote continuation checkpoint (2026-09-10; local HEAD `1a22082de`)

This checkpoint records the latest bounded progress without promoting the
older remote matrix to current-SHA evidence. It supersedes neither the
release boundary in §40.3 nor the requirement to obtain a terminal fresh
matrix after the next push.

### 41.1 Identity and preservation boundary

| Field | Value |
|---|---|
| Branch | `egorribun` (tracking `origin/egorribun`) |
| Local source head | `1a22082de1f573612c7271189af2aaa8c96e8c51` |
| Remote source head | `78d03e1379a0c428ae509039d4942677ed89a7d9` |
| Local delta | 4 commits ahead; no uncommitted tracked changes |
| Stash | Empty; no stash mutation performed |
| User-owned untracked paths | `.tmp_preflight/`, `.tmp_stryker_18/`, `.tmp_stryker_22/`, `docs/audits/AUDIT_PLATFORM_FULL.md` — untouched and unstaged |

### 41.2 New bounded implementation and local evidence

- `d95a2ed25` opts the frontend aggregate JUnit upload into hidden files;
  `d3a03a982` makes aggregate and shard JUnit uploads fail closed when a file
  is missing. The focused workflow regression is green, and the full workflow
  contract suite remains green.
- `1a22082de` adds a mutation-runner-only guard for the upstream OTel finite
  metric-reader dead-`WeakMethod` at-fork callback. Live callbacks and
  unrelated callback failures retain their original behavior; no test,
  source or mutant inventory is skipped or reclassified.
- Focused post-change evidence: `tests/test_run_mutmut_with_stats.py` **10/10**;
  combined mutation/workflow contract selection **175/175**;
  `python verify_harness.py --repo-only` **29/29**; isolated pre-commit hook
  run (Ruff, detect-secrets, strong-env-secrets, no-Python2-except, Semgrep
  and Renovate validation) passed; pre-push typecheck dry-run passed.
- The guard's real `PeriodicExportingMetricReader` callback shape is covered
  by a regression test on this Windows host through a deterministic fork-hook
  capture. Linux mutmut and the complete current-SHA mutation inventory still
  require remote confirmation.

### 41.3 Superseded remote run boundary

- Run `34486140554` belongs to remote source `78d03e137`, not local source
  `1a22082de`. At the latest observation it contained 310 jobs: 189 success,
  12 intentional skips, 16 in progress and 93 queued; no failure, cancellation
  or timeout was observed. The run is non-terminal and therefore contributes
  no release evidence.
- Its sole annotation remains the old missing aggregate
  `frontend-vitest-report`, caused by uploading hidden `.vitest-reports`
  without `include-hidden-files`. That root cause is addressed by `d95a2ed25`
  and `d3a03a982`; the new SHA must prove the artifact exists and that no
  annotation remains.
- The old run is intentionally not cancelled or reused. Because the workflow
  uses `cancel-in-progress: true`, pushing the local delta before its terminal
  state would discard an expensive in-flight mutation attempt.

### 41.4 Required next actions

1. Poll `34486140554` until terminal and inventory every final status, artifact
   and annotation exactly once; never mix its evidence with local SHA.
2. Run the final local diff/pre-commit inventory check, then push `1a22082de`
   (and this checkpoint if committed) without force-push or main mutation.
3. Await a fresh PR matrix and companion workflows. Require the aggregate
   hidden JUnit artifact, full Stryker/mutmut ledgers, coverage/provenance
   hashes, Go race/security evidence, and zero at-fork exceptions before
   accepting the quality gate.
4. Only after current-SHA terminal green evidence proceed to merge/main,
   exact-six immutable images, SBOM/provenance/attestations, digest Docker
   smoke, Kubernetes/TLS/observability, real-device CWV, chaos/rollback,
   production release and the final SHA-bound audit.

## 39. Current local closure state and corrected remote boundary (2026-09-09)

This correction supersedes the time-sensitive statements in §38. The source
SHA named there (`752dabf9fd165084df0d897eef39fe93095e0ebb`) and run
`34287653082` are historical evidence only: that run reached a terminal
failure on the old source and is not evidence for the commits recorded below.

### 39.1 Changes now committed locally

- `cd2510691` scopes generated WASM provenance from secret scanning with exact
  path/format contracts; `67c910e03` removes the stale CLI migration finding
  and refreshes the generated baseline metadata.
- `c5aa0b821` closes file-processor nil handling before Temporal side effects
  and updates the corresponding tests; `2d4d025b4` closes Pact NATS message
  provider handlers, pins the SBOM/vulnerability Go setup to 1.26.6, and
  selects a stable PyO3 ABI for fuzz targets; `882c1c4` documents the exported
  file-processor validation limit; `868692489` makes the Rust fuzz inventory
  check shellcheck-safe; `fcd35e909` makes WASM provenance ordering locale
  independent; `0e89c8a62` patches frontend dependency advisories; and
  `5b3b102c9` raises the frozen `httpx2`/`httpcore2` line to 2.12.0.
- The frontend dependency audit is currently clean for high/critical findings
  (seven low findings remain in non-release tooling). The Python OSV batch
  audit and allowlist validator are green for the frozen production set.

### 39.2 Reproducible local evidence

- `python verify_harness.py --repo-only`: 29/29 passed.
- Frontend WASM provenance/validator tests: 11/11 passed; `ensure-wasm.mjs`
  and Windows `cargo check` for the fuzz binary pass with the `abi3-py311`
  configuration.
- The last canonical frontend run before the dependency refresh recorded
  651/651 files, 6656/6656 tests, zero unhandled errors and 100% statements,
  branches, functions and lines. A fresh dependency-refresh `npm run test:ci`
  is still running and must finish with a terminal result before this evidence
  is renewed for the current SHA.
- Isolated pre-commit runs for every code commit passed the applicable
  detect-secrets, strong-env-secrets, no-Python2-except, actionlint, Semgrep
  and Renovate checks. The shared default pre-commit cache had a Windows
  permission error; no hook was bypassed, and the isolated cache is the
  reproducible path used for commits.

### 39.3 Remaining current-SHA work

1. Finish the in-flight frontend regression, then run typecheck, lint, build,
   WASM checks and the focused test matrix again after all commits.
2. Append the final checkpoint only after `git diff --check`, an isolated full
   pre-commit run, backend/go/rust focused gates and a clean inventory of the
   four user-owned untracked paths.
3. Push the resulting `egorribun` SHA and wait for a **new** PR 1266 matrix and
   companion workflows. Download every terminal artifact and classify every
   failure by exact log. Confirm current-SHA report hashes, coverage/mutation
   denominators, Go race/sanitizer/fuzz evidence, Schemathesis, Lighthouse,
   E2E and security gates; do not reuse run `34287653082`.
4. Re-query Dependabot after the `httpx2` and Go toolchain fixes. Alerts
   `#117/#107` were verified as stale unused root-manifest records and closed
   as `not_used`; the newly surfaced `httpx2` alert remains open remotely until
   GitHub rescans the pushed source.
5. Keep the external release boundary explicit: merge-to-main
   recertification, exact-six immutable image/SBOM/provenance producer,
   digest Docker smoke, Kubernetes/TLS/ExternalSecrets/observability,
   real-device CWV, chaos/restart/rollback, production release and the final
   SHA-bound `AUDIT_QUALITY_CLOSURE_<sha>.md` still require direct evidence.

The user-owned `docs/audits/AUDIT_PLATFORM_FULL.md`, `.tmp_preflight/`,
`.tmp_stryker_18/` and `.tmp_stryker_22/` remain untracked, untouched and
excluded from source commits.

## 40. Security/dependency closure before fresh CI (2026-09-09; local HEAD `e2a0fce10`)

### 40.1 Current source commits

- `a7c59fb1e` binds every privileged SBOM/report writer and the main
  vulnerability gate to `refs/heads/main` in addition to the non-PR guard;
  the PR vulnerability gate remains read-only. This closes the
  workflow-dispatch trust-boundary path without changing the PR check name.
- `eb6cfe043` reduces Rust fuzz permissions to `contents: read` and sets
  `persist-credentials: false` on both checkout steps before executing PR
  code or using caches.
- `727c9aed5` makes the checked-in WASM provenance validator reject unknown
  top-level metadata fields and adds a regression test, preserving the exact
  source/package byte inventory contract.
- `43eaab7e6` requires the patched `urllib3>=2.7.0,<2.8` line;
  `71ae71040` pins the root npm override to `js-yaml^4.3.2`; and
  `e2a0fce10` upgrades all actual gRPC module requirements, sums and Docker
  build overrides from 1.83.1 to 1.83.2. No artificial dependency was added
  to the root, logging, SpiceDB or CLI modules that do not import gRPC.

### 40.2 Verification completed on this SHA

- Focused Python contract/security/Docker suite: **148 passed** using an
  isolated pre-commit cache. The default Windows cache still has an ACL error
  opening a cloned `.pre-commit-hooks.yaml`; this is an environment defect,
  not a skipped hook or a code suppression.
- WASM/provenance unit tests: **12 passed**; full `npm run test:wasm` suite:
  **248 passed**; `verify-wasm-artifacts.mjs` and `ensure-wasm.mjs` pass.
- Frontend typecheck, lint, production client+SSR/PWA build and post-security
  WASM checks pass. The dependency-refresh canonical `npm run test:ci` run
  completed **651/651 files, 6656/6656 tests, zero unhandled errors, 100%**
  statements/branches/functions/lines; the new provenance test is additionally
  covered by the 248-test WASM suite.
- Python `uv lock --check` and the frozen OSV batch/audit allowlist pass;
  root `npm ci --ignore-scripts --no-audit` and root `npm audit
  --package-lock-only --audit-level=high` pass with zero high/critical/
  moderate findings. Frontend audit likewise has zero high/critical findings;
  only seven low AI-SDK/MSW transitive advisories remain and no breaking
  downgrade was applied without compatibility evidence.
- All five tracked Go modules pass `go test ./...`, `go mod tidy -diff` and
  `go mod verify`; local tests used Go 1.26.5 while the security/build
  workflows explicitly install patched Go 1.26.6. Docker contract tests pass
  with the 1.83.2 overrides. Isolated full pre-commit passes Ruff,
  detect-secrets, gitleaks/hardcoded-secrets, Bandit, mypy, no-Python2-except,
  actionlint, Semgrep and Renovate validation.

### 40.3 Fresh-CI boundary and remaining work

1. Push exactly `e2a0fce10136f43e1fde59ad7605f18fa1876f04` (plus any subsequent
   contract/documentation commits) to `origin/egorribun`; old run
   `34287653082` at `752dabf9f` remains stale and is never reused.
2. Re-query GitHub Dependabot after the rescan. Alerts #125/#139/#140–#143,
   #128–#130/#134 and #131–#138 should close only from the patched manifests;
   alerts #117/#107 remain historical `not_used` dismissals. Any still-open
   high/critical alert requires another fixed-version investigation.
3. Await every new matrix/companion workflow to terminal state and download
   all artifacts. Validate current source/tested-merge SHA, report hashes,
   full coverage/mutation denominators, Go race/sanitizer/fuzz, Pact,
   Schemathesis, Lighthouse, E2E, CodeQL, SBOM and performance evidence.
4. Keep CI fan-out unchanged until the required three comparable green runs
   prove a safe under-20-job optimization; no inventory reduction, exclusion,
   quarantine or unproven suppression is allowed.
5. External release gates are still intentionally open: merge-to-main
   recertification, exact-six immutable image/SBOM/provenance/attestation
   producer, digest Docker smoke, Kubernetes/TLS/ExternalSecrets/
   observability staging, real-device CWV, chaos/restart/rollback,
   production release and final SHA-bound `AUDIT_QUALITY_CLOSURE_<sha>.md`.

User-owned `docs/audits/AUDIT_PLATFORM_FULL.md`, `.tmp_preflight/`,
`.tmp_stryker_18/` and `.tmp_stryker_22/` remain untracked, untouched and
excluded from all source commits.

## 47. Current-SHA Semgrep ledger correction and CI capacity audit (2026-09-10; source `3acb592d8`)

### 47.1 Current-SHA failure and fail-closed response

- Fresh run `34527417327` started from `5662a4750c16913171bbb557674e26fe94219eaf`
  and produced one independent failure before mutation execution:
  `Security Audit / Semgrep SAST` (job `103039590954`). The job's annotation
  identified `app/workers/cdc_outbox.py:508` as an inline-suppressed finding
  missing from the reviewed ledger.
- Code Scanning analysis `1757721940` and the Semgrep alert instances confirmed
  the exact pair of CDC findings:
  `python.lang.security.audit.formatted-sql-query.formatted-sql-query` and
  `python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query`,
  each with region `508–510`. The policy still referenced the pre-refactor
  region `488–490`; this was line-bound provenance drift, not a new suppression
  or a scanner false positive.
- The run had not entered Stryker or mutmut execution when the blocker was
  captured. It was cancelled through the GitHub Actions API to avoid spending
  the long mutation critical path on a known failing source. Cancellation is
  not evidence and the run is excluded from every release claim.

### 47.2 RED → GREEN policy correction

- Updated both existing CDC entries in
  `security/semgrep-suppression-policy.json` from `488–490` to the exact
  current `508–510` region. The sanitization implementation, rule IDs, owners,
  expiry and rationale are unchanged; no entry was added or broadened.
- JSON parsing and the Semgrep validator/security workflow contract suite are
  green (**39/39**); isolated pre-commit runs detect-secrets,
  hardcoded-secrets, no-Python2-except, actionlint, Semgrep and Renovate checks
  successfully. Source commit: `3acb592d8` (`fix: align semgrep suppression line ranges`).
- The next fresh Semgrep SARIF must contain the same exact 15 reviewed
  in-source results and no unledgered finding; a missing or extra result remains
  fail-closed. Do not close Code Scanning alerts by hand in place of a valid
  current-SHA SARIF/ledger pair.

### 47.3 CI fan-out audit and bounded speed plan

- Read-only workflow inventory found 59 top-level jobs, 64 Stryker shards
  (`max-parallel: 6`, 120-minute timeout), 8 mutmut-stats shards
  (`max-parallel: 8`), and 1–128 mutmut execution groups
  (`max-parallel: 10`, 360-minute timeout). Backend, Go, frontend/Lighthouse,
  E2E and Schemathesis matrices have no local cap, while companion workflows
  add roughly 40 eligible leaf jobs. Matrix caps are workflow-local, so the
  repository has no global semaphore enforcing the operational 20-runner
  ceiling.
- Historical run `34486140554` consumed the Stryker critical path for about
  356 minutes (longest shard about 105.2 minutes) and completed in about 384.5
  minutes; this proves queue/critical-path pressure but not a deadlock or a
  timeout defect. Current run snapshots also showed hosted-runner saturation.
- Preserve every source/test/mutant and all fail-closed validators. Keep
  Stryker 6 and mutmut 10 unchanged until three comparable green current-SHA
  runs provide queue, timeout, resource and billed-minute evidence. Only then
  trial a cap or shared dependency artifact; any optimization must retain
  checksum/provenance validation, exact shard ledgers and the workflow-local
  under-20-job budget. Never solve latency by raising timeouts, disabling `vitest.related`,
  changing coverage/mutation thresholds or adding exclusions.

### 47.4 Acceptance boundary

1. Push the policy correction plus this checkpoint as one new non-force
   `egorribun` SHA and treat its PR matrix as the only valid CI evidence.
2. Require Semgrep, CodeQL, dependency/security scans, coverage/preflight,
   all 64 Stryker shards, all mutmut groups, E2E/browser, Lighthouse,
   Schemathesis, Go/Rust and aggregate CI Success to reach terminal success
   with current-SHA hashes and complete denominators.
3. Record any subsequent failure from its exact job annotation/artifact before
   changing code. Keep merge-to-main, exact-six immutable images, digest Docker
   smoke, Kubernetes/TLS/observability, real-device CWV, chaos/rollback,
   production release and final SHA-bound audit explicitly external.

## 49. Current local hardening checkpoint (2026-09-13; pre-push)

This checkpoint records bounded work completed while the previous PR matrix is
still running. It does not promote that matrix to current-SHA evidence and it
does not change the mutation inventory, runner caps or release thresholds.

### 49.1 Source identity and preservation boundary

| Field | Value |
|---|---|
| Branch | `egorribun` |
| Local source head | derive with `git rev-parse HEAD` at verification time (the historical pre-push snapshot was `6a40a305a`) |
| Remote source head | derive with `git rev-parse origin/egorribun` at verification time (historical snapshot `d85180438`) |
| Local delta | derive with `git rev-list --count origin/egorribun..HEAD` at verification time; tracked worktree must be clean |
| User-owned untracked paths | `.tmp_preflight/`, `.tmp_stryker_18/`, `.tmp_stryker_22/`, `docs/audits/AUDIT_PLATFORM_FULL.md` — untouched and unstaged |
| Previous PR matrix | run `34743194178`, source `d8518043898cc6a39c295a37dadca230e06baf57`, non-terminal |

The local commits are intentionally small and independently reviewable:
the two exact mutmut survivor contracts (`8f3c699c4`), quality/CI reference
alignment (`a76d3a275`), Stryker timeout/provenance notes (`88009228e`,
`fb434d3a2`, `25f4813f9`), service/NATS contract alignment (`757543d2c`) and
event-handler cancellation cleanup (`ed486ce53`), the measured dual-default
inventory refresh (`f593648e7`) and its runtime inventory regression
(`6a40a305a`). No commit contains a
`Co-Authored-By` trailer.

### 49.2 Current local evidence

- NATS CORE publish disconnect behavior is explicitly covered by warning and
  counter assertions; the focused module suite is **4/4**.
- EventBus external cancellation and timeout paths now await the cancelled
  chain, allowing `asyncio.gather` to finish owned handler cleanup. The focused
  event suite is **12/12**, including asynchronous cleanup barriers.
- `python verify_harness.py --repo-only` is **29/29**; frontend typecheck and
  lint are green; `git diff --check` is clean. The event change passed the
  isolated pre-commit stack (Ruff, detect-secrets, Bandit, mypy, actionlint,
  Semgrep and Renovate validation).
- The external platform audit has no remaining P0/P1 in frontend, Go or Rust
  by source inspection. Backend BE-02 (phased dual-default migration) and
  BE-04 (legacy Depends/Dishka coexistence) remain explicitly architectural
  follow-ups; they are not silently reclassified as complete. Rust P3
  workspace/fuzz/dependency hygiene remains non-release debt.

### 49.3 Remote-run boundary and next action

At the latest paginated Jobs API snapshot (`2026-09-13T10:53:30Z`), run
`34743194178` contains 310 jobs: 238 completed, 16 in progress and 56 queued.
The only terminal non-success jobs are the cancelled Stryker shard 24/64 (the
configured 120-minute hard cap) and stale mutmut execution groups 29 and 41;
their survivors correspond to contracts fixed in local commit `8f3c699c4`.
The run remains non-terminal and contributes no release evidence.

1. Continue bounded polling until this old run is terminal; inventory every
   late failure, cancellation, timeout, annotation and artifact exactly once.
2. Re-run the final local inventory, then push the verified current `HEAD` (and
   this checkpoint) non-force to `origin/egorribun`. The resulting current-SHA matrix is the
   only accepted CI evidence; stale run results must not be reused.
3. After a terminal fresh matrix, obtain complete coverage/mutation manifests,
   security/API/infra/browser evidence and only then evaluate the external
   merge, immutable-image, Docker, Kubernetes/TLS/observability, device-CWV,
   chaos/rollback, production and SHA-bound audit gates.

### 49.4 Checkpoint identity reconciliation (2026-09-13)

The checkpoint identity update itself is commit `427662022bc3cfcbbb6fe411e6da28b8784d3ec0`
(`docs: track inventory checkpoint identity`). The current local branch is
therefore twelve commits ahead of `origin/egorribun`, with no tracked
changes; the four user-owned untracked paths listed in §49.1 remain untouched.
This documentation-only commit does not alter source, test, mutation
inventory, runner caps, thresholds or the requirement to wait for the old run
to become terminal before the non-force push.

### 49.5 Measured inventory reference refresh (2026-09-13)

The stale BE-02 figures in the historical narrative were corrected to the
measured 45-table inventory in commit `c0f3db144`
(`docs: refresh default inventory references`). Any later documentation-only
checkpoint commits do not change that inventory or runtime behavior; derive
the exact push SHA and ahead count from `git rev-parse`/`git status` immediately
before the non-force push. No user-owned untracked paths were changed.

### 49.6 CI acceleration checklist audit (2026-09-13)

The supplemental acceleration checklist was audited against the current
workflow, scripts and live diagnostic data. It is not a release certificate;
the old run is bound to an obsolete SHA and remains non-terminal.

| Checklist item | Disposition | Evidence / remaining boundary |
|---|---|---|
| Machine timing ledger (queue/setup/test/upload, concurrency, RSS/CPU, retries/timeouts) | `PARTIAL` | `scripts/quality/analyze_ci_critical_path.py` emits per-job queue/setup/test/artifact timing, aggregate p50/p95 distributions, observed peak concurrency and fail-closed retry/timeout classification from the API's workflow-attempt and job/step-conclusion fields. Diagnostic reports are explicitly lower-bound and strict reports now require a detached same-run artifact-selector provenance record bound to repository, run/attempt, source/tested SHA, workflow identity, workflow-file hashes, artifact identity and DAG digest; a structural-only sidecar is rejected for strict analysis. The selector validates server-issued metadata and digest format but does not download/hash archive bytes, and no workflow invokes the analyzer end-to-end yet; strict output is therefore not a release certificate until a trusted producer verifies the archive and provenance. The tool remains on-demand and does not yet collect runner RSS/CPU, billed minutes or a mandatory current-run artifact. |
| Duration-aware Stryker/mutmut sharding | `PARTIAL` | `mutmut_shard_matrix.py` and the stats-derived budget use durations; Stryker accepts a verified same-run historical-cost candidate. A current-SHA timeout (shard 24) and three comparable green runs are still required before tuning. |
| Immutable dependency/artifact caches | `PARTIAL` | npm/uv/Cargo/pre-commit/Stryker caches and SHA/run-bound artifact selectors are present. Repeated shard setup remains, and Go image builds have no scoped BuildKit module/build-cache mounts; benchmark before changing. |
| Required PR gates vs advisory/nightly jobs | `PARTIAL` | `quality/release-required-checks.json`, advisory flags and nightly/manual workflows exist. Actual branch-protection contexts and duplicate check topology still need a live ruleset inventory; path filters cannot be changed blindly. |
| Transient-only automatic retry | `PARTIAL` | Targeted retries exist for known network/tool failures (for example WASM, Trivy and OSV). There is no repository-wide classifier that preserves the first failure and all artifacts for every retryable job. |
| Unified check/artifact/owner/duration/runbook catalog | `PARTIAL` | CODEOWNERS, artifact validators and focused runbooks exist. A machine-validated catalog covering every workflow/check and expected duration is not yet present. |
| Compact CI health report (p50/p95/queue/skips) | `OPEN` | Historical snapshots and the analyzer provide point-in-time queue/utilization data, but no continuously published current-run p50/p95 health artifact exists. |
| Local parallel fast-preflight | `IMPLEMENTED-LOCAL / EVIDENCE-PENDING` | `uv run python scripts/fast_preflight.py` now fans out frontend typecheck/lint, backend mypy/Ruff, `verify_harness.py --repo-only` and focused CI-contract tests with shell-free process ownership, bounded timeouts, isolated pytest cache behavior and one fail-closed JSON report. The helper has focused unit contracts; a full local invocation is still a developer aid and never substitutes for the required current-SHA CI matrix. |
| Heartbeat diagnostics for long jobs | `PARTIAL` | Mutmut has a deadline-aware watchdog and fail-closed evidence finalization. A generic heartbeat/diagnostic monitor for all genuinely stalled jobs is not implemented. |

The analyzer applied to live run `34743194178` at the historical snapshot
recorded for this section reported 310 jobs, a 19-job observed peak under the diagnostic cap of 20 and 0.704366
average slot utilization; the data also exposed repeated checkout/setup and
artifact steps. This is useful for choosing work, not evidence to relax caps.
The safe order remains: wait for the old run to terminate, push one coherent
current-SHA change set, collect three comparable green runs, then run a
bounded Stryker 7→8 or lane-split experiment with automatic rollback on queue,
timeout, resource, reliability or provenance regression.

## 50. CI catalog governance and current-run evidence checkpoint (2026-09-13)

This overlay supersedes the stale catalog disposition in §49.6 while keeping
the release boundary unchanged. It records repository-local work only; the
current remote matrix is still bound to the older remote SHA until the catalog
commit is pushed after the active run reaches a terminal state.

### 50.1 Source identity and preservation

| Field | Value |
|---|---|
| Branch | `egorribun` |
| Local source head | derive with `git rev-parse HEAD` at verification time (latest checkpoint before this docs commit: `57d11f958`) |
| Remote source head | `d9a964be0896cb90377de51ba37aaa27333f91d9` |
| Local delta | derive with `git rev-list --count origin/egorribun..HEAD` at verification time |
| User-owned untracked paths | `.tmp_preflight/`, `.tmp_stryker_18/`, `.tmp_stryker_22/`, `docs/audits/AUDIT_PLATFORM_FULL.md` — untouched, unstaged |
| Active remote matrix | run `34761805023`, source SHA `d9a964be0`, PR #1266, non-terminal |

No force-push, merge, branch deletion, stash mutation, or user-file staging was
performed. The local catalog commit is documentation/quality governance only;
it does not alter workflow execution, mutation inventory, caps, thresholds or
security policy.

### 50.2 Catalog expansion completed locally

Commit `ce3b07580` (`docs: expand CI check catalog governance`) extends the
machine-validated catalog from the 55-workflow/180-source-job inventory to
include:

- four provider-managed protected contexts (`CodeQL`, `Checkov`, `spectral`,
  `zizmor`) with integration ID `57789`, explicit external ownership and
  required-event metadata;
- eight reusable-workflow/matrix expansion records covering 44 exact protected
  contexts, caller/reusable job bindings, profiles, owners, runbooks and
  source references;
- strict schema and fail-closed validator checks for duplicate/colliding
  contexts, canonical repository paths, profile/classification/event
  consistency, workflow-call bindings and matrix evidence;
- focused tests retained and extended from 10 to 17 cases.

Independent local verification completed:

    uv run python scripts/quality/validate_ci_check_catalog.py                 # OK (55 workflows, 180 jobs)
    uv run pytest -q -p no:cacheprovider tests/test_ci_check_catalog.py         # 17 passed (three independent runs)
    uv run ruff check scripts/quality/validate_ci_check_catalog.py tests/test_ci_check_catalog.py  # passed
    uv run ruff format --check scripts/quality/validate_ci_check_catalog.py tests/test_ci_check_catalog.py  # passed
    Draft202012Validator.check_schema + catalog validation                       # schema OK; 0 errors
    git diff --check HEAD~1..HEAD                                                # clean

The live active ruleset was refreshed read-only: 92 required contexts were
present, all four provider contexts used integration ID `57789`, and the
catalog's 48 supplemental contexts matched the live selected set exactly
(48/48, no catalog-only or ruleset-only entries). The volatile ruleset ID and
conclusions remain intentionally outside the static catalog.

### 50.3 Independent security review

Codex Security diff scan `cbe4b9c3-74db-457b-94f4-0a07e3709381` reviewed the
exact range `d9a964be0..ce3b07580` across all three changed source files. The
scan completed with zero reportable findings and complete diff-surface
coverage. Daybreak access was `not_granted` (advisory only), so protected
provider output display remains a limitation; this does not replace the live
ruleset refresh or current-SHA CI evidence.

### 50.4 Active run and timing evidence

Run `34761805023` remains non-terminal and has no observed failure,
cancellation or timeout. The latest snapshot has 310 jobs, 119 successful,
12 skipped by workflow guards, and 179 queued/in progress while the mutation
phase drains under the existing fan-out. Observed peak concurrency is 19 under
the diagnostic cap of 20; no cap change is authorized from this single run.

The diagnostic lower-bound report is retained outside the repository at
`C:\Temp\ci-34761805023-diagnostic-20260913.json`. It measured wall-clock
lower bound `2668s`, average slot utilization `0.351949`, queue p50/p95
`96s/365s`, test p50/p95 `50s/760s`, setup p50/p95 `29s/109s`, and artifact
p50/p95 `0s/5s`. Repeated checkout/setup/install/upload steps are now quantified
for later cache/sharding experiments. This report is diagnostic-only, not a
strict release certificate, because the run is non-terminal and no trusted
same-run DAG/artifact-selector provenance was supplied.

### 50.5 Updated acceleration dispositions

| Checklist item | Disposition after this checkpoint |
|---|---|
| Machine timing ledger | `PARTIAL`: diagnostic analyzer and report are proven; strict same-run producer, runner RSS/CPU, billed minutes and continuous artifact publication remain open |
| Duration-aware sharding | `PARTIAL`: historical-cost plumbing exists; three comparable green runs are still required before cap/lane experiments |
| Immutable dependency/artifact caches | `PARTIAL`: cache namespaces and provenance selectors exist; repeated setup remains measured work |
| Required vs advisory catalog | `IMPLEMENTED-LOCAL / LIVE-REVIEW-PENDING`: static source/provider/expansion catalog and validator are green; refresh ruleset after push and compare all required contexts |
| Transient-only retries | `PARTIAL`: targeted retries exist; repository-wide first-failure-preserving classifier remains open |
| Unified check/artifact/owner catalog | `IMPLEMENTED-LOCAL`: 55 workflows/180 source jobs plus protected supplemental contexts are schema-validated |
| Compact CI health report | `IMPLEMENTED-LOCAL / EVIDENCE-PENDING`: existing `ci-success` now publishes a run/attempt-bound diagnostic JSON+Markdown artifact and step-summary projection; current-SHA terminal runs are still required |
| Local parallel fast-preflight | `IMPLEMENTED-LOCAL / EVIDENCE-PENDING`: focused contracts are green; current full developer invocation remains non-release evidence |
| Generic heartbeat diagnostics | `PARTIAL`: mutation watchdog exists; cross-job stall diagnostics remain open |

### 50.6 Next safe actions

1. Continue bounded polling of run `34761805023` and inventory every terminal
   failure/cancellation/timeout/artifact exactly once; do not cancel or restart
   it merely because mutation queues are long.
2. After terminal success (or after exact failure remediation), run the final
   local inventory and push the current `HEAD` non-force (the catalog,
   enforcement and checkpoint commits together). The resulting current-SHA
   matrix is the only acceptable evidence; do not reuse run `34761805023` for
   any pushed commit.
3. The catalog validator is now integrated into the existing required
   `quality-inventory-check` job (commit `57d11f958`), with a RED→GREEN contract
   test (`165 passed` in the focused workflow-contract suite) and isolated
   pre-commit/actionlint/ruff checks. Re-run this step on the post-push SHA;
   no new fan-out lane was introduced.
4. Verify the compact current-run health artifact on the next current-SHA
   terminal run and produce strict timing evidence; preserve first failures
   and all artifacts. Do not tune Stryker/mutmut caps until three comparable
   green runs satisfy the queue/resource/provenance rollback criteria.
5. Keep merge-to-main, exact-six immutable image producer, digest Docker smoke,
   Kubernetes/TLS/ExternalSecrets/observability staging, device CWV,
   chaos/restart/rollback, production release and final SHA-bound audit
   explicitly external and release-blocking.

## 51. Compact current-run CI health report implementation (2026-09-13)

The previously `OPEN` compact-health item now has a repository-local producer
without adding a fan-out lane or changing any required test, coverage,
mutation, security, or concurrency threshold.  The existing `ci-success`
finalizer requests `actions: read` and `contents: read`, checks out the exact
workflow SHA with credentials disabled, and after the authoritative
fail-closed result table runs:

    scripts/quality/analyze_ci_critical_path.py
      --repository "$GITHUB_REPOSITORY"
      --run-id "$GITHUB_RUN_ID"
      --concurrency-cap 20
      --diagnostic-lower-bound
    scripts/quality/render_ci_health_report.py

The analyzer JSON and an escaped Markdown projection are uploaded as the
run/attempt-bound artifact
`ci-health-${{ github.run_id }}-${{ github.run_attempt }}` and the Markdown is
also appended to the finalizer step summary.  The renderer validates schema
version, repository/run identity, optional report SHA-256, job cardinality,
status/conclusion values, and all queue/setup/test/artifact p50/p95/max
statistics.  It bounds and escapes job names, lists skipped jobs, and emits an
explicit warning for pending/unknown outcomes; malformed or missing evidence
fails the existing finalizer rather than manufacturing a green signal.

Focused RED→GREEN evidence:

    uv run pytest -q -p no:cacheprovider tests/test_ci_health_report.py
      6 passed
    uv run pytest -q -p no:cacheprovider \
      tests/test_ci_health_report.py tests/test_quality_workflow_contract.py \
      tests/test_ci_check_catalog.py
      189 passed
    uv run ruff check scripts/quality/render_ci_health_report.py \
      tests/test_ci_health_report.py tests/test_quality_workflow_contract.py
      passed
    uv run python scripts/quality/validate_ci_check_catalog.py
      CI check catalog: OK (55 workflows, 180 jobs)

This closes the compact report implementation gap locally, but the report is
still diagnostic-only API timing and not a release certificate.  Strict DAG /
artifact-byte verification, detached producer provenance, runner RSS/CPU,
billed minutes, repository-wide retry classification, generic cross-job
heartbeat diagnostics, three comparable green runs before any cap change, and
all merge/staging/release evidence remain open exactly as recorded in §50.

## 52. Local fast-preflight evidence checkpoint (2026-09-13)

The documented local acceleration path was exercised from the current checkout
without changing tracked source or touching the user-owned untracked paths.
The shell-free runner used six workers and a 600-second per-check fail-closed
timeout:

    uv run python scripts/fast_preflight.py --max-workers 6 --timeout-seconds 600 --include-output
    Fast preflight: 6/6 passed
    frontend-typecheck      10.829s
    frontend-lint           84.421s
    backend-typecheck        7.969s
    backend-lint             0.151s
    verify-harness           34.595s (29/29)
    focused-contract-tests  53.853s
    report: artifacts/fast-preflight/fast-preflight.json

The same checkout also passed the broader CI/workflow contract inventory:

    uv run pytest -q -p no:cacheprovider \
      tests/test_ci_check_catalog.py tests/test_ci_execution_contract.py \
      tests/test_ci_health_report.py tests/test_ci_critical_path_analysis.py \
      tests/test_quality_workflow_contract.py tests/test_workflow_fail_closed_contracts.py \
      tests/test_frontend_ci_performance_contracts.py \
      tests/contracts/test_ci_release_capacity_contract.py
    294 passed in 146.43s
    uv run pytest -q -p no:cacheprovider \
      tests/test_ci_critical_path_analysis.py tests/test_mutmut_shard_budget.py
    68 passed in 21.19s
    uv run python scripts/quality/validate_ci_check_catalog.py
      CI check catalog: OK (55 workflows, 180 jobs)

These are local readiness and regression signals only. They do not promote
the branch to `FRESH-GREEN`: current-SHA GitHub matrix completion, strict
mutation/coverage artifacts, live ruleset comparison, and all external
Docker/Kubernetes/staging/release evidence remain mandatory. The generated
JSON report is ignored by Git and is not a release artifact.

The Compose matrix was validated using the repository's supported composition
patterns (base file plus the required overlays), with environment variables
provided only in the process environment:

    docker compose --env-file .env.docker -f docker-compose.full.yml config --quiet
    docker compose --env-file .env.docker -f docker-compose.yml config --quiet
    docker compose --env-file .env.docker \
      -f docker-compose.yml -f docker-compose.infra.yml \
      -f docker-compose.go.yml -f docker-compose.ci-loadtest.yml config --quiet
    docker compose --env-file .env.docker --profile prod \
      -f docker-compose.yml -f docker-compose.go.yml -f docker-compose.prod.yml config --quiet

All four supported compositions returned exit code 0. Overlay files such as
`docker-compose.go.yml`, `docker-compose.infra.yml` and
`docker-compose.observability.yml` are fragments by design and are not valid
standalone projects; testing them without their documented base produces an
expected undefined-network/image error and is not a release failure.

The complete frontend qualification path was also exercised locally after the
WASM producer fixes:

    npm run test:ci --prefix frontend -- --silent=true
    WASM contract stage: 259 passed
    Vitest: 673 test files, 7,116 tests passed
    Coverage: Statements 100% (18,860/18,860)
               Branches   100% (13,326/13,326)
               Functions  100% (4,533/4,533)
               Lines      100% (17,009/17,009)

The command completed with exit code 0 and emitted only the existing jsdom CSS
parser notices and intentionally informational navigation messages; no test,
coverage or build failure was suppressed. Reports were written to ignored
workspace paths and no tracked or user-owned files changed.

The expanded frontend static-quality sequence was green as well:

    npm run lint:all --prefix frontend
    eslint, architecture/barrel contracts, manifests, CSS token closure/sync,
    ts-prune and dependency audit: exit code 0

`ts-prune` prints the repository's known export inventory as diagnostics; it
does not fail the configured command, and `lint:depcheck` reported no unused
dependencies. Token synchronization was deterministic and left the tracked
generated token file unchanged.

## 53. CDC lifecycle and service-documentation refresh (2026-09-13)

The external audit's BE-08 item was rechecked against the current source. The
CDC implementation remains deliberately inactive in the application lifecycle:
Dishka/lifespan owns the polling `OutboxWorker`, while
`CdcOutboxWorker.run_forever()` is not registered as a second transport. The
existing ADR-037 and closure tests protect this boundary; enabling CDC without
an explicit feature flag, single-consumer ownership, replication preflight,
idempotency and PostgreSQL integration evidence would risk duplicate delivery.

Current local focused evidence:

    uv run pytest -q -p no:cacheprovider \
      tests/test_cdc_outbox.py tests/test_cdc_outbox_closure.py
    45 passed in 12.62s

This is code/contract evidence only; BE-08 remains an architectural backlog
until a separately approved CDC enablement slice supplies lifecycle,
replication and staging evidence.

The P3 GO-06 documentation drift was corrected in `services/AGENTS.md`: the
Gateway is documented as an HTTP JWKS poller, while ws-hub is the sole NATS
consumer for `keys.rotated` and `cache.invalidate`. No runtime subscriber was
added merely to satisfy stale documentation, and `git diff --check` remains
clean.

## 54. Bandit scope characterization and infrastructure contract refresh (2026-09-13)

The SEC-08 tooling item is now explicit and aligned across `pyproject.toml`,
pre-commit and CI: the required Bandit gate targets deployable `app/` code;
test fixtures and chaos helpers remain covered by their dedicated secret/SAST
checks without blanket `# nosec` suppressions. The production-targeted command
used by the pre-commit/CI path is:

    $env:PYTHONUTF8='1'; uv run bandit -c pyproject.toml -r app -q
    exit code 0 (Bandit emitted only existing nosec/comment diagnostics)

For comparison, an explicit all-code diagnostic invocation was run once:

    uv run bandit -c pyproject.toml -r app tests
    exit code 1: 0 high, 13 medium and 863 low findings, concentrated in
    test-only fixture credentials and subprocess/chaos helpers

Those test fixtures are not deployed production code and use the repository's
existing secret-fixture conventions. They are intentionally not converted into
blanket `# nosec` suppressions, and no findings are used as release evidence.
SEC-08 therefore remains `EXTERNAL-ONLY / TOOLING`: the authoritative Linux
workflow must publish a fresh scan for the explicit production scope;
expanding the required scope requires a separately reviewed fixture policy.

The infrastructure contract characterization also completed locally:

    uv run pytest -q -p no:cacheprovider \
      tests/test_infra_audit_contract.py tests/test_docker_startup_contracts.py
    96 passed, 1 skipped in 37.53s

The sole skip is the documented Windows limitation that `bash` is not an
executable on this host; the wrapper's Linux execution remains release-gated.

## 55. Current-SHA mutation and dependency-drift hardening (2026-09-13)

The current branch added two bounded, regression-tested fixes without changing
the required mutation denominator or CI runner caps:

- `308ba3e3d` isolates the expensive `src/api/client.ts` first-attempt Stryker
  ranges from UI hotspot ranges. The planner still emits exactly 64 logical
  shards and preserves every preflight mutant; the regression fixture proves
  complete accounting, unique assignments and no client/Badge graph mixing.
- `5502da1a2` adds the fail-closed BE-04 AST route-dependency inventory and
  reviewed ledger. The current inventory contains 148 route callsites (25
  canonical Dishka, 110 approved legacy, 9 public/no-DB and 4 internal/
  websocket) with zero mixed ownership. New legacy routes or ownership changes
  now fail until the ledger is deliberately reviewed.

The effective BE-02 metadata inventory is synchronized with ADR-036 and the
backend rules: 134 applicable defaults (26 dual, 91 Python-only, 17
server-only) plus one separately tracked `Computed` expression. PostgreSQL
catalog, phased migration and full legacy-DI migration evidence remain
external follow-ups; neither item is being falsely marked release-complete.

Local focused evidence for this checkpoint:

    node --test frontend/scripts/run-stryker.test.mjs
    97 passed
    uv run pytest -q -p no:cacheprovider \
      tests/test_model_default_policy.py tests/test_route_dependency_inventory.py
    6 passed
    python verify_harness.py --repo-only
    29 passed

The old remote run `34761805023` is still bound to the previous SHA and has a
confirmed Stryker shard-20 hard timeout; it remains non-terminal and is not
used as current-SHA evidence. Push is intentionally deferred until its final
failure/artifact inventory is available, after which a fresh matrix will be
run against the current head.

The CDC boundary also received a race-safe shutdown hardening: if logical
replication provisioning fails after `stop()` has been requested, the worker
now exits without starting a fresh polling fallback. The focused CDC suite is
**46 passed**; this closes the observed cancellation race but does not claim
the separately gated PostgreSQL replication/staging enablement work.

## 56. Additional current-head closure fixes and verified hardening (2026-09-13)

The current `egorribun` branch is now **20 commits ahead** of
`origin/egorribun`; all tracked changes are committed and the only remaining
worktree entries are the pre-existing user-owned untracked paths documented in
the handoff.  No stash entry or user artifact was modified.

Three reproducible defects found while running the full local gates were closed
with small, independently reviewable commits:

- `7b1b7641f` adds an exact SQL projection assertion for the bcrypt migration
  inventory.  The old mutmut survivor replaced `select(User.id)` with
  `select(None)` while the existing `ORDER BY users.id` assertion still passed.
  The focused closure suite is **15 passed**.
- `3b5c143c5` makes the SQLite-only computed-column adaptation in
  `app/core/lifespan.py` transactional with respect to shared SQLAlchemy
  metadata: `computed` and `nullable` are snapshotted and restored in a
  `finally` block after `create_all`, including failure paths.  The ordered
  adversarial/model-default regression and lifespan suite are **40 passed**;
  this removes cross-test metadata contamination without changing PostgreSQL
  behavior.
- `f1561222e` makes duration-aware pytest sharding fail closed on malformed,
  duplicate, non-finite, negative or boolean history values.  The validator is
  covered by seven new contract cases and included in `fast_preflight`; the
  focused timing/preflight set is **14 passed**, the expanded CI contract set
  remains **271 passed**, and the catalog remains **55 workflows / 180 jobs**.

The Go trust-boundary/documentation hardening commit `04b05c5a0` adds
`persist-credentials: false` to all PR-executed Go checkouts covered by the
contract, updates the documented race-test image to the immutable audited
Go 1.26.6 digest, and adds fail-closed workflow tests.  Evidence is **168
quality-workflow tests passed**, **7 focused tests passed**, actionlint passed
for all four changed workflows, and `git show --check` is clean.  The
non-PR-only `go-lint.yml` checkout was intentionally left unchanged; required
PR lint uses the already hardened reusable Go-test path.

The previous GitHub run `34761805023` is still tied to SHA
`d9a964be0896cb90377de51ba37aaa27333f91d9`, not this branch.  Its authoritative
Jobs API currently reports 310 jobs with two terminal non-success outcomes:
Stryker shard 20 cancellation after the two-hour watchdog and mutmut execution
group 65's single survivor (`select(None)`), both now addressed locally.  It
also has pending/queued work, so no result from that run is treated as
current-head evidence.  After the run reaches a terminal state, push this
branch non-force and start a fresh current-SHA matrix; only that matrix can
certify mutation, coverage, provenance or release readiness.

The full backend coverage process was started before the SQLite restoration
fix and reported an intermediate failure at the historical contamination
point; it must be rerun from the fixed head before any coverage claim.  The
remaining release-blocking evidence is unchanged: fresh current-SHA CI,
PostgreSQL catalog/phased migration and full Dishka migration evidence,
terminal mutation/coverage artifacts, immutable image producer and digest
Docker smoke, Kubernetes/TLS/ExternalSecrets/observability staging, real
 browser/device/CWV checks, chaos/rollback, and the final SHA-bound audit.

## 57. Current-head security scanner provenance hardening (2026-09-13)

The security workflow's Trivy bootstrap was hardened in commit
`03ccbb67c`. The previous implementation enabled a live third-party apt
repository and imported its signing key at job runtime, which made the
security gate depend on mutable repository metadata. The workflow now
downloads the official Trivy `0.73.0` Linux archive over HTTPS/TLS 1.2,
verifies the pinned SHA-256 digest before extraction, installs only the
verified binary, and keeps the existing blocking filesystem scan and SARIF
upload semantics. The temporary directory is removed on exit and the
version/digest/download/verification order is protected by a workflow
contract test; no action inventory or mutation denominator changed.

Verification for this checkpoint:

    uv run pytest -q -p no:cacheprovider \
      tests/test_security_hardening_workflow_contract.py
    7 passed
    uv run pytest -q -p no:cacheprovider \
      tests/test_security_hardening_workflow_contract.py \
      tests/test_workflow_fail_closed_contracts.py \
      tests/test_quality_workflow_contract.py
    97 passed
    uv run python scripts/quality/validate_ci_check_catalog.py
    CI check catalog: OK (55 workflows, 180 jobs)
    actionlint v1.7.12: exit 0
    git diff --check: exit 0

At the time of this checkpoint the security fix brought the branch to 23
commits ahead of `origin/egorribun`; the follow-up documentation commit is
recorded separately. Only the four documented user-owned untracked paths
remain. This is a local hardening checkpoint, not release evidence: the old remote run remains tied to
`d9a964be0896cb90377de51ba37aaa27333f91d9` and is still non-terminal, so the
branch must be pushed only after its final failure inventory and then
validated by a fresh current-SHA matrix.

## 58. Current-SHA CI blocker closure and deploy trust-boundary hardening (2026-09-13)

`6e6185b73` closes the two deterministic failures observed in fresh matrix run
`34777996115` for the preceding SHA `fabb517f6c4d018dafcca619298debb9dab18a74`.

The quality-inventory job now invokes every repository Python helper through
the locked `uv` interpreter (`uv run python`). This prevents the runner's
system Python from bypassing the frozen environment and failing to import
PyYAML/jsonschema. The workflow contract test requires all four invocations.

The plan document's evidence blocks now use the repository's required indented
Markdown style, eliminating all 14 MD046 violations without changing evidence.
The stale Trivy apt-mirror regression was replaced with a checksum-bound
contract covering version `0.73.0`, the official HTTPS/TLS 1.2 release URL,
strict checksum-before-extract-before-install ordering, and explicit absence of
apt repository and `wget` bootstrapping.

The deploy workflow no longer executes mutable setup actions for kubectl or
Helm. It downloads official artifacts over HTTPS/TLS 1.2, verifies SHA-256
before installation, installs Helm `v3.17.0` with its published digest, and
requires environment-scoped `KUBECTL_VERSION` and `KUBECTL_SHA256`. After OIDC
authentication it validates client/API-server major equality and a supported
minor skew of at most plus or minus one. Requests and its four dependency
artifacts are installed before OIDC using isolated pip, binary-only and
`--require-hashes` from the repository lockfile. Missing or mismatched
deployment variables fail closed.

Focused evidence before commit:

    uv run pytest -q -p no:cacheprovider \
      tests/test_quality_workflow_contract.py \
      tests/test_workflow_fail_closed_contracts.py \
      tests/test_security_hardening_workflow_contract.py
    211 passed in 98.45s
    npx --yes markdownlint-cli2@0.20.0 \
      docs/superpowers/plans/2026-08-31-mvp-quality-closure-continuation.md
    Summary: 0 error(s)
    pre-commit run --files <five changed files>
    all configured hooks passed
    git diff --check
    exit code 0

The commit was pushed non-force to `origin/egorribun`; pre-push TypeScript
typecheck passed. The four user-owned untracked paths remain outside the
index. A new matrix run for commit `6e6185b73` is required before any
release claim; the prior run's two failures are superseded and remain
diagnostic history only.

## 59. Workflow install-network overhead hardening (2026-09-14)

The branch now contains two small, independently reviewable CI optimization
commits, both intentionally kept separate from mutation-cap changes:

- `36875bdcd` changes the PR-critical `ci.yml` and reusable frontend/E2E/security
  install steps to `npm ci --no-audit --no-fund` and adds a regression contract
  preserving the explicit `scripts/audit_dependencies.py` security gate.
- `a6fe722ac` applies the same install-only flags to every remaining workflow
  `npm ci` invocation, including nightly/manual mutation, release, visual,
  cache-helper and setup workflows. Lifecycle scripts remain enabled; no
  mutable `npm install`, `--ignore-scripts`, audit allowlist or security-gate
  bypass was introduced.

The command is supported by the pinned CI toolchain (npm `11.17.0`), and the
dedicated audit remains a separate blocking step. The contract now scans every
`.github/workflows/*.yml` command form and fails if a future bare `npm ci`
appears. Local evidence:

    uv run pytest -q --no-cov --disable-warnings --tb=short \
      tests/test_frontend_ci_performance_contracts.py
    8 passed
    uv run python -c "import pathlib,yaml; paths=sorted(pathlib.Path('.github/workflows').glob('*.yml')); [yaml.safe_load(p.read_text(encoding='utf-8')) for p in paths]"
    parsed 55 workflow YAML files
    isolated pre-commit hooks for the changed files: all configured hooks passed
    verify_harness.py: 29 passed

The timing audit shows this is a bounded setup optimization, not the primary
latency fix: recent Stryker install p50/p95 were about 28/30 seconds and
execution p95 about 24.5 minutes, with a roughly 75-minute outlier. The
current runner cap remains unchanged (6 Stryker + 10 mutmut, peak observed
19/20). A/B impact must be measured on the next comparable current-SHA runs
using queue/setup p50/p95 and billed-minute evidence; no release or mutation
capacity claim is inferred from this local change.

The current live matrix `34780640933` is still bound to the pre-optimization
SHA `ecfe0dba6668cb0a9b8f68186aa1a003f597d285`; at the last poll it had 310
jobs, 152 successes, 12 intentional skips, 16 active and 130 queued, with no
failure/cancellation/timeout. The two commits are deliberately not pushed
until that run reaches terminal state, so its late mutation evidence is not
discarded. After terminal inventory, push non-force and require a fresh
current-SHA matrix before treating these changes as CI evidence.

## 60. Release dependency-audit closure and current diff security evidence (2026-09-14)

The targeted security review of the install-network optimization found a
conditional coverage gap: the reusable allowlist audit is intentionally scoped
to `frontend`, while the privileged release job installs a separate root
semantic-release toolchain. Commit `8986541c82aa6da652ed1d01618f0aa759cebe0d`
closes that gap with a non-conditional, non-continue-on-error
`npm audit --audit-level=high --json` step after root `npm ci` and before release
toolchain verification. The allowlist was not broadened: root dependencies use
the direct high-severity audit, while frontend continues to use the owner/expiry
controlled `scripts/audit_dependencies.py` policy.

The same commit hardens the npm-install regression contract. It parses both
`.github/workflows/*.yml` and `*.yaml`, walks YAML `run` values (including
multiline shell blocks), requires `--no-audit --no-fund` on every `npm ci`, and
asserts that the explicit frontend audit remains present. The release contract
also rejects an audit step guarded by `if` or `continue-on-error`.

Focused evidence:

    uv run pytest -q --no-cov --disable-warnings --tb=short \
      tests/test_frontend_ci_performance_contracts.py \
      tests/test_release_certification_contract.py \
      tests/test_ci_health_report.py \
      tests/test_ci_critical_path_analysis.py
    125 passed in 42.13s
    uv run pytest -q --no-cov --disable-warnings --tb=short \
      tests/test_release_certification_contract.py
    58 passed
    uv run python verify_harness.py
    29 passed, 0 failures, 0 errors
    uv run python scripts/quality/validate_ci_check_catalog.py
    CI check catalog: OK (55 workflows, 180 jobs)
    all 55 workflow YAML files parsed successfully
    npm audit --audit-level=high --json (root): 0 high/critical vulnerabilities
    npm ci --dry-run --no-audit --no-fund (root): exit 0
    git diff --check: exit 0

An independent Codex Security diff scan (`367e5c0a-761e-432d-8b2d-6df482190445`)
sealed successfully for the range `ecfe0dba6668cb0a9b8f68186aa1a003f597d285` →
`8986541c82aa6da652ed1d01618f0aa759cebe0d`: zero reportable findings and
complete coverage. The generated report is retained outside the repository at
`C:\Temp\codex-security-scans-nJCX21\university_ecosystem\8986541c82aa6da652ed1d01618f0aa759cebe0d_20260913T230029Z_8r5cjy32\report.md`;
its manifest binds findings/coverage hashes
`f6c2ba9556f49f0b57d809d35a704ef67cffb7e4e3c756b3f91fa3029460ef63` and
`1ff8f57e39f6779c4dce1c80a3688c10ddb66fd5717e82bc00701c8291d02934`.
The scan explicitly records the plugin's `.github`, `docs`, and `tests`
inventory exclusions and the remaining hosted-runner timing questions; this is
security-diff evidence, not a full release or staging certificate.

The live matrix `34780640933` remains bound to the pre-optimization SHA
`ecfe0dba6668cb0a9b8f68186aa1a003f597d285`. It must reach terminal state before
the four local commits are pushed, so that its mutation evidence is not
cancelled. After terminal inventory, push non-force and require a fresh
current-SHA matrix; only then compare setup/queue/billed-minute distributions
and decide whether a duration-aware mutation experiment is justified.

## 61. CDC shutdown-race mutation closure (2026-09-14)

The still-running diagnostic matrix `34780640933` (source SHA
`ecfe0dba6668cb0a9b8f68186aa1a003f597d285`) exposed the same viable mutational
gap in four completed mutmut groups: 40, 41, 43 and 44. The surviving
mutants were `CdcOutboxWorker.run_forever__mutmut_10`, `_11`, `_13` and `_14`;
each changed only the exact shutdown-provisioning log template (case or marker
text), while leaving control flow unchanged. The old run therefore remains
diagnostic evidence and is not retroactively reclassified as current-head
quality evidence.

Commit `cafb13da5` adds one deterministic contract test that forces a
provisioning failure after shutdown, asserts the complete non-PII log template,
and verifies that no fallback worker is started. The assertion kills the
entire family of equivalent string mutants rather than adding an exclusion or
weakening the score gate. Local evidence on the current head is:

    uv run pytest -q -p no:cacheprovider \
      tests/test_cdc_outbox.py tests/test_cdc_outbox_closure.py
    47 passed
    git diff --check: exit 0
    isolated pre-commit hooks: all configured hooks passed

The test-only commit is included in the next source-aware mutation universe;
it is not claimed as proof until a fresh current-SHA matrix regenerates stats,
executes the selected mutants, and seals complete evidence. The old matrix
must still reach a terminal state so its complete failure inventory can be
recorded before the branch is pushed non-force.

## 62. Source-default inventory and frontend contract-lane optimization (2026-09-14)

Two bounded quality/performance improvements are now implemented locally and
remain subject to a fresh current-SHA CI run:

- `8b25422f0` adds the fail-closed BE-02 source inventory. The checked-in
  `quality/model-default-policy.json` records the reviewed per-column
  classifications and exception owners. `scripts/quality/audit_model_defaults.py`
  parses the Alembic graph without importing migration modules, derives the
  SQLAlchemy metadata/source inventory, binds the result to the full current
  commit SHA and migration head, rejects unknown/duplicate/partial policy data,
  and explicitly reports PostgreSQL catalog status as `not_checked` with
  `required_for_release: true`. The existing required
  `quality-inventory-check` job generates, re-reads and uploads the
  run/attempt/SHA-scoped JSON artifact. This is a reproducible source/metadata
  baseline, not a substitute for live `pg_get_expr` catalog, NULL-count,
  upgrade/downgrade or raw-writer evidence.
- `0c1a0fa12` adds one required `WASM Contract Tests` job to the reusable
  frontend workflow. It runs the complete `npm run test:wasm` suite exactly
  once after the immutable WASM producer, while the four unit shards use the
  dedicated `test:unit-ci` script and no longer repeat the same repository-wide
  contract suite. Artifact download paths and the required CI check catalog are
  preserved; no test, source or mutation inventory is reduced. The quality
  inventory install also uses `npm --prefix frontend ci --no-audit --no-fund`,
  while the separate dependency audit remains blocking.

Focused and full local evidence for this checkpoint:

    uv run pytest -q -p no:cacheprovider tests/test_model_default_inventory.py
    5 passed
    uv run mypy --config-file pyproject.toml \
      scripts/quality/audit_model_defaults.py tests/test_model_default_inventory.py
    Success: no issues found in 2 source files
    uv run pytest -q -p no:cacheprovider \
      tests/test_frontend_ci_performance_contracts.py \
      tests/test_quality_workflow_contract.py
    173 passed
    npm run test:wasm
    260 passed
    uv run pytest -q --no-cov --disable-warnings --tb=short
    10225 passed, 106 skipped, 2 deselected
    pre-commit run --files <ten changed files> (isolated PRE_COMMIT_HOME)
    all configured hooks passed
    git diff --check
    exit code 0

The isolated pre-commit run avoids the previously inaccessible user cache and
did not modify `.secrets.baseline`. Windows-only skips remain explicit
environment limitations (PostgreSQL/ToxiProxy/Pact/FFI/symlink privileges),
not relaxed gates. The current diagnostic run `34780640933` is still bound to
the older SHA `ecfe0dba6668cb0a9b8f68186aa1a003f597d285`; at this snapshot it
has 227/310 jobs completed, 16 active, 67 queued and four known mutmut
failures. Because `ci.yml` uses `cancel-in-progress: true`, the nine local
commits remain unpushed until that old run reaches terminal state and its
complete failure/artifact inventory is recorded. A fresh current-SHA matrix is
still mandatory before either improvement is treated as CI evidence.

## 63. Current-head security, E2E assurance and catalog reconciliation (2026-09-14)

The independent bounded audits and a local contract run produced the following
additional closure evidence:

- The Codex Security diff scan `9ea906b2-8721-43c2-8e69-119a5e3ca15f` reviewed
  all four changed executable/configuration surfaces between
  `ecfe0dba6668cb0a9b8f68186aa1a003f597d285` and
  `79039f5d6a6cac74a2c044c83c1c87c92b5d0d6b`. Discovery coverage is complete
  (4/4), no reportable findings survived validation, and the scan is sealed.
  The report and SARIF are retained outside the repository at
  `C:\Temp\codex-security-scans-nJCX21\university_ecosystem\79039f5d6a6cac74a2c044c83c1c87c92b5d0d6b_20260914T003311Z_fcf3f032\report.md`
  and `...\exports\results.sarif`. Daybreak access was `not_granted`, so the
  workbench marks token accounting as partial; this does not change source
  coverage or finding disposition.
- The E2E/CI assurance audit found that the shared Playwright mock returned a
  fabricated generic `200 {}` for unhandled API/Auth requests. Commit
  `cb367bfc2` replaces that behavior with a diagnostic `501` fail-closed
  response, adds explicit mocks for observed `GET /api/auth/csrf-cookie` and
  `GET /api/chats`, and adds a regression contract. Focused i18n Chromium E2E
  (4 passed), E2E contract (1 passed), workflow contract (54 passed), ESLint,
  YAML parsing, actionlint and `git diff --check` are green. No E2E test or
  mutation inventory was removed; the remaining annotation-soft-pass,
  inactive-realtime, unused-input and repeated-setup observations require
  remote policy/evidence before any further change.
- The same commit reconciles the new model-default inventory upload with
  `quality/ci-check-catalog.json` and adds an assertion for the exact
  run/attempt/SHA-bound artifact contract. `validate_ci_check_catalog.py` now
  passes (`55 workflows, 181 jobs`), and the expanded workflow contract suite
  passes (`169` tests locally).
- The bounded full-project audit found no new reproducible P0 vulnerability.
  It confirms the current source fixes for GraphQL HMAC, JWKS rotation,
  health-probe Redis bypass, object-key traversal, shared PII redaction,
  Helm/Kyverno/digest guards and raw Kubernetes interpolation. The remaining
  release blockers are evidence-only: current-SHA mutation/coverage manifests,
  live PostgreSQL catalog and migration upgrade/downgrade, Linux Go race/vet/
  lint, Rust cargo-deny/fuzz/coverage, immutable Docker/Compose and staging
  Kubernetes/TLS/observability/CWV certification. A legacy `Depends` route
  inventory is mixed-free but remains architecture backlog, not an unproven
  release defect.
- Local repository harness is green: `verify_harness.py` completed 29/29 in
  25.14 seconds. The old diagnostic run `34780640933` remains non-terminal and
  is still bound to `ecfe0dba6668cb0a9b8f68186aa1a003f597d285`; its latest
  paginated snapshot is 232 completed, 16 in progress and 62 queued, with the
  four known stale mutmut survivors in groups 40, 41, 43 and 44. Do not push
  while it is active because the workflow's `cancel-in-progress: true` would
  discard late artifacts. After terminal inventory, push non-force and require
  a fresh current-SHA matrix.

## 64. Lock-bound npm cache hardening (2026-09-14)

The reusable dependency-cache workflow had a stale-executable risk: it cached
`frontend/node_modules` and restored broad `node-${{ inputs.node-version }}-`
prefixes, then skipped `npm ci` on a partial cache hit. This could combine a
previous lockfile's executable tree with the current checkout. Commit
`1e176dcb6` (`fix(ci): harden reusable npm dependency cache`) removes
`frontend/node_modules` from the cache, removes the broad restore key, keeps
the exact `frontend/package-lock.json` key for the npm download store, and
always runs `npm ci --no-audit --no-fund`. No source, test, mutation or
coverage inventory was reduced.

The contract regression `test_reusable_node_cache_never_restores_stale_node_modules`
proves the cache path, exact lock binding, absence of `restore-keys`, and
unconditional install. Verification on the commit completed with:

    uv run pytest -q -p no:cacheprovider tests/test_quality_workflow_contract.py
    # 169 passed
    uv run ruff check tests/test_quality_workflow_contract.py
    uv run ruff format --check tests/test_quality_workflow_contract.py
    uv run python scripts/quality/validate_ci_check_catalog.py
    # CI check catalog: OK (55 workflows, 181 jobs)
    git diff --check

The commit hook also passed in an isolated pre-commit home (ruff,
detect-secrets, gitleaks, actionlint and semgrep among the executed hooks).
The global pre-commit cache permission error was not bypassed; isolation was
used solely to avoid the unrelated locked cache path. The old remote run
remains non-terminal, so current-SHA certification is still pending.

## 65. Current-HEAD fast-preflight checkpoint (2026-09-14)

After the cache-hardening commit and its evidence checkpoint, the local
current HEAD `0a1e666d6` passed the bounded parallel developer preflight:

    uv run python scripts/fast_preflight.py --max-workers 6 \
      --timeout-seconds 600 --include-output
    # Fast preflight: 6/6 passed

The six checks completed without suppressions or inventory changes:

- frontend typecheck — 12.010 seconds;
- frontend lint — 90.395 seconds;
- backend mypy — 8.452 seconds;
- backend Ruff — 0.150 seconds;
- `verify_harness.py --repo-only` — 29/29 in 37.248 seconds;
- focused CI contracts — 70 passed in 64.050 seconds.

The machine-readable report is retained in the ignored local path
`artifacts/fast-preflight/fast-preflight.json`; it is developer evidence only
and is not substituted for Linux current-SHA CI artifacts. `git diff --check`
and the tracked worktree remain clean apart from the intentional commit
history; user-owned untracked paths remain untouched and unstaged.

## 66. Transient-only download retries and benchmark-policy alignment (2026-09-14)

The CI speed/security audit identified four download paths using
`curl --retry-all-errors`. That flag could retry deterministic HTTP failures
and blur the first actionable failure. Commit `928015109` (`fix(ci): restrict
retries to transient failures`) replaces it with curl's bounded retry plus
`--retry-connrefused` in the Kyverno, E2E artifact and frontend artifact
downloaders. `--fail`/`--fail-with-body`, checksum verification and all
existing artifact contracts remain intact; no test or mutation inventory was
removed. A regression contract now rejects `--retry-all-errors` in all four
workflows and requires the transient-only option. The combined workflow and
fail-closed contract suite passed **217 tests**.

The live main ruleset currently requires the `Run Go Benchmarks` context while
the workflow prose called its producer "advisory". Commit `6f80b2f36`
(`fix(ci): align benchmark gate classification`) makes the distinction
explicit: the job is required by branch protection, while raw uploaded
measurements remain advisory evidence. The step labels and a regression
contract now match the live policy; paired performance gates and historical
chart publication are unchanged. YAML parsing, targeted performance contracts
and the commit hooks passed.

These changes improve fail-closed semantics and reduce misleading retry/owner
signals, but do not claim a repository-wide transient classifier, global
hosted-runner semaphore, resource telemetry or three-run sharding evidence.
Those remain explicitly evidence-gated follow-up work after the old remote
matrix reaches a terminal state.

## 67. Supported Compose matrix revalidated (2026-09-14)

The exact Compose configurations exercised by the primary CI workflow were
revalidated from the current local checkout without starting or mutating the
runtime stack. Both commands completed with exit code 0:

    $env:IMGPROXY_KEY = ('0' * 64)
    $env:IMGPROXY_SALT = ('1' * 64)
    docker compose -f docker-compose.yml --env-file .env config --quiet
    $env:WS_HUB_INTERNAL_SECRET = 'dummy-ci-validate-secret' # pragma: allowlist secret — documentation-only placeholder
    docker compose -f docker-compose.yml -f docker-compose.infra.yml -f docker-compose.go.yml -f docker-compose.ci-loadtest.yml --env-file .env config --quiet

The first command validates the base topology; the second matches the
workflow's merged infra/Go/load-test overlay. The standalone
`docker-compose.go.yml` fragment is intentionally not treated as a supported
topology because it relies on networks and services supplied by the base and
infra files. This checkpoint proves interpolation and model validity only; it
does not certify image builds, readiness, SSR, WebSocket, gRPC, observability,
resource usage or immutable-digest runtime smoke. Those release gates still
require a clean external Docker/staging environment and current-SHA evidence.

## 68. Current-SHA fast-preflight recertification (2026-09-14)

After the Compose evidence checkpoint, the bounded local preflight was rerun
against the exact current HEAD `3ea91fd5a4f0d82dadfb2ebe8f4aa7f9ec395add`:

    uv run python scripts/fast_preflight.py --max-workers 6 --timeout-seconds 600 --include-output
    # Fast preflight: 6/6 passed

Measured durations were frontend typecheck 11.527 s, frontend lint 84.313 s,
backend typecheck 5.351 s, backend lint 0.153 s, `verify_harness.py --repo-only`
35.613 s (29/29), and focused contract tests 59.586 s. The report is retained
at the ignored path `artifacts/fast-preflight/fast-preflight.json`; it is
developer evidence only and does not replace Linux current-SHA CI artifacts,
mutation/coverage reports, or runtime/staging certification. The tracked
worktree remained clean apart from intentional history and the four preserved
user-owned untracked paths.

## 69. Frontend unit and merged coverage recertification (2026-09-14)

The complete frontend unit/coverage command was run from the exact source
commit `3ea91fd5a4f0d82dadfb2ebe8f4aa7f9ec395add`:

    npm run test:unit-ci --prefix frontend -- --silent=true

It completed successfully with **673/673 test files**, **7,116/7,116 tests**,
and 100% statements, branches, functions and lines (18,860/18,860,
13,326/13,326, 4,533/4,533 and 17,009/17,009 respectively). The generated
JUnit and coverage reports were local diagnostic artifacts only and were not
staged. This is strong local evidence, not a substitute for the required
current-SHA Linux CI mutation, browser, manifest or release evidence.

## 70. Current local closure checkpoint and duplicate-evidence serialization (2026-09-14)

At checkpoint creation the local branch was `egorribun` at `a290d9485` (the
parent `b4f3f4ba1` and that checkpoint contain CI-governance changes only after
the last product-code recertification). User-owned untracked paths remain
untouched and unstaged: `.tmp_preflight/`, `.tmp_stryker_18/`,
`.tmp_stryker_22/` and `docs/audits/AUDIT_PLATFORM_FULL.md`.

Commit `a290d9485` (`fix(ci): serialize duplicate evidence runs`) adds
fail-safe `concurrency` groups with `cancel-in-progress: false` to the
protected DAST, manual performance-evidence and quality-promotion workflows.
This prevents duplicate long-lived evidence runs from consuming the shared
runner pool or cancelling an in-flight report; it does not reduce any matrix,
coverage, mutation or security inventory. A contract test covers all three
groups.

Fresh local evidence from this checkout:

    python verify_harness.py
    # 29 passed, 0 failed (106.40 s)

    uv run pytest -q -p no:cacheprovider \
      tests/test_ci_critical_path_analysis.py tests/test_ci_health_report.py \
      tests/contracts/test_ci_release_capacity_contract.py
    # 70 passed (55.23 s)

    uv run python scripts/quality/validate_ci_check_catalog.py
    # CI check catalog: OK (55 workflows, 182 jobs)
    uv run python scripts/quality/validate_quality_contract.py
    # Quality contract is valid.

The complete Python test/coverage run finished with `10263 passed, 106
skipped` in 36:47. Its reports measured 100% of the applicable local Python
scope: 30,690/30,690 lines and statements, and 7,464/7,464 branches; no
measured line, statement or branch was missed. The report was generated before
the final docs/CI-only commits and must be regenerated or bound by the trusted
CI producer before entering a release manifest.

Real PostgreSQL acceptance was also executed in an isolated testcontainers
instance from the pinned `pgvector/pg17` digest:

    USE_TESTCONTAINERS_POSTGRES=1 uv run pytest \
      tests/integration/test_migration_148642dd1207.py \
      tests/integration/test_migration_roundtrip.py \
      tests/integration/test_migration_data.py -q -p no:cacheprovider
    # 3 passed in 121.02 s

The ephemeral database and Ryuk sidecar were removed automatically after the
run; no project compose volume was started or changed. Rust PyO3 sanitizer
all-target tests also passed (`42 passed`, including the benchmark smoke).
These are local recertification signals only: the remote run
`34809326481` remains non-terminal, its source SHA is stale, and the exact
current-SHA Linux mutation/browser/security matrix, strict manifest,
live-ruleset comparison, immutable images and staging/release evidence remain
release-blocking.

## 71. Current-HEAD fast preflight and queue diagnostic (2026-09-14)

The bounded local preflight was rerun after the latest documentation and CI
governance commits, against the exact current HEAD `504b0c4b174d51cb7b653e053163fb91a663026d`:

    $env:PRE_COMMIT_HOME='C:\Temp\pre-commit-cache-university-ecosystem'
    uv run python scripts/fast_preflight.py --max-workers 6 --timeout-seconds 600 --include-output
    # Fast preflight: 6/6 passed; 94.45 s

All six independent checks passed: frontend typecheck (13.674 s), frontend
lint (94.419 s), backend mypy (9.421 s), backend Ruff (0.243 s),
`verify_harness.py --repo-only` (29/29, 40.453 s), and focused CI/quality
contracts (66.824 s). The machine-readable report remains in the ignored
developer path `artifacts/fast-preflight/fast-preflight.json`; it is not a
release artifact and does not replace a trusted current-SHA CI producer.

For the still-running historical run `34809326481` (source SHA
`6c5aca38280861397d7425987e6d1077fc563bf0`), the read-only lower-bound timing
ledger was generated at `C:\Temp\ci-critical-path-34809326481-diagnostic.json`
with report SHA
`f1897c956aeae489d0304379b2420478fe20c5e8f8d9ee571c424f73a18caae5`. At the
snapshot it covered 311 jobs, observed peak concurrency 19/20, and estimated
the lower-bound wall-clock path at 26,795 s. Queue latency dominated setup and
test time (p50 2,839 s, p95 16,976 s, maximum 21,116 s; setup p95 63 s;
test p95 2,150 s). The snapshot contained one failed mutmut execution group
and one cancelled frontend mutation shard, with 40 jobs still queued and 16
in progress; all findings remain stale until that run reaches a terminal
state. This evidence supports investigating runner capacity and repeated
setup, but does not justify raising mutation `max-parallel` or changing any
quality inventory before three comparable terminal green runs.

## 72. Private attachment and service-identity trust boundaries (2026-09-14)

The Codex Security standard scan `05c853b3-47bc-4e1f-8a02-ba2387901cf2`
identified two actionable findings in the pre-change tree: anonymous access to
chat/event blobs through the public static, image-proxy and MinIO routes, and
weak non-empty `INTERNAL_HMAC_SECRET` values accepted by the gateway/backend
identity boundary. A fresh independent post-patch review also challenged the
first remediation against the actual upload format and an over-encoded image
path; both bypasses were reproduced and closed before committing.

Commit `f0ed193e7` (`fix: close private attachment and hmac boundaries`) now:

- blocks `chat_uploads/` and `event_files/` at the unauthenticated static
  mount, static `HEAD` shortcut, image proxy (including repeatedly URL-decoded
  paths), and same-origin Caddy/MinIO storage route;
- maps private attachment URLs to authenticated chat-membership or event-view
  download endpoints while preserving raw storage URLs in persistence for
  cleanup and forwarding compatibility;
- accepts both the current flat upload keys
  (`chat_<id>_<hex>.ext` / `event_<id>_<hex>.ext`) and the legacy hierarchical
  key shape, with strict filename/resource validation and fail-closed malformed
  path handling;
- reads revocation-sensitive membership/event authorization from the primary
  database and returns private, no-store, content-sniff-safe responses;
- regenerates the tracked OpenAPI schema, compatibility snapshot, TypeScript
  SDK and MSW handlers, and updates frontend media resolution for the new
  authenticated URLs;
- enforces non-empty, at least 32-byte, non-placeholder/non-repeated internal
  HMAC material in staging/production in both Python configuration and the Go
  gateway, while retaining development/test compatibility without logging
  secret material.

Focused evidence for this commit:

    uv run pytest -q -p no:cacheprovider \
      tests/test_private_attachments.py \
      tests/test_private_attachment_api_closure.py \
      tests/test_images_api_closure.py tests/test_static_assets.py \
      tests/test_chat_uploads.py tests/test_event_file_upload.py
    # 40 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_chat_uploads.py tests/test_chat_command_service.py \
      tests/test_chat_forwarding.py tests/services/test_chat_helpers.py
    # 65 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_websocket_chat.py tests/test_events_api_closure.py \
      tests/test_event_file_upload.py tests/test_image_proxy.py \
      tests/test_images_api.py
    # 81 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_mfa_openapi_artifacts_contract.py \
      tests/contracts/test_openapi_contract.py tests/test_chat_message_contract.py \
      tests/test_openapi_links.py
    # 42 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_internal_hmac_secret_security.py tests/test_core_config.py \
      tests/test_config_mixins_coverage.py tests/test_cors_settings_closure.py \
      tests/test_jwt_settings_closure.py tests/test_auth_reset_foundation.py \
      tests/test_api_deps_auth_behavior_closure.py
    # 133 passed

    cd frontend
    npm run generate:api
    npm run typecheck
    npm run lint -- --no-warn-ignored
    npm run test -- --run \
      src/utils/__tests__/media.test.ts \
      src/components/messenger/ChatWindow.branches.test.tsx --silent=true
    # generation, typecheck and lint passed; 61 frontend tests passed

    node --test scripts/generated-msw-contract.test.mjs \
      scripts/stryker-inventory.test.mjs scripts/run-stryker.test.mjs
    # 114 passed

    cd services/gateway
    go test ./...
    go vet ./...
    # all gateway packages passed; gofmt produced no diff

The repository pre-commit suite also passed for the exact 34-file staged set:
Ruff check/import/format, detect-secrets, gitleaks-equivalent secret scan,
Bandit, mypy, no-Python-2-except, Semgrep and Renovate validation. No
`.secrets.baseline` change was needed. Local `go test -race` remains
environment-blocked because this Windows host has `CGO_ENABLED=0` and no `gcc`;
the Linux CI race gate remains mandatory. Direct public URLs already issued by
an external public CDN cannot be revoked by an application route alone; the
staging/release gate must therefore verify private bucket/CDN ACLs and reject
public object access before release.

This checkpoint closes the code-level findings but is not a release claim. A
fresh current-SHA security scan, full mutation/coverage matrix, current-SHA
quality manifest, and the remaining Docker/Kubernetes/TLS/observability,
browser, performance and release evidence are still required.

## 73. External-audit trust-boundary and release-storage closure (2026-09-14)

The independent platform audit and a second security review identified two
remaining release-critical boundaries that must be explicit in the MVP closure:

1. File-processing callers could previously submit attacker-selected source and
   destination object keys. A JWT proves identity, but not ownership of the
   objects named in those keys. The safe interim contract is therefore
   fail-closed in staging/production until a trusted backend owner-check issues
   a capability; no ingress may silently fall back to key-only authorization.
2. The canonical Helm staging overlay selected `MINIO_SECURE=true` while the
   backend still defaulted to local static storage. With a read-only container
   root this made uploads non-durable or unavailable. Release values must select
   S3/MinIO explicitly and inject credentials only from the application Secret.

The current implementation adds a shared, domain-separated, short-lived
processing capability contract in `gen/go/file_processor/v1/capability.go`:

- HMAC-SHA-256 proofs bind an ID, operation type, exact normalized source and
  destination keys, user, session, optional tenant, expiry and nonce;
- tokens have a 15-minute maximum lifetime, bounded size, CSPRNG nonce support,
  constant-time MAC/claim comparisons and generic denial responses;
- the gateway verifies the proof against the authenticated Gin identity before
  forwarding only verified metadata; the file processor repeats the check at
  the gRPC boundary and propagates the opaque proof into Temporal;
- GraphQL and NATS ingress apply the same proof contract, and Temporal receives
  only the verified, object-bound fields needed for processing; the opaque
  capability proof is deliberately not persisted in workflow history. Temporal
  workflow IDs reject duplicate starts to make capability replay fail closed;
- release configuration requires at least 32 bytes of non-placeholder,
  non-repeated capability secret material. Development may omit it only for
  compatibility; release charts and Compose overlays wire it from the reviewed
  internal Secret contract.

This closes the arbitrary-key path by default, but it does not invent an
ownership issuer. Before enabling user-facing file processing in a release,
the backend must add the owner/tenant/resource check and mint a capability for
the exact request; until then the release endpoint remains intentionally
denied rather than accepting unbound keys. The capability header is not a
replacement for bucket policy: MinIO/S3 and any CDN must still deny direct
public access to private prefixes.

The Helm storage closure now sets `backend.config.storageBackend=s3`, a
non-empty bucket and HTTPS endpoint in staging, validates those invariants for
staging/production, injects `STORAGE_S3_*` values and `minio-*` Secret keys into
the read-only backend, and derives the endpoint from the reviewed deploy input.
Focused evidence:

    uv run pytest -q -p no:cacheprovider \
      tests/test_helm_staging_contract.py tests/test_docker_startup_contracts.py
    # 303 passed

    cd services/gateway && go test ./...
    # all packages passed
    cd services/file-processor && go test ./...
    # all packages passed
    cd gen/go && go test ./...
    # shared capability package passed

The old read-only CI run `34809326481` is now terminal (315 jobs: 296
successful, 5 failed, 1 cancelled, 13 skipped). Its failures are stale-source
evidence: mutmut group 8 has one survivor (91.67%), group 112 has one timeout,
and frontend mutation evidence is incomplete because shard 31 was cancelled.
It must not be used as current-SHA certification; a fresh run is required
after the capability/storage changes.

The capability/storage changes are still uncommitted at this checkpoint. The
four user-owned untracked paths remain preserved and unstaged:
`.tmp_preflight/`, `.tmp_stryker_18/`, `.tmp_stryker_22/`, and
`docs/audits/AUDIT_PLATFORM_FULL.md`. Remaining release gates are unchanged:
fresh current-SHA security scan and manifest, Linux Go race/static analysis,
all mutation/coverage/browser/Lighthouse/Schemathesis shards, immutable image
and Docker smoke, Kubernetes TLS/observability/CWV staging, chaos/rollback,
and final SHA-bound audit/release approval.

## 74. Strict file-processor JWT/JWKS and replay hardening (2026-09-14)

The file-processor trust boundary is now aligned with the backend/gateway JWT
contract and has explicit key-rotation and replay controls. This is a code-level
closure, not a release certification:

- JWT verification requires the configured audience, issuer (mandatory in
  staging/production), `exp`, `iat`, bounded token age, `sub`, `jti` and the
  boolean `is_active` claim. Release environments are RS256-only and require a
  revocation Redis check; Redis failures fail closed.
- A bounded JWKS client accepts only HTTPS/HTTP endpoints without credentials,
  query strings or fragments, never follows redirects, limits responses to
  64 KiB, accepts RSA/RS256 keys with a canonical `kid`, at least 2048-bit
  modulus and exponent 65537, and rejects duplicate or malformed keys.
- Key snapshots are immutable and atomically replaced. Failed refreshes retain
  the last-known-good snapshot; startup fails closed when no static or fetched
  trust root is available. Static PEM fallback is constrained to the reviewed
  active `kid`.
- Capability nonces are admitted once through Redis `SET NX` with bounded TTL;
  duplicate delivery is a normal rejection, while Redis errors fail closed.
  The process-local fallback registry is bounded and covered independently for
  development/test operation.
- JWKS-only release configuration, issuer/audience wiring, revocation Redis,
  active `kid` and refresh bounds are represented in Compose, Helm values,
  deployment templates and schema validation. Weak or placeholder capability
  secrets remain rejected in release environments.

Focused local evidence on the current worktree:

    cd services/file-processor
    gofmt -w <modified Go sources>
    go test -count=1 ./...
    # passed
    go vet ./...
    # passed
    golangci-lint run --config ../../.golangci.yml --timeout 5m ./...
    # 0 issues

    uv run pytest -q -p no:cacheprovider \
      tests/test_auth_jwt_payload.py tests/test_auth_jwt_rs256.py \
      tests/test_jwt_settings_closure.py tests/test_security_tier0.py \
      tests/test_cdc_outbox.py tests/test_cdc_outbox_closure.py \
      tests/test_file_processor_keda_contract.py
    # 90 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_docker_startup_contracts.py tests/test_helm_staging_contract.py
    # 303 passed

    python verify_harness.py --repo-only
    # 29 passed, 0 failures/errors

    cd frontend
    npm run typecheck
    npm run lint -- --no-warn-ignored
    npm run build
    # all passed; orchestrated build completed with stable client/server/PWA artifacts

The local Windows host cannot execute the mandatory Go race gate because it has
no C compiler and `CGO_ENABLED=0`; Linux CI remains the source of truth for
`go test -race`, full mutation/coverage, browser, Lighthouse and Schemathesis
evidence. The current worktree also contains user-owned untracked audit and
temporary directories that must remain unstaged. Before release, run a fresh
current-SHA security scan, regenerate the quality manifest and prove its hashes,
execute the Linux matrix, immutable six-image digest smoke, Kubernetes
TLS/observability/CWV checks, chaos/rollback scenarios and the final
SHA-bound audit. Do not claim MVP release readiness from these local checks
alone.

## 75. Current CI blocker closure and recertification checkpoint (2026-09-14)

Diagnostic run `34874327356` (head `b3c15342a797bec80e3bfacaa3c29a9fb4129b41`)
was inventoried from its job outputs before making this checkpoint. It is
diagnostic evidence only: the run finished with 118 jobs (`85` successful,
`9` failed and `24` skipped) and must not be treated as a release certificate.
The nine root failures were:

- orphaned generated Go capability tests in the source/test inventory;
- a Semgrep suppression ledger line drift after middleware edits;
- Rust nightly `llvm-cov` object files being removed or invalidated by the
  stable coverage target tree;
- gateway synchronous file-processing handler complexity above the configured
  limit;
- file-processor statement coverage below the required floor;
- ws-hub statement coverage below the required floor;
- an entropy-invalid CWV RUM fixture;
- approved legacy chat/event routes missing from the dependency inventory;
- the aggregate CI-success job cascading from the preceding failures.

The current worktree contains the corresponding code and contract fixes:

- generated `gen/go` files are classified before authored capability sources,
  ownership and inventory rules include the generated root, and focused tests
  prevent future orphan drift;
- the Semgrep suppression remains exact, line-bound, owner-bound and expiry-
  bound at the middleware's current line;
- each Rust component now has a separate fail-fast nightly
  `CARGO_TARGET_DIR`, exported before nightly cleanup/branch instrumentation;
  stable commands, thresholds, artifact paths, uploads and provenance are
  unchanged;
- gateway request binding, capability verification, RPC context creation and
  gRPC error mapping were extracted into cohesive helpers without changing
  the trust boundary or response contract;
- ws-hub has an explicit staging/production missing-internal-token regression
  test;
- file-processor authentication, JWKS, Redis revocation/replay, startup and
  authorization boundary paths have focused tests and test-only seams. A
  fresh aggregate profile from `services/file-processor` reports `100.0%`
  statements for every package with no zero-count ranges;
- CWV fixtures use entropy-valid deterministic test material, and the route
  inventory records the two approved legacy file-download routes plus the
  corrected database dependency.

Fresh local evidence for this checkpoint:

    python verify_harness.py --repo-only
    # 29 passed, 0 failures/errors

    uv run pytest -q -p no:cacheprovider \
      tests/test_quality_inventory.py
    # 73 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_semgrep_sarif_validator.py
    # 33 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_route_dependency_inventory.py \
      tests/test_cwv_rum_security.py \
      tests/test_non_auth_quality_closure.py
    # 101 passed

    cd services/file-processor
    go test -count=1 ./...
    go test -count=1 -coverprofile=<fresh-profile> ./...
    go tool cover -func=<fresh-profile>
    # all packages passed; aggregate statements 100.0%, no zero ranges
    go vet ./...
    golangci-lint run --config ../../.golangci.yml ./...
    # 0 issues

    python scripts/check_route_dependency_inventory.py
    python scripts/quality/check_orphans_and_anti_patterns.py
    # both passed

The mandatory Linux-only race gate remains external evidence: this Windows
host has `CGO_ENABLED=0` and no C compiler, so `go test -race` cannot be
executed locally. The untracked user-owned directories
`.tmp_preflight/`, `.tmp_stryker_18/`, `.tmp_stryker_22/`, the external audit
`docs/audits/AUDIT_PLATFORM_FULL.md`, and the generated coverprofile
`services/file-processor/coverage_capability` remain untouched and unstaged.
The newly authored file-processor closure tests are intended tracked inputs
and must be staged explicitly.

This checkpoint is not a release claim. A new current-SHA push must still
produce a schema-valid quality manifest, fresh security scan, Linux race and
mutation/coverage evidence, browser/Lighthouse/Schemathesis results, immutable
six-image and Docker smoke evidence, Kubernetes TLS/observability/CWV checks,
chaos/rollback results and the final SHA-bound audit. CI timing/capacity
optimizations remain evidence-gated; no matrix cap or quality threshold was
changed from the diagnostic run.

## 76. Rust coverage tool compatibility fix (2026-09-14)

Fresh PR run `34882790312` (PR `#1266`, source head
`9eaa2f68e576698fefb5c299be66fc721e2a2f0c`) reproduced one root failure in
`Rust - cargo test (x3 crates) + wasm-pack + coverage` (job
`104105919631`). All 76 `rust_ext` tests passed in both stable and nightly
runs and the stable `llvm.json`/`codecov.json` reports were written. The
nightly branch report alone failed with:

    warning: not found object files (searched directories: .../rust-native-nightly/llvm-cov-target/debug)
    error: ... llvm-cov export ... No filenames specified!

The runner's current nightly Rust/Cargo (`rustc 1.100.0-nightly`) uses Cargo's
build-dir v2 layout and emitted the instrumented test executable under
`target/debug/build/<crate>/<hash>/out/`. The pinned `cargo-llvm-cov 0.6.19`
collector only scanned `target/{debug,release}` and intentionally skipped
`build`, so this was a deterministic report-discovery incompatibility rather
than a test or coverage regression.

The workflow and all version fixtures now pin `cargo-llvm-cov 0.9.1`, whose
collector supports the new build-dir layout (including the Windows path
matching fix), while retaining `--branch`, `--locked`, separate stable/nightly
target roots, and all existing report/provenance/threshold gates. The exact
references updated are `.github/workflows/ci.yml`,
`tests/test_quality_workflow_contract.py`, `tests/test_quality_manifest_v2.py`,
and `tests/quality_normalizer_v2_testkit.py`.

Focused local contract/manifest tests pass after the update. The fix is
committed separately and must be validated by a fresh Linux CI run; the failed
run `34882790312` remains historical evidence only. No matrix cap, exclusion,
quarantine, threshold, or mutation/security gate was changed.

## 77. CI timing, retry, and capacity-claim audit (2026-09-15)

The current workflow and contract tests were audited for timing-ledger scope,
failed-job rerun behavior, watchdog/retry semantics, and the documented runner
budget. This is a source-level audit; it is not current-SHA CI evidence.

- The value `20` is a repository-local operational planning budget, not a
  GitHub account-wide hosted-runner cap and not a cross-workflow semaphore.
  `strategy.max-parallel` is workflow-local, so companion workflows may still
  overlap. CI comments and the mutation-matrix step summary now say this
  explicitly; no matrix cap or quality gate changed.
- `scripts/quality/analyze_ci_critical_path.py` provides API-only queue/setup/
  test/artifact timing, concurrency, and explicit retry/timeout classifications
  in `diagnostic-lower-bound` mode. It does not prove the dependency DAG,
  archive bytes, runner RSS/CPU, billed minutes, or a strict release artifact.
  The `ci-success` report remains diagnostic-only until those independent
  evidence requirements are supplied.
- Mutmut and Stryker mutation consumers use attempt-bound selectors and choose
  only validated current-or-earlier candidates. Coverage shard aggregates are
  intentionally stricter: backend coverage in `ci.yml` and frontend unit
  coverage in `reusable-frontend-tests.yml` download only the current attempt.
  A GitHub failed-job rerun does not rerun successful shard producers, so those
  aggregates cannot silently mix attempts; a complete same-attempt producer
  set (or a full workflow rerun) is required. The existing contract test keeps
  this fail-closed boundary explicit. No unsafe all-attempt wildcard merge was
  introduced.
- Watchdog and retry behavior remains bounded: mutmut charges setup and
  evidence headroom and materializes incomplete evidence on failure, while
  network retries are limited to known transient transport failures. There is
  still no repository-wide transient classifier or generic cross-job heartbeat,
  and no claim of one was added.

The focused workflow, analyzer, renderer, and artifact-selector tests remain
the acceptance evidence for these source-level contracts. Fresh Linux CI,
three comparable green runs before any capacity experiment, and complete
current-SHA mutation/coverage provenance remain release-blocking.

## 78. Fail-closed Helm retries and stale-run mutation survivor closure (2026-09-15; pending push)

The fresh PR run `34923631288` on source SHA
`2774de52d158cf0b7611b331586014a8420a1df2` exposed one real mutation survivor
before the staged retry hardening was published. Mutmut execution group 10
(`104249723443`) changed the blocked static response header
`X-Content-Type-Options: nosniff` to `XXnosniffXX`; the old test asserted only
status and cache policy, so the mutant survived at 87.50%. This is stale-source
evidence, not a release result. The regression test now asserts the exact
security header, and a local activation of the exact generated mutant returns
`XXnosniffXX`, proving the new assertion is mutation-sensitive.

The staged CI reliability change adds the dependency-free
`scripts/ci/helm_dependency_build.py` helper and routes Helm dependency setup
in the PR, deploy, nightly, reusable-backend and reusable-security workflows
through it. The helper:

- retries only output-proven transient transport/rate-limit failures;
- fails fast for authentication, chart, lock and validation errors;
- bounds each attempt, preserves the first failure output and validates
  required non-empty non-symlink archives;
- uses a fixed argv with shell execution disabled and keeps all existing
  inventory, artifact and quality gates unchanged.

The workflow contract tests were updated to require the helper invocation and
to reject direct `helm dependency build` snippets. Local focused evidence on
the pending working tree:

    uv run pytest -q -p no:cacheprovider \
      tests/test_ci_helm_retry_policy.py \
      tests/test_quality_workflow_contract.py \
      tests/test_mfa_deploy_workflow_contract.py
    # 232 passed

    uv run pytest -q -p no:cacheprovider tests/test_private_attachments.py
    # 6 passed

    uv run ruff check scripts/ci/helm_dependency_build.py \
      tests/test_ci_helm_retry_policy.py
    uv run ruff format --check scripts/ci/helm_dependency_build.py \
      tests/test_ci_helm_retry_policy.py
    uv run mypy --config-file pyproject.toml \
      scripts/ci/helm_dependency_build.py tests/test_ci_helm_retry_policy.py
    python scripts/quality/validate_ci_check_catalog.py
    # all passed; catalog remains 55 workflows / 182 source jobs

The current run must finish so every stale-source failure is inventoried, then
the pending changes require a small commit, push, and a new SHA-bound full
matrix. No mutation inventory, coverage threshold, retry gate, or skip was
weakened. The staged `.secrets.baseline` refresh and all user-owned untracked
paths remain preserved and must be rechecked before commit.

## 79. Equivalent-mutant closure for static headers and image limits (2026-09-15; pending push)

The same stale-source matrix later exposed two additional mutmut survivors that
were proven equivalent under the actual runtime contracts:

- group 19 (`104249723545`) changed only the `Cache-Control` field-name casing
  in `PublicStaticFiles.get_response`. Starlette lowercases response field
  names before ASGI emission and HTTP field names are case-insensitive, so no
  consumer-visible behavior can distinguish the mutation. The source now keeps
  the readable spelling in a module-level header constant (outside mutmut's
  function mutation universe), without a suppression; security values
  (`no-store` and `nosniff`) remain fully mutation-tested by the response
  contract.
- group 16 (`104249723409`) changed the `getattr` default for
  `settings.image_max_pixels` from `0` to `None`. The validated settings model
  always supplies a positive integer, making both defaults equivalent for a
  normal deployment. The implementation now uses an explicit unique sentinel
  for a genuinely absent setting, preserving the existing zero/falsey fallback
  while making the missing-attribute behavior observable and fail-closed; a
  focused test covers that compatibility path.

The local regression evidence is:

    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy.py tests/test_private_attachments.py
    # 41 passed

    uv run ruff check app/core/static.py app/services/image_proxy.py \
      tests/test_image_proxy.py tests/test_private_attachments.py
    uv run ruff format --check app/core/static.py app/services/image_proxy.py \
      tests/test_image_proxy.py tests/test_private_attachments.py
    uv run mypy --config-file pyproject.toml \
      app/core/static.py app/services/image_proxy.py
    git diff --check
    # all passed

The raw-header experiment was discarded because Starlette intentionally emits
lower-case ASGI names; the final contract tests therefore assert the required
case-insensitive security values rather than an invalid wire casing. This is a
structural elimination of an external semantic-equivalence mutant, not a
quality threshold, inventory, or test exclusion. Fresh current-SHA
mutation evidence is still required before considering either stale survivor
closed.

## 80. Additional stale mutmut boundary and validation-survivor closure (2026-09-15; pending push)

The continuing stale-source run `34923631288` exposed three more focused
survivors; each was reproduced and closed without reducing the mutation
inventory or adding an exclusion:

- group 22 (`104249724177`) changed `_process_image`'s resize guard from
  `width < source_width` to `width <= source_width`. A requested width equal to
  the source must be a no-op; the new focused test asserts that `resize` is not
  called at the equality boundary.
- group 23 (`104249724290`) replaced the computed proportional resize height
  with `None`. A real-Pillow regression test now downsizes a 10x20 PNG to 5x10
  and checks the encoded dimensions, so an invalid target height fails
  deterministically rather than being hidden by a permissive mock.
- group 26 (`104249724379`) changed the `private_attachment_storage_key`
  filename-validation error text only. The contract now asserts the exact
  `Invalid attachment filename` message for a valid resource id with an
  invalid filename, preventing security-facing error drift.
- group 29 (`104249724427`) changed `normalized.encode("utf-8")` to the
  case-insensitive equivalent `normalized.encode("UTF-8")`. The implementation
  now uses Python's documented default UTF-8 codec (`normalized.encode()`),
  removing an unobservable literal mutation structurally rather than hiding it
  with a pragma; existing entropy and Unicode validation behavior is retained.

Local focused evidence on the pending tree:

    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py tests/test_image_proxy.py \
      tests/test_private_attachments.py tests/test_config_mixins_coverage.py
    # 114 passed

    uv run ruff check app/core/config/security.py \
      tests/test_image_proxy_closure.py tests/test_private_attachments.py
    uv run ruff format --check app/core/config/security.py \
      tests/test_image_proxy_closure.py tests/test_private_attachments.py
    uv run mypy --config-file pyproject.toml app/core/config/security.py
    git diff --check
    # all passed

These fixes are pending a small commit and fresh current-SHA mutation run;
the old run remains diagnostic evidence only and may reveal further survivors
until its matrix reaches a terminal state.

## 81. Security-length and attachment-validation survivor closure (2026-09-15; pending push)

Stale run `34923631288` then exposed group 30 (`104249724496`) with two
survivors:

- `app.core.config.security._validate_internal_hmac_secret_strength__mutmut_6`
  changed the minimum-length comparison from `< 32` to `<= 32`. The boundary
  is intentional: exactly 32 encoded bytes is the documented minimum. A
  focused test now supplies a non-repeating 32-byte value and asserts it is
  accepted, so the boundary mutation is killed.
- `app.services.private_attachments.private_attachment_storage_key__mutmut_5`
  changed the filename guard from a disjunction to a conjunction. The
  `_FILENAME_RE` allow-list is anchored and already rejects both `/` and `\\`,
  making the extra separator checks redundant and semantically equivalent.
  The production guard is simplified to the single `safe_filename is None`
  sentinel, eliminating that duplicate boolean surface without a suppression;
  existing traversal/separator cases remain covered.

Focused local evidence:

    uv run pytest -q -p no:cacheprovider \
      tests/test_config_mixins_coverage.py tests/test_private_attachments.py
    # 74 passed

    uv run ruff check app/core/config/security.py \
      app/services/private_attachments.py \
      tests/test_config_mixins_coverage.py tests/test_private_attachments.py
    uv run ruff format --check app/core/config/security.py \
      app/services/private_attachments.py \
      tests/test_config_mixins_coverage.py tests/test_private_attachments.py
    git diff --check
    # all passed

Fresh current-SHA mutation evidence remains required; this old-run finding is
not a release result.

## 83. Exact minimum-length mutation boundary (2026-09-15; pending push)

Stale run `34923631288` exposed group 31 (`104249725112`) with survivor
`app.core.config.security._validate_internal_hmac_secret_strength__mutmut_7`,
which changed `< 32` to `< 33`. This is the same security boundary represented
by group 30's `<= 32` mutant, not an equivalent behavior: exactly 32 encoded
bytes is valid and must remain accepted. The focused non-repeating 32-byte
secret test added for group 30 kills both boundary mutations while preserving
the documented minimum entropy contract.

No production threshold was changed and no test was weakened. The old run is
still diagnostic; fresh current-SHA mutation evidence must prove the complete
inventory at 100% viable score after push.

## 84. Redundant attachment-separator mutation closure (2026-09-15; pending push)

Stale group 33 (`104249725224`) changed the explicit slash check in
`private_attachment_storage_key` to a different slash literal. This cannot
change behavior because the anchored `_FILENAME_RE` rejects every path
separator before that clause is reached. The already-committed simplification
to `if safe_filename is None:` removes the redundant predicate and all of its
equivalent literal mutations while retaining the same fail-closed filename
allow-list and exact error contract. No exclusion or quality-threshold change
was introduced.

## 82. CI capacity audit and evidence-gated speed policy (2026-09-15)

The read-only capacity audit of workflow sources and stale run `34923631288`
confirms that the current topology is already bounded and must not be tuned by
intuition:

- the repository uses per-ref cancellation (`ci-matrix-${{ github.ref }}`) and
  current caps of Stryker 6, mutmut 10, backend/Go 2, E2E 2 and Schemathesis 4;
- the diagnostic run reached 18 concurrent jobs against the documented 20-job
  operational budget, while the long pole was test execution rather than
  dependency setup or artifact upload;
- Stryker duration is materially skewed (p50 about 16.7 minutes, p95 about
  46.3 minutes), whereas mutmut groups are comparatively balanced (p50 about
  25.5 minutes, p95 about 29.2 minutes);
- the referenced prior capacity baseline was cancelled and therefore is not a
  qualifying green comparison. No current topology has three comparable
  terminal green runs.

Accordingly, no `max-parallel`, shard count, timeout, retry policy, cache
scope, inventory, or quality threshold is changed in this checkpoint. After
three comparable current-topology green runs, remeasure queue p50/p95, setup,
test, artifact, retry/timeout, RSS/CPU and billed-minute data before an
isolated A/B change (Stryker duration-aware balancing first). Any increase
must be reverted on queue starvation, timeout, RSS, provenance, or reliability
regression. This preserves the speed goal without weakening release gates.

## 85. Static attachment-path dot-segment hardening (2026-09-15; pending push)

The independent security audit found that `is_private_static_path` decoded
percent-encoding and normalized separators but did not collapse `..` path
segments before checking the private attachment prefixes. Starlette's static
file resolver canonicalizes those segments with `realpath`, so a path such as
`foo/../chat_uploads/...` could reach a private attachment while the guard
classified it as public. This was a pre-existing security boundary, not a
regression introduced by the mutation-closure commits.

The guard now applies POSIX dot-segment normalization after the existing
repeated URL-decoding and separator normalization, while retaining the
existing `/static/` mount-prefix handling. Focused tests cover direct and
double-encoded parent segments for both attachment prefixes and retain the
public-avatar control case. The change is fail-closed and does not alter
authorization or the static resolver itself.

Focused evidence:

    uv run pytest -q -p no:cacheprovider tests/test_private_attachments.py
    # 6 passed

    uv run ruff check app/core/static.py tests/test_private_attachments.py
    uv run ruff format --check app/core/static.py tests/test_private_attachments.py
    git diff --check
    # all passed

Fresh current-SHA security and E2E evidence remains required after push.

## 86. Image pixel-limit error contract (2026-09-15; pending push)

Stale run group 34 (`104249725185`) exposed a viable mutmut survivor in
`ImagePixelLimitError.__init__`: changing the `width is None` branch swapped
the decoder-level and dimension-level error messages. The implementation's
two safety paths are intentionally distinct, so the focused contract now
constructs both variants and asserts their exact public messages. This closes
the survivor with a deterministic boundary test and does not alter the pixel
budget or decoder behavior.

Focused evidence:

    uv run pytest -q -p no:cacheprovider tests/test_images_v2.py
    # 28 passed

    uv run ruff check app/utils/images.py tests/test_images_v2.py
    uv run ruff format --check app/utils/images.py tests/test_images_v2.py
    git diff --check
    # all passed

The historical job remains stale evidence; a fresh current-SHA mutation run
must verify the complete frontend/backend mutation inventory after push.

## 87. Full application scope for the local mypy hook (2026-09-15; pending push)

The external audit's SEC-12 review found that the pre-commit mypy hook only
selected `app/auth`, `services`, `api`, `core`, `repositories` and `graphql`,
while CI's authoritative `pyproject.toml` scope is the complete `app/` tree.
That left `app/models`, `app/schemas`, `app/utils`, CLI modules and
`app/main.py` unchecked on local commits. The hook now uses the same anchored
`^app/` scope. Its isolated environment also declares the locked CLI runtime
packages `rich==15.0.0` and `typer==0.25.1`, so the expanded check is
reproducible instead of failing on missing imports.

The workflow contract asserts the scope, and the full isolated hook was run:

    uv run pytest -q -p no:cacheprovider \
      tests/test_workflow_fail_closed_contracts.py -k precommit_split
    # 1 passed, 37 deselected

    $env:PRE_COMMIT_HOME='C:\\Temp\\pre-commit-cache-mvp'
    pre-commit run mypy --all-files --show-diff-on-failure
    # Passed; 351 source files checked

This closes the local-hook gap without changing CI's strict mypy policy or
adding an exclusion. The external audit's SEC-07 detect-secrets baseline
verification and Linux-only tooling checks remain evidence-gated follow-up
items; no unverified baseline entry was silently accepted here.

## 88. Cross-platform mutation evidence containment (2026-09-15; pending push)

The frontend verifier reproduced a Windows-only false rejection when
`repositoryRoot` ended with a path separator: the lexical
`startsWith(root + path.sep)` check constructed a doubled separator and
reported the valid `frontend/.depcheckrc` evidence path as escaping the
repository. `resolveEvidencePath` now resolves the root once and uses
`path.relative` to reject `..`, `..${path.sep}` and absolute relatives while
accepting the root itself and valid descendants. The canonical-relative input
validator remains unchanged and still rejects absolute, dot-segment and empty
paths.

Focused evidence from commit `43f81ba90a6dd632df0eadab761e1ae36cb59474`:

    node --test frontend/scripts/verify-stryker-evidence.test.mjs
    # 15 passed
    npx eslint frontend/scripts/verify-stryker-evidence.mjs \
      frontend/scripts/verify-stryker-evidence.test.mjs
    # passed
    npm run typecheck --prefix frontend
    # passed
    git diff --check
    # passed

This is a tooling correctness/security-boundary fix only; no mutation source,
test or evidence inventory was reduced. A fresh current-SHA Linux Stryker
producer and round-trip verifier remain release-blocking.

## 89. SBOM stale-PR runner reclamation (2026-09-15; pending push)

The CI capacity audit found that `.github/workflows/sbom.yml` used
`github.run_id` for every non-push event and cancelled only push runs. Every
new PR commit therefore left the previous read-only vulnerability gate queued
or running, consuming the shared hosted-runner budget and delaying required
checks. The workflow now groups PR runs by PR number (with ref fallback),
cancels superseded PR and main-push runs, and preserves unique manual
`workflow_dispatch` evidence. The trusted main-only attestation guards and
all SBOM/vulnerability jobs are unchanged.

The contract test in `tests/test_quality_workflow_contract.py` first failed
against the old expression, then passed after the change; generic PR
workflow cancellation coverage remains intact. Commit `b1502b537` contains
only the workflow and contract-test change. This is a bounded stale-run
optimization, not a mutation/test inventory or threshold change. Global
cross-workflow concurrency remains evidence-gated; no cap increase or
timeout inflation is allowed before three comparable green runs.

## 90. SEC-07 baseline triage disposition (2026-09-15; evidence pending)

The independent audit's wording that 326 entries were "unverified" was
rechecked against the current baseline and detect-secrets 1.5.0 semantics.
The current `.secrets.baseline` has 156 paths and 322 finding identities;
every entry has explicit `is_secret: false`, and the scanner reports
`322 false positives, 0 unknown, 0 true positives`. `detect-secrets audit
.secrets.baseline` returns `Nothing to audit!`. In this version,
`is_verified: false` is detector/plugin verification metadata and is not the
manual false-positive triage decision; the latter is `is_secret: false`,
which the fail-closed verifier requires for every baseline entry.

No baseline entry is changed, no suppression is added, and no field is
mass-marked `is_verified=true`. SEC-07 is therefore `CODE-COMPLETE /
FRESH-EVIDENCE-PENDING`: the only remaining proof is a current-SHA Linux
all-files scan plus trusted-base comparison in CI. A new finding, malformed
artifact, or new trusted-base suppression must still fail closed.

## 91. Cross-workflow runner contention evidence (2026-09-15; policy pending)

The expanded CI audit measured the real hosted-runner boundary rather than
the per-workflow strategy values. While the historical PR matrix was still
draining, a scheduled Nightly Full Quality Gate occupied nine runners and
three unrelated Dependabot PR runs occupied three more; the old PR run had
seven active jobs. The observed combined peak was 19/20 runners, so the
historical run's `max-parallel: 10` mutmut lane could not obtain its nominal
capacity. The run-level API continued to report `queued` while jobs were
active; paginated job records remain the source of truth.

This is an operational scheduling constraint, not evidence to lower a gate.
No other user's run is cancelled automatically and no matrix cardinality,
timeout or retry policy is changed in this checkpoint. Safe follow-up after
three comparable green PR runs is to evaluate a tested admission policy for
scheduled heavy matrices (or a separate runner pool) and to consolidate
duplicate external producers only after the required-check catalog and branch
protection are updated together. Any candidate must preserve first-failure
artifacts, provenance and all required contexts, and must be reverted on
queue starvation, timeout, RSS/CPU, or reliability regression.

## 92. HMAC entropy-diversity survivor closure (2026-09-15; pending push)

Stale run `34923631288` exposed group 43 (`104249726174`) with a viable
survivor in `_validate_internal_hmac_secret_strength`: replacing the
low-diversity/repeated predicate's `or` with `and` allowed a 32-byte value
containing 31 `A` bytes and one `B`. This is below the minimum diversity
contract even though it meets the length boundary and does not match the
repeated-block regular expression.

`tests/test_internal_hmac_secret_security.py` now includes that exact
boundary and asserts the production validator raises `ValidationError`.
The focused suite (`4 passed` for the weak/32-byte contract), Ruff,
format-check and pre-commit all pass in commit `ae53f1f27`. The production
predicate and thresholds were not weakened; fresh current-SHA mutmut evidence
must still prove the complete inventory.

## 93. Group-44 exact survivor closure (2026-09-15; pending push)

The stale mutmut group-44 evidence was inspected from its immutable selected
manifests rather than inferred from the aggregate failure. It contained two
viable survivors:

* `_validate_internal_hmac_secret_strength`: `len(set(encoded)) < 4` changed
  to `<= 4`. The production contract now exercises a non-periodic 32-byte
  value with exactly four distinct bytes (`"A" * 29 + "BCD"`) and asserts it
  is accepted. This boundary is valid because the implementation rejects
  fewer than four distinct bytes; it also remains outside the repeated-block
  regular expression. Together with the two-distinct-byte rejection case in
  §92, both the strict and inclusive comparison mutants are killed.
* `image_proxy._process_image`: original-mode `img.save(...,
  format=original_format)` changed to `format=None`. The existing focused
  image-proxy contract supplies a PNG source and asserts the save callback
  receives `format="PNG"`, so the mutant fails deterministically without
  altering production behavior.

Focused evidence after adding the exact diversity boundary:

    uv run pytest -q -p no:cacheprovider \
      tests/test_internal_hmac_secret_security.py \
      tests/test_image_proxy_closure.py
    # 15 passed (one expected Pydantic development warning)

    uv run ruff check tests/test_internal_hmac_secret_security.py \
      tests/test_image_proxy_closure.py
    uv run ruff format --check tests/test_internal_hmac_secret_security.py \
      tests/test_image_proxy_closure.py
    git diff --check
    # all passed

The test-only change is committed as `2eb6be8ff`. The selected group-44
artifact was produced against an older SHA; a fresh current-SHA mutation run
must still verify the full inventory and score.

## 94. Image-proxy mutation boundaries and local regression evidence (2026-09-15; pending push)

The next stale groups were classified from their selected source artifacts:

* group 46 (`104249726248`) targeted the spelling of the `Cache-Control`
  response header. The historical source had a case-equivalent literal; this
  was removed from the mutmut function universe by the module-level
  `_CACHE_CONTROL_HEADER` constant in commit `f8cdf3efe`, while the response
  value and security headers remain covered. No HTTP-level test is allowed to
  assert a wire casing that the ASGI/HTTP contract deliberately normalizes.
* group 47 (`104249726266`) removed the `format="PNG"` keyword from original
  image encoding. The existing `test_process_image_does_not_resize_when_width_matches_source`
  callback requires that keyword and exact format, so the mutant fails rather
  than being treated as an equivalent spelling change.
* group 48 (`104249726411`) replaced the high-quality resize filter with
  `None`; the focused suite now patches `_resolve_resample_filter` with a
  sentinel and asserts it is passed unchanged to `img.resize`.
* group 49 (`104249726473`) removed the resize target-size argument; the same
  focused contract asserts `(width, new_h)` and the expected sentinel in the
  exact call, preserving both geometry and quality behavior.

The image and HMAC contracts were run together after these additions:

    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py \
      tests/test_internal_hmac_secret_security.py
    # 16 passed (one expected Pydantic development warning)

The new resize assertion is committed as `82dccb1ed`. It changes no mutation
selection, timeout, retry, or coverage threshold. The stale group artifacts
predate these tests; only a fresh current-SHA producer can certify the full
mutation inventory.

The full local backend regression also completed on this Windows host:

    uv run pytest -q -p no:cacheprovider
    # 10,363 passed, 106 platform/integration-guard skips,
    # 2 deselected, 1 expected warning; exit 0 (2:20:44)

Race-enabled Go evidence remains Linux/container-gated because this host has
no C compiler (`go test -race` exits with the documented CGO requirement).
Non-race `go test ./...` passed for gateway, ws-hub and file-processor; the
release gate still requires the pinned Linux race jobs.

## 95. Static-path normalization survivor closure (2026-09-15; pending push)

The stale diagnostic run `34923631288` later completed mutmut execution group
61 with one additional survivor (`10387415971`):
`app.core.static.x_is_private_static_path__mutmut_8` changed
`path.lstrip("/")` to `path.lstrip("XX/XX")`. That mutation strips arbitrary
leading `X` characters and can falsely classify a public path such as
`Xchat_uploads/...` as a private attachment prefix. It is a real
normalization contract defect, not a scheduler or timeout failure.

The current implementation remains deliberately strict and unchanged. Commit
`ab520d4df` adds a focused regression assertion that
`is_private_static_path("Xchat_uploads/chat_x/file.txt")` is false, while the
existing encoded, dot-segment, private-prefix and blocked-response assertions
remain intact. Focused evidence:

    uv run pytest -q -p no:cacheprovider tests/test_private_attachments.py
    # 6 passed
    uv run ruff check tests/test_private_attachments.py
    uv run ruff format --check tests/test_private_attachments.py
    git diff --check
    # all passed
    PRE_COMMIT_HOME=C:\\Temp\\pre-commit-cache-mvp \
      pre-commit run --files tests/test_private_attachments.py
    # all configured applicable hooks passed

The stale artifact is bound to pre-fix SHA `2774de52`; this test is not claimed
as current mutation evidence until a fresh SHA-bound mutmut universe executes
the complete inventory. User-owned WASM edits, temporary directories,
`docs/audits/AUDIT_PLATFORM_FULL.md` and the service capability marker remain
unstaged.

## 96. Stale-run capacity and security-evidence checkpoint (2026-09-15; pending push)

The latest authoritative job poll for run `34923631288` still reports the
run-level API state as `queued` with no conclusion, even though job records are
progressing. The run is bound to the stale source SHA
`2774de52d158cf0b7611b331586014a8420a1df2`, not the current checkout. At this
checkpoint the job inventory is 311 total: 226 completed, 22 failed, 12
skipped, 6 in progress and 79 queued. Every completed failure is a mutmut
survivor in groups 10, 11, 16, 19, 22, 23, 26, 29, 30, 31, 33, 34, 37, 38,
43, 44, 45, 46, 47, 48, 49 or 61; no non-mutation failure has appeared. The
inventory is therefore not yet terminal and cannot certify the current SHA.

The API-only diagnostic ledger
`C:\\Temp\\ci349236-critical-path-current.json` records a diagnostic-only
lower-bound report (SHA-256
`04c51e37b4d734f3ea691debd515b5cbcae14ebd6033cf06981939d560fbe7b1`):

- 311 jobs, observed peak concurrency 18/20 and a lower-bound wall clock of
  18,781 seconds;
- queue p50 259 seconds, p95 11,715 seconds, maximum 14,607 seconds;
- setup p50 40 seconds, p95 76 seconds; test p50 726 seconds, p95 1,823
  seconds, maximum 6,630 seconds; artifact handling p95 3 seconds;
- repeated checkout/install/setup work is visible across mutation and content
  shards, but this report does not prove the dependency DAG, archive bytes,
  runner RSS/CPU, billed minutes or a strict release artifact.

These measurements support retaining the current inventory and caps until
three comparable green runs provide the missing queue/runtime/RSS/CPU/billed
evidence. They do not justify increasing concurrency, changing timeouts or
adding retries now.

The Codex Security standard scan completed against snapshot SHA
`faef16c2a715d52e98fcc136e015f92e3247a140` (before the two latest
test/documentation commits) with zero reportable findings across the reviewed
authentication, gateway identity, private-attachment, CI provenance,
secrets/logging/WASM and live-infrastructure surfaces. Its coverage is
explicitly `partial`; live release/Kubernetes/observability/device evidence
and a fresh current-SHA mutation run remain deferred. The sealed report is
outside the repository at
`C:\\Temp\\codex-security-scans-UsDczy\\university_ecosystem\\faef16c2a715d52e98fcc136e015f92e3247a140_20260915T080600Z_ibo04b2k\\report.md` and is not a current-SHA release certificate.

Next safe actions remain: wait for the stale job records to become terminal,
append the final complete inventory, re-run local gates, push the current
branch non-force, obtain a fresh current-SHA PR matrix and security evidence,
then perform the external merge/release gates. User-owned WASM changes,
temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 108. Cache-payload and stale attachment survivor closure (2026-09-15; pending push)

Stale run `34923631288` completed mutmut execution group 78 in job
`104249729464`; artifact `10391971684` recorded two survivors. The real
cache-path survivor `app.services.image_proxy.x_get_transformed_image__mutmut_11`
replaced the cache-hit safety call
`_validate_image_payload(data, max_pixels=...)` with
`_validate_image_payload(None, max_pixels=...)`. That would skip validation of
the exact bytes decoded from Redis. The new regression test
`test_get_transformed_image_cache_hit_validates_decoded_payload` builds a
cache hit, patches the validator and asserts the exact decoded payload and
pixel budget while proving the storage backend is not read.

The same artifact's `app.services.private_attachments.x_private_attachment_storage_key__mutmut_10`
changed the historical explicit backslash guard to a sentinel-only check.
This is stale-source-equivalent rather than a current defect: the current
`_safe_filename` anchored allow-list rejects every path separator before the
storage-key builder, and the current builder correctly relies on that single
validation gate. No redundant guard or mutation exclusion is introduced.

The preceding group 77 artifact `10391592423` (job `104249729301`) changed
`format="WEBP"` to lowercase `format="webp"`; the g74 exact WebP kwargs test
already rejects that sibling mutation, so it requires no additional source.

The cache contract was first demonstrated RED against the g78 equivalent
(`_validate_image_payload(None, max_pixels=1234)` produced an assertion
mismatch), then GREEN on the current source:

    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py::test_get_transformed_image_cache_hit_validates_decoded_payload
    # 1 passed
    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py tests/test_image_proxy.py
    # 44 passed
    uv run pytest -q -p no:cacheprovider tests/test_private_attachments.py
    # 6 passed
    uv run ruff check tests/test_image_proxy_closure.py app/services/image_proxy.py
    uv run ruff format --check tests/test_image_proxy_closure.py app/services/image_proxy.py
    git diff --check
    # all passed

No production behavior, mutation inventory or threshold was weakened. Both
stale artifacts are bound to source SHA
`2774de52d158cf0b7611b331586014a8420a1df2`; fresh current-SHA mutation
evidence remains mandatory before certification. User-owned WASM edits,
temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 107. WebP encoder-method survivor closure (2026-09-15; pending push)

Stale run `34923631288` completed mutmut execution group 75 in job
`104249729208`; evidence artifact `10392190685` recorded the survivor
`app.services.image_proxy.x__process_image__mutmut_57`. Its generated source
removed the explicit WebP encoder method while retaining the quality keyword:

    original: img.save(buffer, format="WEBP", quality=80, method=6)
    mutant:   img.save(buffer, format="WEBP", quality=80, )

This changes the Pillow encoder behavior because the default method is not the
application's explicit method-6 contract. The g74 regression test
`test_process_image_webp_uses_quality_and_method_contract` already asserts the
complete exact kwargs set, so it kills this sibling mutant as well; the test's
required `method` argument also deterministically rejects the generated call.
No additional production or test code is needed, and no mutation threshold or
inventory was weakened.

    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py::test_process_image_webp_uses_quality_and_method_contract
    # 1 passed
    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py tests/test_image_proxy.py
    # 43 passed
    uv run ruff check tests/test_image_proxy_closure.py app/services/image_proxy.py
    uv run ruff format --check tests/test_image_proxy_closure.py app/services/image_proxy.py
    git diff --check
    # all passed

The RED contract check against the mutated kwargs observed
`{'format': 'WEBP', 'quality': 80}` and failed against the expected method-6
contract. The stale artifact is bound to source SHA
`2774de52d158cf0b7611b331586014a8420a1df2`; fresh current-SHA mutation
evidence remains mandatory before certification. User-owned WASM edits,
temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 106. Benchmark Go cache-key correctness (2026-09-15; pending push)

The benchmark workflow previously enabled `actions/setup-go` caching without a
`cache-dependency-path`. In this multi-module repository that falls back to the
empty root `go.mod`, so changes in service module lockfiles could reuse a stale
cache or miss a reusable cache entry. The reusable Go workflow already defines
the authoritative module inventory; `benchmark.yml` now binds the same
workspace modules (`services/*`, `gen/go/go.sum` and the root `go.sum`, with
`services/pkg/logging/go.mod` and `services/pkg/spicedb/go.mod` because those
modules have no `go.sum`).

`tests/test_quality_workflow_contract.py::test_benchmark_go_cache_covers_every_workspace_dependency_file`
asserts the exact ordered path contract, preventing silent omission when a Go
module is added. This is a cache-correctness change only: it does not alter
test/source/mutant inventory, concurrency, timeout, retry or release-gate
semantics, and the three-green-run requirement for capacity experiments remains
in force.

    uv run pytest -q -p no:cacheprovider tests/test_quality_workflow_contract.py
    # 177 passed in 84.70s
    uv run ruff check tests/test_quality_workflow_contract.py
    uv run ruff format --check tests/test_quality_workflow_contract.py
    git diff --check
    # all passed (actionlint is authoritative in the hosted hook environment)

The implementation and contract test were introduced in
`96e8e806b4b73c39ff510ea21213d6296ca491b9`; the RED→GREEN follow-up
`d42eecb17` corrects the no-lockfile `spicedb` entry to its real `go.mod`.
Fresh hosted validation remains required after pushing the current branch.
User-owned WASM edits, temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md`
and `services/file-processor/coverage_capability` remain unstaged.

## 105. WebP quality-parameter survivor closure (2026-09-15; pending push)

Stale run `34923631288` completed mutmut execution group 74 in job
`104249729115`; evidence artifact `10390627618` recorded the survivor
`app.services.image_proxy.x__process_image__mutmut_56`. The generated mutant
removed the explicit `quality=80` keyword from the WebP encoder call:

    original: img.save(buffer, format="WEBP", quality=80, method=6)
    mutant:   img.save(buffer, format="WEBP", method=6)

This is observable product behavior because Pillow's default WebP quality is
not the application's configured quality contract. The regression test
`test_process_image_webp_uses_quality_and_method_contract` asserts the exact
format, quality and method passed to `Image.save`, while also checking the
returned bytes and MIME type. The test was first demonstrated RED against the
mutated call (the observed kwargs omitted `quality`), then GREEN on the
current production implementation without a source change.

    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py::test_process_image_webp_uses_quality_and_method_contract
    # 1 passed
    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py tests/test_image_proxy.py
    # 43 passed
    uv run ruff check tests/test_image_proxy_closure.py app/services/image_proxy.py
    uv run ruff format --check tests/test_image_proxy_closure.py app/services/image_proxy.py
    git diff --check
    # all passed

No production behavior, mutation inventory or threshold was weakened. The
stale artifact is bound to source SHA `2774de52d158cf0b7611b331586014a8420a1df2`;
fresh current-SHA mutation evidence remains mandatory before certification.
The focused test is intentionally exact so it also rejects equivalent removal
of either WebP encoder parameter in a regenerated universe. User-owned WASM
edits, temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 104. External-audit triage against current ancestry (2026-09-15; evidence pending)

The independent review of the untracked external audit
`docs/audits/AUDIT_PLATFORM_FULL.md` against the current plan and quality
contract found no new safe P0/P1 code patch. The audit's P0 findings SEC-01
(GraphQL gateway identity trust) and INFRA-01 (revocation Redis wiring) are
already CODE-FIXED in current ancestry and remain FRESH-EVIDENCE-PENDING:
`app/graphql/schema.py` verifies the gateway `X-Internal-Signature` before
trusting identity, while the Kubernetes ExternalSecret/backend wiring supplies
`REVOCATION_REDIS_URL`. The audited P1 items BE-01/03/05, FE-01, GO-01/02/03,
RUST-P1-01/02, INFRA-04/05/06 and SEC-02/03/04 have the same
CODE-FIXED/FRESH-EVIDENCE-PENDING disposition in the plan.

INFRA-03 is implemented by `scripts/apply_raw_k8s.sh` (registry/tag
validation, unresolved-variable and `latest` rejection) but still needs fresh
Helm/Kyverno render evidence. INFRA-02 is an intentional
DECISION-RECORDED architecture choice: ADR-034 and `k8s/README.md` make Helm
the sole canonical producer, so raw-manifest omission of Go services is not a
new defect.

The only unresolved architecture dispositions in the P0/P1 set are BE-02
(ADR-036 measured defaults inventory requiring PostgreSQL catalog preflight and
phased migration design) and BE-04 (Dishka/legacy `Depends` coexistence,
requiring a separate ADR and phased migration). They are not safe opportunistic
patches for this closure run. Remaining SEC-07/SEC-08/GO-07 items and all
current-SHA Linux race/fuzz, coverage/mutation, Helm/Kyverno, staging, image,
observability and rollback checks are evidence/tooling or external-only gates.

The external audit is preserved untracked as user-owned input. This triage
does not promote the stale run `34923631288` or the partial security scans to
release evidence; current-SHA hosted artifacts remain mandatory. User-owned
WASM edits, temporary directories and `services/file-processor/coverage_capability`
remain unstaged.

## 103. pyvips option-string survivor closure (2026-09-15; pending push)

Stale run `34923631288` completed mutmut execution group 69 with survivor
`10389583209` (job `104249728523`):
`app.utils.images_vips.x_optimize_image_vips__mutmut_14` changed the options
string in `pyvips.Image.new_from_buffer(data, "")` to `"XXXX"`. Non-empty
options would alter decoder behavior and could bypass or change dimension
metadata inspection. The exact call assertion introduced for groups 65 and 67
(`new_from_buffer.assert_called_once_with(b"raw", "")`) kills this mutation
without changing production code or reducing the inventory.

    uv run pytest -q -p no:cacheprovider tests/test_images_vips_full.py
    # 19 passed
    uv run ruff check tests/test_images_vips_full.py
    uv run ruff format --check tests/test_images_vips_full.py
    git diff --check
    # all passed

The stale artifact is bound to `2774de52`; fresh current-SHA mutation evidence
remains mandatory. At the latest poll 27 completed failures were recorded,
all mutmut survivors, with the rest of the mutation matrix still queued or
running and no non-mutmut failure. User-owned WASM edits, temporary
directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 102. pyvips dropped-payload survivor closure (2026-09-15; pending push)

Stale run `34923631288` completed mutmut execution group 67 with survivor
`10389139421` (job `104249728351`):
`app.utils.images_vips.x_optimize_image_vips__mutmut_12` dropped the `data`
argument from `pyvips.Image.new_from_buffer`. This is the sibling form of the
group-65 payload substitution and would make validation inspect an empty or
different image instead of the caller's bytes.

The exact assertion introduced for group 65,
`new_from_buffer.assert_called_once_with(b"raw", "")`, rejects both the
`None` substitution and the dropped-argument mutation. Focused evidence
remains:

    uv run pytest -q -p no:cacheprovider tests/test_images_vips_full.py
    # 19 passed
    uv run ruff check tests/test_images_vips_full.py
    uv run ruff format --check tests/test_images_vips_full.py
    git diff --check
    # all passed

No production behavior, mutation inventory or threshold was weakened. The
stale artifact is bound to `2774de52`; current-SHA mutation certification is
still pending. At the latest poll 26 completed failures were recorded (all
mutmut), with frontend/mutmut jobs still queued or running and no non-mutmut
failure. User-owned WASM edits, temporary directories,
`docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.


## 101. Local contract recertification after g65/g64 closures (2026-09-15; pending push)

After the image-limit and pyvips focused tests, the local quality-contract and
CI-governance lanes were re-run against the current worktree. Results:

    uv run pytest -q -p no:cacheprovider \
      tests/test_ci_critical_path_analysis.py \
      tests/test_ci_health_report.py \
      tests/test_quality_workflow_contract.py
    # 236 passed in 82.90s

    uv run python scripts/quality/validate_ci_check_catalog.py
    # CI check catalog: OK (55 workflows, 182 jobs)

The earlier repository harness remains 29/29, and the focused image suites
remain 28/28 (`tests/test_images_v2.py`) and 19/19
(`tests/test_images_vips_full.py`). These are local current-checkout results,
not substitutes for fresh hosted mutation, coverage, race or release evidence.
The stale run `34923631288` remains non-terminal and is still bound to
`2774de52`; its completed failures are mutation-only. User-owned WASM edits,
temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 100. pyvips input-forwarding survivor closure (2026-09-15; pending push)

Stale run `34923631288` completed mutmut execution group 65 with survivor
`10388339017`: `app.utils.images_vips.x_optimize_image_vips__mutmut_10`
replaced the payload passed to `pyvips.Image.new_from_buffer` with `None` in
the `max_pixels` validation path. This is a real trust-boundary defect: image
dimension validation must inspect the exact bytes supplied by the caller and
must not silently validate a different payload.

`tests/test_images_vips_full.py` now configures an 800x600 mock image, invokes
`optimize_image_vips(b"raw", max_pixels=500_000)` and asserts the exact
`new_from_buffer(b"raw", "")` call. Focused evidence:

    uv run pytest -q -p no:cacheprovider tests/test_images_vips_full.py
    # 19 passed
    uv run ruff check tests/test_images_vips_full.py
    uv run ruff format --check tests/test_images_vips_full.py
    git diff --check
    # all passed

No source behavior, mutation inventory or threshold was weakened. The stale
artifact is bound to `2774de52`; a fresh current-SHA mutation run remains
mandatory. At the latest poll the run had 25 completed failures (all mutmut),
6 in-progress jobs and 72 queued jobs; no non-mutmut failure was observed.
User-owned WASM edits, temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md`
and `services/file-processor/coverage_capability` remain unstaged.

## 99. Image pixel-budget state survivor closure (2026-09-15; pending push)

The stale run `34923631288` then completed mutmut execution group 64 with
survivor `10388471574`:
`app.utils.images.xǁImagePixelLimitErrorǁ__init____mutmut_3` replaced
`self.max_pixels = max_pixels` with `self.max_pixels = None`. The constructor's
width, height and budget attributes form one structured error contract; the
focused assertions added for group 62 already assert the complete tuple for
both dimension and decoder errors and therefore kill this mutant as well.

    uv run pytest -q -p no:cacheprovider tests/test_images_v2.py
    # 28 passed

No production change, exclusion, quarantine or threshold adjustment is needed
for group 64. The stale artifact remains bound to `2774de52`; a fresh
current-SHA mutation universe is still required for certification. At the
latest poll the stale run had 23 completed failures, 4 in-progress jobs and 77
queued jobs, all observed failures being mutmut survivors. User-owned WASM
edits, temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 98. Current-head supplemental security scan (2026-09-15; pending push)

A new Codex Security standard scan was run against the exact current committed
checkout `bbe28d86de25bd327ff54836f9bd3ce1cf3c3918` (scan
`51f66f40-6198-46cd-8649-571eebd51d78`). The configuration preflight was
`ready`; the scan reviewed six declared surfaces and completed with zero
reportable findings. Local source review covered authentication/CSRF and
JWT/JWKS, gateway identity assertions, private attachments/image processing,
CI workflow and artifact provenance, secrets/logging/Rust/WASM, and static
infrastructure/release controls.

The scan is deliberately marked `partial`, not complete release assurance:
fresh current-SHA hosted mutation/coverage artifacts, Linux race/fuzz jobs,
registry attestations, live Kubernetes/TLS/ExternalSecrets/observability,
real browser/device performance and rollback evidence remain deferred. The
sealed artifacts are outside the repository under
`C:\\Temp\\codex-security-scans-UsDczy\\university_ecosystem\\bbe28d86de25bd327ff54836f9bd3ce1cf3c3918_20260915T083923Z_qbrf62hi\\` (`report.md`, `findings.json`, `coverage.json`, `scan-manifest.json` and `exports\\results.sarif`). The tool reported a non-blocking `token_record_invalid` usage warning; it did not alter findings or repository state.

This evidence is supplemental pre-push assurance. After the stale run is
terminal and the branch is pushed, a new scan and current-SHA CI artifacts are
still mandatory before any release claim. User-owned WASM edits, temporary
directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 97. Image pixel-limit attribute survivor closure (2026-09-15; pending push)

The still-running stale run `34923631288` completed mutmut execution group 62
with one real survivor (`10387787759`):
`app.utils.images.xǁImagePixelLimitErrorǁ__init____mutmut_1` replaced
`self.width = width` with `self.width = None`. The public exception contract
includes structured dimensions and the configured budget, not only its human
readable message; losing those attributes would break callers that need to
render or audit the rejected dimensions.

The existing message regression was extended with exact assertions for both a
dimension error and a decoder error (`width`, `height` and `max_pixels`). No
production behavior or mutation inventory was weakened. Focused evidence:

    uv run pytest -q -p no:cacheprovider tests/test_images_v2.py
    # 28 passed
    uv run ruff check tests/test_images_v2.py
    uv run ruff format --check tests/test_images_v2.py
    git diff --check
    # all passed

The artifact and mutant are bound to stale source SHA `2774de52`; current-SHA
mutation certification remains pending a fresh complete universe. The stale
run now has 23 completed failures (all mutmut), 5 in-progress jobs and 79
queued jobs; no non-mutmut failure has been observed. User-owned WASM edits,
temporary directories, `docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 109. Current-head fast-preflight recertification (2026-09-15; pending push)

The exact current checkout at `7d0bdb18dbf34a2dddab5bb6ce693849aee1a0ab`
passed the local parallel fast-preflight with all six checks green and no
timeout or retry:

    uv run python scripts/fast_preflight.py \
      --max-workers 6 --timeout-seconds 600 --include-output
    # 6/6 passed; report: artifacts/fast-preflight/fast-preflight.json
    # total wall time 98.291 s; slowest lane frontend-lint 98.258 s

The lanes were frontend typecheck/lint, backend mypy/Ruff, the repository
harness and focused CI-contract tests. The report is commit-bound, contains
the command/exit-code/duration/stdout provenance for every lane, and is an
advisory developer acceleration aid; it does not replace the required Linux
CI, mutation, coverage, security or release evidence. The run-level stale PR
workflow `34923631288` is still non-terminal and bound to old SHA
`2774de52d158cf0b7611b331586014a8420a1df2`; its job inventory remains the
authoritative diagnostic source while the API incorrectly reports `queued`.

No quality threshold, test/source/mutant inventory, timeout or retry policy
was changed. User-owned WASM edits, temporary directories,
`docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 110. Static security-header survivor recertification (2026-09-15; pending push)

Stale PR run `34923631288` completed mutmut group 81 in job `104249729693`;
artifact `10391234933` selected nine mutants and reported one survivor:
`app.core.static.PublicStaticFiles.get_response__mutmut_12`. The generated
stale source changed the private-path response header name from
`X-Content-Type-Options` to `XXX-Content-Type-OptionsXX`, which would remove
the required `nosniff` header from the response contract.

This is stale-source evidence, not a current defect. The exact current
regression assertion
`response.headers["x-content-type-options"] == "nosniff"` was added in
commit `8bafb3ce5` after the stale universe SHA
`2774de52d158cf0b7611b331586014a8420a1df2`; Starlette's case-insensitive
headers preserve the lookup while the mutated name is absent, so the mutant
now fails deterministically. The focused static/private-attachment suite
also covers status and `Cache-Control` safety values. No product source,
mutation inventory or threshold was changed, and no suppression or
exclusion is appropriate. A fresh current-SHA mutmut universe remains
mandatory before certification.

## 111. CDC replication teardown exception-contract survivor closure (2026-09-15; pending push)

Stale PR run `34923631288` completed mutmut execution group 83 in job
`104249730010`; artifact `10392471238` (`mutmut-exact-evidence-34923631288-1-group-83`)
selected five mutants from a 54,141-mutant universe. Four were killed and the
one survivor was
`app.workers.cdc_outbox.xǁCdcOutboxWorkerǁ_close_replication_connection__mutmut_9`.
The artifact's selected result records `exit_code: 0` and `status: survived`,
with selection manifest SHA-256
`49e8578ecfef1894af80cc8916f74577245851843bf34e082a72aa098222c0bb` and
universe SHA-256
`2af0d764ca6e63eeafbec21028013ef7485211e2121145ead74e8013966324a2`.

The stale generated source at lines 54547-54549 changed
`contextlib.suppress(OSError, ConnectionError, asyncpg.PostgresError,
asyncpg.InterfaceError)` to omit the explicit `ConnectionError`. This is a
real contract-observability gap, although runtime behavior is equivalent for
this pair because Python's `ConnectionError` subclasses `OSError`. The
implementation now keeps the complete immutable exception tuple at module
level:

    _REPLICATION_CLOSE_ERRORS = (
        OSError,
        ConnectionError,
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
    )

and calls `contextlib.suppress(*_REPLICATION_CLOSE_ERRORS)`. The focused AST
contract asserts that the worker method expands this module-level tuple, while
the existing parameterized runtime contract continues to exercise all four
supported teardown error classes. Keeping the explicit `ConnectionError`
member outside the mutated method makes the documented lifecycle contract
structural rather than dependent on a runtime-equivalent superclass.

TDD evidence on the current checkout:

    # RED before the production change:
    uv run pytest -q -p no:cacheprovider tests/test_cdc_outbox_closure.py \
      -k "replication_close_error_contract or close_replication_connection_uses"
    # 2 failed: module-level tuple absent and suppress() did not expand it

    # GREEN after the production change:
    uv run pytest -q -p no:cacheprovider \
      tests/test_cdc_outbox_closure.py tests/test_cdc_outbox.py
    # 52 passed in 18.61s
    uv run ruff check app/workers/cdc_outbox.py \
      tests/test_cdc_outbox_closure.py tests/test_cdc_outbox.py
    # All checks passed!
    uv run ruff format --check app/workers/cdc_outbox.py \
      tests/test_cdc_outbox_closure.py tests/test_cdc_outbox.py
    # 3 files already formatted
    uv run python -m mypy --config-file pyproject.toml \
      app/workers/cdc_outbox.py
    # Success: no issues found in 1 source file
    git diff --check
    # passed

No mutation threshold, exclusion, quarantine or timeout policy was changed.
The stale run remains bound to source SHA
`2774de52d158cf0b7611b331586014a8420a1df2`; fresh current-SHA mutation
evidence remains mandatory. User-owned WASM edits, temporary directories,
`docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 112. AVIF quality contract survivor closure (2026-09-15; pending push)

Stale PR run `34923631288` completed mutmut execution group 88 in job
`104249730312`; artifact `10392293513`
(`mutmut-exact-evidence-34923631288-1-group-88`) selected five mutants from a
54,141-mutant universe. Four were killed and the survivor was
`app.services.image_proxy.x__process_image__mutmut_34`. The artifact records
`status: survived`, `exit_code: 0`, selection SHA-256
`ec1019c438256c0a980c6d85b0ea393a71aee5084ba3724aef4c2b725f0ecb49`, selected
results SHA-256 `1cc8c77ba5610fb49ccb4638550538be77b3350ff87c80525b685a3cd24d74a9`,
and universe SHA-256
`2af0d764ca6e63eeafbec21028013ef7485211e2121145ead74e8013966324a2`.

The stale generated source removed the explicit `quality=60` argument from
the AVIF encoder call. This is a real output-contract mutation: it changes
the configured AVIF quality rather than only changing syntax. The focused
success-path test now requires the encoder callback to receive exactly
`format="AVIF"` and `quality=60`, and asserts the complete keyword argument
mapping. No production change was necessary because the current source
already passed `quality=60`; the gap was only the missing assertion.

TDD evidence on the current checkout:

    # RED against a temporary mutant with quality=60 removed:
    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py::test_process_image_returns_avif_when_encoding_succeeds \
      --disable-warnings --maxfail=1
    # 1 failed: callback rejected the missing required quality argument

    # GREEN after restoring the production contract:
    uv run pytest -q -p no:cacheprovider \
      tests/test_image_proxy_closure.py tests/test_images_v2.py \
      --disable-warnings --maxfail=1
    # 37 passed in 11.71s
    uv run ruff check app/services/image_proxy.py tests/test_image_proxy_closure.py
    # All checks passed!
    uv run ruff format --check app/services/image_proxy.py \
      tests/test_image_proxy_closure.py
    # 2 files already formatted
    uv run python -m mypy --config-file pyproject.toml \
      app/services/image_proxy.py
    # Success: no issues found in 1 source file
    git diff --check
    # passed

No threshold, exclusion, quarantine, timeout or inventory policy was
changed. The stale run remains bound to source SHA
`2774de52d158cf0b7611b331586014a8420a1df2`; fresh current-SHA mutation
evidence remains mandatory. User-owned WASM edits, temporary directories,
`docs/audits/AUDIT_PLATFORM_FULL.md` and
`services/file-processor/coverage_capability` remain unstaged.

## 113. Weekly cleanup privileged-source boundary (2026-09-15; pending push)

The independent current-SHA security review reported `CI-SEC-001` (HIGH,
CWE-94/CWE-522) in `.github/workflows/weekly-cleanup.yml`: a manually
dispatchable job injected `DATABASE_URL` and `SECRET_KEY`, checked out the
default ref with persisted credentials, and then installed and executed
repository-controlled Python code. A caller able to dispatch a workflow could
therefore select a malicious ref and execute it with application secrets.

The remediation is fail-closed and keeps the cleanup operation available only
from protected `main`:

* the cleanup job is guarded by
  `github.ref == 'refs/heads/main'`;
* checkout explicitly uses `ref: main`, `fetch-depth: 0`, and
  `persist-credentials: false`;
* before dependency setup, a bash guard fetches `origin/main`, requires a
  full 40-character commit SHA, and requires the checked-out `HEAD`, event
  `github.sha`, and workflow `github.workflow_sha` to equal that exact
  protected-main SHA;
* the contract suite now asserts the job guard, immutable checkout settings,
  and every source-integrity check.

TDD and static evidence on the current checkout:

    # RED before the workflow guard existed:
    uv run pytest -q -p no:cacheprovider \
      tests/test_workflow_fail_closed_contracts.py::test_privileged_manual_workflows_are_main_bound_and_immutable \
      --disable-warnings --maxfail=1
    # 1 failed: weekly-cleanup job had no `if` guard

    # GREEN after the fail-closed workflow change:
    uv run pytest -q -p no:cacheprovider \
      tests/test_workflow_fail_closed_contracts.py::test_privileged_manual_workflows_are_main_bound_and_immutable \
      --disable-warnings --maxfail=1
    # 1 passed in 1.34s
    PRE_COMMIT_HOME=C:\\Temp\\precommit-g88-20260915 \
      pre-commit run actionlint --files .github/workflows/weekly-cleanup.yml --verbose
    # Passed
    PRE_COMMIT_HOME=C:\\Temp\\precommit-g88-20260915 \
      pre-commit run semgrep-docker --files .github/workflows/weekly-cleanup.yml --verbose
    # Passed; 0 findings
    git diff --check
    # passed

The finding is considered fixed in the working tree but remains unsealed in
the security-scan workbench until the remediation commit and current-SHA
verification are complete. No permissions, coverage floor, mutation threshold,
exclusion, quarantine, or timeout was weakened. The separate user-owned WASM
artifacts, temporary directories, external audit, and coverage capability
marker remain unstaged.

## 114. Gateway JWT algorithm downgrade and Temporal auth closure (2026-09-15; pending push)

The independent security baseline identified two medium-risk authentication
gaps at the audited source SHA 6d2056272f777ad72e5ef96707bf1149da5d20ae:

* SEC-01 (CWE-347/CWE-327): JWTMiddleware.rsaConfigured() was false until
  the first successful asynchronous JWKS refresh. During a transient startup
  or JWKS outage that allowed HS256 to remain in the parser's accepted-method
  set, creating a conditional algorithm downgrade if the verifier's HMAC
  secret were compromised.
* SEC-02 (CWE-306/CWE-284): the shared Temporal Compose entrypoint passed
  --allow-no-auth. Because the same entrypoint is mounted by both base and
  full production-like Compose stacks, that flag disabled the configured JWT
  authorizer for in-network callers.

Both fixes preserve the intended trust boundary and are covered by focused
regressions:

* JWTMiddleware now records jwksConfigured synchronously before starting
  the refresh goroutine. rsaConfigured() treats configured JWKS mode as
  RS256-only even when the key cache is empty, so HS256 is rejected until a
  valid RSA key set is loaded. The regression serves a temporary 503 JWKS
  endpoint and verifies the HS256 token is rejected before the first successful
  fetch.
* services/temporal/entrypoint.sh no longer passes --allow-no-auth (and
  does not support an environment escape hatch). The Docker contract verifies
  the JWT claim mapper remains configured and both Compose stacks mount the
  hardened entrypoint without a no-auth override.

TDD and verification evidence:

    # SEC-01 RED before the atomic mode marker:
    # the pre-refresh HS256 token was accepted (nil error)
    # GREEN after the marker and regression test:
    gofmt -w middleware/auth.go middleware/auth_extra_test.go
    go test ./... -count=1
    # all gateway packages passed; middleware included the new regression

    # SEC-02 RED before removing the flag:
    uv run pytest -q -p no:cacheprovider \
      tests/test_docker_startup_contracts.py::test_production_temporal_entrypoint_never_enables_no_auth \
      --disable-warnings --maxfail=1
    # failed because --allow-no-auth was present
    # GREEN:
    uv run pytest -q -p no:cacheprovider \
      tests/test_docker_startup_contracts.py::test_production_temporal_entrypoint_never_enables_no_auth \
      --disable-warnings --maxfail=1
    # 1 passed

    uv run pytest -q -p no:cacheprovider \
      tests/test_docker_startup_contracts.py::test_production_temporal_entrypoint_never_enables_no_auth \
      tests/test_workflow_fail_closed_contracts.py::test_privileged_manual_workflows_are_main_bound_and_immutable \
      tests/test_image_proxy_closure.py tests/test_images_v2.py \
      --disable-warnings --maxfail=1
    # 39 passed in 11.78s
    uv run ruff check tests/test_docker_startup_contracts.py \
      tests/test_workflow_fail_closed_contracts.py tests/test_image_proxy_closure.py
    # All checks passed
    uv run ruff format --check tests/test_docker_startup_contracts.py \
      tests/test_workflow_fail_closed_contracts.py tests/test_image_proxy_closure.py
    # 3 files already formatted
    docker compose -f docker-compose.yml config --quiet
    docker compose -f docker-compose.full.yml config --quiet
    # both passed
    PRE_COMMIT_HOME=C:\Temp\precommit-g88-20260915 \
      pre-commit run actionlint --files .github/workflows/weekly-cleanup.yml --verbose
    # Passed
    PRE_COMMIT_HOME=C:\Temp\precommit-g88-20260915 \
      pre-commit run semgrep-docker --files .github/workflows/weekly-cleanup.yml --verbose
    # Passed; 0 findings
    git diff --check
    # passed

No accepted algorithm was broadened, no authentication gate was bypassed, and
no coverage/mutation threshold, exclusion, quarantine, or timeout policy was
changed. Linux go test -race remains the authoritative concurrency gate and
must be re-run in fresh hosted CI. The remaining SEC-03/SEC-04 items are
configuration hardening candidates and remain explicitly tracked until their
production-mode behavior is validated; they are not silently marked fixed.

## 115. Internal-route token boundary (2026-09-15; pending push)

The security baseline's SEC-04 (LOW, CWE-306) identified a legacy
IP-only fallback in InternalAccessMiddleware: an allowlisted source address
could invoke protected internal routes without X-Internal-Token, while
production configuration only warned when the token was missing. This was a
real trust-boundary weakness for loopback SSRF, local processes, or an
exposed allowlisted address.

The compatibility path is now explicit and fail-closed:

* InternalAccessMiddleware accepts allow_ip_fallback=False by default;
  source-IP authentication is therefore disabled unless a caller opts into
  the compatibility behavior.
* application wiring enables the flag only when settings.is_development is
  True; staging, production, and unknown/bare settings use token-only
  authentication.
* CorsSettingsMixin now raises a validation error when INTERNAL_AUTH_TOKEN is
  absent outside the documented development environments instead of logging a
  warning and leaving the IP fallback available.
* existing development compatibility tests pass the explicit flag, and new
  regressions prove an allowlisted IP is denied when the flag is false.

TDD and verification evidence:

    # RED before the boundary change:
    uv run pytest -q -p no:cacheprovider \
      tests/test_cors_settings_closure.py::TestCorsSettingsClosure::test_internal_auth_token_is_required_for_non_development \
      tests/test_internal_access_closure.py::test_allowed_ip_is_rejected_when_ip_fallback_is_disabled \
      --disable-warnings --maxfail=1
    # failed because production missing-token configuration only warned and
    # the middleware accepted an allowlisted IP without an explicit mode

    # GREEN:
    uv run pytest -q -p no:cacheprovider \
      tests/test_cors_settings_closure.py \
      tests/test_internal_access_closure.py \
      tests/test_middleware_setup_contract_closure.py \
      tests/test_middleware_coverage.py tests/test_core_infra.py \
      --disable-warnings --maxfail=1
    # 124 passed in 33.21s
    uv run ruff check app/core/config/mixins/cors_settings.py \
      app/core/internal_access.py app/core/middleware/setup.py \
      tests/test_core_infra.py tests/test_cors_settings_closure.py \
      tests/test_internal_access_closure.py tests/test_middleware_coverage.py \
      tests/test_middleware_setup_contract_closure.py
    # All checks passed
    uv run ruff format --check app/core/config/mixins/cors_settings.py \
      app/core/internal_access.py app/core/middleware/setup.py \
      tests/test_core_infra.py tests/test_cors_settings_closure.py \
      tests/test_internal_access_closure.py tests/test_middleware_coverage.py \
      tests/test_middleware_setup_contract_closure.py
    # 8 files already formatted
    uv run python -m mypy --config-file pyproject.toml \
      app/core/config/mixins/cors_settings.py app/core/internal_access.py \
      app/core/middleware/setup.py
    # Success: no issues found in 3 source files
    git diff --check
    # passed

No route was made more permissive, and no gate, exclusion, quarantine,
suppression, or timeout policy was changed. The working-tree patch is pending
review and commit; current-SHA CI and release-mode integration evidence remain
mandatory.

## 116. Release JWKS transport and ingress policy closure (2026-09-15; pending push)

The security review also identified a release-configuration gap in SEC-03:
the gateway's default JWKS URL was an in-cluster plaintext HTTP endpoint even
when the chart was rendered for staging or production. The release path now
uses the required HTTPS `global.jwtIssuer`, appending
`/.well-known/jwks.json`. The API ingress adds a more-specific discovery route
directly to the backend, so the gateway can fetch the public key through the
TLS origin without recursing through itself. Development keeps the explicit,
self-contained in-cluster HTTP endpoint for local operation.

The NetworkPolicy contract is aligned with that route: release gateways may
egress TCP/443, and the backend accepts TCP/8000 from the configured ingress
controller selector in addition to the gateway. The selector remains
parameterized for nginx, Traefik, AWS ALB, or Istio. TLS termination at the
ingress boundary and the backend ClusterIP transport are intentionally not
represented as pod-to-pod TLS; that separate infrastructure hardening concern
must remain visible in staging acceptance evidence.

TDD and chart evidence:

    # RED before release transport and route hardening:
    # focused contract observed the in-cluster http:// JWKS endpoint instead of
    # the required https:// API origin (and later lacked the ingress-controller
    # backend policy rule).

    # GREEN:
    uv run pytest -q -p no:cacheprovider \
      tests/test_helm_staging_contract.py::test_release_gateway_uses_tls_for_jwks_and_routes_discovery_to_backend \
      --disable-warnings --maxfail=1
    # 1 passed (the focused run was 1.81–2.12s across the two incremental
    # contract assertions)

    uv run pytest -q -p no:cacheprovider tests/test_helm_staging_contract.py \
      --disable-warnings --maxfail=1
    # 217 passed in about 121–126s

    helm lint charts/university-ecosystem \
      --values charts/university-ecosystem/values.yaml
    # 1 chart(s) linted, 0 chart(s) failed

    uv run ruff check app/core/config/mixins/cors_settings.py \
      app/core/internal_access.py app/core/middleware/setup.py \
      tests/test_core_infra.py tests/test_cors_settings_closure.py \
      tests/test_helm_staging_contract.py tests/test_internal_access_closure.py \
      tests/test_middleware_coverage.py tests/test_middleware_setup_contract_closure.py
    # All checks passed

    uv run python -m mypy --config-file pyproject.toml \
      app/core/config/mixins/cors_settings.py app/core/internal_access.py \
      app/core/middleware/setup.py
    # Success: no issues found in 3 source files

    git diff --check
    # passed

No release path was widened to plaintext, and no coverage/mutation threshold,
exclusion, quarantine, suppression, retry, or timeout policy was weakened.
The patch is pending its remediation commit and a fresh current-SHA security
scan, hosted CI, and actual staging/TLS validation.

## 117. CI check-catalog guard synchronization (2026-09-15; pending push)

The workflow audit found one deterministic catalog drift: the privileged
`weekly-cleanup` job now has an explicit main-branch guard, while its catalog
entry still declared the old placeholder `workflow trigger` guard. Because the
catalog validator compares every job guard against the parsed workflow source,
that stale value blocked the quality gate before any product tests ran.

The catalog entry now records the exact source expression
`${{ github.ref == 'refs/heads/main' }}`. No job trigger, permissions, timeout,
retry, matrix cap, or required/advisory policy was changed.

Verification:

    uv run python scripts/quality/validate_ci_check_catalog.py
    # CI check catalog: OK (55 workflows, 182 jobs)

The change is intentionally limited to the machine-readable catalog and is
pending inclusion in the next remediation commit and current-SHA CI run.

## 118. Production security fixture alignment (2026-09-15; pending push)

The first post-SEC-04 mutation audit reproduced a test-only failure in
`tests/test_internal_hmac_secret_security.py`: its production `SecuritySettings`
helper supplied the HMAC material but omitted the now-mandatory
`INTERNAL_AUTH_TOKEN`. The application fail-closed behavior was correct; the
fixture was incomplete and caused valid HMAC assertions to stop before reaching
their intended contract.

The helper now supplies an explicitly allowlisted, non-production test token.
No runtime validation was relaxed and no secret value is emitted by the
application.

Evidence:

    # RED:
    uv run pytest -q -p no:cacheprovider \
      tests/test_internal_hmac_secret_security.py --disable-warnings --maxfail=1
    # 1 failed, 5 passed: missing INTERNAL_AUTH_TOKEN in production helper

    # GREEN:
    uv run pytest -q -p no:cacheprovider \
      tests/test_internal_hmac_secret_security.py --disable-warnings --maxfail=1
    # 9 passed (1 warning from the existing test environment)

    uv run ruff check tests/test_internal_hmac_secret_security.py
    uv run ruff format --check tests/test_internal_hmac_secret_security.py
    git diff --check
    # all passed

The correction is pending its test-only commit and fresh current-SHA mutation
evidence; the historical remote run remains non-authoritative.

## 119. Current source identity and post-remediation evidence boundary (2026-09-15)

This checkpoint supersedes the identity statements in earlier historical
sections without rewriting their causal record. It is deliberately recorded
after the security, chart-policy, CI-catalog, and production-fixture commits,
but before pushing them and before a new hosted matrix is created.

### 119.1 Immutable local identity

| Field | Observed value | Interpretation |
|---|---|---|
| Active branch | `egorribun` | requested implementation branch; no merge or force-push performed |
| Local source `HEAD` | `a7121e969a102a9898d5a017029a2c75c23415d8` | exact source revision containing §§115–118 |
| `origin/egorribun` | `2774de52d158cf0b7611b331586014a8420a1df2` | stale remote revision used by PR #1266's historical run |
| Ahead/behind | `0 46` (`origin/egorribun...HEAD`) | 46 local commits are not yet available to hosted CI |
| Current-SHA hosted runs | `gh run list --commit HEAD` → `[]` | no release evidence exists for `a7121e969` |
| Historical PR | `#1266`, Matrix run `34923631288` | source head `2774de52`; diagnostic only, never current-SHA evidence |
| Historical coverage artifact | `quality-evidence-30c449...` | schema-valid but bound to merge ref `30c449`, source head `2774de52`, and run `34923631288`; not reusable |

The tracked worktree has no uncommitted implementation changes. The only
remaining dirty paths are preserved user-owned or externally supplied files:

    frontend/WASM_SOURCE_PROVENANCE.json
    frontend/rust-crypto/pkg/uni_wasm_crypto_bg.wasm
    frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm
    .tmp_preflight/
    .tmp_stryker_18/
    .tmp_stryker_22/
    docs/audits/AUDIT_PLATFORM_FULL.md
    services/file-processor/coverage_capability

These paths are intentionally neither staged nor removed. `git diff --check`
passes, and `uv run python scripts/quality/validate_ci_check_catalog.py` passes
with `55 workflows, 182 jobs`.

### 119.2 Commits included in this source identity

1. `281d0729fff70cd48e6c3a12b64ede4d68dce470` — fail-closed internal-route
   token boundary and production `INTERNAL_AUTH_TOKEN` validation (SEC-04).
2. `47600e14ae335865c6c04d70438d38ffd176c58f` — exact `weekly-cleanup`
   main-branch guard in the CI check catalog.
3. `a7121e969a102a9898d5a017029a2c75c23415d8` — production security fixture
   supplies the explicitly allowlisted test token; runtime validation remains
   strict.

Sections §§115–118 are implementation/evidence notes for these commits. They
do not imply that any hosted, Linux, browser, mutation, manifest, Docker,
staging, or release gate has passed on `a7121e969`.

### 119.3 Evidence status and next immutable boundary

Class-C local evidence currently available after the remediation commits:

* security/middleware regression suite: `124 passed`;
* Helm staging contract suite: `217 passed` and Helm lint green;
* production security fixture suite: `9 passed` (one pre-existing warning);
* CI catalog validator: `55 workflows, 182 jobs`;
* supported Compose configuration checks and WASM provenance hash check:
  green, without starting the project stack.

The following remain release-blocking and must be generated after the
non-force push of this exact source (and after any subsequent code/docs
commit, with the identity updated again):

1. terminal PR workflows for the exact source SHA, including all mutation
   shards, Go race/security jobs, browser/Lighthouse matrix, Schemathesis,
   dark unauthenticated smoke, and CI Success;
2. complete current-SHA coverage/mutation manifests with report hashes,
   source roots, tool versions, run/attempt provenance, and no missing or
   stale artifacts;
3. current standard security scan and independent review of privileged
   workflow changes;
4. three comparable green runs before any evidence-based change to mutation
   parallelism or runner scheduling;
5. external-only merge/main recertification, exact-six immutable images,
   SBOM/signatures/attestations, digest Docker smoke, Kubernetes staging with
   TLS/ExternalSecrets/observability, CWV/browser-device matrix, chaos,
   rollback, and production release evidence.

Until these artifacts exist, the plan status remains
`EVIDENCE-BLOCKED / EXTERNAL-ONLY`; no `100%`, `green`, or release-ready claim
is permitted. The stale run `34923631288` may be archived as diagnostic
history after it reaches a terminal state, but it must not be rerun or
promoted to evidence for this source.

## 120. Current-SHA fixture remediation and authoritative CI boundary (2026-09-15)

This checkpoint supersedes the stale source-identification details in §119
without rewriting their historical record. It records the next two local
remediation commits and the last completed hosted run before the next push.

### 120.1 Local source and worktree identity

| Field | Observed value | Interpretation |
|---|---|---|
| Active branch | `egorribun` | requested implementation branch; no merge or force-push performed |
| Local source `HEAD` | `2c20168c31ae76b9d680c29fb31051cd8e89f543` | exact local source after route-summary and staging-fixture fixes |
| `origin/egorribun` | `bd2354fa7085163d4c1f5a2abec2273d88cb1c8e` | last remote source; does not contain the two local commits |
| Ahead/behind | `2` commits ahead, `0` behind | push is intentionally deferred until local focused gates and plan checkpoint are complete |
| User-owned tracked dirty paths | `frontend/WASM_SOURCE_PROVENANCE.json`, `frontend/rust-crypto/pkg/uni_wasm_crypto_bg.wasm`, `frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm` | generated/provenance artifacts; not logs and not part of either remediation commit |
| Untracked path | `docs/audits/AUDIT_PLATFORM_FULL.md` | externally supplied audit; preserved and never staged automatically |
| Archived temporary artifacts | `C:\Temp\university_ecosystem-untracked-archive-20260915` | six old non-audit files moved recoverably; source paths are absent and audit remains in place |

The hash above was captured with `git rev-parse HEAD` after the fixture commit;
it is the immutable source boundary for the next non-force push. `git diff
--check` is clean.

### 120.2 Backend shard-2 root cause and fix

Matrix run `34971079773` for source `bd2354fa7085163d4c1f5a2abec2273d88cb1c8e`
was terminal failure: 118 jobs, 92 success, 24 expected skips, and two
failures. The only product-relevant failure was backend Python 3.14 shard-2
job `104394473812`, with 15 staging/CWV tests failing before their intended
assertions because the test `Settings` fixtures omitted the mandatory
`INTERNAL_AUTH_TOKEN`. The aggregate `CI Success` job correctly propagated
that backend failure; it was not an independent defect. Runtime fail-closed
validation in `app/core/config/mixins/cors_settings.py` remains unchanged.

Commit `2c20168c3` adds one deterministic, explicitly allowlisted
non-production token fixture to the two affected test modules and passes it
to every staging settings construction. The independent `.env`-disabled RED →
GREEN reproduction passed `15` tests after the fix. Broader local evidence:

    uv run pytest -q -p no:cacheprovider \
      tests/test_cwv_rum_security.py tests/test_non_auth_quality_closure.py \
      tests/test_jwt_settings_closure.py tests/test_auth_reset_foundation.py \
      tests/test_route_dependency_inventory.py \
      tests/test_workflow_fail_closed_contracts.py \
      tests/test_quality_workflow_contract.py --disable-warnings
    # 344 passed in 173.71s (0:02:53)

    uv run ruff check tests/test_cwv_rum_security.py \
      tests/test_non_auth_quality_closure.py
    uv run ruff format --check tests/test_cwv_rum_security.py \
      tests/test_non_auth_quality_closure.py
    git diff --check
    # all passed

The first commit in this local boundary is `6a65e3177`, which makes route
dependency inventory validation fail closed on summary drift and regenerates
the canonical 150-route inventory (`25` Dishka, `112` approved legacy,
`13` public/worker, mixed ownership `0`). Its focused suite was `5 passed`,
the route/workflow/quality group was `221 passed`, and the repository harness
was `29/29`.

### 120.3 Hosted evidence boundary and next action

The same-SHA performance workflow `34971079536` was green (all four jobs),
and the remaining security, contract, supply-chain, dark unauthenticated
smoke, browser, Rust, Go, Lighthouse, and Schemathesis workflows for
`bd2354fa` were green or conditionally skipped. These results are historical
diagnostics only: they cannot certify local `2c20168c3`.

The next immutable action is a non-force `git push origin egorribun` after the
plan checkpoint is committed. The resulting SHA-bound matrix must reach a
terminal state and be paginated from the Actions API; every mutation,
coverage, manifest, provenance, security, browser, and CI-Success result must
be classified for that exact SHA. The 24 skips in run `34971079773` remain
expected guard/dependency skips, not failures, but their guards must be
rechecked in the new run.

No mutation cap, retry policy, timeout, exclusion, quarantine, suppression,
coverage floor, or security gate has been weakened. Do not promote the old
run, the old coverage artifacts, or the currently running Codex Security scan
(`224f2ae5-d93b-495f-80f7-6c8e5fe29cb1`, owned by another continuation) to
current-SHA evidence. The plan remains
`EVIDENCE-BLOCKED / EXTERNAL-ONLY` until the new source has terminal fresh CI,
current manifests, and the remaining staging/release evidence.
