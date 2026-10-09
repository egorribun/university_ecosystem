# Сообщение для нового чата: довести MVP до выпуска

Продолжи автономное исполнение MVP по единому мастер-плану до обычного merge и выпуска. Ниже — моё поручение для новой сессии: разрешаю необходимые изменения, commit/push на `egorribun`, работу в существующем PR и публикацию ровно шести образов готовым main-only producer. Не делай admin bypass или force-push. Branch protection можно изменить только в явно разрешённой границе 14 contexts после готового reviewed CI diff и проверок; остальные правила сохраняются.

Последующее явное разрешение владельца от 2026-10-09 дополняет эту границу
ровно одним context: `Security Audit / Semgrep SAST`. Удалить его только после
reviewed scanner de-dup diff и проверок; CodeQL остаётся blocking, Semgrep —
в pre-commit. Во всех ниже приведённых ссылках на исходные14 учитывать также
это единственное дополнение (91 →76 contexts), сохраняя остальные правила.

## Цель и источники истины

Ты — root-оркестратор для репозитория `C:\Users\egorribun\Documents\university_ecosystem`. Работай только в одном checkout на `egorribun`, в текущем PR #1306. Не создавай новые ветки и worktree. Root владеет всеми Git-операциями: stage, hooks, commit, push, PR и обычный merge; root также единственный владелец правок canonical `MVP_MASTER_PLAN.md`, `STATUS.md`, `AGENTS.md`, ADR-047 и readiness audit. Разрешённое число итоговых GHCR images — ровно шесть, через уже существующий main-only producer; не переписывай его ради упрощения проверки.

В самом начале освежи рабочее состояние: `git status`, текущий branch/HEAD/upstream, PR и его проверки, завершённые/активные GitHub Actions, доступность `gh` и точные применимые инструкции `AGENTS.md`. Последний independently verified опубликованный ориентир перед этим обновлением — HEAD `cce5e6eb5be85bbe22493d5a0f6f25ebccb4091d`, PR #1306; checkpoint ниже и в `STATUS.md`. Root может добавить successor commit после подготовки этого сообщения: не требуй self-SHA документа. Matrix `37972688405` и Owned Live `37972687964` завершены SUCCESS для cce5 в своих границах; не переносить их green на новый HEAD.

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

## Проверенный checkpoint и ближайший порядок

Работа возобновлена, goal active. Последний независимо verified published
checkpoint перед этим обновлением — `cce5e6eb5be85bbe22493d5a0f6f25ebccb4091d`,
tree `acb4ba868c5dfb3cff7a7a68cf81b49d6dfe2187`, HEAD/origin/PR совпадали.
Successor SHA/hooks/push/CI сверять по actual Git/PR, без self-SHA документа.

- Matrix37972688405/a1 SUCCESS: exact-head/ruleset join19:14 UTC76/76 required
  SUCCESS, pending/missing/failed0, CodeQL SUCCESS,140 unique check runs.
  Matrix72 jobs SUCCESS/14 SKIPPED; required span43,37min, цель15min открыта.
  Q1/Q4 и14+1 protection removals DONE; backend cap2 и остальные76 contexts сохранить.
- Owned Live37972687964/a1 SUCCESS в advisory Core-smoke границе; frozen-RC
  full-stack steps SKIPPED, не full PASS. Browser-free isolation fix опубликован
  наcce5; root Node158/158 без browser PASS. Старый c06 advisory FAIL не повторять.
- Corecce5 fresh up/admin-only seed/readiness/SEC-03/canonical demo seed PASS.
  Targeted six specs8 PASS/7 FAIL/1 expected skip за3m13s, fullcce5 не запускался.
  Actual News diagnostics доказали RU/EN category drift и zero desktop setup-scroll;
  Schedule API28 lessons/group assigned, два valid grids; seed/production не менять.
  Logout429/Retry-After33 не помещался в26,463s remaining: strict FAIL сохранён.
- Root integrated19-file reviewed package: locale-stable News helper/5consumers,
  seven unit test files; real positive scroll+settled route content; named Schedule
  grid/tablist locators+existing contracts. Assertions/deadline/caps/rules не ослаблены.
  Vitest70/70 PASS, static types/lint/format/i18n4/4 PASS, browser-absent live Node
  contracts158/158 PASS,0 skips. Ordinary hooks/restage baseline/commit/push successor проверить;
  current-source browser/hosted acceptance пока не подтверждены.
  Дополнительный full frontend coverage20:23–20:28 отменён root: CANCELLED,
  source/21-path working snapshot stable, owned children0; не считать coverage PASS.
  Обязательный hosted coverage и нынешние floors сохраняются.
  Дополнительно root integrated reviewed logout-header V3 в5 файлах: отдельный
  bounded stdout protocol, legacy retry record и deadline/caps/logout→401 сохранены.
  Root Node160/160, весь live_stand Python1292/1292, Ruff check/format и повторный
  integrated static4/4 PASS;26-path snapshot stable/owned children0/stopfalse.
  Root integrated canonical remote visual collector + News bounded readiness
  в2 файлах: root visual/auth/admin Node59/59 PASS, scoped ESLint/Prettier PASS,
  28-path snapshot stable/owned children0. Linux capture/owner approval пока NOT RUN.
- Canonical Corecce5 teardown19:52–19:56 PASS; independent post-teardown readback
  containers/networks/volumes0/0/0, source stable/owned children0/guardfalse.
  Старый state `run-66842753-1521-4c10-a5e0-ac5e1fbcb8a6` и private receipts
  сохранить. На этом state больше ничего не запускать; создать новый unique run.
- Home12 наddbbc84d уже явно approved владельцем;12 tracked baselines/provenance
  byte-identical. cce5 technical12/12/axe0/cleanup PASS не approval других bytes.
  Ошибочный navbar-regression вывод исправлен actual crop comparison; новых
  navbar fixes не требуется. Остальные visual packets/LHCI/owner approvals открыты.
- Native V10 actual INCOMPLETE:20/20close, heap delta254461,6≤524288,
  hidden7000,7ms/focus/scroll/reduce/zero writes/auth/browser/process cleanup PASS,
  baseline DOM2/760/437→все20close2/714/435 —strict DOM gate FAIL.
  Native V11 private root+peer static CLEAR, runtime NOT RUN. Новый bounded
  pre-warmup wait доказывает только settled/not-refetching Dashboard/Story UI,
  не successful data queries; solewarmup/exact20/DOM/heap/cleanup сохраняются.
- Push V4/V5 FAIL до browser на Mounts representation, оба exact-owned extra
  containers удалены. V6 root+peer CLEAR добавляет bounded true tmpfs mountinfo
  check; runtime NOT RUN. Historic education0/12 permission denied остаётся,
  real all-five-topic Push открыт; не grant/requestPermission/mock subscription.
- LHCI V12 candidate-v2 static CLEAR, runtime NOT RUN; fresh seed/readiness/
  cookie/source/state mandatory,21reports/7routes×3/cleanup unchanged.
  Paired S3V6 ACL/read-probeV3 static CLEAR, avatar fixtureV3 reviewed;
  actual isolated DB/S3 snapshot/restore/object read NOT RUN.
  -63 audit IDs исторически60 CLOSED/2 DECLINED/1 OPEN(BE-02),21 P0/P1 source/test
  review без нового дефекта; не full runtime certification. Exact3382/3383
  dismissals DONE. Native key rotation/Rust signing и deployedBE02 не сертифицированы.
- Root private operators/receipts:
  `C:\Temp\ue-mvp-root-20261009-7013fd5453f545c4bdf6abc7f24736c7\rootreceipt`.
  Frozen executed candidate bytes не перезаписывать. Для будущего clean SHA
  обновлять только caller binding/fresh proofs, проверяя individual source pins.
  Старые proofs не переносить cross-SHA/state и prepared не считать PASS.

Не повторять уже integrated inventory/hook/semantic/upload/auth/SSR/navbar/
membership/Q1/Q4/Events/browser-free fixes. Root prior Python1286/1286 и Events
41/41 scoped100% относятся к соответствующему source; unaffected backend не
повторять без нового основания. Historical full89 FAIL76/114/8 и aborted14c2
cleanupUNCONFIRMED сохранить; superseded Core14c2/df/89/dd/f14/cce5 уже удалены.

Ближайшее действие: verify ordinary successor hooks/commit/push/CI → новый clean
Core/readiness/admin-only seed/Home comparison/SEC-03/demo seed → affected specs →
два consecutive full. Каждый full:190 PASS+exact8 source/project expected skips,
failures/flaky/interrupted/did-not-run0. Затем оставшиеся real auth/MFA/WS/Push,
Native Stories, visual packets/approvals/LHCI/JS<500KB, stop/start persistence,
security/data/paired restore, frozen-RC full smoke и ordinary release.

После teardown RAM44,98%/free17,50GiB; static peak52,11%/minimum free15,23GiB.
После отмены дополнительного coverage RAM35,93%/free20,38GiB.
Последний account refresh20% weekly consumed/80% remaining, ordinary usage allowed.
Stopped capped builder/cache сохранить; перед каждым workload измерить заново.

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
