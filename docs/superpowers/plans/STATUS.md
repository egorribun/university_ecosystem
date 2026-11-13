# Статус выпуска MVP v1.0.0 — краткий текущий срез

Дата среза: **2026-11-13 (UTC)**. Текущие итоги аудита — в [docs/audits/INDEX.md](../../audits/INDEX.md).
Полная предыдущая версия этого файла (8286 строк, датированные разделы
2026-09 — 2026-11-11) сохранена в git: `git show d8891684f:docs/superpowers/plans/STATUS.md`.

## Ветка и источник

- Main: `5b3357858` — PR #1383 слит 2026-11-12.
- Ветка `egorribun`: впереди main коммитами закрытия аудита (на момент среза HEAD `d8891684f`).
  PR ещё не открыт. Его итоговый SHA требует собственных required checks; до них
  ни один CI, release или deployment статус не подтверждён.
- Scoped-приёмки от 2026-11-12 привязаны к hosted runs на main
  `eb853a37cca3a614a32c8ee598f7cf6f3d10e0ec` (PR #1380) и
  `81ee9ce6c64bd36fa9b0f48a6093bedf48611f7f` (PR #1382). Это исторические источники
  именно этих приёмок, а не текущий main.

## Аудит: 506/512

Формальный итог: **506/512 (98.8%) accepted or resolved, 6 open**, **4S / 2P / 0U / 0N**.
Приняты AUD-167, AUD-251, AUD-432 и AUD-484, каждый по своему критерию. Предыдущий срез
502/512 сохранён как история. Границы решений:
[Current scoped supplement — 2026-11-13](../../audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-13).

Счёт поддерживается в шести файлах: `docs/audits/INDEX.md`, reassessment,
reconciliation, `AUDIT-2026-10.md`, этот файл и `docs/README.md`.

The current policy-file inventory is **512 dispositions / 242 baseline identities / 27 Gitleaks fingerprints / 15 Semgrep rows**. This is inventory only, not evidence of a passing scan or required checks.

### Открытые находки и текущий план

Состав открытых находок — из
[current 6-finding complement](../../audits/AUDIT-2026-10-30-reconciliation.md#current-6-finding-reconciliation--2026-11-13).

| ID | Статус | Что нужно для закрытия |
| --- | --- | --- |
| AUD-154 | S | Green hosted Owned Live Acceptance run на точном SHA (эквивалентность принята владельцем); read-receipt live check добавить, в live-наборе ещё есть падения. |
| AUD-169 | S | Реальный file-processor в kind + Calico: старт процесса и пара revoked/unrevoked токенов через него; сейчас Redis-проверки идут через stand-in pod. |
| AUD-188 | S | Реальный JWKS refresher file-processor, приём ProcessFile по gRPC и обновление ключа на каждой реплике без рестарта; сейчас stand-in consumer без refresher. |
| AUD-438 | S | HTTP GET /metrics: неаутентифицированный успех из monitoring и отказ из неизбранного namespace и публичного ingress; сейчас только TCP-проверки. |
| AUD-189 | P | В kind: link-local TCP/443, backup public TCP/443 (политика при backup.enabled=true), notifications-worker и outbox-worker по addenda ADR-054 от 2026-11-13. |
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
  (2026-11-12); открыты до проверок из таблицы выше. AUD-251 принят на этой среде.

## Следующие шаги

1. Открыть PR из `egorribun` и дождаться required checks на его итоговом SHA. Обычный merge; без admin bypass.
2. Этап 3: traceability matrix ТЗ 2–13 (MVP_MASTER_PLAN, Блок 4), реальный Chromium,
   два последовательных прогона, stop/start и seed.
3. AUD-169, AUD-188, AUD-189, AUD-438: реальный file-processor и недостающие проверки в kind + Calico run.
4. AUD-154: green hosted Owned Live Acceptance на точном SHA; AUD-381: проверенный ZAP-отчёт.
5. Этап 5: один DB/S3 backup и restore в изолированную цель (ещё не запускался).
6. Этап 4: визуальные и performance-пакеты RU/EN, light/dark, desktop/mobile за пределами Home12.

## History

Предыдущие датированные разделы, checkpoints, hosted-run журналы и доказательства до
2026-11-12 не удалены из истории: см. `git log -- docs/superpowers/plans/STATUS.md`
и `git show d8891684f:docs/superpowers/plans/STATUS.md`.
