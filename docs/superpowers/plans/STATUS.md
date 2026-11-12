# Статус выпуска MVP v1.0.0 — краткий текущий срез

Дата среза: **2026-11-12 (UTC)**. Текущие итоги аудита — в [docs/audits/INDEX.md](../../audits/INDEX.md).
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

## Аудит: 502/512

Формальный итог: **502/512 (98.0%) accepted or resolved, 10 open**, **4S / 6P / 0U / 0N**.
Приняты AUD-313, AUD-321, AUD-322, AUD-346, AUD-347, AUD-375, AUD-378 и AUD-483,
каждый по своему критерию. Границы решений:
[Current scoped supplement — 2026-11-12](../../audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-12).

Счёт поддерживается в шести файлах: `docs/audits/INDEX.md`, reassessment,
reconciliation, `AUDIT-2026-10.md`, этот файл и `docs/README.md`.

The current policy-file inventory is **512 dispositions / 242 baseline identities / 27 Gitleaks fingerprints / 15 Semgrep rows**. This is inventory only, not evidence of a passing scan or required checks.

### Открытые находки и текущий план

Состав открытых находок — из
[current 10-finding complement](../../audits/AUDIT-2026-10-30-reconciliation.md#current-10-finding-reconciliation--2026-11-12).

| ID | Статус | Что нужно для закрытия |
| --- | --- | --- |
| AUD-154 | S | Именованный live-кейс delivery/Sent/Read проходит на desktop и mobile, но исходный критерий не выполнен. Нужно доказать исходный критерий. |
| AUD-169 | S | Нужна Kubernetes-цель; подготовленные проверки ждут первого Kubernetes deployment. |
| AUD-188 | S | Нужна Kubernetes-цель; подготовленные проверки ждут первого Kubernetes deployment. |
| AUD-438 | S | Нужна Kubernetes-цель; подготовленные проверки ждут первого Kubernetes deployment. |
| AUD-167 | P | Два клиента и поддельный forwarded header через реальный Caddy к gateway и ws-hub. |
| AUD-189 | P | Нужна Kubernetes-цель; подготовленные проверки ждут первого Kubernetes deployment. |
| AUD-251 | P | Нужна Kubernetes-цель; подготовленные проверки ждут первого Kubernetes deployment. |
| AUD-381 | P | Реальный ZAP-скан авторизованной цели. Weekly DAST на main падает с 2026-09-20. |
| AUD-432 | P | `ssr-hydration-i18n.live.spec.ts` в focused run падают 4 из 6 кейсов. Продуктовый дефект или дефект спеки не определён. |
| AUD-484 | P | Владелец должен решить судьбу восьми Trivy alerts (2995–3002), открытых только на ref `egorribun`: удалить два устаревших analysis или отклонить alerts. Решения нет. |

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

- AUD-484: судьба восьми stale Trivy alerts (удалить analyses или dismiss). Не решено.
- AUD-381: авторизованная цель для ZAP-скана. Не назначена.
- AUD-169, AUD-188, AUD-189, AUD-251, AUD-438: нужно ли до v1.0.0 первое Kubernetes deployment,
  если ADR-054 фиксирует Docker Compose как MVP-цель. Не решено.

## Следующие шаги

1. Открыть PR из `egorribun` и дождаться required checks на его итоговом SHA. Обычный merge; без admin bypass.
2. Этап 3: traceability matrix ТЗ 2–13 (MVP_MASTER_PLAN, Блок 4), реальный Chromium,
   два последовательных прогона, stop/start и seed.
3. AUD-432: определить, продуктовый это дефект или дефект спеки в `ssr-hydration-i18n.live.spec.ts`;
   исправить и повторить focused job.
4. AUD-167: доказать поведение двух клиентов с поддельным forwarded header через реальный Caddy.
5. Этап 5: один DB/S3 backup и restore в изолированную цель (ещё не запускался).
6. Этап 4: визуальные и performance-пакеты RU/EN, light/dark, desktop/mobile за пределами Home12.

## History

Предыдущие датированные разделы, checkpoints, hosted-run журналы и доказательства до
2026-11-12 не удалены из истории: см. `git log -- docs/superpowers/plans/STATUS.md`
и `git show d8891684f:docs/superpowers/plans/STATUS.md`.
