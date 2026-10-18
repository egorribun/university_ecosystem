# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-18 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Общий процент закрытия пока не установлен. Приёмка MVP продолжается после этого приоритета.

Один checkout, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git и принимает работу максимум трёх GPT-6 Luna Max агентов с непересекающимися файлами. Merge/deploy и обходы проверок не выполнялись.

## Текущая партия и CI

Текущий опубликованный HEAD и PR — [8d810371](https://github.com/egorribun/university_ecosystem/commit/8d810371d9e8a69affacb26076693a08393e9d1d). Все 23 workflow runs завершены: 18 SUCCESS, два штатных SKIPPED, три FAILURE. [Matrix 39104776721](https://github.com/egorribun/university_ecosystem/actions/runs/39104776721) выявил прежние frontend cache expectations, Pillow fallback fixture и Compose topology expectation. [Nilaway](https://github.com/egorribun/university_ecosystem/actions/runs/39104776669) выявил три отсутствующие nil guards. [Owned live Core](https://github.com/egorribun/university_ecosystem/actions/runs/39104776697) остановился на прямой host-проверке frontend: Caddy `/login` был доступен. Исправления входят в локальную партию; её hosted acceptance ещё не выполнена. CodeQL и отдельные security workflows на опубликованном SHA прошли.

Текущая auth/configuration партия подготовлена локально:

- AUD-238: отдельный TOTP keyring с явным active ID, проверкой независимости ключей и поддержкой расшифровки прежних записей. CLI выводит legacy key в защищённый файл и выполняет ограниченную ротацию с dry-run по умолчанию. Backend и migrations получают ключи; non-auth workers остаются без TOTP keyring.
- AUD-252: production Compose использует обязательные file-backed secret sources. AUD-467: production validation учитывает среду и парность интеграционных credentials; явный пустой optional secret file не подменяется fallback.
- AUD-243: после неподтверждённого logout пользователь видит уведомление; подтверждённое удаление текущей сессии не создаёт ложное предупреждение. Поздний ответ старого пользователя не очищает новую сессию. Отказ записи browser generation при неизменной подтверждённой identity сохраняет локальную очистку; stale binding не получает это разрешение.
- AUD-192/193: startup ждёт healthy frontend container и проверяет доступ через Caddy; nil guards Docker API proxy сохранены вместе с проверками корректного streaming response. Обновлены связанные test expectations, без ослабления runtime gates.

Проверено root: 490 Python tests PASS / два штатных platform/database skips, все пять затронутых app-модулей — 100% line/branch (805 statements, 206 branches). PostgreSQL acceptance — шесть PASS; Linux CLI acceptance — семь PASS. Frontend — 433 PASS в девяти suites; пять модулей — 100% всех четырёх V8-метрик, TypeScript/ESLint PASS. Новый storage-write regression воспроизвёл ошибку до production fix. Targeted pinned Nilaway, Linux race tests proxy/ws-hub и canonical golangci прошли. Inventory, 432 Markdown link checks и harness 28/28 PASS. [Подробности партии](../../audits/AUDIT-2026-10.md#auth-configuration-and-logout-follow-up-2026-10-18).

Предварительный полный secret scan — 4 908 файлов / 537 findings / 18 unmatched. Шесть новых синтетических identities заменены генерируемыми значениями во всех повторениях; их Python tests прошли. Для 11 публичных Compose mapping identities и одной deployment-doc identity подготовлен отдельный private proposal. До решения владельца policy остаётся на 261 записи, эти 12 identities блокируют публикацию. Финальный source scan, обычные hooks и hosted gates нового SHA ещё обязательны.

Ранее опубликованные исправления network/auth/notification, image metadata, GeoIP, Spotify и scheduler описаны в [audit supplement](../../audits/AUDIT-2026-10.md#audit-network-auth-and-notification-follow-up-2026-10-18). Наличие commit и локальной приёмки не означает итогового закрытия всех затронутых AUD IDs. Chat, event/vector, health-probe и audit-response кандидаты остаются приватными до отдельной интеграции и runtime-проверок. AUD-189 требует реальной CNI-проверки.

## Последняя полностью принятая контрольная точка

На [780ef932](https://github.com/egorribun/university_ecosystem/commit/780ef9323cd032c3a44e3cb386d8d5955f1754f5) все 23 workflow runs terminal: 21 SUCCESS, два штатных SKIPPED, failures 0. [Matrix 39069496976](https://github.com/egorribun/university_ecosystem/actions/runs/39069496976), Coverage & Quality Policy Gate и CI Success прошли. Все 78 required context/app pairs найдены: 77 SUCCESS и отдельно проверенный Checkov code-scanning NEUTRAL из-за отсутствующей main configuration сравнения. NEUTRAL не означает отсутствие alerts; отдельные Checkov Actions и CodeQL прошли.

Owned live Core acceptance: 221 contracts, 18 browser tests, два штатных skips и успешный cleanup. Это evidence только для 780ef932; последующие audit-коммиты требуют своих проверок. [Историческая контрольная точка](../../audits/AUDIT-2026-10.md#hosted-closure-checkpoint-2026-10-18-780ef932).

Причина прежнего flaky первого login не объявлена установленной. Исправленный SSR hydration readiness defect имеет отдельное доказательство; новая live приёмка ещё требуется.

## Зависимости, политика и ресурсы

- Dependency checkpoint C8 (`5611eb00`) принят; последующие изменения проверяются на собственных SHA. Шесть compatibility holds и открытый SeaweedFS advisory сохранены в [dependency supplement](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15). Удалённые `dependency-updates-2026-10`, `merge-exceptions.md` и `NEXT_SESSION_PROMPT.md` не восстанавливаются.
- Сохраняются baseline319, ровно 261 owner-approved exact disposition, 78 required contexts, blocking CodeQL и обычные hooks. Новые identities остаются блокирующими. Finite131 касается только неизменённых migration blobs из base `ac74e915` до 2026-11-13; остальные Tier 0 и затронутые миграции требуют 100%.
- Один тяжёлый локальный прогон одновременно. Admission RAM ≤75% / free ≥8 GiB; stop RAM ≥85% / free <4 GiB. Разрешение Linux screenshots: ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse: 75% / 8 GiB, cap 2 GiB / 2 CPU.
- Одноразовые PostgreSQL/Linux/Alloy контейнеры, сети и proxy image удалены по точным ownership metadata. Успешный Alloy guard подтвердил неизменность source, отсутствие оставшихся owned процессов и минимум 14,85 GiB свободной RAM; BuildKit и его state volume также удалены. Два принадлежащих задаче Go cache volumes временно сохранены для следующих проверок. Global prune и удаление чужих ресурсов, env, Git history или private rescue bundle не применяются.

## После аудита

Закрыть quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`.

Staging/production не развёрнуты; фактические trusted proxy/CNI/PVC/CSI проверки и соответствующие operational решения остаются открытыми.
