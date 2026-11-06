# Напутствие агенту — исторический снимок (пауза 2026-11-05 ~14:30 MSK)

Оперативные инструкции ниже заменены [безопасной паузой 2026-11-06](2026-11-06-pause-handoff.md). Работа остановлена по поручению владельца; не возобновлять автоматически.

Этот handoff используется до завершения работы; решение об удалении принимается
после проверки сохранности нужного контекста.

## Текущие правила и статус — post-CAS checkpoint до обновления документов, 2026-11-06 11:47 UTC

Этот раздел заменяет оперативные инструкции ниже. Работай только в основном checkout на ветке egorribun и используй только GPT-6 Luna Max. Изменения Git выполняет только root; read-only Git checks разрешены. Не делай hard reset или stash, не создавай и не используй worktree и не запускай старые команды из исторических разделов.

Точный семифайловый CAS одобренных owner postimages завершён 2026-11-06 в 11:47 UTC. Этот checkpoint отражает состояние после policy/guard интеграции и до обновления документов; текущие policy counts проверены отдельно. Он не утверждает, что финальные source gates прошли.

Формальная приёмка не изменилась: **449 / 512 accepted, 63 open**. Активны baseline 242, disposition policy **490 (363 + 106 + 21)**, Gitleaks 27 и Semgrep ledger 15. Обе owner decisions материализованы точными postimages; 106 ранее approved и 21 новых identities входят в active 490. Политические записи не являются scanner clearance и не меняют audit acceptance.

Сохранённый SAST run был запущен в 11:02 UTC, до policy CAS в 11:47, и не проверяет post-CAS policy/guard. Он сообщил 15 observed findings и 0 scanner errors; offline mapping добавил два inline HTML slices: 2,589 paths всего, 15 findings, 0 inline findings, 4 SARIF runs. Raw runner завершился с кодом 1 из-за strict stale inline-SARIF namespace rejection; дополнительно `python.boto3.security.hardcoded-token` получил `FIXPOINT TIMEOUT` в `run_gate`. Offline remap не является новым scan и не снимает timeout. Gate остаётся HOLD до refactor без изменения rules/limits, targeted proof timeout rule, затем нового полного scan итогового source. **GREEN нет.**

Ограниченные результаты: backend mypy 366 files PASS; frontend typecheck/lint/format source-rebound на 2,245 paths; Ruff/format 108 staged Python paths PASS; выбранные `fc4e` tests 32 PASS; Linux race 19 packages PASS для трёх Go services на отдельном immutable source archive; pinned Node/Caddy Alpine zlib 1.3.2-r1 checks PASS с подтверждённой очисткой временных containers. Это scoped evidence, не замена full-source gate и hosted required checks.

Temporal runtime proof был привязан к отдельному сохранённому source snapshot и прошёл за 46.292s в указанной области: file processor `default:write` обработал permissioned workflow, traversal остановлен до MinIO, прошли пять JWT denial cases и девять peer port negatives; scanner показал два workflow-start markers и не показал fatal marker. Это не доказывает scanner polling или непроверенные порты. Cleanup отдельно подтверждён: Compose down 0, ресурсов проекта не осталось, bootstrap lease scrubbed, runtime-input root пуст с protected ACL, synthetic inputs удалены. Предыдущая compile-only failure попытка остаётся отдельной исторической receipt и не подменяет последующий PASS.

Следующий checkpoint: завершить частный refactor SAST orchestration без изменения rules/limits, доказать targeted timeout rule, затем повторить full-source SAST и обычный hook на post-CAS source; выполнить применимые hosted required checks для окончательного source. Active policy остаётся 490; audit acceptance — 449/512, 63 open. Отдельные Temporal/Go receipts сохраняют только указанную область и не дают общего GREEN.

## Исторические стартовые инструкции — superseded

Следующие детали фиксируют прежний план и не являются командой к выполнению.
Прежний план требовал чтения AGENTS.md и fetch перед работой; эти шаги не
заменяют текущие правила выше. В нём также были описаны состояние checkout на
тот момент и резервные patch-файлы; их наличие не разрешает восстановление,
reset или откат.

Прежний handoff назначал Haiku для кода и ревью и допускал до семи агентов.
Теперь эти рекомендации заменены правилом GPT-6 Luna Max. Старый порядок
коммитов предлагал worktree `C:\uewt3`, `git reset --hard`, staging, commit,
push и reset основного checkout; все эти действия superseded. Их нельзя
выполнять: Git операции принадлежат только root, hard reset/stash/worktree
запрещены. Упоминание другого старого worktree ниже также историческое.

## Исторический отчёт сессии

Сведения ниже отражают состояние на момент прежней паузы; верхний текущий
раздел supersedes их для статуса source и hosted checks.

### Что было сделано в той сессии
Ревью 96 ночных коммитов `c3693dbed..350b21608` (31 тыс. строк) провели 7 ревьюеров. Отчёты лежат в `.git/ue-review-2026-11-05/R1..R7-findings.md`, разборы CI в `D1-diagnosis.md` там же. Критических дефектов нет. Трейлеров и запрещённых паттернов в коммитах нет.

Запушено:
| Коммит | Что |
|---|---|
| 2400a1659…350b21608 | шесть ночных коммитов, раньше лежали только локально |
| 39bfd0152 | autouse-фикстура в `tests/conftest.py` снимает глобальное OTel-инструментирование SQLAlchemy после каждого теста. Это причина падения шарда 0 в `test_retained_table_migration` (утечку давал `test_otel_v2::test_otel_sampler_configuration`) |
| 8c76acbc9 | chat: при Redis ReadOnly/MasterDown/ClusterDown откат к receipt-constraint, комментарий в DLQ поправлен |
| da36ff6c8 | TruffleHog AGPL-3.0: точное исключение по пакету, верификатор привязан к пину из `trufflehog.yml`, срок до 2027-01-10 |
| 1cc8fb2db | тесты named-proofs, AUD-363, OSV теперь доходят до своих guard; runner AUD-363 убирает tmp |

CI на 1cc8fb2db ещё не смотрели. На 6c56a28dd было 7 красных проверок:
- шард 0 (исправлено в 39bfd0152);
- Dependency Review (исправлено в da36ff6c8);
- live-realtime-visual (Temporal);
- kind;
- три агрегата, которые красные из-за упавших выше.

## 3. Исторический снимок WIP на момент паузы

Списки файлов, статусы и todo ниже сохранены для истории. Они не являются
текущими назначениями и не разрешают редактировать исходники или запускать
проверки. Используй только актуальные root-задачи; старые пункты проверяй по
текущему исходнику и receipts, прежде чем делать вывод о состоянии.

### 3.1 Kind: диагностика пробы mTLS (готово, тесты 168/168, не закоммичено)
- **Файлы:** `app/server/internal_mtls.py`, `app/server/spiffe_transport.py`, `scripts/kind/aud373_internal_mtls_proof.sh`, `tests/test_internal_mtls_kind_contract.py`, `tests/test_internal_http_mtls.py`, `tests/test_spiffe_transport.py`.
- **Что сделано:** каждый отказ `probe()` пишет в stderr `internal_mtls_probe_failed step=… error=…`, `admit()` логирует `internal_mtls_peer_rejected`, скрипт kind запускает пробу в каждом backend-поде. Заодно исправлены cleanup при частичном создании кластера, таймауты curl/build/push, ловушки INT/TERM и ложный FAIL из-за pipefail.
- **Что блокирует коммит:** локальный хук Semgrep (`--config auto`, правила дрейфуют) падает на audit-правиле `python.lang.security.audit.httpsconnection-detected` в строке `HTTPSConnection(` файла `internal_mtls.py`. Эта строка есть и на HEAD, но раньше хук её пропускал. **Не обходить.** Блок разблокирует задача 3.6: локальный хук на закреплённом наборе правил (в нём audit-only правил нет).
- **Первый кандидат на причину:** в `probe()` `timeout=1` на TLS-соединение и запрос `/health/ready`. Если readiness проверяет зависимости дольше секунды, проба молча возвращает False. Подтвердить по новой диагностике в первом же прогоне kind.

### 3.2 Temporal: loopback internal-frontend (почти готово, тесты не прогнаны)
- **Причина** (доказана по исходникам Temporal v1.30.7, `D1-diagnosis.md`): включён JWT-авторизатор, а `internal-frontend` нет. Системный клиент worker scanner ходит в публичный frontend без токена, получает `Request unauthorized`, и scanner.go:252 завершает процесс через Fatal.
- **Решение владельца:** `internal-frontend` на 127.0.0.1:7236 (membership 6936); history, matching и worker тоже на 127.0.0.1; `broadcastAddress` 127.0.0.1; `TEMPORAL_SERVICES=frontend,history,matching,worker,internal-frontend`. Наружу открыт только аутентифицированный frontend 7233. Без межузловых сертификатов.
- **Файлы в работе:** `services/temporal/config.yaml`, `services/temporal/entrypoint.sh`, `docker-compose.yml`, `docker-compose.full.yml`, `scripts/temporal/bootstrap-functions.ps1`, `tests/test_docker_startup_contracts.py`, `tests/test_temporal_bootstrap_inplace.py`, `tests/test_temporal_bootstrap_runtime.py`, новый `tests/test_temporal_single_container_entrypoint.py`, `tests/test_temporal_service_token_proof.py`.
- Ночной in-place mTLS overlay (`config/dynamic/entrypoint-inplace-mtls*`, `test_temporal_inplace_mtls_entrypoint.py`) владелец отверг, агент его удалил.
- **Осталось:**
  - проверить, что ни один контракт с точным набором env/mounts не ослаблен, только расширен;
  - прогнать тесты;
  - по возможности поднять Postgres и Temporal в docker с проектом `ue-r9-temporal`, после проверки сделать `down -v`;
  - решить судьбу `tests/fixtures/temporal_auth_proof/` (нужен ли он хоть одному оставшемуся тесту).
- **Ещё по тестам** (R6 #1/#2, подтверждено): в `test_temporal_bootstrap_inplace.py` тесты failure/timeout пустые. Обернуть вызов в try/catch, печатать `RESULT=ok|ERROR: <msg>` и `ELAPSED`, проверять конкретные сообщения. Тексты сообщений есть в отчёте полосы tq (вставлены ниже, в 3.7).

### 3.3 Workflow: sqlmap / DAST / chaos (наполовину)
- **Решение владельца по sqlmap: ОБА режима.**
  - Вернуть блокирующий анонимный скан всего OpenAPI с флагами как в `c3693dbed:.github/workflows/sqlmap.yml`. Любая инъекция валит сборку. Скан обязан доказать, что дошёл до конца: маркеры завершения, число целей совпадает с числом операций, нет предупреждений incomplete/timeout.
  - Сохранить доказательный скан `/api/v1/news` с сидом.
  - Отчёты хранить 90 дней.
  - Комментарий у sqlmap.yml:~213 «raw files retained» должен совпасть с поведением.
- **Файлы в работе:** `.github/workflows/sqlmap.yml` (не изменён), `scripts/quality/sqlmap_scan_gate.py`, `tests/test_sqlmap_scan_gate.py`. На Windows имя каталога `127.0.0.1:8000` недопустимо, агент переходил на `api.invalid`.
- **DAST:** WIP убрал `::add-mask::` для URL цели. Вернуть и потребовать это в `tests/test_dast_workflow_contract.py`. Исправить комментарий ZAP v0.10.0 → v0.13.0.
- **Chaos:** `scripts/quality/validate_chaos_resilience_junit.py` никто не вызывает. В ночной chaos-джобе добавить `--junitxml` и запуск валидатора.
- Каталог: после правок workflow обнови `quality/ci-check-catalog.json` и прогони `tests/test_ci_check_catalog.py`.

### 3.4 Frontend: Trusted Types (наполовину, подтверждённый баг продукта)
- **Баг:** production CSP `require-trusted-types-for 'script'` действует, политики `app dompurify-news goog#html`, default-политики нет. Markdown-новости пишут строку в `template.innerHTML` и `dangerouslySetInnerHTML`, поэтому в Chrome будет TypeError. Баг старый, был ещё до c3693dbed.
- **Файлы в работе:** `NewsDetailBody.tsx`, `SafeHtml.tsx`, `sanitizeArticleHtml.ts`, `utils/trustedTypes.ts` и тесты к ним.
- **Нужно:**
  - каждая запись в синк получает TrustedHTML от существующей политики, новые имена политик и default не добавлять, CSP не трогать;
  - Markdown не деградирует в plain text, если нет `setHTML`;
  - SSR-fallback после гидрации заменяется на rich-тело;
  - вернуть `normalizeLegacyText` и два удалённых теста.
- **Другие находки R4:**
  - #4: вернуть RFC-проверку PBKDF2 через код приложения. Ожидаемое значение вычислять в рантайме через `node:crypto`, не хранить hex-литералом.
  - #5: oracle wasm-fuzzer должен ловить `javascript:`/`data:` URL и теги iframe, object, embed.
- Прогнать vitest, eslint, `tsc --noEmit` и покрытие затронутых файлов.

### 3.5 Semgrep AUD-380 (работа ночного агента, не завершена)
- **Файлы:**
  - джоба `semgrep-sast` в `ci.yml`;
  - `scripts/quality/select_semgrep_rules.py` (уже на HEAD) и `semgrep_dispositions_gate.py` с тестом;
  - `quality/semgrep-dispositions.json` (пустой);
  - `.semgrep.yml`;
  - CODEOWNERS и policy-integrity списки;
  - публичный пин rules-checkout 363-й записью в `security-false-positive-dispositions.json`, его владелец **одобрил**;
  - счётчики 362→363 в AGENTS.md, ADR-047, README и тестах.
- 11 `nosemgrep` удалены: `app/auth/security.py` ×8, `telemetry.ts`, `NewsDetailBody.tsx`, `SafeHtml.tsx`. Совпадающих записей в исключениях пока нет.
- **Порядок:**
  1. Воспроизвести хостовый скан локально: образ `semgrep/semgrep:1.179.0@sha256:93963d92…`, rules на `16b9e6d45f10649f6a531ec4838ed9924372c3bc`, подмножество от селектора, флаги `--metrics off --oss-only --error --disable-nosem`, репозиторий смонтирован read-only, контейнер `ue-r9-semgrep-*`.
  2. Разобрать каждую находку. Настоящие проблемы исправить с тестами. Для оправданных завести точную запись: `check_id` без префикса пути, путь, sha256 строки, причина, egorribun, 2026-11-05, expires 2027-01-10.
  3. **Показать владельцу список исключений ДО коммита.**
- Кандидаты в оправданные: SHA-1 для HIBP с `usedforsecurity=False`, hostPID/hostNetwork у SPIRE agent, sink в `SafeHtml`, ws:// в dev-CSP, `HTTPSConnection` к фиксированному хосту.

### 3.6 Локальный хук Semgrep (решение владельца, не начато)
Перевести `semgrep-sast` в `.pre-commit-config.yaml` на тот же закреплённый набор правил и тот же скрипт точных исключений, что и в CI. Одна политика, никаких inline-комментариев. Это разблокирует 3.1 и 3.5. Файл `.pre-commit-config.yaml` теперь в CODEOWNERS.

### 3.7 Прочее в WIP
- **Готово и пригодно к коммиту после прогона:**
  - DAST: пин правил ZAP на `github.sha`, sparse checkout;
  - CODEOWNERS и policy-integrity;
  - `tests/test_symlink_privilege_probe_contract.py`, `test_jsx_opening_tag_linear.py`, `test_alembic_settings_isolation.py`;
  - `useChatWebSocket.aud334.test.tsx` и `services/ws-hub/pkg/hub/aud334_legacy_wire_correlation_test.go` (не запускались);
  - `scripts/k8s/` (офлайн-инструмент, не подключён);
  - `frontend/tests/e2e-live/aud178-reset-referer-csp.live.spec.ts`.
- **Chaos AUD-322:** правки `tests/chaos/test_resilience.py` и `tests/test_aud322_*` выглядят верными, но валидатор не подключён (см. 3.3).
- **`tests/test_verify_secrets_baseline.py`:** полоса tq вернула мутации `chart_identity`/`chart_metadata` для SPIRE-записи, файл прошёл 1083 из 1083. Коммитить вместе с блоком 363.
- **Сообщения для `test_temporal_bootstrap_inplace` (R6 #2):**
  - list-error → "Cannot inspect Temporal bootstrap volume inventory."
  - inspect-error → "Cannot inspect an existing Temporal bootstrap volume."
  - invalid-json, wrong-driver, wrong-name, wrong-scope → "An existing volume is not an unconfigured local volume."
  - array-options, bind → "An existing volume has unverified backing options."
  - failure → "Temporal bootstrap Docker command failed."
  - timeout → "...command timed out." (ELAPSED < 4)
- **ADR-047, текст дополнения для TruffleHog** (внести при ближайшем коммите ADR): «2026-11-05 (owner egorribun). GitHub Action trufflesecurity/trufflehog, по данным dependency graph AGPL-3.0, разрешён точной записью `pkg:github/trufflesecurity/trufflehog`; это не глобальное разрешение лицензии. Action работает только в CI (`.github/workflows/trufflehog.yml`) и не распространяется. `verify_dependency_review_scope.py` принимает ровно одну строку, привязанную к 40-hex пину из workflow, и fail-closed на всём остальном. Срок 2027-01-10; AGPL-3.0 не добавлять в глобальный allow-licenses.» Туда же: sqlmap в двух режимах, loopback-Temporal, единый локальный и хостовый гейт Semgrep.

## 4. Исторический список находок ревью на момент паузы

Перечень ниже — прежний triage, не текущий реестр и не утверждение, что эти
находки сейчас открыты или закрыты.
- ws-hub `RealIP` (ratelimit.go:177-186): пустой XFF-хоп даёт IP доверенного прокси, и rate-limit-ведра схлопываются.
- `startRoomReplay` (ws-hub client.go:814): мёртвый код.
- Scorecard: пол Vulnerabilities = 0, то есть по факту не гейтится. Поднять после разбора Dependabot (AUD-484). Полы Dangerous-Workflow и Token-Permissions = 10 не измерены, сверить с реальным прогоном.
- `reusable-live-realtime-visual.yml:131`: визуальный шаг идёт после упавшего realtime; дефолтный пароль `TestPass@2024x` в `authenticated-visual-audit.mjs`.
- `dast.yml:219`: ZAP checkout `ref: main`. Часть закрыта WIP-пином на `github.sha`.
- gunicorn пишет «Read-only file system: /home/app/.gunicorn». Задать HOME в writable tmp (чарт backend).
- `scripts/temporal/bootstrap-functions.ps1:1-2` и `namespace-init.sh:2`: устаревшие заголовки «review candidate».
- `check_caddy_govulncheck.py:122`: захардкожен stdlib v1.26.10.
- Остальное: в `R*-findings.md`. Low с низкой уверенностью сначала проверить.

## 5. Исторический порядок до релиза — superseded

Этот старый checklist сохранён как запись прежнего плана. Нижеописанные
последовательность коммитов, push, merge, release и cleanup не авторизованы
этим документом и не должны выполняться. Git действия выполняет только root;
никакие старые сведения о разрешении merge или cleanup не заменяют текущую
авторизацию.

1. Прежний план предлагал последовательность задач 3.6 → 3.1 → 3.2 → 3.3 → 3.4
   и отдельные коммиты через hooks. Эта последовательность отменена.
2. Для задачи 3.5 прежний план предлагал скан, разбор и передачу списка
   владельцу до коммита. Это не текущее поручение; пакет и решение владельца
   должны оцениваться по актуальному статусу выше.
3. Старый checklist предполагал push и hosted CI на source SHA. Push выполняет
   только root; required checks нужны для каждого нового source SHA. Прежние
   советы по перезапуску и Kind не заменяют актуальную диагностику.
4. Сверка аудита, rescue-bundle и разбор Dependabot были предложены как шаги
   после GREEN; это исторический план, а не разрешение выполнять Git или
   cleanup-операции.
5. Прежняя запись о merge #1343 и последующем release была привязана к
   состоянию того handoff. Она не даёт текущего разрешения на merge, тег,
   публикацию в GHCR или deploy.
6. Старое предложение удалить worktrees и audit-папки отозвано. Не удаляй и не
   перемещай их на основании этой записи.

## 6. Историческая запись решений владельца

Список ниже воспроизводит записи на момент прежнего handoff. Он не подтверждает
текущую область разрешений; используй актуальные AGENTS.md, ADR и явные текущие
решения владельца/root. Новые Semgrep dispositions и projected count выше не
одобрены.
- **2026-11-05:**
  - ревью тоже делает Haiku;
  - TruffleHog: точное исключение;
  - две новые identity (пин Semgrep rules, SHA-256 архива SPIRE 0.30.4) владелец **подтвердил**;
  - sqlmap: оба режима;
  - Temporal: loopback internal-frontend без сертификатов;
  - локальный Semgrep-хук: тот же гейт, что в CI.
- **2026-11-04:**
  - 4 xdist-воркера на шард, число шардов и таймауты не трогать, Contract Tests ≤10 мин;
  - AUD-313: запись владельца без подписи;
  - AUD-272: удалено (ADR-051);
  - заполненных БД нет, критерии апгрейда для AUD-275/327/348/350/393/433 сняты;
  - AUD-373: kind в CI;
  - AUD-429: ночью и обязательно в PR на main;
  - AUD-381: Nuclei валит на medium+, sqlmap на любую инъекцию с доказательством завершения, Scorecard по 6 ключевым проверкам (полы только растут), отчёты 90 дней;
  - AUD-380: блокирующая джоба и точные исключения, **список показать до коммита**;
  - AUD-245: пути, срок 2027-01-10 (валидатор допускает до 90 дней);
  - AUD-478: без replay (`cache.revoke` с ограниченным replay);
  - AUD-447: без чистки строк;
  - отдельные роли SpiceDB и Temporal, ежедневный CronJob retention, MinIO и ES внутри кластера;
  - продление двух Trivy-записей до 2027-01-10.
- **Ранее:**
  - один baseline миграций (ADR-051);
  - Squawk-исключение из 5 правил только для baseline;
  - go-jose/v3 только для caddy до 2027-01-10;
  - пароль ≥12 символов, zxcvbn ≥2;
  - SPIFFE mTLS обязателен в prod;
  - роль БД приложения не суперпользователь;
  - политики только ужесточаются.

## 7. Исторически записанные запреты

Актуальные ограничения задают AGENTS.md и текущие root-инструкции выше. Этот
перечень сохранён как прежний снимок и не расширяет их.
- Никаких `--no-verify`, force-push, admin bypass.
- Никаких `pragma: allowlist secret`, `type: ignore`, `nosemgrep`, skip, xfail, eslint-disable. `# noqa: S603  # причина` допустим.
- Не ослаблять гейты, пороги, обязательные проверки и полы покрытия. Не делать тест «мягче», чтобы он прошёл. Альтернативы в `assertRaisesRegex` тоже ослабление.
- Новые сущности для detect-secrets или Gitleaks только с согласия владельца. Перепривязки 1:1 разрешены.
- Не трогать тома `university_*`, не делать глобальный prune. Контейнеры называть `ue-r9-*` и удалять с `-v`.
- Не отправлять email пользователя в сервисы.
- Жёсткий срок **2026-11-13**. Если с 7–8.11 он под угрозой, заранее дай владельцу конкретный выбор.
