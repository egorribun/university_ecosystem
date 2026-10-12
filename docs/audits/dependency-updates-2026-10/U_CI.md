# U_CI

Снимок: origin/egorribun 04fdd84c2. Проверка: 2026-10-12 07:31 UTC. Cooldown 7 дней: релиз младше 2026-10-05 07:31 UTC помечен «рано». Рабочий репозиторий и снимок не менялись.

Итого: patch/minor 31 строка, major 12 строк, security-фиксов 43 (26 подтверждены GitHub Advisory API, 17 по release notes).

## Политика
- Cooldown 7 дней: Renovate `minimumReleaseAge: "7 days"` (renovate.json), Dependabot `cooldown.default-days: 7`. Security-alert PR без cooldown, но без automerge. Аварийный путь только по подтверждённому advisory (docs/DEPENDENCY_COOLDOWN_EMERGENCY.md).
- Пины: Actions полным SHA с комментарием `# тег`; Docker по sha256-digest (MOD-2026-01); CI-инструменты по URL с sha256; Python через uv.lock и hash-verified requirements. Toolchain: Python 3.14, Node 24, Go 1.26.9 (fuzz 1.27.2), ruff 0.14.14 (AGENTS.md §4, pyproject `<0.17`), mypy `<2.4` (pyproject:383).
- Не менять без отдельного решения: actionlint (5dc52e8 = PR #745 из форка, open), ruff 0.14.14, Rust/wasm-pack/binaryen (меняют WASM, нужна регенерация provenance), `uv lock --upgrade` (запрещено, только обычный `uv lock`).
- Renovate/Dependabot не покрывают: inline-версии в run-скриптах, `with: version:`, `go install …@vX`, `uv pip install sqlmap==`, `npm -g`, Docker-образы в `run:` и `services:` (customManagers нет). Эти пины обновляются вручную.

## Patch/minor — можно обновить
| Пакет | Где | Сейчас | → Версия | Дата | Cooldown | Security | Риск |
|---|---|---|---|---|---|---|---|
| anchore/sbom-action (+download-syft) | ci.yml:847, go-lint.yml:81, reusable-security-audit.yml:543, reusable-build-and-sign.yml | v0.24.2 | v0.24.3 | 2026-10-02 | OK, 10 д | нет | низкий |
| SonarSource/sonarqube-scan-action | sonar.yml | v8.2.2 | v8.3.0 | 2026-09-30 | OK, 12 д | GHSA <6.0.0, не затронуто | низкий |
| github/codeql-action (12 uses) | codeql.yml, ci.yml, dast.yml, checkov.yml, sbom.yml и др. | v4.38.1 | v4.38.2 | 2026-09-24 | OK, 18 д | нет | низкий (bundle 2.27.1) |
| chromaui/action | chromatic.yml:152 (skip: true) | v18.9.4 | v18.10.2 | 2026-10-02 | OK, 10 д | нет | низкий |
| trufflesecurity/trufflehog (action и CLI) | trufflehog.yml:48 | v3.97.5 | v3.97.9 | 2026-09-24 | OK, 18 д | нет | низкий |
| bridgecrewio/checkov-action | checkov.yml:71 | v12.3125.0 | v12.3129.0 | 2026-10-05 | на границе: 7 д 0 ч | нет | низкий; нет release notes |
| taiki-e/install-action (11 uses) | 10 workflows (wasm-pack), ci.yml:1759 (cargo-llvm-cov) | 54420ca6 (main, +1 к v2.82.7) | v2.87.24 | 2026-10-04 | OK, 8 д | нет | низкий; меняет дефолт «latest» |
| helm (CLI) | ci.yml:1293, deploy.yml:619 (HELM_VERSION), reusable-backend-tests.yml:141, reusable-helm-dependencies.yml:132, reusable-full-backend-mutation.yml ×4, reusable-security-audit.yml:311 | 3.17.0 | 3.22.0 | 2026-09-10 | OK, 32 д | 6 GHSA; кандидат 3.22.0 не затронут, вкл. high CVE-2025-53547 | средний |
| nuclei (CLI) | dast.yml:80 | 3.3.9 | 3.11.1 | 2026-08-08 | OK, 65 д | 6 GHSA (fix ≤3.10.0), вкл. high CVE-2026-76819 | средний: 3.11 требует подписи JS-шаблонов (своих нет) |
| kyverno (CLI) | ci.yml:2953, nightly-full-gate.yml:945 | 1.19.0 | 1.19.1 | 2026-09-10 | OK, 32 д | 3 по release notes: CVE-2026-39821, CVE-2026-56853, GHSA-5cjf-wwfg-pj4c | низкий |
| Node.js | release.yml:204; nightly-full-gate.yml ×4; manual-mutation-evidence.yml ×4 | 24.15.0 | 24.21.0 | 2026-09-07 | OK, 35 д | 24.17.0 security release (CVE-2026-48618) | низкий |
| nats-server (service image) | admin-smoke-monitoring.yml:92, reusable-backend-tests.yml:504, unauthenticated-routes-smoke.yml:67, visual-audit.yml:137 | 2.10.25-alpine | 2.15.0-alpine (тег не проверен) | 2026-09-17 | OK, 25 д | 14 GHSA (fix ≤2.15.0), вкл. high CVE-2026-27889 | средний: линия 2.10 → 2.15 |
| caddy (image) | admin-smoke-monitoring.yml:308, unauthenticated-routes-smoke.yml:250, visual-audit.yml:431 | 2.11.4-alpine (digest устарел) | 2.11.7-alpine | 2026-10-03 | OK, 9 д | 2.11.6: 11 пунктов Security fixes, GHSA-6365-7ppr-5r92 | средний: 2.11.6 breaking (заголовки 16 KiB, idle-таймаут 1 мин); CI-Caddyfile простой |
| mailpit (image, ghcr) | reusable-backend-tests.yml:392, docker-compose.live.yml:71 | v1.31.1 | v1.31.4 | 2026-10-03 | OK, 9 д | 1.31.2: фикс обработки вложений | низкий |
| seaweedfs (image, ghcr) | nightly-full-gate.yml:677, docker-compose*.yml | 4.47 | 4.48 | 2026-09-28 | OK, 14 д | 4.48: «bump vulnerable deps» | средний: manual review (Renovate, ADR-042) |
| toxiproxy (image, ghcr) | nightly-full-gate.yml:686, docker-compose.test.yml:41 | 2.9.0 | 2.12.0 | 2025-03-18 | OK | нет | низкий |
| stoplight/spectral (image) | contract-validation.yml:76, 94 | 6.15.0 | 6.17.0 | 2026-10-01 | OK, 11 д | нет | средний: новые правила |
| semgrep (hook image и rev) | .pre-commit-config.yaml:126, 130 | image 1.113.0; rev v1.168.0 | 1.179.0 | 2026-10-02 | OK, 10 д | нет | средний: --config auto, --error |
| hadolint | ci.yml:412 | 2.12.0 | 2.15.1 | 2026-07-31 | OK, 73 д | нет | низкий (новый sha256) |
| gitleaks (pre-commit и CLI) | .pre-commit-config.yaml:38 | v8.30.0 | v8.30.1 | 2026-03-21 | OK | нет | низкий |
| golangci-lint | go-lint.yml:48, reusable-go-tests.yml:1154 | v2.13.2 | v2.14.0 | 2026-09-24 | OK, 18 д | нет | средний: линтеры и конфиг |
| govulncheck | reusable-security-audit.yml:515, sbom.yml:321, 435 | v1.7.0 | v1.8.0 | 2026-09-08 | OK, 34 д | нет | низкий |
| squawk | ci.yml:934 | v2.44.0 | v2.67.0 | 2026-10-04 | OK, 8 д | нет | средний: правила ban-drop-* (DROP VIEW/FUNCTION/TYPE/DEFAULT, такие есть в alembic) |
| slsa-verifier | ci.yml:877 | 2.7.0 | 2.7.1 | 2025-06-27 | OK | нет | низкий |
| sqlmap | sqlmap.yml:60 | 1.10.8 | 1.10.9 | 2026-09-02 | OK, 40 д | нет | низкий (PyPI: авторы проекта sqlmap) |
| uv (CI) | pyproject.toml:451 (required-version) | 0.11.28 | 0.11.33 | 2026-07-28 | OK | нет | низкий: правка pyproject |
| renovatebot/pre-commit-hooks | .pre-commit-config.yaml:139 | 43.268.4 | 43.288.0 | 2026-07-29 | OK | нет | низкий |
| web-vitals (RUM-библиотека) | quality/cwv-field-policy.json:8, frontend | 6.1.1 | 6.2.2 | 2026-09-14 | OK | нет | средний: JSON и пакет обновлять вместе |
| go-mutesting (псевдоверсия) | reusable-go-tests.yml:481, 836 | 48d0401f00fb (2025-12-26) | 9ce5f731e321 (2026-10-02) | 2026-10-02 | OK, 10 д | нет | средний: нет релизов, нужен diff |
| nilaway (псевдоверсия) | nilaway.yml:36 | 8649a03c818a (2026-08-08) | acb8859b9031 (2026-09-18) | 2026-09-18 | OK, 24 д | нет | средний: новые находки |
| Rust toolchain (dtolnay, 11 мест) | admin-smoke-monitoring.yml:137, chromatic.yml:128, ci.yml:541, ci.yml:1735 и др. | 1.97.1 | 1.99.0 | 2026-10-01 (манифест) | OK, 11 д | нет (GHSA не покрывает rustc) | высокий: WASM-сборка; политика reproducibility, нужна регенерация provenance |

Рано (cooldown, не обновлять до даты):
- Actions: setup-node v7.1.0 (до 10-15), upload-artifact v7.0.2 (10-14), download-artifact v8.0.2 (10-14), setup-uv v10.3.0 (10-16), scorecard-action v2.5.0 (10-19), codeql v4.38.3 (10-15), taiki-e v2.87.25 (сегодня 14:49), v2.87.26–28 (10-13..10-19), chromaui v18.11.0 (сегодня 15:08), checkov v12.3130–12.3132 (10-13..10-18), trufflehog v3.98.0 (сегодня 17:39), v3.99.x (10-13..10-15).
- Tools: sqlmap 1.10.10 (сегодня 21:47), web-vitals 6.2.3 (сегодня 10:03), semgrep 1.180.0 (10-14), squawk 2.68.0 (10-15), uv 0.13.0 (10-16), ruff 0.17.0 (10-16, вне cap), nats 2.14.8 и 2.15.1 (10-16), mailpit 1.31.5 (10-18), govulncheck 1.9.0 (10-18), osv-scanner v2.7.0 (10-19), renovate hooks 44.x (10-16..10-19), mxab v0.74.0 повторный тег 2026-10-11 (10-18), dtolnay master (10-16).

## Major — отдельно
| Пакет | Где | Сейчас | Последний major | Дата | Breaking changes (кратко) | Затронутый код | Оценка |
|---|---|---|---|---|---|---|---|
| k6 | tests/performance/*.js; ci.yml:1998 | 0.54.0 | 2.3.0 (eligible; 2.x) | 2026-09-21 | v2: модуль go.k6.io/k6/v2; удалены `k6 login/pause/resume/scale/status`, `externally-controlled`, `loadimpact`, `k6/experimental/redis`, позиционный `k6 cloud`; HTTP API не стартует по умолчанию; web-vitals v5 | k6/http, k6/ws, k6/metrics, k6/data, constant-vus; удалённых API нет (grep) | средний: прогон |
| helm | 9 мест (3.17.0) | 3.17.0 → 3.22.0 (patch-линия) | 4.3.0 | 2026-09-09 | Helm 4: несовместимые флаги и вывод CLI и SDK; chart apiVersion v2 работает | upgrade --i, dependency build/update/list, template, lint --strict, status, rollback, uninstall | высокий: оставаться на 3.x |
| osv-scanner | sbom.yml:116, 125 | v1.9.2 (v1 закрыта) | v2.6.0 (2.7.0 рано) | 2026-09-14 | v2: удалены --verbosity=verbose, экспериментальные флаги, reporter API, пакет lockfile | `scan --recursive --format sarif --output` | средний |
| amannn/action-semantic-pull-request | semantic-pr.yml:23 | непомеченный main-коммит 2c9480cf (комментарий «v5.5.3») | v6.1.1 (48f256284b) | 2025-08-22 | v6.0.0: Node 24 и ESM | types, requireScope; входы есть в v6.1.1 | низкий; переход с коммита на релиз |
| wasm-pack | taiki-e (10 мест), frontend/scripts/build-wasm.mjs | 0.13.1 | 0.15.0 (0.x) | 2026-05-15 | 0.14: npm-обёртка (CVE-2026-23745, axios); 0.15: binary-install заменён, шаблон вендорен | WASM byte-exact provenance (frontend/WASM_SOURCE_PROVENANCE.json) | высокий: сначала проверить install-action |
| ruff | pyproject `<0.17`; .pre-commit rev v0.14.14; AGENTS.md §4 | 0.14.14 | 0.16.10 (0.17.0 рано и вне cap) | 2026-10-01 | 0.16.0: 413 правил по умолчанию (было 59), форматирование Markdown-кода по умолчанию; исправление регрессии except-скобок в 0.15.x в notes не подтверждено | pyproject [tool.ruff]; pre-commit ruff и ruff-format | высокий: политика — оставить 0.14.14 |
| shellcheck | ci.yml:434; scripts/**/*.sh | 0.10.0 | 0.11.0 (0.x) | 2025-08-04 | SC2015 срабатывает реже; SC3013 удалён | `-e SC2086 -e SC2001 -e SC2030 -e SC2031` | низкий |
| kubeconform | ci.yml:1324, 1336, 1344 | 0.6.7 | 0.8.0 (0.x) | 2026-06-04 | 0.7: jsonschema v6, невалидный JSON не ошибка; 0.8: duration через strfmt, фикс паники | -strict -summary -skip -schema-location | средний: валидация может измениться |
| trivy | reusable-build-and-sign.yml:119, reusable-security-audit.yml:322 (sha256) | 0.73.0 | 0.75.0 (0.x; 0.74.0 — 2026-08-14) | 2026-10-01 | 0.75: BREAKING — удалён getHostByName из шаблонов; 0.74: RapidFort, Java-лицензии | `trivy config --misconfig-scanners helm`; собственных шаблонов нет | средний: пересчитать sha256 и триаж находок |
| mxab/pre-commit-trivy | .pre-commit-config.yaml:146 (stage manual) | v0.18.0 | 0.74.0 (0.x) | 2026-09-03 | номера 0.72–0.74 совпадают с номерами trivy; есть также тег v0.74.0 (2026-10-11, рано) | hook manual-stage | низкий |
| binaryen (wasm-opt) | reusable-e2e-wasm-build.yml:64, reusable-frontend-tests.yml:204 | version_117 | version_133 | 2026-09-21 | нумерация не semver, 16 релизов; меняет вывод WASM | WASM provenance | высокий |
| mypy (pre-commit mirror) | .pre-commit-config.yaml:52 | v1.15.0 (ниже floor проекта 1.20.1) | 2.4.0 (линия 2.x) | 2026-10-01 | 2.0: --local-partial-types и --strict-bytes по умолчанию; --allow-redefinition работает иначе | pyproject `[tool.mypy] strict = true` | средний: 2.4 вне cap <2.4 (ADR-035); uv.lock = 2.3.1 |

## Расхождения пинов
- amannn/action-semantic-pull-request: SHA 2c9480cf — непомеченный коммит main (+16 к v6.1.1, 2026-07-01); комментарий «v5.5.3» неверен (semantic-pr.yml:23).
- taiki-e/install-action: SHA 54420ca6 — коммит main на 1 позже тега v2.82.7 (16b05812); комментарии — имена инструментов.
- dtolnay/rust-toolchain: SHA 02cb101e без версионных тегов, на 5 коммитов позади master (e2a55d2f, 2026-10-09); комментарии nightly/stable/pinned — не версии.
- actions/upload-artifact: SHA = v7.0.1, но в одном месте «v6.0.0» и в трёх «v7» (тег v7 указывает на другой коммит).
- anchore/sbom-action: SHA = v0.24.2, в ci.yml:847 комментарий «v0.24.0 — RZ-22-03».
- dast.yml (блок-комментарии): zaproxy «v0.10.0» и nuclei-action «v3.1.0»; в строках v0.13.0 и v3.1.1 (SHA строк совпадают с тегами).
- actionlint: 5dc52e8 — head PR rhysd/actionlint#745 из форка Controla-ai/actionlint (open); релиз v1.7.12 не содержит cache-mode.
- Semgrep: rev v1.168.0, но entry запускает образ 1.113.0 (2025-03); реально исполняется старая версия.
- mypy: pre-commit v1.15.0 ниже floor проекта (mypy>=1.20.1, pyproject:383); расхождение упомянуто в pyproject:187–204; uv.lock — 2.3.1.
- Python: AGENTS.md — 3.14; python-fuzz.yml:31 — 3.12.
- Digest-пины устарели: caddy:2.11.4-alpine (тег перестроен 2026-09-23), redis:7-alpine (2026-09-21), pgvector/pgvector:pg17 (2026-10-01); digest в ~30 местах, включая docker-compose*.yml.
- Одна версия задана во многих местах: helm 3.17.0 (9 мест), Node 24.15.0 (9 мест), Rust 1.97.1 (11 мест). Править одной командой и проверять git diff.

## Уже актуально
- Actions без изменений: checkout v7.0.1, setup-go v7.0.0, setup-python v7.0.0, actions/cache v6.1.0, github-script v9.0.0, attest-build-provenance v4.2.2, attest-sbom v4.1.0, dependency-review v5.0.0, trivy-action v0.36.0, azure/setup-helm v5.0.1, aws-actions/configure-aws-credentials v6.3.0, benchmark-action v1.22.2, codecov v7.1.1, docker/login v4.6.0, docker/build-push v7.4.0, docker/setup-buildx v4.4.1, cosign-installer v4.1.2, gitleaks-action v3.0.0, golangci-lint-action v9.3.0, jaxxstorm/action-install-gh-release v3.0.0, cspell-action v9.1.0, markdownlint-cli2-action v24.2.0, cargo-deny-action v2.1.1, pre-commit/action v3.0.1, zaproxy action-full-scan v0.13.0, zizmor-action v0.6.4, nuclei-action v3.1.1 (тег; release нет). GitHub Advisory DB (ecosystem actions, 56 записей): запинённые версии trivy-action, sonarqube, codeql и download-artifact не попадают в диапазоны уязвимостей.
- Текущий пин, но есть более новый релиз «рано»: download-artifact 8.0.1, upload-artifact 7.0.1, setup-node 7.0.0, setup-uv 10.2.0, scorecard 2.4.4.
- Tools: pre-commit 4.6.2, bandit 1.9.4, detect-secrets 1.5.0 (hash), pip-audit 2.10.1, cargo-llvm-cov 0.9.1, cargo-audit 0.22.2, @oasdiff-js/oasdiff-js 1.0.0, mypy 2.3.1 (uv.lock, в cap), Go 1.26.9 (последний 1.26.x) и 1.27.2 (fuzz), trivy 0.73.0 (GHSA только для 0.69.4), Python 3.14.8 и 3.12.15 (плавающие).
- Транзитивные (detect-secrets runner) без security-фиксов, не включены в список: PyYAML 6.0.3, requests 2.34.2, certifi 2026.7.22, idna 3.20, urllib3 2.8.0, charset-normalizer 3.5.1 (3.5.2 без security).

## Не удалось проверить
- kubectl: KUBECTL_VERSION и KUBECTL_SHA256 берутся из GitHub Variables (deploy.yml:446–447), в снимке не заданы.
- Версии, которые выбирает сам action (в workflow не зафиксированы): zizmor, gitleaks-action, checkov CLI, syft (anchore), cosign, codecov CLI, sonar-scanner, chromatic CLI, cspell, markdownlint-cli2, ZAP-образ zaproxy (плавающий), nuclei-templates (`-t cves/` и др., плавающие), «latest»-инструменты taiki-e.
- ghcr.io-образы mailpit, toxiproxy, seaweedfs: digest не проверен (Docker Hub API не отдаёт ghcr), версии по GitHub releases. Новые digest для caddy 2.11.7, nats 2.15.0, spectral 6.17.0, semgrep 1.179.0 не получены; наличие тегов nats:2.15.0-alpine и spectral 6.17.0 не проверено.
- Changelog не читался полностью: binaryen 118–133; golang/vuln v1.8.0 (нет release body); uv 0.11.33 и 0.13; nats 2.11–2.15; spectral 6.16–6.17; renovate 43.288.0; mypy 2.4 (читался только 2.0); golangci 2.14 (только список коммитов); kubeconform 0.8 (частично); trivy 0.74 (только заголовок); helm 4 (общий список, флаги построчно не сверены); checkov-action и chromaui v18.10.2 без release notes.
- Совместимость wasm-pack ≥0.14 с taiki-e install-action, binaryen 133 и Rust 1.99.0 с WASM provenance: требуется прогон CI, не выполнялся.
- GHSA-6365-7ppr-5r92 (caddy) и GHSA-5cjf-wwfg-pj4c (kyverno): 404 в GitHub Advisory API; учтены по release notes.
- Node и Rust: GHSA не покрывает Node core и rustc; учтён только security-релиз Node 24.17.0 по release notes.
- go-mutesting и nilaway (псевдоверсии): diff коммитов не анализировался.
- Playwright (версия из frontend lock) и базовые образы Dockerfile/docker-compose: вне пакета CI.

## Команды (не выполнены)
Выполнять в корне репозитория на отдельной ветке, после решения владельца. `<DIGEST>` получить через `docker buildx imagetools inspect <image>:<tag> --format '{{.Manifest.Digest}}'`.

```bash
# 1) GitHub Actions: SHA + комментарий тега (патч/минор)
sed -i 's|anchore/sbom-action@3ad7283483fc7af8ff2b4ea19663c2d5ca935e26 # v0.24.2|anchore/sbom-action@66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c # v0.24.3|g; s|anchore/sbom-action/download-syft@3ad7283483fc7af8ff2b4ea19663c2d5ca935e26 # v0.24.2|anchore/sbom-action/download-syft@66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c # v0.24.3|g' .github/workflows/*.yml
sed -i 's|SonarSource/sonarqube-scan-action@ba9859eae8dd6bd29e412f25ddbbef3d032000f4 # v8.2.2|SonarSource/sonarqube-scan-action@d209202bc7d53ff1cc128f7f907dac145c9d6ae9 # v8.3.0|g' .github/workflows/sonar.yml
sed -i 's|\(github/codeql-action/[a-z-]*\)@1c5b675653bb5c22dbe9b12b556ec555138e09fd # v4.38.1|\1@2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2|g' .github/workflows/*.yml
sed -i 's|chromaui/action@bb3b582719a93c1828c5e520e62992b2937d7889 # v18.9.4|chromaui/action@a18e9f57b71eb05f941848c0b927aab2ee644e3e # v18.10.2|g' .github/workflows/chromatic.yml
sed -i 's|trufflesecurity/trufflehog@f714bf454f350590f4a24c3ddb1aef02c35bf5b6 # v3.97.5|trufflesecurity/trufflehog@4dd8831c5f12599465d4d45c3c447b4018a34c85 # v3.97.9|g' .github/workflows/trufflehog.yml
sed -i 's|bridgecrewio/checkov-action@444c9db6fa75e2d9c19ebf1fde7322089be9009e # v12.3125.0|bridgecrewio/checkov-action@7b1bd992e2c40a3404e3511944aeb8d014703d9a # v12.3129.0|g' .github/workflows/checkov.yml
sed -i 's|taiki-e/install-action@54420ca6e3a4cab262aeabc1af4f52908ca28931 #|taiki-e/install-action@e407f7bafb71fd004bc5c2da3032e5470cbb6ef0 #|g' .github/workflows/*.yml

# 2) Версии в run-скриптах и with: (патч/минор)
sed -i 's|hadolint_version="2.12.0"|hadolint_version="2.15.1"|' .github/workflows/ci.yml   # затем hadolint_sha256 из asset digest релиза
sed -i 's|slsa_verifier_version="2.7.0"|slsa_verifier_version="2.7.1"|' .github/workflows/ci.yml   # затем slsa_verifier_sha256
sed -i 's/v1\.19\.0/v1.19.1/g' .github/workflows/ci.yml .github/workflows/nightly-full-gate.yml   # только kyverno; проверить git diff
sed -i 's/version: "3\.17\.0"/version: "3.22.0"/; s/version: v3\.17\.0/version: v3.22.0/; s/HELM_VERSION: v3\.17\.0/HELM_VERSION: v3.22.0/' .github/workflows/*.yml
sed -i 's/version: v2\.13\.2/version: v2.14.0/' .github/workflows/go-lint.yml .github/workflows/reusable-go-tests.yml
sed -i 's/version: v3\.3\.9/version: v3.11.1/' .github/workflows/dast.yml
sed -i 's/node-version: "24\.15\.0"/node-version: "24.21.0"/g; s/node-version: 24\.15\.0/node-version: 24.21.0/' .github/workflows/release.yml .github/workflows/nightly-full-gate.yml .github/workflows/manual-mutation-evidence.yml
sed -i 's|golang.org/x/vuln/cmd/govulncheck@v1.7.0|golang.org/x/vuln/cmd/govulncheck@v1.8.0|g' .github/workflows/reusable-security-audit.yml .github/workflows/sbom.yml
sed -i 's|go.uber.org/nilaway/cmd/nilaway@v0.0.0-20260808063849-8649a03c818a|go.uber.org/nilaway/cmd/nilaway@v0.0.0-20260918162853-acb8859b9031|' .github/workflows/nilaway.yml
sed -i 's|go-mutesting@v0.0.0-20251226130216-48d0401f00fb|go-mutesting@v0.0.0-20261002081621-9ce5f731e321|g' .github/workflows/reusable-go-tests.yml
sed -i 's|uv pip install "sqlmap==1.10.8"|uv pip install "sqlmap==1.10.9"|' .github/workflows/sqlmap.yml
sed -i 's|required-version = "==0.11.28"|required-version = "==0.11.33"|' pyproject.toml

# 3) pre-commit
sed -i 's|rev: v8.30.0|rev: v8.30.1|; s|rev: v1.168.0|rev: v1.179.0|' .pre-commit-config.yaml
sed -i 's|rev: 43.268.4 # ece9d8611e4e7da8cbcf7ea28039ec7928316032|rev: 43.288.0 # <SHA коммита тега 43.288.0>|' .pre-commit-config.yaml
sed -i 's|semgrep/semgrep:1.113.0@sha256:136c094630123be54d7f832217fd0a217d148a8bfea08c7c366ce17f94cfdb22|semgrep/semgrep:1.179.0@sha256:<DIGEST>|' .pre-commit-config.yaml

# 4) Образы (с <DIGEST>)
sed -i 's|caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648|caddy:2.11.7-alpine@sha256:<DIGEST>|g' .github/workflows/admin-smoke-monitoring.yml .github/workflows/unauthenticated-routes-smoke.yml .github/workflows/visual-audit.yml
sed -i 's|nats:2.10.25-alpine@sha256:3290c829aa05ddd4da12026783ccaff86f3fbc1f0551722908a934c293cd6228|nats:2.15.0-alpine@sha256:<DIGEST>|g' .github/workflows/admin-smoke-monitoring.yml .github/workflows/reusable-backend-tests.yml .github/workflows/unauthenticated-routes-smoke.yml .github/workflows/visual-audit.yml
sed -i 's|ghcr.io/axllent/mailpit:v1.31.1@sha256:98b916bd3c8d61f7633a52d3ea2f58d00620cb01ca57ab59edde68c347a95365|ghcr.io/axllent/mailpit:v1.31.4@sha256:<DIGEST>|g' .github/workflows/reusable-backend-tests.yml docker-compose.live.yml
sed -i 's|ghcr.io/shopify/toxiproxy:2.9.0@sha256:b44c283298cea49e2defaba1b3028783798346f2a926684e3a345fd8441af3b8|ghcr.io/shopify/toxiproxy:2.12.0@sha256:<DIGEST>|g' .github/workflows/nightly-full-gate.yml docker-compose.test.yml
sed -i 's|stoplight/spectral:6.15.0@sha256:b3d5a530f83c4a72df69e682c5ac928bc9821b5ca3c42529e81d926c80fa50ab|stoplight/spectral:6.17.0@sha256:<DIGEST>|g' .github/workflows/contract-validation.yml

# 5) npm / policy JSON
npm --prefix frontend install web-vitals@6.2.2 --save-exact
sed -i 's|"library_version": "6.1.1"|"library_version": "6.2.2"|' quality/cwv-field-policy.json

# 6) Проверки после правок
for h in actionlint gitleaks renovate-config-validator ruff; do pre-commit run "$h" --all-files; done
uv lock --check
git diff --stat
```

Ручные пункты, которые sed не покрывает: hadolint_sha256 (`gh api repos/hadolint/hadolint/releases/tags/v2.15.1 --jq '.assets[] | select(.name | test("Linux-x86_64$")) | .name + " " + (.digest // "")'`), slsa_verifier_sha256 (`gh api repos/slsa-framework/slsa-verifier/releases/tags/v2.7.1 --jq '.assets[] | select(.name=="slsa-verifier-linux-amd64") | .digest'`), SHA коммита тега renovate 43.288.0 (`gh api repos/renovatebot/pre-commit-hooks/git/ref/tags/43.288.0 --jq .object.sha`), Renovate уже покрывает `uses:`, pre-commit revs, docker-compose и Dockerfile.
