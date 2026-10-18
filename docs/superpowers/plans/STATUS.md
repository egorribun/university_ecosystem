# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-18 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Общий процент закрытия пока не установлен. Приёмка MVP продолжается после этого приоритета.

Работа только через GitHub plugin, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git и принимает работу максимум трёх GPT-6 Luna Max агентов с непересекающимися файлами. Merge/deploy и обходы проверок не выполнялись.

## Текущая партия и CI

[4108382](https://github.com/egorribun/university_ecosystem/commit/4108382288f88d69a4eed9c7aa40caacbe2a48c4) завершил все 23 workflows: 20 SUCCESS, два штатных SKIPPED, один FAILURE ([Matrix 39134514681](https://github.com/egorribun/university_ecosystem/actions/runs/39134514681)). Все четыре Python unit shards прошли: 5654 / 3425 / 3869 / 3391 PASS. PostgreSQL integration — 174 PASS / 10 SKIP, отдельный migration gate — 82 PASS. Оба orphan-chat сценария проверены с ограниченной NOLOGIN/NOBYPASSRLS ролью; rendered file-backed TOTP/Spotify migration fixture прошёл без ослабления validators.

[Owned Live Core](https://github.com/egorribun/university_ecosystem/actions/runs/39134514612) — 230 contracts, 18 browser PASS, два штатных SKIP, успешный cleanup и metadata-only receipt. React 418 этого прогона не повторился; причина исторического login flake не объявлена доказанной. Frozen-RC full smoke был SKIPPED и не принят.

Frontend shards 2–4 и новый SSR-stub bridge (весь файл 13/13) прошли. Единственный behavioral failure в shard 1 — повторная очистка после committed logout стирает явный null текущего пользователя. Aggregate frontend и CI Success поэтому FAILURE; Coverage & Quality Policy Gate SKIPPED. Все 78 required context/app pairs сопоставлены по полному paginated ответу: 73 SUCCESS, три FAILURE, один SKIPPED, один Checkov code-scanning NEUTRAL из-за отсутствующей main configuration сравнения. NEUTRAL не означает отсутствие alerts. Полной quality-приёмки нет.

Следующая коррекция сохраняет исходный null-assertion: после полного retirement возвращается только уже опубликованный exact null marker в тот же QueryClient. Private queries, mutations и epochs всё равно очищаются; absent, real-user и placeholder данные не восстанавливаются. Добавлены multi-client, malformed-identity и dead-WeakRef regressions. Anonymous-read mode и security boundaries не меняются.

Дополнительные proof gaps:
- AUD-322, events: прежний тест пытался публично зарегистрировать admin без invitation и скрывал 401 через skip. Теперь owned fixture создаёт только тестовый аккаунт, затем real login и весь CRUD должны пройти, включая 404 после удаления. Это PostgreSQL/HTTP integration с существующими external-service doubles, не live SpiceDB proof. Chaos-половина AUD-322 остаётся открытой.
- AUD-173: в существующий Core smoke добавлен real-session сценарий expired signed v8 envelope, same-origin profile probe и reload с сохранением identity и обновлением cache. До hosted pass нового source это только кандидат runtime proof.
- AUD-170: два существующих cross-session comment tests явно включены в текущий PostgreSQL job; новая PG-приёмка ожидается.
- AUD-172: текущий integration log уже подтвердил real JetStream → production worker → PostgreSQL reader → ACK; повторно создавать этот proof не нужно.

Следующий source требует собственного полного CI, live acceptance и окончательной проверки 78 contexts. Baseline319, policy records, coverage floors и required contexts не меняются. Merge/deploy и заявление о закрытии всех 512 findings отсутствуют.

## Проверенная база первой коррекции

Проверенная база текущей коррекции — [a71b9c90](https://github.com/egorribun/university_ecosystem/commit/a71b9c902b64e4016bf67d009e5a299d07098ab0). Это уже опубликованный source: auth/configuration/logout, chat, event/vector и health-probe изменения нельзя считать приватными кандидатами. Последний commit затрагивает 108 файлов; его краткий заголовок не отражает полный scope.

Все 23 workflow runs этой базы terminal: 17 SUCCESS, два штатных SKIPPED, четыре FAILURE:

- [Matrix 39122778794](https://github.com/egorribun/university_ecosystem/actions/runs/39122778794): 30 Python unit failures, один PostgreSQL integration failure до вызова maintenance service, drift inventory и связанные contract/lint gates.
- [OpenAPI 39122778815](https://github.com/egorribun/university_ecosystem/actions/runs/39122778815): committed artifacts не совпадают с выводом генератора.
- [Owned Live 39122778745](https://github.com/egorribun/university_ecosystem/actions/runs/39122778745): source contract остановил запуск до browser acceptance.
- [Checkov 39122778836](https://github.com/egorribun/university_ecosystem/actions/runs/39122778836): finite staging profile не задаёт обязательный TOTP active key ID, поэтому Helm render завершается до scans.

Nilaway и frontend unit shards на этой базе прошли. Security policy/baseline integrity прошли; это не заменяет финальную проверку исправленного source.

Текущая коррекция согласует artifacts с точным diff фактического CI generator, обновляет fixtures под TOTP keyring и locked/paged chat maintenance, устраняет expired ORM access в PostgreSQL test и сохраняет bounded attachment storage contract с отрицательными mutation cases. Production authorization, row locks, validation, coverage floors, scanner gates и required contexts не ослабляются. Новые результаты могут быть приняты только после полного hosted прогона нового SHA.

Предыдущие локальные 490 Python / 433 frontend результаты и отдельные PostgreSQL/Linux проверки сохранены как исторические evidence в [audit supplement](../../audits/AUDIT-2026-10.md#auth-configuration-and-logout-follow-up-2026-10-18). Они не являются результатами текущей cloud-only коррекции. Указание о 12 pending identities в том supplement относится к прежнему локальному snapshot и не доказывает текущий blocker.

Наличие source не означает закрытие соответствующих AUD IDs. AUD-189 по-прежнему требует реальной CNI-проверки; staging/production не развёрнуты. Общая приёмка всех 512 findings не установлена.

## Последняя полностью принятая контрольная точка

На [cd08c35c](https://github.com/egorribun/university_ecosystem/commit/cd08c35c8c0d144ff3c317aa3f16350a86e2a46c) все 23 workflows terminal: 21 SUCCESS, два штатных SKIPPED, failures 0. [Matrix 39081296285](https://github.com/egorribun/university_ecosystem/actions/runs/39081296285), Coverage & Quality Policy Gate и CI Success прошли. Все 78 required context/app pairs найдены: 77 SUCCESS и отдельно проверенный Checkov code-scanning NEUTRAL из-за отсутствующей main configuration сравнения. NEUTRAL не означает отсутствие alerts.

[Owned live Core](https://github.com/egorribun/university_ecosystem/actions/runs/39081296370): 221 contracts, 18 browser tests, два штатных skips и успешный cleanup. Hydration regression: два tests; TOTP cohort: 22 tests со 100% измеренных метрик. Эти результаты относятся только к cd08c35c, не к последующим audit commits.

Причина прежнего flaky первого login не объявлена установленной. SSR hydration readiness defect имеет отдельное доказательство, не тождественное доказательству причины flake.

## Зависимости, политика и ресурсы

- Dependency checkpoint C8 (`5611eb00`) принят; последующие изменения проверяются на собственных SHA. Шесть compatibility holds и открытый SeaweedFS advisory сохранены в [dependency supplement](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15). Удалённые `dependency-updates-2026-10`, `merge-exceptions.md` и `NEXT_SESSION_PROMPT.md` не восстанавливаются.
- Сохраняются baseline319, 78 required contexts, blocking CodeQL и обычные hooks. В опубликованном a71b9c90 policy содержит 263 записи; прежнее число 261 устарело. Эта коррекция не добавляет dispositions и не подтверждает отсутствующее в текущей проверке отдельное owner approval для двух новых записей. Новые unmatched identities остаются блокирующими. Finite131 касается только неизменённых migration blobs из base `ac74e915` до 2026-11-13; остальные Tier 0 и затронутые миграции требуют 100%.
- Один тяжёлый локальный прогон одновременно. Admission RAM ≤75% / free ≥8 GiB; stop RAM ≥85% / free <4 GiB. Разрешение Linux screenshots: ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse: 75% / 8 GiB, cap 2 GiB / 2 CPU.
- Одноразовые PostgreSQL/Linux/Alloy контейнеры, сети и proxy image удалены по точным ownership metadata. Успешный Alloy guard подтвердил неизменность source, отсутствие оставшихся owned процессов и минимум 14,85 GiB свободной RAM; BuildKit и его state volume также удалены. Два принадлежащих задаче Go cache volumes временно сохранены для следующих проверок. Global prune и удаление чужих ресурсов, env, Git history или private rescue bundle не применяются.

## После аудита

Закрыть quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`.

Staging/production не развёрнуты; фактические trusted proxy/CNI/PVC/CSI проверки и соответствующие operational решения остаются открытыми.
