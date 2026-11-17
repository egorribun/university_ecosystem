# Статус выпуска MVP v1.0.0 — краткий текущий срез

## Текущий срез — 2026-11-17

- Защищённый `main` на дату среза —
  [`b571261a0805a426febd8b16b942810417f32ce8`](https://github.com/egorribun/university_ecosystem/commit/b571261a0805a426febd8b16b942810417f32ce8).
- Hosted Kind + Calico proof на тогдашнем main
  [`057ccd2cb835f82d97144e97413b185cf8bd7a03`](https://github.com/egorribun/university_ecosystem/commit/057ccd2cb835f82d97144e97413b185cf8bd7a03):
  [run 43969553490](https://github.com/egorribun/university_ecosystem/actions/runs/43969553490),
  [job 133657797517](https://github.com/egorribun/university_ecosystem/actions/runs/43969553490/job/133657797517),
  [receipt 14279491890](https://github.com/egorribun/university_ecosystem/actions/runs/43969553490/artifacts/14279491890).
  Матрица 40/40; приняты AUD-169, AUD-188, AUD-189 и AUD-438 в пределах
  [зафиксированных доказательств](../../audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-17).
  Реальный ingress controller и публичный HTTP route не запускались; применён
  ingress-labelled stand-in по принятому владельцем объёму проверки.
- Полные hosted Core [run 43997541022](https://github.com/egorribun/university_ecosystem/actions/runs/43997541022)
  и [run 44011702649](https://github.com/egorribun/university_ecosystem/actions/runs/44011702649)
  на `b571261a0805a426febd8b16b942810417f32ce8` завершились с ошибкой на шаге live acceptance.
  [Metadata-only receipt 14302072870](https://github.com/egorribun/university_ecosystem/actions/runs/44011702649/artifacts/14302072870)
  последнего подтверждает режим `full` и `e2e: failure`; серия green полных Core run на `main` — 0 из 2.
  Более ранний [run 43969553294](https://github.com/egorribun/university_ecosystem/actions/runs/43969553294)
  на `057ccd2cb835f82d97144e97413b185cf8bd7a03` также завершился с ошибкой.
- Формальный итог — **510/512 (99.6%), 2 открытых: 1S / 1P / 0U / 0N**.
  Этот результат не подтверждает общий CI, выпуск или deployment. Новый SHA
  документации и каждый последующий SHA требуют собственных required checks.
- Открыт [PR #1422](https://github.com/egorribun/university_ecosystem/pull/1422) из `egorribun`
  в `main`. В нём: подтверждение личности в настройках, live-диагностика Push и MapLibre
  и 67 черновых PR автоматического облачного агента (#1409–#1488), влитых в `egorribun`
  после локальной проверки. Агент ничего не запускал сам, поэтому найденные дефекты
  исправлены в ветке без ослабления гейтов. Required checks на итоговом SHA ещё не
  подтверждены. Облачный агент приостановлен владельцем; его очереди Actions отменены.
- Отложены до перепривязки реестра: #1431, #1443, #1446, #1447, #1453, #1456, #1464, #1481
  (меняют закреплённые файлы). #1426 (SPIFFE для SSR) не готов к слиянию по оценке самого агента.
- Cargo Deny: временное исключение RUSTSEC-2026-0543 (`chrono` unmaintained, без уязвимости)
  до 2026-12-17 по решению владельца; затем переход `rust_ext` на `time`
  ([ADR-047](../../adr/ADR-047-risk-based-quality-policy.md#time-boxed-cargo-deny-exception-for-rustsec-2026-0543)).
- Риск: в Alpine v3.24 появился `zlib-1.4-r0`; закреплённый `zlib-1.3.2-r1` в
  `frontend.Dockerfile` и `services/caddy/Dockerfile` может исчезнуть с зеркала.

## Предыдущий срез — 2026-11-17 (`0823bdb`, superseded)

- На тот момент `main` указывал на
  [`0823bdb23f41190c07625fd996f0fc98ae565da7`](https://github.com/egorribun/university_ecosystem/commit/0823bdb23f41190c07625fd996f0fc98ae565da7)
  (слияние [PR #1405](https://github.com/egorribun/university_ecosystem/pull/1405)).
  Формальный итог аудита тогда составлял 506/512 при 6 открытых находках;
  документы аудита обновляются только по hosted-доказательствам на точном SHA.
- Kind-прогон NetworkPolicy на этом SHA прошёл: матрица 40/40, реальный file-processor,
  ротация JWKS по репликам, реальные backup и restore, отброшенные запросы метрик к
  репликам ws-hub. [Run 43931898209](https://github.com/egorribun/university_ecosystem/actions/runs/43931898209),
  [artifact 14264158752](https://github.com/egorribun/university_ecosystem/actions/runs/43931898209/artifacts/14264158752).
  На тот момент AUD-189 требовал следующего прогона с публичным TCP/443 для
  outbox-worker (решение владельца, ADR-054, дополнение 2026-11-16).
- Полный Core на этом SHA: 218 пройдено, 2 упало, 8 пропущено, 4 нестабильных.
  [Run 43931883465](https://github.com/egorribun/university_ecosystem/actions/runs/43931883465).
  Серия успешных полных прогонов `main` составляет 0 из 2.
- DAST на этом SHA не дал отчёта ZAP: в hosted-раннерах ZAP ни разу не запускался
  (uid раннера без записи в passwd, `user.home=?`), см. ADR-047.
  [Run 43931891703](https://github.com/egorribun/university_ecosystem/actions/runs/43931891703).
- [PR #1406](https://github.com/egorribun/university_ecosystem/pull/1406) содержал исправления:
  бюджет времени тестов нативного push, гонки в admin-stories-smoke и profile-csrf,
  блокировку кнопок медиа профиля до подтверждения личности, запуск ZAP,
  публичный TCP/443 outbox-worker в Helm и локальный режим worktree лаунчера.
- Трассировочная матрица и этап 3 MVP следуют после подтверждённого завершения
  AUD-2026-10.

## Срез от 2026-11-13

Дата среза: **2026-11-13 (UTC)**. Текущие итоги аудита — в [docs/audits/INDEX.md](../../audits/INDEX.md).
Полная предыдущая версия этого файла (8286 строк, датированные разделы
2026-09 — 2026-11-11) сохранена в git: `git show d8891684f:docs/superpowers/plans/STATUS.md`.

<a id="ветка-и-источник"></a>

## Ветка и источник — срез 2026-11-13

- Main: `5b3357858` — PR #1383 слит 2026-11-12.
- Ветка `egorribun`: впереди main коммитами закрытия аудита (на момент среза HEAD `d8891684f`).
  PR ещё не открыт. Его итоговый SHA требует собственных required checks; до них
  ни один CI, release или deployment статус не подтверждён.
- Scoped-приёмки от 2026-11-12 привязаны к hosted runs на main
  `eb853a37cca3a614a32c8ee598f7cf6f3d10e0ec` (PR #1380) и
  `81ee9ce6c64bd36fa9b0f48a6093bedf48611f7f` (PR #1382). Это исторические источники
  именно этих приёмок, а не текущий main.

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
| AUD-381 | P | ZAP и Nuclei на эфемерном Compose stand должны пройти на main; Nuclei проходит, проверенного ZAP-отчёта ещё нет. |

Остальные требования каждой находки не изменены. Закрытие требует проверки конкретного
source SHA, а не этого среза.

## MVP-этапы (ссылка: [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md))

| Этап | Статус |
| --- | --- |
| 1. Решение и документы | Выполнен. |
| 2. Q1 и Q4 в CI | Интегрированы. Каждый новый SHA требует свежих required-check results. |
| 3. Core и продукт | Не начат. |
| 4. Визуал и performance | Утверждён только визуальный пакет Home12. |
| 5. Security, ledger, данные | Восстановление DB/S3 backup никогда не запускалось. |
| 6. Выпуск | Не начат. |

## Открытые решения владельца

- AUD-484: решено владельцем 2026-11-12, alerts 2995–3002 dismissed, analyses сохранены.
- AUD-381: цель — эфемерный Compose stand в CI (решение владельца 2026-11-12). Проверенного ZAP-отчёта ещё нет.
- AUD-169, AUD-188, AUD-189, AUD-438: kind + Calico принят владельцем как среда доказательств
  (2026-11-12); решения и ограничения записаны в supplement от 2026-11-17. AUD-251 принят на этой среде.

## Следующие шаги

1. AUD-154: green hosted Owned Live Acceptance на точном SHA; AUD-381: ZAP и Nuclei с проверенным ZAP-отчётом.
2. Операционная цель: два последовательных green полных Core run на `main`.
3. Дождаться required checks PR #1422 на его итоговом SHA. Обычный merge; без admin bypass.
4. Этап 3: traceability matrix ТЗ 2–13 (MVP_MASTER_PLAN, Блок 4), реальный Chromium,
   два последовательных прогона, stop/start и seed.
5. Этап 5: один DB/S3 backup и restore в изолированную цель (ещё не запускался).
6. Этап 4: визуальные и performance-пакеты RU/EN, light/dark, desktop/mobile за пределами Home12.

## History

Предыдущие датированные разделы, checkpoints, hosted-run журналы и доказательства до
2026-11-12 не удалены из истории: см. `git log -- docs/superpowers/plans/STATUS.md`
и `git show d8891684f:docs/superpowers/plans/STATUS.md`.
