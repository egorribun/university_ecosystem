# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-22

- [PR #1549](https://github.com/egorribun/university_ecosystem/pull/1549) с source `09a2a727`
  слит обычным merge в защищённый `main` как `fc92e1835ac985eb151ed5564f4a7bbc4ede1db1`.
  На source прошли все 78 обязательных пар context/app и отдельная проверка CodeQL. Проверочный
  merge `f240694a`, source и итоговый `main` имеют одинаковое дерево. Проверка SSR-заголовка ждёт
  готовности клиентского head; для сбоя read-receipt добавлена ограниченная диагностика без изменения
  самой проверки. [PR Core smoke](https://github.com/egorribun/university_ecosystem/actions/runs/44971081790/job/137050784038)
  прошёл с [receipt 14733839451](https://github.com/egorribun/university_ecosystem/actions/runs/44971081790/artifacts/14733839451);
  [realtime и visual](https://github.com/egorribun/university_ecosystem/actions/runs/44971081868/job/137050785456)
  прошли (24/24; [артефакт 14734825914](https://github.com/egorribun/university_ecosystem/actions/runs/44971081868/artifacts/14734825914)).

  - Полный Core на `main` `fc92e1835ac985eb151ed5564f4a7bbc4ede1db1` завершился ошибкой в live E2E:
    220 passed, 1 failed, 8 skipped, 3 flaky. Desktop notification-topics не прошёл на обеих попытках.
    Flaky: desktop reflow расписания, mobile MapLibre phase 2 и mobile начальная доставка события
    авторизованной группы Messenger до удаления участника. Повторы прошли.
    Все шесть именных случаев AUD-154 прошли с первой попытки, включая desktop и mobile read-receipt.
    Проверка checkout, запуск и остановка стенда прошли; live E2E завершился ошибкой.
    [Задание](https://github.com/egorribun/university_ecosystem/actions/runs/44993593499/job/137119776922)
    [Receipt 14744561230](https://github.com/egorribun/university_ecosystem/actions/runs/44993593499/artifacts/14744561230)
    имеет SHA-256 `46bcd88bee53b6345815ea67ea266f716718a7ac1f23f35ee504078a4d2f9611`.
    Эти результаты не устанавливают причину сбоев или соответствие отдельной попытки и ответа
    push-провайдера. Для AUD-154 по-прежнему нужны два последовательных зелёных полных Core на
    `main` с read-receipt; этот красный запуск их не заменяет.

  - Следующий [полный Core](https://github.com/egorribun/university_ecosystem/actions/runs/45014106658/job/137182595658)
    на том же SHA запущен по расписанию, попытка 1; задание началось в 10:47:11 UTC и завершилось
    ошибкой в live E2E: 220 passed, 2 failed, 8 skipped, 2 flaky. На desktop и mobile упала проверка
    Story memory при строгом сравнении счётчиков DOM (`story-viewer-memory.live.spec.ts:522`).
    Flaky: desktop фокус в расписании (`schedule-200-equivalent-reflow.live.spec.ts:56`) и mobile
    доставка notification-topics при ожидании нативного уведомления
    (`notification-topics-delivery.live.spec.ts:557`, `:584`, `:1265`); повторы прошли.
    Все шесть именных случаев AUD-154 прошли с первой попытки, включая desktop и mobile read-receipt.
    Проверка checkout, запуск и остановка стенда прошли; live E2E завершился ошибкой.
    [Receipt 14752895011](https://github.com/egorribun/university_ecosystem/actions/runs/45014106658/artifacts/14752895011)
    имеет проверенный SHA-256 `7773d74ee0e27ac1b8147d03d5fa408efbb3f6678a8f0742679c3457ae1e991e`.
    Эти результаты не устанавливают причину сбоев или связь отдельной попытки с ответом push-провайдера.

  - [DAST](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918), попытка 1,
    выполнен по расписанию на том же `main` SHA. [Проверка доверенного source](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918/job/137158586332)
    прошла. [Nuclei](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918/job/137158603498)
    прошёл; проверенный санитизированный отчёт пуст. [Артефакт 14748396373](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918/artifacts/14748396373)
    имеет SHA-256 `e88643c475a19cddb70bbe0cf420c43dc9336ddfe916615646cba9a8eda0b402`.
    [ZAP](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918/job/137158603525)
    не прошёл severity gate: 17 informational, 7 low, 0 medium, 1 high; `coverage_complete=false`.
    Происхождение и SHA-256 [артефакта 14747819065](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918/artifacts/14747819065)
    проверены: `628574e9a608342faaa499203d5b2bf08d5e3fd6e3a8c4dba23a64323c0a053e`.
    Эти категории не устанавливают причину, расположение или затронутость high; AUD-381 остаётся открытым.

- [PR #1545](https://github.com/egorribun/university_ecosystem/pull/1545) с source `9690f2c0`
  слит обычным merge в защищённый `main` как `d8a010b4`. На source прошли 78 обязательных проверок и CodeQL.
  Проверочный merge `ee3a6b619`, source и итоговый `main` имеют одинаковое дерево.

  - `npm audit --audit-level=info` сообщил о нуле уязвимостей в frontend lockfile.
    [Node.js Dependency Audit](https://github.com/egorribun/university_ecosystem/actions/runs/44949553699/job/136984366141)
  - Сборка и контракты WASM прошли. SHA-256 артефакта — `1310ff61338bcb24c03fc7026c63797ac1cc268d85d482661eeb76546d44463c`.
    [Сборка](https://github.com/egorribun/university_ecosystem/actions/runs/44949553699/job/136984238245)
    [Контракты](https://github.com/egorribun/university_ecosystem/actions/runs/44949553699/job/136984768444)
    [Артефакт 14724414910](https://github.com/egorribun/university_ecosystem/actions/runs/44949553699/artifacts/14724414910)
  - Статический анализ MapLibre 6.15.0 прошёл на `ee3a6b619`. Размер чанка — 292 660 gzip-байт при лимите 292 864.
    SHA-256 отчёта — `7282b66289c86a9d3499e94ec1caf6f870910ced15a78eba7053b0cdb3cdb9bc`.
    [Bundle report 14724877946](https://github.com/egorribun/university_ecosystem/actions/runs/44949553699/artifacts/14724877946)
  - PR Core smoke, realtime и все 24 visual-снимка прошли.
    [PR Core smoke](https://github.com/egorribun/university_ecosystem/actions/runs/44949553489/job/136984235828)
    [Receipt 14725970905](https://github.com/egorribun/university_ecosystem/actions/runs/44949553489/artifacts/14725970905)
    [Realtime и visual](https://github.com/egorribun/university_ecosystem/actions/runs/44949553699/job/136984238221)
    [Артефакт 14725967293](https://github.com/egorribun/university_ecosystem/actions/runs/44949553699/artifacts/14725967293)

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
- [PR #1541](https://github.com/egorribun/university_ecosystem/pull/1541) слит обычным merge после
  78 обязательных проверок и CodeQL на `3156d797a`. Тогдашний `main` — `149814844`.
  [Полный Core](https://github.com/egorribun/university_ecosystem/actions/runs/44925413925) на этом SHA
  дал 223 passed, 8 skipped и 1 flaky. Проверенный артефакт `14717545206` привязан к заданию
  `136910292817`. Все шесть именных случаев AUD-154 прошли с первой попытки, включая read-receipt
  на desktop и mobile. Сбой первого прохождения mobile-сценария Email OTP зарегистрирован
  после HTTP 200 при проверке отзыва соседнего WebSocket. Этот полный Core остался красным.
  Изолированная проверка подтвердила, что durable tombstone мог дать `1008` вместо ожидаемого
  `4401`. В пакете исправления подтверждённый отзыв закрывает соединение с `4401`, а при ошибке
  хранилища остаётся `1008`. Hosted-прогон не зафиксировал фактический close code сбоя.
  PR реализует решения владельца 2026-11-21 (ADR-047):
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
  | `753c2c572` | [прошёл](https://github.com/egorribun/university_ecosystem/actions/runs/44910470846/job/136864997618) | Realtime прошёл; [visual 23/24](https://github.com/egorribun/university_ecosystem/actions/runs/44910471073/job/136864999567). Повторился сетевой сбой Dashboard. |
  | `bba42fa82` | [прошёл](https://github.com/egorribun/university_ecosystem/actions/runs/44914673591/job/136881639122) | Realtime прошёл; [visual 23/24](https://github.com/egorribun/university_ecosystem/actions/runs/44914673817/job/136877707232). Сбой воспроизвёлся на изображении из API. |
  | `762478ff6` | [прошёл](https://github.com/egorribun/university_ecosystem/actions/runs/44918659401/job/136889652977) | [Realtime и visual 24/24 прошли](https://github.com/egorribun/university_ecosystem/actions/runs/44918659599/job/136889655183). Shard 2 упал на числе регистраций маршрута API в AUD-400. |
  | `3156d797a` | [прошёл](https://github.com/egorribun/university_ecosystem/actions/runs/44921979319/job/136899801171) | [Realtime и visual 24/24 прошли](https://github.com/egorribun/university_ecosystem/actions/runs/44921979509/job/136899802964). Все 78 обязательных проверок прошли. |

  На `3c65c9e60` в visual не прошли News (en, тёмная тема, 390 px: два ответа API 4xx, список не
  подтверждён) и Events (ru, светлая тема, 1440 px: ошибка консоли). На `3a452a8a8` шесть маршрутов
  второй половины матрицы (ru) получили ответы API 4xx на ресурсы. Там же два frontend unit-теста
  ожидали `srcset` и `sizes` для логотипа и внешнего URL после `a17ef41f3`.
  На `01a434839` Dashboard (en, светлая тема, 1440 px) записал один сетевой сбой GET к API без
  HTTP-статуса. Локальный полный стенд из того же дерева прошёл 24/24 без ошибок браузера, HTTP и сети.
  На `753c2c572` для той же комбинации Chromium записал `net::ERR_FAILED` без HTTP-статуса.
  Точный маршрут запроса в hosted-прогоне пока не установлен. Отчёт добавляет фиксированные
  семейства API и типы ресурса Chrome для сетевых ошибок с ограничением числа записей.
  Изолированный тест воспроизвёл обрыв публичного `GET /api/v1/campus/config` в service worker
  при инициализации страницы в прежней сессии. Публичный GET теперь идёт напрямую с исходным
  `cache: "no-store"`. Соседние защищённые маршруты сохраняют проверку принадлежности ответа сессии.
  На `bba42fa82` уточнён тип hosted-сбоя. Это `net::ERR_FAILED` без HTTP-статуса для изображения
  из собственного семейства `/api/v1/img`. Повторился тот же сценарий Dashboard.
  В изолированном тесте инициализация прежней сессии превратила успешный ответ этого семейства
  в `Response.error()`. Same-origin GET к image proxy теперь сохраняет исходные запрос и ответ
  до приватного API-кеша и общего кеша изображений. Серверная ревалидация и границы доступа
  к защищённым вложениям сохраняются. Точный механизм hosted-сбоя ещё не установлен.
  В hosted-матрице `762478ff6` все 24 захвата завершились без ошибок сети и браузера. Артефакт
  снимков — `14713602601`. Прямой запрос image proxy выполняется в единственном обработчике API
  до проверки сессии. Неизменённый AUD-400 и полный локальный Vitest прошли (11 555 тестов).
- [PR #1544](https://github.com/egorribun/university_ecosystem/pull/1544) с source `5d402215f` слит в
  защищённый `main` как `c506c637c`. На source прошли все 78 обязательных проверок и CodeQL.
  Проверочный merge `cffa7910a`, source и итоговый `main` имеют одинаковое дерево.

  - Core smoke прошёл. [Задание](https://github.com/egorribun/university_ecosystem/actions/runs/44940349344/job/136955958577)
    [Receipt 14721518600](https://github.com/egorribun/university_ecosystem/actions/runs/44940349344/artifacts/14721518600)
  - Realtime и visual прошли. В артефакте все 24 снимка. [Задание](https://github.com/egorribun/university_ecosystem/actions/runs/44940349526/job/136955960512)
    [Артефакт 14722575291](https://github.com/egorribun/university_ecosystem/actions/runs/44940349526/artifacts/14722575291)
  - Nilaway прошёл. [Задание](https://github.com/egorribun/university_ecosystem/actions/runs/44940349338/job/136955958334)
  - Полный Core на `main` `c506c637c` завершился ошибкой. Итог — 223 passed, 8 skipped, 1 flaky.
    Фрейм сбоя указывает на проверку порога 44 px для кнопки закрытия мобильного меню.
    Измеренная ширина не записана. Все шесть именных случаев AUD-154 прошли с первой попытки,
    включая read-receipt на desktop и mobile.
    [Задание](https://github.com/egorribun/university_ecosystem/actions/runs/44943098243/job/136964397867)
    [Receipt 14723557616](https://github.com/egorribun/university_ecosystem/actions/runs/44943098243/artifacts/14723557616)
    Локальная браузерная проверка с зависимостями npm-пакета воспроизвела дробное округление DOMRect
    во время выезда меню при номинальной ширине 44 px. Тест проверяет рамку кнопки сразу после
    фокуса, затем измеряет стабильную область нажатия. Оба измерения требуют не менее 44 px.
  - Проверка frozen-RC отклонила манифест как недействительный или незамороженный.
    [Задание](https://github.com/egorribun/university_ecosystem/actions/runs/44943098243/job/136964397629)

  PR содержит восстановление Web Push, диагностику префиксов хешей и изоляцию DST-теста #1523.
  На `45f4f42ba` realtime и именные случаи
  AUD-154 прошли. [Visual-прогон](https://github.com/egorribun/university_ecosystem/actions/runs/44926043369/job/136912238208)
  зарегистрировал на Events (en, светлая тема, 390 px) два `net::ERR_FAILED` без HTTP-статуса в
  защищённых XHR GET семейств events и notifications.
  На `73db7bd17` [realtime и visual](https://github.com/egorribun/university_ecosystem/actions/runs/44932304600/job/136931377195)
  прошли (24/24; [артефакт 14719725628](https://github.com/egorribun/university_ecosystem/actions/runs/44932304600/artifacts/14719725628)).
  [Go lint ws-hub](https://github.com/egorribun/university_ecosystem/actions/runs/44932304600/job/136935008996) упал на сложности функции проверки отзыва сессии.
  На `930813a53` [Go lint ws-hub](https://github.com/egorribun/university_ecosystem/actions/runs/44935112740/job/136942741471)
  прошёл. В [visual](https://github.com/egorribun/university_ecosystem/actions/runs/44935112740/job/136939933430)
  повторился сбой Events (23/24; [артефакт 14720190570](https://github.com/egorribun/university_ecosystem/actions/runs/44935112740/artifacts/14720190570)).
  CI Success завершился ошибкой из-за `go-tests` на `73db7bd17` и `live-realtime-visual` на `930813a53`.
  Изолированный тест service worker воспроизвёл обрыв двух GET при установке того же серверного ключа.
  Отдельный тест запуска браузерного приложения воспроизвёл ранний запрос уведомлений до начала
  получения ключа. Источник сетевых ошибок в GitHub Actions ещё предстоит подтвердить.
  Список уведомлений ждёт завершения первого запуска авторизации, если подтверждённого владельца ещё нет.
  При обычном запуске с активным service worker установка ключа ждёт подтверждения обработки SET до
  одной секунды. При таймауте, отсутствии поддержки подтверждения или смене контроллера действует
  прежний путь синхронизации. Проверки владения запросом при выходе и смене сессии сохраняются.
  На `73db7bd17` и `930813a53` Nilaway выявил два обращения к потенциально пустому указателю в тесте
  кода закрытия WebSocket. На итоговом source тест явно проверяет указатель перед проверкой кода `4401`
  и причины закрытия.
- Полный Core на `main` `d8a010b4` завершился ошибкой. Итог — 216 passed, 8 skipped, 8 flaky.
  Пять из шести случаев AUD-154 прошли с первой попытки. Desktop read-receipt прошёл с повтора.
  Состояние прочтения уже сохранилось, когда проверка ожидала WebSocket-событие второй беседы.
  Точечный desktop-сценарий на отдельном локальном Core того же SHA прошёл с первой попытки.
  [Задание](https://github.com/egorribun/university_ecosystem/actions/runs/44963874897/job/137028426752)
  [Receipt 14732273374](https://github.com/egorribun/university_ecosystem/actions/runs/44963874897/artifacts/14732273374)

  Остальные первые попытки упали на измерении зума карты, доставке уведомлений, прокрутке вкладки
  расписания, заголовке News после SSR-навигации и сравнении счётчиков памяти Story Viewer.
  Оба сценария notification-topics нашли сохранённое in-app уведомление и дошли до ожидания нативного.
  Наблюдаемая браузерная подписка совпала с исходной. Запись текущего пользователя при очистке
  отсутствовала на первой попытке и была удалена на повторе. Одна запись Web Push 410 из хвоста
  worker совпала с мобильным наблюдением по усечённому хеш-префиксу. Из этого хвоста невозможно
  привязать ответ к конкретной попытке доставки.

- В рамках подготовки этапа 3 локальный R29 на `d8a010b4` прошёл через браузер. Участник группы
  переименовал её и добавил четвёртого участника. Владелец подтвердил итоговое имя и состав группы.

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
| AUD-381 | P | Успешные подтверждённые отчёты ZAP и Nuclei на эфемерном Compose-стенде для точного SHA `main`. На `fc92e183` Nuclei прошёл с пустым отчётом; ZAP не прошёл severity gate (1 high, `coverage_complete=false`). |

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

1. Разобрать mobile-проверку отзыва соседнего WebSocket после Email OTP и получить свежий отчёт DAST
   на `main`. Зелёные ZAP и Nuclei с проверенным отчётом закрывают AUD-381.
2. Получить обязательные проверки на пакете восстановления Web Push и тесте DST из #1523.
   Для AUD-154 нужны два последовательных зелёных полных Core на `main` с read-receipt,
   не чаще одного запуска в два часа. Диагностика префиксов хешей помогает сопоставить
   сбои доставки, а причину конкретной попытки подтверждают её отдельные доказательства.
3. npm #1520: отдельный PR с привязкой проекцией D1–D4 (ADR-047, раздел «npm manifest projection binding»), затем
   обновления с удержанием maplibre 6.15.0, jsdom 30.1.3, Playwright 1.64.1.
4. Обновить `docs/audits/*` до 512/512 по hosted-доказательствам, затем этапы 3–6 мастер-плана.
