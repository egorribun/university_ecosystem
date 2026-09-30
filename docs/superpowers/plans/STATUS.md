# MVP — оперативный статус

Срез на 2026-09-30 16:44 UTC. [Мастер-план](MVP_MASTER_PLAN.md) содержит решения и
критерии; [ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые требования.
Goal активен; подтверждённая приёмка и выпуск `v1.0.0` не завершены.

## Состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | Текущая ветка `egorribun` на `ca4ff258c7a5d9a4c29d2058bd27e76de0e9aff3`, на шесть коммитов впереди `origin/egorribun` (`cfbf5f6200619a800dff9ecf4533b909544d1efb`). Включены четыре функциональных/quality коммита, пояснение комментария WS lock и standalone OTel security fix; три статусных документа ещё изменены локально. `origin/main` (`78b9499079442191920835eed9de93b726cf36a1`) уже является предком HEAD, поэтому no-op merge не нужен. Единственный открытый PR — [#1306](https://github.com/egorribun/university_ecosystem/pull/1306); его удалённый head пока старый. #1307 закрыт; #1308 штатно смёржен. |
| Worktree / ветки | После аудита и безопасной консолидации зарегистрировано 18 worktree, включая корневой; три архивированы как восстанавливаемые snapshots, три удалены после проверки кэшей и отсутствия пользовательских данных. Все уникальные проверенные изменения перенесены или признаны дублирующими. Локальные ветки сведены к `egorribun` и `main`; удалённые feature refs удалены. Остальные worktree отсоединены от feature refs, чтобы сохранить логи, evidence, `.env`/`.secrets` и live-данные; неизвестный запущенный проект не трогали. |
| CI / Ruleset | Последний PR run `36730805165` относится к старому SHA `cfbf5f6200619a800dff9ecf4533b909544d1efb`. Две причины красного `CI Success`: pytest shard 0 достиг 97%, затем без прогресса упёрся в 45-минутный timeout; Go fuzz не запустился из-за временной HTTP/2 ошибки `proxy.golang.org`. Из-за них downstream chaos/coverage и mutation jobs были пропущены. Отдельный required `Security Audit / Semgrep SAST` прошёл; это другой check, чем non-required `Semgrep OSS`, который отметил SQLAlchemy false positive, адресованный commit `949589bb8`. Отдельный non-required `Security Policy Integrity` вызвал `gh api --fail-with-body` из base workflow; исправление есть в PR, но `pull_request_target` использовал старую версию из `main`. Нужен новый SHA-bound CI run; timeout остаётся нерешённым до результата. Ruleset, branch protection и bypass не менялись. |
| Seed / live tooling | Seed patch интегрирован локально: target guard ограничивает owned live Compose и отдельную эфемерную Admin Smoke DB; seed восстанавливает только отсутствующие связи/переводы, сохраняет существующие credentials и custom data. Admin Smoke workflow передаёт явный target. Review нашла и закрыла fail-closed gap: совпавший fixture email с неожиданной ролью теперь отклоняется до изменения связей или аккаунта. В четырёх целевых файлах с seed/live/startup contracts локально прошло 196 тестов; полный live E2E на новом SHA ещё не запускался. |
| Локальные проверки | Seed/live/startup contracts: 196 passed на текущем checkout. Targeted pre-commit прошёл ruff, форматирование, detect-secrets, hardcoded-secret scan, Python 2 syntax check и Semgrep; `git diff --check` прошёл. Оба link-checker режима проверили 429 Markdown-файлов, `tests/test_markdown_links.py`: 9 passed. WS-hub `go test ./...` и pinned Linux race test прошли до правки только комментария. Semgrep-suppression tests: 35 passed, targeted Semgrep прошёл. Локальные результаты не заменяют новый PR CI. |
| Проверенная live evidence | Полный Compose E2E на SHA `d7218c01baaef58f3d1f9762afc389dd00d9408a` ранее прошёл 18/18 desktop/mobile. Это предыдущий source SHA, не доказательство для текущего PR source. Отдельной полной MVP-приёмки ещё нет. |
| Live stand | Сохранены 12 volumes и `.env` остановленного project `ue-live-97e64749be022c80`. Неизвестный project `ue-live-1dc5f2e4c0503c50` остаётся запущенным и указывает на отсутствующий owner path; не останавливать, не удалять и не читать его данные. Нового live PR/nightly/manual workflow пока нет. |
| Live workflow budget | Full Compose имеет memory limits суммарно `14176 MiB` (`13.84 GiB`); Core allowlist — `7008 MiB` (`6.84 GiB`), без Mailpit, нужного password-reset E2E. Стандартный GitHub `ubuntu-24.04` имеет 4 CPU/16 GB RAM/14 GB SSD. До включения live workflow нужны Core+Mailpit orchestration, readiness и замер памяти, диска и времени. |
| Документация / архивы | Действующие archive-каталоги отсутствуют. Inventory по rescue SHA `d0aad7c296facd79b3d41b037bc4160f5b3132be` сверяет 120 путей и `3,981,581` bytes; уникальные требования перенесены в tracked документы. Bundle остаётся частным и изолированным, не копируется и не распространяется из-за исторических credential-подобных строк. Оба link-checker режима прошли по 429 Markdown-файлам; `tests/test_markdown_links.py`: 9 passed. |
| Credentials / audit key | Пользователь подтвердил reset Chromatic token; Actions metadata обновлена `2026-09-30T10:08:36Z`; значение не читалось и платные workflows не запускались. Исторический seeded-admin пароль и `AUDIT_LOG_SECRET` default использовались только в эфемерных CI/demo-средах (со слов пользователя; базы отдельно не читались). `DataAccessLog` writer/verifier всё ещё расходятся по payload fields; не менять ключ и не мигрировать сохраняемые записи без read-only inventory и плана совместимости. |
| Security / WS | Текущий WS-hub patch удаляет ложную конкуренцию между разными room keys через refcounted keyed locks; тестирует сериализацию и lifecycle cleanup. Патч уже находится в локальном `egorribun`; SHA-bound CI после push ещё нужен. |
| Audit / release | Исторический ledger содержит 63 ID: 55 закрыты source/test references, 6 заменены решениями, BE-02 и RUST-P3-03 открыты; MIG-PASS-01 требует отдельного подтверждения. Нужен новый аудит всех ID на release source. `kind` CLI не найден; Gateway API/kind приёмка и проверка шести GHCR digests не выполнены. |
| Dependencies | GitHub всё ещё показывает шесть открытых alerts на default branch: PyJWT, три OpenTelemetry пакета и две записи gRPC. В `egorribun` PyJWT 2.14.0 и gRPC 1.83.2 выше advisory fixes; workspace OTel — 1.46.0. Два standalone-модуля `gen/go` и `services/pkg/spiffe` ранее выбирали SDK 1.44.0; добавлены минимальные indirect pins OTel/SDK metric 1.45.0, `GOWORK=off go list` подтвердил SDK 1.45.0 и оба standalone `go test ./...` прошли. Workspace tests обоих модулей также прошли на OTel 1.46.0. Alerts не закрывать вручную; ждать пересканирования. |
| Mutation / прогресс | Свежие канонические mutation inventories ещё не собраны; прошлый PR run пропустил mutation jobs и ничего не доказывает о текущем допуске. `origin/main` уже предок ветки. Следующий порядок: получить актуальный CI baseline на обновлённом SHA, затем live seed/smoke и свежие inventories. Грубая оценка по крупным блокам — около 10–15%; блоки 0–3 частично начаты, 4–10 не закрыты. |

## Следующие шаги

1. Завершить проверки dependency manifests после OTel pins; пройти docs checks,
   обновить остаточные формулировки архива и закоммитить проверенные изменения.
2. Не создавать пустой merge: `origin/main` уже предок ветки. Проверить конечный
   PR diff и затронутые Go/workflow контракты.
3. Пройти fast-preflight, затронутые tests, harness, pre-commit, links и
   `git diff --check`; обновить единственный PR #1306 обычным push и проверить CI.
4. После зелёного CI-baseline собрать свежий mutation inventory и начать закрытие
   auth/security/data очередей, продолжая живую продуктовую приёмку.
5. Дальше пройти блоки мастер-плана: визуальное утверждение, backup/restore, BE-02,
   Envoy Gateway + Gateway API/kind, повторный audit ledger и release digest gates.

## Постоянные ограничения

- Сохранять 100% применимого coverage и viable mutation score; не добавлять
  необоснованные exclusions, quarantine, timeout inflation или ручные статусы.
- Не выполнять admin bypass, force-push, переписывание истории или изменение
  branch protection; releases идут обычным PR flow.
- Не удалять `.env`, backups, пользовательские volumes, секреты и другие данные.
  Удалять только проверенные избыточные worktrees/ветки и только после переноса
  нужного кода и повторной проверки владельца ресурсов.
- Для kind использовать Envoy Gateway + Gateway API. Внешний production,
  реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV вне MVP.
