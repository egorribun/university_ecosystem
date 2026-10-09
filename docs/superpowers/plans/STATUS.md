# MVP — оперативный статус

Срез на 2026-10-09 (Europe/Istanbul).
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ MVP](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Выпуск `v1.0.0` не подтверждён; goal этого чата ACTIVE.

## Решения и порядок

- Строго `egorribun`, один checkout, существующий
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root управляет Git; до трёх GPT-6 Luna Max с раздельным ownership.
- Q1/Q4 → Core/product/visual/security/restore → frozen-RC full smoke →
  обычный merge → main checks → существующий producer шести GHCR images → release.
- Q1/Q4 обязательны: тяжёлые lanes scheduled/manual на default branch;
  живой Chromium smoke и fail-closed security/quality gates сохраняются.
  Tier 0 — 100%; прочие coverage floors сохраняются до Q3.
- Владелец разрешил исходные14 readiness-audit contexts и отдельно ровно один
  `Security Audit / Semgrep SAST`: ruleset8335285 изменён91 →76 после review/checks.
  Остальные rules/contexts сохранены; CodeQL blocking, Semgrep в pre-commit.
- Q2/Q3, полный mutation score, три сопоставимых CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — `v1.1`. Один согласованный DB/S3 restore
  с чтением объекта production storage по DB reference обязателен для MVP.
- ADR-006: durable tombstone/WS revoke до commit; rollback может консервативно
  разлогинить siblings. Local failure paths PASS; runtime guarantee открыта.
- ГУУ — внутреннее демо; данные синтетические. Публичный бренд решается отдельно.
  Без embeddings key текстовый поиск доступен, semantic UI выключен,
  direct semantic-only API сообщает недоступность без нулевых векторов.

## Текущий checkpoint: опубликованныйddbbc84d и Home12 approval

- HEAD/origin/PR1306:ddbbc84d8444fa06aee1485fb1ddc0d1ca308d1f. Пакет owned
  live-session cleanup и navbar gap опубликован обычными hooks/commit/push;
  pre-push typecheck PASS, `.secrets.baseline` повторно staged, checkout был чист.
- Fresh Core ddbbc84d up/readiness PASS:23 services,14 healthy checks,
  завершённые init jobs, функциональные Mailpit/Redis probes и signed ports.
  Admin-only seed сохранил пустые Home feeds до screenshots.
- Новый Linux Home-empty packet:12/12 RU/EN × light/dark ×390/768/1440,
  loaded Morph cards visible/settled, serious/critical axe0, exact-session
  cleanup complete. Владелец явно утвердил пакет; единственное замечание
  RU/light/1440 к расстоянию карта кампуса → Messenger закрыто.
  Одобренные12 PNG сохранены byte-for-byte в
  `frontend/visual-baselines/live/home-empty/` с curated approval/SHA-256 metadata;
  это manual comparison baseline, отдельный от mocked Windows snapshot test.
- Exact-head CI snapshot14:10 UTC:67/76 required SUCCESS,1 FAILURE,
  2 in progress,6 absent. Matrix37940158490/a1 ещё не завершён;
  advisory Owned Live37940157634/a1 также выполнялся. Это не current CI PASS.
  Единственный обнаруженный failure — Source/Test Inventory & Anti-Pattern
  Check113852193041: три ожидаемые строковые формы `test.skip(` в Python-тесте
  ошибочно приняты scanner за runtime skip.
- Minimal test-only correction меняет лишь сборку ожидаемой строки;
  scanner и все восемь source/project skip identities сохранены. В основном
  checkout13/13 выбранных skip contracts PASS; неизменённый CI checker и
  Ruff check/format PASS. Следующий commit должен опубликовать это исправление.
- Core ddbbc84d retired canonical owner-checked teardown: containers/networks/
  volumes0/0/0, source stable, owned children0. Первая попытка остановлена
  time guard180s при0/1/6; canonical resume завершился exit0 за24s. RAM guard
  не срабатывал. Private state/evidence сохранены; новый SHA требует нового state.
- Home approval закрывает только этот пакет12; остальные328 visual captures,
  current-SHA SEC-03, два full190+exact8, native stories20 cycles, restore,
  frozen-RC full smoke и обычный выпуск остаются открыты.

## Исторический checkpoint89cb50a4 и опубликованный следующий пакет

- Последний проверенный опубликованный ориентир до этого пакета:
  HEAD/origin/PR1306:89cb50a4e543ce6bcfc55082244343c82940c83f.
  Minimal membership contract correction опубликована обычными hooks/push;
  live-contract suite154/154 PASS. Пакет ниже подготовлен поверх него;
  его текущую публикацию и точный SHA сверять по Git/PR, без повторения исправлений.
- Matrix37922189757/a1 SUCCESS: exact-head join ruleset8335285 подтвердил
  все76 required SUCCESS, missing/duplicate/bad0. Advisory Owned Live37922189320
  SUCCESS — ограниченный hosted auth/roles/reset smoke, не полный Core.
  Matrix critical path41m16s; target15m открыт, backend cap2 сохранён.
- Core89 up/readiness PASS:23 services,4 initializer exit0,14 healthy checks,
  10 signed loopback ports. Admin-only seed выполнен один раз до Home;
  persisted SEC-03 PASS (API/PG row, canonical v2 signature fields, logout/same
  Bearer401). Key rotation и native signing этим не доказаны.
- Linux Home-empty V11:12/12 RU/EN × light/dark ×390/768/1440 технически PASS,
  содержимое трёх loaded Morph cards visible/settled, serious/critical axe0.
  Owner approvalfalse: единственное замечание RU/light/1440 — маленький отступ
  между картой кампуса и Messenger. Baselines не обновлялись.
- Canonical full Core run89:198 declared, passed76/failed114/skipped8 за30m29s,
  exit2/source stable/resource guardfalse, peak75,77%/free7,71 GiB,
  recorded owned children0. Это FAIL. Безопасные diagnostics не устанавливают
  причину всех114 ошибок. В fixtures найден server-session leak после закрытия
  browser context; reviewed cleanup добавлен без изменения auth cap и logout
  limiter5/minute per user/path. Фактический burst429 не доказан; fixture
  отклоняет его без retry и сохраняет исходную ошибку теста.
- Read-only session-count diagnostics не дали допустимых counts. Последний
  operator подтвердил owner/source/compose inventory unchanged, но child_failed;
  query rollback не подтверждён. Причина исторических114 failures не доказана.
- Core89 retired canonical owner-checked teardown: exit0/source stable,
  containers/networks/volumes0, recorded owned children0; private state/evidence
  сохранены. Следующий SHA требует нового уникального Core state.
- Native full Chromium153 direct-CDP capability V3 PASS:3/3 настоящих
  hidden/visible cycles, same window/context, requests0, no OOM/guard,
  owned process group empty/profile removed, exact container удалён.
  Это credentialless capability;20 actual Story Viewer cycles ещё открыты.
- Reviewed navbar gap/long-name fix и loaded-dashboard capture gate применены:
  navbar29/29 PASS, UserMenu/DesktopNav100% line/statement/branch/function;
  visual collector contracts19/19 PASS. Новый source-bound Linux packet,
  owner approval и hosted gate для следующего commit ещё нужны.
- Итоговые scoped проверки пакета: полный tests/test_live_stand.py1234/1234
  PASS за2m24s,0 failures/errors/skips; Node live contracts155/155 PASS за7s;
  семь постоянных Vitest behavior cases PASS. Они проверяют exact new token,
  CSRF/nonce, same-Bearer401, закрытый context, ошибку dashboard assertion,
  unchanged/ambiguous token,429 без retry и сохранение primary error/scope reset.
- Fast preflight пакета сначала8/10 за84s: lint/format нового fixture исправлены
  с переносом final throws за finally и обычным форматированием. После final
  test transfer frontend-typecheck/lint/format rerun3/3 PASS за35s; восемь
  проверок исходного preflight также PASS. Source stable/guardfalse/owned
  children0. Ruff check/format Python paths PASS. Затем обычные hooks/commit/push
  пакета прошли наddbbc84d; новый exact-head CI описан выше.
- Source accounting198 =190 применимых cases +8 ожидаемых project-axis skips;
  skips не считаются passes. Два успешных Core runs требуют190 PASS,
  exact8 ожидаемых identities,0 failures/flaky/interrupted/did-not-run;
  неожиданный skip не принимается. Finite runtime identity accounting реализован
  и unit-checked; full live run с ним ещё не выполнен.
- Same-run JUnit timing review подтвердил: cap2 suite-wall lower bound32m27s;
  одна перестановка shards не достигает15m. Private duration-map candidate не
  принят: proxy gain2,14%, shard3 header/testcase count mismatch5. Gates/cap2 сохранены.

## Сохранённый checkpointdf068410 (исторический срез)

- Пакет29 файлов опубликован обычными hooks/commit/push как
  `df068410c812737a7f592440cf2d6ced86035c84`; HEAD/origin/PR1306 совпали,
  checkout был чистым. Final local preflight10/10 относится к этому пакету.
- Свежий snapshot Matrix37917498689 и ruleset8335285: из76 required contexts
  68 SUCCESS,2 running,6 ещё не emitted; required failures0. Это промежуточный
  результат, не полный green. Advisory Owned Live37917498427 упал до Docker:
  source-code regex ожидал одиночный `await removedPage.reload()`, хотя scenario
  теперь перезагружает две revoked sessions через `Promise.all`. Minimal contract
  correction согласована с обеими sessions и обеими фазами revoke/reconnect.
  Полная существующая `npm run test:e2e:live:contract`:154/154 PASS за7,2s,
  exit0/guardfalse, file hash стабилен; scoped Prettier PASS. Обычная публикация
  следующего SHA ещё нужна. Это source contracts, не live product PASS.
- Позднее shard0/1 этого же Matrix прошли без failures: pytest17:35/17:12,
  4067/3601 cases,18/12 skips; обе JUnit artifacts привязаны к run/head/attempt.
  Shard2/3 ещё выполнялись. Testcase aggregate не равен wall time; target15m открыт.
- Fresh Coredf068410 поднялся за2m55s: exit0/source stable/guardfalse,
  peak69,4%/free9,73 GiB; bounded builder остановлен, recorded owned children0.
  Независимая read-only readiness PASS:23 services,4 initializer exit0,14 healthy
  checks,10 signed loopback ports; все23 container bindings проверены.
  Caddy200/backend ready+brief/Mailpit search200; owner/source/inventory стабильны.
- Этот пустой промежуточный Core удалён canonical owner-checked teardown:
  exit0,containers/networks/volumes0, private receipts/state сохранены,
  guardfalse/recorded owned children0. Admin/global seed, Home, SEC-03 и full198
  наdf068410 не запускались. Следующий clean SHA требует fresh unique state.
- Дополнительный Linux native-window probe:20 minimize/restore cycles в каждом
  из full Chromium headless и headed/Xvfb; hidden transitions0, requests0,
  browser/context закрыты, exact container удалён. Headless CDP bounds сообщали
  minimized, Xvfb readback оставался normal; ни один вариант не доказал native
  hidden state. Focus-emulation diagnostic подготовлена, actual run ещё нужен.

## Сохранённый checkpoint14c2 и исправления пакетаdf068410

- Опубликован `14c2f5ae179dbd2550f06d59bb77aacc742a0b7e` на `egorribun` в PR1306.
  Weather/bookmarks hydration package прошёл обычные hooks/push и preflight10/10.
- Matrix37897949258/a1 завершён за51m07s. Все76 required contexts найдены;
  исходно73 SUCCESS/3 FAILURE. Backend:14337 cases,14238 PASS/99 skips/0 failures/errors.
  После отдельно разрешённого владельцем dismissal только alerts3382/3383
  (`false positive`, audit comment) CodeQL113716129357 подтверждён SUCCESS:
  теперь74 SUCCESS/2 FAILURE — coverage policy и зависимый CI Success.
  Ruleset8335285 до/после идентичен; все76 contexts сохранены. Полного green нет.
- Frontend artifact11602690121 привязан к этому run/head:2 statements/6 branch arms
  пропущены только в AdminAuditFeature. Новый test-only case и navbar boundary tests
  прошли focused29/29; audit coverage68/68 statements,104/104 branch arms,
  17/17 functions,61/61 lines. Это диагностический scoped run, не полный hosted gate.
- Actual Linux Home-empty12/12 записан до global seed. Axe serious/critical0 относится
  только к включённым правилам: private collector отключал часть AA rules без
  согласованного исключения, поэтому полного accessibility PASS нет. Новые Home/general
  copies сохраняют WCAG A/AA и threshold0 без этих overrides; actual run ещё нужен.
  Тот же disabled-rules block удалён из tracked authenticated visual audit;
  Node syntax PASS, WCAG tags/serious-critical threshold и routes сохранены.
  Owner approval отсутствует: на768px найдено перекрытие navbar, а1440px snapshot
  снят до завершения News animation. Drawer до1024px и bounded animation settling
  подготовлены/reviewed; navbar unit checks PASS. Новый visual packet ещё нужен.
- Два existing navbar/footer live specs согласованы с drawer при1024px и tablet
  при1025px; сохранены44px, keyboard/focus/scroll-lock и geometry assertions.
  ESLint/Prettier PASS; число declarations сохранено, actual browser rerun открыт.
- Existing membership-revocation spec теперь проверяет две независимые сессии:
  initial WS delivery обеим → exact room revoke notices → отсутствие следующего
  group message до reload → reconnect/rejoin attempts/REST denial → повторная
  проверка доставки. Room eviction не объявляется transport close; notices/remaining
  delivery обязательны. ESLint/Prettier PASS, actual current-image runtime ещё открыт.
- Fresh source14c2 Core:23 containers/4 one-shot exit0/14 healthy/10 signed loopback
  bindings; up/readiness PASS. Canonical full runner уже выполнил global demo seed.
  Этот superseded Core затем удалён canonical owner-checked teardown: exit0,
  containers/networks/volumes0, private failure evidence/state directory сохранены,
  guardfalse (peak56,6%/free13,83 GiB). Следующий source требует нового Core state.
- Full live pass1 остановлен resource guard при RAM87,3%/free4,05 GiB.
  Итог198 cases отсутствует; cleanup receipt остаётся unconfirmed, несмотря на
  отсутствие записанного PID/его descendants в последующем read-only снимке.
  Private artifacts содержат56 error contexts, включая25 retry folders.
  Повторяющийся React418 и oversized attachment500 разобраны и исправлены ниже;
  подтверждение исправлений на свежем image ещё требуется.
  Все эти ошибки нельзя объявлять доказанным resource cascade. Два full PASS открыты.
- Последующий real SSR→hydrate RED подтвердил timezone15:00/18:00 mismatch и
  различный состав списка около полуночи. DateBullet/EventsCard используют общий
  принцип UTC server snapshot → browser-local post-hydration; final focused28/28 PASS,
  scoped coverage89/89 statements,57/57 branches,37/37 functions,83/83 lines.
  Непрерывный guard: peak57,4%/free13,54 GiB. Это ещё не current-image live PASS.
- Upload RED подтвердил, что TaskGroup оборачивал ожидаемый HTTP413 в ExceptionGroup.
  Исправление восстанавливает только homogeneous HTTP errors, сохраняет mixed/internal
  groups и cleanup. API413/no persisted message, timeout, nested-group/slot и partial
  cleanup проверены27/27 под непрерывным guard (peak57,3%/free13,57 GiB).
- Lockout/email-verification и две PWA ошибки разобраны как defects live specs:
  form-scoped alert, раскрытие email accordion до ожидания ответа, localized title
  и JS marker после reload. Real API/Mailpit/MFA/cache assertions и timeouts сохраняются;
  actual browser rerun ещё нужен. Stories hidden/visible transition на headless shell
  не достигнут;20 cycles/memory plateau и реальная pause/resume остаются открытыми.
- Два credentialless Windows probes дали0/3 реальных visibility transitions на
  default headless shell. Full Chromium channel не запустился (`spawn UNKNOWN`),
  причина OS не доказана. Network requests0; browser configuration не менялась.
  Linux no-network capability probe full Chromium headless и headed/Xvfb завершён:
  каждый20 cycles,0/40 expected visibility pairs, requests0, оба browser/context закрыты,
  exact owned container удалён. Реальная причина ещё исследуется; product PASS нет.
- SEC-03 на Core14c2: persisted production probe PASS (canonical_v2/configured
  key/UTC fields/one PostgreSQL row/logout401); native verifier dispatch PASS.
  Rotation и native signing этими probes не проверялись. SMTP hosted real PG17+
  Mailpit integration job113714252292:1/1 PASS; deadline/cancellation unit tests PASS.
- Rust-P3-03 parity на14c2 подтверждена: producer113713539701,
  artifact11601332318, все6 Rust inputs совпадают с14c2. Финальные release images,
  signatures/SBOM/provenance и performance claims этим не подтверждаются.
- JUnit14337 cases дают проверенный duration refresh без удаления истории.
  Updater merge-mode ошибочно учитывал bookkeeping полностью skipped файлов;
  RED воспроизведён, minimal fix GREEN17/17. Current cap2 и quality floors сохранены;
  target15m остаётся открытым — одно обновление весов не доказывает этот бюджет.
- Final local fast preflight всего29-file package:10/10 PASS за81,966s; process exit0,
  все35 source/config inputs стабильны, оставшихся recorded owned processes0.
  Непрерывный guard: peak58,9%/free13,07 GiB. Это не hosted coverage/live acceptance.

## Сохранённые CI и package проверки предыдущих checkpoint

- MFA checkpoint `fcdda2a0b33332ace6f5a1f54747ec023f41f94d` опубликован в PR1306;
  обычные commit/pre-push hooks PASS, `.secrets.baseline` повторно staged.
  Matrix37893211061/a1 ещё не подтверждён как полный PASS. Hosted live Core
  run37893210706/a1 FAIL: auth-roles, desktop, React hydration418 при dashboard navigation.
- Weather sessionStorage давал server skeleton/client badge; bookmarks localStorage —
  server0/client1. Real renderToString/hydrateRoot воспроизвёл оба RED; fixes сохраняют
  cache после hydration. Weather120/120 в семи модулях (10,76s), bookmarks55/55
  в шести (10,08s), guardfalse; root/peer review CLEAR. Final package preflight10/10 PASS
  после static probes correction; guardfalse, peak66,7%/free10,58 GiB. Hosted smoke открыт.
- Два P1 GraphQL/Python WS DB fallback при mandatory revocation outage
  воспроизведены20 RED cases; fix и actual GraphQL context проверены121/121 PASS.
  Оба production-модуля100% line/branch; root/независимый P1 review CLEAR.
  Current-SHA runtime и release-level auth/session/data review остаются открыты.
- Stale S3 loopback/provenance assertions исправлены без ослабления guards;
  два полных contract-модуля21/21 PASS. LHCI requested/final origin/path policy
  закрывает protected→login false completeness; только root→dashboard alias.
  RED/GREEN18, adjacent48/48 PASS; actual Lighthouse scores NOT RUN.
- Hosted Matrix37886084026/a1 на679 завершён за45m36s: required76/76,
  73 SUCCESS/3 FAILURE. Все четыре Python shard и их unit/integration aggregators PASS.
  Coverage gate FAIL; отдельный CodeQL FAIL; CI Success FAIL как следствие.
- Все четыре coverage artifacts прошли provenance/hash checks; tested merge
  `e3005c6d9716ccf8407a6b47f2861baecc91c94b` имеет parent679 и byte-identical
  affected source. Diagnostic combine:99,957301%, восемь statements/branch paths
  не покрыты в schedule schema, audit service и embedding event handlers.
  Regression bundle167/167 PASS. Все app/quality/pyproject byte-identical tested merge;
  combine четырёх shards и свежего local coverage даёт100%,0 missing/partial.
  Это diagnostic; свежий hosted full gate ещё не подтверждён, исходный100% floor сохранён.
- Цель blocking CI15 минут открыта: backend cap2 даёт два этапа; terminal shard
  занимает19m54s сам по себе. Полный green JUnit нужен до duration reweighting;
  cap2 сохранён, retries/фиктивные PASS не добавлялись.
- Наfcdda все пять CodeQL analyses PASS. GHAS check113698844614 FAIL только по HIGH
  alerts3382/3383; missing-configuration diagnosis не актуален. Read-only triage
  подтвердил cache-mode query-model gap; отдельное разрешение на запись решения
  по двум alerts на том checkpoint ожидалось. Последующее разрешение и exact dismissal
  выполнены только для3382/3383; текущий результат описан выше.
- Frozen-RC uv/npm/setup-node caching отключено; contracts14/14 PASS.
  Actionlint pinned на reviewed upstream PR745 commit5dc52e8 с проверенным SHA-256;
  unmerged provenance сохранён; repo lint PASS, один unchanged HTTP helper FAIL.
- Go CI/builders1.26.9, fuzz1.27.2, x/net0.60.0 и нужные x/text0.42.0 overrides.
  Windows scan9 modules exit0/reachable vulnerabilities0; unimported OpenPGP
  GO-2026-5932 остаётся в трёх graphs без fixed version. Linux hosted gate отдельный.
- Исторический package679 preflight9/10:337 contracts PASS; Prettier исправлен,
  полный format:check отдельно PASS, повторного10/10 не было. Local Node154/
  cleanup54/WASM555 PASS/1 planned skip/0 FAIL не являются hosted acceptance.
- Package9d44: full preflight10/10 PASS (81,22s), scoped Ruff/check format PASS;
  root/peer review и обычные hooks PASS. Новый hosted coverage gate ещё открыт.
- MFA package сохраняет198 cases/59 specs: real sibling ticket/Go WS остаётся OPEN
  до OTP verify, затем ожидается4401/Session revoked, siblingREST401/current session retained.
  Typecheck/lint/format/3 contracts/198 collection PASS; root/peer review CLEAR.
  Последующий full198 attempt остановлен guard; отдельный runtime outcome остаётся unresolved.

## Сохранённые Core и runtime доказательства предыдущих checkpoint

- Fresh Corefcdda: up exit0/guardfalse, peak74,8%/free8,01 GiB. Schema11/source/
  daemon/projection/readiness PASS;23 containers/4 one-shot exit0/14 healthy/
  10 signed loopback bindings. Admin-only seed выполнен один раз; feeds/schedule/chats пусты.
  Core штатно stopped с сохранением данных на время weather fix; cross-SHA rebind запрещён.
- Исторический SEC-03 persisted probe дошёл до SQL parsing, но итог FAIL: boolean `::text`
  возвращал true/false при parser t/f. Private one-line correction reviewed, ещё не выполнена;
  тогда persisted acceptance оставалась открыта. Этот parser failure superseded последующим
  current14c2 persisted PASS выше; старые native receipts отдельно не заменяли её.
- Исторический Core679 resume exit0/guardfalse, peak80,3%/free6,27 GiB;
  source/schema11/daemon/projection/23 containers/4 one-shot exit0/14 healthy/
  10 signed bindings и edge/backend readiness/Mailpit search PASS.
- Existing admin-only seed выполнен один раз. После stop/start read-only transaction
  подтвердила точный roster10 users/1 admin/2 teachers; news/stories/events/schedules/
  chats пусты. Stop сохранил данные; superseded synthetic Core удалён canonical
  owner-checked teardown: exit0, containers/volumes/networks0; receipts сохранены.
- Image679 main JS168786 bytes/164,83 KiB при raw budget500 KiB; Linux Node24.19.0,
  hashes сохранены. Только raw chunk: transfer budgets/Lighthouse этим не доказаны.
- SEC-03 native679 PASS: genuine extension/builtin verifier, один positive canonical_v2;
  owner/health/inventory неизменны, stderr пуст; API/DB calls0/persistent rows0.
- Official Playwright1.63.0 Linux image/digest и Chromium revision1243 проверены.
  Current container→Caddy probe PASS; Windows→host-network WS refused до credentials/
  browser/captures. Exact idle server удалён, failure receipts сохранены. Internal bridge/
  loopback/native exact-origin exposeNetwork adapter подготовлен; runtime ещё открыт.
  Auth/admin ACL и LHCI build-before-collect исправлены/reviewed; actual runs открыты.
  Последующий bridge/Home14c2 PASS описан выше; expired owned browser server retired.
- Live Chromium collection перечислила198 cases/59 specs,99 desktop+99 mobile;
  на том checkpoint полный run NOT RUN; позднее14c2 attempt был guard-aborted, итог открыт.
  Screenshots/owner approval/Linux baselines, SMTP/MFA,
  logout/revocation/product E2E и coordinated DB/S3 restore ещё открыты.
  Home-empty снимать до global-feed seed; shared feeds не очищать.
- Owned bounded builder: Bake parallelism1/CPU2/RAM4 GiB/swap0, реальные limits
  проверены; сейчас остановлен. Только его11 reclaimable exec.cachemount удалены;
  build layers/cache volume сохранены. Старые de3 images удалены после no-ref proof.
  Default builder/shared caches сохранены.

## Сохранённые предыдущие проверки

- Nullable Schedule PATCH: focused24/OpenAPI18/MSW3 PASS; шесть required storage
  полей игнорируют explicit null, optional clear сохранён. TypeAdapter[str] mypy fix принят.
- Existing live CLI quiesce: focused19 и seven-module1265/1265 PASS; writers stopped,
  healthy PostgreSQL/MinIO/marker/volumes сохранены; external writer check отдельный.
  [Runbook](../../runbooks/database-backup-restore.md) описывает quiesce/resume.
- R02 inventory/hooks165, planner317, auth74, SEC-03 focused98/adjacent221 PASS;
  старые auth/reset18 PASS/2 skips относятся к своим SHA. Harness28/runtime44/preflight10
  PASS. Known P2 taskkill после parent exit не гарантирует orphan containment;
  cleanup-unconfirmed даёт failure; Antigravity не является native Codex hook registration.

## Следующий checkpoint

- Завершить reviewed fixture-owned session cleanup и finite skipped-identity
  accounting, сохранив auth caps/assertions/timeouts и quality floors.
  Scoped checks/fast preflight/hooks, restage baseline, commit/push;
  заморозить новый clean SHA и проверить свежие76 required contexts.
- Fresh owner-checked Core: readiness → admin-only seed один раз → исправленный
  Home12 до global seed → persisted SEC-03 → targeted affected scenarios →
  два последовательных Core passes с точным applicable/skip accounting.
- Real Story Viewer20 cycles/memory plateau native-tab механизмом;
  capability3/3 не заменяет product acceptance. Stop/start сохраняет demo data.
- Утвердить RU/EN/light/dark/Linux visual packets, затем tracked baselines;
  реальные all-topic push/SMTP/MFA/WS, reduced motion/a11y и Lighthouse routes.
- Закрыть auth/session/data review, все63 audit IDs и один coordinated DB/S3
  restore. P0/P1 нельзя переносить. Frozen-RC full smoke → ordinary merge/
  main checks → шесть source-bound images/signing/SBOM/provenance/WASM parity →
  accurate release notes. Target15m открыт; cap2 не увеличивать.

## Ресурсы и сохранность

- Один heavy workload: startup RAM≤75%/free≥8 GiB, runtime guard85%/4 GiB.
  Владелец отдельно разрешил исключение только для serial Linux screenshots:
  startup≤80%/free≥6 GiB с1 GiB/2 CPU browser cap; остальные thresholds сохраняются.
- Свежая resource check перед запуском; удалять лишь доказанно owned временные
  ресурсы. Чужие процессы/env/data, shared Docker/WSL/caches и backups сохранять.
  Снимок Codex usage2026-10-09 13:05 UTC:2% consumed/98% remaining,
  ordinary usage allowed; available free reset credits0. Это snapshot, не прогноз.
- Git history/migrations/private rescue bundle сохранить; session logs и superseded
  snapshots не возвращать в indexes. Новые branch/worktree не создавать.
