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
фактического состояния — этот файл и `git log`.

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
4. Если CI-прогон `36553547083` завершён — запушить (раздел 12, шаг 1). Если ещё
   идёт — не пушить: push отменяет прогон (`cancel-in-progress`).
5. Промпт для нового диалога — в конце файла (раздел 14).

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
| Не запушено | 19 коммитов, последний — см. `git log origin/egorribun..HEAD`; копия — git-bundle `../university_ecosystem_backups/2026-09-29/egorribun-unpushed-latest.bundle` |
| CI | Matrix `36553547083` на `634412103`: 311 из 312 job завершены, идёт `Frontend mutation shard 57/64` (старт 15:06 UTC, потолок 270 мин ≈ до 19:36 UTC) |
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
| Ф7 | Остальная quality closure | частично | Rust пин 1.97.1 уже в workflows; O9 закрыт (ADR-045); spelling RU, zero-warning build, BE-02 на все фазы, O1–O8, strict-типизация фикстур — нет |
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
| `../ue-s1` | удаление Python-SPIFFE | **влито** (`7c6b8faee`), можно удалить | — |
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

1. **CI и push.** Дождаться terminal run `36553547083`. Классифицировать красные job
   (root / downstream / by-design по `if:`/`needs:`). Затем `git push origin egorribun`
   (19 коммитов). Скачать артефакты и пересобрать инвентарь:
   `gh run download 36553547083 -D artifacts/quality/inventory-634412103 -p 'frontend-mutation-shard-*'`,
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
5. **Ф8:** метрики SeaweedFS, Grafana provisioning, `restore_db.py`, `config --quiet`
   по комбинациям, замеры. **Ф5/Ф6:** остальные live-спеки и workflow.
6. **Ф6c/Ф7:** Go `staticcheck`, демо-данные, нагрузка ws-hub, spelling RU, review ветки.
7. **Ф9–Ф12** — по плану; merge и post-merge только с явного «да».

## 13. Ссылки и артефакты

- План: `C:\Users\egorribun\.claude\plans\cached-cuddling-ladybug.md`.
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

## 14. Промпт для начала нового диалога

```text
Продолжаем доведение University Ecosystem до эталонного MVP.
Утверждённый план: C:\Users\egorribun\.claude\plans\cached-cuddling-ladybug.md.
Сначала полностью прочитай AGENTS.md, затем docs/superpowers/plans/MVP_MASTER_PLAN.md
(главный источник состояния и порядка продолжения) и STATUS.md. Сверь факты: git status,
git log origin/egorribun..HEAD, git worktree list, статус CI run 36553547083.
Действуй по разделу 12 мастер-плана: 1) push после terminal CI и свежие инвентари;
2) приёмка WIP (ue-s2 санитайзер, ue-b1..b3 backend-мутанты) через патчи из
artifacts/wip/2026-09-29; 3) focused Stryker волны 1; 4) стенд и live-спеки; далее Ф8, Ф6c, Ф7.
Правила: ветка egorribun, никогда Co-Authored-By, документация обновляется в том же коммите,
абсолютная чистота кода и md, одна сессия — одно рабочее дерево. Без моего явного «да» не
делать merge в main, force-push, закрытие Dependabot PR и удаление локальных данных.
Работай автономно, спрашивай при необходимости.
```
