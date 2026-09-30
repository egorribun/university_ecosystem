# MVP — оперативный статус

Срез на 2026-09-30. [Мастер-план](MVP_MASTER_PLAN.md) содержит решения и этапы;
[ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые требования. Goal активен;
приёмка и выпуск `v1.0.0` не завершены.

## Состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | В PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) удалённо опубликован head `849f1f1b3b0699f8a36e1039a97f6ae297d1060a`; он включает security fix `87352a6` для Playwright output paths и статусный срез. PR [#1307](https://github.com/egorribun/university_ecosystem/pull/1307) на `67e4033194f118c5fd4ba9b3c3752debdaf40081`: PyJWT lock reconciliation и rationale-маркеры у трёх динамических test skips. Оба PR основаны на актуальном `main`=`78b9499079442191920835eed9de93b726cf36a1`. |
| CI / Ruleset | Перед push #1306 последний полный срез имел 81 required pass и 2 Python shards in progress; после push `849f1f1b3` свежий required CI [run 36723909059](https://github.com/egorribun/university_ecosystem/actions/runs/36723909059) выполняется. На прежнем #1307 head `b72320b4` было пять required failures: CSpell (`SPIFFE`), Go advisory `GO-2026-6443` (gRPC 1.84.0), Node advisories `brace-expansion` и `detect-secrets` на историческом `AUDIT_LOG_SECRET`; Source/Test Inventory теперь адресован маркерами на `67e403319`. Новый run [36723689650](https://github.com/egorribun/university_ecosystem/actions/runs/36723689650) по этому SHA ещё выполняется. Независимая проверка установила, что fixes для CSpell и npm lockfile уже есть в #1306; перенос на #1307 и двухмодульная Go workspace remediation готовятся. PyJWT 2.14.0 прошёл локальный OSV audit. Live ruleset имеет 91 required context без `Security Policy Integrity`; `quality/release-required-checks.json` требует этот отдельный `pull_request_target_main` evidence profile. Bypass/ruleset changes не делались. |
| Проверки | На SHA `d7218c01baaef58f3d1f9762afc389dd00d9408a` fast-preflight прошёл 9/9; живой full Compose E2E — 18/18 desktop/mobile, 0 failed/skipped. SHA-bound отчёт: `artifacts/live-acceptance/mvp-block-d7218c01-20260930.json`. |
| Локальные проверки | Для `87352a6` прошли `tests/test_live_stand.py` (56), live E2E contract (5), frontend `tsc --noEmit`, ESLint, root pre-commit и Markdown link tests (9); независимый security review output-path fix не нашёл блокеров. Предыдущий SHA `d7218c01b`: 60 launcher/seed тестов, 27 frontend security/admin tests, fast-preflight 9/9, полный live Compose E2E 18/18, link check 429 файлов без broken links. После итоговой правки STATUS повторить `git diff --check` и docs hook. |
| Admin smoke | Коммиты `3061c38`, `3ed3367`, `ca353a9`, `db03ef5`, `a928bed`, `2fcc9e7`, `e96d675` интегрированы после независимого security-review без блокеров; bootstrap дополнен в `f5e8369`, manifest fingerprint — в `ae19006`, root-path routing — в `d7218c0`, последний routing commit независимо одобрен. Admin-пароль новый на прогон; npm получает lockfile bootstrap без тестового пароля, Playwright — минимальный env allowlist и пустые npm configs; stdout/stderr скрыты, выводятся только counts/status; traces/screenshots/video выключены. |
| Live E2E | На `d7218c01` все 18 текущих live specs прошли на desktop/mobile; suite охватывает auth/roles, password reset и один messenger realtime workflow, это ещё не полная MVP-приёмка. В `artifacts/live-acceptance/mvp-block-d7218c01-20260930.json` сохранены SHA, команда, конфигурация, counts и данные среды без secrets. |
| Live stand | `ue-live-97e64749be022c80` использован для прогона на `d7218c01`; после E2E выполнен owned `stop`, все контейнеры остановлены (0 running), 12 принадлежащих проекту volumes сохранены. Принадлежащий worktree и `.env` оставлены. Артефакт подтверждает остановку и сохранение томов, но отдельный лог readiness/Prometheus targets не сохранён. В `.github/workflows` live PR/nightly/manual workflow пока нет. |
| Live workflow budget | Full Compose имеет 34 memory limits суммарно `14176 MiB` (`13.84 GiB`); Core allowlist — `7008 MiB` (`6.84 GiB`), но сейчас не включает Mailpit, нужный password-reset E2E, а live wrapper жёстко запускает full Compose. Стандартный public `ubuntu-24.04` даёт 4 CPU, 16 GB RAM и 14 GB SSD ([GitHub runner specs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)). Перед PR workflow нужны Core+Mailpit orchestration/readiness/limits и измерение RAM, disk и времени; full stack на стандартном runner имеет слишком малый запас. |
| Документация / архивы | В отдельных коммитах удалены 112 архивных audit reports и 8 старых plan snapshots после переноса применимых требований. Rescue bundle и inventory на 120 файлов находятся рядом с repo; `git bundle verify`, blob/size сверка всех путей и sample restore двух файлов прошли. SHA-256 bundle: `7cdaed352df12a0f735f86399dd2937be9c832e60d2f1f0ff66fbbb9bc823b11`; inventory: `20bb5457d104ed2590c33c4940c2f0334f2ba526fb1bff208111f5a99c4cc514`. Bundle не распространять: архивные отчёты содержат строки, похожие на credentials. SEC-03 исправлен: историческое присутствие и ограничения ротации указаны явно. |
| Credentials | Пользователь подтвердил reset Chromatic project token; GitHub Actions metadata `CHROMATIC_PROJECT_TOKEN` обновлена `2026-09-30T10:08:36Z`; значение не читалось. Seeded-admin пароль был только в одноразовой CI-базе. Исторический `AUDIT_LOG_SECRET` HMAC signing-key default обнаружен в 7 из 44 старых revisions; его значение редактировано, текущий production validator отвергает его. Standalone Kubernetes-манифест объявляет Vault mapping; Helm может потреблять existing Secret, но repo не содержит активного release override. В repo-level GitHub Actions secret нет; live cluster/store проверить не удалось. Retained `StoredEvent` hashes могут зависеть от старого ключа, а runbook умеет перерегистрировать только `DataAccessLog`; сначала установить использование и совместимость обоих типов записей, затем решать ротацию. |
| Ruleset | По разрешению пользователя из ruleset `8335285` удалён только retired context `Rust Criterion Benchmarks (pyo3-sanitizer)`. Live GitHub ruleset `main` требует 91 context; `Security Policy Integrity` среди них нет, хотя он отмечен required в `quality/release-required-checks.json`. Python unit/integration, coverage и frontend mutation aliases имеют явные jobs/gates в `ci.yml`; старый run пропустил их вслед за upstream failures. Branch protection и остальные contexts не менялись; bypass не выполнялся. |
| Audit / release | Исторический ledger классифицировал 63 ID: 55 закрыты source/test references, 6 заменены решениями, BE-02 и RUST-P3-03 остались открыты; MIG-PASS-01 проверяется отдельно. Требуется пересмотреть все ID на актуальном release SHA. `kind` CLI не найден в PATH; Gateway API/kind приёмка и шесть GHCR digest-проверок не выполнены. |

## Что подтверждено для архивов

- Bundle и inventory расположены вне репозитория по путям из
  [индекса аудита](../../audits/INDEX.md); история Git не переписывалась.
- Оба режима link checker только что проверили 429 Markdown-файлов, без broken
  links; `tests/test_markdown_links.py` — 9 passed.
- Единственная обнаруженная временная копия sample restore находится в
  `C:\Temp\university-ecosystem-rescue-validation-20260930`. Автоматическая очистка
  была отклонена policy review. Удалить её вручную; не копировать её содержимое.

## Следующие шаги

1. Получить результаты новых CI #1306/#1307; закрыть остающиеся dependency,
   spelling, secret-triage, Go workspace и inventory gates на точных SHA.
2. Отправить исправленную SEC-03 evidence correction обычным PR update; до любой
   ротации установить, зависят ли retained `DataAccessLog` и `StoredEvent` от ключа.
3. Сверить, что #1306 содержит dependency remediation, затем продолжить обычный
   PR путь для проверки trusted policy gate на актуальном `main`.
4. После локальной full-stack приёмки добавить Core+Mailpit orchestration,
   readiness и resource-limit contracts; затем создать advisory PR smoke и
   nightly/manual live workflow с минимальными правами и без секретных artifacts.
   Вводить обязательный PR gate только после трёх сопоставимых зелёных прогонов.
4. Дальше продолжать [мастер-план](MVP_MASTER_PLAN.md): продуктовые и
   визуальные сценарии, coverage/mutation, backup/restore, BE-02, kind с Envoy
   Gateway, security review и опубликованные шесть digests.

## Критерии и ограничения

- Сохранять 100% применимого coverage и viable mutation score; не добавлять
  необоснованные exclusions, quarantine, timeout inflation или ручные статусы.
- Перед push — целевые тесты, fast-preflight, hooks и `git diff --check`; локальные
  проверки не заменяют required CI или release evidence.
- Продолжать обычный PR flow. Не выполнять admin bypass, force-push, переписывание
  истории или изменение branch protection.
- Не удалять пользовательские volumes, `.env`, backups и данные; миграции не
  сжимать. Убирать только подтверждённые ресурсы текущего прогона.
- Для kind использовать Envoy Gateway + Gateway API. Внешний production, реальные
  SMTP/push-провайдеры, физические устройства, CDC и field CWV вне MVP.
