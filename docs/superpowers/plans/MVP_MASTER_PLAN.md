# MVP Master Plan — единый план, контекст и прогресс

Обновлён 2026-09-29 (вечер). Это главный документ по доведению проекта до
эталонного MVP: что нужно сделать, что уже сделано, в каком состоянии всё
находится и как продолжать. Короткий операционный срез — [STATUS.md](STATUS.md);
требования к продукту — [ТЗ MVP](University_Ecosystem_MVP.md).

**Утверждённый план (фазы 0–12, 6b, 6c) хранится вне репозитория:**
`C:\Users\egorribun\.claude\plans\cached-cuddling-ladybug.md`. Он остаётся
источником целей, порядка фаз, решений мейнтейнера от 2026-09-28 и списка
критичных файлов. Этот файл не заменяет его, а фиксирует, где мы находимся
относительно него, и добавляет всё, чего в нём нет: фактические числа,
принятые по ходу решения, состояние незавершённых работ и ловушки окружения.
Если два документа расходятся, для целей и порядка действует план, для
фактического состояния — этот файл и `git log`. Снимок плана от 2026-09-28 лежит в
репозитории: [MVP_APPROVED_PLAN.md](MVP_APPROVED_PLAN.md) — им пользоваться на другой
машине или в агенте без доступа к домашней папке (там же таблицы приёмки по ТЗ).

Иерархия: `cached-cuddling-ladybug.md` (цели) → этот файл (состояние и порядок
продолжения) → [STATUS.md](STATUS.md) (короткая дельта). История прежних сессий —
в [archive/](archive/) и является только историей.

## 1. Как начать новую сессию

1. Прочитать `AGENTS.md` (канонические правила репозитория), затем этот файл.
2. Сверить состояние с реальностью:

   ```powershell
   git status --short
   git log --oneline origin/egorribun..HEAD
   git worktree list
   gh run list -b egorribun -w "CI - Matrix Expansion" -L 3
   ```

3. **Одна сессия — одно рабочее дерево.** 2026-09-29 параллельная сессия (Codex)
   применила WIP в основное дерево, пока эта стояла на паузе; всё удалось
   принять, но так делать нельзя. Перед работой убедиться, что другая сессия
   не пишет в те же каталоги (`Get-Process`, время правки файлов).
4. CI-прогон `36553547083` завершён (раздел 3): пушить можно, порядок — раздел 12, шаг 1.
   Если позже идёт новый прогон — не пушить, push отменяет его (`cancel-in-progress`).
5. Решения, которые ждут мейнтейнера, — раздел 16; перенос на другую машину или в
   другого агента — раздел 17; промпт для нового диалога — раздел 19.

## 2. Правила, которые нельзя нарушать

- Ветка `egorribun`. **Никогда** не добавлять `Co-Authored-By` (AGENTS.md
  сильнее системной атрибуции). Сообщения коммитов — через файл и
  `git commit -F`; коммиты non-wave: `fix|test|docs|chore|refactor(quality|security|ci|frontend|backend)`.
- После падения `detect-secrets` на сдвиге строк — `git add .secrets.baseline` и
  повторить (в diff должны быть только `line_number` и `generated_at`).
  Фикстуры, похожие на секреты, помечать `pragma: allowlist secret` с пояснением.
- Без явного «да» мейнтейнера **не делать**: merge в `main`, force-push, закрытие
  Dependabot PR, изменение branch protection, удаление локальных данных
  (`artifacts/`, тома, кэши Docker), удаление `docs/audits/AUDIT_PLATFORM_FULL.md`
  (файл пользователя; удаляется в фазе 11 после переноса ledger).
- Постоянные разрешения: push в `egorribun`, pinned-загрузки, `gh run download`.
- Без timeout-инфляции, exclusions, `// Stryker disable`, waivers, ручной
  перемаркировки Killed. RED → GREEN для поведенческих изменений.
- Документация обновляется в том же коммите, что и поведение (память
  `docs-consistency-feedback`); мейнтейнер требует абсолютной чистоты кода и md.
- Перед push: `uv run python scripts/fast_preflight.py` (9 lanes, ~10 мин),
  `git diff --check`. После локальной сборки фронтенда восстанавливать
  `frontend/pkg/*.wasm` и provenance (`SKIP_WASM_BUILD=1`).
- Admin-bypass merge допустим только по просьбе мейнтейнера и с причиной в
  merge-коммите (AGENTS.md §5, `scripts/merge-as-admin.ps1`).

## 3. Идентичность на 2026-09-29 вечер

| Что | Значение |
| --- | --- |
| Ветка / PR | `egorribun` / #1266 → `main` (`be8c6a197`, влит merge-ем `dfbb6561f`) |
| `origin/egorribun` | `634412103` |
| Не запушено | все коммиты после `634412103` (`git log --oneline origin/egorribun..HEAD`); копия — git-bundle `../university_ecosystem_backups/2026-09-29/egorribun-unpushed-latest.bundle` |
| CI | Matrix `36553547083` на `634412103` **завершён, failure**: 207 job успешны, 13 пропущены, 96 упали — 93 группы mutmut, `Frontend Mutation Evidence (100%)`, `Incremental Mutation Tests (frontend)` и общий `CI Success`. Все немутационные проверки зелёные |
| PR #1266 | `CONFLICTING`: `main` ушёл на 6 коммитов вперёд (Dependabot: go, npm, detect-secrets; `3836ddcb0`). Пробное слияние `origin/main` в HEAD даёт один конфликт — `frontend/package-lock.json` (решать пересборкой lock из `package.json`) |
| Что в PR | только запушенное (`634412103`): в нём нет SeaweedFS по умолчанию, knip-гейта, удаления SPIFFE и мёртвого кода — они в локальных коммитах |
| Дерево | чистое; untracked только `docs/audits/AUDIT_PLATFORM_FULL.md` (не трогать) |
| Машина | Windows 11, 16 логических CPU, 15.3 ГБ RAM; при 4–5 агентах свободно ≈1.7 ГБ |

## 4. Состояние фаз относительно утверждённого плана

| Фаза | Суть | Статус | Основание и остаток |
| --- | --- | --- | --- |
| Ф0 | Разблокировать CI, свежий инвентарь | **сделано** | O9-шаги в `expected_steps`; фронтенд-инвентарь по run `36443355112` (5 511 открытых); backend-сводка по run `36553547083` (250 непобеждённых); mutmut-песочница чинена (`862eeb7cd`) |
| Ф1 | Security-PR в `main` | **сделано** | #1296 смержен 2026-09-28 (admin bypass); undici в корневом lock обновлён (`37976de9f`) |
| Ф2 | Гигиена процесса | **сделано** | STATUS, архив планов, память, worktree/stash разобраны; дальше — раздел 9 |
| Ф3 | Мутации до 100% viable | **в работе** | frontend волна 1 влита без Stryker-подтверждения; backend 250 мутантов — WIP агентов сохранён патчами; волны 2–4 не начаты (раздел 5) |
| Ф4 | Бампы Dependabot | **сделано** | #1292–#1295, #1298 в ветке; #1297 закрыт; mutmut 3.8 уже в `pyproject` |
| Ф5 | Живой лейн приёмки | **частично** | конфиг, фикстуры, два спека, стенд с Mailpit/VAPID/SeaweedFS есть; `password-reset` спек не запускался; CI-workflow `live-e2e.yml`, перенос никогда не запускавшихся спеков, Linux visual-baselines — нет (раздел 6) |
| Ф6 | Продуктовая приёмка по ТЗ | не начато | зависит от Ф5 |
| Ф6b | Дизайн-ревью | не начато | побочно закрыт дефект окраски индикатора пароля в `ResetPassword` |
| Ф6c | Чистота и демо-готовность | **в основном сделано** | мёртвые файлы, зависимости (deptry, knip), аудит md, SPIFFE, O9; осталось: удаление санитайзера (WIP), Go `staticcheck`, демо-данные, нагрузка ws-hub, security- и code-review ветки |
| Ф6d | Полный аудит мёртвого груза, лишнего кода и устаревшей документации | **не начато, добавлено 2026-09-29** | программа — раздел 14; отчёт `docs/audits/DEAD_WEIGHT_AUDIT_<дата>.md`, удаления отдельными коммитами |
| Ф7 | Остальная quality closure | частично | Rust запинен на 1.97.1 в `ci.yml`, `chromatic.yml`, `admin-smoke-monitoring.yml`, но `benchmark.yml` ещё использует `stable`; O9 закрыт (ADR-045); spelling RU, zero-warning build, BE-02 на все фазы, O1–O8, strict-типизация фикстур — нет |
| Ф8 | Docker Core/full + SeaweedFS | **частично** | SeaweedFS по умолчанию влит (`cc4ebec11`, ADR-042), Helm backup на rclone (`ee90ce97e`); осталось: реальный `up` на чистой машине, метрики SeaweedFS, Grafana provisioning, `restore_db.py` + runbook, `config --quiet` по всем комбинациям, замеры |
| Ф9 | Локальный kind | не начато | |
| Ф10 | Шесть immutable-образов | не начато | Trivy, `.trivyignore` просрочен (ревью до 2026-09-14) |
| Ф11 | Финальный аудит | не начато | включает удаление `AUDIT_PLATFORM_FULL.md` после переноса ledger |
| Ф12 | Merge #1266 и post-merge | не начато | каждый шаг — только с явного «да» |

## 5. Мутационный долг (Ф3)

### 5.1 Frontend

- Инвентарь run `36443355112` (`a4caec3bf`, 2026-09-28): 35 959 killed, 1 306
  ignored (ADR-040), **5 511 открыто** в 269 файлах (5 431 survived, 36
  timeout, 33 runtime error, 11 no coverage). По каталогам: hooks 1 491,
  features 1 286, pages 1 242, components 835, sw 132, contexts 127, push 116.
  Крупнейшие: `useMessengerController` 288, `StoriesAdmin` 142, `Schedule`
  138, `NewsDetail` 131, `useNewsInteraction` 121, `ResetPassword` 115,
  `AdminNotificationsFeature` 92.
- Файлы и срезы очередей: игнорируемый `artifacts/quality/inventory-a4caec3bf/`
  (`frontend-inventory.json`, `queue-w1-auth.json`, `queue-w1-push.json`).
- **Волна 1 влита** (`4b9e4a13d`): `ResetPassword`, `Register`, `ForgotPassword`,
  `useLoginFlow` (тесты), `ssrAuth`, `subscribe`, `usePushPreferences`,
  `useDndSettings`. Полный vitest (712 файлов, 8 205 тестов), typecheck, ESLint,
  Prettier зелёные. **Канонический focused Stryker по этим файлам не запущен** —
  коммит не заявляет 100%. `useAuthApi` (46 мутантов) не начат.
- После этого убраны мёртвые экспорты (`1c40a4b54`), поэтому инвентарь
  устарел по файлам: после terminal-прогона пересобрать.
- Порядок дальше: волна 1 (подтвердить Stryker) → волна 2 messenger/realtime
  (`useMessengerController`, `useChatWebSocket`) → волна 3 файлы ≥50 → волна 4 хвост.
- Шаблон работы над файлом — в плане, §3.3: поведенческий мутант → тест;
  эквивалентный → упростить код; presentation → ADR-040; timeout → устранить причину.

### 5.2 Backend

Источник: `artifacts/wip/2026-09-29/mutmut-36553547083-consolidated-evidence.json`
(SHA256 `638A83E7B9ECA71BB2D77A856315E48B70D6FEA504F8FEA7A08D2CB395A41CC6`).
3 124 мутанта: 2 874 killed, **248 survived, 2 timeout**, 0 no-coverage,
0 runtime error, 128 групп, доказательства исполнения полные.

| Файл | Непобеждённых |
| --- | --- |
| `app/core/lifespan.py` | 51 (`_handle_schema_and_extensions` 31, `_startup_background_workers` 16, `_shutdown_subsystems` 4) |
| `app/services/auth_service.py` | 50 (`perform_password_reset` 44) |
| `app/services/chat/command_service.py` | 36 (`forward_messages`) |
| `app/core/db/schema_drift.py` | 29 (модуль перенесён в `app/`, попал в scope) |
| `app/auth/mfa/totp.py` | 17 |
| `mfa_coordinator.py`, `session_service.py` | по 11 |
| `app/auth/mfa/challenge.py` | 9 |
| `notifications/delivery.py` | 7 |
| `app/core/events.py` (`from_dict`), `user_repository.py`, `attachment_service.py` | 5, 4, 4 |
| `deps/auth.py`, `auth_repository.py` | по 3 |
| `jwt_settings.py`, `core/static.py` (2 таймаута), `storage.py`, `email_otp.py` | по 2 |
| `internal_access.py`, `session_cleanup.py` | по 1 |

Группы агентов (остановлены; патчи сохранены, раздел 10): auth/MFA (≈110),
lifespan + schema_drift + user_repository (≈84), chat + notifications + events +
static + storage (≈56). `auth reset timeouts` из старого списка исчезли после
fork-фикса `_auth_executor` (`da30b91f7`).

Инструменты (игнорируемые, `artifacts/quality/mutation-tools/`): `build_inventory.py`,
`queue_slice.py`, `fresh_mutants.mjs`, `mutant_check_fast.mjs` (фронтенд);
`mm_check.py diff|check` и `mm_loop.py --file … --tests … --all` (backend; python
главного `.venv` из корня worktree, работают на Windows). Они подменяют функцию
в исходнике и восстанавливают из `mutant-backups/`; после любого обрыва проверять
`git diff -- app/` — 2026-09-29 так восстановлен `user_repository.py` в `ue-b2`.

## 6. Живой стенд и live-лейн (Ф5)

- Стенд: `scripts/live_stand.py up|seed|status|down`; отдельный worktree
  `../ue-live` (сейчас на `06b8d85d5`, **устарел**), Compose-проект `ue-live`,
  overlay `docker-compose.live.yml` (Mailpit v1.31.1, VAPID из `.secrets/live-vapid.json`).
  Контейнеры остановлены, тома `ue-live_*` сохранены. Нужны порты 80/443.
  Пересборка на текущем HEAD: `uv run python scripts/live_stand.py up` (после
  влития SeaweedFS-по-умолчанию overlay больше не переопределяет хранилище).
- Live-спеки: `cd frontend; npm run test:e2e:live` (desktop 1440×900 и mobile
  Pixel 7, `workers: 1`). `auth-roles.live.spec.ts` (5 тестов; admin-тест требует
  стенда с исправлением `list_users`, `25c7fd5b3`); `password-reset.live.spec.ts`
  (регистрация → письмо в Mailpit → сброс → вход → повтор ссылки) **ещё не запускался**.
- Фикстуры `frontend/tests/e2e-live/fixtures.ts`: `loginAs/loginWith/submitLogin`,
  `awaitMail`, `freshPassword`, `stubBreachedPasswordLookup`.
- Найдено стендом и исправлено: образ миграций без `scripts/` (перенос в
  `app/core/db/schema_drift.py`), пропадание пользователей со статусом NULL
  (`list_users`), непереведённые строки data-table, битые Docker-сборки
  file-processor и caddy.
- Осталось по плану: email OTP через Mailpit, TOTP, messenger WS между двумя
  контекстами, Web Push с локальным VAPID, admin-страницы, i18n-обход, workflow
  `live-e2e.yml`, перенос `chat-realtime`, `chat_workflow`, `group_management`,
  `a11y-messenger`, Linux visual-baselines.
- Мелочи: дубли заголовков `Cache-Control`/`Service-Worker-Allowed` на `/sw.js`;
  ошибка регистрации SW видна только во встроенной панели браузера.

## 7. Хранилище и инфраструктура (Ф8)

- MinIO больше не публикует образы (`quay.io/minio/*` отвечает 401). Базовые
  `docker-compose.yml` и `docker-compose.full.yml` теперь запускают SeaweedFS 4.47
  (digest `ce9e796f…`) под прежним DNS-именем `minio`; `minio-init` только ждёт S3.
  Фиксированное имя проекта `university_ecosystem` в базовых файлах стабилизирует
  имя тома; `COMPOSE_PROJECT_NAME`/`-p` его переопределяют (так стенд получает
  изолированный том). **Побочный эффект:** запуск из клона в другой папке попадает
  в тот же проект.
- Охрана легаси-тома: `start-docker.ps1`, `scripts/dc.ps1`, `scripts/dc.sh` отказывают
  при наличии `<project>_minio-data` / `_minio_data`, пока нет файла-аттестации
  `.secrets/s3-cutover-attestation.txt` (проект, исходные тома, целевой том).
  Ошибка чтения списка томов — тоже отказ. Runbook — `docs/runbooks/s3-seaweedfs-cutover.md`.
- Легаси-том `university_ecosystem_minio-data` пуст (148 КБ метаданных, бакет
  `uploads` без объектов) — миграция данных не нужна; том не трогать. Образ MinIO
  сохранён: `local/minio-legacy:RELEASE.2025-09-07T16-13-09Z`, tar в
  `../university_ecosystem_backups/2026-09-29/` (SHA256
  `C8C5A4A580EF4E1853CDB9B531F7A1CE350CCF109D7925D0464295C4C615B530`).
- Helm backup: `mc` заменён на rclone 1.75.1 по digest, ключ `backup.s3ClientImage`,
  проверено вживую на SeaweedFS (UID 1000, read-only rootfs).
- Открыто: метрики SeaweedFS для Prometheus (`-metricsPort` ломал S3 при первой
  попытке — перепроверить), Grafana provisioning, `scripts/restore_db.py` + runbook,
  проверка `docker compose config --quiet` по всем комбинациям (полная
  observability-комбинация в одиночку падает на сети `cache_net` — overlay
  рассчитан на базовый файл), реальный `docker compose up` на чистой машине и замеры.

## 8. Качество кода и зависимостей — что сделано

- **Python.** `deptry app` — CI-гейт (`backend-type-check`): удалены `pyasn1`,
  `pyopenssl`, `filelock`; `geoip2` заменён на `maxminddb`; `h2`/`urllib3` стали
  `constraint-dependencies`; объявлены `botocore`, `rich`; мёртвая ветка `msgspec`
  удалена. `mypy` — без ошибок.
- **Frontend.** knip 6.37.0 (`npm run lint:knip`) — единственный fail-closed гейт
  вместо декоративных `ts-prune` (всегда exit 0) и depcheck; `treatConfigHintsAsErrors`.
  Удалено 10 неиспользуемых пакетов, объявлено 8 импортируемых, убрано 67 мёртвых
  экспортов, 54 дубля и 6 пустых barrel-ов. `lint-staged --max-arg-length 6000`
  (иначе на Windows `eslint` на ~150 файлах падает по лимиту `cmd.exe`).
- **Go.** `go mod tidy -diff` чист по 8 модулям (`gen/go` исправлен), `make go-test`
  гоняет все 7 модулей CI.
- **Документация.** Аудит 77 авторских md (ссылки, якоря, идентификаторы, эндпоинты),
  `tests/test_markdown_links.py`; удалены `PROJECT.md`, `TEST_INFRA.md`,
  `TEST_READY.md`, `docs/mcp/`, `.opencode/`, `docs/CHANGELOG.md`,
  `scripts/loadtesting/`, `frontend/TOKENS.md` и мёртвые конфиги/скрипты.
- **Решения, принятые мной по делегированию мейнтейнера (2026-09-29):**
  SPIFFE в Python удалён (`7c6b8faee`, ADR-043: пакета `pyspiffe` нет на PyPI, по
  умолчанию выключено); нативный санитайзер `pyo3-sanitizer` и
  `content_processing.py` признаны неиспользуемыми, удаление в работе (WIP, ADR-044
  зарезервирован); O9 закрыт диагностикой прогресса, watchdog удалён (ADR-045).
- **Прочие ADR:** ADR-042 SeaweedFS по умолчанию; ADR-040/041 из прежних сессий.

## 9. Открытый бэклог чистоты и качества

- Go `staticcheck` (unused) по модулям; при необходимости — правки.
- Демо-данные для первой демонстрации (`live_stand.py seed --demo`), нагрузка ws-hub
  (`run_chaos_loadtest.py`), security-review и code-review всего diff `main...egorribun`.
- Бэклог из ревью: module-level executor-ы в `analytics` и `minio_storage`
  (класс fork-дефекта, сейчас недостижим), кэши по `id(loop)` → `WeakKeyDictionary`,
  глобальный `_push_semaphore` в `webpush`; пользователь может задать статус
  «deleted» и исчезнуть из списков (`list_users`).
- `.trivyignore`: срок пересмотра истёк 2026-09-14 — сверить со свежим Trivy (Ф10).
- Полная программа аудита мёртвого груза — раздел 14 (Ф6d); здесь остаётся то, что уже известно.
- Локальные данные, предложить мейнтейнеру на удаление (ничего не удалять без «да»):
  `artifacts/` (>1 ГБ), локальная `.superpowers/`, ≈10 ГБ кэша сборки Docker, тома
  `ue-live_*`, worktree агентов после переноса, `artifacts/wip/*`.
- Ф7: spelling RU (`@cspell/dict-ru_ru` dev-only), zero-warning build, BE-02 на все
  фазы, O1–O8 (нужны три сопоставимых зелёных прогона), strict mypy тестовых
  фикстур (44 ошибки в `tests/conftest.py`).

## 10. Незавершённые работы, worktree и патчи

Патчи лежат в игнорируемом `artifacts/wip/2026-09-29/`. Worktree создаются от HEAD
и служат площадкой агента; при потере восстановить командой
`git worktree add --detach ../<имя> <sha>` и `git apply --3way <patch>`.

| Worktree | Назначение | Состояние | Патч |
| --- | --- | --- | --- |
| `../ue-b1` | backend auth/MFA мутанты | только тесты (11 файлов, +934), production не менялся; проверки не завершены | `ue-b1-wip.patch` |
| `../ue-b2` | lifespan, schema_drift, user_repository | 5 файлов; правки production минимальны (`schema_drift.py`, `user_repository.py`) | `ue-b2-wip.patch` |
| `../ue-b3` | chat forward, delivery, events, static, storage | 10 файлов, +213/−21 | `ue-b3-wip.patch` |
| `../ue-s2` | удаление нативного санитайзера и его CI-конвейера | 64 файла, −4 314 строк; не проверено, ADR-044 может отсутствовать | `ue-s2-wip.patch` |
| `../ue-live` | стенд | устарел (`06b8d85d5`), контейнеры остановлены | — |
| `../ue-s1` | удаление Python-SPIFFE | влито (`7c6b8faee`), worktree удалён | — |
| `~/.codex/worktrees/dependabot-1304` | чужой worktree Dependabot | не трогать | — |

Прочие страховки: `main-tree-18-11-full.patch` (дерево на момент записи параллельной
сессией), `staged-dead-exports.patch`, `ue-w1/ue-w2-superseded.patch`,
`ue-knip-exports.patch`, `mutmut-…-consolidated-evidence.json`.
Правила агентов: в своём worktree, без commit/push, RED → GREEN, эквивалентные
мутанты убираются упрощением, без exclusions; production-изменения в auth — только
с независимым security-ревью lead-а; результаты переносятся патчем и проверяются
тестами, покрытием (100% line+branch затронутого модуля), ruff, mypy, deptry.

## 11. Ловушки окружения (проверено на практике)

- PowerShell режет аргумент `-s3.port=9000` по точке — брать в кавычки; `$var:` в
  строках ломает парсинг — писать `${var}:`.
- `Path.write_text` на Windows пишет CRLF; писать байтами/`newline="\n"`. Репозиторий — LF.
- Harness блокирует команды с путём `/tmp` в некоторых позициях — выносить в `.ps1`
  в scratchpad.
- `git stash` с intent-to-add файлом падает (`not uptodate`); `go work sync` меняет
  `go.work` и `go.mod` соседних модулей — не запускать.
- `npm` в проекте под карантином 7 дней: `knip@6.38.0` недоступен, брать `6.37.0`.
- `glob` в `frontend/package.json` должен быть ровно `13.0.6` (как в `overrides`),
  иначе `EOVERRIDE`.
- Время: `Get-Date -Format u` печатает локальное время с суффиксом `Z` — для UTC
  использовать `(Get-Date).ToUniversalTime()`.
- Pre-commit `lint-staged` при сбое может оставить дерево в смешанном состоянии;
  восстановление: `git restore --worktree -- <путь>` из индекса, удалить
  воскресшие неотслеживаемые копии удалённых файлов.
- Vitest исключает `tests/e2e/**` и `tests/e2e-live/**`; mutmut копирует только
  `also_copy`: новые корневые `docker-compose*.yml` обязаны попасть туда (контракт).

## 12. Порядок продолжения

1. **Слияние `main` и push.** CI `36553547083` завершён. Слить `origin/main` в ветку
   (`git merge origin/main`), конфликт в `frontend/package-lock.json` решить пересборкой
   (`npm install --package-lock-only --prefix frontend`, затем проверить `npm ci` и
   `npm run lint:knip`), убедиться, что версии Go-модулей из `main` не откатились
   (`go mod tidy -diff` по 8 модулям), прогнать `scripts/fast_preflight.py` и запушить
   одним push (запустится новый полный прогон ≈20 ч). Классификация красных job уже
   известна: все — мутационные гейты (раздел 3). Для свежего инвентаря скачать
   артефакты: `gh run download 36553547083 -D artifacts/quality/inventory-634412103 -p 'frontend-mutation-shard-*'`,
   `uv run python artifacts/quality/mutation-tools/build_inventory.py <dir>`.
2. **Приёмка WIP агентов** (раздел 10): для `ue-s2` — доделать удаление санитайзера
   (ADR-044, uv.lock, workflows, контракты, полный набор тестов); для `ue-b1..b3` —
   доделать мутанты, сверить `git diff` каждого worktree, security-ревью
   production-изменений auth, перенос патчем, тесты и покрытие, коммиты
   `test(quality): close … mutation survivors`.
3. **Focused Stryker волны 1** (`$env:STRYKER_LOCAL_MUTATE_JSON='["src/<файл>"]'; npm run test:mutation`)
   по восьми файлам; затем волны 2–4.
4. **Стенд.** Пересобрать `ue-live` на текущем HEAD, прогнать оба live-спека на
   desktop и mobile, реальный `docker compose up` на SeaweedFS.
5. **Решение по политике мутаций** (раздел 15, **[да]**) и старт **Ф6d** (раздел 14): аудит мёртвого груза, отчёт, удаления отдельными коммитами.
6. **Ф8:** метрики SeaweedFS, Grafana provisioning, `restore_db.py`, `config --quiet`
   по комбинациям, замеры. **Ф5/Ф6:** остальные live-спеки и workflow.
7. **Ф6c/Ф7:** Go `staticcheck`, демо-данные, нагрузка ws-hub, spelling RU, review ветки.
8. **Ф9–Ф12** — по плану; merge и post-merge только с явного «да».

## 13. Слабые места проекта (оценка 2026-09-29)

Оценка сделана по коду, CI и аудитам; продукт живьём и на реальных пользователях не
проверялся. Каждое слабое место привязано к работе, которая его закрывает.

| # | Слабое место | Чем подтверждено | Что делаем |
| --- | --- | --- | --- |
| 1 | Проверочной оснастки больше, чем проверенного продукта | приёмка на моках (45 Playwright-спеков через `page.route`); живой лейн появился только 2026-09-28; базовый стек не стартовал на чистой машине (пропали образы MinIO), а образ миграций с 2026-08 не содержал `scripts/` | Ф5, Ф6, Ф8 идут раньше дальнейшей мутационной работы: реальный `docker compose up` на чистой машине и живая приёмка по ТЗ |
| 2 | Мёртвый груз и «декоративные» механизмы | Python-SPIFFE, который не мог работать; нативный санитайзер с собственным fuzz/ASan/TSan-конвейером, не используемый приложением; гейты, которые не могли упасть (`ts-prune` всегда exit 0, depcheck скрывал находки); дубль каталога навыков на 415 файлов; разовые скрипты | Ф6d (раздел 14) и правило: у каждого гейта доказан путь отказа |
| 3 | Риск интеграции | ветка ≈900 коммитов впереди `main` в одном PR #1266; CI `main` давно красный; полный прогон ≈20 часов | определить «готово» (раздел 15), сократить число push, после слияния работать малыми PR |
| 4 | Единственный мейнтейнер | admin bypass признан нормой в AGENTS.md | зафиксировать процесс, по возможности второй ревьюер и CODEOWNERS, сократить потребность в bypass |
| 5 | История «волн» в коде и документах | 3 940 меток вида «Wave NNN»/`W123` вне аудитов (frontend 2 451, app 659, tests 219, .github 201, services 159, compose 114); 112 архивных отчётов | политика в разделе 14 (K) |
| 6 | Тесты, порождённые метрикой, а не поведением | из 1 553 тест-файлов около 450 названы по метрике: `closure` 267, `coverage` 70, `mutation` 70, `mutation-contract` 39, `branches` 21, `survivor` 11 | оценить сигнал и стоимость, склеить дубли; удалять только с доказательством эквивалентного покрытия |
| 7 | Хрупкость цепочки поставок | закрепление по digest не спасло от исчезновения образов MinIO | плановая проверка, что все закреплённые образы скачиваются; правило замены (раздел 14, G) |
| 8 | Не проверено главное | соответствие ТЗ, дизайн-качество, нагрузка, реальные устройства | Ф6, Ф6b, Ф6c |
| 9 | Разработка на Windows, хрупкие инструменты | lint-staged и лимит `cmd.exe`, CRLF, mutmut, время в PowerShell | ловушки в разделе 11; источник истины — Linux-CI |
| 10 | Вес процесса | прежний handoff 1 591 строка, continuation 8 809; 56 workflows, 103 скрипта, 18 файлов `quality/*.json` | лимит STATUS ≤150 строк, реестр ценности проверок (раздел 14, M) |
| 11 | Медленная обратная связь CI | полный прогон ≈20 часов, push отменяет прогон | локальный быстрый цикл, редкие push; решить, нужна ли полная матрица на каждый push (раздел 15) |

## 14. Программа аудита мёртвого груза и засорения (Ф6d)

Цель — чтобы в репозитории не оставалось того, что не используется, не проверяется
и не описывает реальность. Замеры 2026-09-29: 4 596 отслеживаемых файла, 45 МБ
файлов, pack `.git` ≈200 МиБ; frontend 1 831 файл, tests 878, app 489, `.agents` 427,
services 211, docs 187, alembic 138, scripts 103, workflows 56.

**Правила удаления.** Удаляется только то, на что `git grep` не находит ссылок вне
самого удаляемого и вне тестов, проверяющих именно его. После удаления зелёные
контрактные тесты, линтеры и релевантный набор тестов. Один логический блок — один
коммит, чтобы откат был точечным. Спорное, необратимое для пользователя и всё, что
меняет политику, — только с «да» мейнтейнера (пометка **[да]**). Результат — один
отчёт `docs/audits/DEAD_WEIGHT_AUDIT_<дата>.md` со списком найденного, удалённого и
оставленного с причиной.

**Программа** (инструменты — read-only, запускать в изолированном worktree):

- **A. Python.** `uvx vulture app --min-confidence 80` для неиспользуемых функций и
  классов; поиск модулей, которые импортируются только тестами (так найден
  `content_processing.py`) по всем `app/`; `deptry` (уже гейт); функции, покрытые
  только тестами и недостижимые от точек входа (роутеры, воркеры, CLI, lifespan).
- **B. Поверхность API.** Сверить маршруты OpenAPI с вызовами во frontend, Go и
  документацией; операции сгенерированного SDK без потребителей (в knip они
  игнорируются, их более 80) — решить, урезать ли генерацию; маршруты без клиента и
  без причины существовать.
- **C. База данных.** Таблицы, столбцы и индексы без использования в коде; ветви
  миграций (138 файлов) — только отчёт; сжатие истории миграций — отдельное решение
  по ADR-036 **[да]**.
- **D. Frontend.** knip (уже гейт); токены дизайна без потребителей (631 переменная,
  `sync-tokens`); ключи i18n, которых нет в коде (обратная проверка к сканеру
  статических ключей); ассеты в `public/` и `src/assets`; stories и моки удалённых
  компонентов; сгенерированные MSW-обработчики (0.42 МБ); снапшоты Playwright только
  под win32 (2.8 МБ PNG) — заменить Linux-baselines из Ф5, потом удалить Windows-версии.
- **E. Go.** `staticcheck -checks U1000`, `deadcode` из `golang.org/x/tools`,
  `go mod tidy -diff` (уже чист), неиспользуемые пакеты и Dockerfile.
- **F. Rust.** `cargo udeps` (есть в CI) и `cargo machete`; неиспользуемые крейты и
  fuzz-цели; функции `native/rust_ext`, которые не вызываются из Python.
- **G. Инфраструктура и конфигурация.** Перекрёстная проверка переменных окружения
  (поля настроек ↔ `.env.example` ↔ Compose ↔ Helm values ↔ документация): написать
  `scripts/quality/check_settings_usage.py`; сервисы и профили Compose, которые не
  запускает ни один скрипт и тест; ключи Helm values без использования в шаблонах;
  манифесты `k8s/` вне kustomization, тестов и документации; дашборды и алерты,
  ссылающиеся на несуществующие метрики (например, на MinIO); workflow без запусков
  за 90 дней и дублирующие друг друга (`gh api` по истории запусков); проверка, что
  все закреплённые образы скачиваются (плановый workflow или проверка в CI).
- **H. Данные качества и списки исключений.** Записи `quality/*.json`,
  `test-durations.json`, `.secrets.baseline`, `cspell.json`, `renovate.json`,
  `codecov.yml`, `CODEOWNERS`, `.gitignore`, `.dockerignore` про несуществующие
  файлы и пакеты; сделать это контрактным тестом «каждая ссылка указывает на
  существующий путь».
- **I. Тесты.** Инвентарь skip/xfail, тесты удалённого кода, дубли между
  `*closure*`, `*mutation*`, `*coverage*`, `*branches*`, `*survivor*` файлами
  (≈450); медленные тесты; тесты с «волновыми» именами. Цель — тот же уровень
  проверки при меньшем числе файлов; без доказательства (покрытие и мутации того же
  модуля не хуже) не удалять.
- **J. Документация.** Авторские md (77) уже проверены. Остаётся: 112 архивных
  отчётов `docs/audits/archive` и два больших файла `docs/superpowers/plans/archive`
  (≈0.9 МБ) — предложение: оставить `docs/audits/INDEX.md` и текущий референсный
  набор, остальное убрать из дерева (история сохранится в git и в тегах) **[да]**;
  каталог `.agents/skills` (154 навыка, 415 файлов) — оставить только используемые
  AGENTS.md, хуками и субагентами **[да]**; решить, относится ли harness `.agents/`
  (хуки, субагенты, `verify_harness.py`) к продукту или к личному инструментарию **[да]**.
- **K. Метки истории в коде.** Массовая правка 3 940 меток одним коммитом
  недопустима (разрастание диффа, blame, базовые линии мутаций). Политика: добавить
  линтер, запрещающий новые метки «Wave NNN» вне `docs/audits`; существующие убирать
  по каталогам после стабилизации мутационных базовых линий, скриптовым и
  проверяемым преобразованием, только комментарии **[да]**.
- **L. Вес репозитория.** Крупнейшие файлы и дубликаты (две копии OpenAPI:
  `frontend/openapi.json` и `tests/contracts/snapshots/api_openapi_v1.json` — сверить),
  сгенерированное в дереве; замер до и после.
- **M. Ценность процессной оснастки.** Для каждого из 56 workflows и проверок из
  `quality/ci-check-catalog.json` записать: назначение, стоимость (минуты), когда
  последний раз поймало настоящий дефект (история запусков и коммитов), владельца.
  Кандидаты на удаление — дорогие проверки без единой находки и дубли. Итог —
  реестр ценности проверок в `docs/testing/`.
- **N. Поставка.** Отчёт аудита; коммиты удалений по блокам; обновлённые гейты
  (там, где можно закрепить результат, как сделано для knip и deptry); обновление
  STATUS и этого плана.

Оценка: 3–4 рабочих дня, из них A–H, L — в основном автоматические, I, J, K, M —
требуют решений.

## 15. Сроки и вклад мутационных тестов

Оценка от 2026-09-29, грубая (±30%): темп мутационной работы измерен плохо, а объём
работы Ф5–Ф10 зависит от найденных дефектов. Первоначальная оценка плана в 3–4
недели с учётом фактов двух дней и добавленной Ф6d стала оптимистичной.

**Что остаётся мутационного.** Frontend ≈5 000 открытых мутантов (5 511 минус
волна 1), backend 250. По плану 3 агента дают 300–500 закрытых мутантов в день, то
есть 10–17 рабочих дней агентской работы для frontend плюс приёмка lead-ом
(≈20% времени) и подтверждение в CI: полный прогон длится ≈20 часов, значит каждый
цикл «правка → канонический пересчёт» стоит календарные сутки.

**Что остаётся не мутационного (цепочка lead-а).** Ф5 остаток 2–3 дня, Ф6 4–6, Ф6b
2–3, Ф6c и Ф6d 4–6, Ф7 2–3, Ф8 остаток 1–2, Ф9 3, Ф10 1, Ф11 1, Ф12 0.5 — итого
20–29 рабочих дней (4–6 недель).

**Почему мутации не идут «бесплатно» параллельно.** Агенты работают в фоне, но
делят с Docker-фазами одну машину (15 ГБ ОЗУ): два Stryker-агента занимают 5–6 ГБ,
стенд и kind — 6–8 ГБ. План сам требует не запускать тяжёлые мутационные прогоны во
время Docker, kind и сборки образов (Ф5, Ф8, Ф9, Ф10 ≈ 7–10 дней). Поэтому
пересекается лишь примерно половина мутационной работы, остальное добавляется к
календарю: +8–14 рабочих дней.

| Сценарий | Определение «готово» | Оценка до безупречного MVP |
| --- | --- | --- |
| A. Как сейчас | 100% viable мутантов везде | 6–9 недель |
| B. Гибрид (рекомендую) | 100% для backend (250) и security/auth/data во frontend (волна 1, admin, push, сессии, ≈1 000 мутантов); для остального frontend — порог, например ≥85% (сейчас ≈87%: 35 959 killed при 5 511 открытых) | 4.5–6.5 недель |
| C. Отложить все мутации | мутации вне критического пути, порог не гейтит | 4–6 недель |

**Выигрыш от отложения: примерно 2–3 недели (≈30–35%) для сценария C и 1.5–2.5
недели для B.** Важное условие: выигрыш реален только если поменять определение
«готово». Сейчас обязательная проверка `Frontend Mutation Evidence (100%)` должна
быть зелёной на финальном SHA; если её не менять, отложенные мутации просто
превратятся в красный CI в конце (или в merge через bypass, который мы хотим
сократить). Смена политики — это ADR (риск-ориентированная политика мутаций),
правка `quality/release-required-checks.json` и контрактных тестов, ≈1 рабочий день.
Backend-хвост (250) и security-код стоит закрыть в любом случае: он маленький и
именно там мутации ловят реальные дефекты (уже поймали fork-зависание executor).
Решение о политике — за мейнтейнером **[да]**.

## 16. Решения, ожидающие мейнтейнера

Автономный агент не останавливается на этих пунктах: он продолжает всё, что решения не
требует, а сам вопрос выносит мейнтейнеру с рекомендацией. Без явного «да» пункты **не
выполняются**.

| # | Решение | Рекомендация | Где подробности |
| --- | --- | --- | --- |
| 1 | Политика мутаций: 100% везде, гибрид или отложить | гибрид: 100% для backend и security/auth/data, порог ≈85% для остального frontend (сейчас ≈87%) | раздел 15 |
| 2 | Слияние PR #1266 в `main`: через admin bypass с записанной причиной или после смены политики | сначала слить `main` в ветку и запушить все коммиты; затем выбрать по срочности | раздел 3, 15 |
| 3 | Ф6d: удалить 112 архивных отчётов аудита, ужать каталог навыков (154), решить судьбу harness `.agents/`, сжатие миграций | удалить архив отчётов (история в git), оставить только используемые навыки | раздел 14 (J, C) |
| 4 | Ф6d: политика по 3 940 меткам «Wave NNN» в коде | запретить новые линтером, старые убирать скриптом по каталогам позже | раздел 14 (K) |
| 5 | Удаление локальных данных: `artifacts/` (>1 ГБ), кэш Docker ≈10 ГБ, тома `ue-live_*`, `artifacts/wip/*` | предложить список после переезда | раздел 9 |
| 6 | Закрытие Dependabot PR как superseded, `build-release-images.yml`, любые публичные действия | только после слияния | Ф12 плана |
| 7 | Удаление `docs/audits/AUDIT_PLATFORM_FULL.md` | Ф11, после переноса ledger (открыты BE-02 и RUST-P3-03) | раздел 2 |

## 17. Перенос на другую машину или другому агенту

Git увозит только отслеженное. Для переезда:

1. Запушить ветку (раздел 12, шаг 1). Копия неотправленных коммитов лежит в bundle
   (раздел 3) — на случай, если push не удался.
2. Скопировать вручную, защищённым способом: `.env`, `.env.docker`, `.secrets/` (не
   через git); `docs/audits/AUDIT_PLATFORM_FULL.md` (файл пользователя, не отслеживается);
   `artifacts/wip/2026-09-29/` (патчи незавершённых работ), `artifacts/quality/mutation-tools/`
   и `artifacts/quality/inventory-a4caec3bf/` (инструменты и инвентари мутаций — это
   скрипты вне git; если переезд постоянный, стоит закоммитить инструменты в
   репозиторий); папку памяти Claude
   (`C:\Users\egorribun\.claude\projects\C--Users-egorribun-Documents-university-ecosystem\memory\`);
   `../university_ecosystem_backups/`. Утверждённый план уже есть в репозитории
   ([MVP_APPROVED_PLAN.md](MVP_APPROVED_PLAN.md)).
3. Окружение: Python 3.14 и `uv sync --frozen`; Node 24 и `npm ci --prefix frontend`;
   Rust 1.97.1, Go 1.26.x, Docker; после сборки фронтенда восстановить
   `frontend/pkg/*.wasm` и provenance (`SKIP_WASM_BUILD=1`). Лаунчер `start-docker.ps1`
   и `scripts/live_stand.py` вызывают PowerShell 7 (`pwsh`) — на Linux его нужно
   поставить.
4. Проверка после переезда: `git status`, `git log origin/egorribun..HEAD` (пусто),
   `git worktree list`, `uv run python scripts/fast_preflight.py`, `npm run lint:knip --prefix frontend`.
5. Агентские worktree не переносятся: создать заново от текущего HEAD и применить
   нужные патчи (`git apply --3way`). Инструкции агентам — шаблоны в разделе 10.
6. **Ограничение этого документа:** он не проходил проверку «холодным читателем».
   Первый агент на новой машине должен записать в `STATUS.md`, чего ему не хватило.
7. Ускорение от мощной машины: главное ограничение сейчас — 15 ГБ ОЗУ, из-за которого
   мутационные агенты и Docker-стенд нельзя запускать одновременно; Linux с 32+ ГБ и 16+
   ядрами снимает его и убирает ловушки Windows (раздел 11). Время полного CI (≈20 ч) от
   машины не зависит.

## 18. Ссылки и артефакты

- План: `C:\Users\egorribun\.claude\plans\cached-cuddling-ladybug.md`; снимок в репозитории —
  [MVP_APPROVED_PLAN.md](MVP_APPROVED_PLAN.md).
- Память проекта: `C:\Users\egorribun\.claude\projects\C--Users-egorribun-Documents-university-ecosystem\memory\`
  (`mvp-decisions-2026-09-28`, `docs-consistency-feedback`, `standing-permissions-2026-09-24`,
  `windows-build-rewrites-wasm`).
- Игнорируемые данные: `artifacts/quality/inventory-a4caec3bf/`,
  `artifacts/quality/mutation-tools/`, `artifacts/wip/2026-09-29/`.
- Вне репозитория: `../university_ecosystem_backups/2026-09-29/` (образ MinIO, bundle
  не запушенных коммитов).
- ADR: [ADR-042](../../adr/ADR-042-seaweedfs-default-object-storage.md),
  [ADR-043](../../adr/ADR-043-retire-python-spiffe-mtls.md),
  [ADR-045](../../adr/ADR-045-mutation-hang-diagnostics-without-a-kill-watchdog.md).
- Runbook хранилища: [s3-seaweedfs-cutover](../../runbooks/s3-seaweedfs-cutover.md).
- Прежний handoff 2026-09-29 (история): [archive/2026-09-29-handoff.md](archive/2026-09-29-handoff.md).

## 19. Промпт для начала нового диалога

```text
Продолжаем доведение University Ecosystem до эталонного MVP.
Утверждённый план: C:\Users\egorribun\.claude\plans\cached-cuddling-ladybug.md.
Сначала полностью прочитай AGENTS.md, затем docs/superpowers/plans/MVP_MASTER_PLAN.md
(главный источник состояния и порядка продолжения) и STATUS.md. Сверь факты: git status,
git log origin/egorribun..HEAD, git worktree list, статус CI run 36553547083.
Действуй по разделу 12 мастер-плана (слабые места — раздел 13, аудит мёртвого груза Ф6d — раздел 14, сроки и политика мутаций — раздел 15): 1) push после terminal CI и свежие инвентари;
2) приёмка WIP (ue-s2 санитайзер, ue-b1..b3 backend-мутанты) через патчи из
artifacts/wip/2026-09-29; 3) focused Stryker волны 1; 4) стенд и live-спеки; далее Ф8, Ф6c, Ф7.
Правила: ветка egorribun, никогда Co-Authored-By, документация обновляется в том же коммите,
абсолютная чистота кода и md, одна сессия — одно рабочее дерево. Без моего явного «да» не
делать merge в main, force-push, закрытие Dependabot PR и удаление локальных данных.
Работай автономно, спрашивай при необходимости.
```
