# Статус выпуска MVP v1.0.0 — краткий текущий срез

## Текущий срез — 2026-11-20, 09:03 UTC

- PR #1534 вошёл в `main` обычным слиянием `d33d2761abe8d250e7f5e8f8470323c729329bcb` в 08:02:39 UTC.
  На исходном коммите `20b0a69dc4e629ffbd076927c5706b028ee2dbe8` прошли все 78 обязательных пар
  context/app, включая Coverage & Quality Policy Gate (job `136162118293`) и CI Success (job `136163000272`).
  Деревья PR head, проверенного PR merge SHA `02526d03a87012e06b89b724cfde9ddb0e810f1b` и коммита
  `main` совпадают. GitHub зафиксировал `pass` для `code_scanning` и `required_status_checks`
  в проверке правил `5251871447`. [PR #1534](https://github.com/egorribun/university_ecosystem/pull/1534) ·
  [CI run 44695934771](https://github.com/egorribun/university_ecosystem/actions/runs/44695934771)
- В PR job `136152566727` прошли 18 realtime-сценариев. Артефакт AUD-154 для этого коммита
  подтверждает четыре проверки отправки кнопкой и клавишей Enter на desktop и mobile. Все четыре
  прошли с первой попытки. Результаты read-receipt приведены ниже для полного Core на `main`.
  [Realtime job](https://github.com/egorribun/university_ecosystem/actions/runs/44695934771/job/136152566727) ·
  [AUD-154 артефакт 14612330420](https://github.com/egorribun/university_ecosystem/actions/runs/44695934771/artifacts/14612330420)
- Kubernetes NetworkPolicy job `136164190183` на `d33d2761` подтвердил все 40 проб матрицы
  (15 разрешённых и 25 запрещённых соединений) и 13 прикладных проверок. Для двух реальных реплик
  file-processor прошли 24 проверки, для ws-hub и Prometheus — 6 ограниченных проверок.
  Публичный маршрут и реальный ingress controller, а также реальный file-processor в probe B остаются
  вне этой проверки. Сетевые обращения outbox-worker проверены с подставным клиентом.
  [NetworkPolicy run 44699509643](https://github.com/egorribun/university_ecosystem/actions/runs/44699509643) ·
  [Артефакт 14613871575](https://github.com/egorribun/university_ecosystem/actions/runs/44699509643/artifacts/14613871575)
- Полный Core job `136164176676` на `d33d2761` завершился с результатом 219 passed, 2 failed,
  8 skipped и 3 flaky из 232 сценариев. Все шесть записей AUD-154 — `aud154-sent-confirmation`,
  `aud154-enter-sent-confirmation` и `aud154-read-receipt` для каждого из desktop и mobile — прошли
  с первой попытки. Диагностика охватывает desktop-сценарии notification-topics-delivery, profile-csrf,
  events-scroll-restoration и schedule-200-equivalent-reflow, а также mobile push-delivery. В журнале
  указаны суммарные failed и flaky без привязки к отдельным сценариям. Стенд успешно запущен и остановлен.
  Проверка NATS outage пропущена. Метаданные результата сохранены в артефакте Core.
  [Полный Core run 44699505018](https://github.com/egorribun/university_ecosystem/actions/runs/44699505018) ·
  [Core receipt 14614549272](https://github.com/egorribun/university_ecosystem/actions/runs/44699505018/artifacts/14614549272)
- В `quality/frozen-rc.json` на этом коммите поле `source_sha` равно `null`. Проверка frozen-RC
  (job `136164176498`) завершилась с ошибкой, full-stack smoke (job `136164963022`) пропущен.
  Итог всего workflow — failure. Формальный счёт аудита — **510/512**, открыты AUD-154 и AUD-381.

## Предыдущий срез — 2026-11-20, main `85b0b2a08` (история)

- PR #1524 вошёл в `main` обычным слиянием `85b0b2a08d67de0faa16c90ecf7091cb410a3eee`.
  На исходном коммите `3c7f651092de5b00240b1898dfafe859c09b9e07` прошли все 78 обязательных пар context/app,
  включая Coverage & Quality Policy Gate (job `135681305145`) и CI Success (job `135687551066`).
  В PostgreSQL job `135658513142` прошли 436 тестов, 14 пропущены. Все 86 сценариев обязательной когорты прошли.
  [PR #1524](https://github.com/egorribun/university_ecosystem/pull/1524) · [CI run 44551542543](https://github.com/egorribun/university_ecosystem/actions/runs/44551542543)
- На PR merge SHA `4e73285723492326b8ab00de2a2ade4df655607b` пять анализов CodeQL
  и пять отчётов Checkov завершились без находок. Дерево этого коммита совпадает с деревом `85b0b2a08`.
  GitHub зафиксировал `pass` для `code_scanning` и `required_status_checks` в проверке правил `5235140478`.
  [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/44551542238) ·
  [Checkov](https://github.com/egorribun/university_ecosystem/actions/runs/44551541576).
- На `85b0b2a08` Kubernetes NetworkPolicy job `135690589182` подтвердил все 40 проб матрицы
  (15 разрешённых соединений и 25 запрещённых), 24 проверки реального file-processor и 6 проверок
  ограниченных соединений для ws-hub и Prometheus. Публичный HTTP-маршрут и реальный ingress controller
  остаются вне этой проверки. [Kubernetes NetworkPolicy run 44561178071](https://github.com/egorribun/university_ecosystem/actions/runs/44561178071) · [Артефакт 14552260459](https://github.com/egorribun/university_ecosystem/actions/runs/44561178071/artifacts/14552260459)
- Полный Core job `135690685646` на `85b0b2a08` завершился с ошибкой. Прошли 222 теста, 8 пропущены,
  2 прошли только при повторной попытке. Это desktop-сценарий `admin-stories-rbac` и mobile-сценарий
  `admin-stories-smoke`. Все шесть проверок AUD-154 (sent, Enter-sent и read-receipt на desktop и mobile)
  прошли с первой попытки. Стенд успешно остановлен. Для закрытия AUD-154 нужны два последовательных
  успешных полных Core-прогона на `main`. Свежего отчёта DAST для этого SHA пока нет.
  [Полный Core run 44561200602](https://github.com/egorribun/university_ecosystem/actions/runs/44561200602) · [Артефакт 14552804821](https://github.com/egorribun/university_ecosystem/actions/runs/44561200602/artifacts/14552804821)
- Ранее PR #1519 был слит в `main` обычным слиянием `02c3664abff423960fbac9a35d1e3990575517c3`.
  На исходном коммите `18aa310f9f029449f4a250c7e1befbee0bcb8656` прошли все 78 обязательных пар context/app,
  включая Coverage & Quality Policy Gate (job `135602417513`) и CI Success (job `135604664230`).
  [PR #1519](https://github.com/egorribun/university_ecosystem/pull/1519) · [CI run 44525616113](https://github.com/egorribun/university_ecosystem/actions/runs/44525616113)
- Для PR #1519 пять анализов CodeQL на PR merge SHA `5fe7775e821214beab6f48aa495d2b45617f4dc0`
  завершились без находок. Дерево этого коммита совпадает с деревом `02c3664ab`.
  GitHub зафиксировал `pass` для `code_scanning` и `required_status_checks` в проверке правил `5231970851`.
  Checkov опубликовал пять отчётов без находок, включая отчёт под историческим идентификатором.
  [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/44525615911) · [Checkov](https://github.com/egorribun/university_ecosystem/actions/runs/44525615909)
- На предыдущем `02c3664ab` прошли 40 из 40 проб NetworkPolicy в kind и Calico. Проверка охватывала
  внутрикластерные маршруты. Реальный ingress controller и публичный HTTP-маршрут остаются непроверенными.
  [Kubernetes NetworkPolicy run 44537388732](https://github.com/egorribun/university_ecosystem/actions/runs/44537388732) · [Артефакт 14538737204](https://github.com/egorribun/university_ecosystem/actions/runs/44537388732/artifacts/14538737204)
- На `02c3664ab` полный Core завершился с ошибкой. Результат — 220 passed, 8 skipped, 4 flaky.
  В отчёте указаны три desktop-сценария — `admin-stories-rbac`, `email-otp-mfa-login` и
  `schedule-200-equivalent-reflow`. Все шесть проверок AUD-154 (sent, Enter-sent и read-receipt
  на desktop и mobile) прошли с первой попытки. Отдельный full-stack smoke был пропущен после ошибки
  проверки frozen-RC. Поле `source_sha` в `quality/frozen-rc.json` равно `null`.
  [Полный Core run 44537394864](https://github.com/egorribun/university_ecosystem/actions/runs/44537394864) · [Артефакт 14541137444](https://github.com/egorribun/university_ecosystem/actions/runs/44537394864/artifacts/14541137444)
- Последний опубликованный отчёт DAST относится к `64f7fd514` и содержит пять предупреждений ZAP уровня medium.
  [DAST run 44471112462](https://github.com/egorribun/university_ecosystem/actions/runs/44471112462)
- Формальный итог аудита — **510/512 (99.6%)**. Открыты AUD-154 (S) и AUD-381 (P).
- Коммит `140145bdb` в `egorribun` удаляет серверный кэш расписания, его прогрев и инвалидацию.
  Расписание и список групп читаются из базы в транзакции текущего арендатора. Сервер вычисляет HTTP ETag
  по локализованному ответу. Изменение вошло в `main` с PR #1524.
- Cargo Deny: исключение RUSTSEC-2026-0543 (`chrono`) действует до 2026-12-17; затем
  переход `rust_ext` на `time`
  ([ADR-047](../../adr/ADR-047-risk-based-quality-policy.md#time-boxed-cargo-deny-exception-for-rustsec-2026-0543)).
- `frontend.Dockerfile` на `node:24.21.0-alpine` устанавливает подписанный
  `zlib-1.3.2-r1` из release-ISO Alpine 3.24.3 с проверкой SHA-256. Для той же версии `services/caddy/Dockerfile`
  обращается к изменяемому репозиторию `v3.23/main` и проверяет контрольную сумму и подпись. Существующий
  контракт упаковки react-compiler/zod compat закрепляет Node v24.21.0 и npm 11.17.0
  и проверяет совпадение двух архивов.

## Предыдущий срез — 2026-11-19, main `64f7fd514` (история)

- `64f7fd5148e8c6668b401e755be9459172f99ec8` — слияние
  [PR #1422](https://github.com/egorribun/university_ecosystem/pull/1422). Перед слиянием
  перезапускались упавшие Security Audit jobs: advisory GHSA-fc5q-39xc-vjpf (picomatch)
  отозвана GitHub 2026-11-18.
- Kind + Calico NetworkPolicy прошёл в [run 44471108615](https://github.com/egorribun/university_ecosystem/actions/runs/44471108615).
  В последнем DAST [run 44471112462](https://github.com/egorribun/university_ecosystem/actions/runs/44471112462)
  Nuclei прошёл, ZAP сообщил о пяти medium (10055 ×2, 10106, 10202, 40025).
  В SARIF нет URL; AUD-381 остаётся открытым, свежего результата на `02c3664ab` нет.
- Последний полный Core на этом старом SHA — [run 44512654784](https://github.com/egorribun/university_ecosystem/actions/runs/44512654784):
  219 passed, 1 failed, 8 skipped, 4 flaky. Диагностика двух native Push случаев
  (desktop notification-topics и mobile push-delivery) показала `subscription=true`,
  `matches=0`. Более ранний [run 44471116074](https://github.com/egorribun/university_ecosystem/actions/runs/44471116074)
  дал 217 passed, 8 skipped, 7 flaky и ошибки уведомлений и мобильных admin-stories/events;
  выборка его воркера — `sent=9 gone=3`, три ответа провайдера 4xx.
- В `egorribun` была интегрирована вторая волна PR облачного агента: #1431, #1443,
  #1446, #1447, #1453, #1456, #1464, #1481, #1489–#1498, #1508–#1517 и Dependabot Go
  (#1445, #1448, #1450). Найденные дефекты исправлены; четыре companion-записи
  перепривязаны один к одному (ADR-047, 2026-11-19), retention под RLS описан в
  [ADR-055](../../adr/ADR-055-retention-cleanup-under-tenant-rls.md). #1501 закрыт
  как дубликат; #1426 и диагностические #1506, #1507, #1518 оставлены открытыми.

## Предыдущий срез — 2026-11-17 (superseded)

- `main` указывал на
  [`b571261a0805a426febd8b16b942810417f32ce8`](https://github.com/egorribun/university_ecosystem/commit/b571261a0805a426febd8b16b942810417f32ce8).
- Kind + Calico proof на
  [`057ccd2cb`](https://github.com/egorribun/university_ecosystem/commit/057ccd2cb835f82d97144e97413b185cf8bd7a03):
  [run 43969553490](https://github.com/egorribun/university_ecosystem/actions/runs/43969553490),
  [receipt 14279491890](https://github.com/egorribun/university_ecosystem/actions/runs/43969553490/artifacts/14279491890);
  матрица 40/40, приняты AUD-169, AUD-188, AUD-189 и AUD-438 в пределах
  [зафиксированных доказательств](../../audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-17).
- Полные Core [run 43997541022](https://github.com/egorribun/university_ecosystem/actions/runs/43997541022)
  и [run 44011702649](https://github.com/egorribun/university_ecosystem/actions/runs/44011702649)
  на `b571261a0` упали на push- и notification-спеках.
- История более ранних срезов: `git log -- docs/superpowers/plans/STATUS.md`.

## Аудит: текущий итог 2026-11-17 — 510/512

Формальный итог: **510/512 (99.6%) accepted or resolved, 2 open**, **1S / 1P / 0U / 0N**.
Приняты AUD-169, AUD-188, AUD-189 и AUD-438 в пределах проверки на kind + Calico.
Предыдущие срезы 506/512 и 502/512 сохранены как история. Границы решений:
[Current scoped supplement — 2026-11-17](../../audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-17).

Счёт поддерживается в шести файлах: `docs/audits/INDEX.md`, reassessment,
reconciliation, `AUDIT-2026-10.md`, этот файл и `docs/README.md`.

The current policy-file inventory is **524 dispositions / 242 baseline identities / 27 Gitleaks fingerprints / 15 Semgrep rows**. This is inventory only, not evidence of a passing scan or required checks.

### Открытые находки и текущий план

Состав открытых находок — из
[current 2-finding complement](../../audits/AUDIT-2026-10-30-reconciliation.md#current-2-finding-reconciliation--2026-11-17).

| ID | Статус | Что нужно для закрытия |
| --- | --- | --- |
| AUD-154 | S | Green hosted Owned Live Acceptance run на точном SHA (эквивалентность принята владельцем), включая существующий read-receipt live spec. |
| AUD-381 | P | Нужен успешный отчёт ZAP и Nuclei на эфемерном Compose-стенде для точного SHA `main`. Последний опубликованный отчёт ZAP содержит пять предупреждений medium. |

Остальные требования каждой находки не изменены. Закрытие требует проверки конкретного
source SHA, а не этого среза.

## MVP-этапы (ссылка: [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md))

| Этап | Статус |
| --- | --- |
| 1. Решение и документы | Выполнен. |
| 2. Q1 и Q4 в CI | Интегрированы. Каждый новый SHA требует свежих required-check results. |
| 3. Core и продукт | Подготовлены сценарии и матрица; итоговая приёмка не проведена. |
| 4. Визуал и performance | Утверждён только визуальный пакет Home12. |
| 5. Security, ledger, данные | Восстановление DB/S3 backup никогда не запускалось. |
| 6. Выпуск | Не начат. |

## Открытые решения владельца

- AUD-484: решено владельцем 2026-11-12, alerts 2995–3002 dismissed, analyses сохранены.
- Для AUD-381 владелец выбрал эфемерный Compose-стенд в CI (2026-11-12).
- AUD-169, AUD-188, AUD-189, AUD-438: kind + Calico принят владельцем как среда доказательств
  (2026-11-12); решения и ограничения записаны в supplement от 2026-11-17. AUD-251 принят на этой среде.

## Следующие шаги

1. Разобрать два failed и три flaky полного Core на `d33d2761`, сохраняя различие между результатами
   Core, отдельной проверки frozen-RC и пропущенного full-stack smoke.
2. AUD-154: получить два последовательных green полных Core run на `main` с реальным read-receipt;
   следующий полный запуск — не ранее 2026-11-20 10:03:17 UTC. AUD-381: разобрать пять исторических
   ZAP warnings и получить проверенные ZAP и Nuclei на точном SHA `main`.
3. Этапы 3 и 4: сверить traceability matrix ТЗ §2–13 с кодом и выполнить live Chromium,
   mocked Firefox/WebKit, idempotent seed и stop/start; согласовать визуальные и
   performance-пакеты RU/EN, light/dark, desktop/mobile за пределами Home12.
4. Этап 5: один DB/S3 backup и restore в изолированную цель; затем этап 6 — frozen RC,
   full smoke, required checks и обычный выпуск по мастер-плану.

## History

Предыдущие датированные разделы, checkpoints, hosted-run журналы и доказательства до
2026-11-12 не удалены из истории: см. `git log -- docs/superpowers/plans/STATUS.md`
и `git show d8891684f:docs/superpowers/plans/STATUS.md`.
