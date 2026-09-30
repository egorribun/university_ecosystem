# MVP — оперативный статус

Срез на 2026-09-30. [Мастер-план](MVP_MASTER_PLAN.md) содержит решения и этапы;
[ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые требования. Goal активен;
приёмка и выпуск `v1.0.0` не завершены.

## Состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | Основной checkout чист, ветка `egorribun` на `10697b0d8a83b78a6f679ae9e357a1f0d256a031`, на 14 коммитов впереди `origin/egorribun`=`724da93d8a73c096df493859a7b9f972df8d1894`. `origin/main`=`78b9499079442191920835eed9de93b726cf36a1` — предок. PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) открыт на старом head `724da93`; текущие коммиты ещё не отправлены. |
| Старый CI | Последние доступные проверки PR относятся к `724da93`, не к текущей ветке. Run [#36693219605](https://github.com/egorribun/university_ecosystem/actions/runs/36693219605) содержит падения frontend `knip` и общий агрегатор; [Go Fuzz #36693218514](https://github.com/egorribun/university_ecosystem/actions/runs/36693218514), Security Policy Integrity и Semgrep также завершились ошибкой. Исправления knip и Go readiness есть в локальных коммитах. Python shard-2 был отменён/не дал достоверного итогового результата. Нужен свежий PR run на интегрированном SHA. |
| Проверки | На кодовом SHA `8af4c036` live Compose приёмка прошла 14/14 desktop/mobile; отчёт `artifacts/live-acceptance/mvp-block-8af4c036-20260930.json`. На `0df28b560847b186652a86f5355180c2f2ea669b` fast-preflight прошёл 9/9 за 69.184 с. Это исторические SHA-bound результаты, не доказательство текущего HEAD. |
| Локальный harness | После предыдущего checkpoint owner-port правки целевые проверки прошли: `tests/test_live_stand.py` — 49; frontend quality contract — 23; `verify_harness.py` — 27/27. Этот набор предстоит повторить после интеграции ожидающих ревью исправлений. |
| Admin smoke | В отдельном worktree есть коммиты `cb9298f` и `952db21` для случайного per-run пароля, безопасной передачи и удаления логирования тел входа. Независимое ревью выявило два дефекта live seed и очистку ссылки на пароль на failure path; исправления выполняются. Не интегрировать до тестов и повторного ревью. Платный Chromatic запуск запрещён: billing gates и `skip: true` сохраняются. |
| Live E2E | Коммит `cfdfa2b9` в отдельном worktree добавляет проверки доступа admin и запрета student/teacher к UI и API. Spec-review одобрил сценарии; implementation report: lint/typecheck и discovery 14 desktop/mobile tests прошли. Независимый reviewer не смог повторить ESLint и Playwright discovery из-за неполной frontend dependency install в worktree; live run не запускался. Ожидается code-quality review. |
| Документация / архивы | В отдельных коммитах удалены 112 архивных audit reports и 8 старых plan snapshots после переноса применимых требований и credentials triage. Rescue bundle и 120-строчный inventory находятся рядом с repo; `git bundle verify`, blob/size сверка всех путей и sample restore двух файлов прошли. SHA-256 bundle: `7cdaed352df12a0f735f86399dd2937be9c832e60d2f1f0ff66fbbb9bc823b11`; inventory: `20bb5457d104ed2590c33c4940c2f0334f2ba526fb1bff208111f5a99c4cc514`. Не распространять bundle: архивные отчёты содержали исторические credential-shaped строки. |
| Credentials | Пользователь подтвердил reset Chromatic project token; GitHub Actions metadata `CHROMATIC_PROJECT_TOKEN` обновлена `2026-09-30T10:08:36Z`; значение не читалось. Seeded-admin пароль был только в одноразовой CI-базе. |
| Ruleset | Разрешён только retired context `Rust Criterion Benchmarks (pyo3-sanitizer)` снят с ruleset `8335285`; остальные required contexts и branch protection не менялись. Старые/mismatched contexts ещё требуют штатного решения; bypass не выполнялся. |
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

1. Закрыть seed-password/failure-path findings, закончить независимые ревью двух
   изолированных патчей и интегрировать только reviewed commits.
2. Повторить target tests, contracts и один актуальный fast-preflight; запустить
   изолированный live stand с новой seed-командой, сохранить данные и evidence.
3. Обновить этот статус по фактическому SHA; выполнить docs/link checks и обычным
   push обновить PR #1306. Разбирать новый CI по его конкретным результатам.
4. Продолжать приёмку по [мастер-плану](MVP_MASTER_PLAN.md): живые продуктовые
   сценарии, визуальный review, coverage/mutation, backup/restore, BE-02, kind с
   Envoy Gateway, security review и опубликованные шесть digests.

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
