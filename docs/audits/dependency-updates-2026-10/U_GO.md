# U_GO

## Политика
- Охват: 9 go.mod (корень, gen/go, services/cmd/uni-cli, services/file-processor, services/gateway, services/ws-hub, services/pkg/logging, services/pkg/spicedb, services/pkg/spiffe), go.work (9 модулей в use), директивы `go 1.26.4`, services/caddy/Dockerfile (Caddy 2.11.4, xcaddy v0.4.5, caddy-ratelimit v0.1.0, --replace). Снимок 04fdd84c2 не менялся; `go list`/`go mod` выполнялись в копии tmp\GO. Расчёт на 2026-10-12 07:40Z: cooldown 7 дней, релиз проходит, если вышел не позже 2026-10-05 07:40Z.
- Cooldown: renovate.json — minimumReleaseAge "7 days" для gomod patch (автомерж по выходным), gomod minor/major (ручной review) и golang-тулчейна (ручной review). Dependabot gomod (cooldown 7 дней) покрывает только ws-hub, gateway, file-processor; uni-cli, pkg/*, gen/go и корень ведёт только Renovate.
- Security: vulnerabilityAlerts — minimumReleaseAge null, PR сразу, automerge=false, метка manual-cooldown-override-required. Аварийный путь — docs/DEPENDENCY_COOLDOWN_EMERGENCY.md (запись, security-ревьюер; команда описана только для uv). Все security-фиксы ниже уже прошли cooldown, аварийный путь не нужен. Go-исключений в security/audit-allowlist.yaml нет.
- Pin: go 1.26.4 — минимум (AGENTS: 1.26.4+, CI и Docker 1.26.9, go-fuzz 1.27.2). Caddy/xcaddy — ARG в Dockerfile; транзитивные пины — --replace, но они не покрывают chi, klauspost и cel-go (см. таблицу). Major и Caddy 2.11.6+ (breaking) — только отдельной задачей с тестами.

## Patch/minor — можно обновить
Всего 23 строки: 16 Go-зависимостей с cooldown OK или «рано» (9 прямых OK, 7 прямых «рано»), 4 транзитивных с security-фиксом, Go-тулчейн, 2 Caddy-пина. OK = cooldown пройден.

| Пакет | Где | Сейчас | → Версия | Дата | Cooldown | Security | Риск |
|---|---|---|---|---|---|---|---|
| go.opentelemetry.io/otel | file-processor, gateway, ws-hub (gen/go, pkg/spiffe — indirect v1.45.0) | v1.46.0 | v1.47.0 | 2026-10-02 | OK (10 дн.) | нет | средний: minor OTel, трейсинг всех сервисов |
| go.opentelemetry.io/otel/sdk | file-processor, gateway, ws-hub | v1.46.0 | v1.47.0 | 2026-10-02 | OK (10 дн.) | нет | средний |
| go.opentelemetry.io/otel/trace | gateway, ws-hub | v1.46.0 | v1.47.0 | 2026-10-02 | OK (10 дн.) | нет | средний |
| go.opentelemetry.io/otel/exporters/otlp/otlptrace | ws-hub | v1.46.0 | v1.47.0 | 2026-10-02 | OK (10 дн.) | нет | средний |
| go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc | file-processor, gateway, ws-hub | v1.46.0 | v1.47.0 | 2026-10-02 | OK (10 дн.) | нет | средний |
| go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp | file-processor, ws-hub | v0.71.0 | v0.72.0 | 2026-10-02 | OK (10 дн.) | нет | низкий (требует otel 1.47) |
| go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc | file-processor | v0.71.0 | v0.72.0 | 2026-10-02 | OK (10 дн.) | нет | низкий |
| go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin | gateway | v0.71.0 | v0.72.0 | 2026-10-02 | OK (10 дн.) | нет | низкий |
| google.golang.org/grpc | gen/go, file-processor, gateway, pkg/spiffe | v1.83.2 | v1.84.0 | 2026-09-17 | OK (25 дн.) | нового нет: GO-2026-6443 не затрагивает 1.83.2 (проверено по диапазонам) | средний: minor gRPC, прогнать gRPC-тесты |
| github.com/getsentry/sentry-go (+ /gin) | file-processor, gateway, ws-hub | v0.49.0 | v0.50.0 | 2026-10-08 | рано (до 2026-10-15) | нет | средний: v0.x minor, возможны breaking |
| github.com/prometheus/client_golang | file-processor, gateway, ws-hub | v1.24.1 | v1.25.0 | 2026-10-08 | рано (до 2026-10-15) | нет | низкий |
| github.com/redis/go-redis/v9 | cmd/uni-cli, file-processor, gateway, ws-hub | v9.22.0 | v9.23.0 | 2026-10-05 14:51Z | рано (до 2026-10-12 14:51Z) | нет | низкий-средний |
| github.com/redis/go-redis/extra/redisprometheus/v9 | gateway | v9.22.0 | v9.23.0 | 2026-10-05 14:51Z | рано (до 2026-10-12 14:51Z) | нет | низкий |
| github.com/spiffe/go-spiffe/v2 | gateway, pkg/spiffe | v2.8.2 | v2.9.0 | 2026-10-05 18:18Z | рано (до 2026-10-12 18:18Z) | нет | средний: контур SPIFFE/mTLS |
| github.com/alicebob/miniredis/v2 | gateway, ws-hub (только тесты) | v2.39.0 | v2.40.0 | 2026-10-10 | рано (до 2026-10-17) | нет | низкий |
| golang.org/x/image | file-processor | v0.46.0 | v0.47.0 | 2026-10-09 | рано (до 2026-10-16) | нет | низкий |
| github.com/google/cel-go (транзитивный) | file-processor (граф, go mod why: не импортируется); Caddy-бинарник (импорт: caddyhttp expression matcher, caddy-ratelimit) | v0.26.1 (services), v0.28.1 (Caddy) | v0.32.0 (в Caddy 2.11.7 — cel.dev/cel-go v0.32.0) | 2026-08-19 | OK (54 дн.) | GO-2026-6094, GHSA-gcjh-h69q-9w9g (затронуты 0.22.0–0.28.1, fix 0.30.0); в services тянет go-grpc-middleware/v2 v2.3.4 | services: низкий (не в сборке); Caddy: средний (импортируется) |
| github.com/yuin/goldmark (транзитивный) | ws-hub (через go.uber.org/mock v0.6.0), file-processor (граф) | v1.4.13 | v1.8.6 | 2026-09-03 | OK (39 дн.) | GO-2026-5320, CVE-2026-5160, GHSA-c97m-vxhj-p7j6 (XSS, fix 1.7.17) | низкий (не в сборке); major v2.1.6 не брать |
| github.com/go-chi/chi/v5 (транзитивный, бинарник Caddy) | services/caddy: Caddy 2.11.4 (импорт: caddypki/acmeserver) | v5.2.5 | v5.3.2 (уже требует Caddy 2.11.7; минимум 5.3.0) | 2026-05-22 (v5.3.0) | OK (143 дн.) | GO-2026-5774, GO-2026-5775, GO-2026-5777 (GHSA-3fxj-6jh8-hvhx, GHSA-9g5q-2w5x-hmxf, GHSA-rjr7-jggh-pgcp; IP-spoofing в RealIP) | средний: не закрыт --replace; достижимость RealIP не проверена |
| github.com/klauspost/compress (транзитивный, бинарник Caddy) | services/caddy (импорт gzip/zstd) | v1.18.6 | v1.20.1 (требование 2.11.7; минимум 1.18.7) | 2026-06-30 (v1.18.7) | OK (104 дн.) | GO-2026-5841, GHSA-259r-337f-4rfw (OOB read в compress/s2) | низкий: пакет s2 в бинарник не входит |
| Go-тулчейн: директива go (9 go.mod, go.work); CI и Docker уже 1.26.9 | все модули | go 1.26.4 | go1.26.9 | 2026-10-02 | OK (10 дн.) | GO-2026-4970, 5026, 5856, 5942, 5972, 6088, 6089, 6090, 6091, 6179, 6180, 6218, 6603, 6610, 6611, 6612, 6617 (stdlib/toolchain, фиксы в 1.26.5–1.26.9) | низкий: тот же минор; локальный go1.26.5 отстаёт |
| github.com/caddyserver/caddy/v2 (ARG CADDY_VERSION) | services/caddy/Dockerfile (runtime FROM caddy:2.11.4-alpine) | 2.11.4 | 2.11.7 | 2026-10-03 | OK (9 дн.) | новых GO-ID нет (GO-2026-6512 уже в 2.11.4); notes 2.11.6: 11 пунктов безопасности (вкл. GHSA-6365-7ppr-5r92) | ВЫСОКИЙ: breaking 2.11.6 — idle-таймауты чтения/записи 1 мин (WS, SSE), лимит заголовков 16 KiB, заголовки с `.` отбрасываются, строже валидация конфига, /load возвращает 400, method в верхнем регистре, client_auth не наследуется; 2.11.7 исправляет регрессии 2.11.6. Нужны caddy validate и тесты ws/SSE |
| github.com/caddyserver/xcaddy (ARG XCADDY_VERSION) | services/caddy/Dockerfile | v0.4.5 | v0.4.7 | 2026-08-17 | OK (56 дн.) | нет | низкий (build-tool) |

## Major — отдельно
| Пакет | Где | Сейчас | Последний major | Дата | Breaking changes (кратко) | Затронутый код | Оценка |
|---|---|---|---|---|---|---|---|
| github.com/lestrrat-go/jwx/v2 | ws-hub | v2.1.7 | v4.5.0 (путь /v4; v3.3.0 — тоже 2026-09-08) | 2026-09-08 | v3: jwk.Cache переписан на httprc/v3. v4: jwk.Fetch и jwk.Cache удалены из core, их заменяет github.com/jwx-go/jwkfetch/v4 (NewCache(ctx, httprc.NewClient()), Register(ctx, url, jwkfetch.WithMinInterval(...)), Lookup(ctx, url)); Register/Unregister возвращают error; RegisterProbeField/RegisterCustomField — generic. Источник: MIGRATION.md и Changes-v4.md репозитория lestrrat-go/jwx | services/ws-hub/pkg/hub/hub.go: импорт jwx/v2/jwk (22), поле *jwk.Cache (153), registerJWKSFunc (254), jwk.NewCache и jwk.WithMinRefreshInterval (546–548); 3 тестовых файла (11 ссылок) | средняя: переписать JWKS-кэш и тесты; security-фиксов для текущей версии нет; отдельная задача |
| github.com/sony/gobreaker | ws-hub | v1.0.0 | /v2 v2.4.0 | 2026-01-01 | Путь github.com/sony/gobreaker/v2; дженерики: `NewCircuitBreaker[T any]` (аргумент `Settings`, результат `*CircuitBreaker[T]`), Execute(func() (T, error)) (T, error). Settings, Counts, ReadyToTrip без изменений (README v2) | services/ws-hub/pkg/hub/auth_client.go: импорт (18), поле *gobreaker.CircuitBreaker (82), NewCircuitBreaker (114), Execute (312); тестов нет | низкая: путь /v2 и параметр [any] |
| Go-тулчейн: go1.27.x | все go.mod, go.work; go-fuzz в CI (1.27.2) | go 1.26.4 (CI 1.26.9) | go1.27.2 | 2026-10-02 | go.dev/doc/go1.27: go test — vet stdversion по умолчанию; GODEBUG-настройки с удалёнными значениями валят сборку; net/http: HTTP/1 Response.Body дренируется при close (влияет на reuse соединений), HTTP/2 сервер учитывает RFC 9218; encoding/json на v2 (тексты ошибок); compress/flate — другой вывод (gzip, zip, png); asynctimerchan удалён, таймер-каналы всегда небуферизованные; go tool trace слушает только localhost | go vet и go test по модулям; таймеры в ws-hub и gateway; net/http-прокси в gateway | средняя-высокая: отдельная миграция; сейчас не предлагается (основной тулчейн 1.26.9) |

## Уже актуально
- Без новой версии в своей major (по go list -u и proxy): gin v1.12.0, gin-contrib/cors v1.7.9, redis_rate/v10 v10.0.1, jwt/v5 v5.3.1, google/uuid v1.6.0, gorilla/websocket v1.5.3, graphql-go v1.10.3, go-grpc-middleware/v2 v2.3.4, go-grpc-prometheus v1.2.0, hashicorp/golang-lru/v2 v2.0.7, minio-go/v7 v7.3.0, nats.go v1.54.0, pact-go/v2 v2.8.0, quic-go v0.63.0, webtransport-go v0.13.0, spf13/cobra v1.10.2, spf13/viper v1.21.0, stretchr/testify v1.12.1, testcontainers-go v0.44.0 (+ modules/nats, modules/redis v0.44.0), zsais/go-gin-prometheus v1.0.3, go.temporal.io/api v1.63.6, go.temporal.io/sdk v1.49.0, go.uber.org/goleak v1.3.0, google.golang.org/protobuf v1.36.12, golang.org/x/time v0.16.0; Caddy-плагин mholt/caddy-ratelimit v0.1.0 (новее на proxy нет).
- С major, но в своей major актуально: jwx/v2 v2.1.7, gobreaker v1.0.0 (см. Major).

## Не удалось проверить
- Changelog минорных версий (otel 1.47, contrib 0.72, grpc 1.84, sentry-go 0.50, client_golang 1.25, go-redis 9.23, go-spiffe 2.9, x/image 0.47, miniredis 2.40, cel-go 0.32, goldmark 1.8.6, chi 5.3, klauspost 1.18.7) — не читались; риск оценён по semver и объёму изменений.
- Caddy 2.11.5 — тег есть (proxy, 2026-09-30), GitHub Release отсутствует (404); notes не читались.
- Достижимость chi.RealIP (GO-2026-5774/5775/5777) в caddypki/acmeserver — не проверена (исходники Caddy не выгружались).
- Сборка не выполнялась: go mod tidy и go list -deps проверены во временных модулях (повтор xcaddy go.mod с теми же --replace и с Caddy 2.11.7); govulncheck (символьный) не запускался; совместимость caddy-ratelimit v0.1.0 с Caddy 2.11.x не скомпилирована.
- Digest образа caddy:2.11.7-alpine (runtime FROM) не получен — нужен реестр.
- GHSA, кроме проверенных через per-ID записи vuln.go.dev, поштучно не запрашивались.
- Без фикса и не учитываются как security-фикс: GO-2026-5781 и GO-2026-6115 (rsc.io/pdf v0.1.1 — ни одна сборка модуль не использует, go mod why); GO-2026-5932 (x/crypto/openpgp — пакет не импортируется). GO-2026-4923 (go.etcd.io/bbolt) — WITHDRAWN.
- GO-2026-6443 (grpc): по полю fixed в индексе выглядит затрагивающим 1.83.2, но по per-ID диапазонам 1.83.x закрыт версией 1.83.2 — не учитывается.
- Транзитивные модули без security-фиксов не перечислялись (по заданию).

## Команды (не выполнены)
```bash
# 0. go-директива и тулчейн (9 модулей + go.work), затем tidy
for d in . gen/go services/cmd/uni-cli services/file-processor services/gateway services/pkg/logging services/pkg/spicedb services/pkg/spiffe services/ws-hub; do
  (cd "$d" && GOWORK=off go mod edit -go=1.26.9 && GOWORK=off go mod tidy)
done
go work edit -go=1.26.9

# 1. OpenTelemetry и gRPC (cooldown пройден)
(cd services/ws-hub && GOWORK=off go get go.opentelemetry.io/otel@v1.47.0 go.opentelemetry.io/otel/sdk@v1.47.0 go.opentelemetry.io/otel/trace@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc@v1.47.0 go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp@v0.72.0 && GOWORK=off go mod tidy)
(cd services/gateway && GOWORK=off go get go.opentelemetry.io/otel@v1.47.0 go.opentelemetry.io/otel/sdk@v1.47.0 go.opentelemetry.io/otel/trace@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc@v1.47.0 go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin@v0.72.0 google.golang.org/grpc@v1.84.0 && GOWORK=off go mod tidy)
(cd services/file-processor && GOWORK=off go get go.opentelemetry.io/otel@v1.47.0 go.opentelemetry.io/otel/sdk@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc@v1.47.0 go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc@v0.72.0 go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp@v0.72.0 google.golang.org/grpc@v1.84.0 && GOWORK=off go mod tidy)
(cd gen/go && GOWORK=off go get google.golang.org/grpc@v1.84.0 && GOWORK=off go mod tidy)
(cd services/pkg/spiffe && GOWORK=off go get google.golang.org/grpc@v1.84.0 && GOWORK=off go mod tidy)

# 2. Транзитивные security-фиксы (cooldown пройден)
(cd services/file-processor && GOWORK=off go get github.com/google/cel-go@v0.32.0 github.com/yuin/goldmark@v1.8.6 && GOWORK=off go mod tidy)
(cd services/ws-hub && GOWORK=off go get github.com/yuin/goldmark@v1.8.6 && GOWORK=off go mod tidy)

# 3. Только после даты cooldown (сейчас «рано»):
#   github.com/redis/go-redis/v9 и .../extra/redisprometheus/v9 @v9.23.0 — с 2026-10-12 14:51Z (ws-hub, file-processor, gateway, cmd/uni-cli)
#   github.com/spiffe/go-spiffe/v2 @v2.9.0 — с 2026-10-12 18:18Z (gateway, pkg/spiffe)
#   github.com/getsentry/sentry-go и sentry-go/gin @v0.50.0; github.com/prometheus/client_golang @v1.25.0 — с 2026-10-15
#   golang.org/x/image @v0.47.0 — с 2026-10-16; github.com/alicebob/miniredis/v2 @v2.40.0 — с 2026-10-17

# 4. Caddy: services/caddy/Dockerfile — правки вручную
#   ARG CADDY_VERSION=2.11.7 ; ARG XCADDY_VERSION=v0.4.7
#   runtime: FROM caddy:2.11.7-alpine@sha256:<digest из реестра>
#   оставить   --replace golang.org/x/net=golang.org/x/net@v0.60.0   (2.11.7 требует v0.59.0; v0.60.0 закрывает GO-2026-6603/6610/6611/6612/6617)
#   удалить    --replace golang.org/x/crypto=...@v0.56.0 и все go.opentelemetry.io/otel/* --replace (v1.45.0 / v0.21.0): понижают версии относительно требований 2.11.7 (x/crypto v0.57.0, otel v1.46.0, otlp/log v0.22.0)
#   grpc@v1.83.2 и text@v0.42.0 можно оставить (совпадают с требованиями 2.11.7)
#   chi, klauspost, cel-go отдельных --replace не требуют (2.11.7: chi v5.3.2, klauspost v1.20.1, cel.dev/cel-go v0.32.0)
docker build -t caddy-edge:2.11.7 services/caddy
docker run --rm -v "$PWD/services/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" caddy-edge:2.11.7 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

# 5. Синхронизация и проверка (на Windows тесты с -race — через контейнер, services/AGENTS.md §1.1)
go work sync
(cd services/gateway && go test -race ./...)
(cd services/ws-hub && go test -race ./...)
(cd services/file-processor && go test -race ./...)
(cd services/gateway && govulncheck ./...)   # CI использует govulncheck v1.7.0
```
