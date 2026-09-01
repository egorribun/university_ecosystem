# University Ecosystem MVP Quality Closure Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** продолжить работу от контрольной точки `e0989e29cfca88ee9a650eb264d6fa7674031c9a` на ветке `egorribun`, сохранить уже реализованные основные вертикали MVP, закрыть подтверждённые инфраструктурные и mutation-дефекты текущего PR, получить полный current-SHA набор quality/mutation/security evidence и довести тот же immutable build через Docker и production-like staging до доказуемо готового к релизу состояния.

**Architecture:** репозиторий рассматривается как единая fail-closed система качества. Каждая технологическая область формирует нативные отчёты, а SHA-bound агрегатор принимает только полные, свежие и хешированные артефакты одного workflow run/attempt, отдельно фиксируя source head SHA и tested merge SHA. Уже реализованные продуктовые вертикали проходят evidence-first gap-аудит и меняются только при воспроизведённом дефекте; CI закрывается root-cause группами через RED → GREEN → REFACTOR и оптимизируется по измеренному критическому пути при лимите 20 одновременно исполняемых jobs без ослабления coverage, mutation, security или browser matrix.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, Dishka, PostgreSQL, Redis/Valkey, NATS, transactional outbox, pytest/coverage.py/mutmut; React 19, TypeScript 7, TanStack Router/Query, Zustand, Valibot, Vite 8/Rolldown, Vitest/Stryker, Playwright, Storybook, Lighthouse; Go 1.26 modules, race detector, golangci-lint; Rust, cargo-llvm-cov, WASM, PyO3; Docker Compose, Caddy, Helm/Kubernetes, Kyverno, ExternalSecrets, Prometheus/Grafana/Tempo/Loki; GitHub Actions, CodeQL, Semgrep, Bandit, detect-secrets, gitleaks, Trivy, SBOM и provenance.

**Audit refresh:** `2026-08-31T13:37:11+03:00`; live PR `#1257`, source head `e0989e29cfca88ee9a650eb264d6fa7674031c9a`, active matrix run `33349026009`. Snapshot динамический: перед исполнением и перед любым утверждением о закрытии его необходимо обновить через paginated GitHub Jobs API.

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

### 1.1 Репозиторий

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

### 1.2 Live PR и workflow snapshot

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

### 1.3 Current root-cause ledger

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

### 1.4 Fresh successes на current source SHA

Отдельные workflow runs, завершившиеся success: Cargo Deny, Checkov, CodeQL Advanced, Continuous Performance Benchmarking, Pact boundaries, OpenAPI/Spectral contracts, DB Performance, Dependency Review, Generate OpenAPI, Gitleaks, Go Fuzz, Go Lint & SBOM, Nilaway, Python Fuzz, Renovate validation, Rust Fuzz, semantic title, SonarCloud, SQLMap, TruffleHog, unauthenticated light/dark smoke и Zizmor.

Внутри main matrix run уже подтверждены:

- backend unit shards 0–3, integration shard 0 и backend aggregate;
- Alembic migrations;
- Schemathesis shards 1–4 и aggregate;
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

### 1.5 Skipped и cancelled jobs

| Класс | Jobs | Решение |
|---|---|---|
| intentional guard | `Trusted Codecov Upload` на PR; integration shards 1–3, если reusable workflow назначает integration только shard 0; WebSocket 10k advisory по его явному guard | сохранить guard и contract-test его область |
| upstream-blocked, недопустимы как final evidence | frontend unit shards, lint/format, production build, Lighthouse shards, bundle analysis, performance gate, Coverage & Quality Policy Gate, Frontend Mutation Artifact Round-trip | автоматически разблокировать после `RC-WASM-01` и повторить на новом SHA |
| timeout/cancel defect | ws-hub Go mutation job и семь Stryker shards | исправить стоимость/DAG/evidence; не считать intentional skip |
| separate workflow guard | Chromatic и Dependabot auto-merge | проверить `if:` против event/actor; документировать, но не превращать в required PR blockers без contract change |

Каждая запись проверяется повторно в terminal snapshot: таблица не разрешает blanket-утверждение, что «все skipped нормальны».

### 1.6 Что уже находится в checkpoint

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
| 6. Messenger/ws-hub | `OPEN-DEFECT` | Go integration/lint/fuzz и local `go test ./...` green | закрыть message-length P1, admin-action visibility, 44px targets и stale WS contract; повторить race/coverage/mutation evidence |
| 7. Profile/Settings/Activity/i18n | `OPEN-QUALITY` | profile/activity/settings implementation; local typecheck и `i18n:check` 18/18 green | добавить repository-wide static/dynamic/raw-key scanner; final frontend matrix |
| 8. Notifications/Web Push | `OPEN-DEFECT` | canonical topics, delivery/retry, SSRF/same-origin defenses | admin test/broadcast должны вызывать result cleanup/update path и иметь regression tests |
| 9. Full quality closure | `OPEN-QUALITY` | contracts, migrations, security workflows, cross-browser E2E частично fresh-green | WASM, secrets, mutation, ws-hub evidence, final normalizer/manifest и zero-warning closure |
| 10. Docker/staging/release | `EXTERNAL-ONLY` + `EVIDENCE-BLOCKED` | release/exact-six validators и существующие `-Core`/`-Lean` launch modes | immutable images, Docker smoke, main, registry attestations, staging/TLS/observability/CWV/devices/chaos/rollback/production |

### 1.9 Подтверждённые продуктовые gaps

1. `P1 / MSG-CONTRACT-01` — message length расходится между send/config (`10 000`), DB/edit/frontend WS (`32 768`) и Pydantic create/response (`2 000`). Сообщение, принятое одним слоем, может сломать response validation. Нужен один канонический предел, OpenAPI/WS/backend/frontend generation и boundary tests для `limit-1 / limit / limit+1`.
2. `P2 / MSG-AUTHZ-01` — `ChatArea` показывает Clear/Delete Chat обычным участникам, хотя backend разрешает команды только admin. UI обязан вычислять capability из роли; backend 403 остаётся обязательной защитой; существующий тест, закрепляющий неверное поведение, заменить RED contract test.
3. `P2 / MSG-A11Y-01` — controls 28/36px в `ChatWindow` нарушают обязательные 44×44 touch targets. Исправить hit area без layout/virtualizer regression и проверить keyboard/mobile screenshots.
4. `P2 / PUSH-CLEANUP-01` — admin `/push/test` и `/push/broadcast` вызывают delivery, но не `process_push_results()`: 404/410 subscriptions не удаляются, success не обновляет `last_seen_at`. Унифицировать orchestration и проверить idempotency/partial failure.
5. `P2 / I18N-GATE-01` — текущий `i18n:check` доказывает RU/EN parity, но не сканирует repository-wide static/dynamic/raw keys. Добавить scanner с fixtures для interpolation/plural/date/number и dynamic-key allow contract.
6. `P3 / WS-CONTRACT-01` — Python WS contract test не знает актуальные edited/deleted/reaction/checkpoint types и проверяет устаревший `read`; экспорт `sendRead` не принимается ws-hub allowlist. Удалить dead surface либо синхронизировать contract, generation и tests после определения единственного owning receipt path.

Эти gaps имеют конкретные пути и воспроизведение; они являются единственными основаниями для product changes, найденными в текущем bounded аудите. Остальные checklist-пункты этапов 1–8 используются как recertification, а не как разрешение на перепись.

### 1.10 Focused evidence аудита

- `uv run pytest -q tests/contracts/test_ws_message_contract.py tests/test_mfa_openapi_artifacts_contract.py tests/test_mfa_webauthn_tombstone.py` → `26 passed`;
- `frontend: npm run typecheck` → success;
- `frontend: npm run i18n:check` → `18 passed`, при этом suite проверяет parity, а не полный raw/dynamic-key contract;
- `services/ws-hub: go test ./...` → success;
- `services/ws-hub: CGO_ENABLED=1 go test -race ./...` → local evidence unavailable из-за отсутствующего GCC, поэтому race остаётся CI-owned gate;
- local и `origin/egorribun` HEAD совпадали; субагенты не меняли git/worktree/external state.

Focused evidence имеет класс C и не повышается до release evidence из-за успешного exit code одного subset.

### 1.11 Evidence index и граница полноты

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

**Граница абсолютной полноты:** план хранит все подтверждённые root causes, product gaps, status decisions, dependencies, acceptance criteria, evidence anchors и external boundaries. Он намеренно не дублирует полный многотысячестрочный log и изменяющийся список всех 128 mutmut job IDs. Их каноническая форма — terminal machine-readable artifact из Task 1. Пока run `33349026009` не terminal, утверждение «абсолютно вся финальная CI-информация собрана» запрещено; после terminal state artifact и итоговые totals должны быть добавлены в audit без изменения причинной структуры плана.

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
        A["Checkpoint e0989e29c и terminal CI inventory"] --> B["WASM race + detect-secrets"]
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

## 7. Task 1 — terminal inventory и artifact ledger run 33349026009

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
- [ ] Сохранить machine-readable triage в `artifacts/quality/ci-triage/run-33349026009.json`; не коммитить runtime artifact.
- [ ] Отдельно скачать Stryker preflight/shard artifacts и mutmut selected-results artifacts, не принимая partial reports как release evidence.
- [ ] Для каждого mutation family построить таблицу `expected / observed / missing / duplicate / survivor / timeout / error / no-coverage / killed`.
- [ ] Проверить source head `e0989e29...`, tested merge `3e4d8f89...`, run ID и attempt во всех metadata; неправильное название merge SHA как head — defect, даже если hash сам по себе верен.
- [ ] Составить ordered fix queue: security/data-loss → core build → unit/contracts → browser → mutation → performance.

**Предлагаемый новый анализатор:**

- Add: `scripts/quality/analyze_ci_critical_path.py`
- Add tests: `tests/test_ci_critical_path_analysis.py`
- Generated fixture: `tests/fixtures/quality/github-actions-jobs.json`

Интерфейс:

    uv run python scripts/quality/analyze_ci_critical_path.py --repository egorribun/university_ecosystem --run-id 33349026009 --concurrency-cap 20 --output artifacts/quality/ci-critical-path.json

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

## 8. Task 2 — устранить WASM rustup race

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

## 9. Task 3 — закрыть detect-secrets findings без слепого suppression

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

**Статус:** `FRESH-GREEN` на current tested merge: Alembic, PostgreSQL migration gate, rollback integrity, Squawk (0 issues) и schema drift прошли. Checklist сохраняется для final-SHA rerun.

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

**Статус:** `CODE-COMPLETE / FRESH-BACKEND-GREEN`. Сохранить отдельные duplicate-valid, invalid-format и empty/mixed cases; final-SHA rerun обязателен.

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

**Статус:** `CODE-COMPLETE`. Current `also_copy` уже включает `security`, exact audit allowlist, `quality`, generated inputs, `alembic` и `alembic.ini`; universe v2 проверяет inventory/hash/symlink/traversal. Не повторять старое исправление, а сохранить contract при mutation-runner changes.

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

**Статус:** `FRESH-GREEN` для Chromium 4/4, Firefox, WebKit и mobile-WebKit на current tested merge. Checklist остаётся final-SHA regression contract.

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

**Статус:** `FRESH-GREEN` для light и dark unauthenticated workflows на current source SHA.

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

**Статус аудита:** `OPEN-DEFECT`. Вертикаль в основном реализована, fresh Go integration/lint/fuzz и local `go test ./...` green, но bounded audit нашёл один P1 contract defect, два P2 UI defects и stale WS contract. `go test -race` локально не считается выполненным без доступного CGO/GCC; CI evidence должен быть сохранён отдельно от Go mutation diagnostic.

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

**Статус аудита:** profile/settings/activity — `IMPLEMENTED-IN-CODE / EVIDENCE-BLOCKED`; i18n — `OPEN-QUALITY`. Local typecheck и текущая RU/EN parity suite (18/18) green, но обязательный static/dynamic/raw-key scanner отсутствует.

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

**Статус аудита:** `OPEN-DEFECT`. Канонические topics, Web Push delivery/retry и security defenses реализованы; admin test/broadcast paths не применяют canonical post-delivery result cleanup, поэтому stale subscriptions и `last_seen_at` обрабатываются несогласованно.

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

**Current evidence:** четыре Schemathesis shards/aggregate, OpenAPI/Spectral/backward compatibility, TypeScript/MSW/GraphQL drift и Pact boundaries зелёные на текущем tested merge SHA. Ниже требуется сохранение и final-SHA rerun, а не повторная реализация.

- [ ] Four Schemathesis shards.
- [ ] Aggregate rejects missing/cancelled shard.
- [ ] OpenAPI generated deterministically.
- [ ] TypeScript SDK drift zero.
- [ ] MSW mocks drift zero.
- [ ] Pact and snapshots current.
- [ ] GraphQL schema drift zero.

### 20.6 Security/supply chain

**Current evidence:** отдельные CodeQL, Zizmor, Checkov, Gitleaks, TruffleHog, dependency/container/SBOM workflows зелёные. Baseline Integrity green не закрывает отдельный красный detect-secrets scan с четырьмя findings.

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
- для PR: `source_head_sha=e0989e29...`, `tested_commit_sha=3e4d8f89...`; merge SHA запрещено называть source/head;
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
- [ ] Все fresh failures run 33349026009 отображены в Tasks 2–5 и CI inventory; aggregates не посчитаны как отдельные roots.
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

### 31.1 Identity и сохранность рабочей области

- Рабочая ветка: `egorribun`.
- Локальный и remote checkpoint до следующего push: `e0989e29cfca88ee9a650eb264d6fa7674031c9a`.
- PR #1257 и run `33349026009`, описанные в baseline, являются историческим
  snapshot; после push любого нового коммита их нельзя выдавать за fresh result.
- Пользовательские stash entries не изменяются. Перед staging требуется повторный
  `git status --short` и явная инвентаризация всех untracked paths.
- В `docs/superpowers/` обнаружены только четыре ожидаемых плана; staging
  разрешён только по явным путям, перечисленным в разделе 1.1.

### 31.2 Подтверждённые изменения и локальные evidence

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

### 31.3 CI critical-path и Docker observations

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

Независимый read-only review после Go governance follow-up обнаружил один
введённый этим follow-up P2 и три ранее существовавших P2. Введённый риск
исправлен до staging; остальные не маскируются как зелёные и остаются
воспроизводимым backlog до отдельной security-вертикали:

| ID | Severity/owner | Reproduction and disposition |
|---|---|---|
| `SEC-GO-DIAG-01` | P2 / CI security owner | `CONFIG_SHA256` мог следовать PR-controlled symlink. Исправлено guard-ом `git ls-files --error-unmatch` + `-f && ! -L` до чтения; workflow contract и actionlint повторно зелёные. |
| `SEC-CI-DL-01` | P2 / CI security owner | `ci.yml` actionlint job скачивает installer script с mutable `raw.githubusercontent.com/.../main`. Зафиксировать release asset+checksum или trusted action перед release hardening; текущий PR не подменяет этот backlog на недоказанный suppression. |
| `SEC-CI-DL-02` | P2 / CI security owner | Hadolint/ShellCheck binary downloads используют URL без checksum. Добавить checksum-verified downloads или digest-pinned actions в отдельном RED/GREEN change с runner smoke. |
| `SEC-AUDIT-DL-01` | P2 / security owner | Security-audit checkouts не везде задают `persist-credentials: false`, а detect-secrets installer не hash-pinned. Исправлять совместно с verifier воспроизводимости, не меняя required gate semantics. |
| `SEC-BASELINE-01` | P2 / security owner | `scripts/verify_secrets_baseline.py` сравнивает только result paths; differing finding hashes в том же файле воспроизводимо возвращают `rc=0`. Без historical baseline нельзя безопасно различить допустимое обновление и добавленный secret; нужен отдельный workflow/base-baseline design. |

Эти P2 не являются P0/P1 или high/critical findings и не добавляют
exclusions/quarantines. До выполнения отдельной hardening-вертикали они должны
оставаться явно перечисленными в audit и не могут быть названы закрытыми.
