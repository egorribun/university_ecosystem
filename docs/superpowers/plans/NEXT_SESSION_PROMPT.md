# Сообщение для нового чата: довести MVP до выпуска

Продолжи автономное исполнение MVP по единому мастер-плану до обычного merge и выпуска. Ниже — моё поручение для новой сессии: разрешаю необходимые изменения, commit/push на `egorribun`, работу в существующем PR и публикацию ровно шести образов готовым main-only producer. Не делай admin bypass или force-push. Branch protection можно изменить только в явно разрешённой границе 14 contexts после готового reviewed CI diff и проверок; остальные правила сохраняются.

Последующее явное разрешение владельца от 2026-10-09 дополняет эту границу
ровно одним context: `Security Audit / Semgrep SAST`. Удалить его только после
reviewed scanner de-dup diff и проверок; CodeQL остаётся blocking, Semgrep —
в pre-commit. Во всех ниже приведённых ссылках на исходные14 учитывать также
это единственное дополнение (91 →76 contexts), сохраняя остальные правила.

## Цель и источники истины

Ты — root-оркестратор для репозитория `C:\Users\egorribun\Documents\university_ecosystem`. Работай только в одном checkout на `egorribun`, в текущем PR #1306. Не создавай новые ветки и worktree. Root владеет всеми Git-операциями: stage, hooks, commit, push, PR и обычный merge; root также единственный владелец правок canonical `MVP_MASTER_PLAN.md`, `STATUS.md`, `AGENTS.md`, ADR-047 и readiness audit. Разрешённое число итоговых GHCR images — ровно шесть, через уже существующий main-only producer; не переписывай его ради упрощения проверки.

В самом начале освежи рабочее состояние: `git status`, текущий branch/HEAD/upstream, PR и его проверки, завершённые/активные GitHub Actions, доступность `gh` и точные применимые инструкции `AGENTS.md`. Последний проверенный опубликованный ориентир — HEAD `c06d4d23723b90639ef9696587e1bb77daeb50db`, PR #1306; checkpoint описан ниже и в `STATUS.md`. Root может добавить commit после подготовки этого сообщения, поэтому не требуй именно этого SHA. Run IDs `37966963034` (matrix/CI, pending на18:11 UTC) и `37966962319` (advisory Owned Live, contract preflight FAIL) — указатели для обновления статуса, а не доказательства для нового HEAD. Последний полный required green относится кf14 и Matrix37946889584.

Commit message для maintenance используй без wave, например `fix(quality): ...`, `test(contracts): ...` или `docs(quality): ...`. Никогда не добавляй `Co-Authored-By`. После запуска `detect-secrets` или pre-commit всегда заново stage `.secrets.baseline`, даже если он выглядит неизменённым.

Единственный рабочий master-план — `C:\Users\egorribun\Documents\university_ecosystem\docs\superpowers\plans\MVP_MASTER_PLAN.md`. Продуктовое ТЗ — `C:\Users\egorribun\Documents\university_ecosystem\docs\superpowers\plans\University_Ecosystem_MVP.md`, короткий срез — `C:\Users\egorribun\Documents\university_ecosystem\docs\superpowers\plans\STATUS.md`, политика — `C:\Users\egorribun\Documents\university_ecosystem\docs\adr\ADR-047-risk-based-quality-policy.md`, связанный security decision — `C:\Users\egorribun\Documents\university_ecosystem\docs\adr\ADR-006-websocket-auth-tickets.md`. Прочитай также `C:\Users\egorribun\Documents\university_ecosystem\AGENTS.md`, `C:\Users\egorribun\Documents\university_ecosystem\app\AGENTS.md`, `C:\Users\egorribun\Documents\university_ecosystem\frontend\AGENTS.md`, `C:\Users\egorribun\Documents\university_ecosystem\services\AGENTS.md` и инструкции по реально затрагиваемым областям. Проверь root-аудит `C:\Users\egorribun\Documents\university_ecosystem\docs\audits\MVP_READINESS_AUDIT.md`; он не заменяет canonical plan и не должен переписываться без отдельного владельца. `AUDIT_PROMPT.md` — другой read-only шаблон, не исполняемое поручение. Не добавляй логи и устаревшие снимки в индексы документации.

Проверь состояние Codex goal. Если существует любая незавершённая цель, в том числе `paused`, не вызывай `create_goal` повторно: API не позволяет тебе менять её objective или самостоятельно resume; честно отрази статус и продолжай работу в пределах пользовательского поручения. Не объявляй прежнюю цель завершённой. Создай новую цель на весь выпуск без token budget только если незавершённой цели нет.

## Организация и безопасность выполнения

- Используй root и максимум трёх агентов `gpt-6-luna`, reasoning `max`; делегируй только реально независимые области с непересекающимися файлами. Все работают в том же checkout; root единолично владеет Git и перечисленными canonical docs. Для агентов выбирай `fork_turns=none` или минимальное явно нужное число последних turns, чтобы не наследовать длинные устаревшие handoff-инструкции. Если параллельной работы нет, не создавай агента. На одну область — 30-минутный checkpoint; длительные внешние проверки отслеживай отдельно и не выдавай за завершённые.
- До тяжёлого процесса измеряй RAM/free memory, диск, Docker и занятые порты: стартовать только при RAM ≤75% и free RAM ≥8 GiB; сверить доступный диск с реальным размером workload. Во время процесса остановить только его собственное дерево при RAM ≥85% или free RAM <4 GiB. Один тяжёлый workload за раз. Не убивай чужие процессы, не выключай общий Docker/WSL, не делай global prune и не удаляй неизвестные ресурсы.
- Последующее явное разрешение владельца от2026-10-09: только одиночные Linux screenshot-прогоны допускаются при startup RAM≤80%/free≥6 GiB, browser container ограничен1 GiB/2 CPU. Runtime guard RAM≥85%/free<4 GiB и все проверки качества сохраняются. Это исключение не распространяется на build, полный E2E, Lighthouse или другие workloads.
- Данные только синтетические. Не используй реальные аккаунты/пользовательские данные, не выводи credentials, cookies, tokens, HMAC keys, `.env`, VAPID keys или сырые чувствительные логи. Храни чувствительные доказательства в приватной директории за пределами checkout. Не коммить временные receipts, секреты, screenshots с реальными данными и backup-артефакты. Reviewed visual baselines на синтетических fixtures сохранять в предусмотренных tracked путях после утверждения владельца.
- Для live стенда используй только `scripts/live_stand.py` и уже проверенный owner-checked lifecycle. Перед запуском изучи `--help` и актуальные контракты. Каждая команда CLI `up/status/seed/e2e/stop/teardown` должна указывать один и тот же свежий уникальный `--state-dir` — дочернюю директорию `C:\Temp\ue-live-acceptance\run-<GUID>` — и работать с тем же clean SHA. Для MVP явно выбирай `up --stack core`; E2E `--mode` — отдельное понятие. Перед seed/E2E проверь подписанного владельца, source, daemon, Compose inventory/resources и readiness. Credentials создаёт/использует CLI из принадлежащего ему состояния, не передавай секреты вручную в аргументах/выводе. Остановка должна сохранить данные; teardown удаляет только доказанно принадлежащие этому run синтетические ресурсы.
- Core — основная продуктовая приёмка; full — отдельный smoke на frozen RC. Compose closure вычисляй из текущей проверенной модели, не закрепляй число сервисов из старых отчётов. Требуй readiness всех выбранных сервисов: корректное завершение one-shot init jobs, health long-running сервисов и отдельные функциональные probes, включая Mailpit и revocation Redis. Не подменяй полный результат наличием контейнеров или одним HTTP 200.
- Локальный refresh подтвердил Python 3.14.7, Node24.21, Go1.27.1/Rust1.98.1; актуальный CI pins Go1.26.9 (fuzz1.27.2), канонический Rust сверять по source/lock. Не называй локальную среду эквивалентной CI. Python-скрипты запускай без изменения окружения (`uv run --no-sync`), npm — по lockfile (`npm ci`, только если зависимости реально отсутствуют), не обновляй lockfiles/менеджеры пакетов без необходимости и отдельного review.
- После каждого значимого этапа пиши краткий прогресс root/пользователю: проверенные факты, SHA, конкретный результат, остающийся риск и следующий checkpoint. Не проси повторного разрешения на обычные обратимые шаги, уже явно разрешённые этим поручением.

## Неизменяемые продуктовые и quality-границы

1. Цель v1.0.0 — принятый продукт по ТЗ, одобренные визуальные пакеты, отсутствие открытых P0/P1 security findings, все обязательные проверки, обычный merge и источник-проверяемый выпуск шести образов. Полная сертификация образов в kind, RPO/RTO, global mutation score, три сопоставимых полных CI runs и deployed BE-02/MIG-PASS — v1.1. Один безопасный app-compatible DB/S3 backup/restore в изолированную цель и проверка восстановленного объекта по DB reference обязательны уже для MVP.
2. Q1 и Q4 ADR-047 обязательны до MVP. Q1 убирает mutation execution из blocking PR/main graph, `needs`/`results`/обязательные агрегаты, сохраняя nightly/manual evidence. Q4 переносит Schemathesis, DAST, chaos, cross-browser E2E и kind в scheduled/manual на default branch; PR сохраняет lint/types/unit/contracts, OpenAPI/GraphQL drift, текущие coverage floors, Tier 0 и требуемую security-проверку. Реальный Chromium smoke остаётся на PR. Проверяй `needs`, aggregate `results`/assertions, triggers, catalog, release-required checks и fail-closed поведение согласованно, а не только отдельный YAML job. Используй существующие evidence collectors, не строй новый CI evidence harness вне Q1/Q4. Цель blocking PR — 15 минут критического пути; измерь и честно сообщи результат.
3. До Q3 сохраняются нынешние per-component coverage floors и 100% patch coverage; Tier 0 остаётся 100% по применимым line/statement/branch/function metrics. Не опускай их молча. Q2/Q3 — v1.1. Не запускай полные mutation очереди ради 100% глобального score, не меняй статус mutant вручную и не придумывай исключения.
4. Не расширяй продукт новыми учебными целями, attendance, CDC, сущностями аудиторий/вместимости, QR/лимитами мест или обязательной MFA. RU/EN, light/dark; обязательные ширины 390/768/1440, дополнительные точечные 360/1024. ГУУ остаётся внутренним demo-брендом; реальный пользовательский трафик и публичное использование требуют отдельного решения.
5. По ADR-006 принято направление: сохранить durable tombstone и WebSocket revoke до commit, консервативный rollback с logout siblings документировать. Не меняй этот ordering; независимо проверь failure paths и зафиксируй фактические guarantees/limits. Не превращай тест или непросмотренный сценарий в доказательство безопасности.
6. Исторический audit зафиксировал ruleset `8335285`, enforcement ACTIVE и91 required context. Разрешённые14 contexts плюс отдельно разрешённый `Security Audit / Semgrep SAST` уже удалены после code/contracts/review: текущий проверенный набор76. Остальные rules сохранены, CodeQL blocking, Semgrep в pre-commit. Q4 boundary: четыре full Chromium shards и LHCI scheduled/manual, PR live Chromium smoke сохраняется. Не повторяй выполненные removals и не меняй остальные protection rules. Любое дополнительное protection изменение требует отдельного разрешения. Admin bypass и фиктивные compatibility PASS запрещены.

## Проверенный checkpoint послеf14 и ближайший порядок

Безопасная пауза после checked commit/push c06 завершена; владелец явно
возобновил работу, actual goal active. Новые live/runtime очереди ещё не
запускались. Сверить actual goal/Git/PR: self-SHA документа не закрепляется.

На c06 advisory37966962319/a1 упал до Docker: automatic owned cleanup добавил
eager browser dependency в browser-free page-error contract. Production cleanup
сохраняется; минимальный test-only override проходит private absent-browser
RED15 PASS/1 FAIL→GREEN16/16. Root integrated полный Node suite browser-absent
158/158 PASS18:16 UTC; обычные hooks/commit/push и новый unique Core на новом
clean SHA ещё требуются. Matrix37966963034/a1
на18:11 UTC active:70/76 required SUCCESS,2 active/4 final contexts pending.

Последний independently verified опубликованный HEAD/origin/PR1306:
`c06d4d23723b90639ef9696587e1bb77daeb50db`. Git/PR могут содержать следующий
commit; сверить актуальные значения. Minimal skip-string correction, owned
session cleanup и approved Home baselines уже опубликованы обычными hooks/push.

- Matrix37946889584/a1 SUCCESS: exact-head/ruleset join16:35 UTC76/76 required
  SUCCESS, missing/duplicate/bad/wrong-head/integration-mismatch0.
  All-job span44m53s/required Matrix43m33s; target15m открыт, backend cap2 сохранён.
  Это evidence дляf14, не для нового SHA. Q1/Q4 migration/protection DONE.
- Advisory Owned Live37946889184/a1 FAIL:15 PASS/3 FAIL/2 expected skips;
  logout429→200/reset replay429. Старый run не сохранял Retry-After.
  Не менять auth caps/лимит5/min и не повышать advisory context до required.
- Coref14 startup/readiness/admin-only seed/canonical demo seed PASS;
  persisted SEC-03 API/PG canonical-v2/signature/logout→sameBearer401 PASS
  в узкой границе, без key rotation/native signing certification.
- Coref14 canonical teardown16:42–16:45 UTC PASS: containers/networks/volumes
  0/0/0, source stable, owned children0, resource/time guardfalse.
  Private state/env/evidence сохранены. Новый SHA требует нового unique state.
- Владелец явно утвердил новый Home12 наddbbc84d (RU/EN, light/dark,
  390/768/1440); единственное замечание navbar gap закрыто. Approved12 PNG
  byte-for-byte и curated provenance сохранены в
  `frontend/visual-baselines/live/home-empty/`. Не спрашивать повторно и не
  выдавать freshf14 technical12/12 за approval иных байтов.
- Targeted News/Events/Schedule наf14:1 PASS/14 FAIL/1 expected skip за3m28s,
  source stable/no resource stop/owned children0; fullf14 не запускался.
  Source-proven News heading/count drift, missing archive row и default Events
  tab URL исправлены пакетом послеf14; Schedule production defect не доказан.
- Reviewed RetryV3 сохраняет исходный60s body deadline и assertions;
  только один429 retry при строгом Retry-After1..60 и достаточном реальном
  Playwright slot deadline с cleanup reserve. Уникальный reset-account DELETE
  в существующем owned cleanup slot; logout200→sameBearer401 обязателен.
  V2 deadline bug отклонён. Сначала интегрированные tests/preflight/hooks.
- Native StoryV7 actual:1 warmup+20 measured, hidden7002ms,
  heap delta263892≤524288 bytes, focus/storywrites0/logout401/cleanup PASS.
  Итог INCOMPLETE: DOM unstable, reduced-motion progress>0 probe противоречит
  production progress0. V8 исправляет predicate/добавляет bounded numeric DOM
  series, exact DOM gate сохраняется; proof/SHA/state pins обновить перед run.
  V4/V5/V6 incomplete receipts сохраняются, не повторять без нового evidence.
- Push educationf14 0/12 eligible: actual permission denied. Credentialless
  normal-profile/OTR diagnostic подготовлен; не grant/requestPermission/mock.
  LHCI V12 driver/seeded-DM UUID discovery и paired restore сохранены приватно.
  Ни один prepared operator не считается runtime PASS.
-63 ledger IDs исторически60 CLOSED/2 DECLINED/1 OPEN(BE-02), source/test review
  21 P0/P1 без нового дефекта. Runtime certification каждой строки не заявлена.
  BE-02 deployed catalog/upgrade/rollback —v1.1.

На паузе: Native V9 static root review/hash/ACL PASS, runtime unrun. LHCI driver
V12 нельзя запускать до исправления hardcoded old proof-root, обязательной
freshness по seed guard.finishedUtc и derived Compose count. Paired snapshot V5
draft требует root review; он не выполняет restore. Push comparison parent draft
не прошёл AST/Ruff и explicit file ACL checks. Точные private paths/hash/status
сохранены в `pause-checkpoint-*.json` под приватным rootreceipt:
`C:\Temp\ue-mvp-root-20261009-7013fd5453f545c4bdf6abc7f24736c7\rootreceipt`.
Не выдавать drafts за PASS; старые Core proofs истекли и source/state не заменяют.

Не повторять уже интегрированные inventory/hook/schedule/semantic/upload/auth/
SSR/navbar/membership/Q1/Q4 fixes. Full Core89 FAIL76/114/8 за30m29s;
session leak не доказан причиной всех114. Full14c2 resource-aborted с cleanup
UNCONFIRMED сохраняется. Superseded Core14c2/df/89/dd/f14 удалены canonical
teardown; receipts/Git history приватно сохранены.

Пакет послеf14 интегрирован: root Python1286/1286, Vitest64/64 и Node158/158
PASS; preflight initial8/10, final frontend types/lint/format3/3 PASS,
Ruff4 paths/437 Markdown links PASS. Старые integration FAIL сохранены,
не выдаются за PASS. Ordinary hooks/restage baseline/commit/push проверить по
actual Git/PR и private checkpoint receipt. Новый hosted CI ещё не подтверждён.

После явного возобновления: verify published clean SHA/Git/CI → fresh Core/
readiness/admin-only seed/Home comparison/SEC-03/demo seed → affected targeted
specs → два consecutive full passes. Full success:190 PASS+exact8 source/project
expected skips, failures/flaky/interrupted/did-not-run0. Unexpected skip —FAIL.
Затем native Stories, все согласованные visual packets/approval/LHCI, all-topic
real Push/auth/MFA/WS, stop/start persistence, security/data/isolated restore,
frozen-RC full smoke и обычный выпуск. Наличие подготовленного script или
исторического green не закрывает current-SHA acceptance.

## Исполнение MVP по bounded пакетам

После начального refresh и получения завершённых CI результатов построй live traceability по каждому применимому пункту ТЗ 2–13. Для каждой строки запиши: точное требование/условие, production route/UI, unit/contract test, mock или настоящий backend/Chromium, файл live-сценария/role/locale/viewport, SHA/run/attempt, итог и оставшийся риск. Mock-only покрытие помечай явно; оно не закрывает real auth, authorization, persistence, realtime delivery или Web Push. Проверяй текущие исходники и `rg --files`, не полагайся на старые названия/summary.

Параллельные ограниченные пакеты после проверки ownership:

- **CI/Q1/Q4:** проверить уже согласованный graph/catalog/contracts на новом HEAD; исправлять только конкретные новые failures, сохраняя живой Chromium PR smoke и защиту секретов. Текущий owned-live context advisory; повышать до required только после трёх последовательных smoke successes и измерения бюджета. Ruleset removals уже выполнены; сохранить остальные76 contexts. Проверить обычный PR lane end-to-end и измерить critical path относительно15m.
- **Backend:** подтвердить уже внесённые schedule/semantic/upload/auth fixes на текущем image; новые изменения только по доказанному пробелу. Отдельно audit потребителей `EventRepository.get_analytics_data` прежде чем удалять. Generated OpenAPI/spec/client outputs делать только через текущий канонический exporter, с byte/diff review и tests.
- **Frontend/live:** существующие auth/TOTP/email OTP/reset/roles/lockout, profile/settings persistence, home/stories, messenger DM/group/membership/reconnect, все пять notification topics и настоящий Web Push через настоящий Chromium, admin denial, SSR/i18n/PWA/offline, schedule/map/activity. Новые тесты только если доказан конкретный пробел, реальные fixtures с владельцем/cleanup, без ослабления assertions/timeout и без rote-test-per-mutant.
- **Visual/performance/accessibility:** принимать согласованные RU/EN, light/dark, desktop/mobile screenshots на Linux baselines; точечно проверить ширины из ТЗ. Запустить существующий Lighthouse/Bundle collector на ключевых route-ах, показать JS budget `<500 KB`, сохранить конфигурацию и сырые artifacts приватно. Пройти 20 story viewer cycles, memory plateau/cleanup, reduced motion, axe без serious/critical. Получить одобрение реальных пакетов от владельца; Windows snapshots не выдают за Linux approval.
- **Security/data/restore:** независимо разобрать auth/session/data и все 63 audit ID; P0/P1 нельзя переносить. Завершить один owner-checked DB/S3 restore в отдельные изолированные цели и подтвердить восстановленный объект через DB reference. Сохранять исходные backup/env/data; не заявлять RPO/RTO, kind certification или production migration, если они не проверены.

Для UI проверяй ARIA/keyboard/focus, empty/error/loading state, SSR hydration, client-only APIs и service worker по `frontend/AGENTS.md`. Для backend соблюдай `app/AGENTS.md` и текущую модель ownership/DI. Не добавляй новую runtime-зависимость, mock, generated client, test exclusion или CI compatibility shim без конкретного доказательства и review.

## Текущие CI/security замечания и решения владельца

Перед выводами уточни доступность `gh auth status` и нужных read-only GitHub/API возможностей; наличие MCP-инструмента или gh CLI не означает автоматически полные права. Не открывай browser для чтения секретов. Сохраняй `headSha`, workflow/run ID, attempt, job/step, artifact identity/digest, command/config hash и безопасные counts/status. Не публикуй credential-bearing output. Любой incomplete/cancelled/timeout/unsupported result остаётся незавершённым, не PASS.

Read-only audit `C:\Users\egorribun\Documents\university_ecosystem\docs\audits\MVP_READINESS_AUDIT.md` сохраняет исторический snapshot ruleset `8335285` (91 context), proposal14 и последующие updates. Разрешённые14+1 removals уже выполнены, все прочие76 contexts/rules сохранены; scheduled/manual для четырёх full Chromium shards и LHCI, PR live smoke остаётся. ADR-006 сохраняет durable tombstone/WS-before-commit и conservative sibling logout при rollback. Exact dismissal3382/3383 также уже разрешён и выполнен с audit comment; не расширяй его. Повторный approval нужен только для дополнительного protection изменения. Обычные commit/push/PR/merge/release уже разрешены.

Audit также сообщает, что `Chromatic` пропускается из-за billing gates. Не включай paid run и не проси покупку. Используй существующие бесплатные/локальные visual collectors; конкретное визуальное принятие всё равно требует owner review.

## Завершение и критерии готовности

Не называй MVP готовым, пока не выполнены все обязательные строки финального checklist в master plan на одном зафиксированном SHA. В частности: Q1/Q4 и required checks согласованы; полный применимый Core traceability покрыт двумя последовательными успешными прогонами; основной live workflow явно запускает Core и сохраняет отдельный frozen-RC full smoke; stop/start сохраняет demo state; визуальные пакеты утверждены; security review, audit IDs и один restore закрыты; нет открытых P0/P1; CI проверки прошли без скрытых retries/compatibility passes; PR #1306 обычным способом слит; main-push checks и существующий producer выдали ровно шесть source-bound images с проверенными manifest/digests/signing/SBOM/provenance; release notes/ограничения точны.

В финале сообщи SHA/PR/merge/release, run IDs и evidence links, что реально прошло, что отложено в v1.1 и почему, риски/лимиты, шесть image digests, restore/visual approvals и расходы/сроки тяжёлых проверок. Обнови `STATUS.md` только после проверки фактов и не переписывай историю прошлых результатов. Никакого заявления о release PASS, если обычный merge, свежие main checks или image provenance не подтверждены.
