# University Ecosystem: safe-pause handoff и план полного закрытия

> **Для следующего исполнителя:** пользователь явно возобновил работу 2026-09-27. **Самый свежий операционный статус — §0.resume-20260927; предшествующий снимок паузы — §0.000000.** Более ранние формулировки «текущий HEAD», «чистое дерево» и «текущий CI» исторические. Использовать `executing-plans` либо `subagent-driven-development`, затем независимое ревью и `verification-before-completion`. Чекбоксы ниже означают оставшуюся работу, а не распоряжение повторить уже реализованные вертикали.

**Дата снимка:** 2026-09-22, около 16:25–16:35 Europe/Moscow. GitHub timestamps — UTC.

> **Исторический статус 2026-09-25 01:20 Europe/Moscow:** безопасная пауза того момента. Разделы §1–§5 описывают паузу 2026-09-22 и остаются историей (WASM, MFA, Semgrep из них давно закоммичены и опубликованы). Требования и Definition of Done §6–§13 остаются в силе; текущий статус — §0.000.
>
> **Историческое возобновление 2026-09-25 05:25 Europe/Moscow:** дельта приведена в §0.0; §0.1–§0.9 — предшествующий baseline, а не утверждение о чистом дереве или завершённом CI. Новая пауза и authoritative delta — §0.000.

## 0. Снимок 2026-09-25: полное текущее состояние

### 0.resume-20260927 Возобновление и подтверждённые новые блокеры

#### Последняя контрольная точка — 2026-09-27 20:45 Europe/Moscow

Работа ACTIVE. Следующая дельта заменяет операционные статусы20:30–20:35 ниже; прежние числа и HOLD сохранены только как история review, не текущие блокеры.

1. **LOCAL ROOT HEAD** `68d0ce0b6f3239b4c4830404496c481b0926657d`; origin/PR source по-прежнемуc12, tested merge64d, run36334802892/attempt1. Новые coherent commits: `31f13fa8d4d42f2d011ac4e077f7e91918661ab8` cleanup и `68d0ce0b6f3239b4c4830404496c481b0926657d` pytesthooks. Обычные hooks passed; baseline restaged unchanged. ROOT source/test WIP отсутствует; этот handoff ещё редактируется, пользовательский audit остаётся untracked и не staged. Никакого push/cancel running fullmatrix ради неurgent local batch.
2. **Cleanup review finding закрыт:** malformed UTF8 sentinel теперь означает unproven ownership: DB сохраняется, отдельно доказанный owned fallback cache очищается. A independently APPROVE,42/42; B author116pass/5existingWindows capability skips +39Linux и реальный fork/os._exit leak control. ROOT normal regression **116passed/5existingWindows capability skips,69.76s**, без отключения conftest, Ruff/check/format/diff0. Первый ROOT запуск честно setupERROR: pytest basetemp parent отсутствовал (13pass/108setupERROR); parent создан в owned artifacts, свежий повтор нормальный. Не product regression и не замалчиваемый failure. Source SHA256 `9001cd3b45b84756cf361bd579600c8aeb8b205fc380d35bb40439427f2402a1`, test `149bf99128055511b83fe584870485586c7c84fd42739c955afd0d5f299a1064`. Final author proof `../ue-mut-B/artifacts/quality/mutmut38-probe/late-child-cleanup-evidence-20260927.md` SHA256 `4a6970e9d43c19e38f8d83b9d003fce9105859d34cfbceddc4e52b4d507d7404` заменяет исходныйA94 proof; initialHOLD ниже закрыт этим verdict. Fork-only guard сохранён; нет waiver, timeout increase или universal ancestor/TOCTOU safety claim.
3. **Три pytesthook annotations приняты:** only parser:pytest.Parser/config:pytest.Config/item:pytest.Item и ->None; runtime AST/imports/provider bodies не менялись, независимый B APPROVE. Source `tests/conftest.py` SHA256 `7c4e630c93393adfe25a1ab43da1c43c063b68b3a9c07eafc1aa8bedf224dd61`. ROOT normal **36passed/2existing subprocess-only probe skips,103.55s**, `-W error`, inherited PYTHONDONTWRITEBYTECODE=1, owned basetemp/no cacheprovider. Драйверы subprocess probes выполняются; skips524/718 прежние. Ruff/check/format0; strict mypy **53→50 errors**, три target errors ушли, новых нет; это НЕ whole-conftest green. ROOT harness свежий **29/29,29.97s**. Remaining50 требуют отдельных type/runtime-boundary slices без Any laundering, import bypass или suppressions.
4. **Первый завершённый frontend mutation producer подтверждён:** A read-only actual job108670411964 shard2/64 success17:44:17UTC: **70Killed/0Survived/0NoCoverage/0Timeout/0CompileError/0RuntimeError/0Ignored**. Source API client91:39–145:1 SHA256 `0295bf0afca928d7accf1466d35a18d83b6bc4336646536150252177a6b13850`. Dryrun3397tests5m41s(net91.94s/overhead249.95s), producer717105ms. Preflight590files/42795signatures/64shards; опубликованный StoriesC799/185signatures относится кshard045, НЕ localC525 с новым closed test. Partial snapshot1completed/6running/57queued frontend mutations; **не full100%mutation certificate**. Coverage artifact B919 из дельты20:31 остаётся валидным только дляc12/merge64d, не localHEAD.
5. **Далее:** независимый review этой дельты, Markdown/local-link/diff gates, doc commit; затем ровно один canonical focused Stories run с frozen ROOT source/tests/config, DashboardStories-only, parallelism1/concurrency2 и неизменными default timeout/reuse. До terminal не edit/stash/commit ROOT. A читает реальные mutation CI evidence, B анализирует текущие CI costs/criticalpath/cache trust, C классифицирует каждый current skipped/required check; workers работают isolated/read-only без install/rerun/cancel/settings mutations. Все остальные требования §§6–13/полного goal OPEN до evidence. Ответов на ранее заданные C0/O9 design вопросы пока нет: не выдумывать approval, но продолжать независимые safe задачи.

6. **Свежий полный skip/required audit C:** snapshot17:44:19–17:44:24UTC (последовательный, не atomic): CI183jobs=100success/12skip/14running/57queued; PR235checks=145success/19skip/14running/57queued, no observedfailure/cancel. Все19 skips сопоставлены с точным publishedc12 `if:`/inputs/event: CI12=7optionalGo diagnostics+3backend integration shards+main-onlyWS+main-onlyCodecov; sibling7=benchmarkhistory+Chromatic+4mainSBOM jobs+dependabotactor. **0 prerequisite-failure-blocked skips**, но future failures возможны. Live ruleset8335285:92context/app pairs,90exactSUCCESS,2not-yet-emitted frontendmutation/CISuccess зависят от unfinishedDAG; не stale names и неGREEN. CI Success source ровно одна definition; same-displayname main/PR vulnerability gates различены поjob identity. ROOT прочитал полный C report `../ue-mut-C/artifacts/quality/pr1266-skip-audit-20260927/report.md`, SHA256 `4d8fb5e244d2cfa4fef0e8928f50ebb17e6308852fa5aaf405b54981853efeab`; snapshot `878dc7cc055d979052be3fecc54fbb7bc44e00dcbffa3f3eacf0428799be10e5`, guards `2cc368640d5fbf4d09402633ea39c6e147f17d731882cdff2d868f4e89477958`. Никакого settings mutation/bypass/context removal.

7. **Read-only CI timing обновлён, не ETA:** ROOT прочитал B `../ue-mut-B/artifacts/quality/pr1266-c12-step-timing-20260927.md`, SHA256 `f8a4c9d90326799ce9578cf44dad68759477338efbabcf5c761f9e2673abeadf`, JSON `3a85b92e10f35d7286e2dc7901c616d81d535005682545a41220246afa29e8d0`. Все183jobs/steps в partial capture17:39:31–17:41:43UTC. Backend units span34m30s, pytest3599/3921runner-sec=91.79%, deps138s; max-parallel2 создаёт две admission waves. Fresh6Stryker npm installs172s,8backendstats deps284s; CPU/RSS и завершённая mutation duration ещё неизвестны, не zero. Preserve10backend+6frontend+4reserve, fullinventory/coveragebarrier; cap experiment только после3comparableGREENruns, no speculative timeout/retry/cache bypass. Source590files/42795planned signatures/64plans проверены A, но signature counts не mutation-score. ROOT прочитал A bounded triage `../ue-mut-A/artifacts/ci-artifacts/36334802892/mutation-triage-20260927.md`, SHA256 `d068d489ed31869fe265848e87b1578dfc6ca26e51a1368e4a11b57e8122992d`; shard2 raw report `83fab8292a3fd0f4661026efdb1b17f09f1a2f80529c3bb770d5579bf518b15c`/evidence provenance verified. Никакого ROOT/source/settings/cache изменения этими аудитами.

#### Предыдущая контрольная точка — 2026-09-27 20:30 Europe/Moscow

**Работа активна; это не pause, не final acceptance.** Снимок20:00 и все предыдущие дельты ниже исторические. Опубликованный source остаётся `c12ca4b15cce72935fa8a1840aab4a3af9c5ed2e`; следующие изменения LOCAL и не отменяют текущий длинный CI ordinary push ради неurgent delta.

1. **ROOT identity и сохранность:** implementation HEAD `3bd8b94a80616a0b9a25c7c3587300150d2a9c47`, branch `egorribun`. Семь local commits послеc12: `3a8690eb61f6c193dc5bddd91a25cdc40a4886ef`, `184978c9576486890b94a9851b1ac4890c637c67`, `dc4c1703ecbbabb0787015449dba76c8459da583`, `f6c1df6efb0eab5adfa5619863ced44a623b8ec6`, `60ba817631d5d221d443ea3b494a6f502fbfb559`, `30e3388bc8d806620f1ff4a6a78c87d7f9768d39`, `3bd8b94a80616a0b9a25c7c3587300150d2a9c47`. Ordinary hooks passed, `.secrets.baseline` restaged unchanged; Co-Authored-By отсутствует. До этого doc edit ROOT содержит только сохранённый user audit untracked, SHA256 `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b`; четыре stash прежние, 2026-09-27 13:00:28/12:59:40 и2026-09-25 22:47:40/39. Не broad-stage audit, не reset/clean/delete junctions/legacy data.
2. **Fresh CI, не terminal verdict:** actual all-pages API run `36334802892`, attempt1, sourcec12, последняя выборка105jobs: **92 success / 11 skipped / 2 in progress / 0 failure / 0 cancelled**. Последние backend unit shard2/job108666955436 и shard3/job108667549433 ещё работают. Старый blocker shard0/job108664012516 SUCCESS,16:55:46–17:12:01UTC. Все четыре frontend unit-shards и aggregate, четыре Lighthouse+aggregate, Chromium4/4 shards, Firefox/WebKit/mobile-WebKit, Schemathesis8/8 shards+aggregate SUCCESS. Это не full mutation/coverage evidence: downstream pipeline ещё зависит от backend completion. Пересчитать terminal jobs/required checks и каждому skip проверить актуальный `if:`/`needs:`; не переносить старые19intentional/12blocked. Предыдущий20:12 diagnostic99jobs=79success/10skip/8running/2queued хранится `artifacts/quality/pr1266-c12-ci-20260927-2012.json`, SHA256 `0022c350d1fd277684e8400b2cf785713ce6794efc0eb3534087dbe374ccdc70`. Tested merge identity из sibling остаётся64d107e…, actual mainCI checkout ещё отдельно не прочитан.
3. **Sparse Stories contract принят:** commit `f6c1df6efb0eab5adfa5619863ced44a623b8ec6`, test `DashboardStories.sparse-collection.test.tsx` SHA256 `7bca68a396838e160e9a8577713dcc5dcabe28ab51cd4e6a8c2e1dfdc364caed`. Реальный sparse typed collection compaction перед limit; actual circles/nav/callbacks. Автор baseline1GREEN→remove-filter RED(expected2circles/got1, no crash)→exact restore; independent A APPROVE; ROOT13suites111/111,41.23s, scoped126/46/21/115 все100%; typecheck/scoped lint/format0. Не normal API failure и не canonical Killed.
4. **Redundant closed progress write удалён:** commit `60ba817631d5d221d443ea3b494a6f502fbfb559`. Удалён только `setProgress(0)` в closed branch opening effect; initial0, closeViewer/open/navigation resets и все guards сохранены. Independent C26/26 APPROVE; ROOT13suites111/111,48.11s, scoped125/46/21/114 все100%, typecheck/lint/format0. DashboardStories current SHA256 `c525eeb8fdfe7a4426c396b41b412ff3803ebe37efcac223dcd1d4b481e7f650`. Private transient React state/все pre-passive paint timings не объявлены эквивалентными.
5. **Array species: прежняя broad equivalence исправлена, guard сохранён.** Native Array subclass проходит Array.isArray, filter/slice сохраняют species и inherited null/indexed accessors. Proposed length-sentinel simplification HOLD, source не изменён. Addendum `C:/Users/egorribun/Documents/ue-mut-A/artifacts/stories-survivors-20260927/classification-addendum.md`, SHA256 `c9c1b622a59e5cb39eb6597da0ccc8f4e6fb0dc27865ed185e6738fbd8d8c676`: broad oldID10/197 plain-array equivalence withdrawn, old83 premise narrowed; все historical canonical statuses/score неизменны. Typed public component boundary не normal JSON API exploit. Accepted test-only commit `30e3388bc8d806620f1ff4a6a78c87d7f9768d39`, `DashboardStories.closed-selection.test.tsx` SHA256 `9dad9010e82b964f9076edadf360d563fea7c4efbb1461965ca273b8d999509c`; genuine conditional-false RED: реальный closedcircle unexpectedly selected while dialog absent, no crash; exactC525 restore. Independent C1/1 APPROVE; ROOT14suites **112/112**,44.47s, scoped **125/125statements,46/46branches,21/21functions,114/114lines**, typecheck/scoped lint/format0. ROOT coverage `artifacts/stories-closed-selection-root-20260927/coverage/coverage-final.json` SHA256 `67b3e6151ce943d15d08fd98cfd601d193df4258a9eda2f02d2b8c529486ef2c`. A proof `artifacts/stories-closed-selection-20260927/proof.md` SHA256 `2e4a31fdc867cc8cd494192ec4e40fd0325723426f56ba6a495fd5f2f023e7c3`.
6. **ROOT normal production build terminal0:** на frozenC525 source до добавления последнего test-only контракта. До/после `node scripts/verify-wasm-artifacts.mjs` exit0; only current command `SKIP_WASM_BUILD=1 npm run build`, прежнее process env restored finally. Client5998modules; SSR23.61s; orchestrator artifacts stable70.4s, намеренно завершил hanging Vite child(code1), затем standalone SW/Workbox190files3.76MB/postbuild shell completed, wrapper0. Не представлять child exit как самостоятельный Vite green. Rolldown PLUGIN_TIMINGS notices остаются диагностикой; build не доказывает field CWV/browser matrix. Tracked tokens/source не изменились. Fresh source/test inventory generator и anti-pattern validator ROOT exit0 после нового теста.
7. **Imported fixture typing slice закрыт, broader debt открыт:** commit `3bd8b94a80616a0b9a25c7c3587300150d2a9c47`, only `tests/fixtures/services/service_fixtures.py`, SHA256 `01ff6661637cdc410a014d33d7eaa89bfa2159fd5521e0a039281c075b9e230c`. Genuine strict mypy5→0; no follow-import relaxation/suppressions; Redis[Any] точно совпадает с actual base API, kwargs/defaults object, runtime AST unchanged. Independent B APPROVE и18/18 strict fixtures. ROOT strict mypy0/Ruffcheck+format0, normal cache_deps/cache_integration/stories_api **18/18**,11.32s, `-W error`, owned basetemp/no cacheprovider. Исходный expanded diagnostic58=53conftest+5services НЕ whole-project green. Remaining conftest53:40untypeddefs+2generatorreturns+5dict/localtypes+3validatedstring narrowing+1Redis method replacement+2untypedtestcontainers imports. Следующий изолированный C scope только три pytesthooks annotations; providers/Redis/runtime/import-typing отдельно. Annotation-only не закроет два external typing случая, нельзя Any laundering/importlib обход/ignores. Canonical app364 gate отдельный.
8. **Mutation child cleanup candidate HOLD до исправления review finding:** B reproduced real Linux fork/os._exit baseline success/error leaks DB1+fallbackcache1; candidate0/0, 23Linux focused and100Windows related passed/5existing filesystem-capability skips. Proof `C:/Users/egorribun/Documents/ue-mut-B/artifacts/quality/mutmut38-probe/late-child-cleanup-evidence-20260927.md` SHA256 `a94f73990c78b2a5696be455b4a7a4c6c3d9bcf50c2516b21da6b1d765917d94`; separate forkserver diagnosis `8994fa4eb2f6c8ab4687d0a022e0bb0e0c90bce44b0d1b57c88dca78e9d85bd5`. Independent A reproduced P2: malformed UTF8 ownership sentinel raises UnicodeDecodeError before separately-owned fallback cleanup; unprovenDB stays but ownedcache leaks. Author исправляет through actual RED→minimal reject malformed ownership→independent re-review. ROOT runner/test пока НЕ изменены. Current fork-only fail-closed guard сохраняется; forkserver stats/warmup/IMPORT/lifecycle не разрешены этим fix. Symlink predicates не universal ancestor/TOCTOU certificate. No fake mutation-score claim.
9. **Следующие действия и ограничения:** reviewed B cleanup→ROOT normal focused regression/static+coherent commit; latest handoff review/commit; один fresh canonical focused Stories run на frozen ROOTsource/tests/config с localmutate DashboardStories, shardparallelism1/concurrency2/defaulttimeout/defaultWindowsreuse. До terminal не edit/stash/commitROOT и не run second overlapping mutation. Во время него workers могут работать в isolatedA/B/C без shared install. Старые160Killed/29Survived/84.66% остаются canonical historical, новые tests/DRY не дают score без fresh run. Не push nonurgent batch/cancel currentc12 CI. C0 run-owned live stand и O9 diagnostic design async questions ещё не получили ответ; их approval gate не блокирует остальные safe slices. Full applicable100% metrics/mutation/current-SHA manifest, O1–O9 acceptance, realroles/RUEN/SMTP/WebPush/chat5topics, SeaweedFS Core/full data-preserving cutover, localkind TLS/Kyverno/observability/CWV/chaos/rollback, exact-six immutable images/SBOM/provenance/finalaudit остаются OPEN. Нет authority main merge/bypass/realstaging/production. Shared node_modules junctions, чужие resources/users, persistent.env/DB и legacyMinIOdata не трогать.

10. **Дельта20:31–20:35: backend и coverage barrier пройдены.** Новый all-pages snapshot175jobs =97success/12skip/8running/58queued/0failure/0cancelled. Backend unit4/4+aggregate SUCCESS; `Coverage & Quality Policy Gate` job108670147403 SUCCESS; начали полный frontend mutation64shards (6running), backend generation и chaos. Main job log actual EXPECTED_SHA64d107e…, SOURCE_HEAD_SHAc12, base481d, run36334802892/attempt1; normalizer/validator terminal passed. Artifact10937378025 `quality-evidence-64d107e392bdb21c23c1c9cbbec1ff9f93e065fc-attempt-1`, uploaded archive digest `967fceca88f7729e271cc202d728d6e4c82077445830704d906b59b61bf75cfc`, downloaded isolated `artifacts/quality/pr1266-c12-coverage-20260927/`. Manifest SHA256 `b919352a24836626f255b49e901c6d8570c58dbf5024a8895654a85750bc302c` matches producer checksum; ROOT independently checked **16/16 report sizes+hashes**, validation.valid=true/errors=[]/missingreports=[]/schema3/provenance exact. Python31531/31531lines+statements,7708/7708branches; frontend19033statements/13331branches/4602functions/17162lines all100%. Go gateway1510/file1554/ws2244/shared425statements all100%; unsupported branch/function explicitlyN/A. Rust native1928lines/144branches/161functions; pyo3402/10/66; wasm197/4/26; crypto96/4/8 all100%, statementsN/A. Tier067files, applicable aggregates7421lines/5418statements/1976branches/813functions100%. Toolversions Python3.14.7/coverage7.13.5/Node24.21.0/Vitest4.1.11/Go1.26.6/Rust1.97.1/nightly1.101/cargo-llvm-cov0.9.1. Это **c12/merge64d** coverage evidence, НЕ current localHEAD3bd release evidence и НЕ100%mutation. `gh run view --job --log` отказал пока whole run active; direct completed-job logs API доступен. Попытка локального whole-validator на artifact-only folder честно exit1: нет sourcecheckout/ownershipmapping и enclosing HEAD3bd не64d; это expected fail-closed archive-context mismatch, НЕ новый CI regression. Не подделывать HEAD/добавлять bypass ради localgreen; producer validator в правильном checkout passed. B malformedUTF8 fix пока isolated повторно тестирован author116pass5existingWindows skips/Linux39, independent A rereview pending; прежнийHOLD не объявлять closed до verdict.

#### Предыдущая контрольная точка — 2026-09-27 20:00 Europe/Moscow

**Активная работа; goal не завершён.** Delta 19:44 ниже теперь исторический. Остальные master/continuation/external requirements сохраняются; новые локальные успехи не подменяют whole-project acceptance.

1. **Публикация и новая CI identity:** ordinary push успешно опубликовал все семь implementation-коммитов и doc checkpoint `c12ca4b15cce72935fa8a1840aab4a3af9c5ed2e`. Origin/PR #1266 source — этот SHA; base `481dba81ec78d7d2a33873a3a661470b0ecdd512`; actual sibling Dependency Review checkout подтвердил tested merge `64d107e392bdb21c23c1c9cbbec1ff9f93e065fc`. Новый main CI `36334802892`, attempt1. Initial non-atomic capture: 56 checks = 28 queued / 20 in progress / 7 skipped / 1 success, no failure/cancelled; позднее Dependency Review и Renovate success. Это НЕ terminal verdict. B proof `C:/Users/egorribun/Documents/ue-mut-B/artifacts/quality/pr1266-c12-initial-ci-20260927.json`, SHA256 `30609e9542f4e9cadde9fe6502478fa4dbbe36c837300b576c1cc373df5dc4ec`; MD `096b634fd1d89220614695a5cda0127710505d44000d93b8d3ceb93cfd19d1c3` ROOT прочитан. Исторические failed counts для1e09 НЕ переносить наc12.
2. **Полный ROOT fast-preflight terminal:** `python scripts/fast_preflight.py --max-workers 3 --report artifacts/fast-preflight/integrated-c12ca4b15-20260927.json --include-output`, exit0, **9/9**, 243.773s. Typecheck8.447s; full frontend lint118.265s; full format37.435s; i18n12.220s (2123 static/69 dynamic references, parity18/18); message contract0.145s; strict backend mypy app56.235s/364files; Ruff0.122s; harness29/29/34.906s; десять полных focused contract files **337/337**,161.19s pytest/171.272s process. Report SHA256 `3b4e30ac4a0a9d0ae00880a4ca7bbab00083df02a4a39d730b22b8fa5955a773`, source fieldc12. New selection test был ещё untracked: это WIP-inclusive local-fast-preflight diagnostic, НЕ чистый release certificate. Timeout600s/check и quality gates не изменены.
3. **Corrected selection/resource slice принят:** initial reverse-registration-order106 control (§19:44 item20) INVALID и сохранён только как discarded diagnostic. Исправленный тест регистрирует owned UINT_MAX до foreign0, обрабатывает frame snapshot в registration order с cancellation check; каждый callback под act. Не утверждать универсальный native handle wrap или commit timing всех браузеров. Actual corrected106 negative control и real-circle198/199 controls RED с finally exact source restore; independent C APPROVE и2/2. ROOT baseline **12suites110/110**,38.03s, sourceC799 scoped126statements/48branches/21functions/115lines все100%. Accepted test-only commit `3a8690eb61f6c193dc5bddd91a25cdc40a4886ef`; test SHA256 `1c1e81fc481b88554dea1eea4abfb0b40c55ea1fdf5d892d18dc3e9002e28bcf`. Corrected A patch `15f5efebb1834310848d1a3f74456f6edeae8e171bd250b043db9e935f031fad1`, proof `3ae0197cb4dc55dc6816e442bbe0445d8c6cc4e0af967f8c593a54edbb9c1599`, isolated `artifacts/stories-selection-resource-20260927/`.
4. **Minimal active-ID DRY принят:** commit `184978c9576486890b94a9851b1ac4890c637c67`; exact one-line `StoryList activeStoryId={activeStoryId}` reuse existing pure computed value. Не менялись guards, reset paths, refs, effects, thresholds, handlers или exclusions. C baseline37/37, candidate110/110, scoped100; independent B source/whole-file equivalence APPROVE. ROOT fresh **110/110**,41.49s,126/126statements,46/46branches,21/21functions,115/115lines; fresh typecheck/scoped ESLint/Prettier/diff0. Source SHA256 `e78b71bb511564c2370dce1855910da56e46b322d80a932d3771dd1a4870021b`; C patch `2e6946b91c7ceda44670aadbbe277100a72cd4b70f097162b87bce8608ad22b3`, proof `5f8936979b9710b0db29b3be8d8bd5af1433f02f94788716efb9b53ab4a476f1`. Две removed branch opportunities НЕ Killed mutants. Оба новых коммита пока LOCAL; обычные hooks passed, baseline restaged unchanged, user audit untouched.
5. **Параллельные следующие срезы:** C test-only sparse collection compaction-before-limit: current product GREEN, авторизованный remove-filter sensitivity control должен давать обычный assertion RED, не fake uncaught-render failure; никаких product edits. B read-only disposable C0 stand/run-owned three-role fixture prep. A read-only current branch/dependency applicability; preliminary high/critical package inventory уже patched на branch, default-main warning16 остаётся отдельным состоянием. PR1289 lock имеет js-yaml4.3.1 против current4.3.2: blind copy регрессирует security. Не переносить broad React19.3/Vite8.3 update и не npm install при shared consumers.
6. **Следующая контрольная граница:** получить reviewed sparse test → ROOT fresh verification → coherent local commit → новый focused canonical Stories run на frozen ROOT source/tests/config; во время него никаких edits/stash/commit ROOT. Не push nonurgent local batch поверх runningc12 matrix только ради doc/test delta. Fresh mutation denominator/report должен быть привязан к новому source, старые29 Survived остаются историческими, не GREEN. Полный applicable100% coverage/mutation/security, O1–O9 acceptance, C0 real journeys, data-preserving SeaweedFS Core/full, local kind/TLS/observability/chaos, exact-six immutable producer/images и final SHA-bound audit остаются OPEN. O9 diagnostic design async approval ещё не получено; не блокирует остальные safe slices. Не merge main, не force-push, не deploy real staging/production без отдельной authority.

7. **Дополненный read-only dependency audit:** A `C:/Users/egorribun/Documents/ue-mut-A/artifacts/dependency-readonly-20260927/report.md`, SHA256 `72cf8d052f5f4b7d847ea9edbc947151b6646aa940f4840dd1849645df5efd17`, ROOT прочитан полностью. Все16 actual default-main alert instances сопоставлены с current committed locks и fixed minima: current branch patched. Это НЕ comprehensive fresh scanner/installed/deployed certificate и НЕ основание dismiss alerts main. Main affected locks anyio4.13.0/httpx2-httpcore2 2.9.1/js-yaml4.3.1; urllib3 mainlock2.7.0, но minimum2.6.3 допускает vulnerable resolver. Root Go alert paths могут быть stale graph: reconcile после normal approved promotion, без автоматического dismissal. Новый API refresh mainCI сначала сетевой connect timeout (не CI failure); subsequent bounded REST read подтвердил run36334802892 still queued, sourcec12/attempt1. Не превращать queued в green или искусственно менять quotas/caps.
8. **C0 bootstrap design ещё не реализован:** B read-only prep нашёл independent `docker-compose.sandbox.yml` с pinned SeaweedFS для пустого стенда, но launcher uses worktree-derived project/fixed ports/finally down-v без run-exclusive ownership proof. `seed_admin_data` может promote existing user; auth test factory содержит fake password hash/direct JWT mint, не live-login fixtures. Main agent прочитал Compose/launcher и реальный User.create/UserRole/Argon2 API. Предложен отдельный run-owned topology: first disposable PG/migrations/transactional three roles+second student → later full Core/Mailpit/real UI, exact IDs+labels+manifest before cleanup, deny foreign resource/user collision и rollback без promotion, не менять persistent env/data. Один async design вопрос отправлен пользователю; approval ещё не получено. Это отдельный brainstorming gate, НЕ причина остановить Stories/CI работы. Новый stand/config/fixtures сейчас отсутствует; proposed command `scripts/quality/live_stand.py verify --phase fixtures` не существует и не выдаётся за выполненную проверку.

#### Предыдущая контрольная точка — 2026-09-27 19:44 Europe/Moscow

**Активная работа, не пауза и не завершение goal.** Этот delta является авторитетным операционным снимком; checkpoint 18:44 ниже — история. Scope master/continuation, внешний аудит и все §§6–13 сохраняются. Успех focused suites не означает глобальную сертификацию.

1. **Идентичность:** ROOT branch `egorribun`, локальный implementation HEAD `2b919c396007b544a15347b06d12048d6409733e`; на момент снимка origin/PR #1266 остаётся `1e09a3760cd1e640e2e89624cce05b90f48aaf8e`. Семь перечисленных далее implementation-коммитов ещё LOCAL; публикацию и новый CI сверить отдельно после ordinary push. Audit-only commit этого delta не подменяет SHA проверенного implementation source. Не merge main, не force-push и не deploy реальное окружение.
2. **Свежий terminal CI опубликованного source:** `36330701002@1e09a3760`, completed/failure. Core workflow: 119 checks, **93 success / 2 failure / 24 skipped**; весь PR rollup: 171, **138 success / 2 failure / 31 skipped**, pending нет. Исходный failure — Python unit shard0/job `108652768006`: 2741 passed / 22 skipped / 1 failed, 881.08s; `test_incremental_mutation_stats_are_sharded_and_merged_before_execution` ещё требовал удалённое `mutmut_cli.Config.get()`. Второй failure — derivative CI Success/job `108658926386`. Остальные три backend unit shards и integration успешны. Исправление локально принято в `7472056aa`; старый failed run НЕ доказывает новый source.
3. **Skip-классификация:** 31 = **19 intentional / 12 blocked**. Intentional: core12 (WebSocket advisory1, integration=false3, Go diagnostics7, trusted Codecov1) + sibling7 (actor-dependent1, Chromatic1, SBOM4, performance history1). Blocked: coverage policy1, chaos1, два compatibility dummy jobs2, mutation pipeline8. У backend unit/integration dummy нет `if:` fallback guard: их `needs: backend-tests` делает эти skips зависимостными, НЕ intentional. Полный current-SHA coverage validator не запускался; full mutation execution не стартовал из-за upstream barriers. Пересчитать terminal totals и guards для следующего SHA, не переносить классификацию автоматически.
4. **Семь новых небольших implementation-коммитов:** `db4f19eb26524953d29aac24eb2e0fd3e6c142a0` — validated pytest manifest field types; `2eb151483855514796c5bac723c49398f3552cb9` — Theme SSR/hydration; `7472056aa35c7d6684a3f291810612af7a2a9229` — current adapter workflow contracts; `c69e2c3469c502ab7c4d591601dcd901b890f1ad` — actual installed stats producer version; `2ee232a44dd2cff6708bfdeafbe902452c33c5ce` — workflow contracts in local fast-preflight; `7ef06ddee86c75af3a1785ad5a9ef75769830e3e` — reactive AuthLayout + meaningful anonymous E2E; `2b919c396007b544a15347b06d12048d6409733e` — Stories release ownership. Обычные hooks прошли, `.secrets.baseline` после каждого re-staged и unchanged; Co-Authored-By отсутствует. ROOT после этих коммитов имеет только сохранённый user audit untracked.
5. **Manifest typing:** private TypedDict сохраняет информацию после runtime validation, не ослабляет parsing; 13 runtime function AST bodies unchanged без annotations. Diagnostic RED5 mypy errors → GREEN0 без follow-import relaxation. ROOT normal-fixture tests **20/20**, 11.96s, `-W error`, собственный cache `artifacts/pytest-cache/manifest-typing-root-20260927`, Ruff0. Expanded imported fixture diagnostic debt теперь 58 errors: conftest53 + service_fixtures5; canonical CI mypy app scope не превращается в ложный whole-repository certificate.
6. **Theme:** no-window guard не обращается к Node process localStorage, lazy persisted read + useSyncExternalStore server=false/browser=true обеспечивает одинаковую initial hydration state. DOM/cookie effects gated; обычный createRoot persisted behavior сохранён. Actual RED guard-only dark/light controls имели recoverable hydration error; окончательная real AppearanceSection/LanguageProvider/StrictMode hydration его не имеет. ROOT four related suites **13/13**, 34.92s, Theme-only lines65/statements70/branches28/functions14 все100%; whole typecheck/lint0. Source SHA256 `9eb08ae3131ba038490e7005ea3232387abb6e2ae5bc56ef761bdd67e10e1038`. Это не cross-browser paint/CWV certificate; cookie policy не менялась. React stable19.2.8; canary browser()/use(browser()) не применялись.
7. **Workflow и mutmut sidecar:** workflow test теперь AST-проверяет реальный `collect_stats_shard` → `get_mutmut_config(mutmut_cli)`; legacy Config API не закрепляется. ROOT normal fixtures workflow/universe/stats protocol **218 passed / 4 existing Windows symlink capability skips**, 124.25s, strict warnings/own cache. Stats producer читает `importlib.metadata.version('mutmut')`, не литерал3.8; missing metadata fail-closed с сохранением cause, I/O first cause не маскируется, malformed producer metadata отвергается existing validator до publication. ROOT retry-artifact/workflow/provenance **78 passed / 2 existing filesystem capability skips**, 65.38s; scoped strict mypy/Ruff0. Исторические artifacts не переписаны.
8. **Fast-preflight:** добавлен полный `tests/test_quality_workflow_contract.py` и существующая ledger assertion усилена; прежние targets/600s timeout сохранены. Actual RED missing target → ROOT **8/8**, 2.88s, strict warnings. Whole workflow contracts обычно ~2min ловят этот дефект раньше remote shard (~15min); это не measured whole concurrent preflight speed certificate.
9. **AuthLayout:** beforeLoad live Zustand/evaluateAuthGuard и ssr:true сохранены; mounted layout подписывается на user/loading, немедленно скрывает Outlet после anonymous settlement/logout и делает replace login. Effect-only episode latch не читает refs при render и сохраняет первый destination при pending navigation. Original real-router nine cases6pass/3fail; naive effect выявил recursive redirect, окончательный held login-loader Promise проверяет loader once/query/hash before and after release/finally. Author38/38/scoped100%; независимый B **34/34**, typecheck/lint/format0. E2E `/admin` tautology заменена настоящим `/admin/users` → exact login/usable inputs/no Users heading; `networkidle; expect(true)` заменён `/settings?tab=2` → exact login + original redirect. Нет timeout widening или новых console filters. Source `b24e0d138087b19a53b669ad4ceed3ef26915f2a574312d204b3933007805b3e`; proof C `artifacts/auth-layout-20260927/proof.md`, SHA256 `b2d54fb556f7bb6a27163e691d0f0f5fd2adf122a1f8f2d7c99e43ed2eb29056`. ROOT actual two Chromium cases **2/2**, 7.1s, retries0/worker1; owned preview5189 closed finally. Genuine wrong `/admin` route accepted by old predicate, rejected by new exact assertion; injected-DOM controls были invalid и discarded. Не утверждать backend authorization bypass или real login/MFA acceptance.
10. **Stories canonical terminal, не новый GREEN:** ROOT frozen source `1e09`, DashboardStories SHA256 `8de4dc1d2ce88a541d97e68b5392c98ff52fa85cb67c77de2d29f3df943cce94`: 189 instrumented; dry106pass; **160 Killed / 29 Survived / 0 NoCoverage / 0 RuntimeError / 0 Timeout**, score84.66%, exit1, 31m41s. Raw `frontend/reports/mutation/focused/52a08d09485e22a41ca4987fa1dd38a189526505a29d8e36be63209e3c0a560c/runs/1852e9e8-421a-4daf-8249-34a8defa9d6f/shard-000/mutation.json`, SHA256 `2cf9343e1aada12d67a0748b7ebe913db2156f51d2b92d7d39519c7df05d635f`. Это local-focused/release-ineligible. Старый207-mutant raw ниже остаётся историческим; IDs не смешивать между source snapshots. Все29 классифицированы в isolated A `artifacts/stories-survivors-20260927/classification.md`, SHA256 `24de4c52cd2bc34079b446f3071382ec53d7e1e33e9d00ecd654025f39b33c4f`: genuine gaps, invariant-equivalent, defensive runtime cases и unresolved transient-effect hypotheses разделены. Ни один equivalent не исключён и не назван Killed.
11. **Stories воспроизведённый P2:** real StoryViewer pointer leave/up/cancel без prior pause напрямую rebased clock и терял elapsed. Original source8de: три genuine failures, три controls passed; expected40%, actual9.230769. Minimal fix: handleResume только releases interaction state, existing visibility effect owns resume on true owner transition. New six real-child cases включают repeated pauses, hidden releases и already-hidden opening; автор108/108/scoped100%, independent C24/24. ROOT source `c7991d545ef99041063eed10d485a46efab33f975db0dcd2b0ba48fac170a355`, test `6b762a80c6fa2340ecc5969524ef7359ec12a50117b9ef8061a74b6764c6de9f`; sole RAF acquisition/non-null cancellation/stale-frame guards не удалены. Удалённая mutation opportunity НЕ становится Killed; fresh canonical inventory/run необходим. Следующий isolated A test-only slice: selected real StoryList circle198/199 и foreign RAF0 after final owned completion106, exact negative controls; nullable input4 отдельно отложен. Не удалять immediate navigation/open resets или missing-story guards без доказательства pre-effect correctness.
12. **Свежая объединённая ROOT verification:** 18 suites **157/157**, 76.53s, two workers; Stories/Auth/Theme all four scoped metrics100%: statements216/216, branches85/85, functions41/41, lines196/196. Full frontend typecheck0/lint0; six changed files Prettier0, diff0; inventory generation + orphan/anti-pattern validator0; harness **29/29**, 29.89s. Scoped coverage НЕ global frontend coverage или mutation certificate. Source hashes после formatting/hooks совпадают с reviewed candidates. Нельзя commit/stash исходники, пока ROOT process ещё их читает.
13. **Свежий штатный ROOT build:** actual `node scripts/verify-wasm-artifacts.mjs` до и после passed; `SKIP_WASM_BUILD=1 npm run build` exit0, source/pkg unchanged, client33.81s/SSR20.11s/artifacts stable63.1s, Workbox190files/3.76MB, main174.91KB. Existing owner законно завершил retained Vite subprocess после usable stable artifacts и completed SW/post-build; это штатный orchestrated exit0, не direct Vite exit0. Серверный Experimental localStorage warning на этом полном запуске больше не появился. Rolldown PLUGIN_TIMINGS notices остаются: client babel72%24.3s + worker34%11.5s, SSR babel92%18.4s; overlaps/queue оговорены самим profiler. Не суммировать проценты как CPU и не отключать React compiler/warnings ради green. Source provenance `631182476176f444bf15ee711d6e515e89fb72b3d50fc942712d18312eb01626`; новая Rust/Linux generated-byte parity не подтверждена. Конфигурация shared node_modules не менялась.
14. **Дополненный actual mutmut3.8 Linux proof:** B `artifacts/quality/mutmut38-probe/compatibility-evidence.md` теперь SHA256 `8ed8d6e22ec583092b201e114e157b550c38c2449ba370c31143f576fce83457`, не старый c216. Actual exporter CLI + verify exact selected lifecycle завершены: minimal universe2, selected1 Killed, unselected completed0, raw mutant exit1; fresh/reuse source universe/stats/generation unchanged. C independently read/hashes approved, Docker повторно не запускал. Это снимает helper-only ограничение checkpoint18:44, но НЕ whole app/current-SHA score. Runtime Python3.14.6 против CI3.14.7, no whole uv.lock parity; default fork only. Reproduced forkserver late env/os._exit owned-temp leak и fail-closed compatibility guard остаются OPEN для настоящего lifecycle support.
15. **CI speed/O1–O9:** isolated C `artifacts/quality/o-speed-20260927/{precoverage-ledger.json,recompute.mjs,summary.md}` прочитан и root recompute0; модель all56 workflows31direct/26reusable допускает frontier57slots, cap2→4 даёт59 — это admitted demand, НЕ simultaneous scheduling. Historical4af+23siblings138 intervals дают repopeak20/CIpeak19; source account-wide quota не проверена. Fixed-work backend model36m01→18m39 даёт potential17m22, не promised PR speedup. Three comparable green runs нет; caps/reserve/required checks не менять. O9 existing exact-1 observer accepted; отдельный bounded always diagnostic design в B `artifacts/quality/o9-ci-enablement-design.md` требует ответа на уже отправленный async вопрос. Не считать отсутствие ответа blocker остальных reproduced fixes. Не добавлять CPU/RSS guesses, второй process killer, новые timeouts/retries или release evidence из diagnostic. CI enablement/durable diagnostics/resource-aware inactivity остаются OPEN.
16. **C0 live acceptance — важный незакрытый scope:** isolated A `artifacts/c0-live-readiness-20260927/report.md`, SHA256 `6550832ef730fc7ebbfce76719169d9b518bdb11379874e2312fb5de84382aea`: 45 обычных specs,30 directly useMockApi; реальный PG/backend в reusable E2E не превращает intercepted requests в live journeys. Admin smoke делает настоящую HTTP login/rendering, Mailpit handler integration доказывает bounded outbox/SMTP, но real UI three-role MFA/chat/notifications не сертифицированы. Отдельного live config/owned role fixtures нет. Conditional realtime synthetic events/banner-only/close1006 не доказывают delivery; Web Push stub не vendor transport. Очередь: disposable owned stand/readiness/teardown → three-role/idempotent run-owned fixtures → отдельный real browser lane → UI TOTP/email/recovery → two-context ws-hub journeys → five actual notification topics/local-only labelled push fallback. SSRF private-endpoint defence не ослаблять ради localhost sink; persistent DB/roles/volumes не truncate/reseed.
17. **Сохранность/ресурсы:** user `docs/audits/AUDIT_PLATFORM_FULL.md` untracked и SHA256 `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b` unchanged; четыре stash повторно прочитаны (2026-09-27 13:00:28/12:59:40, 2026-09-25 22:47:40/39), не менять. Isolated A/B/C WIP, backups, artifacts, NTFS junctions и legacy MinIO volume сохраняются; ROOT node_modules real directory, агенты junction, никаких npm installs пока active consumers. Docker last-read12CPU/12541640704bytes (~11.68GiB), это VM capacity не measured free RAM; Core configured cap sums runtime/bootstrap6240MiB4.65CPU, with init7008MiB5.5CPU не observed RSS/safe-fit certificate. OSS SeaweedFS approved, opt-in overlay не означает завершённый Core/full data-preserving cutover. Перед cutover freeze/copy/backup/verify/explicit ACK; untouched legacy data не удалять.
18. **Следующие действия/весь остаток:** проверить post-hook exact files + этот delta/docs gates → ordinary push coherent batch (предыдущий CI terminal, no cancellation) → зафиксировать fresh run/source-head/tested-merge/base identities, все producers/derivatives/skips/coverage/mutation artifacts. Parallel A next test-only slice → independent review → ROOT fresh verification вне source freeze → новый canonical focused Stories на настоящем ROOT node_modules; не редактировать ROOT source/tests/config до terminal. Полные 100% applicable coverage/viable mutation/security/API/Go/Rust/manifest gates, default-main alerts vs fresh branch findings, expanded typing debt, O1–O9 measured acceptance, npm/dependency follow-up при IDLE, real role/language/state/browser/a11y/performance matrices, disposable Docker Core/full + SeaweedFS migration, local kind/TLS/Kyverno/observability/chaos/rollback, exact-six immutable images/SBOM/provenance и SHA-bound final audit всё ещё открыты по §§6–13/external phases0–13. Main merge/real staging/production требуют отдельного полномочия. Goal остаётся active; «осталось только CI» неверно.

19. **Независимая CI provenance verification:** B read-only inventory immutable `1e09`: base `481dba81ec78d7d2a33873a3a661470b0ecdd512`, реально tested PR merge `cdab3a1827809698cbd5294a421b98efb86a5378`, подтверждены checkout log + reusable workflow ref и оба parents. Все92required context/app pairs active ruleset8335285 найдены среди171head checkruns; missing/name drift0. Это alignment, не green acceptance. Полные171names/119jobs/31skipconditions/92pairs в B `artifacts/quality/pr1266-ci36330701002-terminal.json` SHA256 `85842bbc6bde856f9374f481502af4fc083d66cd45ef0bce146ca1079b0e5d8c` и MD SHA256 `ed33fb6496a02d112f3d6b281038236ee9e37a3be92241793f49ad5e4a398897`, оба ROOT прочитаны. После push эта provenance историческая; не путать source head с merge SHA.

20. **Новый test-only Stories slice НЕ принят:** A `DashboardStories.selection-resource.test.tsx` initial SHA256 `671e243d65fbd47136f1dcf9f183884fc61c1656396e21d9ab6de7a2e0d66711` даёт author110/110 и C focused2/2, но review выявил P2 fixture-fidelity: foreign RAF0 зарегистрирован ДО owned1, а test исполняет owned1 первым, оставляя0 pending. HTML frame processing следует registration order; initial106 negative-control НЕ valid browser evidence. C selected-circle contract одобрен, resource case approval HOLD. A исправляет законный wrap-boundary owned UINT_MAX first/foreign0 second и повторяет serialized controls с finally exact source restoration. ROOT этот файл не переносил, commit/push batch его не содержит; результаты source mutation score не менять. Это конкретный пример, почему author GREEN без независимого review недостаточен. После исправления fresh hashes/proof/review обязательны.

#### Предыдущая контрольная точка — 2026-09-27 18:44 Europe/Moscow

**Исторический snapshot 18:44; authoritative delta 19:44 выше. Следующие counts/LOCAL статусы/agent assignments принадлежат своему времени, не являются актуальными поручениями повторить accepted work.**

**Authoritative delta этого подраздела заменяет операционные статусы ниже. Работа активна; это НЕ пауза и НЕ закрытие goal.** Ветка `egorribun`, PR #1266 → `main` OPEN. Опубликованный source пока `4af5845da415e94a6d7370b8694ec9706a960cd8`; локальный проверенный source checkpoint `58c0d4c99f1dd50edf23ed34c8a36300b90f88e0`, десять новых коммитов пока не отправлены. Этот документ не сертифицирует будущий doc-only SHA.

1. **Свежий terminal CI:** run `36325173446`, attempt 1, completed/failure. Обновлённый PR rollup: **142 success / 2 failure / 27 skipped**; ранее 26 skips были промежуточным снимком до появления последнего sibling check. Producer failure — `Coverage & Quality Policy Gate`, job `108643006152`; normalize отверг frontend lines/statements/branches ниже 100. `CI Success` производный. Backend все четыре unit shards и integration SUCCESS. Mutation stats/execution не запускались из-за coverage barrier: свежего backend/frontend полного mutation verdict НЕТ. Source `4af5845da…`, tested merge `e191ce3845a147646a7cc247d56bdbe9ab9aadd3`, base `481dba81ec78d7d2a33873a3a661470b0ecdd512`; identities не взаимозаменяемы. Root сверил guards: **19 intentional** — dependabot actor mismatch (1), main/billing-only Chromatic (1), main-only SBOM producers+gate (4), main-only performance history (1), main-only advisory WS10k (1), integration=false backend legs (3), scheduled/manual Go mutation diagnostics (7), trusted-main Codecov (1). **8 blocked downstream** — frontend shard/aggregate/roundtrip/final gate и mutmut generation/stats/universe/execution; это НЕ intentional release skips. Main-only skipped jobs не доказывают готовность main/release.
2. **Exact coverage diagnosis:** четыре unit artifacts скачаны в ignored `artifacts/ci-artifacts/36325173446/coverage-diagnosis/unit-{1..4}`. Для каждого проверены schema 2, run/attempt/tested SHA, bytes и report hash. `merge-vitest-coverage.mjs --expected-shards=4` exit 0; aggregate SHA256 `e8be996b4839ec6c700972cb5caa1b375bcbaaf67353ba80761a874bffbb897d`. Unit denominator: 17 150/17 152 lines, 19 011/19 013 statements, 4 597/4 597 functions, 13 319/13 320 branch arms. Единственный authored gap — `DashboardStories.tsx`: старые L66–67 missing-target close/return, branch L65 `[0,10]`. Предыдущие WebSocket gaps закрыты в этих fresh artifacts. Raw E2E compiled URL maps лежат отдельно в `e2e-coverage-diagnosis/shard-{1..4}`; наивная Istanbul union с authored unit paths НЕ является валидным component percentage или доказательством новых gaps.
3. **Canonical local-focused mutation terminal:** PRIMARY frozen на `4af5845da…`, `STRYKER_LOCAL_MUTATE_JSON=["src/components/stories/DashboardStories.tsx"]`, parallelism 1, concurrency 2. Dry run 84 tests passed; 207 mutants: **141 Killed / 63 Survived / 2 NoCoverage / 1 RuntimeError / 0 Timeout**, score 68.45%, exit 1, 34m33s. Raw `frontend/reports/mutation/focused/52a08d09485e22a41ca4987fa1dd38a189526505a29d8e36be63209e3c0a560c/runs/54a0c734-222e-4cca-8433-c919ee27ff9b/shard-000/mutation.json`, SHA256 `5f6a479ae2dab978a951e6d5a4b78e12dc5932c619cee881d8078a3ec09f5925`. Run freeze завершён; raw сохранён. Это focused diagnostic, всегда release-ineligible, не сертификат whole frontend. NoCoverage IDs42/43 относятся к missing-target guard; RuntimeError46 — обязательный вызов optional `onStoryOpen` из real event без callback. IDs и locations принадлежат только этому snapshot.
4. **Принятые коммиты:** `cd35dde6909e991e4b41de45b19c439d19bbe6f0` — opt-in progress context + actual runner/config registration, success-only terminal validation ПОСЛЕ existing child exit/close/quiescence и ДО чтения shard report/evidence; `c18eb7d1f479623d9cd8ca27a2200984bbf9efd9` — direct Stories navigation lookup, сохранён missing-target guard, Next boundary делегирован ему; новые boundaries9 + real-child navigation6; `cc1be0f0fcc9d5e9de1b9dc88f5f4c3ab1a19202` — UploadFile ownership test success/error/CancelledError; `a32f813352b44c4ca775845098498a50b920cce6` — ровно три mount-stable callbacks close/pause/resume через pure lazy state initializers. Все независимо reviewed, root verified, штатные hooks прошли; никаких Co-Authored-By или исключений.
5. **Свежая ROOT verification:** Node `npm run test:wasm` **436 total / 434 passed / 2 existing Windows capability skips / 0 failed**, exit 0, 16.19s. Stories navigation baseline **9 suites / 95 tests**, all four coverage metrics 100: 121 lines / 130 statements / 52 branch arms / 23 functions. После трёх stable closures повторный ROOT **95/95**, 32.55s, scoped 121/121 lines, 133/133 statements, 52/52 branches, 23/23 functions. Source SHA256 `2a6fd77e985c4c0305f293e13f823c5dc02e9d2f38084c1c7e2861d8e0421e7a`. Эти scoped denominators не подменяют global manifest. Full lint exit 0, typecheck exit 0, changed-file ESLint/Prettier/diff-check exit 0. Harness **29/29**, 33.34s. Inventory generation + orphan/anti-pattern validation exit 0.
6. **Backend ROOT verification:** normal repo fixtures, new ownership test **3/3**, related storage/copy group **54/54**, 14.11s, warnings-as-errors. Первый запуск прошёл сценарии, но session finish упал на PermissionError записи старого `.pytest_cache/v/cache/nodeids`; это FAILED run, не green evidence. Повторный запуск с `-o cache_dir=artifacts/pytest-cache/attachment-ownership-root-20260927` сохранил cache plugin и strict warnings, exit 0. Related group использует свой writable cache. Никакая warning suppression не добавлена; старый пользовательский cache не удалён и permissions не менялись. CancelledError сценарий не доказывает repeated Task.cancel/ошибку close.
7. **Stable closure rationale:** empty callback dependency-array mutations34/173/177 были constant-equivalent при unchanged bodies; pure lazy initializers только выделяют функцию, не читают refs/window/document/performance и не запускают setters при render. Реактивные openStory/goToIndex/navigation/visibility dependencies НЕ заморожены. Review подтвердил SSR/StrictMode/compiler ownership; ROOT lint/typecheck/95 behavior прошли. Isolated A valid negative controls дают по одному observable failure при удалении close setter, pause flag и изменении resume arithmetic; каждый восстановлен finally до exact hash. Один overlapping ранний pause-control discarded и не используется как proof. Mount cleanup ID27 и другие equivalent families не объявлены убитыми/исключёнными; новый полный mutation run обязателен.
8. **O9 live observer принят:** `b660395c630ed53a62354cf1ca42b147bd97d805`, четыре файла runner/test/context/test. Frozen patch SHA256 `ab36dd1118c04d5fb601a6f9f1981d0fba02f9983c7bac5ad67de20edf59bec4`, independent A review APPROVE; автор и reviewer 212 total/210 pass/2 Windows capability skips. Root canonical `npm run test:wasm`: **455 total / 453 pass / 2 existing capability skips / 0 failure**, exit 0, 16.11s; scoped ESLint/Prettier/diff-check exit 0. Exact-1 opt-in передаёт bounded synchronous reader в existing runNode/waitForChildClose owner; один 1000ms timer прекращается при exit/close/termination/settlement, late callback inert. Invalid live snapshot идёт через existing tree termination, first cause и ожидание close/quiescence; actual Windows root+descendant shutdown проверен, новых PID killers нет. Success-only terminal validation остаётся перед report/evidence processing. Missing/duplicate snapshots не означают inactivity. Full Linux author run **211 pass / 1 GitENOENT failure**, не green: pinned Node image не содержит Git; narrower Linux observer19 + context/monitor83 passed без skips, реальные POSIX descendants освобождены. Синхронный bounded-size filesystem read не гарантирует bounded I/O latency на hostile FS. Context удаляет пять inherited progress fields; disabled без files/timers, enabled private mkdtemp. CI enablement, legitimate quiet-phase measurement, inactivity policy, CPU/RSS и always diagnostics остаются OPEN; 15 300 000ms wall/30m dry-run bounds не расширены. Unknown metrics не фабрикуются.
9. **Watchdog compatibility risk проверен диагностически:** Python `heartbeat_watchdog.py` считает только outer PGID, тогда как Node владеет detached child PGID. B bounded Linux fixture: outer CPU не растёт, nested owned worker CPU растёт; synthetic clock 0→901 при stall 900 даёт ошибочную term decision. Это не реальный 900s hang и не текущая CI cancellation (wrapper не подключён к Stryker). Доказательство ignored B `artifacts/quality/o9-owner-boundary/compatibility-audit.md`, SHA256 `c6a62434cc2bf32337d6683e55d48e4a7989815cc51b1728300857ade7819907`. Не оборачивать Stryker слепо; live observer должен пользоваться existing exact owned PGID/Windows Job и first-cause/quiescence lifecycle.
10. **CI speed diagnostic:** B `artifacts/quality/backend-critical-path-20260927.{md,json}` (MD SHA256 `5b6c2e11ca2163778b03d04bdeae3c59443253dc23aaf58e189066c9aac99595`); terminal supplement `backend-closure-terminal-36325173446.md` SHA256 `7029544fea4f68210fb6251100f7ace274c1fa078525137c299ab920dea5a427`. Backend current unit span 36m01s; four runtimes 1040/881/1118/1119s. Shards2/3 CREATED ровно после первых completed shards: dominant delay — matrix admission max-parallel2, не придуманная runner queue. Модель fixed work cap4 даёт 18m39s (экономия 17m22s), но это не гарантированный PR speedup. Expanded backend peak будет 5 jobs; observed workflow peak19 не доказывает свободные slots/account quota. Перед экспериментом нужна реальная precoverage DAG reservation (16 ordinary + 4 reserve), учёт sibling workflows, three comparable green runs; requested three runs cancelled/failed/failed этому не отвечают. Mutation 10/6/4 allocations, coverage barrier и required checks не менялись.
11. **Backend mutation compatibility принят:** `e2db73ce6a23355c31314e02f06a023014c190e7`, пять scripts + четыре tests; frozen nine-file patch независимо одобрен C, exact ROOT baselines/hashes совпали. CI устанавливает mutmut3.8.0 из pyproject/uv.lock. Исправлены удалённые Config.ensure_loaded/get → original singleton config(), stats runner → get_mutant_runner/collect_stats, ListAllTestsResult → runners.harness, включая пятый exporter consumer. Default fork не переписан; modern missing/null/unknown/forkserver mode отвергается ДО generation/copy/reuse/output или установки temporary hooks. Export чтение pending None не превращает в fabricated terminal outcome. Actual minimal Linux Python3.14.6 (НЕ CI3.14.7), mutmut3.8.0/pytest9.0.3, cached digest `4ff4b92a68355dbdb52584ab3391dff8d371a61d4e063468bfd0130e3189c6d9`: fresh stats/test mapping, clean/forced baseline и selected Killed; повтор с validated reused-generation manifest прошёл. Два minimal mutants существуют, выбран один; overall score НЕ заявлен. Export actual proof пока helper-only pending collection, НЕ завершённый exporter CLI/evidence lifecycle. B ignored `artifacts/quality/mutmut38-probe/compatibility-evidence.md`, frozen review SHA256 `c216fe3b0a714811c4ee61ce46217b37dcB3baac010fa72cd2c147784b9fad9c` (hex case insignificant). Forkserver actual AST-extracted ROOT ownership fixture (`tests/conftest.py` SHA256 `b2763c1321be392f960c3886f2093fa2d9504da8b4d4ef428c3e9ec6f28424b9`) воспроизвёл late AUTO env/os._exit leak: stats один dead-child owned dir, execution ещё три. Own sentinels очищены finally; fixture TIMEOUT не accepted score. Forkserver lifecycle support OPEN, временный guard fail-closed, config/fingerprints/inventory/timeout/floors не ослаблены.
12. **Active isolated lanes:** A — TDD browser boundary ThemeContext SSR после actual production trace: bare localStorage getter вызывается readStoredTheme/useState при prerender; no warning suppression/dependency install. B — frozen compatibility уже перенесён/committed, дополнительное bounded completed-export proof может выполняться только в own ignored probe. C — compatibility review завершён APPROVE, read-only imported mypy scope/backlog audit. Root единолично stage/commit/push. Следующий canonical Stories запуск — в ROOT с настоящим node_modules, после doc/push и freeze; A junction непригоден для Stryker sandbox discovery. Agent checks не подменяют ROOT verification. npm #1289 deferred, пока shared-dependency users активны; никаких installs в shared node_modules.
13. **Сохранность/полный остаток:** пользовательский `AUDIT_PLATFORM_FULL.md` untracked, прежний SHA256 `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b`; четыре пользовательских stash сохранены. Isolated WIP/backups/junctions и legacy MinIO data volume не трогать. Нельзя сказать «осталось только CI»: full current-SHA coverage/mutation/security/manifest, O1–O9 измерения, role/language/state/browser/a11y/performance recertification, Docker Core/full data-preserving OSS cutover, local kind TLS/Kyverno/observability/chaos/rollback, exact-six immutable images/SBOM/provenance и final audit sourceSHA≠docSHA всё ещё обязательны. Main merge и реальные staging/production actions требуют отдельного разрешения.

14. **Дополнительно приняты Stories contracts:** `de497ee123bff8dcde189bacefbedc9907746d9a` — optional onStoryOpen через real UI с scoped window-error collection и обязательной empty-errors assertion; отрицательные controls optional→mandatory дают именно assertion failure, а не скрытый RuntimeError, stale callback dependency даёт observable callback mismatch. `24bde114a` — пять nonzero epoch/initial-hidden/interaction-visibility/foreign RAF0 contracts, real children и StrictMode. Авторские isolated controls genuine RED; два ранних sentinel reports с неверным baseline/ReferenceError **discarded**, только isolated reruns пригодны. Новый test SHA256 `5888023b103d0ea12bbbd6c7381da3b2bb89577906d77012680c2da482d0c4a59`; ROOT mechanical formatting восстановил exact author bytes. Fresh ROOT **10 suites / 102 tests**, exit 0, 14.24s, coverage 121/121 lines, 133/133 statements, 52/52 branches, 23/23 functions. Full typecheck exit 0; i18n scanner 2123 static/69 dynamic references + parity **18/18**, exit 0. Это scoped behavior evidence, НЕ обещание нового 100% mutation score.
15. **Build/Windows artifact ownership:** прямой diagnostic Vite run с отдельным output compiled client/SSR/prerender, но завис на retained handles; exact owned PID10500 tree завершён, exit 1, **не green build**. Затем штатный `npm run build` **exit 0**: client25.96s, SSR18.21s, existing orchestrator подтвердил fresh usable artifacts/stability53.7s и завершил именно свой retained Vite child; Workbox190 files/3.76MB, main index174.56KB. WASM metadata/license hints и Node Experimental localStorage warning остаются наблюдениями, не zero-warning certification. До build три tracked outputs были clean, checkpoint сохранён `artifacts/wasm-windows-checkpoint-20260927-1807/`; свои generated bytes сохранены в `generated/`. По ранее согласованному Windows rule восстановлены ТОЛЬКО own generated crypto.wasm/sanitizer.wasm/WASM_SOURCE_PROVENANCE.json из HEAD; user edits/source не затронуты. Fresh `validateSourceProvenance` exit 0, source_tree_sha256 `631182476176f444bf15ee711d6e515e89fb72b3d50fc942712d18312eb01626`. Linux generated-byte parity отдельно не подтверждалась.
16. **Stories DRY принят:** `65af08143dacce0bc2d32b340f4feb71db50732a`, source SHA256 `8de4dc1d2ce88a541d97e68b5392c98ff52fa85cb67c77de2d29f3df943cce94`. Удалены только девять строк duplicate mount cleanup; every RAF acquisition, stale ownsPlayback guard и nonnull cleanup остались у одного playback effect. Author и independent C ownership review APPROVE, reviewer18/18; отрицательный sole-cleanup no-op обнаруживает лишний RAF после unmount. Fresh ROOT102/102, 15.62s, all four focused metrics100: 116 lines / 128 statements / 50 branch arms / 21 functions; typecheck/ESLint/Prettier/diff0, штатные hooks прошли. Изменённый denominator — результат удаления дублирования source, НЕ exclusion/quarantine. После этого fresh orchestrated build **exit0**: client26.63s / SSR19.30s / artifacts stable54.1s / Workbox190files3.76MB. `SKIP_WASM_BUILD=1` использован только для валидации unchanged checked-in WASM/provenance без повторной Windows regeneration во время shared-dependency users; source/pkg bytes не менялись, новые Rust/Linux artifacts не сертифицируются. A canonical attempt `18cc3667-cb5d-4972-ad3a-1ed7eebdee54` после exact runner/config alignment завершился exit1 ДО dry run: 189 instrumented/0 tested, sandbox ERR_MODULE_NOT_FOUND vitest, mutation.json/score отсутствуют. Причина — NTFS node_modules junction не входит в Stryker10 Dirent.isDirectory discovery (findNodeModulesList=[]), тогда как ROOT node_modules обычный directory. Source8de4… и 10 tests/fingerprint `600a3f4b3edf31d2860ea28c3c4fa4d55870a44b22adf96f93dd09f33d0fa178` start/end unchanged. Это toolchain/environment failure, НЕ mutation verdict. Не менять/удалять junction ради ретрая; ROOT candidate LOCAL, не published. Durable A start/end metadata — `artifacts/stories-navigation-20260927/dry-focused-{start,end}.json`.

17. **Свежие ROOT compatibility gates:** normal repo fixtures/cache plugin, `-W error`, собственный writable `artifacts/pytest-cache/mutmut38-root`: 14 suites **219 passed / 7 existing Windows capability skips**, exit0, 104.37s. Ruff check/format9files exit0, scoped mypy5files `--follow-imports=silent` exit0 (unused-section info), все обычные commit hooks прошли; это НЕ full app/whole-repo type certificate. Дополнительный diagnostic mypy без silent обнаружил **63 errors / 3 imported files**: scripts/quality/pytest_shard_manifest.py5, tests/fixtures/services/service_fixtures.py5, tests/conftest.py53. Canonical mypy files=['app'], CI/precommit/fast-preflight app scope; ошибки — expanded diagnostic debt, не доказанный текущий canonical CI blocker. Owner @egorribun; требуется отдельная точная типизация parsed shard documents и fixtures/hooks, без blanket suppression/exclusion. Scoped adapter pass не скрывает этот долг.
18. **Comments, не timeout policy:** `58c0d4c99f1dd50edf23ed34c8a36300b90f88e0` устраняет stale workflow3.7 comments и ложную гарантию бюджета. Actual default fork wall `(estimate+constant)*multiplier`; constant6 при multiplier15 даёт min90s, не гарантирует pytest120s first. Ни constants, ни planner caps, ни behavior не изменены. ROOT budget/group contracts **43/43**, 23.82s, strict warnings; actionlint и все hooks passed. ROOT harness **29/29**, 29.22s. Свежий full frontend `npm run lint` exit0. Пользовательский audit SHA256 и четыре stash повторно сверены, unchanged.

**Следующая последовательность:** свежие ROOT regression завершить → обновлённый handoff/ordinary push coherent группы (старый CI terminal) → canonical focused Stories в ROOT и fresh whole coverage/mutation CI на новом SHA; ROOT source/tests/config не менять до terminal focused результата. Параллельно isolated SSR TDD, O9 CI wiring/legitimate-quiet CPU/RSS measurement и precoverage DAG reservation. После независимого review переносить следующий slice только вне freeze. Не перезапускать старый SHA ради проверки нового source, не переносить отчёты между identities. Затем npm #1289 при IDLE shared users и все §§6–13. Внешние release/deployment полномочия не подразумеваются.

#### Предыдущая контрольная точка — 2026-09-27 17:12 Europe/Moscow

**Исторический snapshot 17:12; актуальный delta приведён выше в checkpoint 18:44. Последующие bullets — хронология, не повторное поручение переносить уже принятые файлы.**

- Проверенный source checkpoint до этого doc commit: `4417832af5e4fa7dca55a244e99c6937a113f32b`, ветка `egorribun`. Опубликованный source пока `5c2cad4de394a1c607af723427d608e94ac3ecaa`; ordinary push следующего checkpoint ещё предстоит. Не смешивать локальные проверки с CI старого head.
- Terminal run `36320204798`: 97 success / 2 failure / 20 skipped. Один failed producer: frontend coverage statements/branches; `CI Success` производный. Полные новые mutation reports не произведены. Exact source/tested/base SHA и отдельное место скачанных artifacts приведены ниже в terminal diagnosis.
- Полный frozen frontend unit run на `fbee69a21`: **699 files / 8 034 tests passed**, exit 0, 1 858.62 s, maxWorkers=2. CSS-parser/navigation diagnostics этого снимка сохраняются как наблюдение; это НЕ zero-warning certification и НЕ полная проверка последующих Stories/WS/CSS изменений.
- Приняты и закоммичены: `5e1ada75a` HMAC fixture warning isolation; `80ff0fa44` Stories playback ownership и paused restart; `a40d622b7` stale chat publication/error callbacks. Fresh root Stories+WS: **12 suites / 259 tests**, exit 0, 38.74 s. Новые WS cases проходят реальные QueryCache/account transitions; удаление каждого соответствующего guard даёт genuine behavior failure. Guard не удалён ради coverage.
- Focused WS coverage автора: **409/409 statements, 236/236 branch arms, 74/74 functions, 353/353 lines**. Два ранее отсутствовавших guard counters теперь ненулевые. Diagnostic JSON в `../ue-mut-A/frontend/artifacts/coverage-diagnosis/ws-36320204798-20260927-1643-six/coverage-final.json`, SHA256 `9dbe6798…044c`. Это scoped proof, не whole-frontend manifest; новый CI должен подтвердить полный denominator.
- `1b9c9dccd` исправляет настоящий test CSS pipeline через Tailwind Lightning CSS lowering только при test environment. CSS не отключён, VirtualConsole errors не фильтруются. Реальный Vite→Tailwind→JSDOM contract **13/13**, main entrypoint **16/16** без CSS diagnostics. Test восстанавливает cwd/environment и закрывает server/DOM в nested finally; dev/prod defaults сохранены. Независимое review одобрено.
- O9 standalone slices: `a5bd85638` reporter, `f66b1b24d` bounded snapshot monitor, `4417832af` Stryker10 factory adapter. Node acceptance suites добавлены в канонический `test:wasm` и защищены отдельными presence contracts. **Runner/config/CI registration пока НЕ подключены**: export factory registration сам по себе не означает production enablement. Нет новых inactivity timers, CPU/RSS guesses или расширения mutation ignores.
- Fresh ROOT diagnostic-module Linux run: **94/94**, zero skips/failures, exact Node24 image `sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43`; network none, CPU1, memory256MiB, read-only scripts/dependencies, writable tmp only, auto-remove. Реальные symlink/FIFO checks выполнены. ROOT Windows modules+quality contracts: **106 passed / 2 explicit capability skips** (108 total). После test-only fixture field rename дополнительно **40/40**; privacy assertions сохранены.
- Независимое review обнаружило и исправило P2 adapter test cleanup: latched reporter failure теперь не пропускает другие reporters, injector disposal, восстановление environment и удаление только своего temp directory; first cause сохраняется. Stock detect-secrets распознал два dummy fixture field names; заменены только неиспользуемые metadata names, без pragma, baseline, exclusions или изменения scanner. Все успешные commit hooks прошли; baseline повторно staged и не изменён.
- Fresh canonical `npm run test:wasm`: **398 passed / 2 Windows capability skips** (400 total), exit 0, 12.53 s после восстановления checked-in WASM. Full typecheck и `npm run lint` exit 0; scoped ESLint/Prettier и `git diff --check` exit 0. Harness **29/29**, 29.36 s. Полная новая Vitest coverage/mutation matrix остаётся обязательной.
- `npm run build` exit 0: client+SSR+PWA произведены, main index chunk 174.56 kB, precache 190 files / 3.76 MB. Остались наблюдаемые toolchain notices: WASM crate metadata/license-file hints, Rolldown plugin timings и Node prerender localStorage ExperimentalWarning; build exit 0 не заменяет zero-warning/reproducibility acceptance. Согласно утверждённому Windows правилу восстановлены только три own build outputs (два `.wasm` и provenance), до запуска они были clean. Новые диагностические bytes сохранены в ignored `artifacts/wasm-windows-checkpoint-20260927-1709/`; strict validator прошёл. Source tree hash не изменился, canonical Linux byte parity не заявлена.
- O4 live read-only audit: main ruleset `8335285`, **92 required context+integration_id pairs**, все присутствуют среди 171 check-runs опубликованного source. Missing/stale/impossible contexts — 0; 89 required success, два failure и один blocked frontend mutation aggregate. `artifacts/quality/o4-required.txt` совпадает с live ruleset. Legacy protection endpoint 404 НЕ означает отсутствие защиты. Никаких settings changes не требуется; повторить exact-pair сверку на свежем green SHA. Неблокирующий cleanup: два SBOM jobs имеют одинаковое имя `Vulnerability gate (CRITICAL/HIGH)`; не переименовывать обязательные contexts без review.
- Сохранность: пользовательский audit untracked и hash прежний; stash, все isolated WIP/backups и NTFS junctions сохранены. Docker после bounded tests пуст; legacy MinIO data volume не удалён. В README/plan backlog не объявлять закрытыми внешнюю recertification, Docker/Core/full cutover, local kind/TLS/observability/rollback, exact-six immutable images, final SHA audit или production gates.
- Backend read-only triage на `4417832af`: все 12 модулей исторических 143 Survived / 1 Timeout уже затронуты `29987745e` и `153256c26`; свежий status пока неизвестен. Приоритет verification queues — storage (44 исторических outcomes) и chat attachments (39), IDs брать из `artifacts/quality/mutation-tools/inventories/mutmut-36194161259.json`, затем remap по текущей generation. У `copy_for_forward` сейчас 48 mutants, исторический suffix 55 исчез, нынешний 42 уже означает другое изменение; это generation diagnostic, не kill proof. Fresh связанные storage/copy tests **51/51**, 13.27 s, warnings-as-errors; pytest cache plugin отключён только из-за существующих filesystem permissions, assertions не ослаблены. Отдельный test-hardening кандидат: проверить закрытие переданного UploadFile после success/error/cancellation; source уже имеет finally-close, production defect не заявлен.

**Следующая работа:** ordinary push текущего проверенного checkpoint → fresh coverage gate и полный canonical mutation inventory; параллельно O9 runner-owned context + terminal validation TDD (после existing child exit/quiescence, до shard evidence), без изменения wall/dry-run budgets. Backend historic survivors уже затронуты commits, поэтому перед новым behavioral fix сначала fresh generated-ID mapping, не слепое повторение старых mutation replacements. Затем npm #1289 только при IDLE всех пользователей shared dependencies, O9 workflow wiring, product/browser acceptance и фазы 6–13. Merge main и реальные внешние deployment действия отдельно требуют полномочий; текущая локальная работа ими не блокируется.

#### Хронология resume до последней контрольной точки

- Проверенный baseline: `HEAD = origin/egorribun = f336d518eb84db5feb71e5d84bfe5d5ab72365d1`, PR #1266 открыт. Пользовательский аудит сохранён untracked, SHA256 совпадает с таблицей следующего раздела; Docker-контейнеров при resume нет. Goal активен, не завершён.
- Run `36313157002` на `29987745e` **cancelled**, а не полный мутационный результат: 55 cancelled / 9 skipped / 1 success / 1 derivative failure (`CI Success`). Новый run `36313288124` относится к `f336d518e`. Снимок 11:00 UTC: 82 success / 11 skipped / 3 failure / 8 без conclusion; не terminal evidence и не release acceptance.
- Три failed producers нового run: `Pre-commit Security & Types (Read-only)` и `Security Audit / detect-secrets Baseline Integrity` распознали пояснение в handoff как Secret Keyword; `Source/Test Inventory & Anti-Pattern Check` нашёл четыре undocumented wait bounds в `tests/test_heartbeat_watchdog.py`. Исправления проходят отдельный RED→GREEN, без ослабления сканера или sleep-policy.
- Локальный inventory дополнительно распознавал сохранённые копии тестов в ignored корневом `artifacts/wip/` как orphan/unowned source. Новый regression contract отделяет root output tree от authored source, сохраняя вложенный `app/artifacts/` в inventory. Резервные копии не удаляются.
- Параллельные bounded задачи: backend image_proxy/outbox mutation contracts в основном дереве; review/исправление Spotify offline policy в `../ue-mut-A`; review/исправление ActivityHeatmap в `../ue-mut-C`. Корневой координатор единолично делает stage/commit/push после независимого ревью; writers не пересекаются.
- Read-only review A: 23 focused files / 525 tests прошли. Найден реальный P2: удаление `networkMode: "online"` в `useNowPlaying` наследует production `offlineFirst`, из-за чего запрос выполняется офлайн. До исправления и нового offline-теста NowPlaying-пакет не переносить.
- Read-only review B: 13 focused suites / 167 tests, typecheck и changed-file lint прошли. Не переносить SpotifyConnect-тесты до проверки всех пойманных async rejections; ScheduleCardSkeleton меняет class merge semantics и требует отдельной оценки. Остальные safe groups перечислены в отчёте review, не являются 100% mutation evidence.
- Review C: 8 focused tests прошли, но typecheck выявил `string | undefined` в helper под `noUncheckedIndexedAccess`; добавить guards без ослабления TS. Удалить mutation-marker-specific assertion, обеспечить требуемую доступную табличную альтернативу heatmap с RED-тестом.
- Root verification после исправлений: `tests/test_quality_inventory.py` + `tests/test_heartbeat_watchdog.py` — 95 passed / 1 существующий POSIX-only skip на Windows; отдельный readonly Docker-run Python 3.14 — 20/20 watchdog tests на Linux, включая orphan cleanup. Первый Linux запуск загрузил общий `conftest.py` и упал на отсутствующем SQLAlchemy; он не считается evidence. Повторный запуск скопировал только watchdog test в `/tmp`, сохранив production imports через readonly `/repo`.
- `generate_test_inventory.py` и `check_orphans_and_anti_patterns.py`, Ruff, `git diff --check`, detect-secrets по шести изменённым/новым root files прошли; harness `--repo-only` — 29/29. Backend два новых файла — 7/7 свежего root-run; автор дополнительно получил 91/91 связанных tests и assertion failures всех восьми targeted mutant replays (не полная сертификация mutmut universe).
- Независимое spec review четырёх slices прошло. Code-quality review дополнительно обнаружило слабый GC-тест NowPlaying: 20 ms не доказывают 5 минут. Заменяется проверкой retention при 299 999 ms и eviction при 300 000 ms с async fake timers и cleanup QueryClient; неожиданные async errors SpotifyConnect проверяются отдельно в B.
- Контрольные локальные коммиты: `8a20fbc70` (`fix(quality): distinguish output backups and document watchdog wait bounds`) и `153256c26` (`test(quality): verify image cache eviction and durable outbox accounting`). Оба прошли штатные commit hooks; обычный push ещё не выполнен. Пользовательский audit не включён.
- Terminal CI `36313288124`: **95 success / 4 failure / 20 skipped**, conclusion `failure`. Три исходных producer failures перечислены выше; четвёртый — производный `CI Success`. Mutation downstream blocked/skipped, поэтому этот run не сертифицирует ни прежние, ни новые mutation fixes. Не трактовать все 20 skips как intentional.
- Отревьюенные A NowPlaying (включая исправление GC-теста и offline-контракты), C heatmap и B rejection-observability tests перенесены в основное дерево. Fresh combined: 4 suites / **67 passed**, full frontend typecheck, scoped ESLint/Prettier и полный `npm run lint` exit 0. Полный frontend unit run ещё выполняется; локальный canonical focused Stryker для heatmap запускается в `../ue-mut-C` и не может произвести release marker.
- Дополнительные подтверждённые gaps: SpotifyConnect async click handlers отклоняют promise без продуктового feedback (в B исправляется с существующими RU/EN ключами); watchdog O9 не имеет bounded cleanup при supervisor exceptions/cancellation, а Stryker владеет detached process groups. Нельзя слепо оборачивать `npm` текущим watchdog: CPU/termination initial PGID не охватывают эти группы. Сначала TDD hardening, затем самостоятельные ownership contracts и CI wiring с неизменными wall budgets/artifact gates.
- Все 20 skips разобраны по guards: 12 intentional (3 backend integration только shard 0; 7 Go diagnostic только schedule/manual; WebSocket10k и Trusted Codecov только protected main), 8 blocked mutation downstream. PR суммарно 140 pass / 4 fail / 26 skip, дополнительные 6 skips intentional sibling-workflows. Из 59 artifacts есть только frontend mutation **preflight**, ни executed mutation reports, ни mutmut universe/results не произведены. Tested PR merge SHA `786a6712…` отличается от head `f336d518…`.
- Local canonical heatmap Stryker: первая попытка в C остановилась до dry run из-за `ERR_MODULE_NOT_FOUND vitest`. Причина подтверждена по установленному Stryker 10: discovery принимает лишь `Dirent.isDirectory()`, NTFS-junction даёт `isSymbolicLink()`, хотя `stat()` подтверждает каталог. Повтор в основном checkout с обычным `node_modules` прошёл initial run (47 tests; 134 instrumented mutants); финальный результат ещё ожидается. Junctions не удалять, vendor-код не патчить, провал setup не считать Killed или Survived.
- **Scratch-tool ограничения:** `fresh_mutants.mjs:44` обрезает replacement до 300 characters; `mutant_check_fast.mjs:146–157` включает TIMEOUT в «not surviving» и допускает exit 0 без проверки runtime/compile failure причин. Его summaries НЕ являются свидетельством 100% viable score. В этом resume используются canonical `run-stryker.mjs` и свежие CI artifacts; focused local path отдельно помечен `local-focused` и не выдаёт release markers.
- **Обновление 14:53 Europe/Moscow:** полный frontend unit run исходного интегрированного снимка завершился: **696 files / 7 886 tests passed**, 1 282.53 s, exit 0. Это снимок до окончательного Spotify feedback и crypto/performance delta, не проверка последующего HEAD. Во время run были CSS-parser/jsdom navigation diagnostics; zero-warning acceptance ещё не доказан. После окончательного переноса свежие root runs: Spotify + реальный sanitizer + NowPlaying + heatmap **82 passed**; crypto/performance **40 passed**; полный typecheck, changed-file ESLint zero warnings и Prettier exit 0.
- Watchdog hardening: **134 passed / 8 POSIX-only skipped** на Windows (39.86 s свежего root-run), **66 passed** на digest-pinned Linux (15.23 s авторского run); независимый spec runner дополнительно 39 passed. RED доказал утечки при supervisor failure и замену первого TERM/INT вторичной ошибкой/сигналом. GREEN сохраняет 143/130, bounded owned-PGID cleanup и type-only secondary diagnostics; handlers живут до final report, затем восстанавливаются. Оба независимых spec/code reviews одобрены. **CI wiring по-прежнему отсутствует**, Windows cleanup только direct child, не утверждать process-tree equivalence или завершённый O9.
- Raw focused heatmap run `4158e463-7366-4bf0-a2c4-1b4eb4be1d8c`: 134 instrumented / 133 viable, **132 Killed / 1 Survived / 0 Timeout / 0 RuntimeError / 0 NoCoverage**. JSON сохранён в `frontend/reports/mutation/focused/f8f50a1e126609fb504dade6027c0452aab7ea701671442d74124c4f58851c18/runs/4158e463-7366-4bf0-a2c4-1b4eb4be1d8c/shard-000/`. Wrapper exit 1: **evidence changed while running**; aggregate/validated evidence не произведены, результат только диагностический. Новый повтор должен заморозить HEAD, ВСЕ dirty paths и frontend evidence, включая междоменные writers/commit hooks. Точная причина изменения старого identity отдельно не локализована; не выдавать предположение за установленный факт.
- Единственный heatmap survivor добавлял посторонний элемент в пустой month-label array; `.find` игнорировал элемент без weekIndex, поэтому нет наблюдаемого отличия. Вместо marker-specific assertions введён эквивалентный `Map<year-month, first-Monday-label>`. Независимое сравнение **4 386 cases** (каждый день 2023–2024 × все периоды × RU/EN) прошло; существующие exact geometry/locale tests зелёные. **Свежая canonical mutation-проверка изменённого source ещё требуется.**
- Spotify final feedback: реальные query invalidations используют `throwOnError: true`; callback/refetch/connect/disconnect errors доступны через localized alert, retry сбрасывает feedback. Реальный QueryClient/QueryObserver тест доказал default swallowed-refetch defect и GREEN; 29 component + 8 sanitizer tests. Offline UI acceptance и global mutation не сертифицированы этим slice.
- В utility review найден и закрыт существующий P2 crypto worker: синхронный `postMessage` throw раньше оставлял pending entry/timer на 30 s. RED два сценария; GREEN немедленно освобождает оба и сохраняет идентичность DOMException/non-Error rejection. Performance API теперь сохраняет TTFB, даже когда paint API недоступен (намеренное улучшение, не эквивалентное изменение). Независимое ревью обоих groups прошло.
- Новые coherent source/test commits после `153256c26`: `8be555820` watchdog; `cdbb3869c` Spotify feedback; `6c6b6254b` NowPlaying offline/cache contracts; `15ee6c0da` heatmap calendar/table; `61d52560f` crypto sync-failure cleanup; `b5d572b2e` independent performance metrics. Штатные commit hooks прошли; пользовательский audit не stage. Обычный push ещё ожидает checkpoint документации. Крупный WebSocket/replay/login WIP проходит отдельные независимые reviews, не интегрирован автоматически; остальные A/B WIP и все резервные копии сохранены.
- **Checkpoint опубликован:** `4c5ae5186ab366078e65063fc3ff51f2077bec5f`, обычный push, без force/merge. Run `36317352502` проверяет этот head через PR merge `92d1d5df69cae9a9f5091c55de1fcca60dfd0589` (base `481dba81…`); source/tested/base SHA не взаимозаменяемы.
- **Новые producer failures этого run:** read-only pre-commit job `108614471154` и baseline-integrity job `108614591960` распознают историческую длинную строку A-WIP как Secret Keyword; frontend lint/format job `108614943706` отвергает незарегистрированный динамический translation key `feedback.key` в SpotifyConnect. Причины воспроизведены: сырой KeywordDetector 1.5.0 даёт один hit на исходной строке; многострочное перечисление с сохранением всех модулей даёт ноль на Windows и digest-pinned Linux. Scanner/policy/baseline не ослаблены. Spotify state сужен до четырёх concrete keys, добавлена finite registry; RED→GREEN, 38 focused tests и 18 RU/EN parity tests. Полный frontend lint/format/typecheck/message-contract/depcheck exit 0; ts-prune exit 0, но выводит существующие candidates, это не доказательство отсутствия всего dead code. На снимке 15:22 Moscow run ещё не terminal: выполняются backend, Schemathesis и mobile-webkit; прочие failures не установлены.
- **Focused heatmap повтор:** run `48929fd1-1b22-4091-a50e-5dba20c46e6f`, 133 instrumented / 132 viable, **132 Killed / 0 Survived / 0 Timeout / 0 RuntimeError / 0 NoCoverage**, 8m43s. Wrapper exit 1 из-за `Mutation shard producer evidence is malformed: shard-000`: локальный producer честно записывает `workflowRunId=null`, `workflowRunAttempt=null`, а индексатор требовал CI identity. Это диагностический raw 100%, НЕ сертифицированное evidence. Исправление `44777fdad` допускает null/null или оба absent только при explicit local-focused, releaseEligible=false и подтверждённом отсутствии CI/shard environment. Canonical/CI по-прежнему strict; focused не пишет VALIDATED/LOCAL_VALIDATION. Independent review и свежий root-run **146/146 Node tests** прошли. Следующий focused запуск — только после заморозки HEAD, всех dirty paths и frontend evidence; исторический отчёт не перелабеливать.
- **Новые локальные coherent commits:** `c7de318da` finite Spotify translations; `f96ee3e6c` login/MFA error dedup и nullish persisted-email guard; `27b9c69de` spatial marker collision boundaries; `d04de3278` шесть utility sources и два genuine behavior-test файла. Login/map fresh root-run **69/69**, utilities **171/171**, typecheck и scoped lint/format прошли. У карты не удалены spatial fast paths: эксперимент ухудшал dense layout примерно 250→460 ms и полностью откатан. Utility media helper сохраняет declared string contract; unsupported truthy non-string inputs больше не coercе, проверенные callers передают строки. Global coverage/mutation этим не сертифицированы. Все commit hooks прошли, `.secrets.baseline` повторно stage и без изменений; audit сохранён untracked с прежним SHA256.
- **WebSocket P1/P2 интегрирован: `e952643ac4a4978429628ad169e8921bbd9c158e`.** Существующий transport мог пережить A→B и отправить/принять приватные room/resume данные не того аккаунта. Пять WS/replay source/test files перенесены атомарно после независимых spec/security и code-quality reviews. Теперь есть account epochs, account-keyed teardown/reconnect, abort/stale ticket guards, layout-synced refs, socket ownership для outgoing join/leave, captured-account checkpoint writes и deferred DB-write guards. RED→GREEN закрыта presence multi-callback гонка после flushSync A→B. Pre-existing typing timer leaks: unmount оставлял 2 timers, StrictMode создавал 5 вместо 2; владение timers вынесено в ref вне React state updater, cleanup синхронный, expiry callback сверяет identity entry. Автор **223/223**, свежий combined root-run **302/302**; cap contracts проверяют 20 допустимых chats, отказ 21-му и освобождение timers. Commit hook Semgrep распознал две literal URL assertions как insecure WebSocket: это доказанный test-only false positive с ScriptedWebSocket, без реального network. Assertions заменены более строгим semantic URL helper (protocol/host/path/exact query/credentials/hash); свежие **58/58**, все commit hooks прошли без suppressions или изменения baseline. Ограничения: уже начатая IndexedDB transaction не отменяется; persisted/cache data не purge; same-user JTI rotation не различима текущим currentUserId/enabled API. Не считать slice полным real-WS/E2E/race/mutation acceptance.
- **O9 integration design, ещё НЕ реализован:** monitor в существующих runNode/waitForChildClose, не внешний Python wrapper над npm (detached PGIDs/Windows Job Object остаются у Stryker). Reporter считает уникальные completed mutants, а не повторный stdout/percent/elapsed heartbeat. Progress schema bounded, run/shard identity и monotonic counters; CPU только owned PID+start identity, unknown/partial probes явные, reporter CPU исключён. Сначала измерить legit quiet phases: исторический dry run 16m34s делает слепые 900s unsafe. Chronological first-failure latch нужен отдельно: нынешний runPool возвращает ошибки в worker-array order. Always diagnostics artifacts отдельно от строгого mutation artifact. Backend: сначала доказать GNU timeout/process-group containment; сохранить existing wall budget, 600s evidence reserve, 30s kill grace и оба pipeline exit codes. Покрыть CI/nightly/manual; Go advisory lane не менять. Нужны новые ownership/provenance/workflow contracts и actionlint.
- **Supply-chain boundaries:** push сообщает 16 default-main Dependabot alerts, включая high/critical. Read-only сверка показала, что исследованные версии в egorribun уже patched (anyio 4.14.2; httpx2/httpcore2 2.12.0; urllib3 2.7.0; grpc 1.83.2; OTel 1.46.0, shared/gen 1.45.0; js-yaml 4.3.2). Это не fresh full audit и не основание dismiss/merge alerts. PRs #1289–#1292 остаются открыты; npm bump после всех пользователей shared node_modules, без concurrent installs.
- **Terminal CI `36317352502`: 92 success / 4 failure / 23 skipped.** Три failed producers перечислены выше, четвёртый — производный `CI Success`; новых product/test failures нет. Из skips 12 intentional по проверенным event/shard guards (3 backend integration, 7 Go diagnostics, protected-main WebSocket10k и Codecov), 11 blocked downstream (frontend preflight, Performance Gate, Coverage & Quality Policy Gate и 8 mutation jobs). Ни executed mutation evidence, ни green release matrix этот run не доказывает. Не повторять устаревшее утверждение «ещё выполняется» из снимка 15:22.
- **Full Linux secret scan не подтверждён:** первый readonly digest-pinned Python 3.14 run просканировал tracked inventory, но завершился ошибкой validation harness: `extract_findings` получил results без обязательного version. JSON результата не сохранён; это не finding и не успешный scan. Повтор требует version metadata, frozen tree, trusted-main baseline и штатного engine с bounded workers. Windows raw KeywordDetector и Linux single-file проверка handoff дали ноль; они не заменяют full tracked scan. Никаких scanner exclusions, policy weakening или baseline findings не добавлено.
- **Отдельно сохранённый WIP:** A четыре utility/test файла одобрены read-only; animations alias identity требует решения, bootstrap CSS serialization snapshot не переносить. B десять UI/helper files одобрены; Skeleton public radius `sm` даёт invalid inline radius и проходит отдельный RED→GREEN; uiFormPrimitives содержит два pre-existing mutation-marker assertions, заменяются genuine class-propagation contracts. ScheduleCardSkeleton class-merge изменение и остальные Event WIP требуют отдельного review. Нельзя считать authored WIP принятым или автоматически stage весь worktree.
- **Backend canonical follow-up:** все восемь image_proxy/outbox historical mutant IDs существуют в generated mutmut 3.8 source и соответствуют текущим source contracts. Диагностические replays уже записаны выше; canonical execution этих восьми на fresh stats ещё нет. mutmut 3.8 явно не поддерживает native Windows, в ue-mm2 нет prepared Linux runtime/stats. Выполнять generation/stats → exact selected execution plan → canonical run → verify exact execution → score 100 на Linux; не переиспользовать исторические stats как current provenance. Пользовательский storage WIP в ue-mm2 не трогать. Восемь targeted mutants не закрывают весь backend universe.
- **Свежие root gates после WS:** inventory generation и orphan/anti-pattern validator exit 0; `git diff --check` exit 0; пользовательский audit SHA256 неизменен. Typecheck и полный frontend lint/format/i18n exit 0 до последнего test-only semantic URL helper; helper дополнительно прошёл scoped lint/format и все hooks. Старый full unit 696/7 886 относится к предшествующему снимку, не последнему HEAD.
- **Новая опубликованная контрольная точка:** `5c2cad4de394a1c607af723427d608e94ac3ecaa`, ordinary push после всех штатных hooks и pre-push typecheck. CI Matrix run `36320204798` запущен на этом head; до terminal result не утверждать green. Предыдущие семь локальных commits (runner provenance, Spotify registry, login, map, utilities, WebSocket и docs) теперь опубликованы. Пользовательский audit единственным оставался untracked до начала следующего reviewed transfer.
- **Canonical focused heatmap, теперь успешный wrapper:** run `e599c577-81a9-48d3-8ab0-bbabcb798850`, **exit 0**, 9m13s; 133 instrumented, 132 viable **Killed**, 1 governed Ignored, ноль Survived/Timeout/RuntimeError/NoCoverage. Initial run 47 tests. Frozen `sourceRevision.headSha/sourceHeadSha/baseSha` — `5c2cad4de394a1c607af723427d608e94ac3ecaa`; dirty identity содержит ТОЛЬКО пользовательский audit, digest `9617f825682eacfd0e41540f3cd837b9a4aef75e83c2b9153be51112913827e3`. Inventory: `scope.kind=local-focused`, source только ActivityHeatmap, `releaseEligible=false`, workflow IDs null; `VALIDATED`/`LOCAL_VALIDATION` отсутствуют. Reports сохранены в `frontend/reports/mutation/focused/f8f50a1e126609fb504dade6027c0452aab7ea701671442d74124c4f58851c18/`; shard report SHA256 `13cf162e45fa8bcfb4e0f65612b2d27ab6d21b89ce41691f06e75460b79eedcd`, merged report SHA256 `7f2beed037f7849d8d063862808a2c2e2a4a21e2013e5e68faee147344691157`. Это принятый LOCAL focused результат, НЕ full-universe CI/release evidence и не переносимый сертификат последующих HEAD.
- **Full tracked Linux secret diagnostic повтор прошёл:** exit 0, 285.807 s wall; 5 018 tracked / 5 016 scanned, только два штатных CI exclusions. Scanner 1.5.0, 27 plugins/12 filters, stock `SecretsCollection.scan_files(..., num_processors=2)` под `default_settings`; version metadata и negative missing-version validation проверены до full scan. Current/allowed 321 findings (155 files), trusted 326; new unsuppressed, stale allowed, allowed-minus-trusted, new active trusted suppressions — все ноль; explicit false-positive triage valid. Start/end source SHA `5c2cad4de…`, trusted `origin/main` `481dba81ec78d7d2a33873a3a661470b0ecdd512`, byte fingerprint `34e41936bc7328eaac9b1ca23cf98184c23b7570126fc6029dce26ded1f34a85` совпали. Readonly digest-pinned Python image из предыдущего scan, CPU2/memory1GiB, network disabled, mounts readonly, bytecode writes disabled, auto-remove. Cached scanner dependencies НЕ exact CI hashlocked install; это полный локальный diagnostic, не CI-equivalence claim. Repo/baseline/audit не изменялись.
- **Reviewed transfer после окончания freeze:** B 13 файлов (7 UI sources, 5 tests, новый synchronous window-error helper), A 7 файлов (3 utilities, 4 tests), C 2 runner files перенесены apply_patch, проверены на отсутствие published overlap. Skeleton `sm` RED 45 pass/1 fail → GREEN 46/46; все named/custom radii/style precedence. Новые exact CSS serialization и marker assertions не переносились; uiForm marker assertions заменены genuine wrapper/control isolation. Animations удерживает прежний shallow clone; RED alias 6 pass/1 fail → GREEN 7/7, тест восстанавливает mutable exports в finally. Независимые spec/code reviews одобрены. Свежий combined root **15 suites / 162 tests**, exit 0, 77.40 s. Полная unit/coverage/mutation recertification ещё требуется.
- **O9 bounded runner slice:** chronological first-observed failure вместо worker-array order в runPool. RED 1 pass/1 fail; GREEN сохраняет все worker errors, first cause, ожидание in-flight workers, stop scheduling и fail-closed process quiescence. Independent review: 4 focused tests + 6 edge probes; root четыре Node suites **147/147**, exit 0. Полное watchdog ownership/reporter/CPU/CI wiring из design выше остаётся OPEN; маленький latch fix не закрывает O9.
- **Остаточный A audit:** 26 modified + 4 untracked frontend files проверены относительно base; после известных integrated/reviewed groups новых genuine production/test slices нет. Единственный остаток — held bootstrapFallback serialized-css snapshot, не переносить. Исходный isolated WIP и backups сохраняются, не удаляются автоматически.
- **Новые локальные coherent commits (ещё НЕ опубликованы на момент этого снимка):** `124ae1e79` — chronological first-failure runner latch; `f88663438` — UI defaults/Skeleton radius contracts; `9014652baec96d92215c06334a9ca1abfa04bc77` — utilities isolation/localized safety; `6e98d8988` — Events keyboard/name/action settlement. Все commit hooks прошли; `.secrets.baseline` повторно staged, изменений baseline нет. Опубликованный source всё ещё `5c2cad4de…`; не смешивать evidence двух revision.
- **Events slice принят:** EventAboutEditor textbox доступное имя RU/EN; centered edit control minimum 44×44 intent; cancel/reopen сохраняет актуальный baseline без PATCH. RED 17 pass / 2 fail (имя отсутствовало), GREEN 19/19; independent review 19/19, ESLint/Prettier/diff0. EventFileManager failure rollback использует settlement реального React useOptimistic, без mock-hook; success placeholder удаляется до awaited refresh. Три файла перенесены apply_patch; свежий root **4 suites / 57 tests**, exit 0, 23.68 s; typecheck/scoped lint/format/diff0. Actual browser geometry, screen reader и canonical mutation остаются OPEN, jsdom не доказывает пиксельную геометрию.
- **CI delta 2026-09-27 16:10 Europe/Moscow:** run `36320204798` на опубликованном `5c2cad4de…`: 84 success / 10 skipped / 8 unfinished, zero failures, НЕ terminal. Все три прежних failed producers (pre-commit security/types, frontend lint/format, detect-secrets baseline integrity) теперь success. Backend/API/mobile-WebKit и downstream matrix ещё выполняются/создаются; skips ещё не финальная классификация.
- **Остаточный B review:** ScheduleCardSkeleton `cn` меняет публичную семантику conflicting className — HOLD; существующие три tests этого не доказывают. SpotifyConnect остаток ослабляет уже опубликованный finite key union до string — REJECT transfer. Map source/untracked boundaries test и Spotify tests уже совпадают с PRIMARY, не переносить повторно и не удалять isolated WIP. Следующая независимая задача — DashboardStories playback/visibility/RAF contracts по inventory; source только после RED. O9 reporter standalone TDD делегирован в C, runner/workflow wiring пока отсутствует.
- **Terminal CI 2026-09-27:** run `36320204798` — **97 success / 2 failure / 20 skipped**. Единственный failed producer — `Coverage & Quality Policy Gate`, job `108629189913`: normalizer отвергает frontend statements и branches ниже 100%; второй failure — производный `CI Success`. Source head `5c2cad4de394a1c607af723427d608e94ac3ecaa`, tested merge `113835f8ab84289e77ed19e8b22961f04b74468d`, base `481dba81ec78d7d2a33873a3a661470b0ecdd512`. Все прежние security/lint producers прошли. Skips: 12 intentional по прежним guards, 8 blocked mutation downstream; полного нового mutation результата НЕТ.
- **Fresh coverage diagnosis:** canonical unit artifact содержит ровно два uncovered statements и два branch arms, все в `useChatWebSocket.ts`: line 714 (statement 260, branch 85 arm 0) и line 914 (statement 343, branch 104 arm 0). Оба — корректные ownership guards; защиту не удалять ради покрытия. A готовит настоящие stale-transport contracts с независимым review. Artifacts скачаны в отдельный `artifacts/ci-artifacts/36320204798/coverage-diagnosis/diag-7ce2712fce72488ea6566ffe577ba7f3`; root coverage не перезаписан. E2E raw generated-asset maps не заменяют canonical unit denominator.
- **Stories review завершён, transfer ещё ожидается:** в B два файла (DashboardStories и новый playback test). RAF ID 0 освобождается; stale callback не управляет новым viewer; исчезновение/replacement активной истории обработано; Previous первой истории сбрасывает clock, не освобождая владельцев паузы. Начальный RED 1 pass / 6 fail → 7/7; дополнительный restart RED 10 pass / 3 fail → 13/13. Автор 7 suites / 80 passed, независимое final review 13/13 и совпадающие hashes; scoped gates exit 0. Это не browser или canonical mutation closure.
- **O9 standalone reporter review завершён, transfer ещё ожидается:** C два новых Node-файла; 17/17 у автора, независимого reviewer и root. Invalid plan/writer failure latch, exclusive temp ownership, bounded descriptor cleanup, generic errors, informational/non-release payload. Reporter НЕ зарегистрирован в Stryker и НЕ подключён к runner/CI. Stryker swallowing callback errors требует независимого reader/terminal validation; следующий isolated TDD slice именно reader, без непромеренного inactivity killing или фиктивных CPU данных. Caller private-directory ownership остаётся обязательным precondition.
- **CSS diagnosis уточнён:** реальная Vite pipeline уже компилирует Tailwind, первоначальная raw-CSS гипотеза опровергнута. JSDOM 30 не понимает native nesting `.dark &` в compiled CSS. B проверил documented Tailwind optimize/minify-false lowering только в test environment: Node RED → GREEN, main entrypoint 16/16 без CSS diagnostics; development/production output byte-identical. Независимый root запуск нового test из repo root выявил зависимость от cwd (candidate `calc(...)` из постороннего inventory); автор устраняет воспроизводимость перед переносом. Нельзя отключать CSS или фильтровать VirtualConsole warnings.
- **Дополнительная локальная проверка:** актуальный root harness — **29/29**, exit 0. Backend HMAC fixture теперь явно использует рекомендуемый JWT algorithm, не затрагивая production или отдельный HS256 warning contract: strict UserWarning RED воспроизведён; GREEN 12/12, связанные tests 88/88 без warnings, Ruff exit 0; независимое review одобрено, test-only delta ещё не committed. Полный frontend unit run на frozen `fbee69a21` выполняется; перенос frontend slices и hooks после terminal результата, не смешивать snapshot identities. Пользовательский audit hash неизменен, Docker контейнеров нет, mutation backups пусты.
- **Повторный A WS inventory audit:** product hook и replay checkpoint helper, а также main/replay/closure/mutation tests уже совпадают с PRIMARY; 176/176 focused tests прошли. В isolated transport test остались два старых literal URL assertions; не переносить их поверх нового semantic helper. Это synchronization evidence, не новое независимое review автором собственной прежней реализации. Исходный WIP сохранён.
- **Дальше:** завершить frozen root unit regression → независимо принять Stories/reporter/CSS и два WS coverage contracts → small commits и актуальный handoff → ordinary push (предыдущий CI уже terminal) → canonical focused verification и fresh full mutation inventory → O9 wiring/npm/O4 и оставшиеся фазы 6–13. Полный долг §0.000000 и acceptance §6–§13 сохраняются; 6 083 frontend mutation outcomes нельзя объявлять закрытыми по focused suites. Root-only stage/commit; не трогать audit/stash/junctions/backups, не merge main/deploy реальный staging без разрешения.

### 0.000000 Безопасная пауза 2026-09-27 — предшествующий снимок

Всё ниже §0.000000 — история. Активный план: `C:\Users\egorribun\.claude\plans\rustling-dazzling-stearns.md` (фазы 0–13). Решения пользователя: память `mvp-decisions-2026-09-25`, `mvp-scope-decisions-2026-09-23`, `standing-permissions-2026-09-24`, `frontend-stryker-hybrid-decision`, `windows-build-rewrites-wasm`.

#### 1. Идентичность и сохранность (проверено при паузе)

| Объект | Состояние |
| --- | --- |
| Ветка / PR | `egorribun`, PR #1266 → `main` (OPEN). Merge в `main` — только с разрешения пользователя |
| HEAD = `origin/egorribun` | `29987745ece30ff72cf9d171ae0707c7b07bb845`; локально незапушенных коммитов нет |
| Рабочее дерево | чистое, кроме пользовательского untracked `docs/audits/AUDIT_PLATFORM_FULL.md` (SHA256 `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b`, не трогать и не стейджить) |
| CI на HEAD | run **36313157002** запущен при паузе (статус `pending`) — первым делом проверить итог |
| Процессы | все агенты остановлены; mutant_check/mm_loop/циклы агентов убиты; `artifacts/quality/mutation-tools/mutant-backups/` пуст (последние бэкапы восстановлены: `ue-mm2/app/services/storage.py`, `ue-mut-A/frontend/src/utils/animations.ts`, `ue-mut-C/.../ActivityHeatmap.tsx`) |
| Docker | контейнеров нет; том `university_ecosystem_minio-data` сохранён |
| Ресурсы | WSL поднят пользователем: Docker VM 11.7 GiB / 12 CPU / swap 8 GB |
| Worktrees | `../ue-mut-A` и `../ue-mut-B` на `d576fd208`, `../ue-mut-C` и `../ue-mm2` на `4cbe00c9f` (все detached), `../ue-e2e`, `../ue-mm` — старые. В `ue-mut-A/B/C` `frontend/node_modules` — **NTFS-junction** на основной repo: никогда не удалять рекурсивно (`cmd /c rmdir <path>\frontend\node_modules` сначала, потом `git worktree remove`). `ue-mm2` junction не имеет |

#### 2. Коммиты с прошлой паузы (все опубликованы)

`590b3c57c` Go-бамп (#1292; `go.sum` через `go mod tidy`, удалён неиспользуемый testcontainers MinIO) · `4564c11b6` Actions-бамп (#1291; новые SHA применены во всех workflow и в контракте WASM-тулчейна; 906 контрактов) · `2d429678f` pip-бамп (#1290; strawberry 0.327.7, mutmut 3.8.0, libcst 1.9.0; 523 теста; `mm_loop` работает с mutmut 3.8) · `713e5b256` heartbeat watchdog O9 (`scripts/quality/heartbeat_watchdog.py`, 20/20 на Linux в `python:3.14-slim-bookworm`; **ещё не подключён к CI**) · `4cbe00c9f` handoff · `29987745e` backend-мутанты (см. §4).

Dependabot PR #1289–#1292 сами не тронуты (закрытие — с разрешения). **npm-бамп #1289 не перенесён**: делать, когда нет агентов (общий `node_modules` через junction): `git fetch origin pull/1289/head:refs/remotes/dependabot/1289`, применить `package.json`/`package-lock.json`, `npm ci`, полный frontend gate, восстановить WASM/provenance (память `windows-build-rewrites-wasm`).

#### 3. Полный мутационный инвентарь (CI run 36194161259 на `43279cce8`, все 64 шарда Stryker + 128 групп mutmut)

- **Frontend Stryker:** `artifacts/quality/mutation-tools/inventories/ci-36194161259-full.json` — 35 568 Killed, 1 306 Ignored (ADR-040), **6 083 проблемных**: 5 958 Survived, 67 Timeout, 46 RuntimeError, 12 NoCoverage в **295 файлах**. Мутаторы: StringLiteral 1414 (i18n-ключи 348, ключи/массивы 145, сравнения/enum 128, className лишь 25), ConditionalExpression 1294, ArrayDeclaration 583 (массивы зависимостей хуков → `[]`), ObjectLiteral 483, LogicalOperator 375, BooleanLiteral 331, CallExpression 313, BlockStatement 260, EqualityOperator 247, OptionalChaining 245, прочие <210. Это **поведенческий** долг — закрывать тестами/эквивалентными упрощениями, не расширением ADR-040 (оно требует нового ADR и решения пользователя).
- **Очереди для агентов** (непересекающиеся, `[file, bad, nonSurvivor]`, приоритет Timeout/RuntimeError/NoCoverage): `inventories/queue-A.json` (hooks, push, sw, stores, utils, api, contexts, db, app, i18n, notifications, config, types и корневые `src/*.ts(x)` — 108 файлов / 2 378), `queue-B.json` (components, pages — 116 / 2 220), `queue-C.json` (features, routes и прочее — 71 / 1 485). Пересобрать очереди после новых коммитов по свежему CI.
- **Backend mutmut:** `inventories/mutmut-36194161259.json` — **143 Survived + 1 Timeout** в 12 модулях: storage 44, chat.attachment_service 39, core.events 15, event_handlers 11, auth.mfa.email_otp 11, workers.cdc_outbox 9, image_proxy 7, notifications.dedupe 4, chat.notification_service 1, workers.outbox 1, system_release 1, schedule_changes 1. Логи всех 75 упавших групп: `artifacts/ci-logs/mutmut-36194161259/*.log`; подтверждённый статус разбирать по блокам `=== confirming <mutant> ===` → `Mutant results` (первичные «🙁» в логе включают убитых при подтверждении).

#### 4. Backend: что закрыто в `29987745e` и что осталось

Закрыто тестами/упрощениями (поведенческие тесты прошли: 1 827 связанных тестов; **мутационная перепроверка локально НЕ завершена** — её подтвердит CI run 36313157002, либо `mm_loop` в `../ue-mm2`):

- `storage`: общий `_has_control_chars` (границы 0x1f/0x20/0x7f/0x80), точные сообщения, `max_bytes=0`, отсутствие лишних `read` после лимита, таймаут `probe_bucket`, лог-события; убраны эквивалентные `rstrip("/")`, `cast(bytes, …)`, дефолт `.get("Code", "")`. Бывший **Timeout** `read_file__mutmut_30` (`<` → `<=`) порождали фейковые потоки, отдававшие данные на `read(0)`; теперь фейки реалистичны (`read(0)` → `b""`) в `tests/test_s3_storage_read_errors.py` и `tests/test_storage_key_boundary_contracts.py`.
- `chat.attachment_service`: константы `_CLEANUP_FAILED/_COPY_FAILED`, границы размера (0 и ровно max), `locale`/аргументы `process_upload`, чужой URL при реальном `StaticFSStorage`, подсчёт отказов по пачкам (флаг `failed` заменён счётчиком), удалено мёртвое `len(data) > max_size`. Тесты: `tests/test_chat_attachment_copy_contracts.py`.
- `core.events`: сообщения вынесены в константы, `deferred = any(...)`; тесты `tests/test_event_bus_durable_contracts.py` (включая форму SQL и итоги обработчика очистки вложений).
- `auth.mfa.email_otp.SmtpMfaEmailSender.send`: флаг `delivered` заменён на `except BaseException … abort; raise` (`# RZ-22-01-JUSTIFIED: cleanup then re-raise`); тесты `tests/test_mfa_smtp_sender_contracts.py`.
- `notifications.dedupe`: SQL в модульной константе `_DEDUPE_LOCK`; ключи блокировки для `system_release`, `schedule_changes`, `ChatNotificationService` и CDC-сообщения/лог — `tests/test_notification_dedupe_lock_contracts.py`.

**Осталось (backend):**

1. `services.image_proxy` (7): попытка удалить `.lstrip("/")` в `_backend_source_path` **сломала 4 теста и откатана** — `_sanitize_path_input` возвращает путь с ведущим `/`, мутант `lstrip("XX/XX")` не эквивалентен; нужен тест с путём с ведущим `/`. Плюс тесты на `redis_client.delete(redis_key)` и точное лог-сообщение «Redis stale image eviction failed: %s» при ошибке Redis.
2. `workers.outbox` `deferred_count += 1` → `= 1`: тест «3 события, 2 отложены, 1 успешен → `process_batch()` возвращает 1» написан, но возвращал 0 — причина не найдена (возможно, `batch_size`/выборка событий или порядок); разобраться по образцу `tests/test_outbox_worker.py::test_durable_outbox_deferral_preserves_retry_budget_and_pending_event`, тест удалён до исправления.
3. Мутационно подтвердить все модули §4 (CI или `mm_loop`): `cd ../ue-mm2`, синхронизировать с HEAD (`git stash -u` локальных копий или сравнить `cmp`), `PYTHONIOENCODING=utf-8 ../university_ecosystem/.venv/Scripts/python.exe ../university_ecosystem/artifacts/quality/mutation-tools/mm_loop.py --file app/services/storage.py --tests "<файлы тестов>" <имена мутантов>`. Прогон `--all` по `storage.py` занимает часы (мутанты `get_storage_backend` убиваются лишь в конце набора, ~60 s каждый) — выбирать имена функций регуляркой через `mm_check.mutated_code`.
4. Два теста `tests/test_mfa_smtp_cancellation_contract.py` с реальными сокетами (`drip_fed`, `lost_data_ack`) **падают на этом Windows-хосте и до, и после изменений** (вероятно `networkingMode=mirrored` в `.wslconfig`); в Linux CI проходят — не считать регрессией, подтвердить по CI.

#### 5. Frontend фаза 4: частичная работа агентов (НЕ отревьюена, НЕ перенесена)

Бэкапы: `artifacts/wip/phase4-2026-09-27/ue-mut-{A,B,C}.patch`, `…untracked.txt`, `untracked-{A,B}/…`. Более ранние бэкапы: `artifacts/wip/phase4/`.

- **A (`../ue-mut-A`, база `d576fd208`)**: исторический снимок 24 файлов + 4 новых; актуальная дельта принятия — в §0.resume-20260927.
  - Утилиты: `a11y`, `animations`, `browser`, `cache`, `cryptoWorker`, `media`, `performance`, `sanitize`, `slugify`, `spotify`, `weatherIcons`; тесты bootstrapFallback, trustedTypes и app/pwaEvents.
  - Дополнительный модуль утилит: frontend/src/utils/passwordStrength.ts.
  - Крупный рефакторинг `hooks/useChatWebSocket.ts` (−369 строк) с выносом `hooks/chatReplayCheckpoints.ts`; новые тесты `chatReplayCheckpoints.test.ts`, `useChatWebSocket.transport.test.tsx`.
  - `hooks/useNowPlaying.ts` + `useNowPlaying.polling.test.tsx`; начатые упрощения `hooks/auth/useLoginFlow.ts` (агент был прерван перед их применением — проверить целостность).
- **B (`../ue-mut-B`, база `d576fd208`)**: 16 файлов — `components/ui` (`Card`, `GlassCard`, `SafeHtml`, `ScheduleCardSkeleton`, `Skeleton`, `Spotlight`, `TextField`, `Textarea`) и тесты, `components/events/{EventAboutEditor,EventFileManager}.tsx`, новый `tests/helpers/windowErrors.ts` (назначение уточнить при ревью). `frontend/src/__scratch_b/` удалить, если остался. Badge-литералы — решение: рефакторинг в зону ADR-040 с идентичным выводом или вопрос пользователю, не пиннинг CSS.
- **C (`../ue-mut-C`, база `4cbe00c9f`)**: `features/activity/components/ActivityHeatmap.tsx` + его тест (238 строк).

**Как принимать:** для каждого файла: прочитать дифф; убедиться, что упрощения сохраняют поведение; `fresh_mutants.mjs` + `mutant_check_fast.mjs` на весь файл (N/N, 0 TIMEOUT); перенести в основное дерево (`git -C ../ue-mut-X diff -- <files> | git apply`), `npx tsc --noEmit -p .`, eslint, prettier, полный `npx vitest run`, коммиты `test(quality): …`/`refactor(frontend): …` пакетами. Дифф A по `useChatWebSocket.ts` — отдельный тщательный ревью (WebSocket-транспорт, реконнект, replay), при сомнении — `code-review`/`security-review` скиллы.

#### 6. Инструменты и выученные правила

- `artifacts/quality/mutation-tools/mutant_check_fast.mjs` теперь с `bail: 1` (как Stryker): без него медленные падения выглядели TIMEOUT. Флаги: `--timeout 30000 --inventory <json> --file <src> --tests "<files>" [--only ids]`. `fresh_mutants.mjs --out <json> <src>` (НЕ передавать `--help` — пишет файл `--help`).
- Фильтр мутантов по изменённым строкам: `git diff -U0 HEAD -- <file>` → диапазоны `+start,count` → отбор по `location.start.line+1`. Пути в инвентарях — в регистре git (`src/pages/settings/...`, не `Settings`).
- Зависание под фейковыми таймерами = Stryker Timeout (запрещён). В быстрых тест-файлах ставить `vi.setConfig({ testTimeout: 2_000 })` (пример: `frontend/src/push/__tests__/subscribe.test.ts`), чтобы мутант падал как Killed; реалистичные фейки (read(0) → пусто).
- Агенты: максимум 3, каждый в своём worktree; запрещать фоновые циклы проверок (агент B запускал `run-rest.sh`, который пережил остановку агента и запускал новые проверки — при паузе убивать процессы `mutant_check|mm_loop|run-rest|phase4-` и восстанавливать `mutant-backups/`).
- Коммит только когда никто не пишет в основное дерево (pre-commit прячет unstaged). После detect-secrets — `git add .secrets.baseline`. Push отменяет текущий CI (`cancel-in-progress: true`) — пушить после получения нужного инвентаря.
- detect-secrets может распознавать названия переменных как credentials. Для фикстур endpoint использовать точное имя `privatePushEndpoint`; реальные секреты не переименовывать ради обхода сканирования.
- Ruff S608 — не собирать SQL f-строкой в тестах (использовать `sa.insert(sa.table(...))`); S603 для `subprocess` — `# noqa: S603 - <причина>`.

#### 7. Прочие открытые пункты плана

- **O4:** обязательные контексты `main` (92, `artifacts/quality/o4-required.txt`) сверить с реально производимыми check-runs на зелёном SHA; на `43279cce8` не хватало агрегатов (прогон был незавершён).
- **O9:** подключить `heartbeat_watchdog.py` к долгим CI-стадиям (mutation shards) + контракт-тест workflow + запись в catalog.
- **Фазы 6–13** по плану: live-E2E лейн против Docker Core, спеки Stage 1–8, zero-warning build, CSpell RU (dev-only словарь), WASM Linux-parity, security-сканы, O1–O8, Docker Core/full, SeaweedFS cutover с сохранением данных, kind (TLS/Kyverno/observability/rollback), exact-six образы, финальный SHA-аудит, merge (с разрешения).

#### 8. Порядок возобновления

1. `git status --short --branch`, `git log origin/egorribun..HEAD`, SHA аудита, `ls artifacts/quality/mutation-tools/mutant-backups`, `docker ps -a`, процессы `mutant_check|mm_loop`.
2. Итог CI run 36313157002: разобрать падения; скачать **новый** полный инвентарь Stryker/mutmut (всё в `artifacts/ci-artifacts/<run>/`), пересобрать очереди A/B/C.
3. Backend остатки §4 (image_proxy, outbox) → мутационная проверка → коммит.
4. Ревью и перенос частичной работы агентов §5 → коммиты → запуск агентов по очередям пакетами (~8 файлов), ревью каждого пакета.
5. После снижения фронтенд-долга: npm-бамп, O4/O9, затем фазы 6–13.

### 0.00000 Безопасная пауза 2026-09-26 (лимит сессии) — история

План прежний: `C:\Users\egorribun\.claude\plans\rustling-dazzling-stearns.md`. Лимит WSL поднят пользователем (Docker VM 11.7 GiB / 12 CPU). §0.0000 ниже — предыдущая пауза, теперь история.

**Опубликовано (`origin/egorribun` = `43279cce8`):**

1. Фронтенд Push-границы аккаунта: `dd5daecb1`, `425ca62f6` (6 находок security-review), `43279cce8` (покрытие).
2. UI выбора 5 тем: `cc8c0ad13 feat(wave213)`.
3. ADR-041 дополнен: `d576fd208`.
4. Прочее: `2b7457f56` (File.url в file-processor), `a31df2f0f` (песочница mutmut), `e53e37047` (BE-02 read-only preflight каталога; на PG17: head → 12 converged, 202609220001 → 10 pending/2 converged).

Проверки: полный Vitest 695 файлов/7859 тестов; мутационно по изменённым строкам `subscribe.ts` 56/56, `usePushPreferences.ts` 28/28, `api/notifications.ts` 9/9, `NotificationsSection.tsx` 8/8, `authIdentity.ts` 64/64, `useAuthApi.ts` 23/23.

**Локально, НЕ запушено (4 коммита поверх `43279cce8`):** `590b3c57c` Go-бамп (#1292), `4564c11b6` Actions-бамп (#1291, 906 контрактов), `2d429678f` pip-бамп (#1290: strawberry 0.327.7, mutmut 3.8.0), `713e5b256` heartbeat watchdog O9 (20/20 на Linux). Push отложен, чтобы не отменить CI run **36194161259** на `43279cce8` (`cancel-in-progress: true`): на момент паузы 89 success / 11 skipped / 4 in_progress, падений нет — ждём его полный инвентарь Stryker. При возобновлении: проверить итог run, затем `git push origin egorribun`.

**Фаза 4 (мутационный долг) — частично, НЕ закоммичено, НЕ отревьюено:**

- Частичный CI-инвентарь (33/64 шарда run 36157153947): `artifacts/quality/mutation-tools/inventories/ci-36157153947-partial.json` — 162 проблемных мутанта в 31 файле.
- Агенты остановлены по паузе. Их незавершённые правки лежат в worktree `../ue-mut-A` (утилиты, 19 файлов) и `../ue-mut-B` (UI-компоненты, 16 файлов + новый `frontend/src/tests/helpers/windowErrors.ts`, мусорный `frontend/src/__scratch_b/` удалить). Резервные патчи: `artifacts/wip/phase4/ue-mut-{A,B}.patch`, `…untracked.txt`, `windowErrors.ts`. Оба worktree на `d576fd208`; старые остатки агентов прошлых сессий — в `git -C ../ue-mut-X stash list`.
- Процессы мутаций убиты, `mutant-backups/` пуст, мутантов в файлах не осталось (восстановлены `EventAboutEditor.tsx`, `EventFileManager.tsx` в ue-mut-B). Инструмент `mutant_check_fast.mjs` теперь с `bail: 1` (как Stryker).
- При возобновлении: продолжить агентов (или заново) по тем же файлам, затем ведущий ревьюит дифф, переносит в основное дерево, полный Vitest, коммиты `test(quality): …`.

**Дальше по плану:** npm-бамп #1289 (после агентов: общий `node_modules`), O4 (сверка 92 обязательных контекстов `main` с реально производимыми после завершения run), подключение watchdog к CI, фазы 6–13.

### 0.0000 Безопасная пауза 2026-09-25 (вечер, лимит сессии) — история

Работа идёт по утверждённому плану `C:\Users\egorribun\.claude\plans\rustling-dazzling-stearns.md` (фазы 0–13; решения пользователя 2026-09-25 — в памяти `mvp-decisions-2026-09-25`). Разделы §0.000 и ниже — история.

**Закоммичено после `c6b2c9046` (проверять `git log origin/egorribun..HEAD`):**

1. `68fcd1268 test(auth)`: fixture `_delivery_fixture` получила `lease_expires_at` (устраняет 3 падения CI run 36118352908) и граничные регрессии: без lease или lease ровно до SMTP-дедлайна — `DurableEventDeferred` без отправки; +1 µs — отправка. Мутант `<=`→`<` вручную убит. MFA-наборы 243 passed.
2. `91c9597f1 fix(notifications)`: каноническая модель тем (ADR-041).
   - `UserPushTopic` — источник истины.
   - POST `/push/subscribe` при omitted или `[]` привязывает endpoint к записи вызывающего; непустой список — явное обновление, зеркалируемое на его устройства.
   - Перенос endpoint не читает и не меняет прежнего владельца.
   - unsubscribe не трогает предпочтения.
   - Удалены `_refresh_user_topic_preferences` и `resolve_topics`.
   - Проверки: 917 push/notification тестов; на реальном PostgreSQL 58 + 2 integration (конкурентный захват endpoint); mutmut 13/13 и 28/28.
3. `a6fb310ca fix(ci)`: `rust-lint`/`rust-tests` в `ci.yml` пинованы на 1.97.1 (контракт в `tests/test_frontend_docker_wasm_parity.py`), `.secrets.baseline` сдвиг строк.

**НЕ закоммичено — фронтенд-часть фазы 2.2 (агент остановлен по паузе, не отревьюено):** ~30 файлов `frontend/` (новые `src/stores/authIdentity.ts` + тест; `push/subscribe.ts`, `hooks/usePushPreferences.ts`, `hooks/auth/useAuthApi.ts`, `useProfileSync.ts`, `main.tsx`, `setupTests.ts`, `tests/e2e/utils/mockApi.ts`; удалены `hooks/usePushSync.ts` и его тест).

- **Состояние:** последний отчёт агента — полный Vitest зелёный (7823/7824, одно падение он исправил), затем шла мутационная проверка `authIdentity.ts`. Прерванный мутант восстановлен из crash-backup, `authIdentity` 26/26 passed, `mutant-backups/` пуст.
- **Резервные копии:** `artifacts/wip/push-frontend-wip-2026-09-25-pause.patch`, `artifacts/wip/untracked/…` и более ранний `artifacts/wip/push-wip-2026-09-25.patch` (исходный WIP).
- **Следующий шаг:**
  1. Прочитать diff целиком и сверить с планом §2.2: identity gate без заглушек `ssr-stub`/`-1`/`lhci-*`, темы только явно, очередь вместо `globalEnsureLock`, logout отвязывает endpoint.
  2. Прогнать focused Vitest, typecheck/lint/prettier и Stryker по `authIdentity.ts`, `subscribe.ts`, `usePushPreferences.ts`.
  3. security-review, затем коммит `fix(notifications): gate push persistence on confirmed identity` и `fix(notifications): unbind push endpoint on logout`.
  4. Затем §2.3 (UI выбора тем, `feat(wave213)`) и admin `has_preferences` (схема + регенерация SDK).

**Прочее:**

- Пользовательский аудит `docs/audits/AUDIT_PLATFORM_FULL.md` не тронут.
- Контейнеры не запущены (одноразовый PG `claude-push-pg-adr041` удалён).
- Создан дополнительный worktree `../ue-mm2` (detached `68fcd1268`, копии закоммиченных backend-файлов, **без** node_modules junction) — для mutmut. Можно удалить через `git worktree remove --force ../ue-mm2`.
- Push этого снимка и трёх коммитов выполнен обычным `git push origin egorribun`; свежий CI — фаза 3 плана.

### 0.000 Безопасная пауза 2026-09-25 13:04 Europe/Moscow — АВТОРИТЕТНЫЙ СНИМОК

**Причина остановки:** прямой запрос пользователя «дойди до контрольной точки и приостанови безопасно работу; обнови handoff». Это сознательно незавершённая реализация, а не заявление о green CI или готовом MVP. Этот раздел является дельтой к полному scope §6–§13 и актуальному continuation/master plan; старые статусы §0.00–§5 читать только как историю. Сведения о live GitHub неизбежно стареют — сверить их при следующем resume.

#### A. Сохранность, точная идентичность и границы

| Объект | Проверенный факт на момент паузы |
| --- | --- |
| Репозиторий / ветка | `C:/Users/egorribun/Documents/university_ecosystem`, **`egorribun`**, не менять рабочую ветку пользователя. |
| Локальный HEAD перед этим обновлением | `6b1e2c707ec228b05d16a716b28aa1566270b23e` — `test(storage): verify signed and anonymous S3 object access`. |
| Опубликованный `origin/egorribun` / PR #1266 | `1488096d0621a7292e0664346c67117e37021f85`, [PR #1266](https://github.com/egorribun/university_ecosystem/pull/1266) открыт, base `main`, GitHub `mergeable=MERGEABLE`. Локальный HEAD на **один коммит впереди**; его нельзя называть опубликованным или покрытым текущим CI. |
| Локальные НЕЗАКОММИЧЕННЫЕ файлы | `frontend/src/api/notifications.ts`, `frontend/src/api/__tests__/notifications.test.ts`, `frontend/src/push/subscribe.ts`, `frontend/src/push/__tests__/subscribe.test.ts`. Это WIP текущей попытки, **не сбрасывать и не публиковать как готовое**: независимое ревью выявило два существенных дефекта. |
| Пользовательский untracked | `docs/audits/AUDIT_PLATFORM_FULL.md`, SHA256 `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b`; не удалять, не переписывать и не включать широким `git add -A`. |
| Stash | `git stash list --date=iso` не вывел записей на момент проверки; это не основание менять stash при resume. |
| Worktrees | Основной плюс `../ue-e2e`, `../ue-mm`, `../ue-mut-A/B/C` (detached). Не удалять автоматически: §0.1 предупреждает о NTFS-junction `node_modules` на основной repo. |
| Docker | `docker ps -a` пуст; `university_ecosystem_minio-data` существует и **сохранён**; Docker Engine 29.8.0. Live S3 cutover и перенос объектов не проводились. |
| Subagents | `/root/security_arch_148`, `/root/security_frontend_diff_148`, `/root/security_auth_diff_148` завершили bounded задачи; работающих дочерних агентов и локальных тестовых процессов после проверки нет. |
| Goal | Долгосрочная цель остаётся незавершённой и переводится в `paused` по этой явной просьбе. Не выставлять `complete` по частичному CI. |

**Финальная сверка handoff 2026-09-25 13:19 Europe/Moscow:** документ зафиксирован отдельным текущим `HEAD` (`docs(quality): checkpoint current CI and push-account blockers`); точный SHA проверять `git rev-parse HEAD`, а не вычислять по тексту внутри самого коммита. Ветка `egorribun` на **два** коммита (`6b1e2c7` и handoff `HEAD`) впереди `origin/egorribun`; оба **не запушены**. Четыре frontend WIP-файла по-прежнему unstaged, пользовательский аудит по-прежнему untracked с тем же SHA256; `git diff --check` и `git diff --cached --check` exit 0. Таблица выше фиксирует состояние **до** коммита handoff и объясняет, почему там указан один опережающий коммит. Не делать push только ради checkpoint при известных frontend trust-boundary дефектах; сохранять эту local/remote границу явно.

В этой остановке **не было** merge, force-push, обхода branch protection, деплоя, запуска/удаления контейнеров, изменения Docker volumes, cloud credentials или пользовательского аудита. Исправления после `1488096d0` не представлены в PR, кроме того что уже было опубликовано до снимка. Не запускать новый full CI ради старого SHA, когда локальный WIP ещё требует исправлений.

#### B. Что произошло после предыдущего §0.00

1. Уже опубликованные локально проверенные коммиты `667a11ae6` (CI provenance и durable schedule assertions), `d84e44c09` (Push persistence fail-closed) и `1488096d0` (bounded MFA SMTP delivery/lease) находятся в `origin/egorribun`; **их фактический свежий CI не зелёный**, см. C.
2. `6b1e2c707` — локальный, не опубликован. Реальный disposable SeaweedFS S3-контракт в `tests/integration/test_minio_integration.py`: подписанный presigned GET читает загруженные байты; тот же объект без подписи получает HTTP 403. RED получен с намеренно неподписанным GET (403, exit 1), GREEN всего файла `2 passed` (exit 0, ~4.18 s); Ruff check/format и `git diff --check` пройдены. Это доказывает только одноразовый тестовый endpoint, **не** перенос старых MinIO objects, не Compose Core/full и не staging. Никакой старый том не тронут.
3. Frontend WIP после `1488096d0` (четыре файла в A): generated Axios client теперь вызывается с `throwOnError: true`; наружу выходит status-only `PushSubscriptionPersistenceError` без request config/body/endpoint/keys. `409`/`429` не превращаются в ложный успех; recovery выставляет consent только после сохранения; введён per-user owner marker и проверка смены аккаунта во время запроса. Тесты добавлены в соответствующие API/Push suites. Это **частично готовая**, а не завершённая защита — см. D.
4. Независимое ревью API/Push: `/root/security_frontend_diff_148` подтвердил отсутствие новой утечки ключей через safe API error и RED→GREEN 409/429; `/root/security_auth_diff_148` обнаружил два реальных account-boundary дефекта в WIP; `/root/security_arch_148` проверил S3 путь. Отчёт sealed security plugin на **предыдущий опубликованный** diff `5cebe7df7..1488096d0`: scan ID `2a9e4a40-51a5-432c-94aa-ebe1eeb7e51a`, 7/7 changed items reviewed, 0 новых findings, отчёт `C:/Users/egorribun/.codex/state/plugins/codex-security/scans/university_ecosystem/1488096d0621a7292e0664346c67117e37021f85_20260925T092926Z_yjtiouxe/report.md`. **Он не покрывает ни 6b1e2c7, ни текущий frontend WIP.**
5. Пользователь подтвердил архитектурный выбор **поддерживаемого OSS S3-хранилища** вместо лицензируемого AIStor. В текущем repo это SeaweedFS с opt-in cutover; пользователь не выдавал разрешение на destructive migration, удаление legacy тома или слепое переключение production writers.

#### C. Свежий CI опубликованного SHA: единственный обнаруженный producer failure

- [Run 36118352908](https://github.com/egorribun/university_ecosystem/actions/runs/36118352908), `headSha=1488096d0621a7292e0664346c67117e37021f85`: первоначальный снимок 10:04 UTC был `in_progress` (91 success / 11 skipped / 1 failure / 2 unfinished). **Финальная сверка 10:19 UTC:** run `completed/failure`, **93 success / 24 skipped / 2 failure** из 119 jobs. Два красных контекста: producer backend shard 1 ниже и производный `CI Success`; новых независимых failed producers нет. Двадцать четыре skipped нужно классифицировать по `if:`/DAG перед финальным audit: среди них есть downstream quality/coverage/mutation jobs, пропущенные из-за красного upstream, а не успешно пройденные gates. `gh pr view 1266` по-прежнему показывает опубликованный source SHA `1488096d0`. Учитывать разницу между PR source SHA `1488096d0` и tested merge SHA `f929df40a039047ba9bd54ec3bf937ccff64e7d4` в job logs; нельзя подменять одно другим в audit.
- Упавший producer: `Backend Tests (Python 3.14-shard-1) / Unit Tests (All-Python 3.14-shard-1)`, job `108018917327`. Лог доступен через `gh api repos/egorribun/university_ecosystem/actions/jobs/108018917327/logs` даже пока run in progress. Итог job: **3 failed / 2637 passed / 15 skipped**, 853.23 s, exit 1. `gh run view --log-failed` во время активного run не возвращает лог, но API jobs/logs возвращает HTTP 200.
- Все три failure в `tests/test_backend_mutation_survivor_contracts.py`: `test_delivery_cancellation_requires_an_explicit_single_row_update`, `test_delivery_completion_requires_an_explicit_single_row_update`, `test_delivery_completion_with_single_rowcount_succeeds`. `_delivery_fixture()` создаёт `SimpleNamespace` без `lease_expires_at`, а после `1488096d0` `EmailOtpService.deliver()` читает `delivery.lease_expires_at` при повторной проверке ownership после row locks (`app/auth/mfa/email_otp.py:1162`). Результат — `AttributeError`, тест не доходит до своей rowcount-ветки. Изолированное локальное воспроизведение тех же трёх: **3 failed, 12 deselected**, exit 1, 2.57 s. Локальные два `PytestCacheWarning` о правах `.pytest_cache` не являются причиной трёх assertion failures, но не скрывать их при будущем zero-warning аудите.
- **Следующий минимальный TDD patch:** дать fixture реалистичный `lease_expires_at=NOW + timedelta(minutes=2)` и проверить, что более строгий production guard продолжает fail-closed при истекшей/чужой lease. Прогнать три RED→GREEN, затем весь `tests/test_backend_mutation_survivor_contracts.py`, связанные MFA/unit/integration suites и shard-aware local preflight. Если появляются дополнительные мок-расхождения, не отключать guard или тест. Только затем отдельный coherent `test(auth): ...` commit.
- Нельзя назвать 93 success доказательством всей матрицы: run терминально красный, а часть quality/mutation/manifest jobs не исполнялась после producer failure. Даже гипотетический green старого SHA не покрыл бы локальные WIP, `6b1e2c7` и текущий handoff `HEAD`.

#### D. Два подтверждённых блокера frontend WIP — исправить ДО commit/push

1. **Межаккаунтные темы при восстановлении consent.** `frontend/src/push/subscribe.ts:460-494` вызывает `persistSubscriptionWithBackoff(json)` без `topics`; backend `app/routers/notifications.py:315-329` при существующем endpoint вычисляет `resolve_topics(payload.topics, existing.topics)`. После logout пользователя A browser subscription остаётся; login B вызывает recovery раньше soft sync (`frontend/src/main.tsx:93-101`). Так B может унаследовать список тем A, а owner marker уже будет B. Это security/privacy и корректность settings, не только дублирующий POST. Нужен явный контракт переноса endpoint к B **с B-owned canonical preferences**, либо другой fail-closed способ, подтверждённый backend integration; не подставлять A topics из localStorage.
2. **Cold boot до hydration auth стирает prefs.** В `ensurePushSubscription` около `subscribe.ts:694-712` при `useAuthStore.loading=true`, `user=null`, пустом profile cache получается `currentOwner=null`, `topicsToPersist=[]`, `shouldPersist=true`. Load-event SW setup (`main.tsx:183-190`) может отправить существующий endpoint с действующей cookie пользователя A прежде `/users/me`. Backend `_refresh_user_topic_preferences` при пустом массиве удаляет preference record (`app/routers/notifications.py:130-137`), а `subscription_supports_topic` трактует empty как unrestricted/all (`app/services/push_topics.py:184-192`; тест `tests/test_push_topics_service.py:213-220`). Это восстанавливает все-topic доставку вопреки настроенной фильтрации. **Пустой `[]` здесь НЕ opt-out**. Не выполнять persistence/transfer, пока текущая авторизованная identity не подтверждена live auth state; не использовать stale profile cache как security authority.
3. При следующем resume сначала добавить два RED frontend-теста с реальными условиями A→B/recovery и auth-loading cold boot, плюс backend contract/integration для `None` vs `[]` и принадлежности endpoint. Затем выбрать и проверить canonical B preferences: изучить `GET /api/v1/push/topics`, frontend queries/Settings, хранение `UserPushTopic` и semantics default/all. Не менять историческую `[]` семантику или product opt-in незаметно. Защитить request in flight от смены identity, но учесть что серверный POST может уже завершиться после клиентской смены; backend должен быть final authority. После GREEN — независимое security review нового diff и full relevant frontend/backend checks. Если источник B preferences не гарантирует безопасного account transfer, приостановить transfer и явно попросить решение, а не отправить скрытое наследование.
4. Текущий WIP прошёл локальный `npm run typecheck` (exit 0, 2026-09-25 10:04 UTC) и focused `npx vitest run src/api/__tests__/notifications.test.ts src/push/__tests__/subscribe.test.ts`: **44 + 93 = 137 passed**, 2 files, exit 0, 7.33 s. Эти тесты **не покрывают** дефекты 1–2; не считать их достаточными. Предыдущие расширенные focused runs, по сообщениям исполнителей, были green, но после двух находок нужны новые RED suites. `git diff --check` exit 0. Повторить ESLint/Prettier/TS после будущей правки; не фиксировать сейчас 100% mutation без свежего Stryker.

#### E. Безопасная последовательность продолжения, без потери WIP

1. По явной команде resume: прочесть корневой и доменные `AGENTS.md`, `quality/quality-contract.json`, этот §0.000, continuation plan и master plan; сверить `git status --short --branch`, `git log origin/egorribun..HEAD`, `git diff --check`, наличие четырёх WIP-файлов и SHA пользовательского аудита. **Не делать `reset --hard`, `checkout --`, broad clean/stage, recursive delete worktrees.** Если diff изменился извне — сначала понять owner.
2. Сверить сохранённый terminal snapshot run 36118352908 (93 success / 24 skipped / 2 failure) с workflow `if:` и DAG для каждого skip; producer/backend и derivative `CI Success` не смешивать. Не судить по устаревшим run в чате. При необходимости скачать immutable logs/artifacts; `gh api .../jobs/108018917327/logs` уже подтвердил точные три падения.
3. Быстрый независимый backend slice: исправить `_delivery_fixture` в тесте (не production guard), добавить regression для истечения/reclaim, прогнать focused + MFA/lease integration, Ruff/mypy по затронутому, затем маленький тестовый commit. Этот slice не должен пересекаться с четырьмя frontend WIP-файлами и может идти параллельно у отдельного агента.
4. Frontend slice D через systematic debugging + RED→GREEN→refactor. Работать с реальным серверным meaning `None`/`[]`, authenticated identity и per-user topic preference. Рецензировать trust boundary, логирование ключей и дедупликацию. Коммитить только после combined focused tests, `npm run typecheck`, lint, formatting, build/SSR по необходимости, Push/browser/E2E, и независимого review. Не stage пользовательский untracked audit.
5. Проверить остальные незакрытые master/continuation/external-audit критерии §6–§13 по актуальным SHA/evidence, а не старым чекбоксам. Особые external-only gates: полноценный Docker Core/full и data-preserving SeaweedFS cutover, exact-six immutable images, SBOM/attestations, локальный kind вместо отсутствующего staging (по согласованному 2026-09-23 scope), TLS/ExternalSecrets/observability/CWV/rollback, cross-browser/mobile, SHA-bound final audit. Deployed-catalog preflight Alembic и WASM Linux toolchain parity остаются обязательными до release.
6. После одновременного закрытия code slices — coherent commits на `egorribun`, precommit/security review, сохранить `.secrets.baseline` если hook его изменил, обычный push, fresh CI на новом **точном source SHA**. Дождаться terminal producer/aggregate mutation 100% и полного quality manifest; не merge/deploy/bypass только потому что большинство jobs green. Отдельно зафиксировать audited source SHA vs audit-only commit SHA.

#### F. Проверенные команды и ссылки для следующего исполнителя

```powershell
git status --short --branch
git log --oneline origin/egorribun..HEAD
git diff --check
Get-FileHash -LiteralPath 'docs/audits/AUDIT_PLATFORM_FULL.md' -Algorithm SHA256
gh pr view 1266 --json state,headRefOid,baseRefName,statusCheckRollup
gh run view 36118352908 --json status,conclusion,headSha,jobs
gh api repos/egorribun/university_ecosystem/actions/jobs/108018917327/logs | Select-String 'FAILED|AttributeError|short test summary' -Context 2,2
uv run pytest -q tests/test_backend_mutation_survivor_contracts.py -k 'delivery_cancellation_requires_an_explicit_single_row_update or delivery_completion_requires_an_explicit_single_row_update or delivery_completion_with_single_rowcount_succeeds' --no-cov
cd frontend
npm run typecheck
npx vitest run src/api/__tests__/notifications.test.ts src/push/__tests__/subscribe.test.ts
```

**Политика доказательств:** указанные выше focused GREEN действуют только для текущего *незакоммиченного* дерева; CI run — только для опубликованного `1488096d0`/его tested merge, S3-тест — только для локального `6b1e2c7`. Нельзя суммировать их в «единый green SHA». Timeouts/skips/incomplete evidence остаются release blockers по `quality/quality-contract.json`, если `if:` guard и неприменимость не доказаны. Все 100% coverage/mutation/security floors остаются без ослабления.

#### G. Проверка самого handoff и пределы достоверности

- При финальной сверке 2026-09-25 13:19 Europe/Moscow повторно прочитаны `git status`/локальный и remote SHA, PR #1266, terminal CI run 36118352908, paused goal, `quality/quality-contract.json`, текущие source/contract-файлы BE-02, Rust Base64, Stryker history и CSpell. Все **девять** локальных Markdown-ссылок этого handoff разрешаются в существующие файлы. Пользовательский аудит сверён по SHA256; нет его staging или изменения.
- Предыдущая проверка markdownlint-cli2 из корня на Windows вывела `Linting: 1 file; 0 issues in 0 files`, а запуск из директории документа с `--config ../../../.markdownlint.json` дал тот же результат. Здесь `0 files` в summary означает число файлов **с ошибками**, а не пропуск: строка `Linting: 1 file` подтверждает фактически обработанный документ. Проверить `git diff --check` снова после последнего редактирования и до commit.
- Это операционный handoff и указатель на полный continuation/master plan, **не независимый построчный аудит всего репозитория**. 93 успешных jobs старого SHA, локальные focused tests и links/lint документа не доказывают финальную матрицу. Unknown остаётся unknown; при возобновлении переснять volatile GitHub/Docker/toolchain state и не выдавать старые секции за текущие.

### 0.00 Дельта 2026-09-25 06:50 Europe/Moscow — активная работа

- Последний опубликованный HEAD ветки `egorribun` на момент этого снимка — `a126eff103d351398ebf68aaff400787c447b7f8`; предыдущий §0.0 с `c5019e3`/`7113f0e` является историческим снимком. PR остаётся [#1266](https://github.com/egorribun/university_ecosystem/pull/1266). [CI run 36086573269](https://github.com/egorribun/university_ecosystem/actions/runs/36086573269) на опубликованном SHA завершился **failure**; свежего прогона с локальными исправлениями ещё нет. Локальный HEAD включает `d46ff8a5a`, `062268049`, `86e8e16ab`, `0cc1d0cd0`, `42aecbd8f`, `09f5e3dc6`, `dae2788fd` поверх опубликованного SHA. Не приписывать им результаты старого CI.
- Восемь producer failures старого прогона (и производный `CI Success`) сведены к причинам: устаревший SeaweedFS cell в CI-каталоге, два несуществующих PWA i18n-ключа, MD028, policy rejection Alembic downgrade, устаревшее ожидание Docker Compose в backend-тесте и WebKit mobile E2E. Все имеют локальные адресные исправления и focused GREEN; WebKit повторён на Chromium и mobile-WebKit с проходом без retry. Schemathesis и backend shard 3 не дали новых failures. Mutation downstream не запускался из-за красных upstream gates: только новый SHA может подтвердить полную 100% матрицу.
- Новая защита Docker cutover зафиксирована в локальных `d46ff8a5a` и `09f5e3dc6`: обычный запуск fail-closed при marker, SeaweedFS container/volume или ошибке инспекции; `-SeaweedFS` записывает игнорируемый marker до первого `up`; повторный guard под атомарным lock закрывает гонку внутри одного checkout. `scripts/dc.ps1` и `scripts/dc.sh` больше не могут запускать старый MinIO после cutover и отказывают в `down -v` с поддерживаемыми alias. Ограничения: прямой Compose вне обёрток и параллельные операции из иных checkout не синхронизируются; runbook требует внешней координации. Предыдущий MinIO-том не удалялся. Перед live cutover нужны копирование/проверка объектов и все условия runbook; **live migration не выполнена**.
- Перед прерванным из-за падения свободной RAM Docker Core build создана внешняя резервная копия текущих `.env*` и старых Docker volumes в `C:/Users/egorribun/Documents/university_ecosystem_backups/2026-09-25-pre-core-a126eff1`. После прерывания тома сохранены, работающих контейнеров нет, хеши `.env*` совпадают с копией. Это не восстанавливает исторические байты до инцидента из §0.0. Не помещать backup или секреты в Git/отчёты.
- Текущий worktree содержит только этот незавершённый handoff и нетронутый пользовательский untracked `docs/audits/AUDIT_PLATFORM_FULL.md`; все перечисленные исправления кода и тестов уже в семи локальных коммитах. Windows frontend build повторно менял два tracked `.wasm` и provenance при неизменных исходниках; три точно известные генерируемые записи сверены и восстановлены из HEAD, `verify-wasm-artifacts.mjs` прошёл. Совмещённый focused набор после последней правки обёрток: 159 passed / 53 POSIX-shell skips на Windows (Linux CI обязан выполнить их); предыдущий Docker/WASM набор — 161 passed / 49 skips до правки `exec` payload. CSpell/quality workflow contracts: 189 passed; CSpell 9.2.2 и 10.2.2: 2 файла, 0 issues. Harness 29/29. Базовый Compose config --quiet и overlay с точным ACK проходят; pre-commit/security hooks прошли на всех новых коммитах. `frontend.Dockerfile` статически выровнен с canonical Rust/wasm-pack/Binaryen producer; `docker buildx build --check` exit 0, однако полный Docker image build и байтовая parity ещё не доказаны. Обнаруженный CSpell zero-file gate заменён двумя постоянно проверяемыми English canaries; это начало, не полный spell-audit документации. Следующий шаг: закоммитить этот handoff, обычный push и fresh SHA-bound CI.

### 0.0 Дельта возобновлённой работы, 2026-09-25 05:25 Europe/Moscow

- Ветка остаётся `egorribun`, PR [#1266](https://github.com/egorribun/university_ecosystem/pull/1266). Последний **опубликованный** SHA — `c5019e33038340d3c52b80e4c7c50d7753289496`; локальный HEAD перед этим обновлением — `7113f0eba7175e0183099e607e218048ec80d54d`, на одиннадцать проверенных маленьких коммитов впереди. Не считать локальный HEAD опубликованным и не приписывать ему результаты старого CI.
- По продуктовым P2/P4/P6/P11 выполнены и локально проверены: contextual Web Push после успешной регистрации на событие с per-user/TTL gating и исправлением `qr_token`; единая центрированная auth-shell без промо/particle/glow (RU/EN, 5 viewport), валидированный redirect после TOTP/email/recovery, связь метки роли с select; виртуализация контактного списка с keyboard/focus; компактный мобильный Navbar без CLS. Визуальный аудит 10/10 Login/Register × 360/390/768/1024/1440 выявил и устранил первоначально невидимый CTA; light/dark CTA проверены.
- BE-02 phase four: Alembic `202609250001` добавляет 11 семантических timestamp defaults и `users.role` только после PostgreSQL catalog preflight, schema-qualified locks и fail-closed проверки. Governed inventory: 94 both / 40 python-only / 0 server-only; оставшиеся 40 — документированные UUIDv7/JSON/secret исключения, а не забытые defaults. Реальный **локальный** PostgreSQL upgrade/downgrade/re-upgrade и 3 integration-теста пройдены; deployed-catalog preflight остаётся release gate. Внешний пользовательский аудит `docs/audits/AUDIT_PLATFORM_FULL.md` не изменён и не staged.
- Для OSS S3 выбран SeaweedFS. Disposable CI fixture и nightly cell больше не используют недоступный Quay MinIO; реальный локальный S3 roundtrip прошёл. `start-docker.ps1 -SeaweedFS` требует точное `S3_CUTOVER_ACK=VERIFIED_S3_CUTOVER`, накладывает cutover overlay последним; обычный запуск пока сохраняет MinIO. Это **не live migration**: старый том `university_ecosystem_minio-data` сохранён, новый SeaweedFS-том не создавался, контейнеры сейчас не запущены. До cutover обязательны backup/restore, copy + object inventory, freeze writers, presigned-URL и authorization checks из runbook.
- Локальные проверки: harness 29/29; **полный frontend Vitest 694 файла / 7744 теста, exit 0 (11m50s)**; fresh production build exit 0; WASM-contract suite 296/296; focused backend 75 passed / 1 intentional opt-in S3 skip (его реальный Docker roundtrip выполнен отдельно); WebKit News desktop/mobile E2E по 1/1; P2 и P11 geometry E2E; quality inventory checker; Ruff, mypy, Compose base/overlay config и pre-commit на одиннадцати коммитах. Дополнительное React `act(...)` warning в SyncStatus воспроизведено и убрано ожиданием IndexedDB: isolated 1/1 и focused 28/28 без warning. Дополнительный тест раннего `handleUnauthorized({ broadcast: false })` убивает найденный мутант за ~40ms (ручной RED с подстановкой `true`: assertion 1/1 упал; GREEN после восстановления оригинала 1/1 и общий auth focused 281/281). После этих двух тестовых правок typecheck/lint exit 0. Полный Vitest был до двух правок; их focused tests прошли, но fresh полный прогон на новом SHA ещё обязателен.
- CI run [36079456610](https://github.com/egorribun/university_ecosystem/actions/runs/36079456610) относится к **старому** `c5019e3` и ещё выполняется. Четыре известных failures: source/test inventory (комментарий к PG-only skip), WebKit desktop/mobile News category scroll (детерминированная активация фильтра), mutmut stats shard 3/8 (новый S3 overlay отсутствовал в isolated `also_copy`). Все четыре имеют локальные RED→GREEN исправления, но результат следующего CI неизвестен. **17** скачанных frontend mutation shard reports: 1172 Killed / 1 Timeout (mutant 123, `useProfileSync.ts:1161`, condition → `true`, hit limit 3702/3700), 0 Survived. Timeout — новый release blocker, не считать успешным: ранний bounded channel test теперь различает мутант до remote-feedback loop, точный Stryker result на новом SHA ещё нужен. Остальные шарды и aggregate не завершились. Не push до сбора полезного mutation evidence, если это не станет явно менее выгодно по времени.
- Fresh Windows `npm run build` изменил только два checked-in `.wasm` и их `WASM_SOURCE_PROVENANCE.json`, несмотря на идентичный `source_tree_sha256`: rust-crypto old/new SHA256 `c7ed6bd9…`/`276f05bd…`, sanitizer `4e20e053…`/`11e9a3ff…`. Build exit 0; три именно этих файла восстановлены из HEAD после фиксации хешей, исходные пользовательские изменения не затронуты. Проверка checked-in WASM/provenance 296/296 прошла. Это **не** доказательство воспроизводимости: локальный Rust/wasm-opt toolchain должен быть сопоставлен с pinned Linux CI producer до закрытия `RUST-P3-03`.
- Локальный safety incident: один ошибочный тестовый вызов launcher с fake Docker **не** стартовал/останавливал контейнеры и не тронул тома, но переписал игнорируемые `.env`, `.env.docker`, `.env.docker.workers` в 2026-09-25 01:43:45 UTC. Все три существовали ранее; backups в workspace нет, прежние байты недоступны. Код сохраняет валидные секреты канонического `.env.docker`, но побайтовую идентичность утверждать нельзя. После инцидента их mtime не менялся; новые launcher tests сверяют SHA256 всех трёх файлов до/после каждого read-only `-Logs` вызова. Секреты не выводились в чат или логи.
- Следующий порядок: собрать ещё доступный inventory old-run mutation shards, не затягивая новый SHA-bound CI; коммит этого handoff и push `origin egorribun`; получить fresh полный green CI на нём, включая 100% viable Stryker/mutmut; затем controlled Docker Core/full, immutable image + local kind/TLS/observability/rollback acceptance и SHA-bound audit. Если очередной CI откроет новые defect/survivor, воспроизвести RED и исправить без ослабления gates. `RUST-P3-03` внешнего аудита остаётся отдельно обусловлен воспроизводимым CI WASM build, не объявлять закрытым по локальному снимку.

### 0.1 Идентичность, сохранность и что НЕ трогать

| Поле | Состояние на паузе |
| --- | --- |
| Repository / ветка | `C:/Users/egorribun/Documents/university_ecosystem`, `egorribun` (PR [#1266](https://github.com/egorribun/university_ecosystem/pull/1266) → `main`, OPEN) |
| HEAD | коммит этого handoff поверх `3031cd5fa`; все изменения закоммичены и запушены в `origin/egorribun` (проверять `git status` / `git log origin/egorribun..HEAD` — должно быть пусто) |
| Рабочее дерево | чистое, кроме пользовательского untracked `docs/audits/AUDIT_PLATFORM_FULL.md` (SHA256 `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b`, не изменять и не стейджить) |
| Коммитов с 0ec4fed3a | 46 (полный список: `git log --oneline 0ec4fed3a..HEAD`) |
| Stash | не использовался |
| Контейнеры | `codex-wasm-base64-0ec4fed3a` удалён с разрешения пользователя; собственный `claude-wasm-base64-0ec4fed3a` удалён ранее; других контейнеров этой работы нет |
| Агенты | все три фоновых агента (группы A, B, C) остановлены; их работа собрана и закоммичена; фоновых процессов/мониторов нет |
| Скрытые мутации | проверено: ни в основном дереве, ни в worktree нет файлов, оставленных мутантом; `artifacts/quality/mutation-tools/…/mutant-backups` пуст |

**Дополнительные git worktree (оставлены намеренно, пустые по содержанию):** `../ue-mut-A`, `../ue-mut-B`, `../ue-mut-C` (агентские, detached на `2dc1c40e3`, их тестовые правки уже перенесены в основное дерево), `../ue-e2e` (чистый HEAD для локального E2E), `../ue-mm` (для backend-мутаций, содержит копии уже закоммиченных файлов). **Опасность:** в каждом `frontend/node_modules` и корневой `node_modules` — это NTFS-junction на `university_ecosystem/…/node_modules`. **Никогда не делать `rm -rf`/`git worktree remove --force` по такому дереву** — рекурсивное удаление через junction снесёт node_modules основного репозитория. Безопасная очистка: сначала `cmd /c rmdir <path>\frontend\node_modules` и `cmd /c rmdir <path>\node_modules` (удаляет только ссылку), затем `git worktree remove <path>`. Если worktree больше не нужны — так их и убрать; содержимого, которого нет в `egorribun`, в них нет (проверка: `git -C ../ue-mut-X status --short` показывает только тесты, совпадающие с основным деревом; `ue-mm` — только копии закоммиченных файлов).

### 0.2 Решения и постоянные полномочия пользователя (действуют дальше)

Зафиксированы в памяти проекта (`~/.claude/projects/…/memory/`):

1. **Scope (2026-09-23):** CDC (BE-08) вне MVP, DEFERRED (ADR-037 §scope); spelling — сначала авторские docs, потом код; реального staging нет → Stage 10 на Docker Core/full + локальный kind; доставка email/push — только локальные sink'и (Mailpit, локальный VAPID).
2. **Frontend Stryker (2026-09-24):** гибрид. Поведенческие survivors убивать тестами; косметические литералы className/style — единственный governed ignorer ADR-040 (`presentation-class-names`). Расширять ignorer — только новым ADR. До 3 параллельных агентов на непересекающихся файлах с ревью ведущего перед коммитом.
3. **Постоянные разрешения (2026-09-24):** скачивать пинованный инструментарий из официальных источников (Playwright-браузеры из lock-версий, Docker-образы из compose/Helm по digest, kind/helm/kubectl/mkcert с checksum); скачивать CI-артефакты своего репо (`gh run download`) в ignored `artifacts/`/scratchpad; обычный `git push origin egorribun` без вопросов. **Всегда спрашивать:** merge в `main`, force-push, закрытие/merge Dependabot PR, branch protection, любые внешние/публичные действия, загрузки вне перечисленного.
4. Коммиты без `Co-Authored-By`; scope non-wave (`fix(frontend)`, `test(quality)`, `test(security)`, `refactor(frontend)`, `docs(quality)`…); `feat(waveXX)` — только новая бизнес-функциональность (последняя — wave212).
5. Лимит сессии аккаунта пользователя может оборвать работу (так остановился агент C 2026-09-24, сброс 23:10 MSK). Перед долгой работой помнить: при обрыве запустить восстановление из §0.7.

### 0.3 Главная находка этой сессии: реальный масштаб mutation-долга

- Frontend aggregate `validate-stryker-inventory` — **fail-fast**: он всегда останавливался на первом плохом мутанте (`shard-001:2 Timeout`), а producer-шарды идут с `break: null` и «зелёные» даже с survivors. Поэтому «100% frontend Stryker» ни разу не был достигнут. По 41 скачанному шарду run 35954304649: **968 поведенческих survivors в 118 файлах** после ADR-040 (145 были косметикой), всего по вселенной ожидалось ~1500 до работы.
- Backend incremental mutmut (run 35976627864): **203 survivors** в коде ветки (schedule_changes 80, logging 49, schedule_service 22, system_release 16, auth_service 11, revocation 7, мелочи 18). **Все 203 закрыты** (см. §0.4).
- Источник поштучных данных: CI-артефакты `frontend-mutation-shard-<run>-*` (mutation.json) и clear-text таблицы в логах jobs «Frontend mutation shard N/64»; backend — строки `🙁 <module>.<mutant>` в логах «Incremental Mutation Tests (mutmut) / execution group N».

### 0.4 Что сделано в этой сессии (коммиты `ad4d2d23f` … HEAD, по темам)

**Продукт (все с RED→GREEN):**
- `ad4d2d23f` P8: sticky-бары категорий News/Events вынесены из короткого `<header>` (sticky не мог выйти из containing block и уезжал), `z-sticky` поверх бейджей карточек, матовая подложка stuck-бара Events; хук `useStableListHeight` держит высоту списка в фазе render (не layout effect), E2E `tests/e2e/category-scroll-stability.spec.ts`.
- `92e37b007` `shouldReload: false` на роутах `/news` и `/events` (loader-префетч не перезапускается на смену search; pending UI роутера перемонтировал страницу) + ETag E2E ищет ссылку карточки, а не текст (quick view дублирует заголовок).
- `1568c7dd2` **баг rate-limit очереди:** после grant, заполнившего rolling-window, никто не ставил таймер — оставшиеся ожидающие висели до чужого release. Теперь acquire при непустой очереди армирует таймер; тест `rateLimit.window.test.ts`.
- `235a8d8de` **баг чётности недели:** `nowParity` считал недели от 1 января с субботы, backend — ISO (`isocalendar()`); dashboard показывал/фильтровал не ту неделю на стыках лет и выходных. Новый `isoWeekNumber`, тесты на 53-недельный год.
- `764c5c649` **баг roomStatus:** занятие 08:00–08:00 делало аудиторию занятой весь день (`end <= start` трактовалось как переход через полночь).
- `9451e88c3` Levenshtein без мутируемых счётчиков циклов (мутант `j++→j--` давал бесконечный цикл = Timeout).

**Mutation/quality infrastructure:**
- `2dc1c40e3` ADR-040 + `frontend/scripts/stryker-presentation-ignorer.mjs`: игнор только строковых листьев в `className`/`*ClassName`, аргументах `cn/clsx/cva/twMerge/twJoin`, биндингах `*Classes/*ClassName`, литеральных значениях `style={{…}}`. Все стадии evidence (`run-stryker.mjs`, `validate-stryker-inventory.mjs`, `verify-stryker-evidence.mjs`, `stryker.config.mjs`) используют `canonicalInstrumenterConfig`; Ignored допускается только с reason ADR-040 и только если совпадает с регенерированным preflight; `ignoredMutants` в summary и вне знаменателя. 152 node-теста скриптов зелёные; проверено на реальном `mutation.json`.

**Frontend survivors (тесты + эквивалентные упрощения без смены поведения):**
- `411d1ee58` sanitizers/redirect/Trusted Types — 100% (security-review: 0 находок): `sanitizeArticleHtml`, `sanitize.ts` (`parseHttpUrl`), `SafeHtml` (тесты теперь проходят WASM-ветку), `trustedTypes`, `redirect` (+SSR-тест).
- `afc38343d` группа A (агент): 198/284. `1476ea7d8` группа B (агент): 157/206. `d96d6e462` + `3031cd5fa` группа C (агент): 49+3 тестовых файла, ~46 из 72 файлов проверены до остановки.
- `2cd4e1c20` эквивалентные guard'ы удалены в weatherIcons, buildingHours, avatar, readingTime, scheduleConflicts (NaN вместо null; `Math.max(null,…)` считал null нулём), passwordStrength, authUtils (`=== -1`), highlight (`replaceAll`), htmlText, loaderLang. Весь unit-набор (5842) зелёный. **Мутационно проверены:** weatherIcons 97/97, avatar 43/43, readingTime 14/14, scheduleUtils 33/33, roomStatus 45/45, levenshtein 18/18. **Не проверены мутационно после упрощения:** buildingHours, scheduleConflicts, passwordStrength, authUtils, highlight, htmlText, loaderLang — сделать первым делом (§0.8 шаг 3).

**Backend survivors — все 203 закрыты, каждый модуль проверен полным набором текущих мутантов:**
- `abfeb7779` schedule_changes 208/208 + новый `render_registered_notification_template` 9/9 (мёртвые fallback'и убраны, точный вызов доставки и fingerprint в тестах).
- `7660b3ad6` PII-редакция логов 107/107 (+ убран эквивалентный 5-символьный shortcut).
- `e4abf5020` `schedule_state`/`delete_schedule` 57/57, `announce_release` 99/99.
- `3555735ed` `_token_hmac_secret` 24/24, `get_revocation_redis_client` 26/26 (поля Settings читаются напрямую).
- `0fd22d2fb` images 33/33 (float-граница бюджета пикселей), HMAC-strength 23/23, event handler 17/17, lifespan shutdown 33/33, DI-композиция 31/31, `get_current_user` 8/8.

### 0.5 CI: текущее состояние

- Последний запушенный до этого handoff SHA `5616cf778` → run [36058587950](https://github.com/egorribun/university_ecosystem/actions/runs/36058587950) был `queued/in_progress` (119 success, 5 failure, 160 queued на момент паузы). Коммиты `235a8d8de…` и этот handoff запушены после — новый run запустится на HEAD; проверять `gh run list --workflow ci.yml --branch egorribun --limit 3`.
- **Падения run 36058587950, классификация:**
  - `Go Integration Tests (file-processor)`: `TestIntegration_MinIOResizeImageHappyPath` — pull `quay.io/minio/minio@sha256:14cea…` вернул `unauthorized` (внешний registry). Не код; rerun при восстановлении registry, при повторе — рассмотреть mirror/кэш образа.
  - `Chaos Engineering (ToxiProxy)`: `Docker pull failed with exit code 1` — та же внешняя причина (проверить, какой образ).
  - `DB Migration Rollback Integrity`: `TOML parse error at line 459, column 17 … failed to parse year in date "7 days"` — **конфигурационный дефект**: `pyproject.toml [tool.uv] exclude-newer = "7 days"` читает старый uv/парсер в этом job. Выяснить, какой бинарь (не `setup-uv` с `required-version ==0.11.28`?), и привести job к канонической установке uv. Код миграций не причём.
  - `E2E webkit` и `E2E mobile-webkit`: `/news` `category-scroll-stability` — `before=522 after=0 max=522` **даже с `shouldReload:false`**. Первопричина НЕ найдена (floor высоты держится, значит это явный scroll-to-top, а не clamp). Chromium зелёный; локальный Windows-WebKit ненадёжен (module-script preload errors → boot loader) — воспроизводить только на Linux WebKit (CI или Docker `mcr.microsoft.com/playwright`). Гипотезы для проверки: focus/scrollIntoView кнопки внутри sticky в WebKit, `useURLState` navigate с `viewTransition`/hash, перемонтирование `NewsList` (другой ключ), `PageTransition`. Скачать trace: `gh run download <run> -n playwright-traces-mobile-webkit-shard-1-of-1`.
- Frontend Stryker на новом SHA даст первый полный инвентарь **после ADR-040**; только по нему судить об остатке. Aggregate по-прежнему fail-fast — полный список брать из шардов (§0.3).

### 0.6 Инструменты мутационной проверки (долговечные копии)

Лежат в ignored `artifacts/quality/mutation-tools/` (оригиналы были во временном scratchpad сессии). Инвентари — в `inventories/` (всегда передавать `--inventory <файл>`, дефолтный путь скриптов указывает на соседний `behavioural-survivors.json`).

- `fresh_mutants.mjs` — генерирует все НЕигнорируемые мутанты текущих исходников тем же Instrumenter + ADR-040: `cd frontend && node ../artifacts/quality/mutation-tools/fresh_mutants.mjs --out /tmp/x.json src/utils/a.ts`.
- `mutant_check_fast.mjs` — один in-process Vitest на все мутанты (~2–7 с/мутант), crash-backup + авто-восстановление: `node …/mutant_check_fast.mjs --inventory /tmp/x.json --file src/utils/a.ts --tests "src/utils/__tests__/a.test.ts"`. Печатает KILLED/SURVIVED/TIMEOUT. `mutant_check.mjs` — медленный эталон (npx на мутант) для перепроверки спорных.
- Backend: `mm_check.py diff <file> <mutant…>` (дифф мутанта через ast), `mm_loop.py --file app/x.py --tests "tests/…" [--all | mutant…]` — один pytest-процесс, переключение `MUTANT_UNDER_TEST` (трамплин mutmut читает его на каждом вызове), watchdog Timeout, shim для `mutmut.__main__` (на Windows не импортируется). Запускать **в отдельном worktree** (`../ue-mm`) основным `.venv/Scripts/python.exe` и `PYTHONIOENCODING=utf-8` (имена методов содержат `ǁ`).
- `narrow_fresh.py` — оставляет из свежих мутантов только те, у которых нет убитого близнеца в CI-отчёте (после рефакторинга позиции сдвигаются).
- **Правила, выученные на ошибках этой сессии:**
  1. Никогда не запускать две мутационные проверки над связанными файлами одновременно в одном дереве.
  2. Во время мутационной проверки в основном дереве **не коммитить**: pre-commit stash и проверка «files were modified by this hook» ломаются, а результаты искажаются.
  3. После любого прерванного прогона проверить `mutant-backups/` и `git status` на неожиданные продуктовые изменения; восстанавливать из бэкапа или `git checkout`.
  4. При восстановлении бэкапов трогать только свои файлы (один раз ошибочно были восстановлены файлы агентов посреди их прогона).
  5. detect-secrets реагирует на тестовые пароли/токены — выносить в константу с `# pragma: allowlist secret` / `// pragma: allowlist secret` на той же строке (ruff/prettier переносят хвостовые комментарии).

### 0.7 Восстановление после обрыва сессии/лимита

1. `git status --short` (ожидается только AUDIT), `git log origin/egorribun..HEAD` (пусто или локальные коммиты — тогда push после preflight).
2. `ls artifacts/quality/mutation-tools/mutant-backups/` (и старый `C:/Temp/claude/…/scratchpad/mutant-backups/`, если существует): каждый файл — URL-кодированный абсолютный путь; сравнить с целевым файлом, восстановить или удалить.
3. Для каждого `../ue-*` worktree: `git -C ../ue-X status --short` — продуктовые (не test) изменения там = оставленный мутант → `git -C ../ue-X checkout -- <file>`.
4. `docker ps -a` — контейнеров этой работы быть не должно.

### 0.8 Что делать дальше — по порядку

1. **CI на HEAD:** дождаться run; классифицировать каждое падение (root/infra/transient). Rerun только доказанно-транзиентных (registry pull) на неизменном SHA.
2. **DB Migration Rollback:** починить установку uv в этом job (TOML `exclude-newer = "7 days"`), контракт-тест на workflow, если есть аналог.
3. **Мутационная проверка 7 упрощённых утилит** (§0.4): `fresh_mutants` + `mutant_check_fast` по каждому с его тестами; добить survivors.
4. **Остаток группы A** (из отчёта агента, всё с предложенными product-диффами): `media.ts` 26 эквивалентов (избыточные early-return/guard'ы — решить удалением, это не security-граница, но аккуратно), `performance.ts` 4, `cryptoWorker.ts` 5 (только утечки map — возможно экспорт размера только для тестов или рефакторинг pending-map), `browser.ts` 4, `spotify.ts` 3, `cache.ts` @6, `api/hooks/news.ts` @66, `slugify.ts` @14, `a11y.ts` @107 ×2, `animations.ts` @48 (убрать лишний `type:"spring"`), `rateLimit.ts` @199 (удалить строку), @40, **@148 Timeout** (пустое тело `waitForClientQueueWaiter` → бесконечная асинхронная рекурсия; лучший путь — direct-handoff слота вместо повторного acquire, с тестами на abort-после-grant), `bootstrapFallback.ts` 34 инлайн-стиля (решение ведущего: НЕ расширять ADR-040, а один тест на полный `style.cssText` элементов fallback — без stylesheet это поведение).
5. **Остаток группы C:** агент проверил ~46 из 72 файлов (`inventories/work-C.json`); остальные — начиная с `MobileBottomNav`, `MapSidebar`, `ContactList`; брать актуальный список из нового CI-инвентаря.
6. **P8 WebKit** (§0.5) — довести до зелёного на Linux WebKit.
7. **P8-файлы после ADR-040:** EventsFeature/NewsFeature/EventsHeader/NewsHeader имели 226 survivors по локальному focused-прогону ДО ignorer — перепроверить по новому CI-инвентарю.
8. Затем план `C:\Users\egorribun\.claude\plans\cryptic-singing-catmull.md`: оставшиеся продуктовые P2 (push-prompt), P4 (auth shell), P6 (виртуализация ContactList), P11 (compact navbar), C0 live-E2E лейн, фаза B (BE-02 phase-four миграция, Mailpit), фаза D (spelling docs→код, zero-warning build, O-задачи), фаза E (Docker Core/full, kind, финальный аудит). Dependabot #1289–#1292 — только с разрешения. Merge в `main` — только с разрешения.

### 0.9 Уточнения к Definition of Done (§13)

- «100% viable» frontend = каждый мутант, кроме ADR-040-ignored и объяснённых CompileError, Killed; Timeout/RuntimeError/NoCoverage недопустимы — лечатся устранением причины (как Levenshtein, rateLimit), а не ослаблением гейта.
- Эквивалентный мутант = сигнал на упрощение кода без смены поведения (с тестом, что поведение сохранено), а не на `// Stryker disable` (запрещено валидатором).
- Ни один из пунктов §0.8 не считать выполненным по старым отчётам; подтверждение — свежий CI на точном SHA.

**Goal:** закрыть весь действующий continuation/master scope на текущем уровне функциональности: воспроизводимый безопасный MVP, все применимые quality metrics 100%, полная продуктовая приёмка и SHA-bound Docker/staging/release evidence. Этот handoff не уменьшает scope и не заменяет критерии готовности удобным подмножеством.

**Архитектура продолжения:** сохранить реализованные функции; сначала закончить незакоммиченный пакет, затем устранить свежие подтверждённые дефекты, собрать полную приёмочную матрицу и продвигать один immutable build. Исправлять product code по воспроизведённому RED, а недостаток доказательств не называть автоматически дефектом продукта.

**Стек:** Python 3.14/FastAPI/SQLAlchemy async/Dishka; React 19/TypeScript/Vite/Vitest/Stryker/Playwright; Go services; четыре Rust-компонента; PostgreSQL/Redis/NATS; Compose/Helm/GitHub Actions.

## 1. Быстрое восстановление контекста

### 1.1 Что читать и в каком порядке

1. Сначала §0.000 этого handoff — операционная точка последней остановки. Остальные §1–§5 содержат историческую WASM/MFA/Semgrep работу и полезную причинную историю, но не актуальный WIP inventory.
2. Корневой [AGENTS.md](../../../AGENTS.md), доменные AGENTS затрагиваемых областей и [quality contract](../../../quality/quality-contract.json).
3. [Continuation plan](2026-08-31-mvp-quality-closure-continuation.md), **§148**, затем относящиеся к текущей задаче acceptance-разделы. Старые operational snapshots не являются текущим статусом.
4. [Исходное MVP ТЗ](University_Ecosystem_MVP.md): требования сохраняются, но предложения «переписать профиль с нуля» заменены утверждённым gap-аудитом существующего продукта.
5. [Foundation plan](2026-08-25-quality-closure-foundation.md) и [старый prompt](prompt.md) — явно HISTORICAL/SUPERSEDED. Старые TypeScript blocker, PR #1257, shard counts и SHA не переносить в новый статус.
6. Внешний аудит `docs/audits/AUDIT_PLATFORM_FULL.md` (пользовательский, не отслеживается в Git), [индекс аудитов](../../audits/INDEX.md), [ADR-037](../../adr/ADR-037-cdc-outbox-transport-ownership.md), [ADR-039](../../adr/ADR-039-frontend-mutation-shard-cost-model.md).

Это дополнительный handoff к одному активному roadmap, не второй конкурирующий master plan. При расхождении статусов использовать свежий код/логи/артефакты; при расхождении требований — утверждённый goal, AGENTS и текущий quality contract, а не старые baseline-таблицы.

### 1.2 Идентичность и сохранность

| Поле | Состояние при остановке |
| --- | --- |
| Repository | `C:/Users/egorribun/Documents/university_ecosystem` |
| Ветка | `egorribun` |
| HEAD и опубликованный PR head | `0ec4fed3a61826561cbbcaf3c7e1b665ac579706` |
| PR | [#1266, OPEN, egorribun → main](https://github.com/egorribun/university_ecosystem/pull/1266) |
| Текущий Matrix run | [35730420629](https://github.com/egorribun/university_ecosystem/actions/runs/35730420629), attempt 1, `in_progress` при последней проверке |
| Worktree | Только основной зарегистрированный worktree |
| Stash | `git stash list` пуст при остановке; ничего из stash не удалялось |
| Index | Текущий пакет не staged; новый handoff также первоначально untracked |
| Worktree cleanliness | **Не чистый по Git:** есть намеренные незакоммиченные изменения ниже |
| User audit | Untracked `docs/audits/AUDIT_PLATFORM_FULL.md`, пользовательский, не изменять/не добавлять автоматически |
| User audit SHA256 | `902f81d4b3a904d074ed32e3e7c3a9157f92e1e45e3dc7fca646f05e8ed2887b` |
| Goal | Active, не complete и не blocked; пауза не означает блокер |

Коммита/пуша при этой безопасной паузе не делается: пользователь запросил остановку и handoff, а текущий WASM-пакет ещё не завершён. Все изменения сохранены на диске. Не заявлять, что они уже находятся на GitHub.

### 1.3 Фактически остановленные процессы

- Локальные E2E preview и PostgreSQL acceptance завершены; тестовые PostgreSQL-контейнеры удалены только после результатов/проверки очистки.
- Субагенты завершены либо interrupted. Новые задачи не запускать во время паузы.
- Единственный работавший сборочный контейнер остановлен, **не удалён**:
  - name: `codex-wasm-base64-0ec4fed3a`;
  - ID: `c745a06530774790c4189eb4bfa9ccc1bcbaa08baf2f1d34db6481f4f467c121`;
  - image: `ubuntu:24.04`, Linux amd64;
  - 2 CPU, 3 GiB, pids limit 256;
  - status: `exited`, exit 143 после намеренной остановки, **не build failure verdict**;
  - исходный процесс имел `timeout 1500`, readonly mount собственных `artifacts/wasm-linux-baseline-0ec4fed3a` в `/input`;
  - `/work`, toolchain и промежуточные результаты остались внутри контейнера.
- После остановки `docker ps` пуст; targeted process scan не нашёл node/python/cargo/docker/wasm процессов с путём проекта или именем этой сборки. Это не утверждение, что на машине нет посторонних процессов.
- Облачный CI **не отменён**. Локальный мониторинг прекращён. Автоматическое возобновление не создавалось; стандартный каталог `C:/Users/egorribun/.codex/automations` отсутствует при проверке.

Не делать `docker start` вслепую: entrypoint повторно выполняет bootstrap с `mkdir` и загрузками и не является идемпотентным resume. Не удалять контейнер до извлечения нужных результатов или доказанной ненужности.

## 2. Что уже закончено и опубликовано

Предыдущая повторная оценка охватила 19 пользовательских коммитов от `d4d3021b912cb59ed6e8bb132c7eec6faed8b2cb` до `2fdb2e2f45618f4c5a836203f379bec36f76313d`, 159 изменённых файлов. Не возвращаться к состоянию до самостоятельной работы пользователя.

| Commit | Изменение | Доказательство / граница |
| --- | --- | --- |
| `0606860c6` | DI route inventory ownership, canonical `Path` import | RED пустых references; 114 focused tests, полный inventory checker |
| `c91f7d0bb` | Scoped provider-utils 4.0.33 override для msw-auto-mock; удалены 8 устаревших undici allowances | npm full/lock audit 0, 4 реальных normalized generated mocks byte-identical |
| `e88009d6f` | Literal-safe default preflight миграции | 42 offline + 6 real PostgreSQL tests; строки не нормализуются с потерей payload |
| `200a48f01` | Fail-closed CDC startup и безопасный WAL acknowledgment | 101 focused tests; touched lifespan/CDC line+branch 100%; реальный transport всё ещё deferred |
| `325418de3` | Auth unavailable/forbidden/success, malformed schedule cache; удалены 5 невозможных Request=None ветвей | 88 auth/schedule + 69 content tests, touched scopes line+branch 100% |
| `c082176f7` | §148 и ADR-039: честный статус после reassessment | Не объявляет продукт и release завершёнными |
| `0ec4fed3a` | Preflight evidence и dormant spelling finding | Текущий опубликованный head |

Предыдущие локальные проверки опубликованного пакета: harness 29/29; frontend typecheck/lint/build exit 0; strict mypy 361 app files; Ruff/AST/Bandit; scoped pre-commit; combined migration/CDC 143 tests; independent PostgreSQL 6 cases; frontend quality/MSW 13 tests. Это scoped evidence, не доказательство полного текущего mutation universe.

Fast-preflight **на `c082176f7`**, не на последующем docs SHA: 6/6, typecheck 8.049 s, lint 98.870 s, backend type 5.851 s, backend lint 0.178 s, harness 34.319 s, contracts 70.833 s. JSON: `artifacts/fast-preflight/fast-preflight.json`. Build имел Rolldown/Node localStorage warnings, поэтому zero-warning release не подтверждён.

## 3. Незакоммиченный пакет: полный ownership inventory

### 3.1 Rust HMAC Base64 — implementation есть, генерация НЕ завершена

Изменены:

- `frontend/rust-crypto/Cargo.toml`, `Cargo.lock`;
- `frontend/rust-crypto/src/lib.rs`, `src/tests.rs`;
- `frontend/rust-crypto/tests/native.rs`, `tests/wasm.rs`;
- `frontend/src/workers/crypto.worker.ts`;
- `frontend/src/workers/__tests__/crypto.worker.closure.test.ts`, `crypto.worker.parity.test.ts`;
- `frontend/scripts/verify-wasm-artifacts.mjs`, `verify-wasm-artifacts.test.mjs`;
- `frontend/scripts/wasm-runtime-smoke.test.mjs`, `challenger-adversarial.test.mjs`.

Изменение: additive export `hmac_sha256_sign_base64(key, message)` возвращает RFC 4648 padded Base64; старый hex export сохранён. Общий private digest сохраняет существующие Zeroizing-буферы и обнуление промежуточного digest; PBKDF2/scrypt не изменены. Worker вызывает новый export вместо regex/parseInt/Uint8Array/btoa. `base64ct = 1.8.3` уже был transitive locked dependency; добавлена одна прямая связь.

Проверено:

- RED: в существующем WASM отсутствует новый export; проверка worker запрещает JS btoa round trip; validator отвергает отсутствие export.
- Worker 11/11; validator 8/8; adversarial validator cases 6/6; provenance unit 5/5.
- Native Rust 27/27 на Windows и Linux; Linux `cargo clippy --all-targets --locked -- -D warnings` exit 0.
- Scoped ESLint/Prettier/Rustfmt/diff checks проходят.
- Независимое source/security review: PASS; не является доказательством полной memory zeroization в оптимизированном бинарнике.

**Важно:** generated `rust-crypto/pkg` и `frontend/WASM_SOURCE_PROVENANCE.json` ещё НЕ обновлены в worktree. Full TypeScript сейчас ожидаемо сообщает TS2724: новый export отсутствует в generated declarations. Не скрывать эту ошибку, не возвращать worker к старому API ради зелёного typecheck, не коммитить половину изменения.

Исходные committed пакеты успешно воспроизведены в Linux **до изменений**, тем самым устранена гипотеза «на этой машине невозможно»:

- Rust 1.97.1; wasm-pack 0.13.1; Binaryen 117; Node 24.21.0.
- Remaps: `/root/.cargo` → `/usr/local/cargo`, root `/work`.
- crypto WASM SHA256: `98e6d43877ef0ac02b4f80859e097d1a24836311a749d75968ac63fa213a59ab`.
- sanitizer WASM SHA256: `4e20e0537cdf3b1f3c78ad2685cd6a31a112b872a6796cc1178d89efc1dd6396`.
- provenance SHA256: `3775d67edf2147e7aedd95424baa36950e07393b5257eacc833fb3a4811be9b5`.
- Strict artifact validator и 2/2 прежних runtime smoke пройдены на baseline. Это не новые Base64 artifacts.

Resume inputs сохранены в ignored `artifacts/wasm-linux-baseline-0ec4fed3a/`: `baseline.sh`, `implementation.sh`, `source.tar`, `changed.tar`. Последний Linux log был компиляцией sanitizer/ammonia; marker `CANONICAL_SECOND_CLEAN_BUILD_VERIFIED` не получен. Не принимать частичные файлы контейнера за готовые.

После команды продолжить:

- [ ] Сверить current source с `changed.tar`, чтобы не собирать устаревшую snapshot.
- [ ] Изучить оба shell helper целиком. Перенести bootstrap в воспроизводимый bounded runner либо безопасно использовать сохранённый toolchain после копирования нужных файлов из stopped container; не исполнять entrypoint повторно без проверки.
- [ ] Сохранить exact versions, checksum verification скачанного инструментария, remaps и lockfiles. Не объединять разные wasm-bindgen lock versions двух crates насильно.
- [ ] Выполнить первую canonical regeneration, runtime smoke, source/provenance validation.
- [ ] Выполнить вторую действительно clean сборку обоих WASM crates, сравнить bytes и strict validator. Удаления разрешены только для проверенных точных owned target/pkg каталогов внутри disposable builder.
- [ ] Только после PASS перенести необходимые generated crypto JS/WASM/declarations и provenance в worktree; sanitizer при отсутствии source changes должен остаться byte-identical.
- [ ] Проверить diff generated export, source hashes, package hashes; независимое review; full typecheck, runtime smoke, worker tests, build.
- [ ] После сохранения доказательств удалить только собственный stopped build container, если он больше не нужен. Не выполнять global prune.

Отдельный незакрытый drift: `frontend.Dockerfile` использует Rust 1.94.1 и непинованный `cargo install wasm-pack`; это не canonical producer. Нужны RED Docker/provenance contracts и выравнивание воспроизводимости либо безопасное потребление проверенных canonical artifacts, а не произвольная смена образа.

### 3.2 PostgreSQL MFA acceptance — локально завершено, не committed

Файлы: modified `tests/integration/test_mfa_email_otp_postgres.py`; new `tests/test_mfa_postgres_acceptance_contract.py`.

Корень gap: test требовал только `MFA_TEST_POSTGRES_DSN`; обычный integration workflow задаёт `RUN_INTEGRATION_TESTS=1` и `DATABASE_URL`, поэтому реальная MFA acceptance тихо пропускалась.

Новая fixture использует существующий integration lane без нового workflow: требует testing/reset opt-in и PostgreSQL test authority; создаёт уникальную `test_mfa_<uuid>` базу через `psycopg.sql.Identifier`; не меняет source DSN; удаляет только успешно созданную owned базу в finally. Failed CREATE/collision не разрешает DROP. Явный manual DSN остаётся caller-owned, автоматически не удаляется. Sync/async engines dispose в finally.

Review выявило и исправило P2: `connect_timeout=10` не ограничивает DDL. Теперь connect options задаёт `lock_timeout=10000`, `statement_timeout=30000`; assertions и timeout propagation покрыты. RED без options подтверждён.

Доказательства:

- 31 lifecycle contract + 36 Semgrep contracts: **67 passed in 34.11 s**, exit 0, с отдельным writable pytest cache.
- Независимый root real-CI-path run без manual MFA DSN: **1 passed in 18.52 s**, exit 0; sentinel value 42 сохранился, запрос `test_mfa_%` вернул 0 строк; собственный контейнер удалён в finally.
- JUnit: `artifacts/quality/mfa-postgres-root-review.xml`.
- Более ранние real PG runs: 1 passed 33.42 s и 35.48 s; agent JUnit в `C:/Temp/mfa-pg-audit-46512ec3ab764826822be98f478a4b9a/`.
- Независимое review после SQL timeout fix: PASS.

Граница: existing autouse `prepare_database` создаёт metadata/RLS в shared suite DB. Новая fixture не мигрирует/не удаляет shared DB, но **весь pytest harness не является read-only** относительно неё. Любые запускаемые DATABASE_URL должны указывать только на явно выделенную disposable test БД.

### 3.3 Email MFA browser contracts — локально завершено, новый файл

Файл: `frontend/tests/e2e/email-mfa.spec.ts`.

Шесть RU/EN случаев: masked hint и email-only login; resend cooldown/rotation/wrong-code/retry; recovery entry → возврат к email challenge. Stateful route doubles фиксируют payload и порядок. Это **mocked browser contract**, не real SMTP/outbox verification.

Независимое review поймало fixed-Date/live-timers race. Контролируемый RED воспроизведён без wall-clock sleep. Исправление: Clock install до navigation, pause после hydration, синхронное продвижение Date/timers и ожидание React labels. Сохранены точные assertions disabled на 59.999 s / enabled на 60 s.

- Repeat-each 5, workers 2: **30/30**, 2.1 min.
- Existing TOTP `mfa.spec.ts`: **4/4**.
- Scoped ESLint/Prettier/diff PASS; независимое review PASS.
- Preview остановлен; traces в `frontend/test-results` (ignored).
- Использовался установленный Chromium 1234 вместо отсутствовавшего ожидаемого 1243; pinned CI browser повторить перед full certification. Prod dist был существующий, так как product login code не менялся; не переносить это evidence на будущий новый build.

### 3.4 Semgrep ledger — исправлен новый CI failure

Файлы: `security/semgrep-suppression-policy.json`, `tests/test_semgrep_sarif_validator.py`.

После добавления CDC startup guard неизменный reviewed SQL сдвинулся с 519–521 на 528–530. Обновлены **только две точные line ranges**, без расширения правил, rationale, owner или expiry. Новая AST-based regression определяет текущую CREATE PUBLICATION call и отвергает shifted/unsuppressed report.

RED совпадает с CI error; 36 tests PASS; independent review PASS. Полный свежий Semgrep hosted job на новом SHA ещё обязателен. Это поддержание существующего доказанного false-positive ledger, не новая blanket suppression.

### 3.5 Documentation — изменён continuation, плюс этот новый handoff

Modified `docs/superpowers/plans/2026-08-31-mvp-quality-closure-continuation.md`:

- уточнён BE-02 status;
- command block переведён в indented syntax для MD046;
- добавлены Dependabot/spelling/WASM/CI diagnostics и границы доказательств.

Pinned Markdownlint CLI2 0.23.2: focused и 199 tracked Markdown files PASS. Local-link checker: 892 files PASS; не проверяет wording/remote URLs/anchors. После handoff и его backlink повторить проверку документов.

## 4. CI: что смотреть первым после паузы

### 4.1 Current run, не исторические списки пользователя

Run `35730420629` выполняется на **опубликованном** `0ec4fed3a`, без незакоммиченных изменений раздела 3. При остановке известны два failure:

| Job | ID | Причина | Исправление |
| --- | --- | --- | --- |
| Security Audit / Semgrep SAST | `106754858489` | ledger не покрывает shifted CDC SQL line 528 | Local fix §3.4, ещё не push |
| Code Spell & Markdown Lint | `106755316998` | MD046 continuation line 8221 | Local doc fix, ещё не push |

Source/Test Inventory и Node.js Dependency Audit на этом run уже SUCCESS. Финальные coverage/mutation результаты не утверждены. Число jobs может увеличиваться, пока workflow создаёт downstream matrices; не сравнивать частичные counts как регрессию.

После возобновления read-only команды:

```powershell
git status --short
git rev-parse HEAD
git worktree list --porcelain
git stash list
gh pr view 1266 --json state,headRefName,headRefOid,baseRefName,url
gh api repos/egorribun/university_ecosystem/actions/runs/35730420629 --jq '{id,head_sha,status,conclusion,run_attempt}'
gh api --paginate 'repos/egorribun/university_ecosystem/actions/runs/35730420629/jobs?per_page=100' --jq '.jobs[] | select(.conclusion=="failure" or .conclusion=="cancelled") | {id,name,status,conclusion}'
```

- [ ] Получить **все страницы** terminal jobs, логи каждого нового failed/cancelled и соответствующие артефакты.
- [ ] Разделить root failures, downstream aggregate failures, conditional skips и missing evidence.
- [ ] Для каждого issue записать source SHA, tested merge SHA, workflow/run/attempt/job, command, first error, reproduction, test и fix.
- [ ] Не печатать giant SARIF JSON целиком: одна строка может содержать сотни тысяч токенов. Сохранять отчёт в ignored artifacts и парсить нужные поля.
- [ ] Rerun отдельных jobs допустим для доказанной transient проблемы на неизменном SHA с корректной attempt provenance. Новый source fix требует нового SHA/run; старый зелёный job не доказывает новый source.
- [ ] Не повышать timeout и не перезапускать весь suite вместо классификации причины.

История, только для диагностики:

- `35724213801`, source `2fdb2e2...`, tested merge `9d811b29cf09fa9e96dbb8081b3b342dc885320b`: 119 jobs, 95 success/4 failure/20 skipped; 2530 s wall. Dependency/inventory/coverage/aggregate failures исправлялись опубликованным пакетом. Mutation downstream skipped.
- `35635039077`: Python group 67 killed 15/15, но upload 403; frontend aggregate отверг `shard-001:2 Timeout`. Ни один из этих частичных результатов не закрывает gate.
- Старые присланные 25+, 82, 140 failures других run не являются автоматически текущим backlog; переносить только подтверждённые незакрытые причины.

## 5. Следующая сессия: закончить локальный пакет без потери работы

### Task A — безопасный resume и inventory

- [ ] Прочитать §1 и проверить HEAD/status/stash/worktree, user audit hash, stopped container и текущий PR. При новых пользовательских изменениях не применять старые assumptions.
- [ ] Проверить доступность tools фактическими read-only командами: gh GitHub read, Python/uv, Node/npm, Docker; наличие skill files/MCP — через доступный registry, не обещать «полный доступ ко всему» по настройке sandbox.
- [ ] Не восстанавливать вручную task handles из старого чата. Проверить active agents/processes, не запускать дубликат живой сборки.
- [ ] Зафиксировать fresh CI terminal state либо bounded live state. Не делать новый push только для косметики.

### Task B — завершить canonical WASM и combined verification

- [ ] Выполнить §3.1 до strict second-clean-build evidence.
- [ ] Повторить точечные и общие проверки **после** переноса generated artifacts.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_mfa_postgres_acceptance_contract.py tests/test_semgrep_sarif_validator.py -q --no-cov -o cache_dir=artifacts/pytest-cache/resume
.venv/Scripts/python.exe scripts/quality/generate_test_inventory.py
.venv/Scripts/python.exe scripts/quality/check_orphans_and_anti_patterns.py
.venv/Scripts/python.exe verify_harness.py --repo-only
.venv/Scripts/python.exe scripts/fast_preflight.py --help
git diff --check
```

Из `frontend/`:

```powershell
node scripts/verify-wasm-artifacts.mjs
node --test scripts/verify-wasm-artifacts.test.mjs scripts/wasm-source-provenance.test.mjs scripts/wasm-runtime-smoke.test.mjs scripts/challenger-adversarial.test.mjs
npm run typecheck
npm run lint
npm run test:wasm
npm run build
```

- [ ] Выполнить worker Vitest focused tests и email/TOTP Playwright на свежем build с настроенным штатным preview и CI browser; не копировать ad hoc browser overrides в репозиторий.
- [ ] Запустить actual parallel fast-preflight с его проверенными текущими flags/defaults; сохранить JSON, SHA, duration и exit codes. `--help` выше — discovery, не проверка качества.
- [ ] Проверить source/test inventory после новых root tests; не добавлять orphan exceptions ради зелёного.
- [ ] Повторить pre-commit изменённых файлов, actionlint/security там, где затронуты boundaries; проверить zero warnings отдельно от exit 0.
- [ ] Проверить весь diff независимым reviewer: spec compliance, correctness/security, generated provenance.

### Task C — coherent commits и push

**Критический concurrency урок:** pre-commit автоматически stash-ит unstaged tracked changes. Никогда не запускать commit/hooks, пока субагенты редактируют файлы. Сначала заморозить всех writers и подтвердить это.

- [ ] Разбить пакет по смыслу: MFA PostgreSQL fixture; email-MFA browser contracts; Semgrep ledger regression; Rust/worker/generated artifacts; актуальный docs checkpoint.
- [ ] Stage явные пути, не `git add .`; внешний user audit не включать.
- [ ] После detect-secrets/pre-commit снова `git add .secrets.baseline`; проверить реальный diff, не создавать пустой шум.
- [ ] Commit maintenance scopes `test(contracts)`, `fix(security)`, `fix(quality)`, `docs(quality)`; без wave labels и без co-author trailers.
- [ ] Не bypass hooks. Если hook изменил файл — review, повторный stage и verification.
- [ ] Push обычный в `egorribun` после combined readiness. Записать точные SHAs; не force-push и не merge.
- [ ] Обновить §148 ссылкой на handoff и новые доказательства; старые timestamps/SHA не выдавать за новые.

## 6. Внешний аудит: фактический remaining scope

59 CLOSED / 2 DECLINED / 2 OPEN в пользовательском файле — его отчёт о другом checkpoint, **не сертификат текущей ветки**. Сам файл сохранить. Повторная оценка нашла BE-08 transport gap; дополнительно доказана возможность canonical WASM на локальном Linux.

### 6.1 BE-02: defaults и migration semantics

**Актуализация относительно исторического инвентаря ниже:** migration `alembic/versions/202609250001_phase_semantic_defaults.py` уже существует; §0.0 фиксирует локально пройденные PostgreSQL upgrade/downgrade/re-upgrade и 3 integration-теста. Последний локальный governed inventory: **94 dual / 40 Python-only / 0 server-only**, причём 40 — документированные application-owned UUIDv7/JSON/secret defaults. Исторические «82/52» и список 12 candidates ниже объясняют происхождение phase four, **не являются текущим backlog к повторной реализации**. Открыты deployed-catalog preflight, production-data/lock-budget/rollback acceptance и final-SHA evidence.

Исторический metadata inventory **до** phase four: 82 dual / 52 Python-only / 0 server-only, 45 tables. Из прежних 52 Python-only: 40 application-owned exceptions — 37 UUIDv7, 1 CSPRNG secret, 2 JSON defaults. Их нельзя «закрывать» копированием Python logic в server_default.

12 тогда ещё остававшихся semantic candidates (реализованы локально в `202609250001`):

1. `attachments.created_at`;
2. `chats.created_at`;
3. `chats.updated_at`;
4. `dead_letter_jobs.created_at`;
5. `dead_letter_jobs.updated_at`;
6. `failed_outbox_events.failed_at`;
7. `grades.created_at`;
8. `grades.updated_at`;
9. `message_reactions.created_at`;
10. `messages.created_at`;
11. `stored_events.created_at`;
12. `users.role`.

- [x] Source/ADR inventory, governed phase-four migration и локальный PostgreSQL upgrade/downgrade/re-upgrade подтверждены на checkpoint §0.0; повторять implementation по историческому списку не нужно.
- [ ] На каждом целевом deployed PostgreSQL **до** DDL выполнить fail-closed catalog preflight: типы, defaults, nullability, NULL rows, enum cast и lock budget; измерить реальный rollback.
- [ ] Fresh final-SHA tests/manifest и прямой SQL/ORM semantic equivalence подтвердить для фактического release target. Локальная metadata таблица не доказывает состояние внешней БД; destructive migration требует точного target и полномочий.

### 6.2 BE-08: CDC

`asyncpg.connect(replication="database")` не поддерживается; `put_copy_data` отсутствует. Исправлен безопасный startup rejection **до side effects**, сохранён default polling. Keepalive больше не подтверждает WAL за пределами успешно отправленных событий. ADR-037 фиксирует deferred transport.

Пользовательский scope от 2026-09-23 уже выводит CDC transport **за пределы функционального MVP** (§0.2). Поэтому согласование MVP-границы не ожидает повторного вопроса; технический CDC transport остаётся отдельным deferred/open долгом и не должен скрываться за статусом MVP.

- [ ] Не называть fail-closed отключение «работающим CDC».
- [ ] Для включения нужны поддерживаемый replication transport, transaction/replay ownership, реальные PostgreSQL/NATS restart/replay/ack tests, durable checkpoint и backpressure.
- [x] Зафиксировать явную MVP-границу (согласовано 2026-09-23); держать техническую строку `BE-08` как deferred/open, а не DONE.

### 6.3 RUST-P3-03 и declined рекомендации

Source-часть Base64 уже реализована: `frontend/rust-crypto/src/lib.rs` экспортирует `hmac_sha256_sign_base64`, а `frontend/src/workers/crypto.worker.ts` его вызывает. Нижеупомянутое «завершить §3.1» — историческая задача исходной паузы, **не текущая просьба повторить source implementation**. Закрытие `RUST-P3-03` требует проверенной parity checked-in `.wasm`/provenance с pinned Linux CI producer и SHA-bound final evidence; Windows build с другим байтовым результатом не достаточен.

- [ ] Подтвердить canonical Linux `.wasm`/provenance parity, worker runtime и final-SHA evidence для уже реализованного Base64 export (§3.1 — историческая source-работа).
- Не отменять без новых доказательств declined `RUST-P3-01`: общий Cargo workspace объединяет несовместимые feature graphs и меняет cache/profile contracts.
- Не ослаблять `INFRA-12`: main-only retention cleanup обязан fail-closed при отсутствии обязательных secrets, а не warn-and-skip.
- [ ] Пересмотреть остальные закрытые audit IDs по mapping source/test/evidence на final SHA, включая дубликаты GO/SEC, без повторной ненужной переписи.

## 7. Master plan stages 0–10: обязательная остаточная приёмка

Существование компонента и локальный unit PASS не доказывают всю строку. Для каждой acceptance строка evidence должна содержать SHA, сценарий, роль/язык/device/state, команду, результат и артефакт. Missing evidence обозначать OPEN/EVIDENCE-BLOCKED.

### Stage 0 — foundation и доказательства

- [ ] Source head, tested merge SHA, artifact SHA и resulting main разделены и проверены.
- [ ] Нормализатор отвергает чужой SHA/hash, пустой/partial/stale/missing report, недопустимую reuse другого run/attempt.
- [ ] Manifest schema, metric capabilities, source roots, versions, timestamps, workflow provenance согласованы.
- [ ] Harness 29/29 либо актуальный полный больший набор; inventory и отсутствие accidental artifacts.

### Stage 1 — общая дизайн-система, a11y и performance

- [ ] Component inventory: typography/spacing/radii/elevation/focus/motion, loading/empty/error/offline.
- [ ] Buttons/fields/tabs/cards/dialogs/popovers едины, focus виден/не перекрыт; targets >=44×44 по внутреннему контракту.
- [ ] Glow и тяжёлые декоративные hover/layout-анимации отсутствуют в утверждённых местах; частые transitions используют transform/opacity и reduced motion.
- [ ] Timers/observers/portals/object URLs освобождаются; повторяемые сценарии дают memory plateau.
- [ ] WCAG 2.2 AA: keyboard, focus order/trap/restore, Accessible Authentication, zoom 200%, contrast, axe без serious/critical и screen-reader smoke.
- [ ] LCP p75 <=2.5 s, INP <=200 ms, CLS <=0.1; LHCI >=95 на ключевых маршрутах; main JS <500 KB; lab score не заменяет field CWV.
- [ ] Visual/Storybook baseline покрывает актуальную систему, без слепого обновления snapshots под regression.

### Stage 2 — auth/MFA и removal

- [ ] Login/register auth-shell, autocomplete/password managers, safe redirect, CSRF, lockout/offline/error, SSR без hydration mismatch.
- [ ] Public normal MFA union `totp | email_otp`, emergency recovery отдельно; runtime/API/schema/UI/generated SDK без WebAuthn. Historical migration data не путать с активным runtime.
- [ ] Destructive credential migration preflight: TOTP → totp; verified email → email_otp; account без применимого безопасного пути блокирует migration до remediation.
- [ ] Email OTP: 6 CSPRNG digits, 10 min TTL, 5 attempts, 60 s resend cooldown, digest/HMAC at rest, one-time consumption, atomic rotation, binding user/challenge/session/fingerprint, IP/user limits, no enumeration/secret leakage.
- [ ] `/auth/mfa/verify` и `/auth/mfa/email/resend`: correct challenge token/revision/expiry/counters/hint; stale code сразу недействителен.
- [ ] Real transactional outbox/SMTP RU/EN: delivery/failure/retry и expired/replayed/wrong/rotated/attempt-exhausted cases; concurrent verify/resend, fingerprint mismatch.
- [ ] Recovery one-use, TOTP, session revocation/trusted devices/reset, roles; PostgreSQL и mocked E2E доказательства §3 не заменяют целый journey.
- [ ] OpenAPI/SDK/MSW deterministic regeneration и zero drift.

### Stage 3 — shell

- [ ] Navbar passive scroll + rAF/hysteresis; stable layout height/CLS; mobile/desktop state parity и reduced motion.
- [ ] Footer groups, official Telegram SVG, external-link labels, responsive layout.
- [ ] MobileMenu focus trap, escape/backdrop, scroll lock, safe areas, быстрые повторные taps без mount races.
- [ ] Bottom nav equal hit sectors, centered icons, один active state, ARIA/keyboard, virtual keyboard/browser chrome.
- [ ] Visual widths 360/390/768/1024/1440 и stress быстрых переходов.

### Stage 4 — scroll/filter/map

- [ ] New route restoration по route key; search/filter сохраняет viewport; modal/detail возвращает anchor/offset.
- [ ] News/Events categories без scroll-to-top/remount; Events/Activity slider geometry и hitboxes согласованы.
- [ ] Map lazy import и idle/intent prefetch, один instance, memo layers/markers, clustering больших данных.
- [ ] Local gesture/overscroll containment не блокирует страницу; wheel/touch/pinch/end interaction не сдвигают внешний viewport.
- [ ] Reduced-motion/weak-device effects, map workers/listeners cleanup; измерение long tasks/memory, не только URL assertions.

### Stage 5 — dashboard/content/Stories

- [ ] Карточки/skeleton-to-content geometry, без лишней empty высоты, wobble/glow; сохраняются CRUD/detail/bookmarks/registration/admin.
- [ ] Stories только с интерактивного avatar/circle; preload следующей, visibility/interaction pause/resume, keyboard/swipe, focus/ARIA, portrait/landscape.
- [ ] Repeated-open/close memory plateau, cleanup media/timers/listeners.
- [ ] Content empty/error/offline/pagination, stable query keys, no duplicate fetch, optimistic rollback.

### Stage 6 — messenger

- [ ] Desktop dialogs/chat/context и mobile back navigation; unread/typing/delivery/read/edited/reply/files.
- [ ] Virtualizer keys/measurements, prepend anchor, autoscroll только у конца; user-reading позиция сохраняется.
- [ ] Real REST hydration + WS dedup/order, reconnect/backoff/offline, retry/idempotency.
- [ ] DM/groups/edit/delete/reply/forward/reactions/receipts/attachments/permissions, oversize frames/files.
- [ ] `role=log`, polite announcements, keyboard composer и accessible attachment/reaction controls.
- [ ] Go race/load/security, delivery latency, goroutine/socket cleanup при restart и disconnect.

### Stage 7 — profile/settings/activity/i18n

- [ ] Gap-аудит существующих profile Header/Details/Editor/Achievements/NowPlaying, не перепись с нуля.
- [ ] Stable Query updates, upload previews/cleanup, тяжёлые sections/rerenders; save/validation/rollback/error.
- [ ] Settings General/Profile/Security/Notifications/Sessions/Integrations, responsive navigation сохраняет state, email MFA без WebAuthn.
- [ ] Activity heatmap/trends/grades/participation/attendance/timeline и единый period; empty/partial/error; табличная доступная альтернатива графикам.
- [ ] RU/EN parity, нет raw keys; interpolation/plural/date/number; backend email/notification translations; dynamic keys scanner.

### Stage 8 — уведомления

- [ ] Пять canonical topics: `news.published`, `schedule.changed`, `events.published`, `chat.message.created`, `system.release`.
- [ ] Один notification ID/metadata для in-app/live/Web Push, dedup и согласованный unread count.
- [ ] Topic opt-in/quiet hours/permission semantics на backend/frontend.
- [ ] Permission request только после понятного действия, не при первом render; default/granted/denied/unsupported; после отказа не повторять без команды пользователя.
- [ ] Real push/deep links/offline/reconnect/stale endpoints/admin publication по всем пяти topics. Mocked PushManager не сертификат реальной доставки.
- [ ] Общие уведомления не расширять на email-канал; email здесь для MFA.

### Stage 9 — полная quality closure

- [ ] Python fresh 100% line/branch/applicable metrics, strict mypy/Ruff/AST, полный mutmut inventory; 100% viable, нет survivor/timeout/no-test/unclassified.
- [ ] Frontend typecheck/lint:all/RUEN/unit/integration/WASM/E2E/SSR/build; merged four metrics100%; Stryker100% viable и полный source universe.
- [ ] Go fmt/vet/golangci/race, required components statements100%; unsupported branch/function явно N/A, не фиктивные100%; Go mutation governance закрыта evidence, не молчаливым omission.
- [ ] Rust четыре компонента, all-target tests, llvm line/function/branch, source-proven zero-branch derivation только где применима, deny/fuzz bounded.
- [ ] API: все фактические shards и aggregate из текущего workflow; исторические «4/8» не использовать без проверки; OpenAPI/SDK/mock/contracts drift0.
- [ ] Security: pre-commit/detect-secrets/gitleaks/Bandit/Semgrep/CodeQL/actionlint/Checkov/dependency/license/image scans, SBOM/provenance; нет незакрытых high/critical.
- [ ] Infra: Compose matrix, Helm, wrapper envsubst, Kyverno, ExternalSecrets/TLS/HPA/resources.
- [ ] Manifest schema-valid/current identity, hashes и native/derived/unsupported; source inventory complete, missing reports empty.
- [ ] Каждый skip доказан `if:` и не исключает обязательный gate данного event.
- [ ] Реальные предупреждения build/local tooling разобраны; exit0 не объявляется zero-warning.

### Stage 10 — Docker, staging, release

**Граница текущей среды:** реального staging-кластера нет; пользовательский scope 2026-09-23 допускает Docker Core/full и локальный kind как доступную MVP-приёмку. Это не доказательство production rollout: внешний кластер, домены, TLS/secrets, реальные устройства и field CWV остаются explicit external-only gates, если их не заменит отдельное согласованное решение. Не подменять локальный kind словом «staging» в SHA-bound аудите.

- [ ] Проверить все поддерживаемые Compose combinations `config --quiet`; не запускать overlays отдельно, если они зависят от base.
- [ ] Реальный путь `start-docker.ps1 -Build`, затем Core/full с измерением RAM/CPU/startup/readiness и корректным shutdown. Не удалять пользовательские volumes и не применять global prune.
- [ ] Backend `/health/ready`, frontend SSR/Caddy, gRPC file processor, WebSocket, PostgreSQL, раздельный Redis, NATS и observability.
- [ ] Real login/TOTP/email, dashboard/news/events/map/chat/profile/settings/activity/push/admin journeys на immutable digest build.
- [ ] Exact-six image producer и manifest: проверить актуальный canonical список, все шесть digests/SBOM/attestations/provenance, source and tested identity.
- [ ] Перед promotion подтвердить разрешение merge/release и точный staging target/context/namespace/TLS domains/secrets. Историческое разрешение merge dependabot не blanket permission на production.
- [ ] Resulting main SHA после merge проверяется отдельно; не присваивать ему сертификат PR source/merge SHA.
- [ ] Тот же immutable build на production-like Kubernetes, TLS, ExternalSecrets refresh, resources/HPA, metrics/logs/traces/alerts.
- [ ] Real browser/device matrix, field CWV, chaos/restart и rollback с доказательством сохранности данных.
- [ ] Итоговый `AUDIT_QUALITY_CLOSURE_<verified-sha>.md`: команды/exit/duration/counts/metrics/scopes/hashes/images/SLO/security/skips/remaining risks. Audit-only commit не подменяет audited source SHA.

## 8. Сквозная acceptance matrix

| Измерение | Обязательный набор |
| --- | --- |
| Роли | student, staff/teacher, admin |
| Языки | RU, EN |
| Viewports | 360×800, 390×844, 768×1024, 1024×768, 1440×900 |
| Браузеры | Последние две Chrome/Edge/Firefox/Safari; реальные iOS Safari/Android Chrome |
| Состояния | loading/empty/partial/success/validation; 401/403/404/409/422/429/5xx; offline/reconnect/timeout |
| A11y | keyboard/focus/200%zoom/reduced motion/contrast/axe/screen reader |
| Performance | cold/warm, slow CPU/network, large histories/data, repeated lifecycle, memory plateau |
| Reliability | duplicate/retry/idempotency/concurrent mutation/restart/stale cache/dependency failure |
| Security | CSRF/redirect/XSS/session/replay/fingerprint/traversal/oversize/secrets+PII |
| Visual | auth/shell/dashboard/news/events/map/chat/profile/settings/activity/notifications/admin |

Playwright browser engines и mobile emulation не равны реальным branded versions/devices. Не утверждать универсальную матрицу по одному desktop Chromium. Существующий тест можно зачесть только после проверки его assertions и scope.

## 9. Все девять организационных задач с исходного изображения

### O1 — machine-readable timing/resource ledger

- [ ] Job/run/source/attempt timestamps: queue/setup/test/upload, peak concurrency, retries, timeout cause; CPU/RSS измерять instrumentation, Jobs API их не предоставляет.
- [ ] Проверить overlap всех workflows в общем account cap20, а не одного Matrix.
- [ ] Существующие analyzer/renderer использовать повторно; unsupported fields помечать явно, не нулями.
- Baseline `35724213801`: queue p50/p95 63/386 s, setup34/98, test51/725, peak19. Mutation не запускалась; 42 минуты не сравнимы с полным mutation run.

### O2 — duration-aware sharding

**Актуализация:** `scripts/quality/select_stryker_history_artifact_cli.py` и `tests/test_select_stryker_history_artifact_cli.py` уже есть и подключены в `.github/workflows/ci.yml`; `tests/test_stryker_cost_workflow_contract.py` содержит contract. Коммиты `8a5d43ff2` и `e0d1da451` защищают trust boundary и совместимый retry исторических timing candidates. Чекбоксы ниже — исходная спецификация, **не перечень файлов, которые надо создать заново**. Проверить на свежем SHA bounded provenance/fallback и замерить реальный выигрыш, не reuse mutant results.

- Python cost-aware execution, frontend same-run retry history и source-код совместимой cross-run timing history уже есть; **свежая end-to-end верификация и измеренный эффект ещё OPEN**.
- [x] CLI `scripts/quality/select_stryker_history_artifact_cli.py`, tests и workflow wiring присутствуют в source. Их существование не означает, что runtime выигрыш и provenance уже доказаны.
- [ ] Проверять config/lock/toolchain/test-input/preflight-inventory fingerprints, trusted producer, digest, finite costs каждого current viable source.
- [ ] Ограничить runs/pages/bytes/entries/age и общий monotonic deadline. В архиве ровно один regular cost JSON; reject links/extra/executable/cache payloads.
- [ ] Invalid/stale/incomplete history → diagnostic и безопасный existing planner fallback; **никогда reuse test/mutation results**.
- Не ослаблять `select_same_run_artifact_cli.py`. `download_stryker_cost_artifacts.py` сейчас не вызывается workflow; его полировка не ускоряет текущий CI.

### O3 — сокращение повторного setup

- [ ] Измерить critical path/setup cache hit/miss; immutable dependencies/artifacts только с проверкой совместимости и trust boundary.
- [ ] Не исполнять untrusted cache в privileged release; read-only PR caches и producer identity разделить.
- [ ] Не путать экономию runner-minutes с улучшением wall time/очереди.

### O4 — mandatory/advisory/nightly

- [ ] Сверить live main ruleset с exact produced check contexts и workflow guards.
- [ ] Документировать событие/guard/required status; не переносить обязательную проверку в nightly ради ускорения.
- [ ] Изменение branch protection требует отдельного согласования, не implied autonomous optimization.

### O5 — retries только transient

- [ ] Классифицировать network/runner/upload errors, сохранить first failure/artifacts; bounded attempts и backoff.
- [ ] Product assertion, survivor, no-test, deterministic crash не retry-until-green.
- [ ] Проверить mixed-attempt aggregation fail-closed; upload403 не превращать в killed certificate.

### O6 — check/artifact/owner/runbook catalog

- [ ] Existing catalog covers56 workflows/185 source jobs на предыдущем checkpoint; проверить актуальное количество.
- [ ] У каждой проверки canonical name, owner role, inputs/outputs, expected measured duration, troubleshooting и skip reason.
- [ ] Catalog validator и tests должны ловить drift; не создавать параллельный несвязанный каталог.

### O7 — CI health report

- [ ] p50/p95 PR completion/queue/setup/test/upload, critical path, failures/retries/timeouts/skips, quality evidence identity.
- [ ] Указывать population/window/sample count; timeout budget не наблюдаемая duration; lower bound не прогноз.

### O8 — local fast-preflight

- [ ] `scripts/fast_preflight.py` уже существует; verify6lanes на combined candidate, bounded parallelism и machine JSON.
- [ ] Не запускать mutating npm installs/build generators параллельно с hooks или writers.
- [ ] Отдельный writable pytest cache для каждого worker/task; старый `.pytest_cache/v/cache` выдавал Windows access denied. Не исправлять это широкими ACL/recursive delete; документировать и использовать owned artifact cache.

### O9 — heartbeat watchdog

- [ ] Existing mutation deadlines/partial reports не равны общему heartbeat watchdog.
- [ ] Нужен heartbeat с PID/process group/stage/last progress/resource counters, bounded graceful shutdown и сохранение partial reports.
- [ ] Отличать долгую законную компиляцию от зависания; test silent-live, stale heartbeat, finished process, orphan-child, signal escalation.
- [ ] Не повышать общий timeout без root-cause evidence.

### Контролируемый A/B после трёх comparable green runs

- [ ] Baseline сохранить на существующем budget (frontend max-parallel6 /64 shards на текущем checkpoint; перепроверить YAML).
- [ ] Затем по одному варианту: max-parallel7, затем8 **либо** lane split8/8,9/7,7/9.
- [ ] Сравнить queue/starvation/RSS/CPU/timeouts/criticalpath/full evidence; rollback при ухудшении или потере provenance.
- [ ] Не обещать обход account cap20. Избыточный matrix fan-out расходует очередь, а не создаёт новые slots.

## 10. Spelling, docs и dependency follow-up

### 10.1 Spelling gate: прежний dormant-дефект устранён, полнота scope ещё открыта

**Актуализация:** прежний `ignorePaths: ["**/*"]` уже удалён. Текущий `cspell.json` исключает только служебные/generated пути и содержит reviewed canary-set из **9 authored English docs**; `tests/test_cspell_gate_contract.py` требует все 9 и запрещает universal ignore, CI проверяет `number_of_files_checked == 9`. §0.00 фиксирует green CSpell 9.2.2/10.2.2 на выборке (2 файла, 0 issues) для более раннего checkpoint; это **не** проверка всего авторского корпуса или RU/EN. Абзац ниже о zero-file gate и предложение scope относятся к исторической диагностике, не к состоянию активного CI. Remaining: согласовать/зафиксировать полный mandatory corpus, RU dictionary/license, пройти все authored docs, затем code и fail-closed nonempty count без сокрытия typo fixtures.

Исторический defect **до исправления**: `cspell.json` содержал `ignorePaths: ["**/*"]`; action-style command проверял 0 файлов и выходил 0. Универсальный ignore уже удалён; открытым остаётся **полнота обязательного корпуса и RU/EN-policy**, а не zero-file gate.

Диагностика: CSpell10.2.2, sample3832trackedtext,27862unknown occurrences, приблизительно2071unique nongenerated; **не 27862 опечатки**. Imported skills/lockfiles исключены только из диагностического sample, не как approved release exclusion. RU dictionary2.3.2 имеет GPL3 dev-tool licensing consideration; dialect EN policy тоже определить.

Пользователю уже предложен выбор scope: начать с authored current docs либо сразу весь authored code/docs. Ответ в текущем контексте не получен. Не объявлять это blocker для остальных задач и не молча урезать gate.

- [ ] Зафиксировать authored/generated/vendor/historical boundaries по policy; уточнить scope если решение меняет обязательность.
- [ ] Добавить CLI/action canary: нормальный RU/EN проходит; `mispeling` и `ашибка` приводят к failure. Document API, обходящий path filtering, недостаточен.
- [x] Убрать universal ignore и зафиксировать nonempty English canary-set.
- [ ] Расширить проверку на утверждённый authored corpus, исправить настоящие опечатки и точечно документировать технический словарь.
- [ ] Не исправлять intentional invalid fixtures (`pullPolcy`, `Привед`, `gmial`) и не добавлять их в глобальный whitelist.
- [ ] Проверить свежий gate реально scanned files>0, RU/EN, lock reproducibility, license scan.
- Diagnostic scripts/data: `C:/Temp/cspell-audit-2ca7a320bb8d4eb887723d376a5c7268/`.

### 10.2 Documentation hygiene

- [ ] Одна активная roadmap с traceable task IDs; handoff — snapshot, external audit — input, historical prompts marked.
- [ ] Reference scan перед move/delete; не удалять original reports/пользовательский untracked audit как «мусор».
- [ ] Обновить заявленные toolchain версии/commands на verified current source, исправить outdated pass claims, проверить local links/anchors/remote URLs по отдельности.
- [ ] Привязать every acceptance requirement к evidence/backlog, а не надеяться на множество разрозненных checkbox.

### 10.3 Dependabot/default branch

На проверенном branch lockfiles affected versions patched: anyio4.14.2, httpx2/httpcore2 2.12.0, urllib3 2.7.0, js-yaml4.3.2, Go OTel1.46.0/grpc1.83.2. Все16open default-branch alerts просмотрены; пять Go alerts ссылаются на старые записи dependency graph, который содержит одновременно old/new versions.

- [ ] Перед promotion обновить live alerts, SBOM и dependency graph provenance; проверить отсутствие реально используемого старого graph/module.
- [ ] После main promotion проверить fresh graph; не dismiss alert и не bump dependency только ради скрытия stale record.
- [ ] Не считать npm audit0 доказательством чистоты Python/Go/Rust/images или всего default branch.

## 11. Организация субагентов после возобновления

**Ближайший актуальный параллельный набор после resume:** lead координирует terminal CI/identity/коммиты; backend worker исправляет три fixture failures и проверяет lease safety; frontend worker закрывает два account-boundary Push дефекта через RED→GREEN; независимый security reviewer проверяет готовый diff (до четырёх active slots вместе с lead). Не давать backend и frontend workers общие файлы. Работать с этим набором только после явной команды продолжить, а не в текущей паузе.

Сейчас доступны максимум четыре active slots: lead + три workers. Параллелить независимые scopes, не количество ради количества. Skill инструкции читать целиком главным агентом до выполнения; subagent reading не заменяет это.

| Роль | Ближайший bounded scope | Запрет пересечения / выход |
| --- | --- | --- |
| lead | Live CI triage, ownership, docs ledger, integration и commit | Единственный stage/commit/push coordinator |
| backend worker | Три MFA delivery fixture failures + lease expiry/reclaim contracts | Только backend tests и при доказанной необходимости MFA production code; RED/GREEN/JUnit |
| frontend worker | Два Push account-boundary дефекта + canonical B topics | Только четыре перечисленных frontend WIP-файла и согласованные focused tests; RED/GREEN/browser |
| independent reviewer | Read-only trust-boundary/security/provenance review готового frontend/backend diff | Не быть автором reviewed patch; findings с файлами/линиями |

После освобождения slots возможны отдельные bounded задачи map lifecycle, real WS contracts, Push topics или CI cost selector. Не запускать одновременно npm installs/formatters/генераторы по одной dependency tree. Не создавать новые user-owned Codex tasks вместо настоящих subagents без запроса пользователя.

Предыдущие agent names помогают найти сообщения, но не гарантируют живые handles:

- `bound_cost_download`: email-MFA E2E и Semgrep; DONE.
- `dependency_alert_reassessment`: dependency audit и WASM; interrupted при pause.
- `spell_gate_audit`: spelling diagnostic и MFA PostgreSQL fixture; DONE.
- `review_mfa_fixture`: независимое fixture/E2E/Rust source review; DONE, generated artifacts ещё не review.

Пример bounded dispatch: «Прочитай domain AGENTS/quality и relevant skill; только указанные файлы; воспроизведи RED, implement, focused tests; никакого stage/commit/deploy; верни причины, diff, commands/exit/counts, resource cleanup и ограничения». Каждый автор → spec review → независимый code/security review → combined gate. Не ожидать часами без проверки живого процесса/прогресса.

## 12. Полномочия, инструменты и неразрешённые внешние шаги

Проверены в этой работе: Git/gh read+обычныйpush, Pythonvenv, npm/Node, DockerLinux, локальные skills и subagents. Context7/ClickUp/MCP использовать если реально доступны и нужны; отсутствие подключения не блокирует канонические repo docs. `danger-full-access` не доказывает наличие cloud credentials, SMTP, push provider или Kubernetes доступа.

Нужны отдельная актуальная проверка/уточнение перед внешними шагами:

- exact staging kube context/namespace/registry/hosts/TLS/secrets/observability target;
- real test email/push recipients и consent, без рассылок третьим лицам;
- main/release promotion authorization, maintenance/rollback window;
- real devices/branded browsers и достаточное окно field CWV;
- spelling mandatory scope, если пользователь ещё не ответил;
- наличие **нового** решения пользователя, если будущий scope вновь включит CDC transport в functional MVP; решение 2026-09-23 пока действует.

Нет необходимости спрашивать пользователя о каждой локальной тестовой правке. Но нельзя считать старое автономное поручение разрешением на destructive production migration, bypass, произвольное merge или изменение прав доступа.

## 13. Evidence и финальная проверка полноты

Для каждого task хранить: ID/requirement, owner, source SHA, tested SHA, run/attempt/job, command/toolversions, OS/env, start/end/duration, exitcode, test count, coverage numerator/denominator, mutation outcomes, artifact paths/hashes, reviewer, ограничения и next action.

Существующие полезные paths:

- `artifacts/quality/ci-health-35724213801.json` и `.md` — partial-run diagnostic;
- `artifacts/quality/model-default-inventory-0ec4fed3a.json`;
- `artifacts/quality/mfa-postgres-root-review.xml`;
- `artifacts/fast-preflight/fast-preflight.json` — старый tested SHA c082;
- `artifacts/wasm-linux-baseline-0ec4fed3a/` — bootstrap/source/change archives;
- `frontend/test-results/` — local Playwright traces;
- `C:/Temp/mfa-pg-audit-46512ec3ab764826822be98f478a4b9a/`;
- `C:/Temp/cspell-audit-2ca7a320bb8d4eb887723d376a5c7268/`.

Ignored artifacts и C:/Temp могут исчезнуть; их отсутствие означает повторную верификацию, не разрешение восстановить цифры по памяти. Не переносить сырые временные артефакты в source history без осмысленной политики. Handoff сохраняет результаты, но не заменяет машинные доказательства.

### Финальная Definition of Done — все строки одновременно

- [ ] Всё обязательное stages0–10 и O1–O9 либо доказанно выполнено, либо explicit user-approved scope change; unknown не DONE.
- [ ] Все applicable coverage metrics100%, viable mutation100%, complete source/test/mutant inventory и fail-closed manifest.
- [ ] Fresh exact-identity required CI green; no unclassified skipped/cancelled/timeout/missing artifacts.
- [ ] Product roles/RUEN/states/devices/a11y/perf/reliability/security matrix подтверждена подходящими реальными проверками.
- [ ] External audit IDs пересмотрены, P0/P1/high/critical findings отсутствуют; deferred boundary согласован, а не скрыт.
- [ ] Exact-six immutable images, DockerCore/full, stagingTLS/observability/CWV/chaos/rollback и authorized release подтверждены.
- [ ] Current docs непротиворечивы; resulting-main/source/tested/audit-only SHA не смешаны.
- [ ] Финальный рабочий каталог не содержит случайных артефактов; судьба пользовательского untracked audit согласована без удаления данных.
- [ ] SHA-bound final audit опубликован; только тогда goal может стать complete.

Этот handoff покрывает известную оставшуюся работу и условия доказательства результата. Он не обещает отсутствия неизвестных дефектов «до каждой строки» и не является сертификатом безупречности. При новой находке — RED, severity/owner/task/evidence, затем исправление или явное согласованное решение.

## 14. Готовая команда для следующей сессии

**Актуальная команда (2026-09-27):**

> Продолжи ACTIVE goal на `egorribun`. Прочитай root/domain AGENTS, quality contract, **самый свежий timestamp внутри §0.resume-20260927** этого handoff, continuation/master и внешний audit без изменения user файла. Сначала сверяй live ROOT/origin/PR/CI identity и процессы: local коммиты могут быть новее опубликованногоc12, а текущий run36334802892 уже прошёл unit/coverage barriers и выполняет mutations. Не повторяй старые Push/MFA/WASM fixes по historical тексту. Не edit/stash/commit frozen ROOT во время canonical mutation; используй isolated workers с независимым review и ROOT fresh gates перед transfer. Не push неurgent batch поверх active fullmatrix. Сохрани4stash/useraudit/junctions/ownedresources/legacydata. Закрой фактически оставшиеся mutation/typing/product/liveinfra/O1–O9 acceptance из актуальной дельты и §§6–13; неподтверждённый пункт остаётсяOPEN. Нет authority main merge/bypass/forcepush/realproduction/staging; localkind согласован, но approval новых C0/O9 дизайнов проверяй по реальному user ответу. Finalgoalcomplete только после exactidentity terminal evidence и всех release gates.

**Историческая команда 2026-09-25 ниже — только запись прежнего resume; не выполнять её stale claims как текущие:**

> Возобнови goal на ветке `egorribun`. Сначала прочитай корневой и затронутые доменные `AGENTS.md`, `quality/quality-contract.json`, **§0.000 этого handoff**, continuation/master plans и пользовательский внешний аудит без его изменения. Проверь live Git/PR/CI вместо старых snapshot: опубликованный PR #1266 на `1488096d0` завершил CI run `36118352908` красным (три backend fixture failures, производный `CI Success`, downstream skips); локальный handoff `HEAD` вместе с `6b1e2c7` ещё не запушен, а четыре frontend Push/API файла остаются unstaged WIP. Не потеряй их и untracked `AUDIT_PLATFORM_FULL.md`; не делай broad stage/reset/clean. Параллельно, но на непересекающихся файлах, исправь backend fixture с RED→GREEN и два подтверждённых cross-account Push дефекта, проверив backend meaning `topics=None` vs `[]` и live auth identity; затем independent security review, proportional full gates, coherent commits, обычный push и fresh exact-SHA CI до terminal 100% coverage/mutation evidence. После этого продолжи remaining §6–§13 и актуальный continuation plan (Docker Core/full, data-preserving OSS S3 cutover, local kind вместо отсутствующего staging по согласованному scope, immutable images/TLS/observability/CWV/rollback/final SHA-bound audit). Не повторяй уже реализованные source-фичи по историческим чекбоксам. Не merge/deploy/bypass без актуальных полномочий и не объявляй весь MVP завершённым по узкому green run.
