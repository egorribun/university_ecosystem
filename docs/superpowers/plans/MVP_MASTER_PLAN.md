# University Ecosystem: полный цикл приёмки и выпуска MVP v1.0.0

Редакция 6 от 2026-10-10 (Europe/Istanbul). Единственный действующий план,
объединяющий прежний мастер-план и решение коммита
`60a886529c6e89176e2d53395268ca6279805cb4` с уточнениями владельца в этой беседе.
Основание качества — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).
[ТЗ MVP](University_Ecosystem_MVP.md) задаёт продукт, [STATUS.md](STATUS.md) —
короткий оперативный срез. Отдельный план выпуска объединён с этим
документом; новую конкурирующую дорожную карту не создавать.

## Цель и принятые решения

**Цель v1.0.0:** выпустить принятый продукт по ТЗ: живые сценарии, утверждённый
визуал, отсутствие открытых P0/P1 по безопасности, успешные обязательные проверки
и обычный merge в `main`; опубликовать шесть образов существующим main-only
producer и релиз с ограничениями. Полная сертификация этих образов в kind,
RPO/RTO, глобальный mutation score и три сопоставимых полных CI-прогона — `v1.1`.

- Работа строго на `egorribun`, один checkout и PR #1306. Root проверяет
  интеграцию и выполняет stage/commit/push; максимум три GPT-6 Luna Max пишут в
  непересекающихся областях. Новые ветки/worktree не создавать. Обычный merge;
  admin bypass, force-push и общие изменения branch protection не разрешены.
  Исключение владельца от 2026-10-09: после готового reviewed CI diff и проверок
  можно убрать только 14 Q1/Q4 contexts из ruleset `8335285`, перечисленных в
  [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md#authorized-required-context-removals); остальные правила сохранить.
  Последующим явным ответом владелец разрешил ещё ровно один context,
  `Security Audit / Semgrep SAST`, после reviewed scanner de-dup diff и проверок;
  CodeQL остаётся blocking, Semgrep — в pre-commit, остальные76 contexts сохранить.
- Уже реализованные исправления, тесты и оснастка сохраняются. Начатые направления
  доводятся до **ограниченной контрольной точки**, указанной ниже, без восстановления
  старого требования полной сертификации до MVP. Наличие исходника или mock-теста
  не является доказательством живой приёмки.
- ГУУ остаётся брендом внутреннего демо. Данные и аккаунты синтетические, роли —
  student/teacher/admin. Согласие на публичное использование названия/логотипа и
  обработку данных реальных пользователей решается отдельно до такого использования.
- Не добавлять новую обязательную MFA, учебные цели/attendance, CDC, сущности
  помещений и вместимости, QR-приход или лимиты мест. Новая учебная модель —
  отдельный план после MVP. «Проверка аудитории при создании» относится к этой
  будущей модели и не является задачей текущего релиза.
- Продуктовая приёмка — на Core; full — отдельный smoke на замороженном релизном
  SHA. Использовать утверждённый Compose inventory, а не постоянное число сервисов
  из старого отчёта. Остановка сохраняет данные; удаление только после проверки
  владельца. Чужие env, тома, backups и процессы сохраняются.
- RU/EN, light/dark; обязательные ширины 390/768/1440 px. На 360/1024 px —
  дополнительные проверки меню, таблиц и найденных адаптивных дефектов. Физические
  устройства, внешние SMTP/push-провайдеры и field CWV вне текущей приёмки.
- Русский — ТЗ/план/статус, английский — технические ADR/runbooks/код.
  Git history, migrations, harness и приватный rescue bundle сохраняются.

## Переход качества: решение и фактический CI

- Tier 0 сохраняет 100% всех применимых coverage-метрик. До Q3 **все нынешние
  per-component floors из `quality/quality-contract.json` и текущий 100% patch
  coverage остаются машинно обязательными**; unsupported метрики не превращать
  в новые требования.
  Ratchet и 90% non-Tier-0 patch coverage ещё не внедрены. Если действующие floors
  блокируют MVP, отдельно согласовать включение Q3; не снижать их молча.
- Q1 обязателен до MVP: мутации исключаются из release gate и перестают запускаться
  как PR/main blocking lane; полные mutmut/Stryker остаются nightly/manual.
  Q1/Q4 source migration и разрешённое обновление protections внедрены.
  Каждый новый SHA требует свежих required-check results; текущий checkpoint и
  CI evidence находятся в [STATUS](STATUS.md). Main-push/release proof ещё открыты.
  Не работать ради global mutation score.
- Q4 также обязателен до MVP: Schemathesis, DAST, chaos, cross-browser E2E и kind
  переходят в scheduled/manual lanes; PR сохраняет lint/types/unit/contracts,
  API drift, coverage и необходимую security-проверку. Live Chromium smoke остаётся
  на PR. Проверить не только `needs`, но и results array, специальные assertions,
  triggers, catalog и release-required checks. Целевой бюджет PR — 15 минут;
  измерить wall time и critical path, не объявлять его выполненным заранее.
- Уточнение владельца 2026-10-09: полный Chromium из четырёх шардов и Lighthouse
  также переходят в scheduled/manual; PR сохраняет живой Chromium smoke.
  Полные сценарии/существующие assertions сохраняются в новых lanes.
  `Owned live acceptance (pull_request)` остаётся advisory/non-required:
  три последовательных успешных smoke и измерение ресурсов/бюджета являются
  обязательными предпосылками повышения; до них required не включать.
  Само выполнение предпосылок не расширяет разрешённую границу ruleset.
- Q2 (nightly mutation regression более 1 процентного пункта, dashboard) и Q3
  (coverage ratchet) — `v1.1`. Nightly сигналы могут оставаться красными на прежнем
  пороге до Q2; они не дают основания подменять результат или считать регрессию
  реализованной. Equivalent exclusions — только доказанные, с owner/evidence и
  сроком до 90 дней; quarantine и ручной `Killed` запрещены.
- Уже готовые security, signing, SBOM/provenance и WASM parity шаги image producer
  сохраняются. Отложена дополнительная сертификация/продвижение в kind, а не
  удаление работающей защиты или публикация произвольного набора образов.

## Шесть этапов до v1.0.0

| Этап | Работа и проверяемый результат | Детали старых блоков |
| --- | --- | --- |
| 1. Решение и документы | ADR-047, единый план, AGENTS/индексы/STATUS согласованы; ссылки проверены. Решение принято, консолидация завершается этим изменением. | 0, 2 |
| 2. Q1 и Q4 в CI | Удалить mutation-зависимости и специальные blocking assertions; перенести тяжёлые lanes; сохранить fail-closed оставшиеся gates, nightly/manual и release-source verification. Contracts и актуальный PR зелёные, бюджет измерен. | 1, 6 |
| 3. Core и продукт | Traceability ТЗ 2–13; реальный Chromium, mocked Firefox/WebKit; два последовательных прогона, stop/start и seed. Исправить schedule update conflicts и проверенные audit defects. | 3, 4 |
| 4. Визуал и performance | Утверждённые небольшие пакеты RU/EN, light/dark, desktop/mobile, Linux baselines; main JS <500 KB, Lighthouse ключевых страниц, stories 20 циклов, a11y/reduced motion. | 5 |
| 5. Security, ledger, данные | Независимый auth/session/data review, решение ADR-006 ordering; все 63 ID классифицированы, P0/P1 нет; один согласованный DB/S3 backup/restore в изолированную цель с чтением объекта по DB reference. | 1, 2, 8 |
| 6. Выпуск | Frozen RC, full smoke, required PR checks, обычный merge, свежие main-push checks, ровно шесть GHCR images существующим producer, tag/release notes и SHA-bound evidence. | 10 |

Порядок допуска: 1 → 2 → 3–5 → 6. Подготовка и исправления этапов 3–5
идут параллельно с этапом 2; ждать всей CI-очереди для независимой работы не нужно.
Тяжёлый локальный процесс один: RAM до запуска ≤75% и free ≥8 GiB; runtime guard
85%/4 GiB. Ненужные owned Docker-ресурсы удалять, global prune не применять.
Отдельное разрешение владельца от2026-10-09 действует только для одиночных
Linux screenshot-прогонов: startup≤80%/free≥6 GiB при browser cap1 GiB/2 CPU;
runtime guard85%/4 GiB неизменен. Build, full E2E и Lighthouse сохраняют75%/8 GiB.
Каждая задача субагента — максимум 30 минут до контрольной точки с чётким
критерием результата. Длительные CI/live-процессы контролируются отдельно;
исчерпание бюджета не превращает failure/NOT RUN в PASS и не снимает требование.
Новая quality/evidence-оснастка до MVP не создаётся, кроме необходимого Q1/Q4.
Использовать готовые collectors, workflows и проверяемые команды.

## Сохранённые начатые направления и границы остановки

| Направление | Что уже есть | Ограниченный результат до MVP; что остаётся v1.1 |
| --- | --- | --- |
| Planner/checker | Cost cache, TypeScript checker и provenance checks интегрированы; synthetic512/128 parity, local tests; global evidence нет. | Сохранить исправления и контракты, включить их в работающие nightly/manual lanes. Не запускать полные mutation очереди ради score. Q2/global closure — v1.1. |
| Live/UI/realtime | Owner-checked Core/full CLI, seed, profile fix, Dashboard hydration и browser-cache override; hosted smoke18/2 на старом SHA. | Свежие Core product scenarios и полная traceability; delivery/group push/visual ещё открыты. Старый smoke не закрывает новый SHA. |
| Backup/restore | Manifest-aware CLI/runbook и paired snapshot; прошлый target restore не начинался. | Завершить один безопасный app-compatible restore с DB/S3 связностью. RPO/RTO и длительная сертификация — v1.1; корректность согласованной копии обязательна сейчас. |
| Envoy/kind | Пinned controllers/CA и run-owned helper; prerequisite smoke пройден, приложение не развёрнуто. | Принятую prerequisite-стадию сохранить; незавершённые chart/routes/render вопросы записать с владельцем, без нового cluster deployment до MVP. App deployment/TLS/chaos/rollback в kind — v1.1. |
| BE-02/MIG-PASS | Preflight CLI и offline/disposable-Postgres contracts. | Сохранить CI миграций и готовые проверки. Непустые deployed DB upgrade/rollback/lock budgets — v1.1. |
| Code/quality cleanup | Частичные catalog, planner, WS lifecycle/perf и consolidation fixes. | Сохранить принятые исправления; закончить текущий маленький пакет без массовой ревизии. Runtime reachability/API/assets/i18n/helpers/invariants/concurrency и gate cost review — v1.1. |
| Image producer | Main-only producer шести images, security/signing/SBOM/provenance; source-bound release consumer. | Выполнить готовую публикацию с проверкой точного main SHA, run/attempt и manifest/digests. Не переписывать producer ради снятия готовых шагов. Полная kind сертификация — v1.1. |

## Кратчайший путь к MVP и организация работы

1. Сначала Q1, затем Q4 отдельными проверяемыми пакетами; одновременно подготовить
   продуктовые сценарии и точечные schedule/search fixes. Один агент владеет CI,
   второй — одним backend-доменом, третий — frontend/live acceptance. Root
   интегрирует, проверяет независимым ревью и управляет ресурсами. Назначения
   меняются по critical path, а не ради постоянной загрузки всех машин.
2. Перед каждым пакетом определить RED/ожидаемое поведение, конкретные файлы,
   необходимые checks и результат за 30 минут. Доказанные defects чинить;
   hypotheses сначала проверять. Не рефакторить домен целиком ради одного дефекта.
3. Проверять затронутые области и required pre-push preflight. Полные coverage,
   cross-browser и security-наборы выполнять в предусмотренной lane; не повторять
   одинаковые прогон/установку без нового изменения или найденной ошибки.
4. На чистом SHA поднять один Core-стенд; совместить продуктовую, visual,
   Lighthouse и restore приёмку, сохранив раздельные результаты. Пока source
   заморожен, остальные агенты проводят review или готовят патчи приватно;
   исходники работающего прогона не изменяют. Стенд останавливать при resource guard.
5. Применить найденные исправления одним согласованным пакетом. Повторить
   затронутые сценарии, затем получить два успешных последовательных продуктовых
   прогона на неизменном RC. Визуальное утверждение запрашивать готовыми пакетами,
   не откладывать все экраны до конца.
6. На frozen RC выполнить один full smoke, обычный merge, main checks и готовую
   публикацию. Не ждать трёх comparable полных CI-прогонов, глобальных мутаций,
   kind deployment или RPO/RTO, отнесённых к v1.1.

Для release каждого обязательного критерия нужен результат; экономия достигается
сокращением дублей, scope и ожидания, а не фиктивными PASS или потерей сценариев.
Срок оценить после Q1/Q4 и первого текущего Core-прогона по реальным длительностям;
число коммитов и прежние оценки не являются прогнозом.

## Evidence и сохранность результатов

Routine local check: SHA, команда, результат и ограничения. Live, coverage,
mutation, backup, kind, baseline и release evidence сохраняют необходимые
config/tool/population/run/attempt/artifact bindings существующими инструментами.
Нельзя смешивать PR head, synthetic merge, resulting main и старый snapshot.
Полный release evidence относится к main SHA и опубликованному manifest; evidence
PR не подменяет проверку main. Session logs не добавлять в индекс документации.
STATUS ≤150 строк: результаты, следующий шаг и конкретные blockers.

## Подробные блоки и их область применения

Блоки 0–10 ниже сохраняют уникальные сценарии и технические инварианты. Их область:
0–2 — контекст/security/документация; 3–4 — Core acceptance; 5 — сокращённая
визуальная приёмка; 6 — Q1/Q4 сейчас и quality backlog v1.1; 7 — v1.1 кроме
начатых малых исправлений; 8 — restore минимум сейчас, сертификация v1.1;
9 — начатая контрольная точка, полная kind acceptance v1.1; 10 — MVP выпуск.
Старые исторические evidence остаются фактами своего SHA, не текущим допуском.

### Блок 0. Goal и проверяемый рабочий контекст

- Подготовительная правка harness завершена в контрольной точке 2026-10-09:
  verifier изолирован от рабочей истории ошибок; per-file failures, shared lock,
  atomic state и fail-closed JSON/timeout сохранены; профили согласованы с одним
  checkout и runtime ограничен. Focused165 PASS, verifier28/28, inventory0,
  relevant preflight10/10 и независимый review CLEAR. Не внедрять повторно;
  новые failures проверять по текущему SHA. Наличие hooks не означает
  автоматической Codex-интеграции; границы запуска описаны в
  [AGENTS.md](../../../AGENTS.md), раздел 8.
- Сохранить один Codex goal без произвольного token budget. Его прежняя
  формулировка включала сертификацию kind; это этап v1.1, а критерии MVP теперь
  задаются этим планом. Не объявлять всю прежнюю сертификацию завершённой при
  выпуске продукта и не создавать конкурирующую цель.
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
- Иерархия источников: ТЗ определяет продукт; этот план и ADR-047 — решения,
  требования и порядок; STATUS — короткое оперативное состояние; ADR/runbooks — подробности
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
- Проверить новые pre-commit, Source/Test Inventory, quality inventory и
  link/spelling failures по конкретным шагам на текущем SHA. R02 inventory
  локально закрыт в контрольной точке 2026-10-09, исключение для orphan не
  добавлялось; сначала подтвердить hosted результат, не повторять принятый fix.
  Исправить новые дефекты и предупреждения, включая устаревшие Python API;
  не маскировать проблемы пропусками.
- Повторно проверить Python и Go advisories после согласованного обновления locks.
  Credential-shaped текст в исторических материалах не копировать в текущие
  документы или baseline. После `detect-secrets`/pre-commit повторно stage
  `.secrets.baseline` согласно `AGENTS.md`; Git history и приватный rescue bundle
  сохраняют исторические материалы по [retention policy](../../audits/INDEX.md#legacy-archive-cleanup-and-recovery).
- **SEC-03 / audit signing key:** в Git history семи revisions `security.py`
  обнаружен исторический `AUDIT_LOG_SECRET` HMAC signing-key default; его значение
  удалено из текущего отчёта. Пользователь подтвердил, что этот default применялся
  только в эфемерных CI/demo-средах, не в постоянных БД или развёртываниях; оснований
  для ротации постоянного production secret по этому факту нет. Production validator
  отвергает этот ключ даже как secondary key. Текущий runbook переоформляет
  `DataAccessLog`, но не умеет перестраивать `StoredEvent` chains. Пользовательская
  оценка не заменяет данные: если конкретная сохраняемая БД содержит подписи,
  перед любой migration необходимы protected consistent backup и read-only
  inventory. Для свежего MVP kind/demo использовать новый случайный ключ без
  переноса эфемерной БД.
  Если найдены другие старые подписи, до записи
  проверить их в изолированном пути, сохранить evidence/trust limitations и
  реализовать проверенную migration для обоих record types. Read-only source
  review установил два legacy HMAC payload формата `DataAccessLog`: основной
  writer `data_access.py` использует JSON-array без row ID, но с context и
  user-agent; `SecureAuditService` использует pipe-delimited payload с row ID, но
  без context/user-agent. Admin verifier знает только второй формат, а deploy
  re-sign sample не проверяет, что каждый non-null signature получил допустимый
  статус. Новые записи перевести на один versioned canonical format, а прежние
  форматы проверять отдельными exact verifiers; статус legacy verification должен
  показывать поля, не подтверждённые прежней подписью. Не переносить автоматически
  unversioned legacy signatures в новый формат: это выдало бы неподписанные
  прежним HMAC значения за аутентифицированные. Любая отдельная migration требует
  установленного ключа, точного inventory и fail-closed учёта каждой ненулевой
  подписи. `StoredEvent` содержит как hash-linked rows, так и nullable поля/rows без
  sequence, которые `app/core/events.py` пишет как outbox; сначала read-only
  inventory должен разделить эти формы. Для chain миграция атомарно покрывает все
  события aggregate по порядку и допускается только после проверки исходной цепи;
  массовый/частичный re-sign без инвентаря недопустим. Не возвращать старый ключ в
  serving config. Не предполагать отсутствие подписанных данных с иными ключами
  без read-only inventory сохраняемой БД.
- Согласовать Go/Rust toolchain в CI, performance/test containers и канонической
  WASM-сборке. Проверить PyJWT/Go fixes и scanner versions, не удаляя обязательные
  SAST/security gates ради зелёного статуса.
- Целево проверить интегрированные auth/MFA, lifespan/schema drift, chat,
  attachments/storage, login/reset и role paths. Регрессионный тест должен дать
  воспроизводимый RED перед исправлением и GREEN после него.
- Зафиксировать остаточный риск password-reset delivery: 45-минутная ссылка с
  bearer-токеном сериализуется в JSON payload файлового JetStream `TASK_QUEUE`,
  где `Limits` допускает хранение до 7 дней; fallback/error logs маскируют token,
  но tracked Compose не задаёт шифрование JetStream-at-rest, а фактическая
  настройка внешнего NATS deployment не проверена. MVP-приёмка ограничена
  синтетическими учётками и Mailpit. До любого production use выбрать и проверить
  scoped auth-task stream/credentials или шифрование payload и управляемый ключ.
  Не включать `AllowMsgTTL` в общую очередь как shortcut: настройка необратима,
  а `Nats-TTL: never` может обойти `MaxAge` ([TTL](https://docs.nats.io/learn/jetstream/message-ttl),
  [шифрование JetStream](https://docs.nats.io/learn/security/encryption)).
- Security/auth/data-review включает как минимум: клиент не может подделать
  серверное `new_message` через WebSocket; удаление участника группы прекращает
  его активную доставку во всех соединениях этой группы и не допускает повторный
  join; смена MFA epoch отзывает связанные sibling/WS sessions в корректном
  порядке относительно commit. При email MFA enablement сохранить текущий
  подтверждённый step-up session, но отозвать siblings; при смене email отозвать
  все затронутые сессии. Отзыв следует tombstone-first контракту
  [ADR-006](../../adr/ADR-006-websocket-auth-tickets.md):
  durable Redis tombstone записывается до commit, ошибка записи или commit
  вызывает rollback; ошибка Pub/Sub после tombstone не отменяет отзыв.
  Решение 2026-10-09 по поручению владельца «лучший вариант»: сохранить эту
  fail-closed границу, включая WS revoke до DB commit; прежнее требование
  post-commit отзыва заменено. При последующем rollback возможен консервативный
  logout siblings, tombstone не удалять для восстановления credential.
  Проверить route-level failure paths и сохранение текущей step-up session.
  Решение порядка само по себе не закрывает security приёмку.
- Провести независимый security review production auth/session/data изменений.

**Приёмка блока:** все известные немутационные падения актуального SHA имеют
причину и исправление либо документированный внешний блокер; локальные целевые
проверки проходят; нет неизвестного security/auth/data failure. Полный canonical CI
остаётся отдельным evidence gate.

### Блок 2. Мигрировать и удалить устаревшую документацию

**Завершённый checkpoint очистки:** к HEAD `cfbf5f6200619a800dff9ecf4533b909544d1efb`
каталоги `docs/audits/archive/` и `docs/superpowers/plans/archive/` уже удалены из
рабочего дерева; Git history не переписывалась. Value-free inventory на rescue SHA
`d0aad7c296facd79b3d41b037bc4160f5b3132be` содержит 120 путей; повторная read-only
сверка подтвердила все 120 blob IDs и размеров (3,981,581 bytes), а три уникальных
полезных требования имеют tracked destinations. Внешние bundle и inventory уже
существуют и задокументированы в [индексе аудита](../../audits/INDEX.md); новые
bundle/копии не создавать, каталоги не восстанавливать и bundle не распространять.

Пользователь подтвердил, что исторический signing-key default применялся только
в эфемерных CI/demo-средах; проверки persistent deployment или ротация ключа из
этого факта не требуются. Несовпадение legacy `DataAccessLog` writer/verifier и
неполная модель `StoredEvent` остаются требованиями к любому будущему переносу
подписанных данных, но не свидетельствуют об использовании этого ключа в
persistent storage. Полную Git history bundle и далее хранить частно и изолированно,
поскольку в исторических материалах есть credential-подобные строки. Архивная
очистка уже выполнена; не создавать новые копии и не восстанавливать архивы без
конкретной задачи восстановления.

**Credential checkpoint:** value-free inventory нашёл девять
Chromatic project-token-shaped упоминаний в трёх исторических отчётах.
Пользователь подтвердил reset токена;
GitHub metadata подтверждает обновление repository secret
`CHROMATIC_PROJECT_TOKEN` в `2026-09-30T10:08:36Z`. Секретное значение не читалось.
Seeded-admin пароль из исторического отчёта пользователь подтвердил как
использовавшийся только в одноразовой CI-базе. Admin smoke должен использовать
отдельный случайный пароль на каждый прогон, передавать его только нужным шагам и
не включать значение в логи или artifacts. Текущий Chromatic workflow намеренно
выключен billing gates и `skip: true`; пользователь не может оплачивать сервис,
поэтому не включать платную публикацию и не требовать workflow-запуска как проверки
ротации. Не выводить credential-shaped содержимое архивов или переносить его в
рабочую документацию. Rescue bundle — закрыто хранимый исторический артефакт;
держать вне repo, не синхронизировать и не публиковать.

Остались проверки требований и evidence; их выполнять без повторного удаления
архивов и без создания/распространения rescue bundle:

- **O1–O8, CI evidence/operability:** O1 фиксирует job durations и необходимые
  timing data; O2 — доверенную source history/fingerprint, защиту от повторного
  использования чужих artifacts; O3 — setup/cache/protected-release условия;
  O4 — branch contexts и review requirements; O5 — классификацию и ограниченные
  retry semantics; O6 — каноническую связь check, artifact и owner; O7 — популяцию,
  окно измерения, p50/p95 и critical path; O8 — девять preflight lanes до candidate
  или push без конкурентной мутации общих install-каталогов. Для согласованных O1–O8
  в v1.1 получить три сопоставимых полных зелёных прогона и сформировать отчёт по одним
  и тем же определениям популяции, SHA, run/attempt, p50/p95, overlap/resource cap
  и critical path. Не выдавать старые числа за новую baseline.
  Подробные критерии и актуальные пробелы O2 находятся в ADR-039, а O3/O5/O7 —
  в [runbook каталога CI](../../testing/ci-check-catalog-runbook.md); наличие
  инструмента или unit-теста само по себе не закрывает end-to-end evidence.
- **MIG-PASS-01 (deployed proof — v1.1):** сохранить точное read-only preflight
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
- **BE-02 / ADR-036 (deployed proof — v1.1):** read-only catalog preflight должен покрывать DDL-фазы,
  предусмотренные ADR-036 (включая phase 1/3/4), и выбирать одну общую миграционную
  логику. Проверить его на непустых deployed Docker и kind БД; сохранить candidate
  catalog, upgrade, rollback/downgrade и lock/statement budget evidence. Source ORM
  inventory не доказывает deployed PostgreSQL catalog.
- **RUST-P3-03:** проверить существующий base64 export path и parity WASM source /
  artifact на каноническом builder, связав evidence с exact final SHA. Не
  реализовывать уже имеющийся экспорт повторно и не утверждать parity по локальному
  артефакту с другого SHA.
- **Audit ledger:** [компактный реестр](../../audits/INDEX.md#findings-ledger) сохраняет
  все 63 ID платформенного аудита, aliases, основания и ссылки на текущие исходники.
  Проверить каждый ID на актуальном RC. Для каждого сохранить final classification (актуален, закрыт с
  evidence, заменён согласованным решением либо только исторический), краткое
  основание, SHA/run/artifact и следующий владелец/шаг, если он открыт. Для MVP
  допустим перенос некритичного пункта в v1.1 с владельцем; P0/P1 security не переносить. Особо
  проверить MIG-PASS-01, BE-02 и RUST-P3-03. Исторический полный отчёт удалён после
  сверки точного набора 63 ID и переноса требований; RC revalidation остаётся
  открытой. Текущие статусы не наследовать из старых снимков.
- **Сверка требований Messenger W208–W211 завершена:** живые критерии групп,
  авторизации/cache/WS, персонального unread, reply и group notifications уже
  перенесены в Block 4. Пересылка сообщения также остаётся live-критерием, чтобы
  подтвердить отсутствие утечки исходного чата. W210/W211 закрывали часть старых
  дефектов, но их live-результаты относятся к прежним SHA; текущая API/WS-группа
  требует нового доказательства. «Seen by N» реализован, однако отсутствует в ТЗ
  и не является MVP gate; W209 auto-delete при составе <3 и отдельные roster WS
  frames также не добавлять без изменения scope. FAB/date separators оценивать в
  общем visual review, не создавать отдельные продуктовые gates. Rationale
  W210/W211 перенесён; исторические копии без текущей роли удалены из working tree.
- Общая сверка документации завершена: применимые решения перенесены сюда, в ADR,
  runbooks и компактный audit ledger. Superseded audits и одноразовый session prompt
  удалены после переноса уникальных требований; актуальная и историческая evidence
  разграничены. Ссылки на удалённые документы не являются текущими инструкциями.
- `docs/README.md`, `docs/audits/INDEX.md` и AGENTS index reference согласованы:
  указаны canonical ownership, retention/rescue policy и bundle restore instructions.
  Обещание хранить все отчёты в archive и allowlist исторических broken links удалены.
- При следующих изменениях переносить долговечные шаги в ADR/runbook и обновлять
  canonical source перед сводками/переводами. Удалять документ только после проверки
  ссылок, переноса уникальных требований и подтверждения, что у него нет
  самостоятельной долговечной роли. Не добавлять старые handoff или абсолютные
  пользовательские пути в текущие инструкции.
- Повторно удалять или восстанавливать архивы не нужно: пути уже отсутствуют в
  текущем HEAD. Сохранять тесты поведения link checker, строгую проверку документов
  и оба режима checker (`--include-archives` — диагностический для restore); не
  создавать фиктивные ссылки на отсутствующие файлы.

**Приёмка документационной очистки:** уникальные требования имеют tracked-адрес;
120/120 path/blob/size строк inventory совпадают с rescue SHA; оба link-checker
режима проходят; Git history не переписана. Отдельный audit ledger остаётся открытым
до проверки всех 63 ID. Bundle остаётся изолированным из-за credential-подобной
истории; конкретной задачи восстановления сейчас нет. Read-only inventory нужен
перед переносом любых реально сохраняемых подписанных записей.

### Блок 3. Безопасный и воспроизводимый live-стенд

- Запускать тестируемый SHA в уникальном Compose project с явно принадлежащими
  этому запуску конфигурациями, сетями, контейнерами и синтетическими
  пользователями. Для текущей работы на `egorribun` использовать режим
  `--in-place` без новой ветки/worktree, с отдельным `--state-dir` вида
  `<system-temp>/ue-live-acceptance/run-<id>`: запуск фиксирует точный `HEAD`,
  требует чистую checkout и совпадение `--ref`, а также отвергает игнорируемые
  файлы в путях Docker `COPY`. Env, ключи, owner marker и Compose overlay хранятся
  только в принадлежащем запуску приватном state root; не читать и не
  перезаписывать `.env*`, `.secrets`, volumes или backups в checkout.
- Разделить CLI-операции: `status` только читает и ничего не генерирует; `stop`
  останавливает текущий стенд и сохраняет данные; `teardown` удаляет только
  проверенные ресурсы с run-owner labels/manifest. Перед запуском проверить порты;
  чужие процессы не останавливать. Compose и kind со взаимно конфликтующими
  портами запускать последовательно.
- Compose project имеет случайный run-id `ue-live-<16 hex>`; `.secrets/live-stand.json`
  связывает его с путями репозитория/run root, source SHA в in-place mode и
  HMAC-подписывается ключом в приватном Git common directory (worktree mode) либо
  приватном state root (in-place mode). Отсутствующий, повреждённый или чужой
  marker закрывает операции. Файл lifecycle lock сериализует `up`, `seed`,
  `stop` и `teardown`; `status` не создаёт и не меняет файлы. После source drift
  `status`, `stop` и `teardown` остаются доступны: stop/teardown пропускают только
  проверку текущего source SHA/cleanliness, но по-прежнему требуют HMAC owner,
  идентичность Docker daemon и совпадение подписанной Compose resource projection;
  изменённая resource projection закрывает удаление. Port preflight проверяет
  wildcard bind для Caddy 80/443 и loopback для Mailpit 18025. Ref сначала
  разрешается и проверяется на live overlay — до остановки текущего стенда и
  переключения worktree. `down` — data-preserving alias для `stop`; `teardown`
  удаляет только resources подписанного project и сохраняет state root,
  checkout, `.env*`, `.secrets` и evidence.
- Выбор `up --stack full|core` отделён от E2E `--mode smoke|full`.
  CLI default остаётся full, но для MVP явно указывать `--stack core`: Core —
  основной продуктовый стенд, full — отдельный release smoke. Его пять корневых сервисов — Caddy, Mailpit,
  notifications-worker, outbox-worker и SpiceDB — запускаются с обычными Compose
  dependencies, без `--no-deps`. Проверять точную утверждённую closure из 23 сервисов,
  включая Tempo/probe и init/migration jobs; изменение состава требует ревью.
  Все 16 значений портов остаются в подписанном interpolation map; Core проверяет
  занятость только десяти активных портов, включая loopback S3 endpoint.
  Resource fingerprint сохраняет identities
  и активные имена портов, чтобы разрешать подписанную смену host ports при restart.
  Full и исторические full owner schemas сохраняют проверку всех объявленных
  ресурсов, включая неиспользуемые volumes, которые удаляет `down --volumes`.
- Проверить в Docker readiness и рабочий ответ backend, SSR/Caddy, gateway, gRPC,
  WebSocket hub, NATS, Redis, S3/SeaweedFS и Mailpit; не считать container
  `running` достаточным readiness.
- На desktop/mobile запустить существующие реальные auth, role, login, MFA/TOTP,
  email OTP через Mailpit и password reset/reuse flows. Проверить безопасные
  redirects и отказ доступа student/teacher/admin по реальным API/данным.
- Завершить idempotent RU/EN demo seed на синтетических ролях: news, events,
  расписание, карта, личные/групповые чаты, stories, текущий Activity и пустые/
  частично заполненные состояния. Seed должен подтверждать владельца стенда,
  повторный запуск не умножает данные и режим явно opt-in. Для Messenger создавать
  только явно demo-owned синтетические аккаунты: DM требует двух участников,
  group — трёх. У Chat seed-id должен быть nullable, unique, внутренним полем
  существующей модели, с additive migration и exact-member validation; существующие
  неразмеченные или изменённые пользователем чаты не присваивать и не переписывать.
  Карта уже представлена локализованным frontend fixture, поэтому её приёмка
  проверяет RU/EN данные, а не создаёт лишнюю DB-модель.
  `/stats/summary` получает Grades из существующей модели `Grade` через
  `UserStatsRepository`; `GradeService` записывает оценки, audit event и отдельные
  уведомления, которые не служат источником статистики. Не создавать синтетические
  оценки/уведомления только ради заполнения Activity. Проверять допустимое пустое
  состояние при отсутствии оценок и согласованность статистики с доступными
  записями `Grade`. Новые предметные функции Activity не добавлять.
  Существующие аккаунты нельзя незаметно promote/reset; пароль demo-admin должен
  быть стабилен только в пределах подписанного стенда и одинаковым для seed и
  повторного live E2E, чтобы stop/start не ломал вход и не требовал изменения hash.
  Секрет хранить в
  проверенном owner-scoped `.secrets` файле с ограниченными правами; не выводить в
  argv/log/artifact и не читать файл чужого worktree. Lifecycle wrapper перед
  запуском повторно проверяет подписанный owner marker и Docker daemon, а дочерний
  seed script проверяет только переданный scope и Compose DB endpoint; environment
  sentinel не считать криптографическим доказательством владения.
- Сохранить действующий `admin-smoke-monitoring` lane на одноразовой GitHub
  PostgreSQL service отдельным явным CI-test-target режимом, ограниченным
  `ENVIRONMENT=testing`, loopback, точными service port/database и этим workflow;
  не добавлять общий bypass для произвольного `DATABASE_URL`. Обновить
  `start-docker.ps1` и контракт, чтобы пользовательский путь seeding шёл через
  проверенный live-stand target, а не напрямую в произвольную базу.
- Повторить запуск после `stop`; доказать воспроизводимость и сохранение данных.
  Исправить обнаруженные дефекты regression test + evidence.

**Приёмка блока:** чистый запуск → полный readiness → idempotent seed → существующие
live specs проходит дважды; stop/start сохраняет данные; status не меняет состояние;
teardown проверяет ownership; пользовательские тома и конфигурации не затронуты.

### Блок 4. Продуктовая приёмка и исполняемый live E2E

Построить traceability matrix: каждый применимый пункт ТЗ ссылается на сценарий,
результат и evidence; явно объяснить ручную проверку для свойства, которое нельзя
автоматически проверить. RU/EN и ширины 390/768/1440 px обязательны; 360/1024 px
проверять для меню, таблиц и рисковых адаптивных сценариев. Не перемножать без
необходимости все языки, роли, темы и ширины: матрица обязана показать, какой
сценарий подтверждает каждую ось и где полный набор вариантов необходим для риска.

- **Auth/MFA:** регистрация, login, TOTP, email OTP из Mailpit, recovery, reset и
  token reuse, safe redirect, cooldown/TTL/attempt limits, правильные 401/429,
  sibling/session revocation. Отдельно подтвердить отсутствие WebAuthn/security
  key flows в UI/API/SDK; это отрицательный критерий, новую поддержку не добавлять.
  Для email OTP принять только SHA-bound Linux integration evidence реального
  Postgres + Mailpit сценария
  `tests/integration/test_mfa_mailpit_outbox.py::test_email_mfa_handler_outbox_smtp_retry_and_resend`:
  SMTP failure оставляет outbox-событие retryable и не создаёт письмо; retry
  доставляет письмо ровно один раз; resend доставляет новый код и делает прежний
  challenge недействительным. В логах и artifacts не должно быть значений кодов,
  challenge tokens или адресов получателей. Slow/trickling SMTP peer должен быть
  остановлен в пределах заданного deadline раньше срока outbox lease; cancellation
  закрывает транспорт и не оставляет позднюю отправку. Свежий Linux evidence должен
  включать `tests/test_mfa_smtp_deadline_contract.py` и
  `tests/test_mfa_smtp_cancellation_contract.py`.
- **Messenger:** два независимых browser contexts и реальный WS; DM/groups,
  ordering/deduplication, reconnect, reply/edit/delete/forward/reactions/
  attachments/unread. Для групп проверить min 3 / max 100 участников при создании;
  разрешения add/rename для участника и remove только владельцем или самим собой;
  403 для постороннего до раскрытия типа чата; отказ групповых операций для DM;
  после изменения membership старый WS/cache не сохраняет доступ. Для пересланных
  и разделяемых вложений удалить blob только после удаления последней ссылки;
  сохранённая ссылка другого сообщения должна удерживать объект, а ошибка
  проверки ссылок или неоднозначное удаление должны оставлять cleanup безопасным
  для повторной доставки. Подтвердить в Postgres integration и storage regression
  tests (`tests/integration/test_chat_attachment_legacy_refs_postgres.py`,
  `tests/test_attachment_cleanup_reference_guard.py`). Прочтение сообщений
  участником A не сбрасывает unread участника B. Group notification
  содержит имя группы и автора. Quoted author получает ровно один `chat.reply`,
  без дополнительного общего `chat.message`. Проверить права на attachment.
  Mutations идут через backend, arbitrary client event payload не становится
  trusted event.
- **Profile/settings:** просмотр/редактирование профиля, avatar, validation и
  rollback, persisted state после reload, существующие достижения и все
  действующие разделы settings; не добавлять новые модели или правила достижений.
- **News/events/map:** сохранение scroll, back/forward, центрирование tabs,
  wheel/touch/pinch isolation и отсутствие page scroll jumps.
- **Schedule:** `app/services/schedule_service.py` при update проверяет итоговое
  расписание тем же правилом конфликтов, что create, исключая текущую запись.
  Regression tests проверяют частичный update, конфликт и допустимое сохранение
  неизменной записи; модель помещений/вместимости не добавлять.
- **Search:** без embeddings key обычный текстовый поиск news/events работает;
  UI остаётся текстовым; новый semantic toggle не добавлять. Прямые semantic-only routes явно
  возвращают недоступность сервиса, без вычисления результатов по нулевому вектору.
  Проверить `app/services/vector_service.py`, news/events API и потребителей UI;
  regression tests включают отсутствие ключа и рабочий configured provider.
  `EventRepository.get_analytics_data` с отсутствующим `max_attendees` удалить
  только после подтверждения отсутствия production/SDK потребителей; не вводить
  новую модель вместимости ради старого неиспользуемого метода.
- **Home/stories/activity:** пустые состояния, stories открываются по avatar,
  keyboard/swipe, пауза в hidden state, memory plateau; индикатор периода
  Activity совпадает с выбранной radio-кнопкой по геометрии bounding box (x, y,
  width и height с допуском 1 px); только текущие heatmap/trends/grades/comparison,
  без новых учебных целей/attendance.
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
failure исправлять, не маскировать ретраями/skip. Существующий mocked-набор
дополнительно прогнать в Firefox, WebKit и mobile-WebKit (эмуляция); он дополняет,
но не заменяет live Chromium-проверки доставки, прав и Web Push.

**Приёмка блока:** traceability matrix заполнена; browser сценарии проходят в
указанной матрице; известные несценарные/manual checks обоснованы; PR/nightly/manual
лейны реально запускают нужные test groups с корректными artifact/provenance.
Сценарии проходят дважды последовательно; полный release run привязан к RC SHA.
Текущий workflow следует перевести на Core явно, сохранив отдельный full smoke;
nightly/manual activation после merge проверить отдельно, не считать активной
только по наличию файла на рабочей ветке.

### Блок 5. Визуальная и performance-приёмка

- Сделать пакеты скриншотов текущих экранов RU/EN, light/dark, desktop/mobile.
  Review проводится небольшими наборами before/after. Принципы: матовый
  минимализм, ясная иерархия, отступы и design tokens; пустые состояния; только
  функциональные микроанимации. После пользовательского утверждения обновлять
  Linux visual baselines и фиксировать связь baseline с SHA.
- Использовать официальный Playwright container, версия которого совпадает с
  проектной Playwright dependency. Linux baseline является каноническим;
  Windows-only snapshot заменять после проверки соответствующего Linux output.
- До MVP: main JavaScript <500 KB по действующему измерителю; один проход
  Lighthouse по ключевым подготовленным маршрутам (login, home, news/events,
  profile/settings и messenger при наличии корректной fixture). Сохранить
  конфигурацию, routes, scores/report и SHA, использовать существующий collector.
  Не отключать действующие LHCI assertions ради ускорения: их перенос из PR
  оформлять отдельно в Q4, сохраняя scheduled/manual проверку.
- В v1.1: полный lab protocol navbar CLS <0.1, отсутствие map long tasks ≥50 ms,
  INP ≤200 ms при CPU4×/Slow4G и сертификация Lighthouse ≥0.95. Готовые измерители
  и исправления сохранить; field CWV остаётся вне локальной MVP-приёмки.
- Выполнить 20 последовательных циклов открытия/закрытия stories и подтвердить
  plateau использования памяти; проверить reduced motion и отсутствие serious /
  critical axe findings на принятых экранах.
- Проверить уже существующие Activity heatmap, trends, grades и comparison; не
  вводить новые предметные модели/функции сверх ТЗ.

**Приёмка блока:** пользователь утвердил конкретные комплекты и baselines; каждый
перфоманс-тезис имеет измерение, конфигурацию, браузер/железо/commit и артефакт;
несоответствия исправлены и перемерены.

### Блок 6. Переход CI сейчас, quality closure в v1.1

- Q1/Q4 ADR-047 интегрированы в reviewable пакетах. Сохранять согласованность
  зависимостей, результатов, event filters, special assertions, release rationale
  и catalog/contracts. Оставшиеся gates fail closed: ошибка, missing evidence
  или неожиданный skip не становятся PASS. Branch protection менять только
  в точной границе исходных14 contexts и отдельно разрешённого
  `Security Audit / Semgrep SAST` после готового reviewed CI diff и проверок;
  остальные правила сохранять, CodeQL оставлять blocking.
- Сохранить integrated planner/checker и ADR-040 presentation ignorer. Проверить
  затронутые контракты; не запускать полные мутации перед каждым MVP-коммитом.
  Полный inventory, survivors/runtime/no-coverage closure, Q2 dashboard/regression
  и Q3 coverage ratchet — v1.1. До Q3 coverage floors остаются действующими.
- Реальный security/auth/data дефект из любого теста исправлять для MVP, даже
  если он обнаружен мутацией. Equivalent exclusion допускается по ADR-047;
  quarantine, timeout-инфляция и ручной статус `Killed` запрещены.
- Strict typing, zero-warning build, Go race/lint, Rust checks, knip/deptry и
  canonical WASM parity сохраняются в применимой части существующих gates.
- O1–O8 и три сопоставимых полных зелёных CI прогона — v1.1. O9/ADR-045 и
  установленную bounded progress-оснастку не реализовывать заново.

**Приёмка MVP-части:** Q1/Q4 интегрированы, обязательные PR/main checks зелёные,
переехавшие lanes остаются исполняемыми, mutation score не блокирует release.
Полная quality closure и её исторические незавершённые результаты не объявляются
закрытыми из-за смены политики.

### Блок 7. Удалить доказанно устаревший код и оснастку

**Область:** v1.1, кроме уже начатого небольшого пакета и конкретных дефектов MVP.
Массовый cleanup не входит в critical path выпуска.

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

**MVP:** один backup/restore в изолированную цель и full smoke. RPO/RTO,
полная observability и deployed BE-02 — v1.1. Paired consistency и сохранность
исходной среды остаются обязательными даже для разового restore.

- Проверить поддерживаемые Compose-комбинации: base/full и overlays, Core, test;
  выполнить clean startup, health/readiness, корректный stop, повторный запуск и
  замер RAM/CPU. Пользовательские volumes и `.env` не удалять/переписывать.
- Проверить реальные S3 Put/Head/Get/Delete, presigned URL, private access,
  upload/download и object integrity. Завершить SeaweedFS metrics и Grafana
  dashboards/alerts; подтвердить Prometheus targets, logs и traces. Не дублировать
  уже существующие datasource configs.
- Использовать существующий manifest-aware `scripts/backup_db.py` и runbook,
  не реализовывать restore повторно. Завершить snapshot/restore-snapshot в
  отдельные DB/S3 targets и прочитать объект через восстановленную DB reference.
  Проверить manifest/checksums и явную цель; credentials принимать через
  environment/secret files, не argv/stdout/log. Согласование Helm CronJob с
  manifest CLI относится к v1.1 и не заменяет этот разовый app-compatible restore.
- Восстанавливать по умолчанию в отдельную БД и отдельное S3 пространство.
  Проверить согласованность относящихся друг к другу DB/S3 snapshot, object
  versions, manifest/checksums и восстановленного состояния; два независимых
  архива не считать автоматически одной точкой восстановления. Прогнать backup,
  restore, validation и rollback без перезаписи пользовательских данных.
- Для app-compatible paired restore manifest должен связывать source storage URL
  base с target public URL base и ключами объектов `<target-prefix>/<source-key>`;
  allowlisted DB references необходимо транзакционно переназначить на эти target
  URLs. Неизвестные ссылки, pending outbox-события со source URLs, несовместимая
  схема или превышение предела колонки должны приводить к отказу с rollback.
  Acceptance требует проверки на actual PostgreSQL/Alembic head и чтения объекта
  через `S3Storage` по ссылке из восстановленной БД; синтетический тест, пустой
  prefix или одна смена app config сами по себе deployed compatibility не доказывают.
- **v1.1:** усовершенствовать BE-02 preflight согласно блоку 2 и ADR-036. На непустых
  deployed Docker/kind databases проверить DDL upgrade/rollback, catalog state,
  idempotency и lock budgets.
- **v1.1:** измерить RPO ≤24h и RTO ≤30m на документированном demo dataset. Указать размер,
  число объектов, инструменты/ресурсы и какие компоненты входят в таймер.

**Приёмка MVP-части:** Core и release full smoke проходят; backup/restore
в отдельную БД и S3 доказал согласованность, чтение объекта по DB reference и
сохранность source. Полная observability, RPO/RTO и deployed migration proof —
отдельная приёмка v1.1; один разовый restore не является их сертификацией.

### Блок 9. Envoy Gateway / Gateway API и kind-приёмка

**Область:** full acceptance — v1.1. Готовые controller/CA prerequisites и
run-owned helper сохраняются на принятой контрольной точке. Не начинать новый
app deployment/chaos/rollback до MVP только ради закрытия старого блока.

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
- Закрыть обнаруженный race установки CRD: отсутствующий объект создавать с
  owner marker атомарно через create-only; SSA допускается для подтверждённого
  same-run объекта. Проверка UID после apply не предотвращает чужую мутацию.
  Добавить контроль конкурентного появления foreign CRD и сохранения его данных;
  ожидать Established до обращения к соответствующему custom resource.
- Поднять cluster/registry до сборки; собрать, просканировать и подписать образы;
  разворачивать immutable image digests, не mutable tags. Проверить TLS,
  HTTP/WebSocket/gRPC маршруты, Kyverno, ExternalSecrets refresh, metrics/HPA,
  restart/failure recovery, data-preserving rollback и storage.

**Приёмка блока:** kind развёрнут на известных immutable image digests; ingress-nginx
не требуется; маршруты/TLS/policies/security проходят контрактные и живые проверки;
chaos/recovery/rollback сохраняют данные; runner не удалил чужие cluster resources.

### Блок 10. Финальный аудит, ordinary merge и v1.0.0

- Перепроверить 63 audit IDs на RC: закрыто с evidence, отклонено с обоснованием
  или перенесено в v1.1 с владельцем. P0/P1 security не оставлять открытыми.
  BE-02/MIG-PASS deployed proof относится к v1.1; canonical WASM parity и
  RUST-P3-03 проверять действующим builder, не реализовывать экспорт повторно.
- Получить независимый auth/session/data review и утверждение визуальных пакетов.
  Заморозить code/dependencies/config/docs; пройти финальные Core scenarios,
  backup/restore и full smoke на этом RC. Изменение поведения после freeze
  создаёт новый кандидат и требует повторить затронутую приёмку.
- Обычный merge единственного PR после required checks. Для resulting main SHA
  получить новое push-main evidence согласно `quality/release-required-checks.json`;
  synthetic PR merge не подменяет released source. Admin bypass, force-push и
  общие изменения branch protection запрещены; разрешены исходные14 Q1/Q4
  contexts и отдельно ровно один `Security Audit / Semgrep SAST` после reviewed
  diff/проверок. Все остальные rules/contexts сохраняются; CodeQL blocking.
- Запустить готовый main-only producer ровно шести images: backend/frontend/
  gateway/ws-hub/file-processor/caddy. Сохранить Trivy, signing, SBOM/provenance
  и WASM parity; проверить фактические published digests и source/run/attempt
  manifest. Отсутствие image или несовпадение SHA не считать готовой публикацией.
- Существующий release consumer не заменять обходом: сверить его прежние
  сертификационные prerequisites с новой областью и согласованно обновить только
  неприменимые v1.1 зависимости, сохранив проверку происхождения шести images.
- Опубликовать tag/release notes `v1.0.0`: состав, ограничения, release SHA,
  image manifest/evidence и backlog v1.1. Не менять source после certification
  только ради вписывания run IDs; приложить готовый отчёт как artifact.

**Приёмка:** product DoD ниже выполнен, published source и шесть digests связаны;
полная kind certification, три comparable runs и RPO/RTO остаются v1.1.

## Изменяемые интерфейсы

Изменять публичные интерфейсы только при доказанной необходимости; передавать
ownership вместе с проверками:

| Интерфейс          | Требуемое поведение                                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Live stand CLI     | Read-only `status`; data-preserving `stop`; owner-checked destructive `teardown`.                                              |
| Demo seed          | Явный opt-in, идемпотентные RU/EN synthetic users/content, verified run ownership.                                             |
| Backup/restore CLI | Manifest/checksum validation, явная restore target, безопасная изолированная среда по умолчанию.                               |
| BE-02              | Read-only catalog preflight, DDL phase selection, единая логика загрузки миграций.                                             |
| Helm/Kubernetes    | Gateway API resources, параметризованные values/schema, сохранение TLS, routing и security policy.                             |
| CI                 | Catalog/contracts синхронны; PR live smoke и полный nightly/manual E2E.                                                        |
| Release evidence   | Source SHA, workflow run/attempt, inventory provenance, immutable digests, signatures, SBOM, результаты приёмки и ограничения. |

## Финальный checklist v1.0.0

- [ ] Каждое применимое требование ТЗ 2–13 имеет сценарий/результат/SHA либо
  обоснованную ручную проверку; Core-сценарии проходят дважды, mocked Firefox/WebKit
  проверены в scheduled/manual lane; stop/start сохраняет demo state.
- [ ] Визуальные RU/EN/light/dark/desktop/mobile пакеты утверждены; Linux baselines,
  JS budget, Lighthouse, 20 циклов stories и accessibility приняты.
- [ ] Нет открытых P0/P1 security; все 63 audit IDs классифицированы, auth/session/
  data review завершён, ADR-006 ordering согласован; бренд ГУУ ограничен внутренним
  синтетическим демо до отдельного решения о публичном использовании.
- [ ] Q1/Q4 внедрены; все оставшиеся required PR и main-push checks проходят,
  Tier 0 и действующие pre-Q3 coverage floors соблюдены. Нет необъяснённых failures,
  skips, исключений, waivers или подменённого evidence.
- [ ] Разовый согласованный DB/S3 backup восстановлен в отдельные цели; объект
  прочитан по ссылке из восстановленной БД, исходные данные сохранены.
- [ ] Frozen RC прошёл full smoke; ordinary merge завершён; resulting-main source
  проверен заново. Готовый producer опубликовал ровно шесть проверенных digests с
  работающими security/signing/evidence шагами.
- [ ] Tag/release notes опубликованы со списком ограничений и backlog v1.1;
  repository чист, документация согласована, rescue bundle остаётся приватным.

## Backlog v1.1 и последующего развития

| Направление | Сохранённая область и обязательная будущая приёмка |
| --- | --- |
| Q2/mutation debt | Nightly regression >1 п.п., dashboard, полный canonical inventory и разбор слабых поведенческих тестов; рабочие цели ADR-047, без ручного Killed. |
| Q3/coverage | Доверенная main baseline, no-decrease ratchet и90% non-Tier-0 patch coverage; Tier 0 остаётся100%. До Q3 текущие floors сохраняются. |
| O1–O8 | Три comparable полных green runs, population/source provenance, timing/cost/critical path и operability report; начатые инструменты сохраняются. |
| Release certification/kind | Опубликованные шесть GHCR digests, их полный kind deploy, TLS/routes/policies, Kyverno/ExternalSecrets/HPA, failure recovery/rollback; подписи/SBOM/provenance уже сохраняются в MVP producer. |
| Storage/DR/observability | RPO24h/RTO30m, согласованный paired restore по документированному набору, реальные targets/logs/traces, dashboards/alerts; MVP one-time restore не исключает DB/S3 consistency. |
| BE-02/MIG-PASS | Непустые deployed DB catalog/upgrade/rollback/lock budgets и secret-backed identity; история миграций сохраняется. |
| WS load | 1000 connections/500 pairs/100 messages per second/30 minutes, p95≤500ms и reconnect/resource stability. |
| Full lab performance | CLS/INP/map long tasks и LHCI≥0.95 protocol; принятые исправления и существующие scheduled checks сохраняются. |
| Code/tooling consolidation | Reachability/API consumers/assets/i18n/generated/helpers/invariants/concurrency, gate cost и дубли; skills/wave cleanup без потери harness/tests. |
| Перед публичным использованием | Разрешение на название/логотип ГУУ, политика/согласие на персональные данные и отдельная приёмка реальных провайдеров/сред. |
| Поздние продуктовые решения | Единый search mechanism и Spotify integration review; QR-приход и лимит мест не добавлять без нового продуктового решения. |

Следующая учебная волна — корпуса/аудитории и вместимость, преподаватели,
дисциплины/нагрузка, семестр/диапазоны недель, численность групп, xlsx import и
площадки мероприятий. Она оформляется отдельным ADR/планом после MVP.

## Продолжение сессии

Прочитать root/domain AGENTS, этот план, ADR-047, STATUS и ТЗ; проверить branch,
HEAD/remotes/CI и owned ресурсы. Продолжить ближайший незавершённый шаг из STATUS:
required CI, product/security fixes, Core acceptance, visual/restore, RC и выпуск.
Не открывать новые mutation,
kind и массовые cleanup очереди ради старого checklist. После контрольной точки
обновить короткий STATUS; старые handoffs и локальные результаты не являются
доказательством текущего SHA. Сохранять чужие env/data/backups, migration history,
Git history и приватный rescue bundle.
