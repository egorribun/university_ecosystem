# Обновления зависимостей — сводка (2026-10-12)

База: `origin/egorribun` `04fdd84c2`. Только отчёт — ни одна команда обновления не выполнялась,
репозиторий не менялся. Версии и даты взяты из официальных реестров и release notes
(PyPI, npm, proxy.golang.org / vuln.go.dev, crates.io, Docker Hub / ghcr, GitHub Releases, GitHub Advisory DB).
Детали по каждому пакету, команды и breaking changes — в файлах `U_*.md` рядом.

| Экосистема | Patch/minor | Major | Security | Файл |
| --- | ---: | ---: | ---: | --- |
| Python | 20 | 13 | 4 advisory | [U_PY.md](U_PY.md) |
| npm | 32 | 12 | 1 (handlebars, 3 GHSA) | [U_NPM.md](U_NPM.md) |
| Go | 23 | 3 | 23 GO-advisory + Caddy | [U_GO.md](U_GO.md) |
| Rust/WASM | 9 | 8 | 2 (ammonia) | [U_RUST.md](U_RUST.md) |
| Образы, compose, Helm | 43 | 16 | 39 advisory в 11 пакетах | [U_IMG.md](U_IMG.md) |
| GitHub Actions, CI-инструменты, pre-commit | 31 | 12 | 43 | [U_CI.md](U_CI.md) |

## 1. Срочно: security-фиксы

| Что | Где | Сейчас → фикс | Примечание |
| --- | --- | --- | --- |
| Kyverno | CI CLI, `minversion` | 1.19.0 → 1.19.1 | 5 GHSA, включая critical |
| NATS | compose, CI | 2.10.25 / 2.12.6 → ≥ 2.12.12 (2.15.0 для CI) | до 14 GHSA, 4 high |
| Caddy | `services/caddy/Dockerfile` | 2.11.4 → 2.11.7 | закрывает уязвимые chi, klauspost/compress, cel-go в бинарнике; breaking: idle-таймауты 1 мин (WS/SSE), лимит заголовков 16 KiB — нужны `caddy validate` и тесты WS/SSE; убрать понижающие `--replace`, `x/net v0.60.0` оставить |
| Prometheus | observability | 3.10.0 → 3.15.0 | CVE-2026-42151 (утечка OAuth-секрета), XSS |
| helm, nuclei | CI | 3.17.0 → 3.22.0; 3.3.9 → 3.11.1 | 6 + 6 GHSA |
| urllib3 | `deploy.yml` smoke-пины (мимо `uv.lock`) | 2.7.0 → 2.8.0 | 3 CVE |
| Werkzeug | `uv.lock` | 3.1.8 → 3.1.9 | 1 CVE |
| rclone | backup | 1.75.1 → 1.75.2 | 10 GHSA; фикс младше cooldown — аварийное исключение |
| handlebars | `package-lock.json` (транзитивно) | 4.7.9 → 4.7.10 | 3 GHSA; cooldown до 2026-10-12 22:37Z |
| ammonia | `frontend/wasm-sanitizer` | → 4.2.3 | фиксы санитайзера; cooldown до 2026-10-18 |
| imgproxy | compose | 3.28.0 → 4.0.x | 4 GHSA, только через major |
| SeaweedFS | compose (S3) | 4.47 | GHSA-99q7 (high) без опубликованного фикса — следить |

## 2. Блокеры и связки

- **cryptography** заблокирован постоянным `exclude-newer-package` (cutoff 2026-08-01) — решение владельца.
- **botocore/aiobotocore** держит `aioboto3==15.5.0`.
- **ruff > 0.14.14** ломает гейт `no-python2-except`; AGENTS.md фиксирует 0.14.14.
- **TypeScript 7** — нет JS compiler API, `typescript-eslint` требует TS < 6.1. **picomatch 4** — boundary-адаптер привязан к 2.3.2.
- **vitest 5** — только вместе с `@storybook/addon-vitest` 10.6.1; `@tanstack/react-router` — вместе с `router-core`.
- **eslint-plugin-react / jsx-a11y** не поддерживают ESLint 10; конфликт скрыт `legacy-peer-deps`.
- **scrypt 0.12** ломает сборку `rust-crypto` (`ScryptParams::new`); **criterion 0.8** — `black_box` deprecated при clippy `-D warnings`.
- **wasm-pack / Rust / binaryen** меняют WASM — нужна регенерация provenance.

## 3. Рассинхроны и гигиена

- Go: директива `go 1.26.4` в go.mod против 1.26.9 в CI/Docker. Rust: 1.94.1 в `backend.Dockerfile` против 1.97.1 в CI/frontend; wasm-bindgen 0.2.114 и 0.2.129 в разных крейтах.
- Override `@opentelemetry/core` 2.8.0 отстаёт от `sdk-trace-*` 2.11.0.
- Semgrep: pre-commit rev v1.168.0, а запускается образ 1.113.0; mypy в pre-commit v1.15.0 ниже минимума pyproject (≥ 1.20.1).
- Устаревшие digest-пины: python, golang, rust, node, caddy, busybox, pgvector, valkey, redis. uv 0.11.28 → 0.11.33.
- Пины actions не на релизных тегах: `amannn/action-semantic-pull-request`, `taiki-e/install-action`, `dtolnay/rust-toolchain`; `actionlint` взят из открытого PR форка `Controla-ai` — заменить первым.
- Автоматика не видит inline-версии в скриптах, `with: version:`, `go install`, `npm -g`, образы в `run:`/`services:`; Dependabot покрывает 3 из 9 go.mod (Renovate — все); четыре постоянных исключения cooldown противоречат `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`.
- Bitnami: `bitnami/nats` без публичных тегов, `bitnami/redis` только `latest` — для chart revocation-store нужен проверяемый источник образа.

## 4. Major — отдельным решением

Python 13, npm 12, Go 3 (jwx v2→v4, gobreaker v1→v2, Go 1.27), Rust 8 (hmac/sha2/pbkdf2/scrypt RustCrypto, getrandom 0.4, criterion 0.8, cargo-fuzz, wasm-pack), образы 16 (Grafana 13, Tempo 3, Valkey 9, Redis 8, Elasticsearch 9, Node 26, imgproxy 4 и др.), CI 12 (k6 2.x, helm 4, osv-scanner 2, ruff 0.16, mypy ≥ 2.4 и др.). Breaking changes проверены для части позиций; для большинства мажоров образов changelog не разобран — см. «Не удалось проверить» в `U_IMG.md`.

## 5. Рекомендуемый порядок (когда правки будут разрешены)

1. Security-фиксы из раздела 1, начиная с Kyverno, NATS, Prometheus, helm/nuclei, urllib3, Werkzeug; Caddy 2.11.7 — с тестами WS/SSE.
2. Замена `actionlint` из форка и пинов actions на релизные теги.
3. Patch/minor, прошедшие cooldown, по экосистемам отдельными коммитами с полным прогоном гейтов; Windows-сборку WASM вести с `SKIP_WASM_BUILD=1` и восстановлением артефактов.
4. Выравнивание toolchain (`go`-директива, Rust в Dockerfile, wasm-bindgen) и digest-пинов.
5. Major — по одному, с отдельным планом миграции.

Ограничения: сборки, тесты, `pip-audit`/`cargo-audit`/`govulncheck` после обновлений не запускались; совместимость оценена по метаданным реестров, release notes и поиску по коду. Для проверки уязвимостей агенты отправляли в OSV/GitHub Advisory только публичные пары «пакет@версия».
