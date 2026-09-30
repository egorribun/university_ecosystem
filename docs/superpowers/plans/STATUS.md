# MVP — оперативный статус

Срез на 2026-09-30. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md) содержит решения и
критерии блоков 0–10; [ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые
требования. Goal активен. Блоки 0–3 остаются открытыми до свежего живого запуска
и полного приёмочного evidence.

## Рабочее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git | `egorribun`; implementation checkpoint `a730749868aa38f6c409b2e36ea4845d1ff640ce`, merge `origin/main` (`78b9499079442191920835eed9de93b726cf36a1`) включён. PR #1266 уже смержен. Новый checkpoint ещё требует обычных PR checks и canonical evidence resulting-main SHA; админский bypass и force-push запрещены. |
| Доступ и окружение | GitHub CLI аутентифицирован; token scopes: `gist`, `read:org`, `repo`, `workflow`; scope `packages` не показан, прямой GHCR push не подтверждён. Docker Engine 29.8.1 / Compose 5.5.1: 16 CPU / 23.48 GiB, C: свободно 373.5 GB; WSL2 Ubuntu остановлен, `docker-desktop` запущен. Python 3.14.7, uv 0.11.28, Node 24.21.0, Go 1.27.1 (локально), Rust 1.98.1, Playwright 1.63.0 с установленным Chromium 153. В checkout нет `.env`, kind не установлен. Docker показывает 20 images и 4 неактивных volumes; контейнеров нет, volumes/cache не очищались. |
| Архивы | 120 tracked-файлов / 3,981,581 байт; ещё не удалены. Rescue bundle восстановлен и проверен для SHA `d0aad7c296facd79b3d41b037bc4160f5b3132be`, SHA-256 `7cdaed352df12a0f735f86399dd2937be9c832e60d2f1f0ff66fbbb9bc823b11`. |
| Archive inventory | Полный path/blob/size/disposition/destination ledger сверил 120/120 записей. CSV рядом с bundle дополнен найденной credential reference в `AUDIT_WAVE171.md:118`; новый SHA-256 `20bb5457d104ed2590c33c4940c2f0334f2ba526fb1bff208111f5a99c4cc514`. Шесть архивных отчётов содержат 12 старых ссылок на отсутствующие цели; текущий link-checker без архивов проходит. |
| Секреты в исторических отчётах | `detect-secrets` на трёх ранее отмеченных архивных отчётах прошёл без новых findings. Неизвестные Chromatic-похожие значения и demo-account credential-shaped строка в `AUDIT_WAVE171.md:118` не подтверждены как placeholders/отозванные/rotated. Значения не копировать; решение об удалении архивов и распространении bundle ждёт классификации. |
| Текущий выпуск | Checkpoint `a730749` зафиксировал изменения приложения, CI и документов, но не завершил выпуск. Kind/live acceptance, пользовательское визуальное утверждение и release evidence не завершены. |
| Audit ledger | Предыдущий снимок классифицировал 63 ID: 56 закрыты с evidence, 5 заменены ADR/решениями, BE-02 и RUST-P3-03 оставались открытыми. Это не финальная классификация release SHA. Ledger остаётся tracked до переноса и проверки evidence. |

## Проверки и изменения этого цикла

- `uv run python verify_harness.py` — 27/27 harness checks passed на Python 3.14.7.
- `uv run python scripts/fast_preflight.py --max-workers 3` — 9/9 lanes passed on
  the dirty workspace; local report is `artifacts/fast-preflight/codex-d0aad7c-20260930.json`.
  This is not SHA-bound release evidence; current-commit Actions checks are still absent.
- Три quality-evidence ожидания исправлены по фактическому контракту: 14 уникальных
  report paths и три Rust branch reports; набор — 118 passed, 1 skipped на Windows.
- Source/test inventory gate проходит; три динамических `pytest.skip` содержат
  `QUALITY-123` и owner, allowlist не расширен.
- Frozen Python OSV gate проходит с PyJWT 2.14.0. Pinned `govulncheck@v1.7.0` на
  Go 1.26.6 прошёл по 9 модулям без достижимых уязвимостей. Остался
  dependency-only `GO-2026-5932` для неимпортируемого `openpgp` без известного fix.
- CSpell `SPIFFE` добавлен в словарь; CSpell CLI локально доступен через `npx`, но
  русскоязычные планы не являются целью English spellcheck. `docs/adr/README.md`
  прошёл целевой запуск. Повторный полный secret hook на исправленном ledger ранее
  прошёл; baseline после запуска повторно staged.
- Admin visual smoke проверяет 5 маршрутов × RU/EN × light/dark и полные
  sidecar/artifact evidence. Последний Node suite — 13 passed; live workflow пока
  не запускался.
- Live-stand CLI имеет read-only `status`, data-preserving `stop`, отдельный
  owner-checked `teardown`, случайный Compose project, HMAC-подписанный ownership
  marker и lifecycle lock. Reparse-point preflight защищает worktree, `.secrets`,
  marker/VAPID и создаваемые `.env*`/key paths; dirty tracked worktree отклоняется
  до `compose stop`. Suite — 31 passed на Windows, включая junction/dangling-link
  regression cases. Docker startup + S3/Compose contracts — 108 passed.
  Изолированный запуск на SHA `d0aad7c` прежде создал конфигурацию в `../ue-live`,
  но остановился до Compose на проверке `WASM_SOURCE_PROVENANCE.json`; контейнеры,
  volumes и networks не создавались, принадлежащие сборке images сохранены.
- Outbox retry starvation для `batch_size=1` и больших batches исправлен; последний
  целевой набор — 56 passed, `app/workers/outbox.py` имеет 100% line/branch coverage.
  Mutmut остаётся непроверенным; контракт не обходили.
- WS-hub: полный `go test ./...`, `golangci-lint run` и `go test -race ./...` прошли
  на pinned `golang:1.26.6-bookworm` digest после явного unlock на всех ветвях
  `WritePump`. Детерминированный тест проверяет membership stripe
  во время заблокированной записи и порядок относительно auth denial; 100 повторов
  прошли. Дополнительный тест не даёт room-scoped
  error payload обойти revoke; точное служебное notice остаётся доставляемым.
  User-wide invalidation принимает пустой `room_id` только без eviction; eviction
  и остальные room-scoped события требуют UUID. Go tests, lint и race прошли;
  кроссплатформенные contract-helper cases — 4 passed. Четыре Pact-интеракции
  локально пропущены: pact-python недоступен в Windows окружении.
- Независимый WS review не нашёл auth/order bypass. Остались два не измеренных
  эксплуатационных риска: 256 общих membership-stripes удерживаются через socket
  write (deadline 10 s), а per-replica JetStream `DeliverAll` consumer не durable
  и повторно читает до 7 дней retained invalidations после рестарта. Сначала
  нужны профиль 1000 соединений / 500 пар / 100 msg/s / 30 min, slow-reader
  probe и per-replica restart/catch-up evidence; не менять lock/consumer model
  без замеров, shared durable consumer нарушит fan-out.
- Path preflight блокирует существующие symlink/junction до записи, остановки и
  teardown. Условная TOCTOU-гонка между проверкой и открытием требует другого
  локального процесса с правом изменять stand worktree; handle-bound I/O не
  реализовано. Для текущего single-owner стенда это не блокер.
- Release producer/workflow/CWV контракт синхронизирован; независимый review не
  нашёл замечаний. Значения CWV явно передаются в canonical image build; свежий
  набор из release manifest, single producer, workflow, fail-closed, Docker/S3,
  CWV и WASM контрактов — 354 passed. Field CWV вне обязательной MVP-приёмки.
- Удаление участника группы сохраняет transactional outbox и после commit делает
  best-effort WS-hub eviction с тем же event ID; тесты доказывают порядок, отказ
  fast path и безопасный повтор. Три основных файла `test_chat_command_service`,
  `test_chat_command_branch_closure` и `test_outbox_worker` — 64 passed; расширенный
  набор с двумя event-handler файлами — 84 passed. Ruff, format и targeted mypy
  прошли. Ошибка cache invalidation больше не мешает
  попытке WS fast path; cache exception сохраняет прежний error contract.
  Невалидная повреждённая строка outbox может повторяться без DLQ, но нормальный
  producer всегда пишет оба ID; это poison-event observability/recovery edge.
- WASM provenance drift разобран на pinned Linux builder: отличаются ровно два
  `.wasm` package и две записи `packages`; inventory шести source files и
  `source_tree_sha256` неизменны. Старые бинарники содержали Windows backslashes,
  новые — Linux slash paths. Бинарники заменены выводом builder, provenance
  пересоздана тем же writer; local и pinned Node 24 verifier прошли, WASM suite —
  23 passed, потребители — 32 passed. Это локальное подтверждение, не CI-attestation.
- Docker `deps` stage прошёл verify и `npm ci` (2109 packages, 0 npm vulnerabilities).
  Production `builder` stage теперь использует ту же конечную пару, что Linux CI:
  RSS 2048 MiB / V8 heap 1536 MiB. Весь build завершился; локальный intermediate
  image ID `sha256:19f8e791d1a92a715568c2cbe7701bb61c579eabb095b86b865ac2556ff17722`.
  Это проверка dirty working tree; SHA-bound reusable CI producer ещё нужен.
- Полный production frontend `runtime` stage собран успешно; production npm install
  добавил 390 packages, аудит 392 packages нашёл 0 vulnerabilities. Локальный
  image ID/RepoDigest для `linux/amd64` —
  `sha256:9340427f8869d4f4b4cd07a8fb392f8cec1e31ee6d9d2cf8689b8426a4794ae1`.
  Изолированный container без сети и volumes прошёл штатный `/healthz`; после
  проверки удалён только контейнер с подтверждёнными метками этого smoke-run.
  Это локальное evidence для dirty tree, не релизная аттестация.
- Обычный link checker прошёл для 547 Markdown файлов; 9 link-checker tests passed.
  `--include-archives` ожидаемо находит 12 исторических broken targets, пока архивы
  не удалены. Исправлены неверные CWV-пояснения в обеих версиях DEPLOY; повторный
  link-check прошёл. Визуальные baseline без пользовательского утверждения не
  менялись.

## Ближайшая работа

1. На актуальном проверяемом SHA повторить isolated live stand, readiness и
   применимые Docker/live/S3 contracts; получить новый канонический CI verdict
   через обычный commit/push/PR до использования этих результатов как evidence.
2. Классифицировать все credential-shaped значения в архивах: подтвердить
   placeholder/отзыв/ротацию либо обработать как потенциально действующие. Не
   раскрывать значения и не распространять rescue bundle до triage.
3. Пересмотреть 63 audit ID на итоговом SHA; отдельно закрыть BE-02 и
   RUST-P3-03 по согласованным критериям. User visual approval для baselines не
   заменять автоматическим тестом.
4. Удалять два архива раздельными логическими коммитами только после полной
   классификации/переноса, проверки оба link-checker modes и восстановления.

## Постоянные границы

- Не ослаблять 100% применимые coverage и viable mutation contracts; не добавлять
  необоснованные exclusions, quarantine, timeout inflation или ручной статус.
- Разрешён обычный цикл commit/push/PR/merge/GHCR/release. Нет admin bypass,
  force-push, branch-protection изменений и переписывания Git history.
- Не удалять существующие пользовательские volumes, `.env`, backups или данные;
  историю миграций не сжимать. Удалять только принадлежащие прогону ресурсы.
- Kubernetes MVP использует Envoy Gateway + Gateway API. Внешний production,
  реальные SMTP/push-провайдеры, физические устройства и field CWV вне MVP.
- Визуальные комплекты/baselines требуют пользовательского утверждения. Не
  добавлять новые обязательные MFA правила или предметные Activity-функции.
