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
- Локальная проверка на стенде `715010904` с закреплённым образом ZAP (пассивный baseline с тем же
  hook и ключами CSRF): 10055-6 — low, 10202 — informational, 10055-4 нет, medium нет. Демо-изображения
  отдаются через `/api/v1/img` (AVIF), CSP сужен, форма входа содержит `data-csrf="header"`.
  Активное правило 20012 требует полного сканирования.
- **Локальный OOM на source `715010904`.** При запросах холодных изображений память backend дошла до
  лимита 512 MiB, gunicorn-воркеры получили SIGKILL, `OOMKilled=true`. Изображения: 149 ответов 200,
  15 — 502, 11 — 404; входы: 8 ответов 200, 7 — 502. На этом source `/api/v1/img` кодировал AVIF
  без ограничения параллельности.
- **Hosted #1541 отдельно:** на source `715010904` упали
  [Owned Live](https://github.com/egorribun/university_ecosystem/actions/runs/44836750319)
  (49 passed, 3 flaky; затем NATS preflight `inventory_invalid_runtime`) и
  [live-realtime-visual](https://github.com/egorribun/university_ecosystem/actions/runs/44836750657).
  На source `f0ee138d5` [Owned Live](https://github.com/egorribun/university_ecosystem/actions/runs/44843030034)
  завершился с 47 passed, 2 failed, 2 skipped, 3 flaky и ошибкой NATS preflight
  `inventory_invalid_runtime`. В [CI Matrix](https://github.com/egorribun/university_ecosystem/actions/runs/44843030340)
  realtime job завершился с 17 passed, 1 failed (desktop messenger-unread-read). Эти результаты не
  доказывают OOM как причину hosted-сбоев.
- `live-realtime-visual` на первой голове #1541 (`1881aa596`) тоже упал: вход отвечал 502. Повтор
  без доказательства инфраструктурного сбоя не запускался.
- **Hosted на source `3c65c9e60`, synthetic merge `52a1d673c`:**
  - [Owned Live](https://github.com/egorribun/university_ecosystem/actions/runs/44848242946/job/136673165875):
    E2E — 52 passed, 2 skipped; стенд остановлен успешно. NATS preflight завершился
    `inventory_invalid_runtime`, без имени службы и причины; job упал.
  - [Realtime и visual](https://github.com/egorribun/university_ecosystem/actions/runs/44848243079/job/136673168806):
    realtime — 17 passed, 1 flaky; четыре именных случая прошли на retry 0, но агрегат не принят.
    Все 24 страницы визуальной матрицы ответили HTTP 200. В одном варианте News
    (английский язык, тёмная тема, ширина 390 px) проверка не подтвердила стабильный
    непустой список с фильтром по умолчанию.
  - Прошли 77 из 78 обязательных проверок. `CI Success` сохранил отказ realtime/visual.
    Все десять анализов CodeQL/Checkov завершились без находок. После публикации недостающей
    зависимости Renovate точечный повтор прошёл, включая оба PostgreSQL gate и Quality & Coverage.
- **Изменения в `3c65c9e60`:** ограничены преобразования изображений на процесс и число потоков AVIF;
  повторный seed обновляет узнаваемые старые URL демо-медиа в совпадающих записях; элементы формы
  сброса пароля в SSR заблокированы до гидратации. CSP-фильтр понижает уровень только для однозначного
  канонического evidence с единственной разрешённой `style-src`; неоднозначное evidence не понижается.
  Это относится к одной строке evidence, а не ко всем заголовкам ответа.
- В WSL прошли 233 теста; `app/services/image_proxy.py` и `app/core/config/storage.py` — 100% строк и
  ветвей. Локальный обычный smoke dashboard/news декодировал три AVIF и запросил один URL для пяти
  ширин; OOM и рестартов не было, после очистки контейнеров, сетей и томов осталось 0/0/0.
- При отказе NATS с `inventory_invalid_runtime` новая диагностика выводит нарушенное условие
  и имя службы из списка Core. Для неизвестного имени используется `unknown`.
- `SmartImage` указывает ширины в `srcset` только для путей, которым image proxy может передать
  параметр `w`. Для абсолютного URL карточка использует исходное изображение через `src`.
- На локальном Core с тем же `3c65c9e60` обе выборочные проверки готовности прошли.
  В News (en, тёмная тема, 390 px) отобразились десять статей с фильтром All,
  в Events (ru, светлая тема, 1440 px) — десять карточек. Обе страницы ответили HTTP 200.
  Браузер работал с отключёнными service workers и закрытым внешним доступом.

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

1. PR #1541: завершить диагностику hosted-сбоев и получить required checks для итогового SHA перед
   обычным merge.
2. После merge: DAST и полный Core на `main` (полный Core не чаще одного раза в 2 часа). Зелёный ZAP и
   Nuclei с проверенным отчётом закрывают AUD-381.
3. AUD-154: найти причину сбоев mobile/desktop topics и установить ответы для конкретных попыток, затем два
   последовательных green полных Core на `main`.
4. npm #1520: отдельный PR с привязкой проекцией D1–D4 (ADR-047, раздел «npm manifest projection binding»), затем
   обновления с удержанием maplibre 6.15.0, jsdom 30.1.3, Playwright 1.64.1.
5. Обновить `docs/audits/*` до 512/512 по hosted-доказательствам, затем этапы 3–6 мастер-плана.
