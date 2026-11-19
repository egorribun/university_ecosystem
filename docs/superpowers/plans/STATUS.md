# Статус выпуска MVP v1.0.0 — краткий текущий срез

## Текущий срез — 2026-11-19

- `main` —
  [`64f7fd5148e8c6668b401e755be9459172f99ec8`](https://github.com/egorribun/university_ecosystem/commit/64f7fd5148e8c6668b401e755be9459172f99ec8)
  (слияние [PR #1422](https://github.com/egorribun/university_ecosystem/pull/1422): 124 required
  checks green на `bc7313ca4`). Перед слиянием перезапущены только упавшие Security Audit
  jobs: advisory GHSA-fc5q-39xc-vjpf (picomatch) отозвана GitHub 2026-11-18.
- Проверки после слияния на `64f7fd514`:
  - Kind + Calico NetworkPolicy — успех,
    [run 44471108615](https://github.com/egorribun/university_ecosystem/actions/runs/44471108615).
  - DAST — Nuclei прошёл; ZAP на hosted-раннере впервые запустился и сообщил о 5
    предупреждениях уровня medium (правила 10055 ×2, 10106, 10202, 40025),
    [run 44471112462](https://github.com/egorribun/university_ecosystem/actions/runs/44471112462).
    Опубликованный SARIF не содержит URL; разбор требует локального DAST-стенда. AUD-381 открыт.
  - Полный Core —
    [run 44471116074](https://github.com/egorribun/university_ecosystem/actions/runs/44471116074):
    217 пройдено, 8 пропущено, 7 нестабильных. Упали notification-topics-delivery
    (desktop, mobile), push-delivery (mobile), а также впервые admin-stories-rbac и
    events-scroll-restoration (mobile). Браузер подписан (`subscription=true`), но
    уведомления не приходят (`matches=0`); выборка воркера: `sent=9 gone=3`, три ответа
    провайдера 4xx. Успешных полных Core run подряд на `main` пока нет (цель — два).
- Формальный итог — **510/512 (99.6%), 2 открытых: 1S / 1P / 0U / 0N**. Документы аудита
  обновляются только по hosted-доказательствам на точном SHA.
- В `egorribun` влита вторая волна PR облачного агента после полной локальной проверки:
  #1431, #1443, #1446, #1447, #1453, #1456, #1464, #1481, #1489–#1498, #1508–#1517 и
  Dependabot Go (#1445, #1448, #1450). Найденные дефекты исправлены (ETag расписания,
  бесконечный цикл UUID backfill, фокус Select, возобновление опроса Spotify и др.),
  четыре companion-записи перепривязаны один к одному (ADR-047, 2026-11-19), правило
  retention под RLS вынесено в [ADR-055](../../adr/ADR-055-retention-cleanup-under-tenant-rls.md).
  #1501 закрыт как дубликат. Открытыми оставлены #1426 (SPIFFE для SSR) и диагностические
  эксперименты #1506, #1507, #1518: они добавляют workflow без продуктовой пользы.
- Cargo Deny: исключение RUSTSEC-2026-0543 (`chrono`) действует до 2026-12-17; затем
  переход `rust_ext` на `time`
  ([ADR-047](../../adr/ADR-047-risk-based-quality-policy.md#time-boxed-cargo-deny-exception-for-rustsec-2026-0543)).
- zlib: `frontend.Dockerfile` получает подписанный `zlib-1.3.2-r1` из release-ISO Alpine
  3.24.3 с проверкой SHA-256; `services/caddy/Dockerfile` по-прежнему качает его из
  `v3.23/main`, где пакет уже не индексирован (там `1.4-r0`). Оба пина убираются обновлением
  базовых образов: `node:24.22.3-alpine` и пересобранный `caddy:2.11.7-alpine` уже содержат
  `zlib-1.3.2-r1`. Для Node это требует пересборки пакета react-compiler/zod compat.
- Мёртвая запись кэша расписания: после #1446 `schedule:group:*` пишется прогревом и
  инвалидируется командами, но никем не читается. Удаление — следующая задача.

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

1. AUD-154: green hosted Owned Live Acceptance на точном SHA — сначала причина недоставки
   push (выборка воркера `sent=9 gone=3`) и новые мобильные падения admin-stories-rbac и
   events-scroll-restoration. AUD-381: разобрать 5 предупреждений ZAP на локальном
   DAST-стенде и исправить их или вынести на решение владельца.
2. Операционная цель: два последовательных green полных Core run на `main`.
3. PR из `egorribun` в `main` со второй волной: дождаться required checks на итоговом SHA.
   Обычный merge; без admin bypass. Затем удалить мёртвую запись кэша расписания.
4. Этап 3: traceability matrix ТЗ 2–13 (MVP_MASTER_PLAN, Блок 4), реальный Chromium,
   два последовательных прогона, stop/start и seed.
5. Этап 5: один DB/S3 backup и restore в изолированную цель (ещё не запускался).
6. Этап 4: визуальные и performance-пакеты RU/EN, light/dark, desktop/mobile за пределами Home12.

## History

Предыдущие датированные разделы, checkpoints, hosted-run журналы и доказательства до
2026-11-12 не удалены из истории: см. `git log -- docs/superpowers/plans/STATUS.md`
и `git show d8891684f:docs/superpowers/plans/STATUS.md`.
