# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-22 (Europe/Istanbul). План — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Приоритет и подтверждённый прогресс

Закрыть все 512 исходных AUD IDs [октябрьского аудита](../../audits/AUDIT-2026-10.md). Принятая нижняя граница — **223/512 (43,6%)**; [ledger](../../audits/AUDIT-2026-10.md#evidence-checkpoint-223-verified-original-aud-ids). Исправление, commit и отдельный успешный тест не заменяют приёмку. К продуктовой приёмке MVP вернуться после аудита.

Работа идёт только на `egorribun`, в одном checkout, через [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git; максимум три GPT-6 Luna Max с непересекающимися файлами. Удалённые операции — GitHub plugin. Новые проектные ветки/worktree, force-push, bypass, merge/deploy не выполняются.

**Работа возобновлена по поручению владельца 2026-10-20, 20:28 UTC.** Начальная сверка GitHub подтверждает опубликованную контрольную точку [8c202a75](https://github.com/egorribun/university_ecosystem/commit/8c202a7570b8cdbece3fda11b6097493e40966a8), tree 94ff3ce66f90998f02886790e74e763f1a3d79c3: 24 пути уже опубликованы, а не остаются локальным набором. Приватные кандидаты не импортируются и не считаются частью этого source. Продолжение выполняется через GitHub plugin; сведения о локальных прогонах ниже сохранены как исторические доказательства, а не новые проверки. На момент возобновления принятый ledger составлял 156/512; новая приёмка приведена ниже.

## Проверенные source и CI

На [source 3a28c89](https://github.com/egorribun/university_ecosystem/commit/3a28c89b54e654c467c3fd5a0da2c19324818447), tree 87f50dfa1bbfcda3a5fd2fb053786b2a96c47780, merge-checkout 8197424500bedb0723fcd93d495baa7905e04b05 имеет тот же tree. [Matrix 39502529030](https://github.com/egorribun/university_ecosystem/actions/runs/39502529030): WASM/worker/PDF job 118905382283 — 657 Node PASS и 55 Vitest PASS; Contract job 118904463197 — 676 PASS / один deselected, включая все 61 catalog tests и 19 Caddy controls, затем отдельно 239 security-policy PASS. Pre-commit, frontend lint и baseline integrity — SUCCESS. AUD-473 закрывает повторную инициализацию после rejected shared promise, AUD-475 — ослабление required classification/events через job override, но не изменение самого профиля или независимый ruleset parity. Полный CI не принят: inventory job 118904463266 обнаружил искусственный sleep в новом process.wait fixture. В следующем checkpoint он заменён нормально завершающимся дочерним процессом с тем же fault injection и проверками cleanup, без pragma/suppression; собственный recheck ещё требуется. Hosted Caddy причина и NATS outage остаются неподтверждёнными.

На возобновлённом source 8c202a75 проверен merge-checkout 66f4adf71038299d3ff46ea14d8d87db97af14f8 с тем же tree. В [Matrix 39492090074](https://github.com/egorribun/university_ecosystem/actions/runs/39492090074) уже SUCCESS: frontend production build и lint/format, inventory, backend types, Contract Tests (239 тестов finite secret policy) и detect-secrets baseline integrity. Это частичная проверка, не полный CI и не новое закрытие AUD ID.

Dependency Review run 39492089723/job 118867601939 и Python Dependency Audit job 118867975837 отказали на новом GHSA-6q48-6c7w-9gw2 для certifi 2026.7.22. Владелец разрешил ровно certifi 2026.10.19 раньше семидневного срока; [точные границы](../../DEPENDENCY_COOLDOWN_EMERGENCY.md#owner-approved-certifi-exception-2026-10-20) сохраняют общий cooldown. Временный bounded generator на dd27830 успешно выполнил targeted uv lock и проверил candidate: job 118875905694, run 39494503454. Он подтвердил неизменность остальных 229 packages, восстановил исходный uv.lock, после чего обычный lock gate ожидаемо отказал. Полученный 36-строчный diff сверён с upstream и интегрирован этим follow-up; временный шаг удалён. Собственные final-source lock и vulnerability gates ещё требуются. npm audit с уже опубликованным follow-redirects 1.16.1 — SUCCESS. В frontend shard-4 исходного 8c job 118868613555: 2307 PASS / один FAIL legacy PDF mock; исправлен только harness font-fetch/registration/save, production PDF source не изменён. Owned Live 39492090053 завершился отказом e2e; outage SKIP, штатные stop/receipt/upload SUCCESS. Причина Caddy разбирается по finite stage metadata; приёмка AUD-174 не заявлена.

Предыдущий опубликованный source — [bef8b046](https://github.com/egorribun/university_ecosystem/commit/bef8b0463cc3284aed0e379eb805fa72f02a3499), tree 25188fe88de43cc04a56fa316069b279569606e9. В 32-файловую публикацию вошли NATS CLI/workflow wiring, единое Caddy log read, исправление frontend differential gate и test hygiene. Ordinary pre-commit/pre-push, полный trusted scan, fast preflight 10/10, inventory и проверка 463 Markdown файлов прошли до публикации. Собственные hosted CodeQL, Gitleaks, detect-secrets, security/types, inventory, четыре frontend shard, production build и performance workflow — SUCCESS. Полный CI не принят: npm audit job 118841268652 выявил advisory 1242604/1242605 для follow-redirects 1.16.0; Owned Live job 118840391100 дал 38 browser PASS / два штатных SKIP, затем Caddy verifier FAIL. NATS outage поэтому SKIP; исправленная публикация не считается actual outage evidence. Причины и следующий source проверяются отдельно.

Последний полностью принятый CI checkpoint — [e15027a](https://github.com/egorribun/university_ecosystem/commit/e15027afdb4793838de373463654fb9ffc31d079), [Matrix 39240974262](https://github.com/egorribun/university_ecosystem/actions/runs/39240974262): 21 SUCCESS / два SKIP workflows; 78 required context/app pairs сверены — 77 SUCCESS / один NEUTRAL, без missing/duplicates/pending/failures. Подробности Python/frontend/PG/coverage и допустимого Checkov NEUTRAL сохранены в аудите. Owned Live этого checkpoint подтверждает auth/role/reset smoke, без full smoke, deployment и устранения исторического RSS-margin risk.

Предыдущий hosted source — [c84441f3](https://github.com/egorribun/university_ecosystem/commit/c84441f31ef9345df0ae32c5d617b12c370c9c98), [Matrix 39465395305](https://github.com/egorribun/university_ecosystem/actions/runs/39465395305). Checkout c5c21bf242592bac73d3e323acf7dac7e2c99959 имеет exact tree 9c29c2e4846a3f38484798f4fae4d135a4a12693. Полный CI не принят; каждый следующий source требует собственных checks.

- Hosted PostgreSQL job 118777833587: **206 PASS / девять штатных SKIP**. Все три quarantine concurrency/late-PUT/migration-DDL cases именованно PASS; upgrade и ожидаемый отказ irreversible downgrade проверены.
- Source/Test Inventory job 118775343852 отказал на старом policy head 202610120002 вместо 202610200001. Точечная синхронизация сохраняет 40 прежних exception records, добавляет только существующий UUIDv7-mixin record для quarantine_reservations.id и отражает source-derived 46 tables / 126 defaults. Root ordinary cohort: 27 PASS; actual generator/output/check PASS. Собственный hosted recheck ещё требуется.
- Gitleaks job 118775340779 отказал на 845 findings; root проверил, что все они относятся к 94 commits из ancestry base и лежат вне intended base..head. Причина воспроизведена локальным Git fixture: depth-one fetch после полного checkout делает base shallow и расширяет разность истории. Correction сохраняет полный fetch и запрещает scanner launch на shallow checkout. Root complete contracts: 21 PASS. Подавления не добавлены; собственный hosted recheck ещё требуется.
- Backend shard-0: 832 PASS / один известный FAIL на отсутствующем NATS outage step. Shard-1: 3761 PASS / 30 штатных SKIP / один FAIL устаревшего security workflow contract. Контракт теперь требует полного ancestry для Gitleaks и узнаёт новое имя scanner step, сохраняя прежний policy-before-scanner guard; root: 31 PASS в двух полных модулях и один PASS отдельного disposition contract. Owned Live job 118775342603 — SUCCESS; это обычный smoke, не полный AUD-174 proof.
- Performance run 39465394994: текущий Rust job 118775341779 — SUCCESS. Исторический FAIL 58ff776a на batch_detect_conflicts/100 сохранён в аудите; same-harness attribution не выполнена и не требуется подменять ею текущий gate. WS-Hub job 118775341113 отказал на prefetch base dependencies до измерений; это пока не установленная Go-регрессия. Artifact разбирается отдельно; gate и пороги сохранены.

## Карантин и actual Core evidence

Далее сохранена хронология предшествующих локальных и hosted проверок. Слова «локально», «staged» и «следующий source» в ней относятся к описанному этапу до публикации 8c202a75, а не к текущему состоянию ветки.

Опубликован следующий source [0dca1faf](https://github.com/egorribun/university_ecosystem/commit/0dca1faf01e56e9b0b6fdfabe19cd9231fdb6eee), tree 8a6bbcea1e86ebc34b429b574bb146431e45b24c, exact checkout 8f618888ad0602b0c4cd7184378dce59c9520287. Ordinary hooks, full trusted scan и local merge-aware Gitleaks PASS. Hosted Gitleaks 39471485768/job 118796397165 и detect-secrets job 118798262077 — SUCCESS; AUD-185/186 приняты в своём точном объёме. Model inventory в Matrix 39471486170 теперь PASS, но следующий strict hygiene check нашёл три test sleeps и один dynamic skip. Их двухфайловое исправление проверено root: 67 PASS / zero SKIP, полный inventory/anti-pattern check PASS; собственный hosted recheck ещё нужен. На 0dca также SUCCESS: CodeQL, четыре frontend shard, production build, обычный Owned Live и DB Performance. Backend shard-1 теперь SUCCESS; shard-0 сохраняет единственный FAIL отсутствующего NATS outage step (832 PASS). Rust performance job 118796400463 — SUCCESS; WS-Hub job 118796400932 повторно отказал до измерений из-за HTTP/2 INTERNAL_ERROR proxy.golang.org при загрузке testcontainers/nats v0.44.0. Artifact 12286614172 проверен по digest. Полный CI не принят. Root дополнительно выявил vacuous frontend differential check: LCOV использует src/..., а Git diff — frontend/src/.... На digest-verified artifact после нормализации и immutable ac74..0dca diff: 4320 reportable changed lines, 12 missing, 99,72% при floor 100%; исправление gate и тестов готовится без снижения требования. Новые поведенческие тесты интегрированы: combined root cohort 89 PASS. Focused differential diagnostic больше не показывает прежние12 violations; три expression locations учитываются как BRDA, синтетические DA не добавляются. Полный новый patch100 ещё требует свежего общего CI.

AUD-241 принят в точном source/evidence scope; собственный 0dca PostgreSQL job 118798357406: 206 PASS / девять штатных SKIP, все три целевых case PASS. Независимое ревью и root подтвердили неизменность app/alembic между c844, 0dca и working tree. Rollout с миграцией/draining old writers остаётся отдельным этапом. В c844 интегрированы durable storage-scoped quota-before-PUT, cross-worker reservations и TTL для подтверждённых stored objects. Root ordinary cohort: 412 PASS / zero SKIP; два service modules — 647 statements / 246 branches, 100% строк и ветвей. Root7 actual PostgreSQL: **3 PASS / zero SKIP**, три database receipts, реальные DDL/index/constraint проверки, стабильные source pins и exact-ID cleanup; host guard PASS. Прежний Root5 outer-runner SystemExit defect исправлен отдельно; его исторический exit 1 сохранён в evidence. Неопределённые pending writes занимают квоту до fenced reconciliation; versioned S3 и неполный inventory запрещают admission. Новая миграция не входит в finite131; текущие coverage/quality gates сохраняются.

Actual local Core c844 поднят штатно: readiness через published IPv4 и trusted-proxy refresh PASS. Browser/display origin сохранён. BuildKit остановлен после сборки, cache сохранён; startup guard PASS, sourceStable=true, zero recorded owned processes.

Точечный AUD-174 прогон: **два browser PASS**, затем общий Caddy verifier FAIL. Diagnostic repeat подтвердил успешный redaction parser для первого проекта, но повторная full ownership проверка исчерпала общий 25-second deadline. Это не принятая end-to-end redaction/visual проверка. Готовится batching тех же exact-ID runtime inspections без удаления проверок или увеличения бюджета. Core затем штатно остановлен с данными; stop guard PASS. Работающих принадлежащих прогону контейнеров нет.

Root проверил batching candidate на всех 23 остановленных owned containers: 15 с Health и восемь без него, одна bounded inspection за 0,201 секунды. Первый шаблон воспроизводимо отказал на отсутствующем Health; исправленный использует безопасный lookup, сохраняет восемь mount identity fields и отклоняет неоднозначные IDs/JSON. Полный canonical launcher cohort: **2064 PASS / zero SKIP**, fast preflight: **10/10 PASS**, ordinary pre-commit/pre-push: PASS. Реальная browser/redaction проверка исправленного source ещё требуется.

Actual Core 0dca startup guard PASS: sourceStable=true, zero recorded owned processes, пик RAM 69,53%, free ≥9,69 GiB. Обычный focused browser run снова дал два PASS и итоговый Caddy verifier exit 2. Closed-stage diagnostic подтвердил причину: fresh full pin ≈9,2 s, шесть повторов не помещаются в общий 25 s; первый redaction parser PASS, последующий pin исчерпывает бюджет. Ни один прогон не принят как полный AUD-174 proof. Готовится один bounded log read с двумя прежними correlation/window проверками и fresh полным pin до/после операции; лимиты сохраняются. Core затем штатно остановлен: stop guard PASS, данные/cache сохранены, работающих контейнеров нет. Root-проверка нового единого чтения: 2088 PASS / zero SKIP; actual повтор на опубликованном SHA ещё требуется.

AUD-015: проверенный семифайловый кандидат сохранён отдельно до решения владельца по 18 точным checksum/SRI dispositions; в текущую публикацию он не входит. До отделения: 17 root canonical PASS, TypeScript/focused ESLint PASS; точные RU/EN/mixed-script title и дата извлечены из трёх реально созданных PDF, русский render просмотрен. Генератор повторно дал побайтно тот же TTF (199704 bytes, 1284 codepoints). После разрешения ещё нужны интеграция политики, final-source scan, production bundle/asset delivery и собственные hosted checks.

NATS v2 интегрирован локально: root actual projection PASS на 23 остановленных контейнерах, native Linux CPython 3.14.4 — 610 PASS / zero SKIP в 17 модулях против canonical source с отдельным unit pytest configuration. Это ограниченное unit evidence; последующие CLI/wiring проверки описаны ниже, actual outage ещё не выполнялся.

Новый локальный follow-up: NATS CLI интегрирован после root ordinary cohort **143 PASS / zero SKIP** и независимого ревью; workflow wiring интегрирован после независимого ревью, actual outage ещё не выполнялся. Frontend differential gate исправлен без снижения floor: root **14 Node PASS / пять policy PASS**, raw reports сохраняются, проверяются DA/BRDA и наличие изменённых source records. Отдельный RED/GREEN подтверждает немедленный отказ при неуспешном `uv sync --frozen`. Собственный общий CI нового source ещё требуется. Завершённый Matrix 39471486170: **66 SUCCESS / 17 SKIP / три FAIL**, включая итоговый агрегатор; две независимые причины — hygiene и отсутствующий outage step. На этом историческом этапе принятая нижняя граница составляла 156/512.

## Следующие действия

На source 49f8c67 собственные Renovate/lock check (job 118891463776) и Dependency Review (118891464456) прошли. SBOM vulnerability gate 118891463532 отказал на девяти Pillow advisories для 12.3.0; certifi 2026.10.19 установлен и больше не является причиной этого отказа. Владелец отдельно разрешил переход на Pillow 13.0.0 и точечное major-bound/cooldown exception 2026-10-20 в 21:57 UTC. Generated Pillow lock проверен на source 19509334: run 39505978632/job 118914878260, 230 packages, только Pillow package и три согласованных metadata изменения. Все 48 artifacts сверены с PyPI; uv timestamp приведён к его доказанной millisecond precision без изменения raw cutoff. Candidate lock check PASS, restored-old check ожидаемо FAIL. 131-строчный diff интегрирован, временный generator удалён. Шесть real-codec cases и dependency-policy module включены в существующий early Contract cohort; полный backend suite сохранён. Собственные final-source vulnerability и compatibility gates ещё требуются.

Pre-commit 118891467883 выявил только форматирование новых catalog tests. Применён точный Ruff diff, assertions не изменены. Чтобы получать regression-first evidence без ожидания всей матрицы, существующие Contract Tests и WASM Contract Tests дополнены конечным списком catalog/Caddy и worker/PDF проверок; прежние команды, jobs, budgets, coverage и required contexts сохранены. Двенадцать тестов реального bounded reader дали пять diagnostic RED и семь PASS controls. Correction сохраняет общий 1 MiB cap, 10/25-second deadlines, cleanup и post-pin precedence; различает overflow, nonzero exit и pipe I/O, не объявляя причину реального hosted отказа установленной. Добавлены process.wait error и finite-reason controls.

Сначала проверить интегрированный generated certifi lock и исправленный legacy PDF harness на новом source. Tests-first для AUD-473 и AUD-475 подтвердились на 6e8de319. WASM job 118897939175: 657 Node contracts PASS, затем 53 Vitest PASS / два ожидаемых crypto RED; все 19 PDF/export, девять parity и 20 wrapper cases PASS. Contract job 118897207349: 658 PASS / 11 ожидаемых FAIL / один deselected, затем 239 security-policy PASS. Шесть FAIL — catalog overrides, пять — неразличимые причины bounded read. В этом follow-up добавлены минимальный failed-init reset, запрет ослабляющих job overrides и только finite Caddy diagnostics. На source 3a28c89 собственные целевые GREEN и независимое ревью подтверждены: AUD-473 и AUD-475 приняты в ограниченном объёме, ledger увеличен до 158/512. Это не приёмка полного CI.

Актуальный follow-up: владелец утвердил ровно 18 checksum/SRI identities для AUD-015 и точный validator/test diff. Прежние 264 записи сохранены; интегрированная локальная политика содержит 282 записи, baseline остаётся 319. Root verifier module: 239 PASS без предупреждений. Семифайловый PDF-кандидат возвращён в staged source; production bundle/asset delivery и final-source scan ещё требуются. AUD-257 (отсечение NaN/±Infinity до SQL LIMIT) и AUD-470 (положительные L1 cache capacities) интегрированы после независимого ревью; root ordinary modules дают соответственно 25 и 20 PASS. Эти локальные результаты пока не увеличивают принятый ledger. AUD-155 проходит дополнительное исправление доказанных гонок rollback; AUD-328 — дополнительных rename/path controls. Ранние кандидаты с известными дефектами не интегрированы.

Полный scan staged набора с утверждённой 282-record policy: zero unmatched, 241 currently matched dispositions, baseline 319 без изменений. Ordinary pre-commit после исправления optional field-name label — PASS, включая isolated mypy и actionlint. На bef8 backend job 118842238530 дополнительно выявил устаревший pytest node ID после переименования NATS CLI test. Однострочная синхронизация workflow сохраняет проверку отказа до state side effects; root cohort — 182 PASS, все 109 явно указанных workflow paths/nodes существуют. Это отдельная коррекция; полный frozen-RC coverage gate ещё требует hosted recheck.

Follow-redirects 1.16.1 интегрирован локально: только version/resolved/integrity одной lock-записи, package.json и остальные lock fields сохранены. Root сверил registry SRI и tarball; private audit — zero vulnerabilities, direct detector comparison — zero new identities. Offline install без package scripts обновил установленную версию до 1.16.1. Unskipped Windows build завершился exit 0, но guard отказал из-за пересоздания пяти tracked WASM outputs; эти результаты сохранены отдельно, worktree восстановлен из index. Повторный focused font build валидирует неизменённые WASM artifacts/provenance: guard PASS, stable staged tree, 22,32 s, peak RAM 50,51%, free ≥15,74 GiB, zero remaining owned processes. Это не замена полному hosted build. Production SSR на loopback действительно отдаёт emitted TTF: HTTP 200 / font/ttf / 199704 bytes, hash совпадает с source; lazy wrapper импортируется Activity chunk. Временный exact-owned сервер остановлен. После обновления dependencies оба PDF test modules дают 17 PASS. AUD-015 ещё требует final-source scan и собственных hosted checks; новая визуальная приёмка не объявлена.

AUD-328 v3 интегрирован после исправления найденных независимым ревью пропусков rename/type-change/unmerged и added-symlink paths. Staged mode проверяет индексные blobs только regular 100644/100755; clean-index mode действительно читает tracked Python worktree с проверкой ancestors/reparse и descriptor/path identity. Comments/strings не считаются кодом; ошибки Git/tokenization/чтения дают отказ. Root module: 18 PASS / zero SKIP; прямой полный fallback — 1677 tracked Python files / zero violations, без изменения index. Это lexical gate, не полный Python parser; Git capture limit проверяется после capture и не объявляется hard memory cap. Собственная hosted проверка нового source ещё требуется.

До паузы устранена зависимость нового directory-link fixture от Windows symlink privilege: Windows действительно создаёт и проверяет junction, POSIX сохраняет реальный symlink. Проверка отказа checker не ослаблена, новые skips не добавлены. Root полный модуль снова даёт 18 PASS / zero SKIP; POSIX-ветвь этого follow-up на Windows не выполнялась. Это не закрывает отдельные original AUD-332 file-symlink fixtures. AUD-331 имеет отдельный воспроизведённый WSL/Git-Bash path-adapter hold; изменения пока private.

Для следующего Caddy прогона интегрирована только bounded metadata диагностика: одна строка с кодом из фиксированного конечного набора при отказе, без log/error/nonce/correlation values. Generic outward error, union read, 1 MiB cap, 25-second budget и full pins сохранены. Root полный canonical test_live_stand.py: 1993 PASS / zero SKIP; неизвестная причина hosted отказа не объявлена исправленной. Предшествующий fast preflight прошёл 10/10; новый launcher отдельно проверен полным модулем. AUD-155 v4 остаётся private и проходит независимое ревью после 62 авторских тестов; в текущий набор не включён.

Actual focused AUD-174 на bef8: два browser PASS и `redaction=verified projects=2`; startup/browser/stop guards PASS со стабильными SHA/tree, zero remaining owned processes, пик RAM 68,74%, free ≥9,94 GiB. Независимо сверены receipt, guard hashes и source. Core и captured BuildKit остановлены, данные/cache сохранены. Этот узкий результат не заменяет отказавший hosted smoke и не закрывает AUD-174 до устранения расхождения.

Следующий список сохраняет план прежней контрольной точки; актуальные результаты и оставшиеся блокеры приведены ниже.

1. Завершить source-bound проверку опубликованного набора AUD-015/257/470/328 и ровно 18 утверждённых font dispositions. Follow-redirects уже обновлён до 1.16.1 и собственный npm audit прошёл. Выполнить разрешённое точечное обновление certifi, затем проверить окончательный lock и все обычные gates. Go-prefetch helper остаётся отдельным кандидатом до завершения immutable checkpoint/pin перехода; performance workflow на bef8 уже SUCCESS, поэтому новая попытка оправдана только проверенным повторным отказом.
2. AUD-085 принят в точном объёме CSS generation. AUD-141 ждёт исправленного differential coverage gate и свежего полного coverage evidence. Meaningful regressions для fallback actor и остальных11 schedule/export/weather точек интегрированы и проверены локально. Root cohort: 35 PASS; четыре hosted frontend shard, lint, build и bundle analysis на 0dca SUCCESS. Новая визуальная приёмка остаётся отдельной.
3. Разобрать отказ hosted Caddy verifier при успешном локальном focused proof, сохранить лимиты и повторить smoke на исправленном source. Затем продолжить operational holds AUD-164/167/169. Browser, deployed infrastructure и визуальная приёмка остаются отдельными видами evidence.
4. Продолжить [NATS spec](../specs/2026-10-18-owned-nats-outbox-acceptance.md), [outage plan](2026-10-19-owned-nats-outage.md) и [Docker observation](2026-10-20-owned-nats-docker-observation.md). SQL имеет ограниченный actual PG proof; HTTP/broker/composite/pin factory — private contracts. Lease-bootstrap и адаптеры интегрированы после исправления optional-map/JSON projection и замены четырёх credential-shaped test literals на свежие synthetic values. Root native cohort: 610 PASS; actual stopped-container projection PASS. Минимальный CLI интегрирован и проверен: root 143 PASS, независимое ревью без blockers. Workflow wiring интегрирован; root 150 обычных тестов, полный launcher/Caddy cohort 2088 PASS и isolated Linux cohort 619 PASS. Actual outage ещё не выполнялся.
5. Закрывать оставшиеся AUD IDs, причину отказа Go prefetch и AUD-015 Cyrillic PDF export с именованными source-bound доказательствами. Тематические планы: [UI lifecycle](2026-10-19-ui-lifecycle-reconciliation.md), [cleanup/timing](2026-10-20-runtime-cleanup-timing.md), [quality entrypoints](2026-10-20-quality-entrypoints.md).

## Неизменные границы

Detect-secrets baseline — 319 identities; опубликованная в 8c202a75 политика — 282 owner-approved dispositions. Исторический bef8 содержал прежние 264. Отдельное Gitleaks-разрешение ограничено 25 точными историческими fingerprints. Все 78 required context/app pairs, blocking CodeQL, hooks и finite131 migration exception до 2026-11-13 сохраняются. Changed/unmatched identities остаются блокирующими. Q1/Q4 migration действует; Q2/Q3 — v1.1; глобальный mutation score не повышается ради MVP.

Перед тяжёлым прогоном: RAM ≤75% / free ≥8 GiB; остановка при RAM ≥85% / free <4 GiB. Отдельное исключение для одиночных Linux screenshots: ≤80% / ≥6 GiB, container ≤1 GiB / 2 CPU. Удалять только доказанно принадлежащие работе ресурсы; чужие процессы и prune не трогать.

Manifest source_sha остаётся null. Actual RC, main/bootstrap activation, pre-merge full smoke, следующие визуальные пакеты и deployment — отдельные этапы. Home12 ранее утверждён только в своём exact scope; новые CSS/PDF изменения не получают визуального одобрения автоматически. Merge/deploy не выполнены. NATS outage теперь запускался, но завершился отказом; успешной приёмки и доказательства конкретных stop side effects пока нет.

Исторический actual Core 3a28c89: run 39502529019/job 118906851834 завершился 36 browser PASS / два FAIL / два штатных SKIP. Оба FAIL относятся к password-reset smoke desktop/mobile; до Caddy verifier выполнение не дошло. NATS outage SKIP; stop, receipt и upload SUCCESS. Это не доказательство исправления либо новой причины Caddy. Первичный registration submit без наблюдаемого запроса и последующие admission refusals разбираются отдельно.

На опубликованном 32ab49e собственные lock/Renovate и Dependency Review — SUCCESS; SBOM gate завершил Python/Go/Rust policy checks успешно. Contract job 118918529745: 690 PASS / один deselected, затем 239 security-policy PASS. Все шесть real-codec cases именованно PASS, включая оба AVIF handlers и Pillow-only RGBA/LA. Hooks, security/types, inventory и baseline integrity также прошли. Это не полный CI. Следующий tests-first checkpoint добавляет 10 Node и 15 Python cases для finite registration diagnostics и владения response waiter, не меняя browser callback или admission policy; RED пока только ожидается.

На 56fe8c6 tests-first подтверждён: Owned Live pre-Docker contracts — 241 Node PASS / 10 ожидаемых FAIL; Matrix consumer — 691 PASS / 14 ожидаемых FAIL / один deselected, затем 239 policy PASS. Добавлены finite registration reporter/parser и маленький arm/click/await helper с сохранением исходной ошибки и обработчиком оставленного response waiter. Собственный GREEN ещё требуется. Правила admission, budgets и auth assertions не изменены.

Новый actual Core 19509334: 38 browser PASS / два штатных SKIP, затем finite Caddy stage log_size; штатные stop/receipt/upload SUCCESS, NATS outage SKIP. Это доказанный overflow, не ошибка redaction. Добавлены 11 tests-first cases для coalesced probe windows и общего byte/time budget; production reader пока прежний. Межоконный gap намеренно не входит в будущий scoped probe proof; все сохранённые окна продолжают проверяться совместно.

На 8ee5d67 подтверждены семь Caddy RED: consumer job 118929362171/run 39510013601 — 709 PASS / 7 ожидаемых FAIL / один deselected, затем 239 policy PASS. Все 15 registration parser/runner cases теперь PASS; pre-Docker Node contracts также прошли. Исправление Caddy объединяет только пересекающиеся/соприкасающиеся ±5 s окна, читает disjoint окна последовательно с общими 1 MiB/10 s и прежними 25 s/full pins, совместно валидирует все сохранённые bytes. Для multi-capture незавершённые строки запрещены до объединения; single-capture semantics сохранены. Добавлены 15 safety cases с реальными дочерними процессами, overflow, framing, deadline и post-pin precedence, плюс два прежних one-read controls. Независимое ревью дополнительно исключило rebasing relative timeout: reader получает minimum общего и абсолютного capture deadline, pins сохраняют общий deadline; отдельный delayed-admission test запрещает запуск после истечения capture phase. Свежие GREEN и actual hosted fit ещё требуются; gap вне scoped proof, ledger остаётся 158/512.

На source 78d342b consumer job 118937137770/run 39512384414: 733 PASS / один deselected, затем 239 policy PASS. Все Caddy window/real-child/framing/deadline controls прошли; actual stand ещё требует результата. Security/types, inventory и baseline integrity — SUCCESS. Pre-commit нашёл только однострочное оформление f-string в fixture; применён точный Ruff diff без изменения поведения. Полный CI ещё не GREEN.

Для проверки уже интегрированных AUD-470/328 полные существующие модули добавлены в early consumer cohort. Для AUD-257 добавлены три настоящих PostgreSQL/pgvector cases с временной таблицей и rollback cleanup; три новых PG-only cases применяют стандартный RUN_INTEGRATION_TESTS guard вне PG lane, а прежний PostgreSQL job включает flag=1 и обязан исполнить все три. Существующие тесты, unit/deploy workflows и coverage не исключаются и не меняются. Routing contract проверяет точное условие и обязательный PostgreSQL dialect; unit skips не считаются приёмкой. Новые runtime результаты ещё требуются, ledger не увеличен.

На source 78d342b завершена исходная приёмка AUD-174: Owned Live 39512384207/job 118936316527, exact-tree checkout da68d561c8bd51b914069ba11fc22db38417eab2 — 38 browser PASS / два прежних SKIP, затем Caddy redaction verified для обоих проектов в 23:22:12 UTC. Реальная SSR-форма проверена с отключённым JavaScript; отдельный synthetic query проверяет actual Caddy redaction, а не отправку disabled формы. Source/regression + owned Core scope принят после независимого ревью; Эта приёмка вошла в новый совокупный ledger ниже. Probe windows, budgets и full pins сохранены; excluded gap и production deployment не покрываются.

Следующий NATS outage step фактически выполнился и отказал через generic error; точная стадия пока неизвестна. Штатные stop/receipt/upload SUCCESS, весь Owned Live job FAIL. Полный CI не принят. На опубликованном 5c7980b запущены собственные Matrix 39515095074 и Owned Live 39515095041; новые cache/checker/PG cases ещё ожидают результата. Исторические формулировки о pending Caddy и skipped NATS выше относятся только к указанным прежним прогонам.

Для NATS подготовлены tests-first проверки конечных outcome/stage и двух exception boundaries, hostile values и cleanup precedence. Production launcher ещё не изменён; 38 диагностических RED пока ожидаются, а не наблюдались. Причина actual отказа остаётся неизвестной; ослабления owner/source/runtime guards, budgets и cleanup нет.

На 5c7980b consumer job 118945230288: 771 PASS / два deselected и 239 policy PASS; все 20 cache-settings и 18 lexical-checker cases именованно прошли. Hooks/security/types/inventory/baseline также SUCCESS. Новый routing contract случайно попал под прежний фильтр not integration из-за собственного имени; меняются только имя и selector на pg_routing, без ослабления фильтра. Его runtime PASS ещё не заявлен.

Приняты ещё AUD-470 и AUD-328 по полным именованным cloud-модулям и actual no-python2-except hook, а AUD-257 — по трём настоящим PostgreSQL/pgvector сценариям. PG job 118947074469: 209 PASS / девять прежних SKIP; все три новых case PASS, не skip. Вместе с AUD-174 нижняя граница теперь 162/512 (31,6%). Границы: cache config до нормального construction; lexical gate на Linux, не полный parser; generic VectorService, не отдельный EventRepository/tenant E2E. Полный CI и NATS outage acceptance не заявлены. Детальные source-bound доказательства и ограничения записаны в текущем ledger аудита.

Новый отдельный блокер 5c7980b: backend shard-0 job 118947074609 остановлен пятиминутным timeout шага frozen-RC/validator coverage на 99%, до обычного unit run. Завершённого результата этого cohort нет; функциональная регрессия не установлена. Лимит и coverage gates не повышаются и не ослабляются, разбираются затраты выполнения.

На 2d6583e consumer job 118952407565: 781 PASS / 38 ожидаемых диагностических FAIL / один deselected, затем 239 policy PASS. Все predicted NATS RED подтверждены; pg_routing contract теперь именованно PASS. Launcher добавляет только finite typed outcome/stage либо фиксированную причину boundary, сохраняя silent success, exit 2, guards и cleanup; actual причина outage ещё неизвестна.

Отдельное исправление timeout оставляет все 93 selectors/835 cases, прежние пять минут и итоговое 100% validator coverage. Используются ровно два xdist worker и уже установленный pytest-cov для объединения данных; простой coverage run не используется для subprocess coverage. Temp config/data изолированы, зависимости и бюджеты не меняются. Новые GREEN, полное исполнение cohort и фактическое ускорение ещё требуют hosted evidence. Ledger остаётся 162/512.

Подготовлены пять tests-first сценариев AUD-335 для native image-picker buttons, Tab/Shift+Tab, Enter/Space/pointer и отсутствия случайного submit. Production пока не меняется; JSDOM helper даёт geometry только локальной тройке элементов, не имитирует доказательство OS picker/full browser focus. Пять RED ещё только ожидаются.

Для уже интегрированных AUD-468/469 добавлены шесть существующих cases в verbose consumer cohort. AUD-467 остаётся в прежнем focused backend cohort; -q заменён на -v только для именованного evidence. Принятый ledger остаётся 162/512, новые закрытия без runtime не заявлены. Последовательный 2d frozen-RC cohort дал 834 PASS / один ожидаемый NATS FAIL за 255,19 s: прежний timeout не объявляется детерминированным, ускорение нового parallel source ещё проверяется.

На 93172422 consumer job 118957134578/run 39518552065: 820 PASS / один deselected и 239 policy PASS; все 38 прежних NATS diagnostic RED теперь GREEN. Пройдены также routing и parallel-coverage workflow contracts. Pre-commit потребовал только два изменения Ruff оформления нового теста; применён точный hosted diff. Из-за этого format gate runtime двухпроцессного preflight ещё не проверен. Старый 2d Owned снова дал 38 browser PASS / два SKIP, Caddy verifiedprojects2, затем generic NATS FAIL и штатный stop/receipt; это не выполнение нового диагностического source. Полный CI остаётся непринятым.

На 146a0c consumer job 118961355979 подтверждены 826 PASS / один deselected и 239 policy PASS. После независимой сверки приняты AUD-468 (реальный MMDB Reader/lookup) и AUD-469 (scheduler resilience с контролируемыми work/sleep callbacks). Ledger теперь 164/512 (32,0%); actual partition DDL, deployment и полный CI не включаются.

Все пять AUD-335 RED наблюдались в shard-2/3/4: отсутствовала доступная button role. Исправление заменяет label controls на native type=button с ref-вызовом отдельного hidden input; RHF refs, обработчики, styles и прежние disabled expressions сохранены. Старые label-ancestor assertions перенесены на button role, короткий waitFor отформатирован. Свежий GREEN ещё нужен; AUD-335 не закрыт и OS picker не объявляется проверенным.

Actual 931 Owned завершился 38 browser PASS / два SKIP, Caddy verifiedprojects2, затем NATS outcome=failed stage=preflight и штатный stop/receipt. Это ещё не точная причина: facade fallback тоже возвращает preflight при неожиданном исключении coordinator. Добавлены 47 tests-first cases для closed operation checkpoint, cleanup precedence и privacy; production NATS в этом этапе не меняется, RED ещё ожидается.

Следующие existing-fix proofs: пять AUD-195 случаев и 24 actual Compose cases AUD-252 направлены в early cohort. Для Compose нужна именно именованная PASS, не capability SKIP. AUD-467 остаётся до получения именованного focused evidence. Все бюджеты и финальные quality gates сохранены.


## Контрольная точка 2026-10-21, 01:00 UTC

Принят AUD-467: семь именованных composed Settings cases в focused job
118962086178, всего 226 PASS. Ledger — 165/512 (32,2%). AUD-471 повторно
не считается. Тот же job подтвердил 835 frozen-RC PASS за 119,71 s и
итоговые 100% валидатора при прежнем пятиминутном лимите.

На 37021397 consumer job 118971887144 дал ровно 47 ожидаемых checkpoint RED,
855 PASS / один deselected и 239 policy PASS. Добавлена минимальная
типизированная диагностика preflight операций и coordinator exception,
без изменения guards, бюджетов и cleanup. Собственные GREEN и actual outage
ещё требуются. AUD-195/252 имеют именованные PASS, но ждут отдельного ревью.

Устаревшее ожидание certifi в tooling-lock тесте синхронизировано с уже
одобренным 2026.10.19 и независимым wheel digest. Старый pragma на изменённой
строке удалён; нового подавления нет. Scanner и contract recheck обязательны,
новая identity при обнаружении требует отдельного решения. Полный CI пока
не принят; последний общий checkpoint — e15027a.


## Контрольная точка 2026-10-21, 01:16 UTC

Приняты AUD-195 (history sender projection), AUD-252 (actual Compose config)
и AUD-335 (пять native keyboard pickers в JSDOM). Ledger — 168/512 (32,8%).
На 37021397 все четыре frontend shard, static gates и production build SUCCESS;
границы каждого доказательства записаны в ledger, deployment не заявлен.

На 02f59138 consumer job 118978366223: 902 PASS / один deselected и
239 policy PASS; все 47 checkpoint RED исправлены. Actual NATS ещё ожидается.
Сканер выявил ровно новую публичную certifi checksum identity. Владелец явно
разрешил её 2026-10-21 в 01:13 UTC до 2027-01-10: добавлена одна запись,
283 всего, прежние 282 неизменны. Baseline319 и все quality gates сохранены;
собственный scanner recheck обязателен.

Следующий tests-first этап — восемь Spotify transport fallback сценариев
и cancellation control; production Spotify не менялся. Полный fallback module
и исправленный tooling-lock contract включены в early cohort.
Полный CI пока не принят; последний общий checkpoint — e15027a.


## Уточнение проверки 2026-10-21, 01:43 UTC

На a41af3e9 consumer job 118985551935: 9 FAIL / 914 PASS / один deselected,
затем 239 policy PASS. Все девять новых Spotify cases остановились на
подготовке пароля без uppercase/symbol, а не на transport fallback.
Генератор исправлен без отключения password policy; production Spotify
не менялся, корректный RED ещё нужен.

Certifi tooling-lock contract именованно PASS. Baseline integrity job
118985830896 SUCCESS; обычному hook требуется только точное обновление шести
line_number и generated_at из hosted diff, все 319 identities/flags неизменны.
Ruff continuation diff также применён без изменения проверки Authorization.

Owned 02f59138 локализовал отказ в read_signed_owner callback, включающем
Docker bootstrap. Подтверждено расхождение process cwd=repository и
owner.worktree=state root. Добавлены три real-context tests-first сценария,
но production guard пока не изменён. Частные marker bytes не исследовались;
дополнительный reader issue не исключён. Ledger остаётся 168/512 (32,8%),
полный CI и actual NATS не приняты.


## Минимальные исправления после RED, 2026-10-21 02:02 UTC

На ea0d20ea consumer job 118992144847 подтвердил именно 9 целевых FAIL /
946 PASS / один deselected и 239 policy PASS: восемь HTTP transport ошибок
Spotify и один repository-CWD отказ NATS. Подготовка пароля теперь проходит;
cancellation и state/unrelated-CWD controls PASS. Оба pre-commit job и inventory
SUCCESS, метаданные baseline согласованы.

NATS принимает только два подписанных корня запуска и привязывает вложенные
Docker reads к owner.worktree, без chdir и без ослабления остальных guards.
Spotify ловит только TransportError вне breaker context и использует прежний
fallback; cancellation и неожиданные ошибки не скрываются. Добавлены два
контроля RuntimeError/ValueError. Собственные GREEN, actual outage и приёмка
AUD-342 ещё требуются. Ledger остаётся 168/512 (32,8%); последний полностью
принятый CI по-прежнему e15027a.


## Сверка исходного AUD-342, 2026-10-21 02:20 UTC

На 8d45a636 consumer job 118997184302: 957 PASS / один deselected и
239 policy PASS. Context/NATS и GET/Spotify исправления подтверждены в
своём тестовом объёме, но actual outage ещё не принят.

Исходные строки AUD-342 относятся к POST обновления токена, а не GET.
Предыдущее сопоставление было неверным; GET-only GREEN не закрывает находку.
Добавлены 16 refresh transport tests-first случаев и три helper controls,
без изменения production refresh. Ledger остаётся 168/512 (32,8%).

Go scanner обнаружил GO-2026-6809 в 1.26.9; официальные fixed версии,
остальные активные Go pins и границы policy проверяются отдельно.
Полный CI не принят, предупреждение не подавляется.


## Refresh fallback после подтверждённого RED, 2026-10-21 02:39 UTC

На 16992ee0 consumer job 119003482007: ровно 16 ожидаемых refresh
transport FAIL, 960 PASS / один deselected и 239 policy PASS.
Все три cancellation/unexpected-error controls PASS; pre-commit,
security/types и baseline integrity SUCCESS.

Добавлен узкий catch httpx.TransportError вне breaker context в refresh
helper. Состояние Spotify и прежняя обработка HTTP-статусов/прав доступа
сохранены. Собственный GREEN ещё требуется; AUD-342 остаётся открытым,
ledger 168/512 (32,8%), последний общий CI checkpoint e15027a.

Actual NATS на 8d45a636 прошёл прежний read_signed_owner checkpoint,
но остановился в observe_runtime; точная подфаза пока не установлена.
Очистка и receipt завершены. Go security gate остаётся блокирующим,
точечное досрочное обновление ожидает явного разрешения владельца.


## Приёмка AUD-342, 2026-10-21 02:56 UTC

Принята ровно одна исходная находка: refresh POST transport fallback.
На b5fd21d8 consumer job 119008421004: 976 PASS / один deselected и
239 policy PASS. Все 16 прежних RED и три helper controls теперь PASS;
pre-commit, security/types, inventory и baseline integrity SUCCESS.
Merge checkout 01ca2b02 имеет тот же tree a30b662d, что и source.

Новая нижняя граница — 169/512 (33,0%). Проверены cached 200 / empty 204,
одна refresh попытка, breaker accounting и сохранность состояния Spotify.
Другие endpoints, non-transport failures и доступность провайдера не заявлены.
Go security gate и actual NATS observe_runtime остаются открытыми;
полный CI не принят, последний общий checkpoint — e15027a.


## NATS: tests-first диагностика runtime, 2026-10-21 03:08 UTC

Повторный actual прогон b5fd21d8/job 119007865327 подтверждает тот же
observe_runtime отказ после 38 browser PASS / двух skips и Caddy redaction.
Очистка завершена, receipt 12317264520 загружен.

Добавлены проверки конечного набора диагностических этапов, сохранения
порядка daemon/decode guards, отсутствия частных данных, reset и точных
типов CLI. Production API ещё не изменён; ожидаемый missing-API RED пока
не наблюдался. Ledger остаётся 169/512; полного CI/NATS acceptance нет.


## Ограниченная NATS диагностика после RED, 2026-10-21 03:31 UTC

На 20660744 consumer119017866791 подтверждены 23 missing-API FAIL,
1018 PASS / один deselected и 239 policy PASS. Добавлена только типизированная
диагностика: порядок проверок, сроки, owner/daemon guards и cleanup сохранены.
Сырые данные и тексты исключений не выводятся; прежний CLI без метаданных
остаётся неизменным.

Устранены замечания Ruff к raw regex и форматированию. Старый точный schema
contract синхронизирован с конечными полями результата без удаления проверок
приватности и включён в ранний прогон. Собственные GREEN и новая actual
диагностика ещё требуются; неизвестная причина NATS не считается исправленной.
Ledger 169/512, полного CI acceptance нет.


## Уточнение runtime boundary, 2026-10-21 04:03 UTC

Диагностика на 84052b6d: 1043 consumer PASS / один deselected и 239 policy PASS;
статические gates и baseline SUCCESS. Actual Owned119024534410 вновь
останавливается в observe_runtime, но без внутренней метки. Это не доказывает
ошибку Docker: checkpoint включает последующую проверку inventory координатором.

Добавлены tests-first проверки callback/metadata rejection и четырёх конечных
inventory verdicts с valid control. Production не изменён, RED ещё ожидается.
Прежние owner/daemon/health/initializer guards сохраняются. Ledger 169/512;
NATS и общий CI не приняты.


## Coordinator diagnostic после RED, 2026-10-21 04:20 UTC

На 53b39f9c подтверждены 8 ожидаемых FAIL / 1043 PASS / один deselected,
затем 239 policy PASS. Valid control проходит. Координатор теперь различает
callback/metadata boundary и четыре конечных inventory verdicts.
Проверки и порядок допуска неизменны; после valid inventory метка очищается,
при cleanup/later-stage failure не переносится.

Собственные GREEN и actual сигнал ещё ожидаются. Причина реального NATS
отказа не объявлена установленной, ledger остаётся 169/512.


## AUD-465: последовательный tests-first regression

Добавлена HTTP-проверка запрета retry для persisted COMPLETED с localized409
и неизменностью четырёх изменяемых handler полей. FAILED/PENDING/stale RETRYING
сохраняют успешный retry; прежний404 test не изменён. Полный test_api_dlq
включён в ранний прогон. Production пока не изменён, RED ещё не подтверждён.
Worker/admin race не считается покрытым; ledger остаётся 169/512.


## DLQ RED и inventory health, 2026-10-21 04:59 UTC

На ab88b3a consumer 119040647784: один целевой FAIL / 1062 PASS /
один deselected и 239 policy PASS. Completed retry действительно отвечает 200
вместо 409; положительные статусы и прежний 404 проходят. Merge 504f8ae и source
имеют одинаковое tree e5da100e. Статические pre-commit gates SUCCESS.

На 920fb9fb consumer завершил 1051 PASS, но policy step отменился после
следующей публикации; полный GREEN для него не заявлен. Actual Owned
119038246185 после 38 browser PASS / двух skips и Caddy redaction выдаёт
inventory_unhealthy. Конкретный сервис в логах не раскрыт; receipt только
метаданные. В обоих Compose найден inherited HTTP healthcheck у migrations,
который запускает Alembic без HTTP-сервера. Это отдельное статическое
несоответствие, а не доказанная причина actual отказа.

Добавлены tests-first source contracts для обоих Compose и PostgreSQL
worker/admin interleaving через реальный replay worker. Проверка требует
ожидания именно SELECT FOR UPDATE, обновления stale identity-map и сохранения
completed state/timestamps. Production пока не меняется; собственный RED
новых проверок ещё ожидается. Validator и gates не ослаблены.
Ledger 169/512; Go approval, actual NATS и полный CI остаются открытыми.


## Минимальные исправления после RED, 2026-10-21 05:32 UTC

На 19c8c885 PostgreSQL job 119053393266: один целевой FAIL / 53 PASS.
Наблюдатель видит блокировку admin UPDATE, а не SELECT; worker уже завершил
задачу внутри незакоммиченной транзакции. Consumer 119052983397: три целевых
FAIL / 1062 PASS / один deselected и 239 policy PASS. Два новых Compose
контракта падают именно на отсутствующем override. Pre-commit, security/types
и inventory SUCCESS; checkout afc7223 имеет то же tree, что source.

DLQ теперь блокирует и обновляет identity-map при чтении, затем отклоняет
COMPLETED до изменения полей. Прежние 404, остальные retry статусы, auth и
commit сохранены. Для migrations обоих Compose отключён только унаследованный
HTTP probe, неприменимый к Alembic; exit-status и остальные health guards
сохранены. Свежие GREEN и actual стенд ещё требуются. AUD-465 пока не принят,
ledger 169/512, полный CI и Go cooldown approval остаются открытыми.


## Приёмка AUD-465 и следующий tests-first этап, 2026-10-21 05:52 UTC

Принята ровно одна находка: повторный retry завершённой DLQ-задачи.
На 5eda2282 consumer 119058380490: 1065 PASS / один deselected и
239 policy PASS. PostgreSQL integration 119059881779: 210 PASS / девять skips;
реальный worker/admin interleaving именованно PASS. HTTP проверяет localized
409 и неизменность persisted state, а PostgreSQL доказывает ожидание SELECT,
обновление stale identity-map и сохранение результата worker. Pre-commit,
security/types, inventory и baseline SUCCESS; merge 8758cf9 имеет тот же tree.

Нижняя граница теперь 170/512 (33,2%). Это не полный DLQ state-machine,
не общий CI GREEN и не actual NATS acceptance. Go cooldown approval остаётся
открытым; последний полностью принятый CI checkpoint — e15027a.

Следующий AUD-466: tests-first запрет утверждать целостность при
verify_chain=false. Существующие bypass cases сохраняют state assertions,
но требуют False. HTTP добавляет реальное повреждение payload и настоящий
verified-corrupt control, затем bypass без вызова verifier. Empty history
проверяется для обоих значений флага; прежний API 404 сохраняется.
Bool schema не меняется; False означает, что целостность не установлена,
а не обязательно доказанное повреждение. Production audit пока не изменён,
собственный RED ещё ожидается.


Actual Owned на 5eda2282/job 119058318655 прошёл прежнюю проверку runtime
inventory после 38 browser PASS / двух skips и Caddy redaction. Новый отказ
в 05:55:13 UTC: preflight/read_policy. Cleanup и receipt 12324400981 завершены.
Это прохождение прежнего health boundary, но не полный NATS outage acceptance;
теперь отдельно проверяется чтение и валидация policy.


## AUD-466 после RED и Docker formatter regression, 2026-10-21 06:25 UTC

На 72f358b2 consumer 119070082750: десять целевых FAIL / 1172 PASS /
один deselected и 239 policy PASS. HTTP дошёл до ошибочного True при bypass;
настоящий verifier уже обнаружил изменение payload. Положительные controls
и статические gates проходят. Merge 9079763 имеет то же tree, что source.

Изменены только начальное значение validity и empty-window return:
при пропуске проверки False, при запрошенной проверке пустого окна сохранено
прежнее vacuous True. API bool, replay и авторизация неизменны. Собственный
GREEN ещё требуется, AUD-466 не принят; ledger 170/512.

Для NATS найдено несовпадение шаблона и реального Docker CLI: оба добавляют
конечный перевод строки. Добавлены два tests-first запуска настоящего CLI
с изолированным синтетическим API и ограниченными stdout/stderr. Тест не
выдаётся за проверку реального daemon или API negotiation. Production template
и строгий decoder пока не менялись; требуется hosted RED. Go approval и
полный CI по-прежнему открыты.


## Реальный Docker CLI: подтверждённый RED, 2026-10-21 06:46 UTC

На 3373104 consumer 119076006979: два целевых formatter FAIL / 1182 PASS /
один deselected и 239 policy PASS. CLI действительно завершился успешно,
не вывел лишние env-поля и добавил второй конечный LF. Все десять прежних
AUD-466 cases теперь PASS, но приёмка пока не расширяется.

Шаблон теперь добавляет только внутренние разделители, а конечный LF оставляет
Docker CLI. Decoder и все owner/daemon/process/deadline guards неизменны.
Требуются собственный GREEN и fresh Owned acceptance.

Исправлены два статических замечания: вместо неподтверждённых dynamic skips
используется существующий supported-or-fail-closed подход, а assertion оформлен
по hosted Ruff diff. На неподдерживаемом локальном host проверяются реальный
отказ containment и отсутствие spawn; это не formatter coverage. В обязательном
GitHub CI такой путь запрещён, Docker CLI обязателен. Ledger остаётся 170/512;
Go approval и полный CI всё ещё открыты.


## Docker CLI GREEN и синхронизация старого контракта, 2026-10-21 07:06 UTC

На 96c4e47 оба настоящих Docker CLI сценария PASS. Consumer 119082105447:
один FAIL / 1183 PASS / один deselected и 239 policy PASS. Единственный FAIL —
старый source-shape test, требующий ошибочные println-разделители. Обновлены
только эти два ожидания и добавлен запрет прежних выражений; privacy assertions
и реальные CLI-проверки сохранены. Production код в этом follow-up не меняется.

Inventory и security/types SUCCESS. Применён точный оставшийся Ruff wrap
для assertion наличия Docker CLI, без изменения условия. Нужны собственные
чистые checks и actual NATS; AUD-466 пока не принят, ledger 170/512.


Actual Owned 119082103077 на 96c4e47 уже проходит прежние preflight boundaries,
но завершается отказом stage=broker в 07:11 UTC. Cleanup и receipt 12327177966
завершены; полный outage не принят. Причина broker-stage проверяется отдельно.

В 12:28 UTC владелец разрешил точечное досрочное обновление Go 1.26.9 →
1.26.10, fuzz 1.27.2 → 1.27.3 и соответствующих проверенных образов для
GO-2026-6809. Это не разрешение на новые scanner dispositions, подавления,
baseline/gate изменения, merge или deploy. Изменения Go и собственные проверки
ещё предстоят.

### 2026-10-21: owner-approved Go security refresh, validation pending

The owner approved Go 1.26.9 -> 1.26.10 and fuzz Go 1.27.2 -> 1.27.3,
with corresponding verified official image indexes, as a narrow exception
to the seven-day cooldown for GO-2026-6809. Earlier pending-approval notes
remain historical. Source `133f87d` reproduces reachable
`crypto/x509@go1.26.9`, fixed in `go1.26.10`, with exit 3 in the
[required Go vulnerability scan](https://github.com/egorribun/university_ecosystem/actions/runs/39600982588/job/119225455954).

Active toolchain/image pins, benchmark expectations, current developer docs,
and independent assertions are synchronized. The pin contract now covers
all 14 active Go workflows and all nine module files plus the workspace.
Go minimum directives remain 1.26.4. The exact exception and official
provenance are recorded in `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`.

The preceding source `133f87d` has 1,184 consumer tests passing (one existing
deselection) and all 239 policy tests passing, with lint and security/type
hooks successful. Its tested merge `6b2c344` has the identical tree
`a89754933a89dad213e777e6c7a0025bfc9168bb`. These results do not transfer
to the new Go pins: fresh hosted compatibility and security evidence is
pending. No module dependency, scanner disposition, baseline319, required78,
blocking CodeQL, hook, or finite131 migration exception is changed.
No merge or deployment is authorized or performed. Accepted audit progress
remains **170/512**; this refresh does not accept AUD-466 or live NATS.

## Приёмка AUD-466 и tests-first NATS boundary, 2026-10-21

Принята только AUD-466: пропущенная проверка цепочки больше не возвращает
подтверждённую целостность. Source 133f87d и merge 6b2c344 имеют одинаковый tree.
После десяти целевых RED текущие consumer проверки дают 1184 PASS /
один прежний deselected, затем 239 policy PASS. Настоящее повреждение
подписанного события, verified-corrupt control и bypass без вызова verifier
проходят; API bool, права, 404 и replay сохранены. Lint, security/types,
inventory и baseline SUCCESS. Принятый ledger теперь **171/512 (33,4%)**.

Два из четырёх общих backend shard и PostgreSQL на этом source также SUCCESS:
4178 PASS / 52 SKIP; 843 frozen-RC + 226 focused + 4210 PASS / 42 SKIP;
210 PASS / 9 SKIP соответственно. Это не общий CI GREEN: Go vulnerability
gate на 133f87d оставался красным, а опубликованный Go refresh ca6d711
требует собственных доказательств. Полностью принятый checkpoint остаётся e15027a.

Owned 119225099516 снова даёт 38 browser PASS / 2 прежних SKIP, затем stage=broker;
cleanup receipt 12347621017 завершён. Эта метка также охватывает финальную
проверку owner/runtime после валидного broker receipt. Пять существующих
drift cases теперь требуют отдельную final_revalidation boundary, сохраняя
failure, точные send/restore counts, cleanup и финальные owner/runtime reads.
Невалидные receipt остаются на BROKER, успешный путь на COMPLETE.
Это tests-first этап: production не меняется, собственный RED ещё ожидается.

### Go vulnerability GREEN and generated catalog synchronization

On Go-refresh source `ca6d711`, Matrix 39605507434 Go vulnerability job
119242311896 succeeds with the actual Go 1.26.10 toolchain and reports no
reachable vulnerabilities. Some modules retain an uncalled advisory in a
dependency; this is not a claim that every transitive advisory disappeared.
Tested merge `bb82b976f151151fef5730161f1f6097b1be1818` has the identical
tree `14bebdac6f4ae5492b263c2960a35d80b732b9a2`.

Inventory job 119242066552 rejects exactly three stale workflow-call guard
snapshots in `quality/ci-check-catalog.json`, at workflows 34, 38, and 39.
Only their serialized `inputs.go-version.default` values are synchronized
from 1.26.9 to 1.26.10, matching the already-updated reusable cache,
Go integration, and Go test workflows. Validator logic, events, jobs,
classifications, timeouts, artifacts, and required context/app pairs are
unchanged. This is a generated metadata correction after observed RED, not
a gate relaxation; its own source-bound GREEN remains required.

The SBOM read-only producer contract also retains one old compiler expectation
in `tests/contracts/test_ci_release_capacity_contract.py`; only that expected
version becomes 1.26.10. Its credential, permission, scanner, source-ref,
and signing constraints are retained.

The new source scan separately reports one unmatched public image checksum
at `tests/test_docker_startup_contracts.py:3028` (Hex High Entropy String).
The separate exact singleton approval and its bounded policy update are
recorded below. No baseline change is included.

### Owner-approved singleton public Go image checksum, 2026-10-21

The owner explicitly approved the one pending public-integrity identity
reported by source `ca6d711`: `tests/test_docker_startup_contracts.py`,
detector Hex High Entropy String, for the official Go 1.26.10-alpine3.24
image index checksum. Exactly one record is added under the existing
`public_integrity_digest` category, reviewed 2026-10-21 and expiring
2027-01-10. All prior 283 records remain unchanged, for **284** total.
The independent source-binding test fixes the expected finding identity
and checks the real source literal, owner, category, approval, and dates.
No raw checksum is duplicated here. No baseline, validator, suppression,
hook, required context, or other identity is changed.

This approval is separate from the compiler cooldown exception. On `ca6d711`,
consumer job 119242066749 logs seven failures (six stale catalog controls
and one old SBOM Go expectation), 1,177 passes, and one deselection in
490.18 seconds. Its subsequent policy step logs all 239 passes in 54.03
seconds, although the job's final metadata is cancelled; this is not a
successful job claim. The two observed source mismatches are corrected in
this slice. Fresh hosted scans and tests, and the expected five NATS
stage-regression failures, remain to be observed before production changes.

## Ранний NATS cohort и Go-policy GREEN, 2026-10-21

На a9841d6 consumer 119252013903: 1184 PASS / один прежний deselected,
затем 240 policy PASS. Lint, security/types, inventory и baseline integrity
SUCCESS: согласованный singleton и source-binding test проверены на своём source.

В раннем cohort раньше были только две функции coordinator-модуля. Поэтому
его GREEN не запускал пять новых final-revalidation cases и не заменяет RED.
Теперь ранний прогон добавляет пять final-drift cases, три invalid-receipt cases
и valid-path control, сохраняя оба прежних selector. Десятиминутный бюджет
job и полный backend сбор не меняются; production stage ещё не исправляется. Ledger остаётся 171/512.

Уточнение отчёта: backend matrix содержит четыре legs с max-parallel 2.
Предыдущие результаты подтверждали два названных unit shard и PostgreSQL,
не всю backend matrix и не общий CI GREEN.

## NATS stage RED и tests-first AUD-256, 2026-10-21

На adb02d37 consumer 119261108734 даёт ровно пять целевых FAIL /
1188 PASS / один прежний deselected, затем 240 policy PASS.
Все пять отказов доходят до сравнения broker с final_revalidation,
после failure/count/cleanup и owner/runtime assertions. Невалидные
broker receipt и успешный restored path проходят.

Production меняется ровно в двух местах: новый конечный stage label и его
назначение после успешного _delivery, перед финальным _complete_inventory.
Guard, restoration, deadline, polling и cleanup не ослаблены; требуется
собственный GREEN и actual Owned сигнал. Полный outage ещё не принят.

Следующий AUD-256 пока только tests-first: восемь строковых границ для
Create/Update после прежней нормализации; Text поля не ограничиваются.
Смешанные naive/aware даты должны давать 422, а допустимые пары и порядок
по абсолютному времени сохраняются. HTTP PATCH проверяется на реальной
сохранённой записи с реальными auth/service/DB и только разрешающим
permission checker. Проверяются отсутствие изменения данных после 422,
title-only PATCH без изменения времени и внутренний partial-time merge
с awareness, прочитанной из БД. Тесты явно включены в ранний cohort;
бюджет и полный backend сбор неизменны. Production событий не меняется,
RED ещё требуется. Ledger **171/512**, общий CI и NATS acceptance открыты.

## Уточнение AUD-256 и NATS unit GREEN, 2026-10-21

На 4e7a843 consumer 119270267303: 61 FAIL / 1228 PASS /
один прежний deselected, затем 240 policy PASS. Пять NATS stage cases
теперь проходят; actual outage этим не подтверждён.

Из 61 отказа 14 были ошибками ожиданий тестов: базовый SecureBaseModel
уже удаляет крайние пробелы, TAB/LF и другие whitespace до AfterValidator.
Эти ожидания исправлены, а внутренние TAB/LF проверяются отдельно.
Остальные 47 отказов показывают отсутствие нормализованных строковых
границ или TypeError при mixed naive/aware. Настоящие title-only HTTP
и внутренний partial-time merge проходят.

PostgreSQL допускает только ASCII-пробелы за VARCHAR-границей. На API
эта особенность применима после CleanStr, когда удаление NUL открывает
прежде защищённые от первого trim пробелы. Новый real-PG модуль проверяет
восемь колонок через ORM INSERT/refresh и savepoints, без CAST/bulk-delete;
его hosted evidence ещё требуется. Production событий пока не изменён.

Убрана ровно одна лишняя пустая строка импортов по hosted Ruff diff.
Владелец отдельно разрешил только line_number 22 -> 29 у прежней записи
baseline. Все 319 identity, пути, типы, hashes, статусы и generated_at
неизменны; policy 284 и ledger 171/512 сохраняются. Свежие checks требуются.

После подтверждённого завершения текущей AUD-256, по новому поручению
владельца: пересмотреть весь оставшийся аудит, сначала закрывать самые
простые и быстрые находки, затем повышать сложность с учётом зависимостей.
Уже принятые находки не пересчитывать; NATS/full-CI остаются отдельными
открытыми проверками.


## AUD-256: фактическая схема и частичное исправление времени

На source `2f30d813` / merge `f3ee0dfa` с одинаковым tree
`26470d8294615aa9cf023a18e025946fa52d96cc` consumer дал
83 FAIL / 1228 PASS / 1 deselected (469.52 s), затем policy 240 PASS
(45.25 s). Static lint, types/security, inventory и baseline зелёные.

PG job 119285838468 остановился на 1 FAIL / 28 PASS: title длиной 513
сохранился после refresh. Исторические миграции оставляют String без длины;
ограничение ORM не изменяет уже созданную таблицу. Предыдущее предположение
теста об обязательном физическом VARCHAR(512) неверно. Проверки разделены
на фактические мигрированные Event и изолированный bounded VARCHAR;
их новые результаты ещё требуются.

Внесено только совместимое исправление mixed naive/aware: ValidationError
вместо TypeError, без изменения допустимых пар и partial-update правил.
API 1.1.1 и info.version обоих OpenAPI согласованы; MVP 1.0.0 неизменён.
Новые ограничения строк API ожидают отдельного точного согласования
владельца. AUD-256 не закрыт; ledger **171/512**. Own-source GREEN
ещё не заявлен. После завершения находки остаётся поручение разобрать
весь остаток аудита и идти от простого/быстрого к сложному.

Owned 39617731487/job119282959917 снова остановился на broker
(14:50:51 UTC), до final revalidation; receipt12354910829 сохранён.
Это отдельный незакрытый блокер, не успешная приёмка NATS.


## AUD-256: подтверждение SQL-схемы и исправление ожидания драйвера

Source `234280b` и merge `30c917ed` имеют одинаковый tree
`c81c932d6b2edd740210552cf46ea1fabf00144b`.
PG job119307242894 подтвердил unbounded metadata всех восьми колонок,
восемь ORM round trips длинных значений и по восемь bounded-проверок
ASCII-пробелов и Unicode. Первый отрицательный пример действительно
отклонён PostgreSQL, но asyncpg/SQLAlchemy использует DBAPIError вместо
ожидавшегося DataError: итог 1 FAIL / 53 PASS, 91.21 s.
Исправлены только импорт/ожидание класса; обязательный SQLSTATE 22001
и savepoint сохранены. Остальные отрицательные случаи требуют нового прогона.

OpenAPI/Spectral39623956662 и отдельный Contract Tests39623957288 зелёные.
Это не общий GREEN Matrix и не закрытие AUD-256. Ограничения строк остаются
на согласовании; ledger **171/512**, новые миграции и обрезка данных отсутствуют.


## AUD-256: согласованы и внесены ограничения входных строк

2026-10-21 в 16:31 UTC владелец разрешил точное исключение совместимости
API v1 для AUD-256: 512/128/2048 символов по согласованным полям после
существующей нормализации. Описания не ограничиваются; существующие данные
не изменяются, миграции и новый router не добавляются. Новые after-валидаторы
отклоняют непустое не-пробельное превышение с 422 и сохраняют узкую
нормализацию excess ASCII spaces, соответствующую bounded VARCHAR.
API policy документирует осознанное сужение ранее допустимого ввода.

Предыдущий source `e6afe376` / merge `5fc33f83` имеет tree
`e685c6c6df967d38d18535441878b98b7ba77eeb`.
Consumer119313051165: 76 length-only FAIL / 1235 PASS / 1 deselected,
425.29 s; policy240 PASS, 43.36 s. Исправление времени проверено.
PG119314226606: все 57 AUD-256 PASS; весь shard267 PASS / 9 SKIP,
240.22 s. OpenAPI, lint, inventory, baseline, types/security зелёные.
Эти результаты относятся к предыдущему source, не к новой реализации.

Ledger остаётся **171/512** до own-source приёмки AUD-256.
После её завершения: полный разбор остатка аудита, сначала самые простые
и быстрые находки, далее по нарастающей сложности с учётом зависимостей.


## Приёмка AUD-256 и переход к полной очереди остатка

Принята только AUD-256: **172/512 (33,6%)**, остаются 340 исходных IDs.
Source `c1aed673` / merge `28a17a87`, одинаковый tree
`89e9a60c8e7edabc44a372aa8ad479362bbaf97d`.
Consumer119368407218: 1311 PASS / 1 deselected, 478.58 s; policy240 PASS,
48.41 s; все 114 event API cases и internal partial-time control прошли.
PG119369545215: все57 AUD-256 PASS; весь shard267 PASS / 9 SKIP,231.59 s.
Lint, types/security, inventory, baseline, spelling/Markdown, OpenAPI и
migration gates зелёные. Это scoped приёмка, не полный global CI/NATS.

Начат полный разбор остатка аудита: сначала простые и быстрые независимые
находки, затем сложнее с учётом зависимостей. Отдельно появился блокер
Dependency Review: virtualenv21.14.5 / GHSA-vxj4-q4g9-crj7.
Исправленная21.14.7 выпущена12 октября и не требует обхода cooldown.
В текущем tests-first checkpoint добавлена проверка dev-only floor/lock;
пакет ещё не обновлён. Также в ранний cohort включён существующий
scanner-bootstrap guard для наблюдения устаревшего ожидания Go1.26.9.
Timeouts, required78, baseline319, policy284 и finite131 не изменены.


## Быстрые подтверждения и полная очередь: 174/512

Приняты только AUD-142/143 сверх предыдущих172: **174/512 (34,0%)**,
остаются338 IDs. weatherCodes прошёл3 теста в job119379643479 на b7549f87.
MapSidebar и buildingHours прошли7+16 тестов в jobs119369639102/119369639034
на c1aed673. Полное frontend-поддерево обеих ревизий одинаково:
`d9123a1d5501c8e967e0a9a5bee1ea6605adac46`. Это scoped доказательства,
не общий GREEN текущего HEAD. Изменять уже исправленный frontend не нужно.

Первичный разбор всех512 исходных записей и точная сверка accepted set
завершены. Весь остаток338 распределён без пересечений:16 quick/local или
verification,113 moderate,84 complex/dependent,125 требуют уточнения.
Точные ID-наборы и условия приоритета приведены в checkpoint174 аудита.
Начальная очередь:496; подтверждения148 и353/367/448; маленькие042/410;
далее421/424/437,355,395,398 и037. Не подменять source-проверку угадыванием:
318,396,488 и Windows-зависимый502 требуют дополнительных условий.

Текущий slice исправляет отдельный dev-tooling blocker virtualenv до21.14.7
без обхода cooldown и обновляет два устаревших ожидания Go до1.26.10.
Предыдущий consumer119378763256 дал ровно2 ожидаемых FAIL / 1311 PASS /
1 deselected,511.44 s; policy240 PASS,45.12 s; финальный job cancelled,
поэтому это не GREEN. Новые hash-install/lock/scanner результаты требуются.

Добавлены tests-first042/410 и точные lifecycle guards для будущего
DB-only ускорения67 policy-функций. Fixtures/GC/task cleanup пока не
изменены; все240 policy-кейсов,10-minute budget, baseline319, policy284,
required78 и finite131 сохраняются. Для496 удалён только ложный комментарий,
приёмка ожидает проверки. NATS/global CI остаются отдельными блокерами.


## Следующая небольшая пачка после подтверждённого RED

Принятая нижняя граница остаётся **174/512**. На 011f6ea5 consumer
119401701428 дал ровно 6 ожидаемых FAIL / 1322 PASS / 1 deselected
(484,78 s), затем policy: 240 PASS (47,23 s). Source и tested merge
95347342 имеют одинаковое дерево. Это не общий GREEN.

Исправлены причины AUD-042/410 и добавлен отдельный DB-only профиль
для 67 ранее проверенных policy-функций. GC, отмена задач, session teardown
и все проверки сохраняются; ускорение ещё нужно измерить. Применён
точный Ruff diff двух конструкций CLI-теста. virtualenv 21.14.7 уже прошёл
lock/hash-install, Dependency Review, Python audit и security/baseline gates.

Подготовлены корректировки документации AUD-421/424/437 с контрактами,
ранние проверки существующих исправлений AUD-148 и AUD-353/367/448,
а также tests-first AUD-355 без изменения management-кода. Эти находки
пока не добавлены в accepted set; AUD-496 также ждёт итоговой проверки.

Владелец отдельно одобрил обновление immutable helper pin на ca6d7117
и ровно 10 новых публичных provenance identities в двух согласованных
файлах. Реестр дополнен с 284 до 294, прежние записи неизменны,
expiry 2027-01-10. Новый точный policy-тест добавляет один кейс и не
включён в DB-only exemption. Baseline 319, required 78, Gitleaks 25,
CodeQL, finite 131, benchmark population/threshold и лимиты времени
не меняются. Нужны результаты нового HEAD; merge/deploy не выполнялись.


## Проверка b531 и следующая точечная коррекция

Accepted set пока **174/512**. На b5313982 consumer 119413064562:
1347 PASS / 2 ожидаемых UUID FAIL / 1 deselected, 424,68 s.
Policy: все 241 PASS, 40,80 s. Исправления CLI/mypy, lifecycle-профиль,
async duplicates, backend GraphQL 404, CDC/config и helper pins прошли.
Security/types, inventory и baseline также прошли. Последний подтвердил
319 baseline findings и 242 совпавших reviewed identities из реестра 294.

Остаётся одно замечание Ruff к переносу predicate в новом policy-тесте;
из-за него документационные и другие downstream gates были skipped,
не GREEN. Точный formatter diff применён вместе с UUID parser fix.
Также исправлены обе версии DEPLOY для AUD-318 с контрактом фактических
metric factory keys. AUD-037 пока tests-first, с быстрым frontend запуском.
Новые находки не засчитываются до оставшихся проверок; глобальный GREEN,
merge/deploy и дополнительное ускорение не заявлены.


## Принятая пачка: 186/512

На ed8ca1e6 приняты AUD-042/148/318/353/355/367/410/421/424/437/448/496:
**186/512 (36,3%)**, остаток **326**. Consumer 119421189861:
1352 PASS / 1 deselected; policy: 241 PASS. Линтеры, security/types,
inventory, baseline и CSpell/Markdown прошли. Три нужных Go lint jobs
и gateway GraphQL retirement test тоже прошли; source/merge trees совпали.
Независимая scoped-проверка подтвердила приёмку.

GraphQL-находки закрыты только удалением backend endpoint по ADR-046,
не исправлением оставшегося внутреннего кода; AUD-368 остаётся отдельно.
Для CLI проверен SQLAlchemy API, не соединение с реальным PostgreSQL.
Для AUD-355 реальное состояние пользователей/MFA не менялось.

AUD-037 дал ожидаемый frontend RED (1 FAIL / 49 PASS); total-length guard
применён и ждёт GREEN. AUD-395/396 теперь tests-first без правки компонентов.
Для 396 исправляется экспортируемый компонент, не текущий live route.
Уточнённая очередь: 5 quick, 112 moderate, 84 complex, 125 uncertain.

Глобальный CI не GREEN. npm audit сообщил IDs 1242747/1242753 при
неизменном lock; точные пакеты ещё устанавливаются. Добавлен только
failure-only диагностический вывод публичных metadata, исходный audit
остаётся blocking, allowlist и порог не меняются. NATS также остаётся
отдельным глобальным вопросом. Baseline 319, policy 294, required 78,
Gitleaks 25, CodeQL и finite 131 сохранены. Merge/deploy не выполнялись.


## Два подтверждения и следующие быстрые регрессии: 188/512

Приняты только AUD-037 и AUD-502 сверх прежних 186: **188/512 (36,7%)**,
остаток 324. На 560adf6e / tested merge 08ad0ab2 trees совпали.
Граничные 48/49 символов AUD-037 прошли, frontend lint/format тоже.
AUD-502 закрыт как ложная находка исключительно о названии теста:
имя уже соответствовало assertions на исходном audit HEAD. Новая
Windows runtime-проверка не заявлена; код и имя не менялись.

Consumer 119432893457: 1353 PASS / 1 deselected, 492,30 s;
policy: 241 PASS, 42,78 s. Оба шага завершились до новой публикации.
В frontend quick cohort ровно четыре ожидаемых AUD-395/396 FAIL и
91 PASS. Теперь применены переводы OTP label и h2 для дней, со h1
в Storybook fixture. Их новая приёмка требует GREEN следующего source.

AUD-398 пока tests-first: изолированный временный fixture проверяет
реальную ordinary Playwright config через collection без браузера/server,
с контрольным запуском вне CI. Production forbidOnly ещё не добавлен.
Независимый quick Vitest cohort запускается после Node failure, но не
после cancellation; общий job сохраняет failure, проверок не убавлено.
Очередь: 3 quick, 112 moderate, 84 complex, 125 uncertain.

Два npm IDs оказались одним critical GHSA-f2ph-cmg5-wxc8 для Storybook
и addon-vitest. Исправление 10.6.2 от 12 октября старше cooldown;
обновление готовится без исключений. Описанный риск касается dev-server,
открытого в браузере, а не статической Storybook сборки. Global CI/NATS
не приняты; baseline 319, policy 294, required 78 и прочие границы прежние.


## Проверка AUD-150 и исправление Storybook

Нижняя граница **189/512 (36,9%)**, остаток323. Добавлен только AUD-150:
три scope-регрессии прошли в119432893457, проверяемые файлы совпадают
с текущими. Существующая реализация уже корректна, лишней правки нет.
AUD-149 получает два существующих Go masking-теста в раннем cohort;
приёмка ждёт hosted PASS. Очередь:3 quick,111 moderate,84 complex,125 uncertain.

Storybook обновлён согласованно до10.6.2, Chromatic addon до5.5.1.
Обе версии от12 октября старше cooldown; исключения не нужны.
Изменены11 package entries и root lock floors, остальные2377 сохранены.
Integrity metadata взяты из immutable публичного lock, обычный npm ci
ещё должен подтвердить загрузку. Добавлены floor/alignment contract и
bounded static Storybook build без dev-server, публикации, токена или
ослабления origin-защит. Chromatic workflow не включается.

Новое npm audit/static build и общий CI ещё не приняты; NATS остаётся
отдельно. Required78, baseline319, policy294, Gitleaks25 и finite131 прежние.


На a7fabb quick Vitest прошёл95/95, frontend lint/format тоже. Node suite:
657 PASS и один ожидаемый AUD-398 FAIL: CI ошибочно принял focused fixture,
при успешном контрольном запуске вне CI. Добавлен только forbidOnly для CI.
Security/types прошёл mypy, но detect-secrets потребовал metadata refresh:
одна прежняя запись en/auth.json сдвинулась211→212; применён точный hosted
diff с timestamp19:42:39. Все319 identities и флаги неизменны.
AUD-395/396 пока не засчитаны до чистой повторной проверки.


Следующая verification-only пачка: AUD-020/021/074/217/222. Текущий код
уже содержит исправления; существующие suites включены в quick cohort,
для категории добавлены явные «Мастер-класс»/Workshop cases с одинаковыми
canonical metadata. Production-код этих пяти находок не меняется,
новая приёмка пока не заявлена.


## Проверенная нижняя граница: 205/512

На c6cc7816 / merge04bf9b7f с одинаковым tree приняты ещё16 IDs:
020/021/074/141/149/152/153/209/210/213/215/217/222/395/396/398.
Итого **205/512 (40,0%)**, остаток307:98 moderate,84 complex,125 uncertain.
Исходная quick-очередь исчерпана. Точные ID и границы доказательств в аудите.

Все четыре frontend shard дали9631 PASS; aggregate/differential coverage,
production build, lint, security/types, inventory и baseline прошли.
Node658/658, worker/export55/55, quick120/120. Storybook прошёл установку,
blocking npm audit, Dependency Review и статическую сборку без исключений.

Consumer1356 PASS/1deselected за511,41s, но отдельная policy-проверка
прервана около91% фиксированным10-minute budget. Это не GREEN; GC,
лимит и тесты не ослабляются. После terminal всего run один точный retry
принят в20:45 UTC: job119475683195 завершился успешно, consumer1356 PASS /
1deselected за463,51s, затем policy241 PASS за52,51s. Первый запрос был
отклонён как already running; обхода не было. Другие jobs не перезапускались.

Полные backend shards обнаружили две отдельные несогласованности:
устаревший localhost вместо127.0.0.1 для readiness и лишний continue-on-error
у npm-диагностики. Исправляются только ожидание URL и ненужный флаг
с прямым контрактом, без расширения исключений или изменения readiness.

Следующие036/049/196/199 получают проверку существующих исправлений,
050 и220 остаются tests-first без production-правки до RED. Для214
добавлены недостающие error-state tests. AUD015 ждёт extraction/render PDF.
Owned Live прошёл38 browser cases/2SKIP и Caddy redaction, затем отказал
на NATS stage=broker. Global CI/NATS и релиз не приняты; merge/deploy нет.

Все пять обнаруженных CI-контрактов добавлены в ранний запуск; consumer и policy
выводят20 slowest durations без смены fixtures, выборки или бюджета.
Данные нужны до любого предложения менять GC; оптимизация не предполагается.

Shard3 завершился: 5998 PASS / 38 SKIP / 3 FAIL устаревших ожиданий.
Синхронизируются только test literals Go1.26.10 и API1.1.1; последнее
подтверждено commit234280b и не равно версии MVP/package. Для Caddy
меняется только ожидаемый log deadline110 при сохранении общего125,
финального отказа125.001 и всех production timeout/ownership guards.
Всего13 новых selector entries дают21 case:16 audit и5 CI-регрессий.
Свежие hosted проверки исправлений ещё требуются.


## Подтверждённые существующие исправления: 210/512

Приняты AUD-036/049/196/199/214: **210/512 (41,0%)**, остаток302
(93 moderate,84 complex,125 uncertain). Source dbb586 / merge0e0a8b52
имеют одинаковое полное дерево. Подробные границы приёмки в аудите:
UUID cleanup SQL, DM/group lookup, публичные имена без email, campus-timezone
отображение и EventsList error/empty/cache/offline states. Это scoped
unit/test-database/component evidence, не новое live DB/browser acceptance.

Contract119482431331:1376 PASS/1 ожидаемый AUD-050 UUID FAIL/1deselected,
509,77s. Все пять исправленных CI-контрактов прошли. Policy напечатала
241 PASS за40,18s, затем step/job cancelled при фиксированном10-minute cap.
Общий job не GREEN. Durations выявили readiness5,56s и повторные catalog
cases около3s; GC, cleanup и бюджеты не меняются без отдельных доказательств.

Frontend quick119484393637:154 PASS/2 ожидаемых AUD-220 FAIL;
полный shard1:2698 PASS/те же2 FAIL. Все9 EventsList cases прошли,
lint/format и production build тоже. Теперь внесены минимальные исправления:
новый JSON-compatible wire payload без мутации исходного сообщения и
настоящие кнопки выбора обложки с отдельными скрытыми inputs.
AUD-050/220 ждут собственный GREEN и пока не засчитаны. Baseline319,
policy294,required78,Gitleaks25,CodeQL и finite131 прежние; NATS/global
CI не приняты, merge/deploy отсутствуют.


## AUD-050 и AUD-220: подтверждённый RED → GREEN

Приняты только AUD-050/220 сверх210: **212/512 (41,4%)**, остаток300
(91 moderate,84 complex,125 uncertain). Source1684c437 и mergec69f4aa5
имеют одинаковый treefcb209a9. Contract119492368556 SUCCESS:
1377 PASS/1deselected за465,46s, затем241 policy PASS за34,28s;
оба шага и cleanup завершены до следующей публикации.

Реальный Starlette JSON boundary теперь принимает plain и UUID chat/reply
payload без мутации исходного объекта. Оба story-cover контрола прошли
Tab/Enter/Space на настоящих DOM-кнопках с отдельными скрытыми inputs.
Frontend119493833385:658Node/55worker/156quick PASS; lint, build,
security/types и fast lint также прошли. Full frontend shards1/2 PASS,
остальные пока выполнялись. Это не global CI/NATS или OS-dialog acceptance.

Следующий шаг ускорения пока tests-first: две проверки реального YAML
loader запрещают повторный parse в одном вызове, требуют видеть изменение
valid source в следующем вызове и fail-closed отказ на неучтённом malformed
workflow. Trigger key on сохранён корректно после PyYAML round-trip.
Validator пока не меняется; global cache, урезание тестов/GC и увеличение
таймаута не вводятся. Приёмка ускорения требует RED, реализации и измерений.
Все security/coverage границы сохранены, merge/deploy не выполняются.


## Устранение повторного YAML parse после измеренного RED

На1f00f10 consumer119500457771:1378 PASS/1 ожидаемый parse-count FAIL/
1deselected за548,77s. Все workflow читались минимум дважды, ci.yml шесть
раз. Malformed unlisted control прошёл. Policy cancelled около37% при
прежнем10-minute cap; lint потребовал только убрать пустую строку импорта.
Теперь parsed map живёт ровно один вызов validate_catalog и разделяется
между timeout inventory, catalog и expansion checks. Следующий вызов
читает источник заново; все проверки, fixtures, GC и бюджеты сохранены.
Собственные GREEN и измерение ускорения ещё нужны, не заявлены заранее.

AUD-163 получает три существующих raw-header теста в раннем запуске;
новой приёмки пока нет, ledger212/512. Новый high advisory virtualenv
GHSA-c978-59m8-c77v требует21.14.9 от17октября; точное cooldown-исключение
запрошено, но пока не одобрено. Обычный cooldown заканчивается24октября
16:09:47UTC. Пакеты, исключения и политики не меняются до решения.
NATS/global CI остаются открытыми, merge/deploy не выполняются.


## AUD-163 и измеренный результат catalog validation

Принята только AUD-163: **213/512 (41,6%)**, остаток 299
(90 moderate, 84 complex, 125 uncertain). Source 21bfb48 / merge 09c1a2a9
имеют одинаковый tree c3581713. Contract job 119507854319 — SUCCESS:
1382 PASS / 1 deselected за 245,64 s, затем 241 policy PASS за 20,27 s
и штатный cleanup. Три raw-ASGI-header cases подтверждают lowercase имена
и неизменные значения. Handler уже исправлен, новой правки не требуется.

Catalog parse-once/fresh-next-call и malformed-unlisted tests прошли.
Предыдущие 548,77 s против наблюдаемых 245,64 s не считаются строгой
атрибуцией всего ускорения: runners/load различаются. Повторный parse
устранён прямо проверяемым контрактом; tests/GC/fixtures/security/budget
сохранены. Lint, security/types и inventory также PASS, но global CI/NATS
не приняты.

Следующая AUD-044 пока tests-first: три случая UUID group/user settings
через CSV и JSON-list env, invalid-token filtering и сохранение порядка
и повторов. Используется настоящий CacheSettings; production parsing
не меняется до RED. Общий integer parser для image widths не затрагивается.
Ledger не включает AUD-044. Virtualenv 21.14.9 ждёт точное cooldown-разрешение
владельца; пакеты и политики не меняются. Все finite security/coverage
границы сохранены, merge/deploy нет.


## AUD-044: подтверждённый RED и локальное исправление

На c1acbfc / merge bbfe99bd с одинаковым tree b7feb8f2 получены ровно
три ожидаемых FAIL, 1382 PASS / 1 deselected за 400,85 s; затем policy:
241 PASS за 37,35 s. CSV терял UUID при integer coercion, JSON-list
отклонялся типом list[int]. Lint, security/types и inventory прошли.

Два поля принимают строки или списки строк; локальный UUID parser
сохраняет порядок/повторы и пропускает invalid tokens. Cached properties
возвращают UUID tuples. Общий integer parser для image widths не меняется.
Старый integer-only fixture приведён к реальному UUID-домену с сохранением
проверок фильтрации и нормализации периодов. Четыре прежних input/fan-out
теста добавлены в ранний запуск. Реальные данные и миграции не затронуты.

AUD-044 ждёт final-source GREEN и остаётся OPEN; ledger 213/512.
Virtualenv cooldown-разрешение пока не получено, пакеты и security policy
не меняются. Global CI/NATS не приняты, merge/deploy отсутствуют.


## AUD-044 принята; AUD-039 получает реальный deadline-тест

Принята только AUD-044: **214/512 (41,8%)**, остаток 298
(89 moderate, 84 complex, 125 uncertain). Source 4e71749 / merge e9fa51e5
имеют одинаковый tree 2f934215. Contract 119521583099 — SUCCESS:
1387 PASS / 1 deselected за 411,13 s, затем 241 policy PASS за 35,61 s.
Все семь целевых UUID/config/fan-out случаев прошли; lint, security/types
и inventory также PASS. Это не новая live-проверка наполнения кеша.

Для AUD-039 старый mocked timeout oracle заменён настоящей coroutine,
которая выдерживает повторную cancellation до release Event. Внешний
bounded asyncio.wait проверяет возврат shutdown и сохранение ownership;
finally освобождает и ограниченно дожидается обеих задач, затем callback
подтверждает удаление из registry. Новых sleeps и mocked wait/gather нет,
остальные пять тестов сохранены. Production пока не меняется до RED.
Гарантия касается ограниченного ожидания, не принудительного завершения
Python coroutine или процесса. AUD-039 остаётся OPEN.

Virtualenv cooldown-решение ещё ожидается; пакеты и политики не меняются.
Global CI/NATS не приняты; все finite security/coverage границы сохранены,
merge/deploy не выполняются.


## Точное разрешение virtualenv 21.14.9

Владелец разрешил обновление 21.14.7 → 21.14.9 раньше cooldown
2026-10-21 в 22:44 UTC для GHSA-c978-59m8-c77v. Меняются только dev floor,
сам пакет и root metadata в lock, точный constraint/cutoff и их контракты.
Остальные 228 package records, транзитивные версии, certifi/Pillow и общий
семидневный срок сохранены. Cutoff по двум проверенным артефактам:
2026-10-17 16:09:43 UTC; пересмотр после 2026-10-24 16:09:43 UTC.

Временный bounded hosted шаг сверяет официальные PyPI metadata и targeted
uv regeneration с подготовленным lock, требует отсутствия drift и всегда
восстанавливает исходный lock перед штатным gate. Новая проверка, hash-install
и vulnerability gates ещё не приняты. Старые созданные environments требуют
отдельного пересоздания; lock edit не исправляет их автоматически.
Ledger 214/512, AUD-039 ждёт собственный GREEN реализации. Global CI/NATS не приняты;
новых scanner dispositions, baseline edits, merge/deploy нет.


## AUD-039: реальный RED и ограниченное ожидание

На d35b3b job 119528458081 дал ровно один ожидаемый deadline FAIL,
1387 PASS / 1 deselected за 461,64 s; finally освободил и дождался задачи.
Затем все 241 policy cases прошли за 48,66 s. Теперь shutdown отменяет
snapshot и ожидает через asyncio.wait с прежним timeout, не забывая pending
задачи. Их прежний callback сохраняет cleanup и error logging. Это не
принудительное завершение coroutine/процесса. В ранний запуск включён весь
модуль из шести тестов, без ослабления остальных проверок. AUD-039 остаётся
OPEN до собственного GREEN; ledger 214/512.


## Проверка AUD-039 и очистка временного CI-шага

На a91cbd8a / merge 67e217c6 с одинаковым tree 5b33a252 Contract
119542344789 завершился SUCCESS: 1393 PASS / 1 deselected за 427,51 s,
затем 241 policy PASS за 37,28 s. Все шесть TaskRegistry cases прошли.
Это scoped-доказательство deadline/ownership, не гарантия остановки процесса.

В job 119542345095 прошли официальные PyPI metadata, byte-identical targeted
uv regeneration, обычный lock check, hash-install и lint. Python/npm audit
и Dependency Review также PASS. Отработавший временный шаг из 64 строк
удаляется; точный pin/cutoff и штатные проверки сохраняются.

Security/types 119542345187: mypy PASS, detect-secrets FAIL только из-за
сдвига двух прежних ci.yml baseline line numbers на 64. Удаление шага
возвращает строки 910/920 без изменения baseline identities или настроек.
Свежий чистый scanner ещё нужен; AUD-039 пока не засчитана, ledger 214/512.
Global CI/NATS не приняты. Все finite security/coverage границы сохранены.


## AUD-039 принята; AUD-041 получает реальные lifecycle-тесты

Принята только AUD-039: **215/512 (42,0%)**, остаток 297
(88 moderate, 84 complex, 125 uncertain). Source 951c8435 / merge db17a927
имеют одинаковый tree d030fdc9. Contract 119558096029 SUCCESS:
1393 PASS / 1 deselected за 395,92 s, затем 241 policy PASS за 48,25 s.
Все шесть TaskRegistry случаев прошли после ранее подтверждённого RED.
Гарантия ограничивает ожидание и сохраняет ownership, но не принуждает
Python coroutine или процесс к завершению. Lint 119558095217,
security/types 119558095588 и inventory 119558095354 также PASS.

Три tests-first случая AUD-041 используют настоящий двухместный async
SQLite pool и production listeners: обычный возврат, hard invalidation
с немедленным checkin и повторным использованием записи, idle invalidation
при другом активном соединении. AsyncExitStack освобождает соединения
до dispose. Отдельный файл сохраняет прежние tests и baseline metadata.
Production accounting не меняется до hosted RED; AUD-041 остаётся OPEN.
Это не live PostgreSQL acceptance. Global CI/NATS не приняты; все finite
security/coverage границы сохранены, merge/deploy нет.


## AUD-041: реальный RED и минимальное исправление учёта

На ccda0777 / merge f699bb55 с одинаковым tree abd2ccd5 получены ровно
два ожидаемых active-count FAIL: hard invalidation/checkin и idle invalidation
показывают 0 вместо 1 при другом выданном соединении. Обычный возврат PASS.
Contract 119562921244: 1394 PASS / 2 FAIL / 1 deselected за 405,50 s;
затем 241 policy PASS за 34,35 s. Lint 119562921454, security/types
119562921525 и inventory 119562921474 прошли.

Теперь invalidation увеличивает только свой счётчик событий. Active меняют
только checkout/checkin под прежним lock; hard invalidation сам вызывает
checkin, а idle invalidation не освобождает чужой checkout. Состояние,
markers и callback signatures не добавляются. Два прежних unit-ожидания
приведены к этой семантике с сохранением snapshot/peak/total проверок
и проверкой последующего checkin до нуля. Три реальных теста неизменны.
Прежние metric и structured-log controls добавлены в ранний запуск.

AUD-181 получает три существующих route-теста sanitization/overlong/empty.
Исправление в source уже есть, production news код не меняется.
AUD-041 и AUD-181 пока OPEN; ledger 215/512 до собственного GREEN.
Global CI/NATS не приняты; все finite security/coverage границы сохранены.


## AUD-041 и AUD-181 приняты: 217/512

Добавлены только AUD-041 и AUD-181: **217/512 (42,4%)**, остаток 295.
Source a8851ce5 / merge 1c1d1f9a имеют одинаковый tree 4f813695.
Contract 119568381119 SUCCESS: 1406 PASS / 1 deselected за 437,86 s,
затем 241 policy PASS за 37,93 s. Оба шага и cleanup завершены.

Два реальных lifecycle RED для AUD-041 теперь GREEN без изменения тестов;
обычный возврат, повторное использование записи и metric/log controls тоже
прошли. Это SQLAlchemy/aioSQLite evidence, не live PostgreSQL failover.
AUD-181 подтверждена тремя route-bound cases: sanitization перед записью,
overlong rejection без записи и sanitized-empty rejection. Исправление
уже существовало; production news код не менялся. Это не новая live
HTTP/browser или authorization-проверка.

Lint 119568380799, security/types 119568380942 и inventory 119568381065 PASS.
Frontend contract 119569005088 также PASS; все shards ещё не завершились.
Global CI/NATS не приняты, общий GREEN не заявлен.

Для AUD-057 существующий MapSidebar branch suite добавлен в ранний cohort.
Component/tests неизменны; window resize/snap/custom height/cleanup ждут
hosted-подтверждения. VisualViewport-only keyboard/browser-chrome поведение
этими тестами не доказывается. AUD-057 пока OPEN. Все finite security/
coverage границы сохранены, merge/deploy нет.


## AUD-057 принята; AUD-157 получает tests-first проверку

Добавлена только AUD-057: **218/512 (42,6%)**, остаток 294.
Source 80b7fc98 / merge d27d8e4a имеют одинаковый tree f69ba7a9.
Frontend contract 119574090693: 658 Node / 55 worker / 181 quick PASS.
Все 25 MapSidebar cases прошли, включая изменение window height,
snap/custom-height behavior, short-viewport ARIA/geometry и cleanup.
Компонент уже был исправлен, лишней production/test правки нет.
Приёмка ограничена window.innerHeight/window.resize, не VisualViewport-only
keyboard/browser-chrome и не real-device/browser geometry.

Lint 119573686186, security/types 119573686277 и inventory 119573686355 PASS.
Contract 119573685930 SUCCESS: 1406 PASS / 1 deselected за 470,98 s,
затем 241 policy PASS за 44,67 s. Оба шага и cleanup завершены.

AUD-157 получает три регрессии реального controller/QueryClient:
обратное завершение HTTP sends, microsecond precision и equal-time ID tie.
Проверяются cache/UI order, pagination и response metadata, identity
прежнего элемента и исчезновение optimistic IDs. Finally завершает оба
owned sends, дожидается delivery promises, unmount и очищает client.
Новых sleeps/retries нет. Прежний WebSocket ordering/self-echo suite
также добавлен в ранний cohort. Production append ещё не меняется до RED;
AUD-157 OPEN. Global CI/NATS не приняты; все finite границы сохранены.

## AUD-157 tests-first isolation checkpoint — 2026-10-22

[Source 346d92e](https://github.com/egorribun/university_ecosystem/commit/346d92e1a1a64fc580dab4ccb9002c8ffd9c4679)
produced actual hosted RED in [Matrix 39703534001](https://github.com/egorribun/university_ecosystem/actions/runs/39703534001).
Frontend job 119579113639 passed 55 worker/export tests and 302 quick cases,
but all three new HTTP ordering cases failed. Their visible lists had
server responses in completion order plus two optimistic IDs. The ordering
assertions are retained, not relaxed.

Inspection found two earlier Blob URL lifecycle tests leaving mocked sends
permanently unresolved after unmount. They now own and settle those deferred
requests and await every delivery promise in finally, after the original
unmount/revocation assertions. This removes a plausible React async-Action
test-isolation problem; a hosted rerun must establish its effect before
attributing the lingering optimistic IDs to production. Production code is
unchanged. Two short waitFor expressions are normalized following the
frontend formatting failure; hosted Prettier remains authoritative.

Backend contract job 119578515815 was terminal with **1,406 passes / one
deselected in 449.84 seconds**, followed by **241 policy passes in 39.62
seconds**. Lint, security/types and inventory also passed. Frontend typecheck,
ESLint and i18n passed, but formatting did not. This is neither a globally
green checkpoint nor AUD-157 acceptance. The verified ledger remains
**218/512 (42.6%)**. Baseline 319, policy 294, required 78, Gitleaks 25,
blocking CodeQL and finite migration exception 131 remain unchanged.

## AUD-157 isolated RED and minimal ordering fix — 2026-10-22

[Source fdfe52e](https://github.com/egorribun/university_ecosystem/commit/fdfe52e09da25bfcc4f011eb99f200a9a129bdf2)
and [Matrix 39705589637](https://github.com/egorribun/university_ecosystem/actions/runs/39705589637)
now provide isolated hosted RED. Frontend job 119585956137 passed both
repaired Blob URL lifecycle cases and 302 quick cases, while the same three
HTTP ordering cases failed with only the server-ID order reversed. The
extra optimistic IDs no longer appeared after test-owned Actions settled.
No production optimistic-state workaround is justified by that earlier
test contamination.

The fix extracts the existing microsecond parser and deterministic ID
comparator into a type-only-dependent utility, then inserts HTTP responses
at their ordered position. Duplicate-ID short-circuit behavior, pagination
metadata, invalid-date arrival fallback and existing item order are
preserved. WebSocket caps and recovery cursors retain their existing logic;
HTTP history is not subjected to the live 200-message cap. History-page
merge behavior is outside this change.

The original three RED oracles remain unchanged. Five additional controls
cover retained history beyond 200 items, invalid cached/incoming timestamp
combinations and an HTTP response racing with an already cached same-ID
live record. Every new harness owns and settles its deferred delivery
before unmount/client cleanup. These added controls await hosted execution.

Frontend typecheck, ESLint, i18n, message-contract and knip passed at fdfe52e,
but Prettier still rejected the controller test file. The static-gate runner
now prints bounded, read-only formatter diffs on failure (at most ten files,
200 lines each), while preserving its original exit status. This is
diagnostic evidence, not an autofix, waiver or substitute for formatting
GREEN.

AUD-289 is the next verification-only candidate: the existing Spotify
track link already has a translated accessible name and eight EN/RU
populated/blank/missing/whitespace test cases. Its unchanged dedicated test
is routed into quick checks; neither code presence nor routing accepts the
finding. AUD-157 and AUD-289 remain outside the **218/512 (42.6%)** ledger.

Contract job 119585389303 finished with **1,406 passes / one deselected in
441.80 seconds**, then **241 policy passes in 40.82 seconds**, including
terminal cleanup. Lint, security/types and inventory passed. Global
CI/NATS remain unaccepted. Baseline 319, policy 294, required 78, Gitleaks 25,
blocking CodeQL, migration exception 131, all shard counts and budgets
remain unchanged. No merge, deployment or release is performed.

## Evidence checkpoint: 220 verified original AUD IDs

Verified lower bound: **220/512 (43.0%)**; **292 original IDs remain**.
This checkpoint accepts **AUD-157** and **AUD-289**, preserving the previous
218 verified IDs.

[Source c6620a89](https://github.com/egorribun/university_ecosystem/commit/c6620a89e3958cb97d8675cd33b135fb80f36636)
and PR merge `40001e6b` share tree `8928248a`.
[Matrix 39708376692](https://github.com/egorribun/university_ecosystem/actions/runs/39708376692)
frontend job 119594936038 passed **658 Node checks, 55 worker/export tests
and all 318 quick cases**. Static job 119594935984 passed typecheck, ESLint,
Prettier, i18n, message-contract and knip; Prettier explicitly confirmed all
matched files use its code style. Lint 119594257158, security/types
119594256996 and inventory 119594257092 passed. Contract 119594257016
completed **1,406 passes / one deselected in 426.81 seconds**, followed by
**241 policy passes in 37.78 seconds**; both steps and cleanup were terminal.

AUD-157 has isolated hosted RED at fdfe52e and GREEN at c6620a89 for the
same three reverse-completion, microsecond and equal-instant ID oracles.
Five additional passing cases preserve history beyond 200 messages,
invalid-date arrival fallback and same-ID live/HTTP race behavior. The
existing WebSocket suite also passed. Acceptance covers the HTTP insertion
ordering defect, not a redesign of history-page merging, delivery ACKs,
retry idempotency or optimistic state. The earlier lingering optimistic
IDs were eliminated by settling test-owned Actions, not by a production
workaround.

AUD-289 was already corrected in source. Its unchanged dedicated eight-case
suite now has hosted GREEN for exact accessible link names and hrefs in
EN/RU, including populated, blank, missing and whitespace-only track names.
Acceptance is the audited DOM accessible-name contract, not a claim of
manual screen-reader or real-device certification. Independent read-only
review corroborated both scopes and the RED/GREEN evidence.

Next are tests-first regressions for **AUD-286** and **AUD-298**. TOTP copy
feedback is checked through the application's existing persistent polite
live region, with only localized feedback allowed and no secret in that
region; clipboard rejection and owned fake timers remain controlled.
The test is appended without moving existing baseline-sensitive lines.
The cover-reset case requires a named button and verifies that cancelling
a pending file restores the saved cover without uploading it; URL spies
are restored after unmount even on failure. The existing TOTP suite is
additively routed early. These are unexecuted candidate regressions, not
closure evidence, and neither component is changed at this checkpoint.

Baseline 319, policy 294, required 78, Gitleaks 25, blocking CodeQL and the
finite migration exception 131 are unchanged. No budget, shard count,
test oracle or gate is relaxed. Global CI/NATS remain unaccepted; no merge,
deployment or release is performed.

Current verified IDs: AUD-002, AUD-003, AUD-004, AUD-005, AUD-006, AUD-007, AUD-008, AUD-009, AUD-010, AUD-011, AUD-012, AUD-013, AUD-014, AUD-016, AUD-017, AUD-018, AUD-019, AUD-020, AUD-021, AUD-022, AUD-023, AUD-024, AUD-025, AUD-026, AUD-027, AUD-028, AUD-029, AUD-031, AUD-032, AUD-033, AUD-034, AUD-035, AUD-036, AUD-037, AUD-038, AUD-039, AUD-041, AUD-042, AUD-044, AUD-046, AUD-047, AUD-048, AUD-049, AUD-050, AUD-052, AUD-053, AUD-054, AUD-055, AUD-056, AUD-057, AUD-058, AUD-059, AUD-060, AUD-061, AUD-062, AUD-063, AUD-064, AUD-065, AUD-066, AUD-067, AUD-068, AUD-069, AUD-070, AUD-071, AUD-074, AUD-075, AUD-076, AUD-077, AUD-078, AUD-079, AUD-080, AUD-081, AUD-082, AUD-083, AUD-084, AUD-085, AUD-086, AUD-087, AUD-088, AUD-089, AUD-090, AUD-091, AUD-092, AUD-093, AUD-094, AUD-095, AUD-096, AUD-097, AUD-098, AUD-099, AUD-100, AUD-101, AUD-102, AUD-103, AUD-104, AUD-105, AUD-106, AUD-107, AUD-108, AUD-109, AUD-110, AUD-111, AUD-112, AUD-113, AUD-114, AUD-115, AUD-116, AUD-117, AUD-118, AUD-119, AUD-120, AUD-121, AUD-122, AUD-123, AUD-124, AUD-125, AUD-126, AUD-127, AUD-128, AUD-129, AUD-130, AUD-131, AUD-132, AUD-133, AUD-134, AUD-135, AUD-136, AUD-138, AUD-139, AUD-140, AUD-141, AUD-142, AUD-143, AUD-144, AUD-145, AUD-146, AUD-148, AUD-149, AUD-150, AUD-152, AUD-153, AUD-157, AUD-158, AUD-159, AUD-160, AUD-163, AUD-165, AUD-166, AUD-168, AUD-170, AUD-171, AUD-172, AUD-173, AUD-174, AUD-179, AUD-181, AUD-182, AUD-185, AUD-186, AUD-194, AUD-195, AUD-196, AUD-199, AUD-201, AUD-206, AUD-209, AUD-210, AUD-211, AUD-212, AUD-213, AUD-214, AUD-215, AUD-216, AUD-217, AUD-219, AUD-220, AUD-222, AUD-233, AUD-234, AUD-235, AUD-237, AUD-238, AUD-239, AUD-240, AUD-241, AUD-242, AUD-243, AUD-252, AUD-256, AUD-257, AUD-289, AUD-318, AUD-328, AUD-335, AUD-338, AUD-342, AUD-353, AUD-355, AUD-367, AUD-395, AUD-396, AUD-398, AUD-410, AUD-421, AUD-424, AUD-437, AUD-448, AUD-458, AUD-465, AUD-466, AUD-467, AUD-468, AUD-469, AUD-470, AUD-471, AUD-473, AUD-475, AUD-491, AUD-496, AUD-502.

## Accessibility RED checkpoint: AUD-286 and AUD-298

[Source 3d8f192e](https://github.com/egorribun/university_ecosystem/commit/3d8f192e8887405de40d68dc46d21590618ebf39)
and [Matrix 39710036831](https://github.com/egorribun/university_ecosystem/actions/runs/39710036831)
produced exactly the two intended quick-check failures in job 119600243111:
the cover-reset button had no accessible name, and successful TOTP copying
left the persistent polite live region empty. The other **325 quick cases**
and **55 worker/export tests** passed. Static job 119600243213, security/types
119599587915, lint 119599587896 and inventory 119599587845 passed.
Contract 119599587738 completed **1,406 passes / one deselected in 427.02
seconds**, then **241 policy passes in 37.52 seconds**, with terminal cleanup.

The minimal corrections add the existing translated clear-cover name and
send only translated copy confirmation through the existing application
announcer after clipboard success. No new live region or secret-bearing
announcement is introduced. Existing clipboard rejection behavior stays
unchanged. The original RED assertions remain intact; additional guards
check that clearing the pending cover does not update the saved story and
that neither live-region channel exposes the manual code.

AUD-218 is a verification-only candidate: existing row/bulk purge
confirmation behavior and destructive-race suites are routed into the
early checks. They cover cancellation, confirmation, vanished jobs and
duplicate submissions using mocked APIs, not deletion of live data.
No admin production behavior is changed, and test presence is not closure.

Fresh hosted GREEN remains pending for AUD-286, AUD-298 and AUD-218.
The accepted lower bound stays **220/512 (43.0%)**, with **292 original IDs
remaining**. Baseline 319, policy 294, required 78, Gitleaks 25, blocking
CodeQL, migration exception 131, budgets and shard counts are unchanged.
Global CI/NATS remain unaccepted; no merge, deployment or release occurs.

## Evidence checkpoint: 223 verified original AUD IDs

Verified lower bound: **223/512 (43.6%)**; **289 original IDs remain**.
This checkpoint accepts **AUD-218, AUD-286 and AUD-298**, preserving all
220 previously verified IDs.

[Source a3a45d2](https://github.com/egorribun/university_ecosystem/commit/a3a45d2afb1fc529bfdfc9b98f2c170952217f0f)
and PR merge `70cb69a2` share tree `023150f6`.
[Matrix 39711684773](https://github.com/egorribun/university_ecosystem/actions/runs/39711684773)
quick job 119605613758 passed **658 Node quality contracts, 55 worker/export
tests and 355 quick regressions**. Static job 119605613586 passed typecheck,
ESLint, Prettier, i18n, message-contract and knip. All four frontend shards
passed (788 files, 9,646 tests). Contract 119604858035 completed **1,406
passes / one deselected in 434.16 seconds**, then **241 policy passes in
41.59 seconds**, with terminal cleanup. Security/types, lint and inventory
also passed.

AUD-286 now announces translated TOTP-copy success through the existing
persistent polite live region without exposing the manual code in either
live-region channel. The original hosted RED oracle passed after the fix;
all eight TOTP closure cases passed, including clipboard rejection.
AUD-298 now gives the cover-reset icon button its existing translated
accessible name. Its original RED oracle passed, including restoring the
saved cover without uploading or updating the story; all 28 StoriesAdmin
cases passed. These are DOM accessibility contracts, not claims of manual
screen-reader certification.

AUD-218 was already corrected in source. All 25 admin behavior cases and
three destructive-race cases passed, including row/bulk confirmation,
cancellation, disappeared jobs and duplicate submissions. The tests use
mocked APIs; no live dead-letter data was deleted. Independent review
corroborated the scoped evidence.

Global acceptance remains blocked. Coverage job 119620917005 reported
exactly one uncovered changed Python line, `app/core/lifespan.py:263`,
out of 5,222 changed lines, against the unchanged 100% differential gate.
The new test exercises initialization of the quarantine worker's missing
task registry, waits for an explicit sweep-start event, and cancels/joins
the owned task. Its hosted result and aggregate coverage recheck are
pending; no production workaround or threshold reduction is introduced.
Owned Live 39711684758 passed browser E2E and Caddy redaction, then failed
NATS at the broker stage; cleanup and receipt upload succeeded. The Rust
paired-performance comparison also remains a separate unaccepted check.

Next tests-first candidates are AUD-282 (search failure must not be
reported as no users found) and AUD-283 (inline rename Escape must not
close the group panel). Their new regressions await hosted RED; group
panel production code is unchanged. The Escape case uses the real
focus-trap hook rather than hiding its Escape handling behind a mock.

Baseline 319, policy 294, required 78, Gitleaks 25, blocking CodeQL,
migration exception 131, budgets and shard counts remain unchanged.
No merge, deployment or release is performed.

Current verified IDs: AUD-002, AUD-003, AUD-004, AUD-005, AUD-006, AUD-007, AUD-008, AUD-009, AUD-010, AUD-011, AUD-012, AUD-013, AUD-014, AUD-016, AUD-017, AUD-018, AUD-019, AUD-020, AUD-021, AUD-022, AUD-023, AUD-024, AUD-025, AUD-026, AUD-027, AUD-028, AUD-029, AUD-031, AUD-032, AUD-033, AUD-034, AUD-035, AUD-036, AUD-037, AUD-038, AUD-039, AUD-041, AUD-042, AUD-044, AUD-046, AUD-047, AUD-048, AUD-049, AUD-050, AUD-052, AUD-053, AUD-054, AUD-055, AUD-056, AUD-057, AUD-058, AUD-059, AUD-060, AUD-061, AUD-062, AUD-063, AUD-064, AUD-065, AUD-066, AUD-067, AUD-068, AUD-069, AUD-070, AUD-071, AUD-074, AUD-075, AUD-076, AUD-077, AUD-078, AUD-079, AUD-080, AUD-081, AUD-082, AUD-083, AUD-084, AUD-085, AUD-086, AUD-087, AUD-088, AUD-089, AUD-090, AUD-091, AUD-092, AUD-093, AUD-094, AUD-095, AUD-096, AUD-097, AUD-098, AUD-099, AUD-100, AUD-101, AUD-102, AUD-103, AUD-104, AUD-105, AUD-106, AUD-107, AUD-108, AUD-109, AUD-110, AUD-111, AUD-112, AUD-113, AUD-114, AUD-115, AUD-116, AUD-117, AUD-118, AUD-119, AUD-120, AUD-121, AUD-122, AUD-123, AUD-124, AUD-125, AUD-126, AUD-127, AUD-128, AUD-129, AUD-130, AUD-131, AUD-132, AUD-133, AUD-134, AUD-135, AUD-136, AUD-138, AUD-139, AUD-140, AUD-141, AUD-142, AUD-143, AUD-144, AUD-145, AUD-146, AUD-148, AUD-149, AUD-150, AUD-152, AUD-153, AUD-157, AUD-158, AUD-159, AUD-160, AUD-163, AUD-165, AUD-166, AUD-168, AUD-170, AUD-171, AUD-172, AUD-173, AUD-174, AUD-179, AUD-181, AUD-182, AUD-185, AUD-186, AUD-194, AUD-195, AUD-196, AUD-199, AUD-201, AUD-206, AUD-209, AUD-210, AUD-211, AUD-212, AUD-213, AUD-214, AUD-215, AUD-216, AUD-217, AUD-218, AUD-219, AUD-220, AUD-222, AUD-233, AUD-234, AUD-235, AUD-237, AUD-238, AUD-239, AUD-240, AUD-241, AUD-242, AUD-243, AUD-252, AUD-256, AUD-257, AUD-286, AUD-289, AUD-298, AUD-318, AUD-328, AUD-335, AUD-338, AUD-342, AUD-353, AUD-355, AUD-367, AUD-395, AUD-396, AUD-398, AUD-410, AUD-421, AUD-424, AUD-437, AUD-448, AUD-458, AUD-465, AUD-466, AUD-467, AUD-468, AUD-469, AUD-470, AUD-471, AUD-473, AUD-475, AUD-491, AUD-496, AUD-502.

## Group-panel RED checkpoint and minimal corrections

[Source 5ce585e](https://github.com/egorribun/university_ecosystem/commit/5ce585e0eeb52e90962b1c92fa33861a3df51306)
and [Matrix 39779231466](https://github.com/egorribun/university_ecosystem/actions/runs/39779231466)
quick job 119827143749 reproduced exactly two expected failures with
**396 passing quick cases**, plus **658 Node contracts and 55 worker tests**.
AUD-282 displayed the no-users message after React Query reached its error
state. AUD-283 called the close callback twice when Escape was pressed in
the rename editor, with the real focus-trap hook mounted.

The group panel now renders the existing translated search-error message
as an alert and suppresses the misleading empty state on error. Escape
ownership stays with the panel: the focus trap remains active but does not
independently deactivate on Escape, while the rename editor stops the
handled Escape from reaching the panel close listener. Focus containment,
return-focus configuration and the outer close behavior are retained.
The original RED tests are unchanged; hosted GREEN is still required.

Static job 119827143963, security/types 119825897034, lint 119825897166 and
inventory 119825896646 passed. Contract 119825897363 completed **1,406
passes / one deselected in 422.63 seconds**, then **241 policy passes in
35.49 seconds**, with terminal cleanup before the next branch update.

The next tests-first candidate is AUD-290. The existing InstallPrompt
behavior suite gains two EN/RU cases through the real shared live-region
provider: notification feedback and service-worker update announcements,
independent polite/assertive lifetimes and no duplicate live regions.
Existing cases keep their original rendering configuration. Timers and
rendered trees are cleaned up explicitly. InstallPrompt production code
is unchanged here; these tests have not run and do not establish closure.

The accepted ledger stays **223/512 (43.6%)** with **289 IDs remaining**.
AUD-282, AUD-283 and AUD-290 remain unaccepted. The quarantine-worker
coverage test still needs aggregate coverage proof. Global NATS,
coverage and Rust performance holds remain open. Baseline 319, policy 294,
required 78, Gitleaks 25, blocking CodeQL, migration exception 131, budgets
and shard counts are unchanged. No merge, deployment or release occurs.

## PR #1306 main reconciliation checkpoint (2026-10-22)

The owner requested resolving PR #1306 conflicts before merging it personally.
This reconciliation merges main commit
[be7c8507](https://github.com/egorribun/university_ecosystem/commit/be7c8507b88aa5a939fee1982c16627f7c13f528)
into the audit branch at
[c128cd3e](https://github.com/egorribun/university_ecosystem/commit/c128cd3ef15fa6986110d4be40c911dbf544aab1).
Both parent histories are retained; no force push, PR merge or deployment is
performed by this checkpoint.

Resolution policy, explicitly approved by the owner: retain the coherent
audit npm manifest/lockfile pair rather than splice incompatible dependency
graphs. This preserves the local boundaries/micromatch compatibility package,
the coordinated Vitest 5.0.3 set and browser-package removal, React's
^19.2.4 manifest range with its existing 19.3.0 lock resolution, the direct router-core pin, Stryker support, and scoped js-yaml overrides.
Handlebars 4.7.10 and follow-redirects 1.16.1 already match main. The audit's
idb 8.0.4 runtime dependency is retained rather than moved back to dev-only.

Main's newer npm manifest targets below are deferred, not claimed integrated.
Reconcile them with a regenerated lockfile and fresh compatibility checks in
the next PR; the complete original Dependabot changes remain in main history.

- @sentry/react: retained ^11.5.0; main target ^11.8.0.
- @tanstack/react-query: retained ^5.104.1; main target ^5.104.3.
- @tanstack/react-query-persist-client: retained ^5.104.1; main target ^5.104.3.
- @tanstack/react-router: retained ^1.170.41; main target ^1.170.44.
- @tanstack/react-start: retained ^1.168.60; main target ^1.169.2.
- @tanstack/react-table: retained ^9.2.6; main target ^9.3.1.
- @tanstack/react-virtual: retained ^3.14.13; main target ^3.14.20.
- framer-motion: retained ^14.0.0; main target ^14.2.0.
- i18next: retained ^26.3.6; main target ^26.4.5.
- lucide-react: retained ^1.52.0; main target ^1.57.0.
- maplibre-gl: retained ^6.13.0; main target ^6.14.0.
- marked: retained ^18.1.0; main target ^18.1.1.
- react: retained ^19.2.4; main target ^19.3.1.
- react-dom: retained ^19.2.4; main target ^19.3.1.
- react-hook-form: retained ^7.89.0; main target ^7.90.0.
- @axe-core/playwright: retained ^4.11.2; main target ^4.14.0.
- @playwright/test: retained 1.63.0; main target 1.64.1.
- @testing-library/user-event: retained ^14.5.2; main target ^14.6.8.
- @types/node: retained ^26.6.4; main target ^26.6.5.
- @vitest/browser: retained (removed/moved); main target 5.0.4.
- @vitest/coverage-v8: retained 5.0.3; main target 5.0.4.
- eslint-plugin-boundaries: retained 7.2.0; main target ^7.2.1.
- knip: retained 6.40.0; main target 6.41.0.
- jsdom: retained ^30.1.2; main target ^30.1.3.
- msw: retained ^3.0.2; main target ^3.0.3.
- playwright: retained 1.63.0; main target 1.64.1.
- prettier: retained ^3.9.9; main target ^3.9.10.
- typescript-eslint: retained ^8.71.1; main target ^8.71.2.
- vite: retained ^8.3.3; main target ^8.3.5.
- vitest: retained 5.0.3; main target 5.0.4.

Workflow logic, test selectors, permissions, budgets and audit hardening are
retained; applicable action pins are refreshed to main's revisions, including
Checkov and TruffleHog. Go modules retain audit migrations, removals and
security replacements, including JWX v3, gobreaker v2 and x/net 0.60.0.
Nonconflicting main bumps are layered on top with their existing upstream
checksums: Sentry and Prometheus across the three services, miniredis in
gateway/ws-hub, and MinIO plus x/image, x/sync and x/text in file-processor.
The deleted gateway x/sync requirement is not resurrected. Detect-secrets
runtime versions and hashes already agree; audit ordering is retained.

This is conflict resolution, not a green release checkpoint. The accepted
audit ledger remains 223/512 (289 remaining). At the preceding c128 source,
AUD-282/283 targeted tests passed but the contract job was cancelled; the two
AUD-290 live-region tests remained intentionally RED. Global coverage, NATS
and Rust performance acceptance remain open. Fresh merged-source CI is
required; earlier evidence does not certify this reconciliation. Baseline
319, dispositions 294, required contexts 78, Gitleaks 25 and finite migration
exception 131 are unchanged. The owner will merge PR #1306; further audit
implementation waits for the next PR and a new instruction.

## Audit continuation after PR #1306 (2026-10-22)

The owner merged PR #1306 into main as
[4a2fe84c](https://github.com/egorribun/university_ecosystem/commit/4a2fe84c2704bd32ed492942b8853484772abaa0).
Its tree is identical to the reviewed conflict-resolution checkpoint.
The audit branch joins that squash-merge history without rewriting either
history, then resumes bounded audit work in a new PR. The previously
deferred npm reconciliation remains outstanding.

AUD-290 implementation now routes notification feedback through the shared
live-region announcer: errors use the assertive channel, other feedback the
polite channel. Service-worker update availability uses the existing
translated message on the polite channel. Visible toast markup is retained,
without duplicate live regions. Existing EN/RU regression tests are unchanged.

RED evidence precedes this implementation: source c128cd3e, Matrix run
39781830088, quick job 119836634659, recorded 416 passing and two failing
behavior cases (the new EN/RU announcements), alongside 658 Node contracts
and 55 worker tests. Full frontend shards recorded 9,648 passing and the
same two failing cases. This source change still needs hosted GREEN and
current-source gate evidence; it is not yet accepted as closed.

The accepted ledger remains 223/512 (289 remaining). AUD-282/283 await
terminal contract acceptance; AUD-290 awaits new GREEN. No baseline,
disposition, required-check, coverage-floor, timeout, shard or exception
changes are included. No automatic PR merge, release or deployment is
authorized by this continuation.

## Next audit regression batch (2026-10-22)

Owner-merged Dependabot PR #1344 added 32 npm updates on top of the AUD-290
fix (58e033c3), followed by PRs #1345/#1346 updating moby/api in ws-hub and
file-processor. This batch starts from 257a7432 and preserves those changes.
The earlier deferred npm list is therefore historical, not the current
manifest: the coordinated Vitest packages are now 5.0.5, React is 19.3.1,
and Vite is 8.3.4; the local boundaries package and scoped js-yaml overrides
remain. These source updates do not establish compatibility or GREEN.
The earlier fdb3 and 58e targeted runs were superseded/cancelled without
usable frontend results. The owner asked to continue audit work while
GitHub runs settle; no manual workflow cancellation is performed here.

Tests-first additions:
- AUD-296 mounts the actual Login and Register pages within MainLayout and
  requires one main-content landmark plus a named auth region containing
  its form. Query clients and the full auth-store snapshot are cleaned up.
  Production page markup is unchanged; two nested-main failures are expected.
- AUD-305 adds seven safe-URL and thirteen unsafe-URL parser cases.
  HTTP(S) and relative link spelling must be preserved. Dangerous schemes,
  credentials, embedded controls and malformed URLs must lose only their
  link, not the achievement record. The demonstrated sink is a user-activated
  anchor on the authenticated user's own profile, not established cross-user
  stored XSS. Production parsing is unchanged; unsafe-URL cases are expected RED.

Both suites join the existing quick regression selector. Expected failures
must be observed and diagnosed, not waived. AUD-290 remains pending GREEN;
AUD-282/283 still require terminal contract acceptance. The ledger remains
223/512 (289 remaining). No security baseline, disposition, required-check,
coverage-floor, timeout, concurrency or exception changes are included.

## Owner-approved achievement URL test identity (2026-10-22)

The owner approved exactly one synthetic Basic Auth Credentials identity in
frontend/src/components/profile/__tests__/profileUtils.closure.test.ts,
for the embedded-auth rejection regression. The exact path/type/digest tuple
is recorded under the singleton synthetic_achievement_url_test_fixture
category. Its semantic evidence identifies the reserved example.test host
and test-only rejection coverage; it is not operational credential material.

This extends the prior 294 records to 295 without modifying any prior record.
The record is reviewed on 2026-10-22 and expires on 2027-01-10. Validator
support accepts only the fixed identity and category, requires every evidence
marker, and refuses expiry extension or reclassification. Tests bind the
record to the actual TypeScript fixture and reject changed paths, types,
digests, incomplete evidence, pending/missing approval and expired records.

RED source evidence: ed31fe5a, Matrix 39807552009, security/types job
119927046781 failed detect-secrets on this fixture; mypy passed. This
decision permits no inline pragma, scanner exclusion, baseline edit,
credential use, new identity, category-wide matching or required-gate change.
Baseline 319, required contexts 78, Gitleaks 25, blocking CodeQL, migration
exception 131 and all existing test budgets remain unchanged. Source-bound
scanner and validator GREEN are still required after integration.

This approval does not close AUD-305 or any other audit finding. The accepted
ledger remains 223/512 (289 remaining); AUD-290 awaits hosted GREEN and
AUD-296/AUD-305 remain tests-first candidates pending observed regressions.

The same checkpoint fixes a test-only TypeScript narrowing error observed
on ed31 (frontend static job 119942426710, TS18048 at the unsafe-URL
assertion). A single object match now checks the expected record and its
undefined URL together, still failing for an absent record or an unsafe
string. The production parser and all negative URL inputs are unchanged.

## Auth landmark and achievement URL corrections (2026-10-22)

Source 5cccfb57, Matrix run 39815796693, quick job 119971322119
completed with 430 passing and exactly 15 failing Vitest cases: both
AuthPageLandmarks cases found two main landmarks, and all thirteen unsafe
achievement URL cases retained their link. The PWA behavior suite passed
20 cases; group-panel branches passed 42 and Escape integration passed one.
Frontend static checks and production build passed. Contract job
119968215223 completed with 1,406 passes / one deselected in 440.30 seconds
and 270 exact security-policy passes in 52.48 seconds.

The auth pages now use named sections inside the layout-owned main landmark.
Their standalone assertions follow the named region; the real-layout RED
tests remain unchanged. Achievement parsing now admits only HTTP(S) or
relative links resolved against an inert base, rejects credentials, control
characters and URL parse failures, and preserves the spelling of accepted
links. Unsafe links lose only their URL, not the achievement record. All
thirteen negative and seven positive URL regression inputs are unchanged.

The same source had two test-maintenance failures. Ruff required a missing
blank line and a single-line category subtraction in the policy test.
Detect-secrets flagged the redundant plaintext password assertion in that
test. It now checks non-null before computing the existing digest against
the independently fixed approved identity; the original TypeScript fixture,
exact identity, policy and validator are unchanged. No new disposition or
scanner suppression is introduced.

These corrections still require fresh hosted GREEN. The accepted ledger
remains 223/512 (289 remaining); no new finding is accepted by this commit.
Baseline 319, dispositions 295, required contexts 78, Gitleaks 25, blocking
CodeQL, finite migration exception 131, budgets and shards are unchanged.
No PR merge, deployment or release is performed.

## Dependency-compatible test contracts (2026-10-22)

On source 2c0c0b0e / merge 6ec2ed7d, the quick Vitest regression step
passed all 445 cases in 23 files, including the unchanged AUD-296 and
AUD-305 RED tests, the 20 PWA behavior cases and the group-panel cases.
Its job 119982368493 still failed because the Node closed live-inventory
guard retained Playwright 1.63.0 after the owner's 1.64.1 dependency update.
The four frontend unit shards completed with 9,652 passing and 20 failing
cases: nineteen inline-background assertions and one stale version pin.
These are not a globally passing frontend checkpoint or new audit closures.

Contract job 119981283674 completed with 1,406 passes / one deselected in
444.37 seconds and 270 policy passes in 52.62 seconds. Current-source
security/types, pre-commit lint, inventory, frontend static checks and
production build passed. The Python fixture repair passed detect-secrets
without a new disposition, baseline entry or scanner suppression.

Both explicit Playwright version guards now pin the installed 1.64.1
package set. The private deadline adapter is not changed. Reviewed upstream
[1.64.1 TestInfo](https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright/src/worker/testInfo.ts#L157-L166)
and [monotonic clock](https://github.com/microsoft/playwright/blob/v1.64.1/packages/isomorphic/time.ts#L35-L37)
retain the interfaces used by the adapter, but these remain unsupported
private APIs. A real-runner regression now calls the adapter with actual
TestInfo and requires a finite future deadline within the active timeout.
The existing live-contract command runs it before Docker/browser startup,
with no page fixture or web server. A Python contract binds that invocation.
The live-spec inventory, collection count, retries and timeout policy remain
unchanged; the new smoke itself has no retry. Historical visual-only
container pins are not refreshed or certified by this change.

Inline background token contracts now compare exact CSSOM-normalized
declarations through a narrow helper, rather than asking computed style to
resolve missing theme variables. Missing elements, missing or changed
declarations and invalid expectations still fail. Five helper regressions
cover these failure modes, color normalization and SVG support. Mixed style
assertions retain their non-background checks, and production CSS is
unchanged. This verifies inline token wiring, not rendered theme colors;
browser visual acceptance remains separate.

All new test-contract changes require fresh hosted results. The accepted
audit ledger stays 223/512 (289 remaining). Baseline 319, dispositions 295,
required contexts 78, Gitleaks 25, blocking CodeQL, finite migration
exception 131, dependency manifests/lock versions, budgets and shard counts
remain unchanged. No merge, deployment or release is performed.

## Hosted compatibility results and lint corrections (2026-10-22)

Source 17e61128 / merge 4e685a6f, Matrix 39827163188, completed all four
frontend unit shards successfully: 2,702 + 2,316 + 2,327 + 2,332 =
9,677 passes, zero failures. Jobs 119995616736, 119995616549,
119995616186 and 119995616232 include all previously failing background
contracts and the five new inline-helper cases. Quick job 119995616115
passed all 445 Vitest cases. Consumer Contract job 119994607200 passed
1,406 cases / one deselected in 445.96 seconds and all 270 disposition
checks in 47.99 seconds.

Two lint corrections remain source changes, not waived gates. Ruff's exact
diff wraps the final real-runner invocation contract assertion without
changing its expression. The runtime Playwright test replaces its empty
fixture destructuring with the unused baseURL option alias permitted by the
existing lint rules. Playwright 1.64.1 supports aliased option fixtures; this
does not request a browser or page and preserves the deadline assertions.
The title is shortened only to retain ordinary line formatting.

Static job 119995616107 also reported Knip exit 1 with no diagnostic text.
That result is unresolved; neither the empty-pattern correction nor passing
unit tests establish a Knip fix. Fresh current-source checks must pass
without exclusions, suppression, budgets or gate changes.

The accepted ledger remains 223/512 (289 remaining). These scoped results
do not establish aggregate coverage, global CI, live acceptance or release
readiness. Baseline 319, dispositions 295, required contexts 78, Gitleaks 25,
blocking CodeQL and finite migration exception 131 remain unchanged.

Before this correction, the owner merged Dependabot PR #1347 into egorribun
as 93a575c7, updating ten GitHub Actions dependencies across 21 workflows.
This correction is based on that commit and preserves every updated pin.
Earlier 17e test evidence is historical, not certification of the new action
versions. No PR was merged by this audit correction.

The completed 17e Owned Live job 119993375759 separately confirms the new
pre-Docker command: 254 Node contract passes, followed by one real Playwright
adapter pass in 697 ms with one worker. The later live UI run had 36 passes,
two password-reset failures (desktop and mobile), and two existing skips.
NATS outage acceptance was skipped. Owned cleanup and the metadata-only
Core receipt upload succeeded. The password-reset live failures remain
open; this lint correction does not claim to resolve them.

## Knip configuration-hint visibility (2026-10-22)

Current source 1cac4135 / merge 2d862cf5 passed TypeScript, ESLint,
Prettier, i18n and message contracts in static job 120007931597, but Knip
again exited 1 without diagnostic output. The installed lock resolves
Knip 6.41.0 and cross-env 10.1.0.

Inspection of the exact [Knip 6.41.0 release source](https://github.com/webpro-nl/knip/commit/13d7f21e8ec5b30d8fe6d8377c9012b9db96f871)
confirms that its compact reporter does not print configuration hints.
With progress disabled, a hint-only failure can therefore be silent.
The symbols reporter prints those hints; the command now uses it while
retaining no-progress and treatConfigHintsAsErrors.

The real-runner smoke introduced direct cross-env usage in the package
script. Knip's script parser recognizes that binary, so its former opaque
config-string ignore is now redundant by the release's unused-ignore
mechanism. Only that ignore is removed. The remaining four dependency
exceptions, file globs, path-scoped export exception and binary exceptions
are unchanged. The exact contract is updated to require direct cross-env
usage, the hint-capable reporter and blocking configuration hints.

The observed CI output did not name the redundant entry; this is a
source-supported diagnosis, not an invented diagnostic message. Fresh
hosted Knip and contract results remain required. This patch removes an
exception rather than weakening the gate; no dependency version, lockfile,
timeout, shard or security policy changes. Accepted audit progress stays
223/512 (289 remaining), with no merge, deployment or release.
