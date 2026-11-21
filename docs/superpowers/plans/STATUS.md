# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-21

- [PR #1539](https://github.com/egorribun/university_ecosystem/pull/1539) с source `ae0289f7a` слит в
  `main` как `cca6c8cab`; [PR #1540](https://github.com/egorribun/university_ecosystem/pull/1540) с source
  `572343ad4` — как `7c0af5d42`. Все required checks #1540 на `572343ad4` прошли.
- Проверки на `main` `7c0af5d42`:
  - **DAST** ([run 44818619531](https://github.com/egorribun/university_ecosystem/actions/runs/44818619531)).
    30003 больше не сообщается. Остались 4 medium: 10055 (`img-src` и `style-src`), 10202 и 20012.
  - **Полный Core** ([run 44818624328](https://github.com/egorribun/university_ecosystem/actions/runs/44818624328)).
    221 passed, 1 failed, 8 skipped, 2 flaky.
    - Шесть записей AUD-154 прошли с первой попытки.
    - Mobile notification-topics-delivery упал на обеих попытках; при очистке каждой указано
      `current-user-row=not-found`. Общая выборка worker — `sent=9 gone=3`, три ответа в группе 4xx;
      статусы отдельных попыток не записаны. Связь с конкретным тестом и ответ FCM 410 не доказаны.
      У каждого теста свой временный профиль Chrome.
    - Flaky — mobile push-delivery и footer-bottom-navigation.
- [PR #1541](https://github.com/egorribun/university_ecosystem/pull/1541) открыт (`egorribun` → `main`,
  актуальная голова и её проверки — по ссылке); он несёт решения владельца 2026-11-21 (ADR-047):
  - **10202 и 20012.** Формы входа, регистрации и сброса пароля помечены `data-csrf="header"`. ZAP
    запускается с `rules.csrf.ignore.attname/attvalue` для информационной классификации этих форм.
  - **10055-6.** `style-src 'unsafe-inline'` — принятый риск. Hook ZAP понижает до low только этот
    подпункт и только для точной директивы.
  - **10055-4.** Исправление: `img-src 'self' data: blob: https://i.scdn.co`.
    - Обложки Spotify — только с `i.scdn.co`.
    - Изображения статей — только относительные.
    - Обложка истории — только из загрузки, иначе 422.
    - Запасной аватар — локальный.
    - 35 демо-изображений picsum (разовое скачивание с разрешения владельца) хранятся в
      `scripts/demo_media/` с источником и лицензией Unsplash. Сид кладёт их в хранилище.
    - Заглушки picsum в live E2E и визуальном аудите удалены.
  - **Регистрация** фиксирует транзакцию поиска арендатора до HIBP и хеширования, как вход.
  - **Переподвязка один к одному.** `server-csp.mjs` (Semgrep row 14, запись 443) и
    `compliance_service.py` (row 13, запись 431). Инвентарь остаётся 524.
- Локальный пассивный ZAP baseline на стенде `715010904` с закреплённым образом, тем же hook и ключами
  CSRF: 10055-6 — low, 10202 — informational, 10055-4 и medium нет. Активное правило 20012 требует
  полного сканирования.
- **Hosted-результаты #1541** (остальные обязательные проверки на каждом source прошли):

  | Source | Owned Live Core | Realtime и visual |
  | --- | --- | --- |
  | `1881aa596` | — | вход отвечал 502 |
  | [`715010904`](https://github.com/egorribun/university_ecosystem/actions/runs/44836750319) | 49 passed, 3 flaky; NATS preflight `inventory_invalid_runtime` | [упал](https://github.com/egorribun/university_ecosystem/actions/runs/44836750657) |
  | [`f0ee138d5`](https://github.com/egorribun/university_ecosystem/actions/runs/44843030034) | 47 passed, 2 failed, 3 flaky; NATS preflight | [realtime](https://github.com/egorribun/university_ecosystem/actions/runs/44843030340): 17 passed, 1 failed |
  | [`3c65c9e60`](https://github.com/egorribun/university_ecosystem/actions/runs/44848242946) | 52 passed, 2 skipped; NATS preflight | [realtime](https://github.com/egorribun/university_ecosystem/actions/runs/44848243079) 17 passed, 1 flaky; visual 22/24 |
  | [`3a452a8a8`](https://github.com/egorribun/university_ecosystem/actions/runs/44860700541) | **прошёл**, включая NATS preflight | [realtime](https://github.com/egorribun/university_ecosystem/actions/runs/44860700884) 18 passed; visual 18/24 |
  | `28afad9c5` | **прошёл** | realtime и visual **прошли** (24/24); упал только Contract Tests (gitleaks, состояние процесса `X`) |
  | `01a434839` | [прошёл](https://github.com/egorribun/university_ecosystem/actions/runs/44906878207/job/136854251753) | Realtime прошёл; [visual 23/24](https://github.com/egorribun/university_ecosystem/actions/runs/44906878502/job/136854254040). CI Success не прошёл из-за visual. |

  На `3c65c9e60` в visual не прошли News (en, тёмная тема, 390 px: два ответа API 4xx, список не
  подтверждён) и Events (ru, светлая тема, 1440 px: ошибка консоли). На `3a452a8a8` шесть маршрутов
  второй половины матрицы (ru) получили ответы API 4xx на ресурсы. Там же два frontend unit-теста
  ожидали `srcset` и `sizes` для логотипа и внешнего URL после `a17ef41f3`.
  На `01a434839` Dashboard (en, светлая тема, 1440 px) записал один сетевой сбой GET к API без
  HTTP-статуса. Локальный полный стенд из того же дерева прошёл 24/24 без ошибок браузера, HTTP и сети.
  Причина hosted-сбоя пока не установлена. Отчёт теперь добавляет фиксированные категории Chrome
  и API для сетевых ошибок с ограничением числа записей.
- **Восстановление сборки Caddy.** Alpine удалил `zlib-1.3.2-r1.apk` из `v3.23/main` (HTTP 404).
  Непосредственный сбой подтверждён в [Unauthenticated routes smoke](https://github.com/egorribun/university_ecosystem/actions/runs/44867129509/job/136733196460)
  на `113299b4b`. Исправление получает нужный диапазон байт из официального ISO Alpine 3.23.8,
  проверяет размер и прежний SHA-256 для каждой архитектуры и устанавливает подписанный APK.
  Версии `libapk` и `apk-tools` закреплены на 3.0.9-r0 из подписанного индекса.
  Оба SHA-256 сверены с содержимым ISO. Сборка Caddy на `01a434839` прошла в обеих темах
  [Unauthenticated routes smoke](https://github.com/egorribun/university_ecosystem/actions/runs/44906878206).
- **Нагрузка на backend (измерено локально 2026-11-21).**
  - В простое backend занимал 455 MiB из лимита 512M: два воркера gunicorn по ~254 MB RSS и мастер
    68 MB.
  - Холодная серия из 175 запросов демо-изображений держала cgroup на лимите (более 20 000 событий
    `memory.max`). Чтения хранилища истекали через 21–25 с и возвращались как 404, Caddy отвечал 502
    через 30 с.
  - Каждая операция S3 создавала новую сессию aioboto3: около 0,3 с CPU и 12 MiB.
  - NATS preflight проверяет `OOMKilled` и `ExitCode` каждого контейнера. Связь с hosted-сбоем покажет
    диагностика из `09e9d1161`.
- **Исправления после `3c65c9e60`:**
  - `09e9d1161` — NATS preflight называет нарушенное условие и службу из списка Core (`unknown` для
    прочих). Переподвязка один к одному: Semgrep row 7, запись 495.
  - `a17ef41f3` — `SmartImage` задаёт ширины в `srcset` только для путей image proxy.
  - `9bc0b3776` — одна сессия aioboto3 на экземпляр `S3Storage` и event loop; AVIF со speed 8;
    лимит памяти backend в Compose 768M, как request в Kubernetes.
  - `ebd645e68` — у встроенного логотипа нет вариантов ширины: убраны `sizes` и `responsiveWidths`,
    тесты приведены к новому контракту; фикстура RelatedNews использует путь прокси вместо picsum.
  - `73a3bef60` — `/api/v1/img` получил отдельный бюджет `RATE_LIMIT_STATIC` (300/minute) в глобальном
    ограничителе. Раньше изображения расходовали общий бюджет клиента 200/minute: страница добавляет
    15–20 запросов изображений, и визуальная матрица одного пользователя исчерпывала его к середине.
  - Та же серия на стенде из `9bc0b3776`: 175/175 ответов 200, p95 3,4 с вместо 21,7 с, вся серия
    38,5 с вместо 131 с, пик памяти 616 MiB из 768M, событий `memory.max` и OOM нет.

## Аудит: текущий итог — 510/512

Формальный итог: **510/512 (99.6%) accepted or resolved, 2 open**, **1S / 1P / 0U / 0N**.
Границы решений: [Current scoped supplement — 2026-11-17](../../audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-17).

Счёт поддерживается в шести файлах: `docs/audits/INDEX.md`, reassessment, reconciliation,
`AUDIT-2026-10.md`, этот файл и `docs/README.md`. `docs/audits/*` меняются только по hosted-доказательствам
на точном SHA.

The current policy-file inventory is **524 dispositions / 242 baseline identities / 27 Gitleaks fingerprints / 15 Semgrep rows**. This is inventory only, not evidence of a passing scan or required checks.

### Открытые находки

Состав — из [current 2-finding complement](../../audits/AUDIT-2026-10-30-reconciliation.md#current-2-finding-reconciliation--2026-11-17).

| ID | Статус | Что нужно для закрытия |
| --- | --- | --- |
| AUD-154 | S | Два последовательных green полных Owned Live Acceptance run на `main` (эквивалентность принята владельцем), включая read-receipt live spec. Наблюдались сбои mobile/desktop notification-topics; причина не установлена. |
| AUD-381 | P | Успешные подтверждённые отчёты ZAP и Nuclei на эфемерном Compose-стенде для точного SHA `main`. Последний отчёт ZAP на `7c0af5d42` — 4 medium; #1541 вносит изменения против этих предупреждений, но не закрывает аудит без новых подтверждённых отчётов на `main`. |

## MVP-этапы (ссылка: [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md))

| Этап | Статус |
| --- | --- |
| 1. Решение и документы | Выполнен. |
| 2. Q1 и Q4 в CI | Интегрированы. Каждый новый SHA требует свежих required-check results. |
| 3. Core и продукт | Подготовлены сценарии и матрица; итоговая приёмка не проведена. |
| 4. Визуал и performance | Утверждён только визуальный пакет Home12. |
| 5. Security, ledger, данные | Восстановление DB/S3 backup никогда не запускалось. |
| 6. Выпуск | Не начат. |

## Решения владельца (действующие)

- AUD-381 — эфемерный Compose-стенд в CI (2026-11-12). AUD-484 — alerts 2995–3002 dismissed (2026-11-12).
- AUD-169, AUD-188, AUD-189, AUD-438, AUD-251 — kind + Calico как среда доказательств (2026-11-12).
- ZAP: 10106 исключено только для CI-стенда без TLS (2026-11-19). 10202/20012 — информационные для
  форм с `data-csrf="header"`, 10055-6 — принятый риск low, 10055-4 — исправление (2026-11-21). Любое
  другое исключение — только с согласия владельца.
- Демо-изображения хранятся в репозитории (2026-11-21).
- Новые PR облачного агента интегрируются пачкой, без экспериментов с новыми workflow. Dependabot npm
  (#1520, преемник #1404) — последним, после реализации привязки проекцией D1–D4 (одобрено 2026-11-15).
- Мутационные линии вне объёма MVP (2026-11-13).

## Следующие шаги

1. Получить для #1541 required checks на итоговом SHA, включая независимые live и realtime/visual,
   перед обычным merge.
2. После merge: DAST и полный Core на `main` (полный Core не чаще одного раза в 2 часа). Зелёный ZAP и
   Nuclei с проверенным отчётом закрывают AUD-381.
3. AUD-154: найти причину сбоев mobile/desktop topics и установить ответы для конкретных попыток, затем два
   последовательных green полных Core на `main`.
4. npm #1520: отдельный PR с привязкой проекцией D1–D4 (ADR-047, раздел «npm manifest projection binding»), затем
   обновления с удержанием maplibre 6.15.0, jsdom 30.1.3, Playwright 1.64.1.
5. Обновить `docs/audits/*` до 512/512 по hosted-доказательствам, затем этапы 3–6 мастер-плана.
