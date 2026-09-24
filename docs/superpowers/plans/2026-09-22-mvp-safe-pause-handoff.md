# University Ecosystem: safe-pause handoff и план полного закрытия

> **Для следующего исполнителя:** работа приостановлена по прямому запросу пользователя. Не возобновлять исполнение, контейнеры, мониторинг или публикацию до команды продолжить. После возобновления использовать `executing-plans` либо `subagent-driven-development`, затем независимое ревью и `verification-before-completion`. Чекбоксы ниже означают оставшуюся работу, а не распоряжение повторить уже реализованные вертикали.

**Дата снимка:** 2026-09-22, около 16:25–16:35 Europe/Moscow. GitHub timestamps — UTC.

> **Статус 2026-09-25 01:20 Europe/Moscow — снова безопасная пауза по запросу пользователя.** Актуальное состояние — только **§0 ниже**. Разделы §1–§5 описывают паузу 2026-09-22 и остаются историей (WASM, MFA, Semgrep из них давно закоммичены и опубликованы). Требования и Definition of Done §6–§13 остаются в силе, их уточняет §0.9.

## 0. Снимок 2026-09-25: полное текущее состояние

### 0.1 Идентичность, сохранность и что НЕ трогать

| Поле | Состояние на паузе |
| --- | --- |
| Repository / ветка | `C:/Users/egorribun/Documents/university_ecosystem`, `egorribun` (PR [#1266](https://github.com/egorribun/university_ecosystem/pull/1266) → `main`, OPEN) |
| HEAD | коммит этого handoff поверх `3031cd5fa`; все изменения закоммичены и запушены в `origin/egorribun` (проверять `git status` / `git log origin/egorribun..HEAD` — должно быть пусто) |
| Рабочее дерево | чистое, кроме пользовательского untracked `docs/audits/AUDIT_PLATFORM_FULL.md` (SHA256 `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b`, не изменять и не стейджить) |
| Коммитов с 0ec4fed3a | 46 (полный список: `git log --oneline 0ec4fed3a..HEAD`) |
| Stash | не использовался |
| Контейнеры | `codex-wasm-base64-0ec4fed3a` удалён с разрешения пользователя; собственный `claude-wasm-base64-0ec4fed3a` удалён ранее; других контейнеров этой работы нет |
| Агенты | все три фоновых агента (группы A, B, C) остановлены; их работа собрана и закоммичена; фоновых процессов/мониторов нет |
| Скрытые мутации | проверено: ни в основном дереве, ни в worktree нет файлов, оставленных мутантом; `artifacts/quality/mutation-tools/…/mutant-backups` пуст |

**Дополнительные git worktree (оставлены намеренно, пустые по содержанию):** `../ue-mut-A`, `../ue-mut-B`, `../ue-mut-C` (агентские, detached на `2dc1c40e3`, их тестовые правки уже перенесены в основное дерево), `../ue-e2e` (чистый HEAD для локального E2E), `../ue-mm` (для backend-мутаций, содержит копии уже закоммиченных файлов). **Опасность:** в каждом `frontend/node_modules` и корневой `node_modules` — это NTFS-junction на `university_ecosystem/…/node_modules`. **Никогда не делать `rm -rf`/`git worktree remove --force` по такому дереву** — рекурсивное удаление через junction снесёт node_modules основного репозитория. Безопасная очистка: сначала `cmd /c rmdir <path>\frontend\node_modules` и `cmd /c rmdir <path>\node_modules` (удаляет только ссылку), затем `git worktree remove <path>`. Если worktree больше не нужны — так их и убрать; содержимого, которого нет в `egorribun`, в них нет (проверка: `git -C ../ue-mut-X status --short` показывает только тесты, совпадающие с основным деревом; `ue-mm` — только копии закоммиченных файлов).

### 0.2 Решения и постоянные полномочия пользователя (действуют дальше)

Зафиксированы в памяти проекта (`~/.claude/projects/…/memory/`):

1. **Scope (2026-09-23):** CDC (BE-08) вне MVP, DEFERRED (ADR-037 §scope); spelling — сначала авторские docs, потом код; реального staging нет → Stage 10 на Docker Core/full + локальный kind; доставка email/push — только локальные sink'и (Mailpit, локальный VAPID).
2. **Frontend Stryker (2026-09-24):** гибрид. Поведенческие survivors убивать тестами; косметические литералы className/style — единственный governed ignorer ADR-040 (`presentation-class-names`). Расширять ignorer — только новым ADR. До 3 параллельных агентов на непересекающихся файлах с ревью ведущего перед коммитом.
3. **Постоянные разрешения (2026-09-24):** скачивать пинованный инструментарий из официальных источников (Playwright-браузеры из lock-версий, Docker-образы из compose/Helm по digest, kind/helm/kubectl/mkcert с checksum); скачивать CI-артефакты своего репо (`gh run download`) в ignored `artifacts/`/scratchpad; обычный `git push origin egorribun` без вопросов. **Всегда спрашивать:** merge в `main`, force-push, закрытие/merge Dependabot PR, branch protection, любые внешние/публичные действия, загрузки вне перечисленного.
4. Коммиты без `Co-Authored-By`; scope non-wave (`fix(frontend)`, `test(quality)`, `test(security)`, `refactor(frontend)`, `docs(quality)`…); `feat(waveXX)` — только новая бизнес-функциональность (последняя — wave212).
5. Лимит сессии аккаунта пользователя может оборвать работу (так остановился агент C 2026-09-24, сброс 23:10 MSK). Перед долгой работой помнить: при обрыве запустить восстановление из §0.7.

### 0.3 Главная находка этой сессии: реальный масштаб mutation-долга

- Frontend aggregate `validate-stryker-inventory` — **fail-fast**: он всегда останавливался на первом плохом мутанте (`shard-001:2 Timeout`), а producer-шарды идут с `break: null` и «зелёные» даже с survivors. Поэтому «100% frontend Stryker» ни разу не был достигнут. По 41 скачанному шарду run 35954304649: **968 поведенческих survivors в 118 файлах** после ADR-040 (145 были косметикой), всего по вселенной ожидалось ~1500 до работы.
- Backend incremental mutmut (run 35976627864): **203 survivors** в коде ветки (schedule_changes 80, logging 49, schedule_service 22, system_release 16, auth_service 11, revocation 7, мелочи 18). **Все 203 закрыты** (см. §0.4).
- Источник поштучных данных: CI-артефакты `frontend-mutation-shard-<run>-*` (mutation.json) и clear-text таблицы в логах jobs «Frontend mutation shard N/64»; backend — строки `🙁 <module>.<mutant>` в логах «Incremental Mutation Tests (mutmut) / execution group N».

### 0.4 Что сделано в этой сессии (коммиты `ad4d2d23f` … HEAD, по темам)

**Продукт (все с RED→GREEN):**
- `ad4d2d23f` P8: sticky-бары категорий News/Events вынесены из короткого `<header>` (sticky не мог выйти из containing block и уезжал), `z-sticky` поверх бейджей карточек, матовая подложка stuck-бара Events; хук `useStableListHeight` держит высоту списка в фазе render (не layout effect), E2E `tests/e2e/category-scroll-stability.spec.ts`.
- `92e37b007` `shouldReload: false` на роутах `/news` и `/events` (loader-префетч не перезапускается на смену search; pending UI роутера перемонтировал страницу) + ETag E2E ищет ссылку карточки, а не текст (quick view дублирует заголовок).
- `1568c7dd2` **баг rate-limit очереди:** после grant, заполнившего rolling-window, никто не ставил таймер — оставшиеся ожидающие висели до чужого release. Теперь acquire при непустой очереди армирует таймер; тест `rateLimit.window.test.ts`.
- `235a8d8de` **баг чётности недели:** `nowParity` считал недели от 1 января с субботы, backend — ISO (`isocalendar()`); dashboard показывал/фильтровал не ту неделю на стыках лет и выходных. Новый `isoWeekNumber`, тесты на 53-недельный год.
- `764c5c649` **баг roomStatus:** занятие 08:00–08:00 делало аудиторию занятой весь день (`end <= start` трактовалось как переход через полночь).
- `9451e88c3` Levenshtein без мутируемых счётчиков циклов (мутант `j++→j--` давал бесконечный цикл = Timeout).

**Mutation/quality infrastructure:**
- `2dc1c40e3` ADR-040 + `frontend/scripts/stryker-presentation-ignorer.mjs`: игнор только строковых листьев в `className`/`*ClassName`, аргументах `cn/clsx/cva/twMerge/twJoin`, биндингах `*Classes/*ClassName`, литеральных значениях `style={{…}}`. Все стадии evidence (`run-stryker.mjs`, `validate-stryker-inventory.mjs`, `verify-stryker-evidence.mjs`, `stryker.config.mjs`) используют `canonicalInstrumenterConfig`; Ignored допускается только с reason ADR-040 и только если совпадает с регенерированным preflight; `ignoredMutants` в summary и вне знаменателя. 152 node-теста скриптов зелёные; проверено на реальном `mutation.json`.

**Frontend survivors (тесты + эквивалентные упрощения без смены поведения):**
- `411d1ee58` sanitizers/redirect/Trusted Types — 100% (security-review: 0 находок): `sanitizeArticleHtml`, `sanitize.ts` (`parseHttpUrl`), `SafeHtml` (тесты теперь проходят WASM-ветку), `trustedTypes`, `redirect` (+SSR-тест).
- `afc38343d` группа A (агент): 198/284. `1476ea7d8` группа B (агент): 157/206. `d96d6e462` + `3031cd5fa` группа C (агент): 49+3 тестовых файла, ~46 из 72 файлов проверены до остановки.
- `2cd4e1c20` эквивалентные guard'ы удалены в weatherIcons, buildingHours, avatar, readingTime, scheduleConflicts (NaN вместо null; `Math.max(null,…)` считал null нулём), passwordStrength, authUtils (`=== -1`), highlight (`replaceAll`), htmlText, loaderLang. Весь unit-набор (5842) зелёный. **Мутационно проверены:** weatherIcons 97/97, avatar 43/43, readingTime 14/14, scheduleUtils 33/33, roomStatus 45/45, levenshtein 18/18. **Не проверены мутационно после упрощения:** buildingHours, scheduleConflicts, passwordStrength, authUtils, highlight, htmlText, loaderLang — сделать первым делом (§0.8 шаг 3).

**Backend survivors — все 203 закрыты, каждый модуль проверен полным набором текущих мутантов:**
- `abfeb7779` schedule_changes 208/208 + новый `render_registered_notification_template` 9/9 (мёртвые fallback'и убраны, точный вызов доставки и fingerprint в тестах).
- `7660b3ad6` PII-редакция логов 107/107 (+ убран эквивалентный 5-символьный shortcut).
- `e4abf5020` `schedule_state`/`delete_schedule` 57/57, `announce_release` 99/99.
- `3555735ed` `_token_hmac_secret` 24/24, `get_revocation_redis_client` 26/26 (поля Settings читаются напрямую).
- `0fd22d2fb` images 33/33 (float-граница бюджета пикселей), HMAC-strength 23/23, event handler 17/17, lifespan shutdown 33/33, DI-композиция 31/31, `get_current_user` 8/8.

### 0.5 CI: текущее состояние

- Последний запушенный до этого handoff SHA `5616cf778` → run [36058587950](https://github.com/egorribun/university_ecosystem/actions/runs/36058587950) был `queued/in_progress` (119 success, 5 failure, 160 queued на момент паузы). Коммиты `235a8d8de…` и этот handoff запушены после — новый run запустится на HEAD; проверять `gh run list --workflow ci.yml --branch egorribun --limit 3`.
- **Падения run 36058587950, классификация:**
  - `Go Integration Tests (file-processor)`: `TestIntegration_MinIOResizeImageHappyPath` — pull `quay.io/minio/minio@sha256:14cea…` вернул `unauthorized` (внешний registry). Не код; rerun при восстановлении registry, при повторе — рассмотреть mirror/кэш образа.
  - `Chaos Engineering (ToxiProxy)`: `Docker pull failed with exit code 1` — та же внешняя причина (проверить, какой образ).
  - `DB Migration Rollback Integrity`: `TOML parse error at line 459, column 17 … failed to parse year in date "7 days"` — **конфигурационный дефект**: `pyproject.toml [tool.uv] exclude-newer = "7 days"` читает старый uv/парсер в этом job. Выяснить, какой бинарь (не `setup-uv` с `required-version ==0.11.28`?), и привести job к канонической установке uv. Код миграций не причём.
  - `E2E webkit` и `E2E mobile-webkit`: `/news` `category-scroll-stability` — `before=522 after=0 max=522` **даже с `shouldReload:false`**. Первопричина НЕ найдена (floor высоты держится, значит это явный scroll-to-top, а не clamp). Chromium зелёный; локальный Windows-WebKit ненадёжен (module-script preload errors → boot loader) — воспроизводить только на Linux WebKit (CI или Docker `mcr.microsoft.com/playwright`). Гипотезы для проверки: focus/scrollIntoView кнопки внутри sticky в WebKit, `useURLState` navigate с `viewTransition`/hash, перемонтирование `NewsList` (другой ключ), `PageTransition`. Скачать trace: `gh run download <run> -n playwright-traces-mobile-webkit-shard-1-of-1`.
- Frontend Stryker на новом SHA даст первый полный инвентарь **после ADR-040**; только по нему судить об остатке. Aggregate по-прежнему fail-fast — полный список брать из шардов (§0.3).

### 0.6 Инструменты мутационной проверки (долговечные копии)

Лежат в ignored `artifacts/quality/mutation-tools/` (оригиналы были во временном scratchpad сессии). Инвентари — в `inventories/` (всегда передавать `--inventory <файл>`, дефолтный путь скриптов указывает на соседний `behavioural-survivors.json`).

- `fresh_mutants.mjs` — генерирует все НЕигнорируемые мутанты текущих исходников тем же Instrumenter + ADR-040: `cd frontend && node ../artifacts/quality/mutation-tools/fresh_mutants.mjs --out /tmp/x.json src/utils/a.ts`.
- `mutant_check_fast.mjs` — один in-process Vitest на все мутанты (~2–7 с/мутант), crash-backup + авто-восстановление: `node …/mutant_check_fast.mjs --inventory /tmp/x.json --file src/utils/a.ts --tests "src/utils/__tests__/a.test.ts"`. Печатает KILLED/SURVIVED/TIMEOUT. `mutant_check.mjs` — медленный эталон (npx на мутант) для перепроверки спорных.
- Backend: `mm_check.py diff <file> <mutant…>` (дифф мутанта через ast), `mm_loop.py --file app/x.py --tests "tests/…" [--all | mutant…]` — один pytest-процесс, переключение `MUTANT_UNDER_TEST` (трамплин mutmut читает его на каждом вызове), watchdog Timeout, shim для `mutmut.__main__` (на Windows не импортируется). Запускать **в отдельном worktree** (`../ue-mm`) основным `.venv/Scripts/python.exe` и `PYTHONIOENCODING=utf-8` (имена методов содержат `ǁ`).
- `narrow_fresh.py` — оставляет из свежих мутантов только те, у которых нет убитого близнеца в CI-отчёте (после рефакторинга позиции сдвигаются).
- **Правила, выученные на ошибках этой сессии:**
  1. Никогда не запускать две мутационные проверки над связанными файлами одновременно в одном дереве.
  2. Во время мутационной проверки в основном дереве **не коммитить**: pre-commit stash и проверка «files were modified by this hook» ломаются, а результаты искажаются.
  3. После любого прерванного прогона проверить `mutant-backups/` и `git status` на неожиданные продуктовые изменения; восстанавливать из бэкапа или `git checkout`.
  4. При восстановлении бэкапов трогать только свои файлы (один раз ошибочно были восстановлены файлы агентов посреди их прогона).
  5. detect-secrets реагирует на тестовые пароли/токены — выносить в константу с `# pragma: allowlist secret` / `// pragma: allowlist secret` на той же строке (ruff/prettier переносят хвостовые комментарии).

### 0.7 Восстановление после обрыва сессии/лимита

1. `git status --short` (ожидается только AUDIT), `git log origin/egorribun..HEAD` (пусто или локальные коммиты — тогда push после preflight).
2. `ls artifacts/quality/mutation-tools/mutant-backups/` (и старый `C:/Temp/claude/…/scratchpad/mutant-backups/`, если существует): каждый файл — URL-кодированный абсолютный путь; сравнить с целевым файлом, восстановить или удалить.
3. Для каждого `../ue-*` worktree: `git -C ../ue-X status --short` — продуктовые (не test) изменения там = оставленный мутант → `git -C ../ue-X checkout -- <file>`.
4. `docker ps -a` — контейнеров этой работы быть не должно.

### 0.8 Что делать дальше — по порядку

1. **CI на HEAD:** дождаться run; классифицировать каждое падение (root/infra/transient). Rerun только доказанно-транзиентных (registry pull) на неизменном SHA.
2. **DB Migration Rollback:** починить установку uv в этом job (TOML `exclude-newer = "7 days"`), контракт-тест на workflow, если есть аналог.
3. **Мутационная проверка 7 упрощённых утилит** (§0.4): `fresh_mutants` + `mutant_check_fast` по каждому с его тестами; добить survivors.
4. **Остаток группы A** (из отчёта агента, всё с предложенными product-диффами): `media.ts` 26 эквивалентов (избыточные early-return/guard'ы — решить удалением, это не security-граница, но аккуратно), `performance.ts` 4, `cryptoWorker.ts` 5 (только утечки map — возможно экспорт размера только для тестов или рефакторинг pending-map), `browser.ts` 4, `spotify.ts` 3, `cache.ts` @6, `api/hooks/news.ts` @66, `slugify.ts` @14, `a11y.ts` @107 ×2, `animations.ts` @48 (убрать лишний `type:"spring"`), `rateLimit.ts` @199 (удалить строку), @40, **@148 Timeout** (пустое тело `waitForClientQueueWaiter` → бесконечная асинхронная рекурсия; лучший путь — direct-handoff слота вместо повторного acquire, с тестами на abort-после-grant), `bootstrapFallback.ts` 34 инлайн-стиля (решение ведущего: НЕ расширять ADR-040, а один тест на полный `style.cssText` элементов fallback — без stylesheet это поведение).
5. **Остаток группы C:** агент проверил ~46 из 72 файлов (`inventories/work-C.json`); остальные — начиная с `MobileBottomNav`, `MapSidebar`, `ContactList`; брать актуальный список из нового CI-инвентаря.
6. **P8 WebKit** (§0.5) — довести до зелёного на Linux WebKit.
7. **P8-файлы после ADR-040:** EventsFeature/NewsFeature/EventsHeader/NewsHeader имели 226 survivors по локальному focused-прогону ДО ignorer — перепроверить по новому CI-инвентарю.
8. Затем план `C:\Users\egorribun\.claude\plans\cryptic-singing-catmull.md`: оставшиеся продуктовые P2 (push-prompt), P4 (auth shell), P6 (виртуализация ContactList), P11 (compact navbar), C0 live-E2E лейн, фаза B (BE-02 phase-four миграция, Mailpit), фаза D (spelling docs→код, zero-warning build, O-задачи), фаза E (Docker Core/full, kind, финальный аудит). Dependabot #1289–#1292 — только с разрешения. Merge в `main` — только с разрешения.

### 0.9 Уточнения к Definition of Done (§13)

- «100% viable» frontend = каждый мутант, кроме ADR-040-ignored и объяснённых CompileError, Killed; Timeout/RuntimeError/NoCoverage недопустимы — лечатся устранением причины (как Levenshtein, rateLimit), а не ослаблением гейта.
- Эквивалентный мутант = сигнал на упрощение кода без смены поведения (с тестом, что поведение сохранено), а не на `// Stryker disable` (запрещено валидатором).
- Ни один из пунктов §0.8 не считать выполненным по старым отчётам; подтверждение — свежий CI на точном SHA.

**Goal:** закрыть весь действующий continuation/master scope на текущем уровне функциональности: воспроизводимый безопасный MVP, все применимые quality metrics 100%, полная продуктовая приёмка и SHA-bound Docker/staging/release evidence. Этот handoff не уменьшает scope и не заменяет критерии готовности удобным подмножеством.

**Архитектура продолжения:** сохранить реализованные функции; сначала закончить незакоммиченный пакет, затем устранить свежие подтверждённые дефекты, собрать полную приёмочную матрицу и продвигать один immutable build. Исправлять product code по воспроизведённому RED, а недостаток доказательств не называть автоматически дефектом продукта.

**Стек:** Python 3.14/FastAPI/SQLAlchemy async/Dishka; React 19/TypeScript/Vite/Vitest/Stryker/Playwright; Go services; четыре Rust-компонента; PostgreSQL/Redis/NATS; Compose/Helm/GitHub Actions.

## 1. Быстрое восстановление контекста

### 1.1 Что читать и в каком порядке

1. Этот handoff — операционная точка остановки, включая незавершённую WASM-сборку.
2. Корневой [AGENTS.md](../../../AGENTS.md), доменные AGENTS затрагиваемых областей и [quality contract](../../../quality/quality-contract.json).
3. [Continuation plan](2026-08-31-mvp-quality-closure-continuation.md), **§148**, затем относящиеся к текущей задаче acceptance-разделы. Старые operational snapshots не являются текущим статусом.
4. [Исходное MVP ТЗ](University_Ecosystem_MVP.md): требования сохраняются, но предложения «переписать профиль с нуля» заменены утверждённым gap-аудитом существующего продукта.
5. [Foundation plan](2026-08-25-quality-closure-foundation.md) и [старый prompt](prompt.md) — явно HISTORICAL/SUPERSEDED. Старые TypeScript blocker, PR #1257, shard counts и SHA не переносить в новый статус.
6. Внешний аудит `docs/audits/AUDIT_PLATFORM_FULL.md` (пользовательский, не отслеживается в Git), [индекс аудитов](../../audits/INDEX.md), [ADR-037](../../adr/ADR-037-cdc-outbox-transport-ownership.md), [ADR-039](../../adr/ADR-039-frontend-mutation-shard-cost-model.md).

Это дополнительный handoff к одному активному roadmap, не второй конкурирующий master plan. При расхождении статусов использовать свежий код/логи/артефакты; при расхождении требований — утверждённый goal, AGENTS и текущий quality contract, а не старые baseline-таблицы.

### 1.2 Идентичность и сохранность

| Поле | Состояние при остановке |
| --- | --- |
| Repository | `C:/Users/egorribun/Documents/university_ecosystem` |
| Ветка | `egorribun` |
| HEAD и опубликованный PR head | `0ec4fed3a61826561cbbcaf3c7e1b665ac579706` |
| PR | [#1266, OPEN, egorribun → main](https://github.com/egorribun/university_ecosystem/pull/1266) |
| Текущий Matrix run | [35730420629](https://github.com/egorribun/university_ecosystem/actions/runs/35730420629), attempt 1, `in_progress` при последней проверке |
| Worktree | Только основной зарегистрированный worktree |
| Stash | `git stash list` пуст при остановке; ничего из stash не удалялось |
| Index | Текущий пакет не staged; новый handoff также первоначально untracked |
| Worktree cleanliness | **Не чистый по Git:** есть намеренные незакоммиченные изменения ниже |
| User audit | Untracked `docs/audits/AUDIT_PLATFORM_FULL.md`, пользовательский, не изменять/не добавлять автоматически |
| User audit SHA256 | `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b` |
| Goal | Active, не complete и не blocked; пауза не означает блокер |

Коммита/пуша при этой безопасной паузе не делается: пользователь запросил остановку и handoff, а текущий WASM-пакет ещё не завершён. Все изменения сохранены на диске. Не заявлять, что они уже находятся на GitHub.

### 1.3 Фактически остановленные процессы

- Локальные E2E preview и PostgreSQL acceptance завершены; тестовые PostgreSQL-контейнеры удалены только после результатов/проверки очистки.
- Субагенты завершены либо interrupted. Новые задачи не запускать во время паузы.
- Единственный работавший сборочный контейнер остановлен, **не удалён**:
  - name: `codex-wasm-base64-0ec4fed3a`;
  - ID: `c745a06530774790c4189eb4bfa9ccc1bcbaa08baf2f1d34db6481f4f467c121`;
  - image: `ubuntu:24.04`, Linux amd64;
  - 2 CPU, 3 GiB, pids limit 256;
  - status: `exited`, exit 143 после намеренной остановки, **не build failure verdict**;
  - исходный процесс имел `timeout 1500`, readonly mount собственных `artifacts/wasm-linux-baseline-0ec4fed3a` в `/input`;
  - `/work`, toolchain и промежуточные результаты остались внутри контейнера.
- После остановки `docker ps` пуст; targeted process scan не нашёл node/python/cargo/docker/wasm процессов с путём проекта или именем этой сборки. Это не утверждение, что на машине нет посторонних процессов.
- Облачный CI **не отменён**. Локальный мониторинг прекращён. Автоматическое возобновление не создавалось; стандартный каталог `C:/Users/egorribun/.codex/automations` отсутствует при проверке.

Не делать `docker start` вслепую: entrypoint повторно выполняет bootstrap с `mkdir` и загрузками и не является идемпотентным resume. Не удалять контейнер до извлечения нужных результатов или доказанной ненужности.

## 2. Что уже закончено и опубликовано

Предыдущая повторная оценка охватила 19 пользовательских коммитов от `d4d3021b912cb59ed6e8bb132c7eec6faed8b2cb` до `2fdb2e2f45618f4c5a836203f379bec36f76313d`, 159 изменённых файлов. Не возвращаться к состоянию до самостоятельной работы пользователя.

| Commit | Изменение | Доказательство / граница |
| --- | --- | --- |
| `0606860c6` | DI route inventory ownership, canonical `Path` import | RED пустых references; 114 focused tests, полный inventory checker |
| `c91f7d0bb` | Scoped provider-utils 4.0.33 override для msw-auto-mock; удалены 8 устаревших undici allowances | npm full/lock audit 0, 4 реальных normalized generated mocks byte-identical |
| `e88009d6f` | Literal-safe default preflight миграции | 42 offline + 6 real PostgreSQL tests; строки не нормализуются с потерей payload |
| `200a48f01` | Fail-closed CDC startup и безопасный WAL acknowledgment | 101 focused tests; touched lifespan/CDC line+branch 100%; реальный transport всё ещё deferred |
| `325418de3` | Auth unavailable/forbidden/success, malformed schedule cache; удалены 5 невозможных Request=None ветвей | 88 auth/schedule + 69 content tests, touched scopes line+branch 100% |
| `c082176f7` | §148 и ADR-039: честный статус после reassessment | Не объявляет продукт и release завершёнными |
| `0ec4fed3a` | Preflight evidence и dormant spelling finding | Текущий опубликованный head |

Предыдущие локальные проверки опубликованного пакета: harness 29/29; frontend typecheck/lint/build exit 0; strict mypy 361 app files; Ruff/AST/Bandit; scoped pre-commit; combined migration/CDC 143 tests; independent PostgreSQL 6 cases; frontend quality/MSW 13 tests. Это scoped evidence, не доказательство полного текущего mutation universe.

Fast-preflight **на `c082176f7`**, не на последующем docs SHA: 6/6, typecheck 8.049 s, lint 98.870 s, backend type 5.851 s, backend lint 0.178 s, harness 34.319 s, contracts 70.833 s. JSON: `artifacts/fast-preflight/fast-preflight.json`. Build имел Rolldown/Node localStorage warnings, поэтому zero-warning release не подтверждён.

## 3. Незакоммиченный пакет: полный ownership inventory

### 3.1 Rust HMAC Base64 — implementation есть, генерация НЕ завершена

Изменены:

- `frontend/rust-crypto/Cargo.toml`, `Cargo.lock`;
- `frontend/rust-crypto/src/lib.rs`, `src/tests.rs`;
- `frontend/rust-crypto/tests/native.rs`, `tests/wasm.rs`;
- `frontend/src/workers/crypto.worker.ts`;
- `frontend/src/workers/__tests__/crypto.worker.closure.test.ts`, `crypto.worker.parity.test.ts`;
- `frontend/scripts/verify-wasm-artifacts.mjs`, `verify-wasm-artifacts.test.mjs`;
- `frontend/scripts/wasm-runtime-smoke.test.mjs`, `challenger-adversarial.test.mjs`.

Изменение: additive export `hmac_sha256_sign_base64(key, message)` возвращает RFC 4648 padded Base64; старый hex export сохранён. Общий private digest сохраняет существующие Zeroizing-буферы и обнуление промежуточного digest; PBKDF2/scrypt не изменены. Worker вызывает новый export вместо regex/parseInt/Uint8Array/btoa. `base64ct = 1.8.3` уже был transitive locked dependency; добавлена одна прямая связь.

Проверено:

- RED: в существующем WASM отсутствует новый export; проверка worker запрещает JS btoa round trip; validator отвергает отсутствие export.
- Worker 11/11; validator 8/8; adversarial validator cases 6/6; provenance unit 5/5.
- Native Rust 27/27 на Windows и Linux; Linux `cargo clippy --all-targets --locked -- -D warnings` exit 0.
- Scoped ESLint/Prettier/Rustfmt/diff checks проходят.
- Независимое source/security review: PASS; не является доказательством полной memory zeroization в оптимизированном бинарнике.

**Важно:** generated `rust-crypto/pkg` и `frontend/WASM_SOURCE_PROVENANCE.json` ещё НЕ обновлены в worktree. Full TypeScript сейчас ожидаемо сообщает TS2724: новый export отсутствует в generated declarations. Не скрывать эту ошибку, не возвращать worker к старому API ради зелёного typecheck, не коммитить половину изменения.

Исходные committed пакеты успешно воспроизведены в Linux **до изменений**, тем самым устранена гипотеза «на этой машине невозможно»:

- Rust 1.97.1; wasm-pack 0.13.1; Binaryen 117; Node 24.21.0.
- Remaps: `/root/.cargo` → `/usr/local/cargo`, root `/work`.
- crypto WASM SHA256: `98e6d43877ef0ac02b4f80859e097d1a24836311a749d75968ac63fa213a59ab`.
- sanitizer WASM SHA256: `4e20e0537cdf3b1f3c78ad2685cd6a31a112b872a6796cc1178d89efc1dd6396`.
- provenance SHA256: `3775d67edf2147e7aedd95424baa36950e07393b5257eacc833fb3a4811be9b5`.
- Strict artifact validator и 2/2 прежних runtime smoke пройдены на baseline. Это не новые Base64 artifacts.

Resume inputs сохранены в ignored `artifacts/wasm-linux-baseline-0ec4fed3a/`: `baseline.sh`, `implementation.sh`, `source.tar`, `changed.tar`. Последний Linux log был компиляцией sanitizer/ammonia; marker `CANONICAL_SECOND_CLEAN_BUILD_VERIFIED` не получен. Не принимать частичные файлы контейнера за готовые.

После команды продолжить:

- [ ] Сверить current source с `changed.tar`, чтобы не собирать устаревшую snapshot.
- [ ] Изучить оба shell helper целиком. Перенести bootstrap в воспроизводимый bounded runner либо безопасно использовать сохранённый toolchain после копирования нужных файлов из stopped container; не исполнять entrypoint повторно без проверки.
- [ ] Сохранить exact versions, checksum verification скачанного инструментария, remaps и lockfiles. Не объединять разные wasm-bindgen lock versions двух crates насильно.
- [ ] Выполнить первую canonical regeneration, runtime smoke, source/provenance validation.
- [ ] Выполнить вторую действительно clean сборку обоих WASM crates, сравнить bytes и strict validator. Удаления разрешены только для проверенных точных owned target/pkg каталогов внутри disposable builder.
- [ ] Только после PASS перенести необходимые generated crypto JS/WASM/declarations и provenance в worktree; sanitizer при отсутствии source changes должен остаться byte-identical.
- [ ] Проверить diff generated export, source hashes, package hashes; независимое review; full typecheck, runtime smoke, worker tests, build.
- [ ] После сохранения доказательств удалить только собственный stopped build container, если он больше не нужен. Не выполнять global prune.

Отдельный незакрытый drift: `frontend.Dockerfile` использует Rust 1.94.1 и непинованный `cargo install wasm-pack`; это не canonical producer. Нужны RED Docker/provenance contracts и выравнивание воспроизводимости либо безопасное потребление проверенных canonical artifacts, а не произвольная смена образа.

### 3.2 PostgreSQL MFA acceptance — локально завершено, не committed

Файлы: modified `tests/integration/test_mfa_email_otp_postgres.py`; new `tests/test_mfa_postgres_acceptance_contract.py`.

Корень gap: test требовал только `MFA_TEST_POSTGRES_DSN`; обычный integration workflow задаёт `RUN_INTEGRATION_TESTS=1` и `DATABASE_URL`, поэтому реальная MFA acceptance тихо пропускалась.

Новая fixture использует существующий integration lane без нового workflow: требует testing/reset opt-in и PostgreSQL test authority; создаёт уникальную `test_mfa_<uuid>` базу через `psycopg.sql.Identifier`; не меняет source DSN; удаляет только успешно созданную owned базу в finally. Failed CREATE/collision не разрешает DROP. Явный manual DSN остаётся caller-owned, автоматически не удаляется. Sync/async engines dispose в finally.

Review выявило и исправило P2: `connect_timeout=10` не ограничивает DDL. Теперь connect options задаёт `lock_timeout=10000`, `statement_timeout=30000`; assertions и timeout propagation покрыты. RED без options подтверждён.

Доказательства:

- 31 lifecycle contract + 36 Semgrep contracts: **67 passed in 34.11 s**, exit 0, с отдельным writable pytest cache.
- Независимый root real-CI-path run без manual MFA DSN: **1 passed in 18.52 s**, exit 0; sentinel value 42 сохранился, запрос `test_mfa_%` вернул 0 строк; собственный контейнер удалён в finally.
- JUnit: `artifacts/quality/mfa-postgres-root-review.xml`.
- Более ранние real PG runs: 1 passed 33.42 s и 35.48 s; agent JUnit в `C:/Temp/mfa-pg-audit-46512ec3ab764826822be98f478a4b9a/`.
- Независимое review после SQL timeout fix: PASS.

Граница: existing autouse `prepare_database` создаёт metadata/RLS в shared suite DB. Новая fixture не мигрирует/не удаляет shared DB, но **весь pytest harness не является read-only** относительно неё. Любые запускаемые DATABASE_URL должны указывать только на явно выделенную disposable test БД.

### 3.3 Email MFA browser contracts — локально завершено, новый файл

Файл: `frontend/tests/e2e/email-mfa.spec.ts`.

Шесть RU/EN случаев: masked hint и email-only login; resend cooldown/rotation/wrong-code/retry; recovery entry → возврат к email challenge. Stateful route doubles фиксируют payload и порядок. Это **mocked browser contract**, не real SMTP/outbox verification.

Независимое review поймало fixed-Date/live-timers race. Контролируемый RED воспроизведён без wall-clock sleep. Исправление: Clock install до navigation, pause после hydration, синхронное продвижение Date/timers и ожидание React labels. Сохранены точные assertions disabled на 59.999 s / enabled на 60 s.

- Repeat-each 5, workers 2: **30/30**, 2.1 min.
- Existing TOTP `mfa.spec.ts`: **4/4**.
- Scoped ESLint/Prettier/diff PASS; независимое review PASS.
- Preview остановлен; traces в `frontend/test-results` (ignored).
- Использовался установленный Chromium 1234 вместо отсутствовавшего ожидаемого 1243; pinned CI browser повторить перед full certification. Prod dist был существующий, так как product login code не менялся; не переносить это evidence на будущий новый build.

### 3.4 Semgrep ledger — исправлен новый CI failure

Файлы: `security/semgrep-suppression-policy.json`, `tests/test_semgrep_sarif_validator.py`.

После добавления CDC startup guard неизменный reviewed SQL сдвинулся с 519–521 на 528–530. Обновлены **только две точные line ranges**, без расширения правил, rationale, owner или expiry. Новая AST-based regression определяет текущую CREATE PUBLICATION call и отвергает shifted/unsuppressed report.

RED совпадает с CI error; 36 tests PASS; independent review PASS. Полный свежий Semgrep hosted job на новом SHA ещё обязателен. Это поддержание существующего доказанного false-positive ledger, не новая blanket suppression.

### 3.5 Documentation — изменён continuation, плюс этот новый handoff

Modified `docs/superpowers/plans/2026-08-31-mvp-quality-closure-continuation.md`:

- уточнён BE-02 status;
- command block переведён в indented syntax для MD046;
- добавлены Dependabot/spelling/WASM/CI diagnostics и границы доказательств.

Pinned Markdownlint CLI2 0.23.2: focused и 199 tracked Markdown files PASS. Local-link checker: 892 files PASS; не проверяет wording/remote URLs/anchors. После handoff и его backlink повторить проверку документов.

## 4. CI: что смотреть первым после паузы

### 4.1 Current run, не исторические списки пользователя

Run `35730420629` выполняется на **опубликованном** `0ec4fed3a`, без незакоммиченных изменений раздела 3. При остановке известны два failure:

| Job | ID | Причина | Исправление |
| --- | --- | --- | --- |
| Security Audit / Semgrep SAST | `106754858489` | ledger не покрывает shifted CDC SQL line 528 | Local fix §3.4, ещё не push |
| Code Spell & Markdown Lint | `106755316998` | MD046 continuation line 8221 | Local doc fix, ещё не push |

Source/Test Inventory и Node.js Dependency Audit на этом run уже SUCCESS. Финальные coverage/mutation результаты не утверждены. Число jobs может увеличиваться, пока workflow создаёт downstream matrices; не сравнивать частичные counts как регрессию.

После возобновления read-only команды:

```powershell
git status --short
git rev-parse HEAD
git worktree list --porcelain
git stash list
gh pr view 1266 --json state,headRefName,headRefOid,baseRefName,url
gh api repos/egorribun/university_ecosystem/actions/runs/35730420629 --jq '{id,head_sha,status,conclusion,run_attempt}'
gh api --paginate 'repos/egorribun/university_ecosystem/actions/runs/35730420629/jobs?per_page=100' --jq '.jobs[] | select(.conclusion=="failure" or .conclusion=="cancelled") | {id,name,status,conclusion}'
```

- [ ] Получить **все страницы** terminal jobs, логи каждого нового failed/cancelled и соответствующие артефакты.
- [ ] Разделить root failures, downstream aggregate failures, conditional skips и missing evidence.
- [ ] Для каждого issue записать source SHA, tested merge SHA, workflow/run/attempt/job, command, first error, reproduction, test и fix.
- [ ] Не печатать giant SARIF JSON целиком: одна строка может содержать сотни тысяч токенов. Сохранять отчёт в ignored artifacts и парсить нужные поля.
- [ ] Rerun отдельных jobs допустим для доказанной transient проблемы на неизменном SHA с корректной attempt provenance. Новый source fix требует нового SHA/run; старый зелёный job не доказывает новый source.
- [ ] Не повышать timeout и не перезапускать весь suite вместо классификации причины.

История, только для диагностики:

- `35724213801`, source `2fdb2e2...`, tested merge `9d811b29cf09fa9e96dbb8081b3b342dc885320b`: 119 jobs, 95 success/4 failure/20 skipped; 2530 s wall. Dependency/inventory/coverage/aggregate failures исправлялись опубликованным пакетом. Mutation downstream skipped.
- `35635039077`: Python group 67 killed 15/15, но upload 403; frontend aggregate отверг `shard-001:2 Timeout`. Ни один из этих частичных результатов не закрывает gate.
- Старые присланные 25+, 82, 140 failures других run не являются автоматически текущим backlog; переносить только подтверждённые незакрытые причины.

## 5. Следующая сессия: закончить локальный пакет без потери работы

### Task A — безопасный resume и inventory

- [ ] Прочитать §1 и проверить HEAD/status/stash/worktree, user audit hash, stopped container и текущий PR. При новых пользовательских изменениях не применять старые assumptions.
- [ ] Проверить доступность tools фактическими read-only командами: gh GitHub read, Python/uv, Node/npm, Docker; наличие skill files/MCP — через доступный registry, не обещать «полный доступ ко всему» по настройке sandbox.
- [ ] Не восстанавливать вручную task handles из старого чата. Проверить active agents/processes, не запускать дубликат живой сборки.
- [ ] Зафиксировать fresh CI terminal state либо bounded live state. Не делать новый push только для косметики.

### Task B — завершить canonical WASM и combined verification

- [ ] Выполнить §3.1 до strict second-clean-build evidence.
- [ ] Повторить точечные и общие проверки **после** переноса generated artifacts.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_mfa_postgres_acceptance_contract.py tests/test_semgrep_sarif_validator.py -q --no-cov -o cache_dir=artifacts/pytest-cache/resume
.venv/Scripts/python.exe scripts/quality/generate_test_inventory.py
.venv/Scripts/python.exe scripts/quality/check_orphans_and_anti_patterns.py
.venv/Scripts/python.exe verify_harness.py --repo-only
.venv/Scripts/python.exe scripts/fast_preflight.py --help
git diff --check
```

Из `frontend/`:

```powershell
node scripts/verify-wasm-artifacts.mjs
node --test scripts/verify-wasm-artifacts.test.mjs scripts/wasm-source-provenance.test.mjs scripts/wasm-runtime-smoke.test.mjs scripts/challenger-adversarial.test.mjs
npm run typecheck
npm run lint
npm run test:wasm
npm run build
```

- [ ] Выполнить worker Vitest focused tests и email/TOTP Playwright на свежем build с настроенным штатным preview и CI browser; не копировать ad hoc browser overrides в репозиторий.
- [ ] Запустить actual parallel fast-preflight с его проверенными текущими flags/defaults; сохранить JSON, SHA, duration и exit codes. `--help` выше — discovery, не проверка качества.
- [ ] Проверить source/test inventory после новых root tests; не добавлять orphan exceptions ради зелёного.
- [ ] Повторить pre-commit изменённых файлов, actionlint/security там, где затронуты boundaries; проверить zero warnings отдельно от exit 0.
- [ ] Проверить весь diff независимым reviewer: spec compliance, correctness/security, generated provenance.

### Task C — coherent commits и push

**Критический concurrency урок:** pre-commit автоматически stash-ит unstaged tracked changes. Никогда не запускать commit/hooks, пока субагенты редактируют файлы. Сначала заморозить всех writers и подтвердить это.

- [ ] Разбить пакет по смыслу: MFA PostgreSQL fixture; email-MFA browser contracts; Semgrep ledger regression; Rust/worker/generated artifacts; актуальный docs checkpoint.
- [ ] Stage явные пути, не `git add .`; внешний user audit не включать.
- [ ] После detect-secrets/pre-commit снова `git add .secrets.baseline`; проверить реальный diff, не создавать пустой шум.
- [ ] Commit maintenance scopes `test(contracts)`, `fix(security)`, `fix(quality)`, `docs(quality)`; без wave labels и без co-author trailers.
- [ ] Не bypass hooks. Если hook изменил файл — review, повторный stage и verification.
- [ ] Push обычный в `egorribun` после combined readiness. Записать точные SHAs; не force-push и не merge.
- [ ] Обновить §148 ссылкой на handoff и новые доказательства; старые timestamps/SHA не выдавать за новые.

## 6. Внешний аудит: фактический remaining scope

59 CLOSED / 2 DECLINED / 2 OPEN в пользовательском файле — его отчёт о другом checkpoint, **не сертификат текущей ветки**. Сам файл сохранить. Повторная оценка нашла BE-08 transport gap; дополнительно доказана возможность canonical WASM на локальном Linux.

### 6.1 BE-02: defaults и migration semantics

Текущее metadata inventory: 82 dual / 52 Python-only / 0 server-only, 45 tables. Из 52 Python-only: 40 application-owned exceptions — 37 UUIDv7, 1 CSPRNG secret, 2 JSON defaults. Их нельзя «закрывать» копированием Python logic в server_default.

12 оставшихся semantic candidates:

1. `attachments.created_at`;
2. `chats.created_at`;
3. `chats.updated_at`;
4. `dead_letter_jobs.created_at`;
5. `dead_letter_jobs.updated_at`;
6. `failed_outbox_events.failed_at`;
7. `grades.created_at`;
8. `grades.updated_at`;
9. `message_reactions.created_at`;
10. `messages.created_at`;
11. `stored_events.created_at`;
12. `users.role`.

- [ ] Прочитать ADR-036 и source inventory; определить UTC/time-of-statement vs transaction, ORM/onupdate vs direct SQL, enum cast semantics.
- [ ] Для каждого кандидата записать решение и тест direct-SQL/ORM equivalence либо обоснованное application ownership.
- [ ] Перед DDL выполнить fail-closed deployed catalog preflight: типы, defaults, nullability, NULL rows, расхождение `'pending'`/`'PENDING'`/`'pen ding'`.
- [ ] Реализовать phased/backfill/check/validate migration там, где требуется; проверить реальный PostgreSQL upgrade/downgrade/re-upgrade, lock budget и rollback.
- [ ] Не считать локальную metadata таблицу доказательством состояния внешней БД; destructive migration только после проверки target и полномочий.

### 6.2 BE-08: CDC

`asyncpg.connect(replication="database")` не поддерживается; `put_copy_data` отсутствует. Исправлен безопасный startup rejection **до side effects**, сохранён default polling. Keepalive больше не подтверждает WAL за пределами успешно отправленных событий. ADR-037 фиксирует deferred transport.

- [ ] Не называть fail-closed отключение «работающим CDC».
- [ ] Для включения нужны поддерживаемый replication transport, transaction/replay ownership, реальные PostgreSQL/NATS restart/replay/ack tests, durable checkpoint и backpressure.
- [ ] Если CDC не входит в функциональный MVP, получить явное согласование такого scope; без него строка остаётся deferred/open, а не DONE.

### 6.3 RUST-P3-03 и declined рекомендации

- [ ] Завершить §3.1 и runtime/provenance evidence для Base64 export.
- Не отменять без новых доказательств declined `RUST-P3-01`: общий Cargo workspace объединяет несовместимые feature graphs и меняет cache/profile contracts.
- Не ослаблять `INFRA-12`: main-only retention cleanup обязан fail-closed при отсутствии обязательных secrets, а не warn-and-skip.
- [ ] Пересмотреть остальные закрытые audit IDs по mapping source/test/evidence на final SHA, включая дубликаты GO/SEC, без повторной ненужной переписи.

## 7. Master plan stages 0–10: обязательная остаточная приёмка

Существование компонента и локальный unit PASS не доказывают всю строку. Для каждой acceptance строка evidence должна содержать SHA, сценарий, роль/язык/device/state, команду, результат и артефакт. Missing evidence обозначать OPEN/EVIDENCE-BLOCKED.

### Stage 0 — foundation и доказательства

- [ ] Source head, tested merge SHA, artifact SHA и resulting main разделены и проверены.
- [ ] Нормализатор отвергает чужой SHA/hash, пустой/partial/stale/missing report, недопустимую reuse другого run/attempt.
- [ ] Manifest schema, metric capabilities, source roots, versions, timestamps, workflow provenance согласованы.
- [ ] Harness 29/29 либо актуальный полный больший набор; inventory и отсутствие accidental artifacts.

### Stage 1 — общая дизайн-система, a11y и performance

- [ ] Component inventory: typography/spacing/radii/elevation/focus/motion, loading/empty/error/offline.
- [ ] Buttons/fields/tabs/cards/dialogs/popovers едины, focus виден/не перекрыт; targets >=44×44 по внутреннему контракту.
- [ ] Glow и тяжёлые декоративные hover/layout-анимации отсутствуют в утверждённых местах; частые transitions используют transform/opacity и reduced motion.
- [ ] Timers/observers/portals/object URLs освобождаются; повторяемые сценарии дают memory plateau.
- [ ] WCAG 2.2 AA: keyboard, focus order/trap/restore, Accessible Authentication, zoom 200%, contrast, axe без serious/critical и screen-reader smoke.
- [ ] LCP p75 <=2.5 s, INP <=200 ms, CLS <=0.1; LHCI >=95 на ключевых маршрутах; main JS <500 KB; lab score не заменяет field CWV.
- [ ] Visual/Storybook baseline покрывает актуальную систему, без слепого обновления snapshots под regression.

### Stage 2 — auth/MFA и removal

- [ ] Login/register auth-shell, autocomplete/password managers, safe redirect, CSRF, lockout/offline/error, SSR без hydration mismatch.
- [ ] Public normal MFA union `totp | email_otp`, emergency recovery отдельно; runtime/API/schema/UI/generated SDK без WebAuthn. Historical migration data не путать с активным runtime.
- [ ] Destructive credential migration preflight: TOTP → totp; verified email → email_otp; account без применимого безопасного пути блокирует migration до remediation.
- [ ] Email OTP: 6 CSPRNG digits, 10 min TTL, 5 attempts, 60 s resend cooldown, digest/HMAC at rest, one-time consumption, atomic rotation, binding user/challenge/session/fingerprint, IP/user limits, no enumeration/secret leakage.
- [ ] `/auth/mfa/verify` и `/auth/mfa/email/resend`: correct challenge token/revision/expiry/counters/hint; stale code сразу недействителен.
- [ ] Real transactional outbox/SMTP RU/EN: delivery/failure/retry и expired/replayed/wrong/rotated/attempt-exhausted cases; concurrent verify/resend, fingerprint mismatch.
- [ ] Recovery one-use, TOTP, session revocation/trusted devices/reset, roles; PostgreSQL и mocked E2E доказательства §3 не заменяют целый journey.
- [ ] OpenAPI/SDK/MSW deterministic regeneration и zero drift.

### Stage 3 — shell

- [ ] Navbar passive scroll + rAF/hysteresis; stable layout height/CLS; mobile/desktop state parity и reduced motion.
- [ ] Footer groups, official Telegram SVG, external-link labels, responsive layout.
- [ ] MobileMenu focus trap, escape/backdrop, scroll lock, safe areas, быстрые повторные taps без mount races.
- [ ] Bottom nav equal hit sectors, centered icons, один active state, ARIA/keyboard, virtual keyboard/browser chrome.
- [ ] Visual widths 360/390/768/1024/1440 и stress быстрых переходов.

### Stage 4 — scroll/filter/map

- [ ] New route restoration по route key; search/filter сохраняет viewport; modal/detail возвращает anchor/offset.
- [ ] News/Events categories без scroll-to-top/remount; Events/Activity slider geometry и hitboxes согласованы.
- [ ] Map lazy import и idle/intent prefetch, один instance, memo layers/markers, clustering больших данных.
- [ ] Local gesture/overscroll containment не блокирует страницу; wheel/touch/pinch/end interaction не сдвигают внешний viewport.
- [ ] Reduced-motion/weak-device effects, map workers/listeners cleanup; измерение long tasks/memory, не только URL assertions.

### Stage 5 — dashboard/content/Stories

- [ ] Карточки/skeleton-to-content geometry, без лишней empty высоты, wobble/glow; сохраняются CRUD/detail/bookmarks/registration/admin.
- [ ] Stories только с интерактивного avatar/circle; preload следующей, visibility/interaction pause/resume, keyboard/swipe, focus/ARIA, portrait/landscape.
- [ ] Repeated-open/close memory plateau, cleanup media/timers/listeners.
- [ ] Content empty/error/offline/pagination, stable query keys, no duplicate fetch, optimistic rollback.

### Stage 6 — messenger

- [ ] Desktop dialogs/chat/context и mobile back navigation; unread/typing/delivery/read/edited/reply/files.
- [ ] Virtualizer keys/measurements, prepend anchor, autoscroll только у конца; user-reading позиция сохраняется.
- [ ] Real REST hydration + WS dedup/order, reconnect/backoff/offline, retry/idempotency.
- [ ] DM/groups/edit/delete/reply/forward/reactions/receipts/attachments/permissions, oversize frames/files.
- [ ] `role=log`, polite announcements, keyboard composer и accessible attachment/reaction controls.
- [ ] Go race/load/security, delivery latency, goroutine/socket cleanup при restart и disconnect.

### Stage 7 — profile/settings/activity/i18n

- [ ] Gap-аудит существующих profile Header/Details/Editor/Achievements/NowPlaying, не перепись с нуля.
- [ ] Stable Query updates, upload previews/cleanup, тяжёлые sections/rerenders; save/validation/rollback/error.
- [ ] Settings General/Profile/Security/Notifications/Sessions/Integrations, responsive navigation сохраняет state, email MFA без WebAuthn.
- [ ] Activity heatmap/trends/grades/participation/attendance/timeline и единый period; empty/partial/error; табличная доступная альтернатива графикам.
- [ ] RU/EN parity, нет raw keys; interpolation/plural/date/number; backend email/notification translations; dynamic keys scanner.

### Stage 8 — уведомления

- [ ] Пять canonical topics: `news.published`, `schedule.changed`, `events.published`, `chat.message.created`, `system.release`.
- [ ] Один notification ID/metadata для in-app/live/Web Push, dedup и согласованный unread count.
- [ ] Topic opt-in/quiet hours/permission semantics на backend/frontend.
- [ ] Permission request только после понятного действия, не при первом render; default/granted/denied/unsupported; после отказа не повторять без команды пользователя.
- [ ] Real push/deep links/offline/reconnect/stale endpoints/admin publication по всем пяти topics. Mocked PushManager не сертификат реальной доставки.
- [ ] Общие уведомления не расширять на email-канал; email здесь для MFA.

### Stage 9 — полная quality closure

- [ ] Python fresh 100% line/branch/applicable metrics, strict mypy/Ruff/AST, полный mutmut inventory; 100% viable, нет survivor/timeout/no-test/unclassified.
- [ ] Frontend typecheck/lint:all/RUEN/unit/integration/WASM/E2E/SSR/build; merged four metrics100%; Stryker100% viable и полный source universe.
- [ ] Go fmt/vet/golangci/race, required components statements100%; unsupported branch/function явно N/A, не фиктивные100%; Go mutation governance закрыта evidence, не молчаливым omission.
- [ ] Rust четыре компонента, all-target tests, llvm line/function/branch, source-proven zero-branch derivation только где применима, deny/fuzz bounded.
- [ ] API: все фактические shards и aggregate из текущего workflow; исторические «4/8» не использовать без проверки; OpenAPI/SDK/mock/contracts drift0.
- [ ] Security: pre-commit/detect-secrets/gitleaks/Bandit/Semgrep/CodeQL/actionlint/Checkov/dependency/license/image scans, SBOM/provenance; нет незакрытых high/critical.
- [ ] Infra: Compose matrix, Helm, wrapper envsubst, Kyverno, ExternalSecrets/TLS/HPA/resources.
- [ ] Manifest schema-valid/current identity, hashes и native/derived/unsupported; source inventory complete, missing reports empty.
- [ ] Каждый skip доказан `if:` и не исключает обязательный gate данного event.
- [ ] Реальные предупреждения build/local tooling разобраны; exit0 не объявляется zero-warning.

### Stage 10 — Docker, staging, release

- [ ] Проверить все поддерживаемые Compose combinations `config --quiet`; не запускать overlays отдельно, если они зависят от base.
- [ ] Реальный путь `start-docker.ps1 -Build`, затем Core/full с измерением RAM/CPU/startup/readiness и корректным shutdown. Не удалять пользовательские volumes и не применять global prune.
- [ ] Backend `/health/ready`, frontend SSR/Caddy, gRPC file processor, WebSocket, PostgreSQL, раздельный Redis, NATS и observability.
- [ ] Real login/TOTP/email, dashboard/news/events/map/chat/profile/settings/activity/push/admin journeys на immutable digest build.
- [ ] Exact-six image producer и manifest: проверить актуальный canonical список, все шесть digests/SBOM/attestations/provenance, source and tested identity.
- [ ] Перед promotion подтвердить разрешение merge/release и точный staging target/context/namespace/TLS domains/secrets. Историческое разрешение merge dependabot не blanket permission на production.
- [ ] Resulting main SHA после merge проверяется отдельно; не присваивать ему сертификат PR source/merge SHA.
- [ ] Тот же immutable build на production-like Kubernetes, TLS, ExternalSecrets refresh, resources/HPA, metrics/logs/traces/alerts.
- [ ] Real browser/device matrix, field CWV, chaos/restart и rollback с доказательством сохранности данных.
- [ ] Итоговый `AUDIT_QUALITY_CLOSURE_<verified-sha>.md`: команды/exit/duration/counts/metrics/scopes/hashes/images/SLO/security/skips/remaining risks. Audit-only commit не подменяет audited source SHA.

## 8. Сквозная acceptance matrix

| Измерение | Обязательный набор |
| --- | --- |
| Роли | student, staff/teacher, admin |
| Языки | RU, EN |
| Viewports | 360×800, 390×844, 768×1024, 1024×768, 1440×900 |
| Браузеры | Последние две Chrome/Edge/Firefox/Safari; реальные iOS Safari/Android Chrome |
| Состояния | loading/empty/partial/success/validation; 401/403/404/409/422/429/5xx; offline/reconnect/timeout |
| A11y | keyboard/focus/200%zoom/reduced motion/contrast/axe/screen reader |
| Performance | cold/warm, slow CPU/network, large histories/data, repeated lifecycle, memory plateau |
| Reliability | duplicate/retry/idempotency/concurrent mutation/restart/stale cache/dependency failure |
| Security | CSRF/redirect/XSS/session/replay/fingerprint/traversal/oversize/secrets+PII |
| Visual | auth/shell/dashboard/news/events/map/chat/profile/settings/activity/notifications/admin |

Playwright browser engines и mobile emulation не равны реальным branded versions/devices. Не утверждать универсальную матрицу по одному desktop Chromium. Существующий тест можно зачесть только после проверки его assertions и scope.

## 9. Все девять организационных задач с исходного изображения

### O1 — machine-readable timing/resource ledger

- [ ] Job/run/source/attempt timestamps: queue/setup/test/upload, peak concurrency, retries, timeout cause; CPU/RSS измерять instrumentation, Jobs API их не предоставляет.
- [ ] Проверить overlap всех workflows в общем account cap20, а не одного Matrix.
- [ ] Существующие analyzer/renderer использовать повторно; unsupported fields помечать явно, не нулями.
- Baseline `35724213801`: queue p50/p95 63/386 s, setup34/98, test51/725, peak19. Mutation не запускалась; 42 минуты не сравнимы с полным mutation run.

### O2 — duration-aware sharding

- Python cost-aware execution и frontend same-run retry history уже есть; **совместимая cross-run history ещё OPEN**.
- [ ] Создать отдельный `scripts/quality/select_stryker_history_artifact_cli.py`; тесты `tests/test_select_stryker_history_artifact_cli.py`, `tests/test_stryker_cost_workflow_contract.py`, planner contracts в `frontend/scripts/run-stryker.test.mjs`.
- [ ] Проверять config/lock/toolchain/test-input/preflight-inventory fingerprints, trusted producer, digest, finite costs каждого current viable source.
- [ ] Ограничить runs/pages/bytes/entries/age и общий monotonic deadline. В архиве ровно один regular cost JSON; reject links/extra/executable/cache payloads.
- [ ] Invalid/stale/incomplete history → diagnostic и безопасный existing planner fallback; **никогда reuse test/mutation results**.
- Не ослаблять `select_same_run_artifact_cli.py`. `download_stryker_cost_artifacts.py` сейчас не вызывается workflow; его полировка не ускоряет текущий CI.

### O3 — сокращение повторного setup

- [ ] Измерить critical path/setup cache hit/miss; immutable dependencies/artifacts только с проверкой совместимости и trust boundary.
- [ ] Не исполнять untrusted cache в privileged release; read-only PR caches и producer identity разделить.
- [ ] Не путать экономию runner-minutes с улучшением wall time/очереди.

### O4 — mandatory/advisory/nightly

- [ ] Сверить live main ruleset с exact produced check contexts и workflow guards.
- [ ] Документировать событие/guard/required status; не переносить обязательную проверку в nightly ради ускорения.
- [ ] Изменение branch protection требует отдельного согласования, не implied autonomous optimization.

### O5 — retries только transient

- [ ] Классифицировать network/runner/upload errors, сохранить first failure/artifacts; bounded attempts и backoff.
- [ ] Product assertion, survivor, no-test, deterministic crash не retry-until-green.
- [ ] Проверить mixed-attempt aggregation fail-closed; upload403 не превращать в killed certificate.

### O6 — check/artifact/owner/runbook catalog

- [ ] Existing catalog covers56 workflows/185 source jobs на предыдущем checkpoint; проверить актуальное количество.
- [ ] У каждой проверки canonical name, owner role, inputs/outputs, expected measured duration, troubleshooting и skip reason.
- [ ] Catalog validator и tests должны ловить drift; не создавать параллельный несвязанный каталог.

### O7 — CI health report

- [ ] p50/p95 PR completion/queue/setup/test/upload, critical path, failures/retries/timeouts/skips, quality evidence identity.
- [ ] Указывать population/window/sample count; timeout budget не наблюдаемая duration; lower bound не прогноз.

### O8 — local fast-preflight

- [ ] `scripts/fast_preflight.py` уже существует; verify6lanes на combined candidate, bounded parallelism и machine JSON.
- [ ] Не запускать mutating npm installs/build generators параллельно с hooks или writers.
- [ ] Отдельный writable pytest cache для каждого worker/task; старый `.pytest_cache/v/cache` выдавал Windows access denied. Не исправлять это широкими ACL/recursive delete; документировать и использовать owned artifact cache.

### O9 — heartbeat watchdog

- [ ] Existing mutation deadlines/partial reports не равны общему heartbeat watchdog.
- [ ] Нужен heartbeat с PID/process group/stage/last progress/resource counters, bounded graceful shutdown и сохранение partial reports.
- [ ] Отличать долгую законную компиляцию от зависания; test silent-live, stale heartbeat, finished process, orphan-child, signal escalation.
- [ ] Не повышать общий timeout без root-cause evidence.

### Контролируемый A/B после трёх comparable green runs

- [ ] Baseline сохранить на существующем budget (frontend max-parallel6 /64 shards на текущем checkpoint; перепроверить YAML).
- [ ] Затем по одному варианту: max-parallel7, затем8 **либо** lane split8/8,9/7,7/9.
- [ ] Сравнить queue/starvation/RSS/CPU/timeouts/criticalpath/full evidence; rollback при ухудшении или потере provenance.
- [ ] Не обещать обход account cap20. Избыточный matrix fan-out расходует очередь, а не создаёт новые slots.

## 10. Spelling, docs и dependency follow-up

### 10.1 Dormant spelling gate

`cspell.json` содержит `ignorePaths: ["**/*"]`. Exact action-style command с `--no-must-find-files` проверяет0files и выходит0. Markdownlint при этом реально работает. Это открытый quality defect.

Диагностика: CSpell10.2.2, sample3832trackedtext,27862unknown occurrences, приблизительно2071unique nongenerated; **не 27862 опечатки**. Imported skills/lockfiles исключены только из диагностического sample, не как approved release exclusion. RU dictionary2.3.2 имеет GPL3 dev-tool licensing consideration; dialect EN policy тоже определить.

Пользователю уже предложен выбор scope: начать с authored current docs либо сразу весь authored code/docs. Ответ в текущем контексте не получен. Не объявлять это blocker для остальных задач и не молча урезать gate.

- [ ] Зафиксировать authored/generated/vendor/historical boundaries по policy; уточнить scope если решение меняет обязательность.
- [ ] Добавить CLI/action canary: нормальный RU/EN проходит; `mispeling` и `ашибка` приводят к failure. Document API, обходящий path filtering, недостаточен.
- [ ] Убрать universal ignore, исправить настоящие опечатки и точечно документировать технический словарь.
- [ ] Не исправлять intentional invalid fixtures (`pullPolcy`, `Привед`, `gmial`) и не добавлять их в глобальный whitelist.
- [ ] Проверить свежий gate реально scanned files>0, RU/EN, lock reproducibility, license scan.
- Diagnostic scripts/data: `C:/Temp/cspell-audit-2ca7a320bb8d4eb887723d376a5c7268/`.

### 10.2 Documentation hygiene

- [ ] Одна активная roadmap с traceable task IDs; handoff — snapshot, external audit — input, historical prompts marked.
- [ ] Reference scan перед move/delete; не удалять original reports/пользовательский untracked audit как «мусор».
- [ ] Обновить заявленные toolchain версии/commands на verified current source, исправить outdated pass claims, проверить local links/anchors/remote URLs по отдельности.
- [ ] Привязать every acceptance requirement к evidence/backlog, а не надеяться на множество разрозненных checkbox.

### 10.3 Dependabot/default branch

На проверенном branch lockfiles affected versions patched: anyio4.14.2, httpx2/httpcore2 2.12.0, urllib3 2.7.0, js-yaml4.3.2, Go OTel1.46.0/grpc1.83.2. Все16open default-branch alerts просмотрены; пять Go alerts ссылаются на старые записи dependency graph, который содержит одновременно old/new versions.

- [ ] Перед promotion обновить live alerts, SBOM и dependency graph provenance; проверить отсутствие реально используемого старого graph/module.
- [ ] После main promotion проверить fresh graph; не dismiss alert и не bump dependency только ради скрытия stale record.
- [ ] Не считать npm audit0 доказательством чистоты Python/Go/Rust/images или всего default branch.

## 11. Организация субагентов после возобновления

Сейчас доступны максимум четыре active slots: lead + три workers. Параллелить независимые scopes, не количество ради количества. Skill инструкции читать целиком главным агентом до выполнения; subagent reading не заменяет это.

| Роль | Ближайший bounded scope | Запрет пересечения / выход |
| --- | --- | --- |
| lead | Live CI triage, ownership, docs ledger, integration и commit | Единственный stage/commit/push coordinator |
| Rust implementer/perf | §3.1 canonical generated WASM, затем Docker producer gap | Только crypto/worker/generator files; toolchain/hash/repeat proof |
| QA/backend | Real MFA/outbox acceptance либо BE02, один выбранный slice | Не менять shared workflows без передачи ownership; RED/GREEN/JUnit |
| independent reviewer | Read-only spec/security/provenance review законченного slice | Не быть автором reviewed patch; findings с файлами/линиями |

После освобождения slots возможны отдельные bounded задачи map lifecycle, real WS contracts, Push topics или CI cost selector. Не запускать одновременно npm installs/formatters/генераторы по одной dependency tree. Не создавать новые user-owned Codex tasks вместо настоящих subagents без запроса пользователя.

Предыдущие agent names помогают найти сообщения, но не гарантируют живые handles:

- `bound_cost_download`: email-MFA E2E и Semgrep; DONE.
- `dependency_alert_reassessment`: dependency audit и WASM; interrupted при pause.
- `spell_gate_audit`: spelling diagnostic и MFA PostgreSQL fixture; DONE.
- `review_mfa_fixture`: независимое fixture/E2E/Rust source review; DONE, generated artifacts ещё не review.

Пример bounded dispatch: «Прочитай domain AGENTS/quality и relevant skill; только указанные файлы; воспроизведи RED, implement, focused tests; никакого stage/commit/deploy; верни причины, diff, commands/exit/counts, resource cleanup и ограничения». Каждый автор → spec review → независимый code/security review → combined gate. Не ожидать часами без проверки живого процесса/прогресса.

## 12. Полномочия, инструменты и неразрешённые внешние шаги

Проверены в этой работе: Git/gh read+обычныйpush, Pythonvenv, npm/Node, DockerLinux, локальные skills и subagents. Context7/ClickUp/MCP использовать если реально доступны и нужны; отсутствие подключения не блокирует канонические repo docs. `danger-full-access` не доказывает наличие cloud credentials, SMTP, push provider или Kubernetes доступа.

Нужны отдельная актуальная проверка/уточнение перед внешними шагами:

- exact staging kube context/namespace/registry/hosts/TLS/secrets/observability target;
- real test email/push recipients и consent, без рассылок третьим лицам;
- main/release promotion authorization, maintenance/rollback window;
- real devices/branded browsers и достаточное окно field CWV;
- spelling mandatory scope, если пользователь ещё не ответил;
- статус deferred CDC относительно functional MVP.

Нет необходимости спрашивать пользователя о каждой локальной тестовой правке. Но нельзя считать старое автономное поручение разрешением на destructive production migration, bypass, произвольное merge или изменение прав доступа.

## 13. Evidence и финальная проверка полноты

Для каждого task хранить: ID/requirement, owner, source SHA, tested SHA, run/attempt/job, command/toolversions, OS/env, start/end/duration, exitcode, test count, coverage numerator/denominator, mutation outcomes, artifact paths/hashes, reviewer, ограничения и next action.

Существующие полезные paths:

- `artifacts/quality/ci-health-35724213801.json` и `.md` — partial-run diagnostic;
- `artifacts/quality/model-default-inventory-0ec4fed3a.json`;
- `artifacts/quality/mfa-postgres-root-review.xml`;
- `artifacts/fast-preflight/fast-preflight.json` — старый tested SHA c082;
- `artifacts/wasm-linux-baseline-0ec4fed3a/` — bootstrap/source/change archives;
- `frontend/test-results/` — local Playwright traces;
- `C:/Temp/mfa-pg-audit-46512ec3ab764826822be98f478a4b9a/`;
- `C:/Temp/cspell-audit-2ca7a320bb8d4eb887723d376a5c7268/`.

Ignored artifacts и C:/Temp могут исчезнуть; их отсутствие означает повторную верификацию, не разрешение восстановить цифры по памяти. Не переносить сырые временные артефакты в source history без осмысленной политики. Handoff сохраняет результаты, но не заменяет машинные доказательства.

### Финальная Definition of Done — все строки одновременно

- [ ] Всё обязательное stages0–10 и O1–O9 либо доказанно выполнено, либо explicit user-approved scope change; unknown не DONE.
- [ ] Все applicable coverage metrics100%, viable mutation100%, complete source/test/mutant inventory и fail-closed manifest.
- [ ] Fresh exact-identity required CI green; no unclassified skipped/cancelled/timeout/missing artifacts.
- [ ] Product roles/RUEN/states/devices/a11y/perf/reliability/security matrix подтверждена подходящими реальными проверками.
- [ ] External audit IDs пересмотрены, P0/P1/high/critical findings отсутствуют; deferred boundary согласован, а не скрыт.
- [ ] Exact-six immutable images, DockerCore/full, stagingTLS/observability/CWV/chaos/rollback и authorized release подтверждены.
- [ ] Current docs непротиворечивы; resulting-main/source/tested/audit-only SHA не смешаны.
- [ ] Финальный рабочий каталог не содержит случайных артефактов; судьба пользовательского untracked audit согласована без удаления данных.
- [ ] SHA-bound final audit опубликован; только тогда goal может стать complete.

Этот handoff покрывает известную оставшуюся работу и условия доказательства результата. Он не обещает отсутствия неизвестных дефектов «до каждой строки» и не является сертификатом безупречности. При новой находке — RED, severity/owner/task/evidence, затем исправление или явное согласованное решение.

## 14. Готовая команда для следующей сессии

> Продолжи на egorribun с чтения AGENTS.md, quality/quality-contract.json и docs/superpowers/plans/2026-09-22-mvp-safe-pause-handoff.md. Сначала проверь live Git/PR/CI и сохранённые незакоммиченные изменения. Заверши canonical Rust/WASM Base64 regeneration: исходники изменены, generated export ещё не перенесён, stopped container сохранён. Не теряй локальные MFA/Semgrep/docs изменения и пользовательский untracked AUDIT_PLATFORM_FULL.md. После независимого review и combined gates сделай coherent commits/push. Далее выполняй весь §148 continuation, stages0–10 и девять organizational tasks, сохраняя100% floors, полный inventory и SHA/run provenance. Не merge/deploy/bypass без актуальных полномочий, не объявляй completion по узкому green run. Используй до трёх независимых workers плюс lead, замораживай writers перед hooks/commits.
