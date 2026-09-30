<!-- markdownlint-disable-next-line MD041 -->
> **Исторический снимок плана от 2026-09-28 — SUPERSEDED.** Это не действующая
> инструкция и не источник разрешений: факты, статусы, порядок работ, действия с
> Git/PR и инфраструктурные решения ниже относятся к снимку на указанную дату.
> Для текущих целей, решений и порядка работы используйте
> [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), для оперативного состояния —
> [STATUS.md](STATUS.md), а для обязательных инвариантов — корневой
> [AGENTS.md](../../../AGENTS.md). Актуальные критерии остаются применимы только
> там, где они подтверждены ТЗ, мастер-планом или действующим quality contract;
> уникальные требования из снимка должны быть перенесены до его удаления.

# [SUPERSEDED] University Ecosystem — исторический план MVP (2026-09-28)

## Context

Этот исторический approved snapshot фиксирует состояние на 2026-09-28. Текущий мастер-план и оперативный статус ведутся в `MVP_MASTER_PLAN.md` и `STATUS.md`; факты ниже относятся к указанному снимку.

**Git и PR**
- `HEAD == origin/egorribun == PR #1266 head == 035e2d2d1`; ветка на 884 коммита впереди `main` (`481dba81e`).
- Tracked-дерево чистое. Untracked только пользовательский `docs/audits/AUDIT_PLATFORM_FULL.md`.
- 4 stash, 10 worktree (3 в `~/.codex/worktrees`, 7 `../ue-*` с junction на `node_modules`), `artifacts/` = 1.1 ГБ (ignored).

**CI на `035e2d2`** (Matrix run `36362444946`) — terminal failure.
- Единственная корневая причина — `tests/test_workflow_fail_closed_contracts.py:1220`. Два новых шага O9 в `ci.yml` (job `stryker-shards`, стр. 1389/1392 и 1409/1411) имеют `continue-on-error: true`, но их нет в `expected_steps` (стр. 1221–1286). Воспроизведено локально.
- Следствие: backend-tests упали, и все mutmut/Stryker jobs были skipped. **На текущем SHA нет ни одного мутационного результата.**
- Остальные 14 PR-workflow зелёные: CodeQL, SBOM, Checkov, fuzz, contract, perf.

**Мутационный долг — главный объём работы**
- Frontend: последний полный инвентарь (run `36194161259`, 09-27) — **6 083 мутанта в 295 файлах**.
  - По каталогам: hooks 1739, features 1391, pages 1251, components 969.
  - 36 файлов с ≥50 мутантами дают 2 992 (≈50%). Top: `useMessengerController` 288, `useChatWebSocket` 188, `StoriesAdmin` 142, `Schedule` 139, `NewsDetail` 131, `useNewsInteraction` 121, `ResetPassword` 115.
  - С тех пор 35 коммитов изменили 80 файлов, поэтому свежее число неизвестно.
- Backend: известные семейства survivors/timeouts:
  - `NotificationDeadLetterPurged.from_dict`;
  - auth reset timeouts (**реальный дефект**: executor, унаследованный через fork, зависает — доказано на Linux);
  - `_unlink_ignore_missing`, `InternalAccessMiddleware.__init__`;
  - private static path, chat forward, notification delivery;
  - SMTP `cast`.
- Темп последних дней — около одного модуля в день под тяжёлой ceremony. Handoff вырос до 1 591 строки, continuation — до 8 809.

**Зависимости**
- 16 Dependabot-алертов на `main` (1 critical anyio, 7 high). В ветке все исправлены (anyio 4.14.2, httpx2/httpcore2 2.12.0, urllib3 2.7.0, js-yaml 4.3.2, grpc 1.83.2, OTel 1.46.0).
- Новые PR: #1292 go (3), #1293 npm (33, в т.ч. React 19.3 и Vite 8.3), #1294 pip (7, в т.ч. mutmut 3.8), #1295 actions (15).

**Продукт** (ТЗ: `docs/superpowers/plans/University_Ecosystem_MVP.md`)
- Все области реализованы. В коде нет ни одного TODO/FIXME.
- Приёмка почти полностью на mocked API: 45 Playwright specs через `page.route`/`mockApi.ts`.
- Живого лейна против реального backend с ролями нет. Mailpit и VAPID в compose тоже нет.
- В CI никогда не запускаются `chat-realtime`, `chat_workflow`, `group_management`, `a11y-messenger`.
- E2E нет у Stories, регистрации и сброса пароля, activity, admin users/flags, shell-поведения. `MainLayout` в E2E-режиме подменяет shell стабами.
- Visual-baselines Playwright есть только под Windows.
- Флаги `new-chat-ui`, `semantic-search`, `graphql-subscriptions` объявлены (`app/core/feature_flags.py`, `k8s/flagd/flags.json`), но нигде не потребляются.

**Инфраструктура**
- Есть: compose Core/full (`start-docker.ps1 -Core/-Build/-SeaweedFS`), Helm-чарт с lint/kubeconform, Kyverno с тестами, workflow шести immutable-образов (Trivy, SBOM, cosign, provenance), read-only `s3_cutover_preflight.py`, `be02_catalog_preflight.py` (только phase four).
- Нет:
  - kind-кластера (нет ни `deploy/kind`, ни скрипта, ни `values-kind.yaml`);
  - Mailpit в compose;
  - provisioning дашбордов Grafana;
  - restore-скрипта и runbook-ов rollback/chaos/DR;
  - `config --quiet` для `full.yml`, cutover- и observability-комбинаций.
- `heartbeat_watchdog.py` существует, но не подключён ни к одному workflow.

**Внешний аудит:** 59 closed / 2 declined / 2 open. Открыты BE-02 (deployed-catalog preflight) и RUST-P3-03 (final-SHA evidence). P0 и P1 закрыты.

## Исторические решения пользователя (снимок 2026-09-28; superseded)

1. **Мутации: 100% viable по всему коду, но индустриально.** Работают 3 агента на непересекающихся файлах. Для обратной связи — локальный incremental Stryker; canonical остаётся fresh. Эквивалентные мутанты убираются упрощением кода. Evidence — только канонический CI. Продуктовая приёмка идёт параллельно.
2. **Процесс облегчается.**
   - Evidence = CI run + JUnit + отчёты мутаций.
   - Независимое ревью нужно только для production-кода security/auth/data.
   - Handoff сжимается до короткого статуса (≤150 строк), история уходит в архив.
   - RED→GREEN, fail-closed гейты и запрет timeout-инфляции/exclusions/waivers сохраняются.
3. Исторический security-PR в `main` предполагал отдельное подтверждение перед merge. Это требование заменено текущей авторизацией полного обычного release cycle из мастер-плана.
4. **Бампы #1292–#1295** вносятся в `egorribun` обычными коммитами по одной группе после первого зелёного CI. mutmut 3.7→3.8 откладывается до закрытия backend-мутаций.

Дополнительно (2026-09-28, после утверждения):

5. Историческое решение допускало admin bypass для #1296 при унаследованных от `main` красных проверках. Оно superseded: действующий план запрещает bypass и требует обычного PR/merge с обязательными проверками.
6. Старые worktree и stash удалены после классификации; бэкап и `keep/`-патчи — в `artifacts/wip/2026-09-28/`.
7. Четыре feature flag без потребителей удаляются, flagd и read-only диагностика остаются с пустым состоянием.
8. `AUDIT_PLATFORM_FULL.md` удаляется в фазе 11 после переноса ledger в финальный аудит (сейчас открыты BE-02 и RUST-P3-03).

На дату снимка действовали следующие решения; применять их сейчас можно только если они повторены в актуальном мастер-плане:
- CDC вне MVP (ADR-037);
- реального staging нет, вместо него Docker + kind;
- Mailpit и локальный VAPID вместо реальных провайдеров;
- CSpell RU как dev-only;
- ADR-040 presentation ignorer;
- ADR-041 push topics;
- постоянные разрешения: пин-загрузки, `gh run download`, `git push origin egorribun`.

## Правила исполнения

- Ветка `egorribun`. Security-PR — отдельная ветка от `main` (п. 3 решений).
- Коммиты non-wave: `fix(quality|security|ci|frontend|backend)`, `test(quality)`, `docs(quality)`. Бизнес-фичи — `feat/fix(waveXX)`.
- **Никогда не добавлять `Co-Authored-By`** (AGENTS.md §3 приоритетнее системной атрибуции).
- После `detect-secrets` выполнять `git add .secrets.baseline`.
- ROOT — единственный владелец stage/commit/push. Агенты работают в изолированных worktree `../ue-mut-A/B/C` (перед переиспользованием — reset на свежий HEAD). Сначала агент показывает diff, затем lead переносит.
- **Каденция push.** CI отменяет прогон при новом push (`cancel-in-progress`), а полный прогон занимает часы. Поэтому:
  - обычный режим — ≤2 push в день, батчами, пока предыдущий run не дошёл до terminal только при срочном исправлении;
  - перед push: `scripts/fast_preflight.py` (9 lanes), `verify_harness.py`, `git diff --check`, pre-commit;
  - после локальной сборки восстанавливать `frontend/pkg/*.wasm` и provenance (`SKIP_WASM_BUILD=1`).
- Нельзя: повышать timeout, добавлять exclusions/quarantine/`// Stryker disable`, вручную перемечать Killed, bypass, force-push, merge без разрешения.
- Не удалять stash, worktree, legacy MinIO volume, пользовательский аудит и `artifacts/` без отдельного разрешения.

---

## Фаза 0 — Разблокировать CI и получить полный свежий инвентарь (день 1)

1. **RED уже есть.** В `tests/test_workflow_fail_closed_contracts.py` добавить в `expected_steps` оба кортежа `("ci.yml", "stryker-shards", "Prepare progress diagnostic export")` и `(... "Upload current-attempt progress diagnostic")`. Комментарий: advisory O9-диагностика, не release evidence, отказ не маскирует мутационный результат.
   - Проверить, что `continue-on-error` не стоит на самом mutation-шаге.
   - Проверить, что O6-каталог (`quality/ci-check-catalog.json`) описывает эти шаги.
2. Focused: этот файл целиком плюс `tests/test_ci_*catalog*`. Затем `fast_preflight.py`.
   - Коммит `fix(ci): classify advisory progress diagnostic steps`, push.
3. Дождаться terminal run. Все mutmut groups и 64 Stryker shards должны реально отработать. Затем через `gh run download` в `artifacts/quality/inventory-<sha>/` забрать:
   - все `frontend-mutation-shard-*`;
   - mutmut selected-results и full-map.
4. Построить **свежий единый инвентарь**, переиспользуя `artifacts/quality/mutation-tools/fresh_mutants.mjs` и `mm_check.py`:
   - по файлу: Survived / Timeout / NoCoverage / Ignored(ADR-040);
   - backend по семействам.
   Инвентарь пересобрать в три сбалансированные очереди A/B/C по файлам (не по числу мутантов) с учётом доменов (см. фазу 3).
5. Все прочие red jobs этого run классифицировать: root, downstream или by-design по `if:`/`needs:`.

## Фаза 1 — Security-PR в `main` (день 1–2, параллельно с ожиданием CI)

- Ветка `security/default-branch-alerts` от `origin/main` (`481dba81e`). Только минимальные бампы lock/манифестов под алерты:
  - `uv.lock`: anyio→4.14.2, httpx2/httpcore2→2.12.0; urllib3 проверить по манифесту `pyproject.toml` (алерт указывает на pyproject);
  - `frontend/package-lock.json`: js-yaml→4.3.2;
  - Go-модули сервисов: grpc→1.83.2, OTel→1.46.0 (`go mod tidy`, `go mod verify`).
- Сверить, что ограничения `pyproject.toml` на `main` допускают эти версии. Иначе — минимальная правка границы.
- Push ветки → PR в `main`. CI `main`-овской версии workflows должен быть зелёным; падения классифицировать.
- Исторически для этой security-ветки ожидалось отдельное подтверждение merge. Текущее разрешение на обычный полный release cycle и запрет bypass определены мастер-планом; после merge проверять alerts по его действующим требованиям.
- Совместимость с #1266: те же версии, конфликт в lock-файлах при финальном merge решается тривиально.

## Фаза 2 — Сброс процесса и гигиена (день 1–2)

1. **Статус вместо handoff.** Новый `docs/superpowers/plans/STATUS.md` (≤150 строк): identity, CI, очереди мутаций, фазы этого плана с чекбоксами, открытые решения.
   - Отдельные handoff-документы были историческими источниками. Их миграция и дальнейшая очистка теперь определяются только текущим мастер-планом.
   - Перед любым удалением — проверить ссылки и перенести уникальные требования в действующие документы.
   - Далее STATUS обновляется одной короткой дельтой за сессию.
2. Память обновить:
   - новый memory-файл с решениями 2026-09-28;
   - убрать из текущих документов ссылки на исторические handoff-файлы и держать оперативный указатель на STATUS;
   - удалить устаревшие записи про «§0.000000».
3. Инвентаризация worktree и stash (read-only отчёт в STATUS):
   - что уникально в `../ue-e2e`, `ue-mm`, `ue-mm2`, `ue-mut-A/B/C`, `.codex/worktrees/*`, 4 stash;
   - предложение пользователю, что удалить. Удаление — с разрешения: сначала `cmd /c rmdir` junction, потом `git worktree remove`.
4. Ledger `AUDIT_PLATFORM_FULL.md` в этом снимке отмечен как незатреканный. Фактическое текущее состояние и условия его удаления см. в `STATUS.md` и мастер-плане.
5. Мёртвые флаги `new-chat-ui`, `semantic-search`, `graphql-subscriptions`: подтвердить отсутствие потребителей, затем удалить из `app/core/feature_flags.py`, `k8s/flagd/flags.json` и `tests/test_feature_flags.py` (`refactor(quality)`). Если потребитель найдётся — оставить и задокументировать.

## Фаза 3 — Индустриальное закрытие мутаций до 100% viable (≈2–3 недели, параллельно фазам 4–9)

### 3.1 Инструментарий (первые 1–2 дня)

- **Решение 2026-09-28 после сверки с документацией Stryker (Context7): incremental не вводится.** Локальный focused-прогон уже идёт через shard-путь `run-stryker.mjs`, встраивание incremental в fail-closed evidence-путь рискованно, а быстрые итерации покрывает `mutant_check_fast.mjs --only <ids>`. Рабочий цикл: `STRYKER_LOCAL_MUTATE_JSON='["<file>"]' npm run test:mutation` для инвентаря файла → `mutant_check_fast.mjs` для итераций → повторный focused-прогон до 100%. Исходный вариант ниже — история.
- ~~Локальный incremental Stryker только для обратной связи.~~
  - Env-переключатель в `frontend/stryker.config.mjs`, например `STRYKER_LOCAL_INCREMENTAL=1`: `incremental: true`, `incrementalFile` в `artifacts/quality/stryker-incremental/`.
  - Запрет при `CI=true` или `STRYKER_SHARD_RUN=1`.
  - Contract-тест: canonical/CI-путь всегда `incremental:false`.
  - Перед реализацией сверить семантику incremental/`--force` по документации Stryker через Context7.
- Скрипт-обёртка `artifacts/quality/mutation-tools/mutant_check_fast.mjs` (уже есть) закрепляется как стандарт per-file цикла: `STRYKER_MUTATE_JSON=[file]`, related tests, JSON → таблица survivors.
- Backend: `mm_loop.py`/`mm_check.py` в `../ue-mm`. Точечный прогон `mutmut run "<module>.<fn>*"` на Linux (Docker `python:3.14`) для семейств с fork/timeout, потому что Windows не воспроизводит.

### 3.2 Порядок (по риску, затем по объёму)

- **Волна 1 — security/auth и продуктовые дефекты**
  - Backend: auth fork executor. Это **product fix**: пересоздание `_auth_executor` и loop-bound семафоров после fork через `os.register_at_fork(after_in_child=...)`. Нужен Linux RED существующего proof, затем TDD и независимое security-ревью. После этого перепроверить все 16 timeout-мутантов auth reset.
  - Далее: `InternalAccessMiddleware`, private static path (не удалять repeated-decode guard), `_unlink_ignore_missing`, `NotificationDeadLetterPurged.from_dict` (тот же optional-delete паттерн, что у Retried/ScheduleDeleted), chat forward, notification delivery.
  - SMTP cast: удалить пустой `cast` структурно (как в кандидате `c0-owned-stand`), Linux-доказательство live-loopback.
  - Frontend: `useLoginFlow`, `ResetPassword`, `Register`, `ssrAuth`, `push/subscribe`, `usePushPreferences`, `useDndSettings`.
- **Волна 2 — messenger/realtime:** `useMessengerController` (288), `useChatWebSocket` (188) и messenger features.
- **Волна 3 — страницы и фичи с ≥50 мутантами:** оставшиеся ~30 файлов.
- **Волна 4 — хвост:** ~260 файлов с <50.

### 3.3 Работа над файлом (обязательный шаблон для агентов)

1. Прочитать свежие survivors файла.
2. Классифицировать каждый:
   - **поведенческий** — тест через публичный API/рендер;
   - **эквивалентный** — упростить код, чтобы мутант исчез: убрать лишние guard/default/cast. Никаких ignore/waiver;
   - **presentation** — должен покрываться ADR-040; если не покрыт, это не повод расширять ignorer без нового ADR.
3. Timeout и NoCoverage лечатся устранением причины: конечные ожидания, fake timers, bounded loops.
4. Повторный focused Stryker файла, результат — 0 survivors/timeouts. Затем полный vitest-файл, typecheck, lint.
5. Агент возвращает diff и таблицу «мутант → причина → чем убит». Lead проверяет выборочно, для security-кода — полностью. Затем коммит `test(quality): close <area> mutation survivors` батчем по 3–8 файлов.

### 3.4 Контроль темпа

- Цель — ≥400 закрытых мутантов в день суммарно (3 агента). В STATUS ежедневно фиксируется остаток по очередям.
- При отставании больше чем на 30% за 3 дня — эскалировать пользователю с цифрами. Молча снижать планку нельзя.
- Каждые 2–3 дня — push и полный CI как канонический пересчёт. Survivors из CI — единственный источник истины.

## Фаза 4 — Бампы зависимостей в ветку (после первого зелёного CI фазы 0)

Каждая группа — отдельный коммит, lock-файлы регенерируются инструментом:
1. #1292 go file-processor: `go mod tidy`, `go test -race ./...`.
2. #1295 actions (15): пины по SHA, `actionlint`, zizmor. Контракт пинов в `tests/`.
3. #1294 pip **без mutmut**: `uv lock --upgrade-package …`, полный backend.
4. #1293 npm (33): полный frontend-гейт — typecheck, lint, unit, build, e2e, bundle budget. Сверка WASM byte-parity и provenance. Особое внимание React 19.3 (hydration warnings) и Vite 8.3 (Rolldown warnings).

Отдельно, после фазы 3 backend: mutmut 3.8 и повторный полный mutmut. Dependabot PR считать superseded и закрывать только после доказательства, что их изменения вошли в выпущенный релиз, как указано в мастер-плане.

## Фаза 5 — Живой лейн приёмки (C0) (≈3–4 дня, lead, параллельно фазе 3)

Дизайн (одобряется вместе с этим планом): **run-owned стенд**, не трогающий пользовательские `.env`, БД и тома.

Уточнение 2026-09-28 после разбора `start-docker.ps1` и `docker-compose.full.yml`: сервисы читают фиксированный `env_file: .env.docker`, build-контексты и монтирования конфигов относительны корню, `container_name` нигде не задан. Поэтому стенд — **отдельный git worktree `../ue-live` на тестируемом SHA**. У него собственные сгенерированные `.env.docker`/`.env`/`.secrets`, а имя compose-проекта по каталогу (`ue-live`) даёт изолированные тома `ue-live_*` и сети. Пользовательские `university_ecosystem_*` тома и `.env*` не затрагиваются. `docker-compose.live.yml` переназначает опубликованные порты (caddy 18080/18443, backend 18000, Mailpit UI/API 18025) и добавляет Mailpit и VAPID. `start-docker.ps1` получает опциональный `-ExtraCompose <file>` (с contract-тестом), чтобы стенд поднимался тем же проверенным путём, что и основной стек. `live_stand.py down` удаляет только проект `ue-live` (guard на имя) и сам worktree.

- `docker-compose.live.yml` — overlay на `docker-compose.full.yml`:
  - запускается с `-p ue-live-<runid>`, у проекта собственные именованные тома и порты из свободного диапазона;
  - добавляет сервис **Mailpit** (v1.31.1, как в CI), backend настраивается на него через SMTP STARTTLS;
  - backend получает **VAPID**-ключи, сгенерированные на старте в `.secrets/live-<runid>/` (py_vapid или web-push generator), не коммитятся.
- `scripts/live_stand.py` с командами `up | seed | down`:
  - `up` — compose up, ожидание `/health/ready`;
  - `seed` — через `scripts/seed_admin_data.py`: student, teacher, admin и демо-контент;
  - `down` — `down -v` **только** своего проекта; guard на префикс имени.
- `frontend/playwright.live.config.ts` + `frontend/tests/e2e-live/`:
  - фикстуры ролей (реальный логин), helper Mailpit API для OTP и reset-писем;
  - Chromium с реальным PushManager против локального VAPID;
  - RU и EN, viewports 360 / 390 / 768 / 1024 / 1440.
- CI: новый `live-e2e.yml` (nightly + `workflow_dispatch`), compose в runner-е. Запись в O6-каталог, contract-тест. В required-контексты не добавлять без измерения бюджета.
- Существующие, но никогда не запускаемые specs (`chat-realtime`, `chat_workflow`, `group_management`, `a11y-messenger`) — перенести в live-лейн или включить в CI в `URL_STATE_E2E`-режиме. Сначала починить.
- Visual-baselines: сгенерировать Linux-снапшоты в официальном Docker-образе Playwright той же версии. Ревью каждого снапшота глазами, никакого слепого `--update-snapshots`. Windows-only baselines удалить или оставить только как локальные.

## Фаза 6 — Продуктовая приёмка по ТЗ (≈4–6 дней, после фазы 5; дефекты чинятся по ходу)

Для каждого пункта нужен live-spec или обоснованный mocked-spec, при необходимости — метрика. Дефект обрабатывается так: RED → fix → коммит `fix(<area>)`, или `feat/fix(waveXX)` для бизнес-функциональности.

| ТЗ | Приёмка (live, если не указано иначе) |
| --- | --- |
| §2 Auth/2FA | Регистрация; логин; TOTP enable/login; email OTP через Mailpit (6 цифр, TTL, 5 попыток, cooldown 60 с, resend, stale code); recovery-коды; reset password через письмо; safe redirect; 401/429. Отсутствие WebAuthn в UI/API/SDK |
| §3 Шапка/футер | Navbar compact-on-scroll без CLS (PerformanceObserver layout-shift <0.1), без glow; footer с Telegram SVG и едиными ссылками |
| §4 Скролл/табы | News/Events: категория не сбрасывает scroll; Map: после wheel/touch/pinch внешний scroll не прыгает; back/forward восстанавливает позицию; центрирование ползунков Events-табов и Activity-периодов (геометрия bbox) |
| §5 Карта | Lazy-import, один instance, long tasks <50 мс при зуме (CDP trace), изоляция жестов |
| §6 Мессенджер | DM и группы: send/receive через реальный WS между двумя контекстами (student↔teacher), dedup/order, reconnect, reply/edit/delete/forward/reactions/attachments, unread, mobile back, `role=log`, a11y |
| §7 Профиль | Просмотр/редактирование, аватар, достижения, валидация и откат, адаптивная сетка |
| §8 Настройки/i18n | Все 6 разделов: save/validation/apply/persist после reload; `i18n:check` плюс live-обход всех маршрутов RU/EN со сканером сырых ключей в DOM |
| §9 Активность | Heatmap/trends/grades, смена периода, empty/partial, табличная альтернатива |
| §10 Главная/Stories | Stories только по аватару; переключение, клавиатура/свайп, pause on hidden; **memory plateau** (CDP `HeapProfiler` после 20 open/close); нет wobble-hover; пустые карточки без лишней высоты |
| §11 Уведомления | Публикация admin по каждому из 5 топиков → in-app + реальный Web Push в Chromium, один notification ID, unread согласован, quiet hours, opt-out; **промпт разрешения** — позиция и показ только после действия пользователя |
| §12 Мобайл | Burger: focus trap, escape, scroll lock, быстрые тапы; bottom nav: равные hit-сектора, один active, центр иконок — на 360/390 |
| §13 Качество | axe без serious/critical на всех маршрутах; keyboard и zoom 200%; reduced motion; LHCI ≥0.95 на ключевых маршрутах; main JS <500 KB |

Плюс кросс-браузер: firefox/webkit/mobile-webkit (эмуляция) на mocked-наборе. Реальные устройства и field CWV в аудите записываются как согласованное ограничение.

Дополнительные строки приёмки (добавлены 2026-09-28 после сверки с ТЗ):

| Область | Приёмка |
| --- | --- |
| Admin | Users, feature flags, stories admin, notifications, audit — live-spec под ролью admin, плюс запрет доступа под student/teacher (403 и скрытая навигация) |
| PWA/offline | Service worker: offline-страница, кэш-стратегия, обновление версии (связка с `system.release`), отсутствие stale-bundle после деплоя |
| SSR | Нет hydration mismatch на всех маршрутах (console error = fail), корректные 404/500 SSR |
| Слабые устройства | Ключевые сценарии под CPU throttling 4× и Slow 4G: INP ≤200 мс, long tasks, FPS навбара и карты через CDP trace |
| Безопасность (матрица §8) | CSRF, open redirect, XSS в пользовательском контенте (news/chat/profile), IDOR между student-аккаунтами, oversize upload, rate limit — отдельные live-негативные specs |

## Фаза 6b — Дизайн-ревью редизайнов ТЗ (≈2–3 дня, после первых зелёных live-specs)

Фаза 6 проверяет поведение, но не отвечает на вопрос, выполнен ли **редизайн** «в стиле матового минимализма уровня ведущих сервисов». Для каждого экрана из ТЗ (login/register §2, navbar/footer §3, мессенджер §6, профиль §7, настройки §8, активность §9, главная и Stories §10, промпт уведомлений §11, burger и bottom nav §12):

- скриншоты RU/EN × 360/390/768/1440 × light/dark из live-стенда;
- разбор по skills `design:design-critique`, `design:accessibility-review` и `design:ux-copy`: иерархия, отступы, консистентность токенов, пустые состояния, микро-взаимодействия, отсутствие glow/wobble;
- список найденных недочётов → исправления `fix(waveXX)` → повторные скриншоты → Linux visual-baselines и Chromatic обновляются только после ревью.
- Итог — таблица «пункт ТЗ → экран → вердикт → коммит» в финальном аудите.

## Фаза 6c — Чистота кода и демо-готовность (≈1–2 дня)

- **Неиспользуемые зависимости и мёртвый код** (ТЗ §13): `knip` для frontend, `deptry` для Python, `go mod tidy` плюс `staticcheck` unused для Go. Каждое удаление подтверждается тестами; инструменты фиксируются как CI-гейты, если чисты.
- **Feature flags:** решение мейнтейнера (STATUS, открытое решение 4) — удалить или подключить.
- **Демо-данные для первой публичной демонстрации:** reviewed seed с правдоподобным контентом RU/EN (новости, события, расписание, карта, чаты, stories, активность) без персональных данных; команда `live_stand.py seed --demo`.
- **Go/realtime нагрузка:** k6 или существующий `run_chaos_loadtest.py` для ws-hub — N одновременных чатов, p95 доставки, отсутствие утечки goroutine/socket после disconnect и рестарта.
- **Security review всей ветки** перед merge: skill `security-review` по diff `main...egorribun` плюс ручная проверка auth/MFA/push/upload; findings → исправления.
- **Code review** итогового diff (`/code-review` high) по ключевым доменам перед финальным CI.

## Фаза 7 — Остальная quality closure (≈2–3 дня, частично параллельно)

- **Spelling:** `@cspell/dict-ru_ru` dev-only с записью в license-policy. Canary `mispeling`/`ашибка` должен падать. Расширить `cspell.json` с 9 файлов до утверждённого authored-корпуса `docs/` RU/EN, исправить реальные опечатки, обновить литерал в `tests/test_cspell_gate_contract.py` и CI-проверку `files_checked`.
- **Zero-warning build:** разобрать Rolldown plugin-timing и Node warnings. Contract на пустой stderr по allowlist.
- **Rust:** пин toolchain 1.97.1 вместо `stable` в `ci.yml` (rust-lint/rust-tests). RUST-P3-03 — final-SHA parity `.wasm`.
- **BE-02:** обобщить `scripts/be02_catalog_preflight.py` на все фазы (phase 1/3/4) через общий loader миграций. Прогон на Docker PG (фаза 8) и в kind (фаза 9) с замером lock budget и rollback.
- **O9:** подключить `scripts/quality/heartbeat_watchdog.py` к mutation jobs (stryker-shards, mutmut groups) как advisory, с contract-тестом и записью в каталог. Альтернатива — оформить существующую progress-диагностику как закрытие O9 решением в ADR, если watchdog дублирует её.
- **O1/O4/O5/O7/O8:** после 3 сопоставимых зелёных прогонов — `analyze_ci_critical_path.py` и `render_ci_health_report.py` по трём run-ам: p50/p95, critical path, overlap под cap 20. Сверка `quality/release-required-checks.json` с live ruleset (без изменения protection). Retry-классификация по каталогу.
- **A/B max-parallel** (6→7/8) — только после трёх зелёных, по одному варианту.
- **Security:** Semgrep, CodeQL, Checkov, Trivy, gitleaks, license, SBOM — 0 high/critical на финальном SHA.
- **Go и Rust полнота:** Go — 100% statements по контракту, `go test -race`, golangci-lint (контейнерный, GO-07); Go-мутации остаются advisory по ADR-038, но отчёт `go-mutation-diagnostic.yml` разбирается и попадает в аудит. Rust — llvm-cov line/function/branch 100% по четырём crate, `cargo deny`, bounded fuzz.
- **Strict typing тестовых фикстур:** 44 открытые ошибки strict mypy в `tests/conftest.py` — закрыть без suppression.

## Фаза 8 — Docker Core/full + SeaweedFS (≈2 дня, последовательно с 9)

1. Contract-тест `docker compose config --quiet` для всех поддерживаемых комбинаций: base; full; full+seaweedfs-cutover; full+live; base+go+observability; test; Core-подмножество. Расширить `tests/test_docker_startup_contracts.py` и шаг CI.
2. Backup `.env*` и томов в `../university_ecosystem_backups/<date>`. Затем `.\start-docker.ps1 -Core -Build` → full.
   - Замеры RAM/CPU/startup/readiness.
   - Health: `/health/ready`, SSR/Caddy, gRPC, WS, NATS, оба Redis.
   - Live-лейн фазы 5 против стека.
   - Корректный shutdown.
3. Grafana: provisioning дашбордов (`infrastructure/observability/grafana/dashboards/` + provider), перенести `docs/observability/grafana-dashboard.json`. Проверить, что метрики, логи и трейсы видны.
4. **Приоритет повышен 2026-09-28:** `quay.io/minio/minio` и `quay.io/minio/mc` отвечают 401 — MinIO больше не публикует образы. Базовые `docker-compose.yml`/`docker-compose.full.yml` не стартуют на чистой машине, Helm backup-cronjob (`backup.minioClientImage`) не скачает mc. Нужно: (а) base compose → SeaweedFS для новых установок; (б) backup-клиент → поддерживаемый S3 CLI (например, pinned `amazon/aws-cli` или `rclone`); (в) для чтения старого тома `university_ecosystem_minio-data` собрать MinIO из исходников по закреплённому тегу (AGPL-исходники на GitHub) только на время миграции. Live-стенд уже работает на SeaweedFS (`354f967a5`).
   SeaweedFS cutover строго по `docs/runbooks/s3-seaweedfs-cutover.md`: `s3_cutover_preflight.py inventory` → freeze → copy → `verify` → smoke (Put/Head/Get/Delete, presigned, private 403). Старый MinIO-том сохраняется; удаление — только с разрешения.
5. Новый `scripts/restore_db.py` (парный к `backup_db.py`) + `docs/runbooks/backup-restore.md`. Restore проверяется на live-стенде.

## Фаза 9 — Локальный kind prod-like (снимок, superseded)

- `deploy/kind/cluster.yaml` (single-node, 80/443 mappings, `ingress-ready`) и `scripts/local_k8s_prod_like.ps1` с командами `up | deploy | smoke | chaos | rollback | down`.
  - Инструменты kind/helm/kubectl/mkcert — пин-версии с checksum (постоянное разрешение).
  - Локальный registry, pod-ы ссылаются по digest (Kyverno policy 9).
- В историческом снимке указывался ingress-nginx. Это решение superseded; для MVP используется Envoy Gateway + Gateway API согласно мастер-плану. Сохраняются применимые критерии TLS, cert-manager + локальная CA, Kyverno, ExternalSecrets refresh, metrics-server/HPA, PG/Redis/NATS/SeaweedFS и observability.
- `charts/university-ecosystem/values-kind.yaml` без плейсхолдеров. Contract-тест: `helm template` + kubeconform для kind values в CI.
- Проверки:
  - `helm upgrade --install`, BE-02 preflight, smoke-сценарии live-лейна по TLS через Gateway API;
  - chaos: delete pod, restart NATS/Redis (манифесты `k8s/chaos/`);
  - `helm rollback` с доказательством сохранности данных;
  - teardown.
- Runbooks: `docs/runbooks/rollback.md`, `docs/runbooks/chaos.md`, `docs/runbooks/local-kind.md`.

## Фаза 10 — Шесть immutable-образов (≈1 день)

- Локально `docker buildx` шести образов (backend, frontend, ws-hub, gateway, file-processor, caddy): Trivy (0 high/critical), Syft SBOM, digests. Во frontend-образе — WASM byte-parity.
- Именно эти digests деплоятся в kind (фаза 9): один immutable build.
- Канонический `build-release-images.yml` (main-only) — после обычного merge release candidate; отдельное разрешение на запуск устарело и не требуется в пределах текущей пользовательской авторизации.

## Фаза 11 — Финальный аудит и документация (≈1 день)

- `docs/audits/AUDIT_QUALITY_CLOSURE_<sha>.md`:
  - identity (source, tested merge, run);
  - 100% coverage всех applicable метрик; mutation 100% viable (Stryker и mutmut, числа);
  - security; образы и digests; Docker/kind/SLO; классификация всех skip;
  - согласованные ограничения: CDC, нет реального staging, нет реальных устройств/field CWV, нет реальных SMTP/push.
- Пересмотр всех 63 ID внешнего аудита на финальном SHA (BE-02 и RUST-P3-03 — закрыть evidence-ом).
- `docs/audits/INDEX.md`, `AGENTS.md` §9 (активные аудиты), `docs/README.md`. STATUS → архив. markdownlint и link-check.
- Worktrees и stash — очистка по согласованному списку из фазы 2.

## Фаза 12 — Исторический merge/post-merge порядок (superseded)

Снимок требовал отдельного подтверждения для каждого merge и post-merge шага.
Это ожидание разрешения больше не действует: текущая пользовательская
авторизация на полный release cycle закреплена в мастер-плане. Указание на #1266
ниже — только завершённая историческая задача; не повторять её. Текущий порядок
merge, проверки итогового `main` SHA и выпуска образов см. в мастер-плане.

---

## Порядок и параллелизм

| День | Lead (ROOT) | Агенты A/B/C (worktrees) |
| --- | --- | --- |
| 1 | Ф0 (fix + push), Ф1 security-PR, Ф2 STATUS/память/инвентарь | — (ждут свежий инвентарь) |
| 2 | Ф0 инвентарь → очереди; Ф3.1 инструменты; Ф4 бампы | Волна 1 (auth/security) |
| 3–7 | Ф5 live-лейн, затем Ф6 приёмка; push раз в 1–2 дня | Волны 1–2 |
| 8–14 | Ф6 дефекты, Ф7 closure, Ф8 Docker | Волны 3–4 |
| 15–18 | Ф9 kind, Ф10 образы | Хвост, fresh CI, добивание |
| 19+ | 3 зелёных прогона → O1/O7 отчёты, Ф11 аудит → Ф12 (с разрешения) | — |

Оценка — 3–4 недели. Мутационная работа — критический путь. Docker, kind и образы требуют RAM и идут строго последовательно; во время них не запускаются тяжёлые локальные мутационные прогоны.

## Критичные файлы

| Область | Файлы |
| --- | --- |
| CI fix | `tests/test_workflow_fail_closed_contracts.py:1221`, `.github/workflows/ci.yml:1389-1411`, `quality/ci-check-catalog.json` |
| Мутации | `frontend/stryker.config.mjs`, `frontend/scripts/stryker-presentation-ignorer.mjs`, `pyproject.toml [tool.mutmut]`, `artifacts/quality/mutation-tools/*`, `quality/quality-contract.json` |
| Auth fork | `app/core/security*` (`_auth_executor`), auth reset service, `tests/` auth reset suites |
| Live-лейн | новые `docker-compose.live.yml`, `scripts/live_stand.py`, `frontend/playwright.live.config.ts`, `frontend/tests/e2e-live/`, `.github/workflows/live-e2e.yml`; переиспользовать `scripts/seed_admin_data.py`, `frontend/tests/e2e/utils/*`, `start-docker.ps1` |
| Инфра | `docker-compose*.yml`, `tests/test_docker_startup_contracts.py`, `scripts/be02_catalog_preflight.py`, `scripts/s3_cutover_preflight.py`, `scripts/backup_db.py` (+ новый restore), новые `deploy/kind/`, `scripts/local_k8s_prod_like.ps1`, `charts/university-ecosystem/values-kind.yaml` |
| Процесс | `docs/superpowers/plans/STATUS.md`, `docs/README.md`, `docs/audits/INDEX.md` |

## Verification

- **Per-slice:** RED → GREEN; focused coverage с `--cov-branch`; focused Stryker/mutmut файла — 0 survivors/timeouts; ruff, mypy, custom_ast_linter или tsc, eslint, prettier; pre-commit.
- **Per-push:** `fast_preflight.py` 9/9, `verify_harness.py`, `git diff --check`, восстановление WASM.
- **Per-CI:** terminal всех jobs; каждый skip доказан `if:`; aggregate `Frontend Mutation Evidence (100%)` и все mutmut groups success; manifest schema-valid; 0 high/critical.
- **Продукт:** live-лейн зелёный в RU и EN на 5 viewport-ах; mocked cross-browser зелёный; axe, LHCI, bundle, memory plateau в артефактах.
- **Инфра:** Docker Core/full health и live-лейн; kind — TLS smoke, chaos, rollback с сохранностью данных; 6 образов с Trivy 0 high/critical.
- **Итог:** финальный аудит привязан к одному verified SHA; цель завершена только после него и после разрешённого merge.

## Прогресс (2026-09-29)

Это устаревший progress snapshot. Текущее состояние, открытая работа и порядок продолжения находятся только в `STATUS.md` и мастер-плане.
