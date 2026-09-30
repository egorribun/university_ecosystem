# University Ecosystem — план приёмки и выпуска MVP v1.0.0

Обновлён 2026-09-30. Это единый долговременный план, набор решений и критериев
приёмки для выпуска MVP. Текущие проверенные факты и ближайшие действия находятся
только в [STATUS.md](STATUS.md); продуктовые требования — в
[ТЗ MVP](University_Ecosystem_MVP.md); обязательные технические инварианты — в
`AGENTS.md`, доменных `AGENTS.md`, ADR, quality contract и runbooks.

Содержимое прежних handoff, старые CI-запуски, локальные worktree и прежние
машины являются историей, а не доказательством текущего состояния. Этот документ
закрепляет решения и критерии. Git, актуальная конфигурация и evidence, связанное с
проверяемым SHA, определяют факты. После переноса применимых требований старые
снимки, архивные отчёты и временные handoff пересматриваются и удаляются по блоку 2;
не создавайте второй текущий план.

## Цель и утверждённые решения

**Goal:** довести University Ecosystem до подтверждённого соответствия MVP-ТЗ,
завершить продуктовую, визуальную, техническую и инфраструктурную приёмку,
согласованно очистить устаревшее содержимое и выпустить `v1.0.0` с шестью
сертифицированными образами в GHCR. Goal считается завершённым после проверки
опубликованных image digests в локальном kind-кластере и наличия полного
SHA-bound release evidence, а не после написания кода или зелёных локальных тестов.

Утверждены следующие границы и решения:

- Полный автономный цикл охватывает изменения, проверки, согласованную очистку,
  обычные коммиты/push/PR/merge, GHCR и `v1.0.0`. Это не разрешает admin bypass,
  force-push, переписывание Git history или удаление чужих данных.
- Сохраняются 100% всех применимых метрик coverage и 100% viable mutation score.
  Не ослаблять quality contract исключениями, quarantine, увеличением timeout,
  waivers или ручной переклассификацией мутантов.
- Сначала восстановить достоверную проверяемость; продуктовую приёмку вести
  параллельно там, где она не конкурирует за тяжёлые ресурсы.
- ТЗ, планы и статус ведутся на русском; технические документы, интерфейсы,
  исходный код и runbooks — на английском, если существующий контракт не требует
  иного.
- Перед удалением архивов перенести полезные требования и инструкции, создать
  внешний Git bundle от rescue SHA и проверить восстановление файлов. Git history
  не переписывать. Сократить `.agents/skills`, сохранив реально применяемые
  навыки; рабочий harness сохранить. Историю миграций не сжимать.
- Для Kubernetes MVP использовать Envoy Gateway + Gateway API. Среды MVP —
  Docker Core/full, локальный kind и GHCR; внешний staging/production не входит.
- Нагрузочная цель WebSocket: 1 000 подключений, 500 пар, до 100 сообщений/с,
  30 минут, p95 доставки не выше 500 мс.
- Backup/restore демонстрирует RPO не хуже 24 часов и RTO не более 30 минут на
  измеренном наборе данных.
- Визуальные комплекты экранов и обновление визуальных baseline требуют
  пользовательского review/утверждения. Показывать небольшие сравнимые комплекты.
- Демо использует вымышленный университет, синтетические данные и роли
  student/teacher/admin. Не добавлять обязательную MFA для новых групп или новые
  предметные функции Activity. CDC остаётся вне MVP.

## Evidence и порядок работы

Каждое значимое доказательство должно фиксировать исходный SHA, workflow/job и
run/attempt либо локальную команду, конфигурацию и её hash, ОС и версии
инструментов/контейнеров, проверяемую популяцию, результат и ссылки на artifacts.
Для mutation/coverage evidence указывать происхождение и полноту инвентаря,
проверку владельца и отсутствие подмены локальным или старым результатом.
Указывать ограничения результата прямо. Старый успешный запуск не подтверждает
новый SHA; PR checks не подменяют проверку resulting `main` SHA.

Работать блоками 0–10; завершение каждого подтверждать доказательствами и
обновлением `STATUS.md`. После первого свежего полного inventory и живого прогона
переоценить срок по реальному темпу и critical path. Старые оценки длительности не
являются обещанием. Независимое исследование и тесты можно распределять между root
и максимум тремя субагентами. В одном worktree в каждый момент только один писатель;
тяжёлые локальные jobs сначала запускать по одному и увеличивать параллельность
только после измерения ресурсов. Не смешивать косметику, поведенческие исправления
и миграции данных в один недифференцированный пакет.

### Блок 0. Goal и проверяемый рабочий контекст

- Держать один активный Codex goal с целью из этого документа, без произвольного
  token budget. Goal уже создан; не создавать конкурирующие цели.
- Прочитать корневые и доменные `AGENTS.md`, это ТЗ/план, STATUS, применимые ADR,
  runbooks и quality contracts. Старые инструкции внутри документов считать
  историческими, если они не подтверждены текущими правилами.
- Зафиксировать branch, HEAD, `origin/main`, `origin/egorribun`, merge-base,
  tree status, актуальные CI run/attempt и состояние окружения. Сверить GitHub и
  GHCR доступ, Docker/WSL CPU/RAM/disk limits, браузеры Playwright и версии
  инструментов.
- Синхронизировать актуальный `main` обычным merge и разрешать конфликты с
  минимальным понятным diff. Проверить конечное дерево/PR diff. PR #1266 уже
  смержен; повторно его не создавать и не сливать.
- Использовать frozen/locked installation и зафиксированные версии; зависимости
  менять только по доказанной причине. Не предполагать наличие старого домашнего
  файла Claude, локального helper script или worktree: убрать такие зависимости
  из действующих инструкций и обеспечить продолжение только по tracked-документам.
- Иерархия источников: ТЗ определяет продукт; этот план — решения, требования и
  порядок; STATUS — короткое оперативное состояние; ADR/runbooks — подробности
  долговечных технических решений; Git/CI/evidence — наблюдаемые факты.

**Приёмка блока:** следующий исполнитель продолжает по tracked-документам без
доступа к старой машине; ancestry и PR diff проверены; идентичности CI/окружения
записаны в STATUS; пользовательские локальные данные сохранены.

### Блок 1. Восстановить немутационную проверяемость и закрыть security findings

На актуальном SHA воспроизвести и классифицировать исторические CI failures; не
считать старые логи вердиктом текущей версии.

- Проверить quality evidence tests, ожидавшие 16 элементов после удаления
  санитайзера: действующий контракт содержит 14 reports и три Rust branch reports.
  Исправить ожидания по фактическому составу, сохранив fail-closed полноту и
  обязательность evidence.
- Воспроизвести pre-commit, Source/Test Inventory, quality inventory и link/spelling
  проблемы по конкретным шагам. Исправить найденные дефекты и предупреждения,
  включая устаревшие Python API; не маскировать проблемы пропусками.
- Повторно проверить Python и Go advisories после согласованного обновления locks.
  Найденный секретоподобный текст в пользовательском audit ledger классифицировать
  по установленной процедуре и безопасно заретушировать, если это исторический
  пример, а не секрет. После `detect-secrets`/pre-commit повторно stage
  `.secrets.baseline` согласно `AGENTS.md`.
- Согласовать Go/Rust toolchain в CI, performance/test containers и канонической
  WASM-сборке. Проверить PyJWT/Go fixes и scanner versions, не удаляя обязательные
  SAST/security gates ради зелёного статуса.
- Целево проверить интегрированные auth/MFA, lifespan/schema drift, chat,
  attachments/storage, login/reset и role paths. Регрессионный тест должен дать
  воспроизводимый RED перед исправлением и GREEN после него.
- Security/auth/data-review включает как минимум: клиент не может подделать
  серверное `new_message` через WebSocket; удаление участника группы прекращает
  его активную доставку во всех соединениях этой группы и не допускает повторный
  join; смена MFA epoch отзывает связанные sibling/WS sessions в корректном
  порядке относительно commit. При email MFA enablement сохранить текущий
  подтверждённый step-up session, но отозвать siblings; при смене email отозвать
  все затронутые сессии. События отзыва публиковать после commit; БД остаётся
  авторитетной при временной ошибке публикации.
- Провести независимый security review production auth/session/data изменений.

**Приёмка блока:** все известные немутационные падения актуального SHA имеют
причину и исправление либо документированный внешний блокер; локальные целевые
проверки проходят; нет неизвестного security/auth/data failure. Полный canonical CI
остаётся отдельным evidence gate.

### Блок 2. Мигрировать и удалить устаревшую документацию

Сначала собрать точный tracked inventory для каждого кандидата на удаление:
путь, Git blob/hash, причина, решение по содержимому и целевая ADR/runbook/plan/кодовая
ссылка. Предварительно найдено 112 файлов в `docs/audits/archive/` и 8 файлов в
`docs/superpowers/plans/archive/` (около 3,8 MiB суммарно); пересчитать по Git перед
изменениями. Зафиксировать rescue SHA со всем набором, создать Git bundle вне
репозитория и проверить его чтением/restore нескольких выбранных файлов во
временный каталог. Записать bundle path, hash, restore command и sample evidence в
канонический индекс/инструкцию; bundle не должен содержать `.env`, секреты или
пользовательские runtime данные.

До удаления перенести и разрешить следующее:

- **O1–O8, CI evidence/operability:** O1 фиксирует job durations и необходимые
  timing data; O2 — доверенную source history/fingerprint, защиту от повторного
  использования чужих artifacts; O3 — setup/cache/protected-release условия;
  O4 — branch contexts и review requirements; O5 — классификацию и ограниченные
  retry semantics; O6 — каноническую связь check, artifact и owner; O7 — популяцию,
  окно измерения, p50/p95 и critical path; O8 — девять preflight lanes до candidate
  или push без конкурентной мутации общих install-каталогов. Для согласованных O1–O8
  получить три сопоставимых полных зелёных прогона и сформировать отчёт по одним
  и тем же определениям популяции, SHA, run/attempt, p50/p95, overlap/resource cap
  и critical path. Не выдавать старые числа за новую baseline.
  Подробные критерии и актуальные пробелы O2 находятся в ADR-039, а O3/O5/O7 —
  в [runbook каталога CI](../../testing/ci-check-catalog-runbook.md); наличие
  инструмента или unit-теста само по себе не закрывает end-to-end evidence.
- **MIG-PASS-01:** сохранить точное read-only preflight
  `python -m app.cli migrate-passwords assert-none`. Exit 0 только если нет
  активных bcrypt credentials; DB/identity/connectivity ошибка — fail closed, без
  skip/pass. Запускать в точном digest-pinned image с secret-backed DB identity.
  Зафиксировать CI/deployed catalog coverage и evidence; не подменять доступ к БД
  локальной проверкой. Текущий CI `DB Migration Gate (Postgres)` покрывает запуск
  команды внутри image по SHA-256 ID на disposable PostgreSQL и ожидаемые clean /
  fail-closed состояния. Это не закрывает требование secret-backed DB identity и
  deployed evidence; acceptance остаётся открытым до такого отдельного proof.
- **Chromatic:** оставить применимую инструкцию для
  `CHROMATIC_PROJECT_TOKEN`, `CHROMATIC_ENABLED=true`, collect-only/report-only
  режима, шести обоснованно исключённых нестабильных stories, проверки dashboard и
  review первого baseline. Не включать blocking diff gate до принятия baseline и
  пользовательского review. Не сохранять machine-local memory paths.
- **Admin visual smoke:** сохранить исполняемую команду/предусловия, роли,
  маршруты, artifacts и ограничение GitHub: schedule/manual workflow должен быть
  доступен из default branch для ожидаемой активации. Smoke считается реальным
  только если проверены admin страницы после login, а не login redirect; не
  наследовать устаревшие ссылки на PR/wave и выводы старого snapshot.
- **BE-02 / ADR-036:** read-only catalog preflight должен покрывать DDL-фазы,
  предусмотренные ADR-036 (включая phase 1/3/4), и выбирать одну общую миграционную
  логику. Проверить его на непустых deployed Docker и kind БД; сохранить candidate
  catalog, upgrade, rollback/downgrade и lock/statement budget evidence. Source ORM
  inventory не доказывает deployed PostgreSQL catalog.
- **RUST-P3-03:** проверить существующий base64 export path и parity WASM source /
  artifact на каноническом builder, связав evidence с exact final SHA. Не
  реализовывать уже имеющийся экспорт повторно и не утверждать parity по локальному
  артефакту с другого SHA.
- **Audit ledger:** проверить все 63 ID платформенного аудита на актуальном
  состоянии. Для каждого сохранить ID, final classification (актуален, закрыт с
  evidence, заменён согласованным решением либо только исторический), краткое
  основание, SHA/run/artifact и следующий владелец/шаг, если он открыт. Особо
  проверить MIG-PASS-01, BE-02 и RUST-P3-03. Удалить `AUDIT_PLATFORM_FULL.md`
  только после переноса ledger и проверки всех IDs; текущие статусы не наследовать
  из старых снимков.
- **Сверка требований Messenger W208–W211 завершена:** живые критерии групп,
  авторизации/cache/WS, персонального unread, reply и group notifications уже
  перенесены в Block 4. Пересылка сообщения также остаётся live-критерием, чтобы
  подтвердить отсутствие утечки исходного чата. W210/W211 закрывали часть старых
  дефектов, но их live-результаты относятся к прежним SHA; текущая API/WS-группа
  требует нового доказательства. «Seen by N» реализован, однако отсутствует в ТЗ
  и не является MVP gate; W209 auto-delete при составе <3 и отдельные roster WS
  frames также не добавлять без изменения scope. FAB/date separators оценивать в
  общем visual review, не создавать отдельные продуктовые gates. После переноса
  rationale классифицировать W210/W211 как исторические документы без текущей
  роли и решить их хранение вместе с прочей документацией вне archive.
- Пересмотреть `MVP_APPROVED_PLAN.md` и другие документы вне archive: применимые
  решения перенести сюда, в ADR или runbooks; удалить документ, если после миграции
  у него нет самостоятельной долговечной роли.
- Найти и заменить literal citations на удаляемые `AUDIT_WAVE*`, старые handoff и
  абсолютные пользовательские пути в workflows, коде, тестах, индексах и
  инструкциях. Оставлять лишь короткое rationale, которое нужно поддерживать;
  переносить долговечные шаги в ADR/runbook, не переписывать старые отчёты целиком.
- Обновить `docs/README.md`, `docs/audits/INDEX.md`, AGENTS index reference и
  документационную политику: перечислить текущие документы, retention/rescue
  policy, bundle restore instructions. Удалить старое обещание держать все отчёты
  в archive и устаревший allowlist 12 исторических broken links.
- Удалить архивные каталоги отдельными логическими коммитами после проверки
  dangling links. Оставить тесты поведения link checker, строгую проверку всех
  оставшихся документов и оба режима checker (`--include-archives` включительно,
  если режим сохраняется).

**Приёмка блока:** полезные уникальные требования имеют tracked-адрес; все 63 audit
ID проверены; rescue bundle восстанавливает sample files; ссылки на удалённые
файлы отсутствуют; default и include-archives link checker проходят; удаление не
меняет Git history и не захватывает пользовательские данные.

### Блок 3. Безопасный и воспроизводимый live-стенд

- Запускать тестируемый SHA в отдельном worktree и уникальном Compose project с
  явно принадлежащими этому запуску конфигурациями, сетями, контейнерами и
  синтетическими пользователями. Секреты/ключи VAPID и тестовые credentials
  генерировать для прогона; не читать и не перезаписывать чужой `.env`.
- Разделить CLI-операции: `status` только читает и ничего не генерирует; `stop`
  останавливает текущий стенд и сохраняет данные; `teardown` удаляет только
  проверенные ресурсы с run-owner labels/manifest. Перед запуском проверить порты;
  чужие процессы не останавливать. Compose и kind со взаимно конфликтующими
  портами запускать последовательно.
- Compose project имеет случайный run-id `ue-live-<16 hex>`; `.secrets/live-stand.json`
  связывает его с путями репозитория/worktree и HMAC-подписывается ключом в
  untracked Git common directory. Отсутствующий, повреждённый или чужой marker
  закрывает операции. Файл lifecycle lock сериализует `up`, `seed`, `stop` и
  `teardown`; `status` не создаёт и не меняет файлы. Port preflight проверяет
  wildcard bind для Caddy 80/443 и loopback для Mailpit 18025. Ref сначала
  разрешается и проверяется на live overlay — до остановки текущего стенда и
  переключения worktree. `down` — data-preserving alias для
  `stop`; `teardown` удаляет только resources подписанного project и сохраняет
  worktree, `.env*`, `.secrets` и evidence.
- Проверить в Docker readiness и рабочий ответ backend, SSR/Caddy, gateway, gRPC,
  WebSocket hub, NATS, Redis, S3/SeaweedFS и Mailpit; не считать container
  `running` достаточным readiness.
- На desktop/mobile запустить существующие реальные auth, role, login, MFA/TOTP,
  email OTP через Mailpit и password reset/reuse flows. Проверить безопасные
  redirects и отказ доступа student/teacher/admin по реальным API/данным.
- Завершить idempotent RU/EN demo seed на синтетических ролях: news, events,
  расписание, карта, личные/групповые чаты, stories, текущий Activity и пустые/
  частично заполненные состояния. Seed должен подтверждать владельца стенда,
  повторный запуск не умножает данные и режим явно opt-in.
- Повторить запуск после `stop`; доказать воспроизводимость и сохранение данных.
  Исправить обнаруженные дефекты regression test + evidence.

**Приёмка блока:** чистый запуск → полный readiness → idempotent seed → существующие
live specs проходит дважды; stop/start сохраняет данные; status не меняет состояние;
teardown проверяет ownership; пользовательские тома и конфигурации не затронуты.

### Блок 4. Продуктовая приёмка и исполняемый live E2E

Построить traceability matrix: каждый применимый пункт ТЗ ссылается на сценарий,
результат и evidence; явно объяснить ручную проверку для свойства, которое нельзя
автоматически проверить. Проверять RU/EN при ширинах 360, 390, 768, 1024 и 1440 px.

- **Auth/MFA:** регистрация, login, TOTP, email OTP из Mailpit, recovery, reset и
  token reuse, safe redirect, cooldown/TTL/attempt limits, правильные 401/429,
  sibling/session revocation.
- **Messenger:** два независимых browser contexts и реальный WS; DM/groups,
  ordering/deduplication, reconnect, reply/edit/delete/forward/reactions/
  attachments/unread. Для групп проверить min 3 / max 100 участников при создании;
  разрешения add/rename для участника и remove только владельцем или самим собой;
  403 для постороннего до раскрытия типа чата; отказ групповых операций для DM;
  после изменения membership старый WS/cache не сохраняет доступ. Прочтение
  сообщений участником A не сбрасывает unread участника B. Group notification
  содержит имя группы и автора. Quoted author получает ровно один `chat.reply`,
  без дополнительного общего `chat.message`. Проверить права на attachment.
  Mutations идут через backend, arbitrary client event payload не становится
  trusted event.
- **Profile/settings:** просмотр/редактирование профиля, avatar, validation и
  rollback, persisted state после reload, все действующие разделы settings.
- **News/events/map:** сохранение scroll, back/forward, центрирование tabs,
  wheel/touch/pinch isolation и отсутствие page scroll jumps.
- **Home/stories/activity:** пустые состояния, stories открываются по avatar,
  keyboard/swipe, пауза в hidden state, memory plateau; только текущие
  Activity heatmap/trends/grades/comparison, без новых учебных целей/attendance.
- **Notifications:** все пять текущих топиков (news, schedule changes, events,
  messages, system updates); in-app и реальный Chromium Web Push через локальный
  VAPID, dedup/unread, group-and-sender context, single `chat.reply` instead of a
  duplicate generic message notification, quiet hours, opt-out; разрешение
  браузера запрашивается после явного пользовательского действия.
- **Admin:** действующие admin pages работают; student/teacher получают отказ на
  UI/API, а не только скрытые ссылки.
- **SSR/PWA/i18n:** нет hydration mismatch, сырых localization keys; корректные
  404/500, offline, service-worker update без stale bundle.
- **Security:** CSRF, IDOR, open redirect, XSS, upload limits/rate limits,
  права на attachments и groups. Проверить как unauthorized, так и cross-user
  cases.
- **Mobile/a11y:** focus trap, Escape, scroll lock, быстрые тапы, hit-target
  geometry, keyboard, 200% zoom, reduced motion и отсутствие serious/critical axe
  findings.

Перенести существующие, но неисполняемые realtime/group/messenger-a11y specs в
действующий набор. Mocks допустимы для изолированного UI; доставка сообщений,
авторизацию и интеграции подтверждать на live stack. Добавить `live-e2e` workflow:
smoke на PR, полный nightly и ручной запуск. Учесть GitHub default-branch
требование для schedule/workflow_dispatch; синхронно обновить CI catalog и
contract tests. После трёх последовательных успешных PR smoke, проверки
сопоставимости и бюджета ресурсов закрепить smoke как required check. Любой
failure исправлять, не маскировать ретраями/skip.

**Приёмка блока:** traceability matrix заполнена; browser сценарии проходят в
указанной матрице; известные несценарные/manual checks обоснованы; PR/nightly/manual
лейны реально запускают нужные test groups с корректными artifact/provenance.

### Блок 5. Визуальная и performance-приёмка

- Сделать пакеты скриншотов текущих экранов RU/EN, light/dark, desktop/mobile.
  Review проводится небольшими наборами before/after. Принципы: матовый
  минимализм, ясная иерархия, отступы и design tokens; пустые состояния; только
  функциональные микроанимации. После пользовательского утверждения обновлять
  Linux visual baselines и фиксировать связь baseline с SHA.
- Использовать официальный Playwright container, версия которого совпадает с
  проектной Playwright dependency. Linux baseline является каноническим;
  Windows-only snapshot заменять после проверки соответствующего Linux output.
- Измерить и сохранить воспроизводимый protocol/config и evidence:
  navbar CLS < 0.1; при zoom карты отсутствуют long tasks ≥ 50 ms; INP ≤ 200 ms
  при CPU 4× и Slow 4G; Lighthouse CI score ≥ 0.95; main JavaScript < 500 KB.
- Выполнить 20 последовательных циклов открытия/закрытия stories и подтвердить
  plateau использования памяти; проверить reduced motion и отсутствие serious /
  critical axe findings на принятых экранах.
- Проверить уже существующие Activity heatmap, trends, grades и comparison; не
  вводить новые предметные модели/функции сверх ТЗ.

**Приёмка блока:** пользователь утвердил конкретные комплекты и baselines; каждый
перфоманс-тезис имеет измерение, конфигурацию, браузер/железо/commit и артефакт;
несоответствия исправлены и перемерены.

### Блок 6. Закрыть mutation debt и quality contract

- Получить свежий canonical inventory для exact source SHA. Старые значения 5 511
  frontend и 250 backend — только историческая точка отсчёта. Проверять
  population, shard completeness, source fingerprint, run/attempt и владельца
  каждого отчёта.
- Закрывать сначала backend/frontend auth, security и data; затем messenger/
  realtime и очереди по новому inventory. Поведенческий survivor требует теста;
  equivalent code — упрощения; timeout/runtime/no-coverage — устранения причины.
  Focused Stryker/mutmut даёт локальную обратную связь; обязательный допуск выдаёт
  canonical process.
- Сохранить 100% применимой line/statement/branch/function coverage и 100%
  viable mutation score для mutmut/Stryker. Метрика вне supported population
  обозначается как N/A только по текущему quality contract; не превращать N/A в
  ноль или зелёное неподтверждённое число.
- Сохранить ADR-040 mutation policy и запреты на исключения, quarantine,
  timeout-инфляцию, выключение Stryker и ручной статус `Killed`. Ошибку исправлять,
  а не менять допуск.
- Закрыть strict typing тестовых фикстур, zero-warning build, Go race/lint,
  Rust coverage/deny/fuzz по контракту, knip и deptry. Проверить WASM source /
  artifact parity на каноническом builder.
- После closure получить три сопоставимых полных зелёных прогона с общей
  population/SHA/run/attempt; опубликовать O1–O8 timing/critical-path report и
  стоимость/узкие места. Не вычитать предполагаемые mutants и не переносить
  доказательства между SHA.
- O9 повторно не реализовывать: проверить, что принятый механизм ADR-045
  (bounded progress diagnostic и существующие job ceilings) соответствует
  текущим CI catalog/contracts.

**Приёмка блока:** canonical evidence для всех applicable quality metrics и
mutation gates полностью зелёное; три повторяемых полных прогона сопоставимы;
security scans и действующие advisories рассмотрены; нет необъяснённых skip,
exclusion или stale evidence.

### Блок 7. Удалить доказанно устаревший код и оснастку

Выполнять небольшими изолированными пакетами. Для удаления зафиксировать
потребителей, причину и релевантный regression/contract test. Результаты
инструментов — кандидаты, не разрешение удалить.

- Проверить достижимость Python/Go/Rust от runtime entrypoints и API по frontend,
  Go, интеграциям, SDK и документации. Не считать endpoint мёртвым только потому,
  что на него нет прямого frontend вызова.
- Пересмотреть assets, design tokens, i18n keys, stories, mocks, generated
  files, exports/barrels и повторяющиеся test helpers; удалить только доказанный
  duplicate/dead content с сохранением покрытия и behavior.
- Сверить env/settings/Compose/Helm/docs, утвердить полезные invariants как
  executable checks. Пересмотреть `.agents/skills`: удалить дубли/неприменяемые,
  сохранить нужные `AGENTS.md`-применения и используемые профили; developer
  harness/hooks/subagents сохранить.
- Объединять тестовые дубли только при сохранении сценариев, coverage и mutation
  результата. Wave-комментарии убирать малыми блоками; косметические изменения не
  смешивать с behavior fixes. Историю Alembic миграций не squash/rewrite.
- Для каждого workflow/quality gate оценить назначение, стоимость, владельца,
  историю реальных находок и дубли. Отсутствие недавних срабатываний само по себе
  не причина удалять защиту. Вести компактный registry там, где это поддерживает
  самостоятельное принятие решений.
- Проверить concurrency кандидаты: module-level executors, loop-keyed caches,
  push semaphore и пользовательский status lifecycle.

**Приёмка блока:** каждое удаление имеет проверенное отсутствие потребителей и
успешные затронутые checks; quality/security защиты сохранены; migrations и harness
сохранены; статусное обоснование оставшегося спорного груза доступно.

### Блок 8. Docker, storage, observability и disaster recovery

- Проверить поддерживаемые Compose-комбинации: base/full и overlays, Core, test;
  выполнить clean startup, health/readiness, корректный stop, повторный запуск и
  замер RAM/CPU. Пользовательские volumes и `.env` не удалять/переписывать.
- Проверить реальные S3 Put/Head/Get/Delete, presigned URL, private access,
  upload/download и object integrity. Завершить SeaweedFS metrics и Grafana
  dashboards/alerts; подтвердить Prometheus targets, logs и traces. Не дублировать
  уже существующие datasource configs.
- Проверить оставшийся `mc` backup path и перевести действующий путь на
  поддерживаемый pinned S3 client. Реализовать restore CLI/runbook с manifest и
  checksums, явной целью; credentials принимать через environment/secret files,
  не argv/stdout/log.
- Восстанавливать по умолчанию в отдельную БД и отдельное S3 пространство.
  Проверить согласованность относящихся друг к другу DB/S3 snapshot, object
  versions, manifest/checksums и восстановленного состояния; два независимых
  архива не считать автоматически одной точкой восстановления. Прогнать backup,
  restore, validation и rollback без перезаписи пользовательских данных.
- Усовершенствовать BE-02 preflight согласно блоку 2 и ADR-036. На непустых
  deployed Docker/kind databases проверить DDL upgrade/rollback, catalog state,
  idempotency и lock budgets.
- Измерить RPO ≤24h и RTO ≤30m на документированном demo dataset. Указать размер,
  число объектов, инструменты/ресурсы и какие компоненты входят в таймер.

**Приёмка блока:** Compose-наборы стабильно поднимаются; S3 целостность и private
access доказаны; observability показывает реальные targets; end-to-end backup/restore
в отдельную среду доказал согласованность данных, RPO/RTO и сохранность исходной
среды.

### Блок 9. Envoy Gateway / Gateway API и kind-приёмка

- Создать ADR перехода с nginx-specific Ingress на Envoy Gateway + Kubernetes
  Gateway API для нового MVP стенда. Сохранить существующие frontend/API/JWKS/WS
  маршруты, приоритеты и Go gateway как владельца проверки identity и
  `X-Internal-Signature` HMAC assertion; не дублировать authentication в Envoy.
- Перенести HTTP→HTTPS redirect, TLS, upload limits, rate/connection limits и
  NetworkPolicies. Проверить, что удаление nginx annotations не убирает защиту.
  Параметризовать Helm values/schema; обновить raw manifests, docs и allowlist
  deployment wrapper. Все `${...}` raw Kubernetes variables по-прежнему проходят
  только через `scripts/apply_raw_k8s.sh`.
- Для kind использовать cert-manager и локальную CA; добавить contract tests
  для render/schema/routes/policies. Создать run-owned kind tooling для prepare,
  local registry, deploy, smoke, chaos/failure, rollback, stop/teardown. Все
  teardown операции проверяют owner/cluster identity.
- Поднять cluster/registry до сборки; собрать, просканировать и подписать образы;
  разворачивать immutable image digests, не mutable tags. Проверить TLS,
  HTTP/WebSocket/gRPC маршруты, Kyverno, ExternalSecrets refresh, metrics/HPA,
  restart/failure recovery, data-preserving rollback и storage.

**Приёмка блока:** kind развёрнут на известных immutable image digests; ingress-nginx
не требуется; маршруты/TLS/policies/security проходят контрактные и живые проверки;
chaos/recovery/rollback сохраняют данные; runner не удалил чужие cluster resources.

### Блок 10. Финальный аудит, ordinary merge и v1.0.0

- Перепроверить все 63 audit IDs по блоку 2 на final candidate. Для каждого
  `CLOSED`/`DECLINED` должно быть актуальное основание/evidence. Особо закрыть
  BE-02 в согласованной Docker/kind области и подтвердить уже реализованный
  RUST-P3-03 base64 path + canonical WASM parity; повторно не реализовывать экспорт.
- Провести независимый final code/security review и получить пользовательское
  утверждение обязательных визуальных пакетов. Заморозить release candidate:
  application code, dependencies, config и документы должны соответствовать
  одному SHA.
- Создать/обновить PR, дождаться обязательных checks и перенести результат в
  `main` обычным merge. Admin bypass, изменение защиты ветки и force-push не
  использовать. После merge получить свежее успешное canonical evidence именно
  для resulting `main` SHA.
- Main-only producer должен выпустить ровно шесть images в GHCR: backend,
  frontend, gateway, ws-hub, file-processor и caddy. Проверить Trivy, SBOM,
  signatures/attestations, provenance, image digests и frontend WASM parity.
- Установить в kind именно опубликованные digest и повторить релизную приёмку:
  TLS, live workflows, role/security checks, backup/restore, failure recovery и
  data-preserving rollback. Сверить фактический deployed digest с GHCR evidence.
- Опубликовать `v1.0.0` с release notes, exact image digests, SHA-bound evidence,
  ограничениями MVP и repeatable delivery instructions. Машинный финальный отчёт
  приложить к release/artifacts; после сертификации не менять source лишь ради
  записи run numbers в Markdown.

**Приёмка блока:** main SHA, evidence, шесть GHCR digests, их kind deploy, audit
ledger и release report связаны и проверены. Только тогда закрыть Codex goal.

## Изменяемые интерфейсы

Изменять публичные интерфейсы только при доказанной необходимости; передавать
ownership вместе с проверками:

| Интерфейс | Требуемое поведение |
| --- | --- |
| Live stand CLI | Read-only `status`; data-preserving `stop`; owner-checked destructive `teardown`. |
| Demo seed | Явный opt-in, идемпотентные RU/EN synthetic users/content, verified run ownership. |
| Backup/restore CLI | Manifest/checksum validation, явная restore target, безопасная изолированная среда по умолчанию. |
| BE-02 | Read-only catalog preflight, DDL phase selection, единая логика загрузки миграций. |
| Helm/Kubernetes | Gateway API resources, параметризованные values/schema, сохранение TLS, routing и security policy. |
| CI | Catalog/contracts синхронны; PR live smoke и полный nightly/manual E2E. |
| Release evidence | Source SHA, workflow run/attempt, inventory provenance, immutable digests, signatures, SBOM, результаты приёмки и ограничения. |

## Финальный checklist

Goal закрывается только если все пункты подтверждены evidence:

- Каждое применимое требование ТЗ трассируется к приёмке; продуктовые и
  визуальные сценарии согласованы и выполнены.
- Все applicable coverage dimensions и viable mutation score составляют 100%;
  gates, security scans и обязательные CI checks зелёные; нет необъяснённых
  failures/skips/exclusions.
- Открытый ledger закрыт актуальным evidence или точно согласованным ограничением.
- Нагрузочный профиль WS, память/reconnect correctness, S3/backup/restore/RPO/RTO,
  BE-02, Gateway API/kind и rollback проверены на реальной целевой конфигурации.
- Три сопоставимых полных зелёных CI наблюдения и release evidence привязаны к
  точным SHA/run/attempt/population.
- Шесть GHCR digests и их signatures/SBOM/provenance проверены и развернуты в
  kind; релиз `v1.0.0` содержит полный машинный отчёт и ограничения.
- Рабочее дерево чистое, актуальные документы и реализация не противоречат друг
  другу; архивный rescue bundle восстанавливаем.

## Продолжение сессии

Сначала прочитать корневой и затронутые доменные `AGENTS.md`, этот файл, `STATUS.md`
и ТЗ. Затем проверить `git status --short --branch`, HEAD/remotes/worktrees, CI и
evidence для exact SHA. Не переиспользовать старые worktree/WIP patches, CI или
локальные результаты как текущие. Продолжить первый незавершённый блок в STATUS.
Сохранять `.env`, volumes, backups, user data, migration history и Git history;
при новых security или destructive-action границах фиксировать точный факт и
продолжать всю независимую безопасную работу.
