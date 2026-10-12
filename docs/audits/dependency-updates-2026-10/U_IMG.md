# U_IMG

База: `origin/egorribun` @ 04fdd84c2. Рабочий репозиторий не менялся. Срез: 2026-10-12 (UTC). Порог cooldown 7 дней: релиз старше 2026-10-05 12:00 UTC. Дата «обр.» означает дату публикации тега в реестре (Docker Hub `tag_last_pushed` или дата сборки из конфига образа), если релиз upstream не найден.

## Сводка
- patch/minor: 43 позиции; 39 проходят cooldown, 4 не проходят (рано или дата неизвестна).
- major: 16 позиций.
- security-фиксы: 11 пакетов, 39 advisories (35 в patch/minor, 4 в major).
- Критичные находки:
  1. Kyverno 1.19.0 (CLI в CI и `minversion` политик): 5 GHSA, включая critical (эскалация привилегий). Фикс: 1.19.1 (2026-09-10, cooldown ок).
  2. NATS 2.12.6 в compose: 9 GHSA (4 high). Фикс: 2.12.12 и выше; 2.12.15 или 2.15.0.
  3. rclone 1.75.1 (backup `s3ClientImage`): 10 GHSA, включая high. Фикс 1.75.2 опубликован 2026-10-09, cooldown не пройден (3 дня), нужна процедура аварийного исключения.
  4. imgproxy 3.28.0: 4 GHSA (3 high, 1 medium), опубликованы 2026-10-06. Фикс только в линии 4.0.x, поэтому нужен мажорный переход.
  5. Prometheus 3.10.0: CVE-2026-42151 (high, утечка OAuth client secret) и 2 XSS (medium). Фикс: 3.15.0.
  6. Redis 7.4.2 (test/sandbox): CVE-2025-49844 (critical, RCE). Фикс: 7.4.6, текущий 7.4.11.
  7. Valkey 8.1.9: GHSA-jcj7-v34w-v9vv (high, use-after-free). Фикс: 8.1.10.
  8. Caddy 2.11.4 (runtime): GHSA-6365-7ppr-5r92 (medium). Фикс: 2.11.5 и выше, текущий 2.11.7.
  9. Базовые образы отстают: backend runtime на Python 3.14.6 (текущий 3.14.8), frontend SSR на Node 24.19.0 (текущий 24.21.0), busybox в k8s из сборки 2024-09.
  10. Дрейф digest-пинов: `golang:1.26.9-alpine3.24` (тег перевыпущен 2026-10-10), `rust:1.94.1` (два разных digest в снимке, один не совпадает с текущим), `python:3.14-slim-bookworm` (два digest, оба отстают), `pgvector:pg17`, `valkey:8.1-alpine`, `distroless/static-debian12`, `caddy:2.11.4-alpine`, `node:24-alpine`, `busybox:1.37.0-musl`.
  11. Go-пины из Dockerfile младше cooldown: `golang 1.26.9` (релиз 2026-10-08) и `golang.org/x/net v0.60.0` (2026-10-08). Пин x/net закрывает 5 GO-advisories, фиксы для golang 1.26.9 не сверены. В снимке нет записи об исключении по `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`.
  12. Bitnami: публичный `docker.io/bitnami/nats` без тегов (0), `bitnami/redis` и `bitnami/redis-exporter` содержат только `latest` и артефакты подписи. Версионные теги лежат в `bitnamilegacy/*`. Digest для деплоя задаются переменными (`REQUIRED_SHA256_DIGEST`), в снимке их нет, поэтому доступность не проверяема.
  13. Внутренние расхождения: `curlimages/curl` в двух версиях (8.21.0 и 8.10.1 из 2024), syntax-директивы `docker/dockerfile:1.12` и `1.7` (2024), Rust 1.97.1 во фронтенде при 1.94.1 в бэкенде и тестах.
  14. SeaweedFS 4.47 (S3 во всех compose-стеках по ADR-042): в `seaweedfs/seaweedfs` опубликовано 25 advisories (9 critical). Текущая версия затронута GHSA-99q7-x53r-6j4g (high, IDOR в Filer TUS, диапазон `>= 4.39`, фикс не опубликован). Версия 4.48 ни один опубликованный advisory не закрывает.

## Политика
- Cooldown 7 дней: `renovate.json` (`minimumReleaseAge: 7 days` для docker-compose, dockerfile, pypi, npm, gomod, cargo и github-actions), Dependabot `cooldown.default-days: 7`. Исключение только по `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`: advisory, точный пакет, фиксированная версия, обычный PR с записью, ревью security. Команда только точечная (`uv lock --upgrade-package`), широкий `uv lock --upgrade` запрещён.
- Pin: образы закреплены по digest (MOD-2026-01, `pinDigests`), автомерж для Docker выключен; seaweedfs, spicedb, temporalio/server и temporalio/ui на ручном review. AGENTS п.6 и 9: базовые образы `python:3.14-slim-bookworm`, `node:24-alpine`, Go digest-pinned `golang:1.26.9-alpine` с `distroless/static-debian12`; Kyverno отклоняет пустые и `:latest` теги.
- uv жёстко закреплён `pyproject.toml:451` (`required-version = "==0.11.28"`), поэтому обновление uv связано с изменением pyproject.

## Patch/minor — можно обновить
| Пакет | Где | Сейчас | → Версия | Дата | Cooldown | Security | Риск |
|---|---|---|---|---|---|---|---|
| flagd (image) | docker-compose.full.yml:134; k8s/flagd/deployment.yaml:42 | v0.16.1 | v0.16.3 | 2026-09-10 | ок (32 д) | GHSA-4c5f-9mj4-m247 (high, Go stdlib в сборке); notes 0.16.3 содержат security-обновления deps; подтвердить | Низкий |
| curlimages/curl | full.yml:167 (8.21.0); full.yml:1479,1518; observability.yml:41,80; docker-compose.yml:943 (8.10.1) | 8.21.0 и 8.10.1 (2024) | 8.22.0 | 2026-09-02 | ок (40 д) | upstream CVE curl не сверены | Низкий; свести к одной версии |
| pgvector/pgvector:pg17 | docker-compose.yml:323,352; full.yml:405,440; prod.yml:160; sandbox.yml:16; test.yml:3; charts values.yaml:122 | PG 17.11, pin cf134a76 (обр. 2026-08-13) | digest refresh (ac08538c) | обр. 2026-10-01 | ок (11 д) | версия PG не меняется | Низкий |
| valkey/valkey:8.1-alpine | docker-compose.yml:393,475; full.yml:484,518 | 8.1.9, pin a0381758 | 8.1.10 | 2026-08-31 (релиз) | ок (42 д) | GHSA-jcj7-v34w-v9vv (high, UAF) закрыт | Средний |
| oliver006/redis_exporter | full.yml:562; observability.yml:245 | v1.88.0 | v1.93.0 | 2026-10-01 | ок (11 д) | 0 GHSA | Низкий |
| chrislusf/seaweedfs (репо seaweedfs/seaweedfs) | docker-compose.yml:770,802; full.yml:593,628; sandbox.yml:72 | 4.47 | 4.48 (фикса для текущей версии нет) | 2026-09-28 (тег) | ок (14 д) | GHSA-99q7-x53r-6j4g (high, IDOR в Filer TUS) затрагивает 4.47, в 4.48 не закрыт; всего 25 advisories, из них 9 critical | Высокий (ручной график по ADR-042; нужен отдельный план) |
| nats | docker-compose.yml:443; full.yml:682; sandbox.yml:54 | 2.12.6-alpine | 2.12.15 (обр. 2026-08-12) или 2.15.0 (2026-09-17) | обр. 2026-08-12; 2026-09-17 | ок (61 д / 25 д) | 9 GHSA (CVE-2026-58207, -58210, -58212, -58213 high; 5 medium); фиксы в 2.12.8–2.12.12, 2.15.0 включает все | Высокий |
| authzed/spicedb | docker-compose.yml:827,861; full.yml:1017,1054 | v1.51.0 | v1.56.2 (или 1.51.1 от 2026-04-14) | 2026-09-11 | ок (31 д) | 3 GHSA: CVE-2026-40091 (medium), CVE-2026-46668, CVE-2026-55866 (low) закрыты в 1.56.2 | Средний |
| temporalio/server, admin-tools | docker-compose.yml:596,635,690; full.yml:1111,1187,1263 | 1.30.2 | 1.30.7 | 2026-09-18 | ок (24 д) | 0 GHSA в репо temporal | Низкий |
| temporalio/ui | docker-compose.yml:742 | 2.48.1 | 2.55.0 (патч 2.48.4 от 2026-04-20) | 2026-10-01 | ок (11 д) | 0 GHSA | Низкий |
| grafana/grafana | full.yml:1349; observability.yml:159 | 12.3.6 | 12.3.11 (патч) или 12.4.12 (минор) | 2026-08-18 / 2026-09-29 | ок (55 / 13 д) | 28 GHSA в репо; по диапазонам ни одна не затрагивает 12.3.6 | Низкий-средний |
| prometheus/prometheus | full.yml:1400; observability.yml:205 | v3.10.0 | v3.15.0 | 2026-09-25 | ок (17 д) | CVE-2026-42151 (high), CVE-2026-40179, CVE-2026-44903 (medium) закрыты | Высокий |
| grafana/tempo | docker-compose.yml:921; full.yml:1450; observability.yml:17 | 2.10.3 | 2.10.8 | 2026-08-13 | ок (60 д) | GHSA-fx6q-qhch-hxgp (critical) относится к memcached в tempo-distributed, не к образу; проверить | Низкий |
| grafana/loki | full.yml:1498; observability.yml:61 | 3.7.1 | 3.7.8 | 2026-09-17 | ок (25 д) | 0 GHSA | Низкий |
| grafana/alloy | full.yml:1537; observability.yml:101 | v1.18.0 | v1.20.1 | 2026-09-28 | ок (14 д) | 0 GHSA | Низкий-средний (сверить config.alloy с notes 1.19 и 1.20) |
| grafana/pyroscope | docker-compose.yml:904; full.yml:1578; observability.yml:141 | 1.19.1 | 1.21.1 (1.x) | 2026-05-07 | ок (158 д) | 0 GHSA | Низкий |
| axllent/mailpit | docker-compose.live.yml:71 | v1.31.1 | v1.31.4 (v1.31.5 от 2026-10-11 рано) | 2026-10-03 | ок (9 д) | GHSA-2vgv-6hcp-mf43 (medium, фикс 1.31.2) | Низкий |
| edoburu/pgbouncer | docker-compose.prod.yml:182 | v1.25.2-p0 | v1.26.0-p0 | 2026-09-23 (релиз); обр. 2026-09-30 | ок (19 д) | GitHub-advisories нет; upstream не сверен | Низкий-средний (prod) |
| redis (library/redis) | docker-compose.test.yml:26; sandbox.yml:37 | 7.4.2-alpine | 7.4.11-alpine | обр. 2026-09-21 | ок (21 д) | CVE-2025-49844 (critical, RCE, фикс 7.4.6) и другие фиксы 7.4.x | Высокий (только test/sandbox) |
| shopify/toxiproxy | docker-compose.test.yml:41 | 2.9.0 | 2.12.0 | 2025-03-18 | ок | 0 GHSA | Низкий |
| rclone/rclone | charts/university-ecosystem/values.yaml:125 (backup) | 1.75.1 | 1.75.2 | 2026-10-09 | рано (3 д): аварийная процедура | 10 GHSA, затрагивают 1.75.1 (2 high, 6 medium, 2 low); фикс 1.75.2 | Высокий (сроки) |
| golang (Dockerfile base, alpine) | Dockerfile.protogen:2; services/caddy/Dockerfile:13; services/file-processor/Dockerfile:4,40; services/gateway/Dockerfile:4; services/ws-hub/Dockerfile:4 | 1.26.9, pin cdfd4fe2 (обр. 2026-10-08) | digest refresh на 1.26.9 (3082400e, обр. 2026-10-10). Dockerfile.test:30 (bookworm, d9c68c2c) актуален | релиз 2026-10-08 | рано (4 д): 1.26.9 ок с 2026-10-15, digest 3082400e ок с 2026-10-17; записи исключения нет | Go minor-релиз, фиксы не сверены | Средний |
| python (base) | backend.Dockerfile:10,65; Dockerfile.test:3 (pin 4ff4b92a = 3.14.6); containers/quality/Dockerfile.performance-rust:5 (23c59390 = 3.14.7) | 3.14.6 и 3.14.7 | 3.14.8 (digest 48b13b00) | релиз 2026-09-30; обр. 2026-10-06 | ок (12 д) | changelog CPython 3.14.7 и 3.14.8 не сверен | Средний-высокий (backend runtime отстаёт на 2 патча) |
| rust (toolchain) | backend.Dockerfile:5; Dockerfile.test:22-23 (5ae2d2ef = 1.94.1 от 2026-03-26); containers/quality/Dockerfile.performance-rust:8-9 (cf9dd0ec = 1.94.1); frontend.Dockerfile:15 (1.97.1) | 1.94.1 и 1.97.1 (разные версии в образах) | 1.99.0 (единая версия) | 2026-10-01 (канал stable); обр. 2026-10-06 | ок (11 д) | changelog не сверен | Средний (унификация) |
| node (base) | frontend.Dockerfile:10,175 | 24.19.0, pin d32cdf61 (обр. 2026-08-03) | 24.21.0 (обр. 2026-09-18) | 2026-09-07 | ок (35 д) | Node 24.20.0 и 24.21.0: changelog не сверен | Средний (SSR runtime) |
| caddy (builder и runtime) | services/caddy/Dockerfile:9 (CADDY_VERSION=2.11.4), :44 (caddy:2.11.4-alpine, digest 5f5c8640 отстаёт; тег перевыпущен 2026-09-23) | 2.11.4 | 2.11.7 | GitHub 2026-10-03; обр. 2026-10-06 | ок по релизу (9 д); обр. 6 д | GHSA-6365-7ppr-5r92 (medium, фикс 2.11.5) закрыт | Средний (security) |
| busybox (init-контейнер SPIRE) | k8s/spire/spire-agent.yaml:71 | 1.37.0-musl, pin fc6dddc4 (сборка 2024-09-26) | 1.38.0-musl | обр. 2026-09-23 | ок (19 д) | не сверено (busybox.net) | Низкий-средний |
| spiffe/spire-agent, spire-server | k8s/spire/spire-agent.yaml:94; k8s/spire/spire-server.yaml:105; .github/workflows/ci.yml:1363,1369 | 1.15.2 | 1.15.3 | 2026-08-21 | ок (52 д) | 3 GHSA в репо; ни одна не затрагивает 1.15.2 | Низкий |
| kyverno (CLI в CI и minversion) | .github/workflows/ci.yml:2950-2954; nightly-full-gate.yml:942-946 (CLI 1.19.0); k8s/kyverno/cluster-policies.yaml:206 | 1.19.0 | 1.19.1 | 2026-09-10 | ок (32 д) | 5 GHSA (1 critical, 4 high), все фиксы 1.19.1 | Высокий (контроллер в кластере не версионирован в репо) |
| docker/dockerfile (syntax) | frontend.Dockerfile:1; backend.Dockerfile:1; Dockerfile.test:1 (1.12); Dockerfile.protogen:1 (1.7) | 1.12 (обр. 2024-12-17) и 1.7 (обр. 2024-04-25) | 1.27.1 (1.28.0 рано) | обр. 2026-09-30 | ок (12 д) | GHSA buildkit относятся к демону, не к frontend-образу | Низкий |
| Gateway API bundle | scripts/kind_gateway_api.py:70 (GATEWAY_API_BUNDLE_VERSION) | v1.6.1 | v1.6.2 (v1.6.3 от 2026-10-06 рано) | 2026-09-03 | ок (39 д) | 0 GHSA | Низкий |
| bufbuild/buf | Dockerfile.protogen:14 (BUF_VERSION) | v1.72.0 | v1.73.0 | 2026-09-11 | ок (31 д) | 0 GHSA | Низкий |
| grpc-health-probe | services/file-processor/Dockerfile:41 | v0.4.51 | v0.4.57 (v0.4.58 и v0.4.59 рано) | 2026-09-05 | ок (37 д) | 0 GHSA | Низкий |
| WebAssembly/binaryen (wasm-opt) | frontend.Dockerfile:29-35 (version_117 + sha256) | version_117 | version_133 | 2026-09-21 | ок (21 д) | 0 GHSA | Средний: меняется WASM-вывод, нужны новый sha256 и WASM_SOURCE_PROVENANCE.json |
| xcaddy | services/caddy/Dockerfile:10 (XCADDY_VERSION), :26 | v0.4.5 | v0.4.7 | 2026-08-17 | ок (56 д) | 0 | Низкий |
| Go: google.golang.org/grpc | services/caddy/Dockerfile:32; services/file-processor/Dockerfile:54-58 (go get) | v1.83.2 | v1.84.0 | 2026-09-17 | ок (25 д) | пин 1.83.2 уже закрывает GHSA-2v4p-qf9q-27wj и GO-2026-6443; новых фиксов нет | Низкий |
| Go: go.opentelemetry.io/otel/sdk | services/caddy/Dockerfile:34,39-44 | v1.45.0 | v1.47.0 | 2026-10-02 | ок (10 д) | пин 1.45.0 закрывает GHSA-8wmf-6v46-5gfg и GO-2026-6505 | Низкий |
| Go: otel log и otlp exporters | services/caddy/Dockerfile:35-38 (v0.21.0), :40-41 (v1.45.0) | v0.21.0 и v1.45.0 | v0.23.0 (log) и v1.47.0 (otlp) | 2026-10-02 | ок (10 д) | пин закрывает GHSA-hjf4-fphr-2h65 и GO-2026-6615 (sdk/log), GHSA-w34q-cm8f-9c5x и GO-2026-6508 (otlploggrpc) | Низкий |
| Go: golang.org/x/crypto | services/caddy/Dockerfile:33 | v0.56.0 | v0.57.0 (v0.58.0 рано 2026-10-09) | 2026-09-08 | ок (34 д) | пин закрывает GO-2026-6354 и GO-2026-6355; GO-2026-5932 (openpgp, без фикса) актуален, только если openpgp в графе | Низкий |
| Go: github.com/spiffe/go-spiffe/v2 | services/file-processor/Dockerfile:54-58 (go get) | v2.7.0 | v2.8.2 (v2.9.0 на границе 2026-10-05) | 2026-09-18 | ок (24 д) | 0 | Низкий |
| Go: golang.org/x/net (держать пин) | services/caddy/Dockerfile:30; services/file-processor/Dockerfile:54-58 | v0.60.0 (2026-10-08) | держать (v0.61.0 от 2026-10-09 рано) | 2026-10-08 | рано (4 д): нужна запись исключения | пин закрывает GO-2026-6603, GO-2026-6610, GO-2026-6611, GO-2026-6612 (и ещё 1) | Высокий (держать, оформить) |
| elastic/elasticsearch (image) | docker-compose.full.yml:992; docker-compose.infra.yml:33 | 8.19.12 | 8.19.22 (8.19.23 рано 2026-10-06) | 2026-09-23 | ок (19 д) | GitHub-advisories нет; ESA не сверены | Средний |
| distroless/static-debian12 (digest) | services/gateway/Dockerfile:39; services/ws-hub/Dockerfile:39; services/file-processor/Dockerfile:67 | pin 20bc6c0b, текущий digest отличается | digest refresh (Debian 12) | дата н/д (gcr) | не проверяется: нет даты | OS-CVE не сверены | Низкий |

Итого: 43 строки, из них 4 не проходят cooldown или не имеют даты (rclone, golang 1.26.9, x/net v0.60.0 и distroless).

## Major — отдельно
| Пакет | Где | Сейчас | Последний major | Дата | Breaking changes (кратко) | Затронутый код | Оценка |
|---|---|---|---|---|---|---|---|
| imgproxy | docker-compose.yml:557-569; full.yml:1318-1328; .env.docker.example:58-60 | v3.28.0 (обр. 2025-03-31) | v4.0.17 (4.0.0 от 2026-05-13) | 2026-09-30 (ок) | Удалены deprecated env и CLI (IMGPROXY_CONCURRENCY, *_TIMEOUT, OPEN_TELEMETRY_*, UNSHARPENING_*, MAX_SVG_CHECK_BYTES, --keypath/--saltpath/--presets, gif_options); удалены histogram download/processing_duration; SVG DPI 72 переходит в 96; ETag и Last-Modified включены по умолчанию; сборка на Ubuntu 22.04 (libc 2.35) | Используемые env (ALLOWED_SOURCES, KEY, SALT, BASE_URL, LOG_LEVEL, USE_ETAG, REPORT_DOWNLOADING_ERRORS, DEVELOPMENT_ERRORS_MODE) не в списке удалённых; SVG-рендер и ETag сверить | Высокая: 4 GHSA (3 high, 1 medium) от 2026-10-06 затрагивают 3.x, фикс только в 4.0.x |
| grafana | full.yml:1349; observability.yml:159 | 12.3.6 | 13.2.3 | 2026-09-29 (13 д) | 13.1: удалён флаг logsPanelControls; 13.1 и 13.2: deprecations (notification provisioning endpoints, scripted dashboards выключены по умолчанию); полные notes 13.0 не сверены | Только provisioning datasources (infrastructure/observability/grafana/provisioning/datasources); дашбордов в репо нет | Низкая-средняя |
| tempo | docker-compose.yml:921; full.yml:1450; observability.yml:17 | 2.10.3 | 3.1.0 | 2026-09-29 (13 д) | 3.x: breaking конфигурация и новые defaults; Redis cache переписан (sentinel удалён); migration guide: legacy ingesters и overrides, v2 blocks, OpenCensus, localblocks | infrastructure/observability/tempo.yaml (distributor, ingester, compactor, storage, querier, metrics_generator, server); cache не используется; legacy-ключи проверить | Средняя |
| grafana/pyroscope | docker-compose.yml:904; full.yml:1578; observability.yml:141 | 1.19.1 | 2.3.1 (2.4.0 рано) | 2026-09-08 (ок) | 2.0.0: раздел Breaking changes в notes (Pyroscope OSS v2.0, Helm chart); полный список не сверен | Конфига в репо нет (только образ) | Низкая |
| valkey | docker-compose.yml:393,475; full.yml:484,518 | 8.1 | 9.2 (обр. 2026-09-21; 9.1.2 от 2026-09-01) | 2026-09-21 (обр.) | 9.x: changelog не сверен | Сервисы compose; конфиг-файлов valkey в репо нет | Средняя |
| redis | docker-compose.test.yml:26; sandbox.yml:37 | 7.4.x | 8.10.2 | 2026-09-17 | 8.x: changelog не сверен | Только test и sandbox | Низкая |
| elasticsearch | docker-compose.full.yml:992; docker-compose.infra.yml:33 | 8.19.x | 9.5.5 (9.4.8) | 2026-10-06 (рано 6 д) | 9.x: changelog не сверен | Использование ES в коде не проверено | Средняя; ждать cooldown |
| node | frontend.Dockerfile:10,175 | 24 (Active LTS, maintenance с 2026-10-20) | 26.11.1 (LTS с 2026-10-28) | 2026-10-07 (рано 5 д) | 26.x: changelog не сверен; график Node: nodejs/Release schedule.json | frontend SSR runtime | Высокая по срокам: планировать на LTS 26 |
| golang (toolchain) | все Dockerfile с golang, Dockerfile.test:30 | 1.26.9 | 1.27.2 (AGENTS: fuzz-джобы могут использовать 1.27.2) | 2026-10-08 (рано 4 д) | Go 1.27: changelog не сверен | services/* (caddy, file-processor, gateway, ws-hub), Dockerfile.protogen, Dockerfile.test | Средняя |
| distroless | services/gateway/Dockerfile:39; services/ws-hub/Dockerfile:39; services/file-processor/Dockerfile:67 | static-debian12 | static-debian13 (образ latest есть в gcr.io) | дата н/д | переход на Debian 13 base; changelog не сверен | Бинарники статические (CGO_ENABLED=0), влияние низкое | Низкая-средняя |
| bitnami/redis (chart) | charts/university-ecosystem/Chart.yaml (redis ~20.x; lock 20.13.4); charts/revocation-store/Chart.yaml (20.13.4) | 20.13.4 | 28.3.1 | 2026-09-30 (обр.) | мажоры 21–28: changelog чарта не сверен | Chart.yaml и Chart.lock, values.yaml (redis.*), .github/scripts/deploy-helm.sh, deploy.yml:1364-1365 | Высокая (+ риск доступности bitnami/redis) |
| bitnami/nats (chart) | charts/university-ecosystem/Chart.yaml (nats ~8.x; lock 8.5.4) | 8.5.4 | 9.0.28 | 2025-08-14 | мажор 9: changelog не сверен | Chart.yaml, values.yaml (nats.*), deploy.yml:1366 | Высокая (bitnami/nats без публичных тегов) |
| kindest/node | k8s/README.md:97; scripts/kind_gateway_api.py:173 (regex 1.33–1.36) | v1.36.4 | v1.37.0 (kind v0.33.0) | 2026-08-26 | k8s 1.37: changes не сверены; вне диапазона скрипта 1.33–1.36 | scripts/kind_gateway_api.py, k8s/README.md, тесты kind | Средняя (политика) |
| wasm-pack | frontend.Dockerfile:23 (`--version 0.13.1`) | 0.13.1 (2024-10-29) | 0.15.0 (0.x: минор ломающий) | 2026-05-15 | 0.14 и 0.15: changelog не сверен | WASM-сборка rust-crypto и wasm-sanitizer; WASM_SOURCE_PROVENANCE.json | Средняя |
| flagd | docker-compose.full.yml:134; k8s/flagd/deployment.yaml:42 | v0.16.1 | v0.17.0 (0.x) | 2026-09-25 | BREAKING: серверные sync-метрики переименованы (feature_flag.flagd.sync.* в ...sync.server.*) | В репо метрик flagd нет (grep); k8s/flagd/flags.json пустой | Низкая |
| uv | backend.Dockerfile:15; Dockerfile.test:37; pyproject.toml:451 | 0.11.28 (required-version ==0.11.28) | 0.12.23 (0.11.33 патч от 2026-07-28) | 2026-10-03 (ок 9 д) | 0.x минор: changelog не сверен | Блок: pyproject, uv.lock и CI (вне IMG) | Средняя |

## Уже актуально
- envoyproxy gateway-helm и gateway-crds-helm v1.9.2 (последний 1.9.x, GHSA не затрагивают); cert-manager v1.21.2 (ок).
- protoc-gen-go v1.36.12 и protoc-gen-go-grpc v1.6.2 (последние версии в proxy.golang.org); mholt/caddy-ratelimit v0.1.0 (релизов с 2024-08-28 нет).
- golang.org/x/text v0.42.0 (2026-09-08, ок; следующий v0.43.0 рано, 2026-10-09).
- APK-пины Caddy (APKINDEX): ca-certificates 20260909-r0, git 2.54.0-r0, apk-tools и libapk 3.0.8-r0, libcrypto3 и libssl3 3.5.9-r0, c-ares 1.34.8-r0, libcurl и curl 8.22.0-r0. Все последние в своей ветке; OSV: curl 8.22.0-r0 и c-ares 1.34.8-r0 закрывают ALPINE-CVE; у остальных известных уязвимостей нет.
- Bitnami chart constraints: redis 20.13.4 последний в ~20.x, nats 8.5.4 последний в ~8.x.
- kindest/node v1.36.4 (последний в диапазоне 1.33–1.36); pgvector PG 17.11 (версия без изменений).
- Не входят в список: rclone 1.75.1 (последний прошедший cooldown, но затронут advisories, см. таблицу patch/minor) и uv 0.11.28 (закреплён pyproject).

## Не удалось проверить
- Bitnami digest: `REQUIRED_SHA256_DIGEST` в values-staging.yaml и values.yaml, значения задаются env в deploy.yml:1364-1366, в снимке их нет. Публичные `bitnami/redis` и `bitnami/redis-exporter`: только `latest` и артефакты подписи (версионных тегов нет по фильтру). `bitnami/nats`: 0 тегов, при активном репозитории (last_updated 2025-08-14). Версии в `bitnamilegacy/*` (nats 2.11.8, redis 8.2.1). Доступность digest для деплоя не подтверждена.
- Elasticsearch: реестр docker.elastic.co отдаёт список не полностью (лимит 8000), версии взяты из GitHub; ESA-advisories недоступны, безопасность не проверена.
- SeaweedFS: релизы и advisories ведутся в `seaweedfs/seaweedfs` (старый путь `chrislusf/seaweedfs` в API пустой). Дата 4.48 взята по коммиту тега (2026-09-28). Фикс для GHSA-99q7 в опубликованных данных не найден: нужно перепроверить после среза.
- Changelog и security-статус не сверены для: CPython 3.14.7 и 3.14.8, Node 24.20.0 и 24.21.0, Go 1.26.9 и 1.27.2, Rust 1.99.0, busybox 1.38.0, pgbouncer 1.26.0, curl 8.22.0 (upstream CVE), temporal 1.30.7, Kyverno-контроллер (не версионирован в репо).
- Breaking changes: полностью не сверены для grafana 13, tempo 3, pyroscope 2, valkey 9, redis 8, elasticsearch 9, node 26, go 1.27, distroless debian13, bitnami-чарты 28 и 9, kubernetes 1.37, wasm-pack 0.14–0.15, uv 0.12. Указанные в таблице breaking частично взяты из notes; полного migration guide не открывал.
- OS-CVE базовых образов (Debian bookworm и trixie, Alpine) вне OSV, кроме APK-пинов Caddy.
- Docker Hub API отдаёт не более 1000 тегов на репозиторий. Для больших репозиториев (golang, python, node, rust, grafana, loki, tempo, rclone, redis, nats, bitnami) последние версии сверены с GitHub-релизами, а не только с Hub.
- Digest-пины, которые совпадают с manifest-ом linux/amd64 индекса (uv), считаются корректными по комментарию в Dockerfile.
- Моложе cooldown на момент среза: rclone 1.75.2 (2026-10-09) станет допустим с 2026-10-16; mailpit 1.31.5 (2026-10-11) с 2026-10-18; Go x/net v0.61.0 и x/text v0.43.0 (2026-10-09) с 2026-10-16.
- Фикстуры Kyverno (`ghcr.io/example/...`, digest из нулей и `aaaa`) тестовые, не проверялись. Образы CI (`aquasecurity/trivy-db`, `kindest/node` в тестах) вне охвата IMG.
- Прочее (вне обновлений): `charts/university-ecosystem/values.yaml` содержит `backup.minioEndpoint: http://minio:9000` и комментарии о MinIO, хотя ADR-042 переводит S3 на SeaweedFS.

## Команды (не выполнены)
Ни одна команда не запускалась. Выполнять в рабочем репозитории через обычный PR, после прохождения cooldown и записей исключений.
- Digest для тега (Docker Hub и ghcr): `docker buildx imagetools inspect --format "{{.Manifest.Digest}}" <repo>:<tag>`; подставить `@sha256:...` в строки image, FROM, COPY --from, values.yaml из таблицы.
- Helm: после правки версий в `charts/*/Chart.yaml`: `helm dependency update charts/university-ecosystem` и `helm dependency update charts/revocation-store` (пересоберёт Chart.lock).
- Go-пины (в копии снимка, с `GOFLAGS=-mod=mod`): `go list -m -u -json golang.org/x/net golang.org/x/crypto google.golang.org/grpc go.opentelemetry.io/otel/sdk`; затем обновить строки `--replace` и `go get` в `services/caddy/Dockerfile:30-41` и `services/file-processor/Dockerfile:54-58`.
- APK-пины (внутри `golang:1.26.9-alpine3.24`): `apk update && apk policy curl c-ares libcrypto3 libssl3 apk-tools git ca-certificates`.
- Kyverno CLI: в `.github/workflows/ci.yml:2950-2954` и `nightly-full-gate.yml:942-946` заменить `v1.19.0` на `v1.19.1`; при необходимости поднять `policies.kyverno.io/minversion` в `k8s/kyverno/cluster-policies.yaml:206`.
- BuildKit syntax: в `frontend.Dockerfile:1`, `backend.Dockerfile:1`, `Dockerfile.test:1`, `Dockerfile.protogen:1` заменить на `docker/dockerfile:1.27.1`.
- Binaryen: `curl -sL https://github.com/WebAssembly/binaryen/releases/download/version_133/binaryen-version_133-x86_64-linux.tar.gz | sha256sum`; заменить sha256, URL и проверку `version 117` в `frontend.Dockerfile:29-35`; затем пересобрать WASM и обновить `frontend/WASM_SOURCE_PROVENANCE.json`.
- Инструменты Dockerfile: `services/caddy/Dockerfile:9` (`CADDY_VERSION=2.11.7`), `:10` (`XCADDY_VERSION=v0.4.7`), `Dockerfile.protogen:14` (`BUF_VERSION=v1.73.0`), `services/file-processor/Dockerfile:41` (`GRPC_HEALTH_PROBE_VERSION=v0.4.57`).
- Compose и k8s: по каждой строке из таблицы, вида `curl -s https://hub.docker.com/v2/repositories/<ns>/<repo>/tags/<tag>` для проверки digest перед правкой.
- uv: только вместе с `pyproject.toml:451`, `uv.lock` и CI (вне IMG).
