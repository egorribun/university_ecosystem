# Итоговый аудит готовности к продолжению MVP

Срез: 2026-10-09, Europe/Istanbul. Исследованный исходный SHA:
`2a042124e7fba7ec28b7ca010730430a50915d6d`, ветка `egorribun`,
[PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
Аудит проверяет готовность следующей рабочей сессии. Он не заменяет
продуктовую приёмку, security certification или release evidence.
Единственный действующий план — [мастер-план](../superpowers/plans/MVP_MASTER_PLAN.md).
[Промпт следующей сессии](../superpowers/plans/NEXT_SESSION_PROMPT.md) передаёт
поручение исполнителю; [STATUS](../superpowers/plans/STATUS.md) хранит текущий срез.

## Вердикт и границы доказательства

Работу можно продолжать по единой траектории: факты, права, ограничения,
области записи агентов и ближайшие задачи определены. Заявление «всё готово
к выпуску» было бы неверным: Q1/Q4 не внедрены, есть текущие failures CI,
подтверждённые продуктовые дефекты и незавершённая live/visual/restore приёмка.

Проверены Git/PR/remote, действующая документация, ADR и quality contracts,
harness и его регрессии, ключевые backend/frontend entrypoints, CI graph,
main ruleset, dependency findings, Compose/live ownership, ресурсы, сохранность
архивного rescue bundle и draft patch, producer/consumer release chain.
Три независимых GPT-6 Luna Max проверили backend/auth/data, frontend/live и
CI/infra; root перепроверил выводы и выполнил локальные проверки.

Это аудит ключевых контуров с явно указанными проверками, а не построчный
анализ всех 1,522 изменённых файлов PR. Не запускались полный coverage matrix,
mutation workloads, новый live стенд, kind deployment, реальный DB/S3 restore,
новый security penetration test или публикация GHCR. Отсутствие подтверждённого
P0 в таком обзоре не доказывает отсутствия всех уязвимостей.

## Проверенная основа

| Контур | Наблюдение | Значение для продолжения |
| --- | --- | --- |
| Git | На входе дерево чистое; HEAD = `origin/egorribun` = исследованный SHA. Один checkout, одна рабочая ветка, один открытый PR | Новый исполнитель не должен интегрировать старые WIP/worktrees повторно |
| Main/ancestry | `origin/main` и merge-base: `6fa133b57f62c554162876d4e6d8349f8060fce9`; divergence `0 / 1266` | Main является предком; новый merge main на этом срезе не нужен |
| PR | OPEN, MERGEABLE, merge state BLOCKED; 1,522 файла, +168,283/−115,086 строк | BLOCKED — проверки/правила; весь большой PR нельзя считать принятым по одному green preflight |
| План | Один master, ТЗ, STATUS и ADR-047; старые approved/release plans и архивные каталоги отсутствуют | В новой сессии прочитать канонические файлы; не применять исторические промпты как новые поручения |
| Качество | Tier 0 и нынешние floors/100% patch сохраняются до отдельно согласованного Q3 | Q1/Q4 снимают blocking mutation/heavy execution, а не coverage/security защиту |
| Harness | Изолированный verifier; shared lock/loader; atomic state; per-file failures; malformed state/timeout fail closed | Проверки не сбрасывают реальную историю ошибок; Antigravity hooks требуют явного запуска |
| Агентные профили | Пять ролей описаны; реальных исполнителей максимум три GPT-6 Luna Max | Профиль не является запущенным процессом; root назначает файлы и выполняет Git |
| Runtime | Python 3.14.7, Node 24.21.0, npm 11.17.0, uv 0.11.28; локальный Go 1.27.1, Rust 1.98.1 | Локальные Go/Rust отличаются от CI pins 1.26.6/1.97.1; нельзя выдавать локальный результат за canonical parity |
| Ресурсы | 20 logical CPU; в одном снимке RAM used49.5%, free16.06 GiB; Docker 16 CPU/23.47 GiB; WSL24 GiB + swap8 GiB; диск C free230.45 GiB | Перед каждым heavy workload измерить снова; один heavy процесс, guards75%/8 GiB → 85%/4 GiB |
| Docker | Контейнеров0; images60, volumes18, build-cache740 records; named Go caches4, anonymous volumes14 | Активных стендов нет; без доказательства владельца анонимные тома не удалять. Не объявлять весь диск очищенным |
| Browsers | Chromium/headless1243 и FFmpeg установлены; Firefox1543/WebKit2359 в стандартном cache не найдены | Для актуальной MVP live приёмки Chromium доступен; private override и executable надо сверить перед запуском |
| Архивная история | Rescue bundle172,738,568 bytes и CSV62,877 bytes присутствуют; SHA-256 совпадают с audit index | История сохранена; bundle остаётся приватным, не копировать, не публиковать и не восстанавливать для routine работы |
| Draft | Schedule patch4,176 bytes присутствует, SHA-256 совпадает | Это черновик, не интегрированный fix; при отсутствии на другой машине RED можно восстановить из контракта |
| GitHub/MCP | GitHub read/API и push контрольной точки работали; инструменты доступны по фактическому каталогу | Доступность инструмента не подтверждает доступ к каждой внешней учётной записи или GHCR публикации |
| Выпуск | Main-only producer и release consumer связывают SHA, run/attempt, manifests/digests/signatures/SBOM/provenance | Сохранить готовую цепочку. Наличие исходников не подтверждает выпуск `v1.0.0` |

## Свежие проверки и их пределы

Protected local receipts:
`C:/Temp/ue-readiness-audit-20261009-33d9ff10be5e4874b697c5273d241367/`.
Каталог ограничен текущим пользователем и SYSTEM; значения secrets не публикуются.
Время запуска preflight в receipt — UTC; дата этого отчёта использует Europe/Istanbul.

| Проверка | Результат на исходном SHA | Что она не доказывает |
| --- | --- | --- |
| `python scripts/fast_preflight.py --max-workers 2 --report <private>/preflight.json --include-output` | 10/10 PASS, 98.829 s; focused contracts375 PASS; verifier28/28 | Нет полного coverage, mutation, inventory execution или браузерного/live допуска |
| `pytest tests/test_harness_hook_runtime.py tests/contracts/test_stop_quality_gate_contract.py tests/test_markdown_links.py -q -o addopts= --basetemp <private>/pytest-focused` | 53 PASS, 9.52 s; state hash неизменен | Mocked dispatch не является настоящим запуском всех toolchains |
| `scripts/docs/check_markdown_links.py` и `--include-archives` | 434 Markdown files, broken links0 в обоих режимах | Не проверяет доступность внешних URL и правдивость текста |
| `generate_test_inventory.py --output <private>/inventory.json` + `check_orphans_and_anti_patterns.py --inventory ...` | RED: 10 нарушений новых harness tests | Старый green preflight эту проверку не включал; исправление описано ниже |
| `npm --prefix frontend audit --json` | Exit1; critical1/moderate2, total3 affected packages | Это локальная база advisory; конкретную причину hosted job устанавливать по его log |
| `npm --prefix frontend explain handlebars` | `handlebars@4.7.9 dev` через `eslint-plugin-boundaries@7.2.0` и `@boundaries/elements@3.1.1` | Dev dependency не означает доказанный runtime exploit приложения |
| `scripts/audit_dependencies.py --allowlist security/audit-allowlist.yaml --npm frontend` | RED exit1: advisories1241676/1241677/1241678 вне allowlist | Точный локальный policy failure, не замена hosted log |
| `uv lock --check`; `npm --prefix frontend ls --depth=0 --json` | PASS: lock согласован, installed graph без missing/invalid problems | Установка не обновлялась; scanner gate остаётся отдельно |
| `node frontend/scripts/verify-wasm-artifacts.mjs` | PASS: artifacts и source provenance валидны | Нет новой canonical builder parity/compiled rebuild сертификации |
| `uv run --frozen --no-sync pytest tests/test_schedule_service_closure.py` | 3 PASS | Нет update-conflict regression |
| Два focused semantic tests | 2 PASS | Они подтверждают прежний zero-vector fallback, противоречащий новому решению |
| `live_stand.py status --in-place --state-dir <nonexistent-owned-run>` | Exit2, каталог отсутствовал до и после | Отказ без изменения файлов; это не readiness рабочего стенда |

## Актуальный CI и безопасность зависимостей

[Matrix `37843217306/a1`](https://github.com/egorribun/university_ecosystem/actions/runs/37843217306)
относится к `pull_request` и исходному SHA. На наблюдаемом срезе он не завершён.
Уже завершены с FAILURE:

- `113538896020` — `Security Audit / Node.js Dependency Audit`, шаг
  `Run npm audit with allowlist` в `reusable-security-audit.yml`. Annotation:
  обнаружены advisories вне allowlist. Package-level hosted log пока не получен.
- `113538762005` — `Source/Test Inventory & Anti-Pattern Check`, шаг
  `Verify Orphans and Anti-Patterns` (`ci.yml`). Предшествующие inventory,
  model-default и catalog steps прошли. Локально воспроизведены десять нарушений.

Нельзя приписать hosted failure конкретный advisory только по локальному npm
audit или объявить новый CI green после локального исправления. В следующем
чате получить итоговые logs/results по точному run/attempt, не запускать дубликаты.

[Owned Live `37843216072/a1`](https://github.com/egorribun/university_ecosystem/actions/runs/37843216072)
на исходном SHA завершился SUCCESS: job113537546170, **18 passed/2 planned skips**,
без failed/flaky/interrupted/did-not-run. Skips — cross-project условия двух
localized rejected-login cases; auth-roles и password-reset на desktop/mobile
дают20 total cases. Это узкий PR smoke, не полный Core/TЗ result. Artifacts0;
protected log SHA-256
`071316da2d1e78fc8041e634be9179bb445a143f4feb43e1dca64360c6b3f001`.
[Performance `37843216466/a1`](https://github.com/egorribun/university_ecosystem/actions/runs/37843216466)
также завершился SUCCESS на этом SHA; не подменяет visual approval или full CI.

В текущем lock есть `handlebars@4.7.9` в dev graph. Maintainer advisories
[AST type confusion](https://github.com/handlebars-lang/handlebars.js/security/advisories/GHSA-8r5x-fm3f-whwj),
[own property check bypass](https://github.com/handlebars-lang/handlebars.js/security/advisories/GHSA-p8wg-vrv2-v86f)
и [unsafe embedding](https://github.com/handlebars-lang/handlebars.js/security/advisories/GHSA-xw65-4hp5-5hc7)
указывают patched version4.7.10. Следующий dependency fix должен доказать
совместимость plugin/lock и пройти audit/lint; не применять предложенный npm
downgrade или добавление allowlist автоматически ради зелёного результата.

Dependabot API для default branch показывает33 open alerts:
critical1/high13/medium15/low4. Они относятся к `main`, а не автоматически к PR.
Critical PyJWT #179 касается `<=2.13.0`; в PR `uv.lock` уже2.15.1.
Аналогично ряд npm ranges исправлен в PR. Сопоставить все findings с точным
release lock/SBOM; не считать либо все33 актуальными уязвимостями PR, либо все
закрытыми по исправлению одного пакета. Alert closure — только после выпуска
исправленного источника и проверки принятой процедуры.

## Открытые обязательные результаты

Здесь P1 означает подтверждённый дефект или обязательный незакрытый результат
MVP. Эту метку нельзя смешивать с доказательством эксплуатируемой P1 security
уязвимости; предметная категория указана отдельно.

| ID | Категория/приоритет | Факт и следующая проверка |
| --- | --- | --- |
| R01 | CI/security dependencies, P1 | Hosted npm audit красный; local critical Handlebars подтверждён. Исправить зависимость и совместимость без необоснованного exception |
| R02 | Подготовка/inventory, P1; локально закрыт | Исходно orphan1 и bounded sleep findings9. Точные authored hook bindings, bounded fixtures и inventory discovery исправлены; focused165 PASS, inventory0, review CLEAR. Новый hosted результат требуется |
| R03 | Q1, обязательная работа | Backend mutmut и Stryker64 shards остаются в PR/main execution graph и `CI Success`; убрать весь blocking graph, сохранив nightly/manual |
| R04 | Q4/required contexts, разрешённый ограниченный этап | Тяжёлые lanes и14 прямых ruleset contexts противоречат переносу. Владелец разрешил точечное снятие после готового reviewed CI diff и проверок; общий protection bypass запрещён |
| R05 | Schedule, P1 product correctness | `ScheduleService.update_schedule` не проверяет conflicts. RED на partial update, self-exclusion и no-op; конфликт не должен обновлять repo/audit/commit |
| R06 | Semantic API, P1 product contract | Отсутствующий key/provider даёт zero vector; direct endpoints могут вернуть cached304 до доступности embedding. Проверить unavailable до cache/vector path; text search сохранить |
| R07 | MFA/auth, security review | Код и ADR-006 используют tombstone → Pub/Sub → DB commit. Противоречие master устранено решением сохранить tombstone-first; route-level failures/live revoke/current-session preservation ещё проверить |
| R08 | Core/live completeness | PR workflow запускает defaultfull, smoke только auth/reset; требуется Core, seed/repeat/stop-start и два продуктовых прогона на неизменном RC |
| R09 | Traceability | Наличие live specs не связывает весь ТЗ2–13 с outcome/evidence. Для каждого требования нужен сценарий, допустимый метод проверки, SHA и факт выполнения |
| R10 | Visual/performance/a11y | Пять Win32 snapshots; Linux baselines и owner approval отсутствуют. Есть instruments/specs, но это не lab measurements и не acceptance |
| R11 | Data/restore | Последний paired snapshot остановился на source gate, target restore не начат. Один реальный isolated DB/S3 restore с чтением объекта по DB reference обязателен для MVP |
| R12 | Audit ledger | 63 ID: historical CLOSED60/DECLINED2/OPEN1(BE-02). Полной revalidation на RC нет; deployed BE-02 вынесен вv1.1, это надо корректно отразить в release classification |
| R13 | Release | Frozen RC/full smoke/required PR/main checks/шесть новых images/tag отсутствуют. Сохранить signing/SBOM/provenance и exact-source evidence |

MFA/current-session сохранность и реальные group/WS revoke paths проверять
независимо. Tombstone failure должен fail closed; Pub/Sub failure не должен
воскрешать credential. Консервативный logout siblings при последующем rollback
не скрывать. Нельзя перенести security риск только из-за переноса performance
или mutation gates.

## Приложение: точный proposal для Q1/Q4 и protection

Read-only snapshot: main ruleset8335285, enforcementACTIVE, required contexts91.
До изменения CI получить/сверить свежий ruleset. Ниже14 существующих contexts,
затронутых вариантом «PR Chromium smoke; full browser/LHCI/heavy scheduled/manual»:

| Этап | Exact context |
| --- | --- |
| Q1 | `Incremental Mutation Tests (frontend)` |
| Q4 | `E2E Tests (shard 1/4) / E2E Tests (chromium)` |
| Q4 | `E2E Tests (shard 2/4) / E2E Tests (chromium)` |
| Q4 | `E2E Tests (shard 3/4) / E2E Tests (chromium)` |
| Q4 | `E2E Tests (shard 4/4) / E2E Tests (chromium)` |
| Q4 | `Frontend Tests / Lighthouse Audit` |
| Q4 | `Frontend Tests / Lighthouse Audit (content)` |
| Q4 | `Frontend Tests / Lighthouse Audit (core)` |
| Q4 | `Frontend Tests / Lighthouse Audit (fallback)` |
| Q4 | `Frontend Tests / Lighthouse Audit (realtime)` |
| Q4 | `Schemathesis - API Schema Conformance` |
| Q4 | `Chaos Loadtest Orchestrator` |
| Q4 | `SQLMap Scan` |
| Q4 | `TruffleHog Scan` |

Cross-browser и `chaos-tests` дополнительно входят в `CI Success`, но отдельных
прямых contexts для них snapshot не содержит. Синхронизировать workflow `needs`,
result arrays, event assertions, summaries, catalog, release requirements и
contracts. Не выпускать fake-green compatibility check взамен снятой защиты.
Сохранить `CI Success`, coverage policy, Gitleaks, CodeQL, оставшийся security
audit, migration и supply-chain gates. Нешардированные Python и frontend unit
contexts имеют реальные агрегирующие emitters; их не удалять как «старые».

`Owned live acceptance (pull_request)` сейчас не required. Повышение — после
трёх последовательных успешных smoke и измерения ресурса/бюджета; не включать
его обязательность раньше. Scheduled/manual activation требует workflow в
default branch по [официальным правилам GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

Владелец 2026-10-09 подтвердил перенос четырёх full Chromium shards и LHCI в
scheduled/manual с сохранением PR live smoke и полных сценариев. Он прямо
разрешил убрать только перечисленные14 contexts после готового CI diff и его
проверки; остальные правила сохранить. Новые/другие contexts не входят в это
разрешение. Настройки в этом аудите не менялись; operational closure Q1/Q4
остаётся открытым. Master/ADR/AGENTS/continuation prompt согласованы с решением.

Для MFA владелец поручил выбрать «лучший вариант». Root выбрал сохранение
существующего ADR-006 tombstone-first boundary: защищённый отказ прежде DB
commit с документированным conservative sibling logout при rollback.
Новую post-commit delivery архитектуру до MVP не вводить; security acceptance
остаётся отдельным обязательным результатом.

## Исправления подготовки в этой контрольной точке

- `TESTING.md`: каждый `--in-place` вызов получает тот же уникальный
  `--state-dir` под Python temp/`ue-live-acceptance/run-*`; acceptance использует
  `live_stand.py e2e` с owner/endpoints/ephemeral-credentials validation.
  `status` не создаёт отсутствующий каталог. Docker startup этим аудитом не запускался.
- Master: старые bullet-поручения deployed BE-02 и RPO/RTO явно помечены `v1.1`,
  чтобы они не восстанавливали отменённое обязательство MVP. Scope не расширен.
- Harness/inventory: R02 исправлен точными source bindings, ограниченными
  timeout/contention fixtures и discovery только authored hook Python files.
  Skills, agent metadata, runtime state и caches не индексируются. Новых
  allowlist/exclusions нет; quality contract и coverage floors не менялись.
  Новая inventory regression сначала RED, после исправления focused165 PASS;
  свежий inventory7000 records, authored hooks5, violations0. Независимый review
  CLEAR по четырём зафиксированным файлам; reviewer тесты повторно не запускал.
- Новый continuation prompt и этот snapshot сохраняют самостоятельную роль;
  они не создают второго master plan или нового quality harness.

## Завершающая локальная проверка кандидата

После подготовительных исправлений на рабочем дереве исходного `2a042124`
получены результаты ниже. Receipt хранит этот base SHA; последующий Git commit
связывает принятый diff. Эти проверки не являются release evidence нового SHA.

- Final preflight: **10/10 PASS**, max2 workers, 95.531 s; focused contracts375
  PASS, verifier28/28. Receipt `preflight-final.json` в защищённом каталоге выше,
  SHA-256 `b7b9f17e924377acdab9447aa5aaa471ce81ec538f9274145ee4bd44b0ea1212`.
- Harness/Stop/inventory modules:165 PASS. Root расширил запуск link tests;
  единственный документальный failure был ссылкой на ещё untracked audit.
  После включения новых документов в index весь link module:9 PASS.
- Свежий `inventory-handoff.json` и checker:PASS, violations0. Оба режима
  Markdown link checker:436 files, broken0. Markdownlint:10 changed docs/0;
  CSpell:9 configured English docs/0. Gates/exclusions не ослаблялись.
- Повторный read-only review нашёл старые imperative bullets harness/R02 в
  master. Они заменены завершённой контрольной точкой и проверкой только новых
  failures; новый исполнитель не получает задания повторить принятый fix.
- Последнее наблюдение Matrix всё ещё `in_progress`, pending1, с двумя failures
  на исходном SHA; PR `OPEN/MERGEABLE/BLOCKED`. Новый handoff CI ещё не запускался.
- Контейнеров0; последняя RAM50.1%, free15.86 GiB. Подготовительные проверки
  не запускали новый стенд, kind или release producer и не меняли ruleset.

## Сохранность, ограничения и следующий старт

Gate-state SHA-256 до/после проверок:
`349452a4d316f17db9a56055cc028f21d4ff3e00efb8d5ea9dbeea57c31d6f7f`.
Историю failures не сбрасывать ради Stop. Known P2 Windows: если parent вышел,
а descendant держит inherited pipe, `taskkill /T` не гарантирует containment;
cleanup-unconfirmed выдаёт failure. Native Codex registration отсутствует:
`.agents/hooks.json` использует Antigravity protocol, что не заменяет
[Codex hook registration](https://developers.openai.com/codex/hooks/).

Chromatic отключён billing gates/skip: true; платный запуск и покупка не нужны.
Ротация исторического project token подтверждена пользователем; seeded-admin
password и исторический signing-key default относились к ephemeral CI/demo.
Secret values, старые архивные примеры и bundle не переносить в prompt/artifacts.

При старте: прочитать canonical docs; освежить HEAD/main/PR/CI/resource snapshot;
сначала закрыть R01 и finish Q1/Q4 contracts, параллельно schedule/semantic
fixes и acceptance traceability. Root один интегрирует и пишет Git; другие
агенты получают disjoint file ownership. На live SHA исходники заморозить,
agent work переключить на review. После Core/visual/security/restore — frozen
RC full smoke, ordinary merge и main-only producer/release.

В текущем чате goal остаётся `paused`. Его прежний objective включает v1.1
сертификацию; доступный API не умеет редактировать objective или resume.
Не объявлять старый goal complete по одному выпуску MVP. Новый чат получает
обновлённое поручение из prompt и проверяет свои доступные goal tools.
