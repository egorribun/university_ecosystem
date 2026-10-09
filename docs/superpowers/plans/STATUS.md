# MVP — оперативный статус

Срез на 2026-10-09 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md) — единственный
действующий план; [ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые границы,
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) — переход качества.
Исполнение возобновлено поручением владельца 2026-10-09; аудит подготовки сохранён.
Выпуск `v1.0.0` пока не подтверждён.

## Решения владельца и ближайший результат

- Работа строго на `egorribun`, один checkout и
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
- Кратчайший путь: Q1/Q4 → Core/product/visual/security/restore → full smoke →
  обычный merge → main checks → готовый producer шести GHCR images → release.
  Независимые исправления идут параллельно; агенту 30 минут до контрольной точки.
- Q1 и весь Q4 обязательны до MVP: мутации, Schemathesis, DAST, chaos,
  full Chromium/Lighthouse, cross-browser и kind переходят в scheduled/manual.
  Live Chromium smoke, security и fail-closed оставшиеся checks сохраняются.
  Source diff проверен локально; commit/push и hosted подтверждение ещё впереди.
- Tier 0 — 100%; остальные действующие coverage floors также сохраняются до Q3.
  Если они блокируют MVP, перенос Q3 согласуется отдельно. Q2/Q3 — `v1.1`.
- Полный mutation score, три сопоставимых полных CI-прогона, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — `v1.1`; готовую оснастку сохраняем.
  Один согласованный изолированный DB/S3 restore обязателен для MVP.
- ГУУ остаётся брендом внутреннего демо; данные синтетические. Публичное
  использование решается отдельно. Помещения/вместимость — после MVP.
- Без embeddings key текстовый поиск работает; UI semantic mode выключен,
  direct semantic-only API сообщает о недоступности без нулевых векторов.
- Разрешено снять 14 contexts ruleset 8335285 и отдельно `Security Audit / Semgrep SAST`
  после reviewed diff и проверок: 91 → 76; CodeQL и остальные правила сохранить.
- ADR-006: сохранить durable tombstone/WS revoke до commit; rollback может
  консервативно разлогинить sibling sessions; local failure paths PASS, live открыт.

## Текущий refresh и аудит подготовки

- Refresh source: `851c4763ff431232cc4bf3cbfc416823bfd0fce3` = origin/egorribun;
  main/merge-base `6fa133b57f62c554162876d4e6d8349f8060fce9`, divergence0/1267.
  PR1306 OPEN/BLOCKED; дерево на старте чистое. Работа Q1/Q4, backend и
  dependency/traceability назначена трём GPT-6 Luna Max, Git принадлежит root.
- Matrix `37848498285/a1` на refresh SHA CANCELLED root после сохранения snapshot:
  111 завершённых jobs, 72 незавершённых mutation jobs; inventory SUCCESS,
  Node audit FAILURE. Handlebars4.7.10: local npm audit/graph/policy PASS.
- Owned Live `37848497910/a1` на refresh SHA: SUCCESS,18 PASS/2 planned skips,
  artifacts0. Smoke остаётся auth/reset, полная Core traceability ещё открыта.
  Упоминание `--stack core` в contract output не доказывает выбор Core при `up`;
  tracked workflow нуждается в явных stack/state-dir и отдельном full smoke.
- Fresh ruleset8335285 ACTIVE,91 contexts; разрешённые14+1 ещё не удалялись.
  Владелец явно одобрил Semgrep de-dup: CodeQL blocking, Semgrep pre-commit.
  Q1/Q4 и бюджет15 минут пока не подтверждены hosted evidence.

- [Readiness audit](../../audits/MVP_READINESS_AUDIT.md) и
  [промпт нового чата](NEXT_SESSION_PROMPT.md) подготовлены на исходном `2a042124`.
  Последующий handoff commit сверить через Git; старые runs не сертифицируют его.
- R02: точные hook source bindings, bounded fixtures и inclusion authored hooks
  в inventory исправлены; независимый review CLEAR; focused165 PASS, inventory0.
- Завершающий preflight10/10 PASS; link module9 PASS, оба link-checker режима
  436/0, Markdownlint10/0, configured CSpell9/0. Это не release certification.
- Hosted Live `37843216072/a1` на `2a042124`: SUCCESS,18 PASS/2 planned skips,
  artifacts0; это auth/reset PR smoke, не full Core/TЗ приёмка.
- Matrix `37843217306/a1`: наблюдались Node dependency audit и inventory failures.
  Inventory исправлен локально; новый hosted результат ещё требуется.
  Npm policy RED этого SHA устранён в текущем source diff; hosted rerun нужен.

## Подтверждённая контрольная точка до изменения политики

- Source checkpoint: `7ddc114b72f346ff27bd6dd6d83e191eb7f89412`, отправлен в remote.
  Новый policy commit: `60a886529c6e89176e2d53395268ca6279805cb4`.
  Старые результаты ниже подтверждают свои SHA, а не текущий release candidate.
- Planner cost cache: RED 24 conversions вместо 4 → GREEN; root317 PASS и
  5 subtests. Synthetic512/128 планы идентичны; global score не получен.
- Browser cache override: validated private pinned Playwright browser работает;
  live CLI1164 tests PASS. Workflow snapshot contracts26/26 PASS после исправления.
  Preflight10/10, staged hooks и push прошли на checkpoint.
- Hosted Live `37767058529/a1` на `460501`: SUCCESS, 18 passed/2 planned skips,
  flaky нет. Uploaded artifact отсутствует; evidence — API/job/redacted stdout.
- Matrix `37767059576/a1` на `460501`: backend shard1 FAILED на трёх stale
  workflow assertions, 4189 passed/18 skipped. Локальное исправление принято;
  новый hosted результат и обязательный зелёный набор ещё нужно подтвердить.
- Profile Core acceptance на `15ad90aac`: 4/4 PASS, validation/save/reload.
  Исторический stop/start smoke на `444ed`: 18 PASS/2 planned skips,
  hashes/secret files/volumes совпали. Полная продуктовая traceability открыта.
- Core на `460501` поднялся, E2E не начат из-за RAM85,4%/free4,63 GiB.
  Stop/teardown PASS; проверенные owned containers/volumes/networks/image tags0.
  Shared base images/build cache сохранены; global prune не применялся.
- Private checkpoint receipt:
  `C:/Temp/ue-quality-session-dm-root-20261008-82730e4856e54ecbb944e5fa90cc3110/checkpoint-7ddc114b-v1.json`.

## Сохранённые начатые направления

- Подготовка harness: verifier изолирован от real gate state; shared loader/lock,
  atomic write и per-file latest map сохраняют failures; malformed JSON и timeout
  fail closed. Все Go modules обнаруживаются, max2 workers/shared95s budget.
  Profiles согласованы с одним checkout/root Git/30-minute checkpoint.
- На предыдущем harness checkpoint verifier28/28, runtime/Stop44/44, preflight10/10,
  live contracts154/154 PASS; real gate state hash неизменен после проверок.
  Старый OwnedLive `37839467416/a1` на `a01e572b5` упал до Docker на двух
  stale plan-wording assertions; они исправлены, свежий smoke указан выше.
- Known P2: Windows timeout cleanup через `taskkill /T` не гарантирует завершение
  descendant, если родитель уже вышел и оставил inherited pipes. В этом случае
  cleanup failure явный, PASS нет; полную Job Object containment отнести в backlog.
  Нативная Codex registration отсутствует; Antigravity hooks вызываются явно.

- Mutation diagnostic: frontend inventory43200, viable88,7101%; backend
  universe54450, complete global score отсутствует. Это debt/baseline,
  не MVP допуск. Полные очереди ради 100% теперь не запускаются.
- Kind K3 helper на `727eecab`: controllers/CA/create/prepare/repeat/preflight/
  smoke/teardown PASS, inventory20 и Helm revisions1 неизменны.
  Приложение не развёрнуто; chart/routes parity и полная приёмка — `v1.1`.
- DR на `76cd4026dbe241f9a57b7f98488f54856f6b37d9`: paired snapshot создан,
  executor остановился на `source_snapshot_gate`; target restore НЕ НАЧИНАЛСЯ.
  Logical restore, DB/S3 связность, RPO/RTO не подтверждены. Неудачные
  immutable diagnostics/receipts сохраняются без заднего изменения outcome.
- Manifest-aware backup/restore CLI/runbook и BE-02 preflight/tests реализованы;
  наличие кода не подтверждает deployed restore/upgrade/rollback.
- Six-image main-only producer и source-bound release consumer реализованы;
  signing/SBOM/provenance/WASM parity сохраняются. Публикация текущего релиза
  и проверка его main SHA/run/attempt/manifest/digests ещё предстоят.

## Открытая MVP-приёмка

- Q1/Q4: 20 модулей/402 PASS до Semgrep; затем 428 PASS и scoped rerun 1 PASS;
  catalog 59/183, actionlint PASS. Перенос не подтверждён hosted/default branch.
- Fresh preflight 10/10 PASS (337 contracts); live CLI/Core: 1189 PASS.
  PowerShell: 16 PASS/1 platform skip, peer CLEAR; Core runtime ещё не запускался.
- Schedule/semantic regressions PASS; root vector/adjacent mocks 82 PASS;
  unused event analytics удалён после проверки потребителей. Auth fail-closed
  review: 74 PASS; durable email-change tombstone failure paths PASS.
- SEC-03 writer/verifier/root/sequence fix: 98 focused и root221 adjacent PASS;
  nullable/delimiter trust metadata: 112 PASS, peer review CLEAR. UI7 PASS.
- ТЗ2–13: актуальные Core auth/MFA, messenger/group delivery, push,
  profile/settings, admin permissions, SSR/PWA/i18n, RU/EN и a11y.
- Visual approval: light/dark, 390/768/1440 px, targeted360/1024;
  Linux baselines, bundle budget, Lighthouse, stories20 cycles/reduced motion.
- Независимый auth/session/data review и ADR-006 tombstone-first ordering;
  все63 audit ID классифицировать; P0/P1 security нельзя переносить молча.
- Один backup/restore в отдельные DB/S3 targets с чтением восстановленного
  объекта через DB reference. Затем frozen RC и один full release smoke.
- Q1/Q4 должны обновить triggers/dependencies/results/assertions/catalog/
  release requirements/contracts вместе. Целевой PR бюджет15 минут ещё не измерен.
  Scheduled/manual lanes требуют default-branch activation; наличие workflow
  в `egorribun` не доказывает их работоспособность на `main`.

## Ресурсы и сохранность

- Один heavy workload: перед стартом RAM≤75%, free≥8 GiB;
  runtime guard85%/4 GiB. Следующий запуск требует свежего измерения.
- Удалять только доказанно принадлежащие нам ненужные Docker ресурсы;
  пользователь разрешил удаление synthetic ue-live данных. Чужие env/data/
  volumes/backups/processes сохраняются. Worktree не создавать.
- Git history/migrations/private rescue bundle сохраняются. Исторические
  session logs и superseded snapshots не возвращать в текущие индексы.
- Goal текущего чата ACTIVE; paused goal из audit относится к прежнему чату.
