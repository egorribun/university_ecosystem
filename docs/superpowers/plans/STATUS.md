# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-18 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Общий процент закрытия пока не установлен. Приёмка MVP продолжается после этого приоритета.

Один checkout, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git и принимает работу максимум трёх GPT-6 Luna Max агентов с непересекающимися файлами. Merge/deploy и обходы проверок не выполнялись.

## Текущая партия и CI

Входная ревизия партии — [0ca7778b](https://github.com/egorribun/university_ecosystem/commit/0ca7778b5b9fb5593e7b04ee154e4737db338ab9). Последние audit-коммиты `a91259f0`, `f7994339`, `0ca7778b` затрагивают 46 уникальных AUD IDs; часть дополняет прежние исправления. Это инвентаризация изменений, а не число окончательно закрытых находок.

[Matrix 39090418920](https://github.com/egorribun/university_ecosystem/actions/runs/39090418920) завершился FAILURE: инвентаризация тестов, Alembic и четыре Python-шарда. Frontend unit/build/lint и отдельные Go/security jobs прошли; они не заменяют aggregate coverage/quality acceptance.

Текущая корректирующая партия:

- AUD-195: публичные поля авторов сообщений читаются одним batch query; email/account state исключены из sender DTO и прямой загрузки автора. OpenAPI и generated frontend-клиент согласованы.
- AUD-208: live Alembic capture сохраняет transaction events, LOCK, копирование данных и комментарии конкретных DDL. Четыре уже затронутые PR миграции получили ограниченные таймауты; добавлены проверки атомарного отката.
- Устаревшие cleanup, Outbox и DLQ tests согласованы с опубликованной логикой. Descendant-pipe regression использует bounded handshake вместо гонки фиксированных пауз.
- CSS/Helm tests явно выражают реальные source dependencies; существующий валидатор инвентаризации и его правила сохраняются.

Локально: PostgreSQL 62/62 и все девять live SQL/Squawk проверок PASS; чат 457/457; Helm/inventory 396/396; Linux descendant-pipe 20/20; DLQ 16/16; contrast 2/2. Outbox/metadata cohort: 68 PASS, шесть PostgreSQL-only cases отдельно прошли в live cohort. Harness 28/28, Ruff, TypeScript, strict mypy и 430 Markdown links PASS. Полный secret scan: 519 findings / 0 unmatched, baseline319. Новая опубликованная ревизия требует полного hosted coverage/quality evidence. [Подробности партии](../../audits/AUDIT-2026-10.md#audit-follow-up-and-ci-reconciliation-2026-10-18).

Следующая параллельная партия: изоляция Compose-сетей (AUD-192), ограничение Docker API для Alloy (AUD-193), маршрутизация персональных уведомлений ws-hub (AUD-476). Приватные кандидаты до интеграции и проверок не считаются исправлениями. AUD-189 уже имеет source fix HTTPS egress; реальная CNI-проверка остаётся открытой.

## Последняя полностью принятая контрольная точка

На [780ef932](https://github.com/egorribun/university_ecosystem/commit/780ef9323cd032c3a44e3cb386d8d5955f1754f5) все 23 workflow runs terminal: 21 SUCCESS, два штатных SKIPPED, failures 0. [Matrix 39069496976](https://github.com/egorribun/university_ecosystem/actions/runs/39069496976), Coverage & Quality Policy Gate и CI Success прошли. Все 78 required context/app pairs найдены: 77 SUCCESS и отдельно проверенный Checkov code-scanning NEUTRAL из-за отсутствующей main configuration сравнения. NEUTRAL не означает отсутствие alerts; отдельные Checkov Actions и CodeQL прошли.

Owned live Core acceptance: 221 contracts, 18 browser tests, два штатных skips и успешный cleanup. Это evidence только для 780ef932; последующие audit-коммиты требуют своих проверок. [Историческая контрольная точка](../../audits/AUDIT-2026-10.md#hosted-closure-checkpoint-2026-10-18-780ef932).

Причина прежнего flaky первого login не объявлена установленной. Исправленный SSR hydration readiness defect имеет отдельное доказательство; новая live приёмка ещё требуется.

## Зависимости, политика и ресурсы

- Dependency checkpoint C8 (`5611eb00`) принят; последующие изменения проверяются на собственных SHA. Шесть compatibility holds и открытый SeaweedFS advisory сохранены в [dependency supplement](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15). Удалённые `dependency-updates-2026-10`, `merge-exceptions.md` и `NEXT_SESSION_PROMPT.md` не восстанавливаются.
- Сохраняются baseline319, ровно 261 owner-approved exact disposition, 78 required contexts, blocking CodeQL и обычные hooks. Новые identities остаются блокирующими. Finite131 касается только неизменённых migration blobs из base `ac74e915` до 2026-11-13; остальные Tier 0 и затронутые миграции требуют 100%.
- Один тяжёлый локальный прогон одновременно. Admission RAM ≤75% / free ≥8 GiB; stop RAM ≥85% / free <4 GiB. Разрешение Linux screenshots: ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse: 75% / 8 GiB, cap 2 GiB / 2 CPU.
- Одноразовые PostgreSQL/Linux контейнеры партии удалены по точным ownership metadata. Успешный PostgreSQL guard подтвердил неизменность source, отсутствие оставшихся owned процессов и минимум 19,58 GiB свободной RAM. Global prune и удаление чужих процессов, volumes, env, Git history или private rescue bundle не применяются.

## После аудита

Закрыть quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`.

Staging/production не развёрнуты; фактические trusted proxy/CNI/PVC/CSI проверки и соответствующие operational решения остаются открытыми.
