# U_PY

Срез: 2026-10-12, UTC 07:32. База: снимок origin/egorribun 04fdd84c2.

## Политика
- Cooldown 7 дней: Renovate `minimumReleaseAge: 7 days` (PyPI и uv), Dependabot `cooldown.default-days: 7`, uv `exclude-newer = "7 days"`. Порог: релизы новее 2026-10-05 07:32Z помечены «рано». Security-PR (`vulnerabilityAlerts`) открываются сразу, без автомержа; обход cooldown только по `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`.
- Pin (ADR-035): все 68 внешних runtime-требований имеют верхнюю границу `<` (проверено). Расширение cap это отдельное изменение с матрицей совместимости, а не патч. Для 0.x `<1` и `<0.N` намеренные.
- Запрещено: широкий `uv lock --upgrade`, `--exclude-newer false`, `UV_EXCLUDE_NEWER=false`, `SKIP=semgrep`, `--no-verify`. Ручной ревью: все major и security-критичные патчи (cryptography, pyjwt, bcrypt, argon2-cffi, pyotp, webauthn, python-jose).
- Toolchain: Python 3.14 (`requires-python >=3.12,<3.15`, образ `python:3.14-slim-bookworm`), uv `required-version ==0.11.28` (CI читает его через setup-uv), ruff 0.14.14 (AGENTS.md, pre-commit).

## Patch/minor — можно обновить
| Пакет | Где | Сейчас | → Версия | Дата | Cooldown | Security | Риск |
|---|---|---|---|---|---|---|---|
| werkzeug (транзитив через schemathesis) | dev | 3.1.8 | 3.1.9 | 2026-09-27 | ок (15д) | CVE-2026-102598 (GHSA-g6x2-hccm-hh4m), фикс в 3.1.9 | низкий |
| python-dotenv | runtime | 1.2.3 | 1.2.4 | 2026-10-01 | ок (11д) | нет | низкий |
| pyroscope-io (не win32) | runtime | 1.2.3 | 1.2.5 | 2026-10-02 | ок (10д) | нет | низкий |
| hypothesis | dev | 6.168.0 | 6.168.4 | 2026-10-05 04:13Z | ок (7д 3ч, на границе) | нет | низкий |
| httpx2 | dev | 2.13.0 | 2.13.1 | 2026-09-23 | ок (19д) | нет | низкий |
| fakeredis | dev | 2.38.0 | 2.39.0 | 2026-10-01 | ок (11д) | нет | низкий |
| sentry-sdk[opentelemetry] | runtime | 2.70.0 | 2.71.0 | 2026-09-28 | ок (14д) | нет | низкий: minor SDK, новая интеграция TypeSafe |
| virtualenv | dev | 21.10.0 | 21.14.5 | 2026-10-02 | ок (10д) | нет (advisory до 21.7.13 уже закрыты) | низкий |
| schemathesis | dev | 4.27.5 | 4.29.2 | 2026-10-04 | ок (8д) | нет | низкий-средний: dev, property-тесты OpenAPI |
| starlette | runtime | 1.6.0 | 1.7.0 | 2026-09-23 | ок (19д) | нет | средний: TestClient, OTel-middleware экспериментальный; снимает блокер cap anyio |
| sqlalchemy[asyncio] | runtime | 2.0.54 | 2.1.3 | 2026-10-02 | ок (10д) | нет | высокий: minor ORM (lazy="noload", mypy-плагин); notes 2.1.0 без явных [change]-тегов, 2.1.3 фиксит регрессию порядка колонок в dataclass-mixin; нужен полный прогон |
| cryptography | runtime, security-критичный | 50.0.0 | 50.0.2 | 2026-09-30 | ок по возрасту, НО заблокирован `exclude-newer-package` (cutoff 2026-08-01) | GHSA на 50.0.0 нет; 50.0.1 (2026-08-25) и 50.0.2 пересобраны с OpenSSL 4.0.2/4.0.3, CVE в changelog не указаны | средний; ручной ревью; нужно решение по cutoff |
| charset-normalizer | security/detect-secrets-requirements.txt | 3.5.1 | 3.5.2 | 2026-09-30 | ок (11д) | нет | низкий; нужны новые sha256 |
| charset-normalizer | deploy.yml (шаг smoke-pins) | 3.4.7 | 3.5.2 | 2026-09-30 | ок (11д) | нет | низкий |
| urllib3 | deploy.yml (шаг smoke-pins) | 2.7.0 | 2.8.0 | 2026-09-15 | ок (27д) | CVE-2026-97687 (high), CVE-2026-97688 (medium), CVE-2026-97689 (high); фикс в 2.8.0 | средний, приоритет: security-пин в CI |
| requests | deploy.yml (smoke-pins) | 2.33.1 | 2.34.2 | 2026-05-14 | ок | нет | низкий |
| certifi | deploy.yml (smoke-pins) | 2026.4.22 | 2026.7.22 | 2026-07-22 | ок | нет | низкий |
| idna | deploy.yml (smoke-pins) | 3.18 | 3.20 | 2026-09-17 | ок (25д) | нет | низкий |
| sqlmap (пин ==1.10.8) | .github/workflows/sqlmap.yml:60 | 1.10.8 | 1.10.9 | 2026-09-02 | ок (1.10.10 от 2026-10-05 21:47Z: рано) | нет | низкий |
| uv (toolchain) | pyproject `[tool.uv].required-version`; backend.Dockerfile:15; Dockerfile.test:37 | 0.11.28 | 0.11.33 (patch) | 2026-07-28 | ок (linux/amd64 digest `sha256:8876e42c…`) | GHSA на uv (rust и pip) нет | низкий |
| python:3.14-slim-bookworm (toolchain, digest) | backend.Dockerfile:10, :65; Dockerfile.test:3 | digest `sha256:4ff4b92a…`: патч не определён, не совпал с amd64-digest тегов 3.14.3–3.14.8 | 3.14.8, digest `sha256:48b13b00…` (текущий тег) | 2026-09-30 (3.14.8) | ок | нет | низкий: обновить digest; локально Python 3.14.6, CI `"3.14"` |

Итого: 20 версий (19 доступны, 1 заблокирован: cryptography) и 1 digest базового образа.

## Major — отдельно
| Пакет | Где | Сейчас | Последний major | Дата | Breaking changes (кратко) | Затронутый код | Оценка |
|---|---|---|---|---|---|---|---|
| fastapi | runtime | 0.141.1 (cap <0.142) | 0.142.2 (0.x-минор, за cap) | 2026-09-30 (ок) | 0.142.0 без явных breaking в notes; starlette 1.6.0 уже в lock | app/api (роутеры); по notes API не меняется | средняя: cap-change по ADR-035 §6 |
| strawberry-graphql | runtime | 0.327.7 (cap <0.328.0) | 0.331.1 | 2026-10-04 (ок) | 0.328: drop graphql-core 3.2, нужен graphql-core 3.3 (сейчас 3.2.12). 0.331: `Annotated[..., strawberry.field(...)]` с отложенными типами даёт UnresolvedStrawberryFieldError (py3.10-3.13) | app/graphql/queries.py: 5 декораторов `@strawberry.field(...)`, не Annotated, не затронуто; graphql-core тянет hypothesis-graphql (dev) | средне-высокая: cap и смена graphql-core |
| mypy | dev | 2.3.1 (cap <2.4) | 2.4.0 | 2026-10-01 (ок) | native parser по умолчанию (legacy через `--no-native-parser`, удаление запланировано на 2027); type-комментарии у for/with игнорируются; parallel не по умолчанию; PEP 661 | в app нет `for/with ... # type:` (проверено); плагины pydantic/sqlalchemy/strawberry не проверены | средняя: cap-change; pre-commit mirror v1.15.0 расходится |
| ruff | dev (+ pre-commit v0.14.14, AGENTS.md) | 0.14.14 (cap <0.17) | 0.16.10 (0.x-минор) | 2026-10-01 (ок) | 0.15.0: скобки у except снимаются на py314, `except A, B:` несовместим с `requires-python >=3.12` и гейтом no-python2-except (это причина пина RZ-30-05/TD-29-03). 0.16.0: 413 default-правил (наш select явный, не влияет). Отката except-изменения в notes 0.16.x не найдено | pyproject `[tool.ruff]` (target py314, явный select); scripts/check_no_python2_except.py | высокая: держать 0.14.14 до решения по except |
| structlog | runtime | 25.5.0 (cap <26) | 26.1.0 (первый 26.x) | 2026-06-06 (ок) | удалена поддержка py3.8/3.9; better-exceptions deprecated; ConsoleRenderer не предупреждает при готовом exception | app/core/logging.py:314-315 (structlog.dev.RichTracebackFormatter, ConsoleRenderer); better-exceptions не используется | низкая-средняя |
| gunicorn | runtime (CMD backend.Dockerfile:116) | 25.3.0 (cap <26) | 26.2.0 | 2026-08-24 (ок) | 26.0: eventlet-воркер удалён (не используется); жёстче валидация HTTP/1.1 (control chars, Content-Length list, request-target); HEAD/204/304 без тела; fast-парсер требует gunicorn_h1c>=0.6.5. 26.2: h2c (opt-in), фиксы HTTP/2 | CMD `--worker-class uvicorn.workers.UvicornWorker`: проверить с uvicorn 0.54; валидация может отвергнуть нестандартные запросы прокси | средняя: нужен live-smoke (/health/ready) |
| uvicorn | runtime | 0.53.0 (cap <1) | 0.54.0 (0.x-минор) | 2026-09-25 (ок) | аддитивно: HTTP/2 zttp (opt-in), trailers, 103 Early Hints | не используется (`--http zttp` нигде не задан) | низкая |
| uvloop | runtime (не win32) | 0.22.1 (cap <1) | 0.23.0 (0.x-минор) | 2026-10-01 (ок) | убран loop._ready_len, убран wheel как build-dep, префикс имени потоков | app/core/uvloop_setup.py:29 (EventLoopPolicy), публичный API | низкая |
| OpenTelemetry (группа) | runtime | api/sdk/exporter-otlp 1.44.0; instrumentation-*, semantic-conventions 0.65b0 | 1.45.0 (1.45.1 рано); 0.66b0 | 2026-09-25 (ок) | [BREAKING] api: подклассы Logger обязаны реализовать enabled(); OTLP HTTP по умолчанию urllib3; SimpleSpanProcessor не отдаёт spans после shutdown. instrumentation 0.66b0 и sdk 1.45 требуют semantic-conventions 0.66b0: двигать вместе | app/core/observability.py: экспортёры gRPC (HTTP-изменения не касаются), LoggerProvider/LoggingHandler, подклассов Logger нет | средняя: 9 пакетов, 0.x-инструментация |
| anyio | runtime | 4.14.2 (cap <4.15) | 4.15.1 | 2026-09-05 (ок) | cap обоснован импортом устаревшего BlockingPortal в starlette TestClient; starlette 1.7.0 его убрал (#3498, #3501), значит cap можно поднять. 4.15: фикс pytest-плагина (CallSpec2), lazy-импорт модулей | tests (TestClient, filterwarnings=error), граница ASGI/WebSocket | средняя: обязательна матрица ADR-035 §6 |
| asyncpg | runtime | 0.31.0 (cap <0.32) | 0.32.0 | 2026-10-06, рано (до 2026-10-13) | pool: min_size становится постоянным полом, появился init_size; direct TLS требует sslmode=require/verify-ca/verify-full; SCRAM быстрее | прямой asyncpg.connect: app/workers/outbox.py:182, app/workers/cdc_outbox.py:525 и :800 (replication); DSN нормализуется только по схеме | низкая-средняя: дождаться cooldown и cap |
| aioboto3 / aiobotocore / botocore | runtime | aioboto3 15.5.0 пинит aiobotocore==2.25.1, тот требует botocore<1.40.62; lock: botocore 1.40.61 | aiobotocore 3.9.2 (major 3, 2026-10-01); botocore 1.43.108 (2026-10-02): обе версии недоступны из-за пина | 2026-10-01 | aiobotocore 2.26.0 тоже закрыт пином aioboto3; aiobotocore 3.x требует botocore<1.43.107; новее aioboto3 15.5.0 нет | app/services/storage.py импортирует botocore напрямую | высокая: нужна замена aioboto3 или решение владельца |
| uv (toolchain) | required-version, CI setup-uv, Dockerfile COPY uv | 0.11.28 | 0.12.23 (0.x-минор, ок); 0.13.0 рано (до 2026-10-16) | 2026-10-03 | 0.12.0: `uv init` с build-system по умолчанию; pre-release `if-necessary`; hash-checking требует secure digest у каждого требования; убраны редкие форматы архивов. 0.13.0: Python 3.15 по умолчанию; `--require-hashes` из constraints; пересборка кэша | CI и Docker (setup-uv, COPY uv); lock пересоздаётся новым uv | средняя: в этот проход не включать |

Итого: 13 позиций.

## Уже актуально
- Runtime: aiofiles 25.1.0, aiosmtplib 5.1.3, aiosqlite 0.22.1, alembic 1.20.0, argon2-cffi 25.1.0, authzed 1.25.0, brotli-asgi 1.6.0, clamd 1.0.2, defusedxml 0.7.1, dishka 1.10.1, elasticsearch 9.5.1, email-validator 2.3.0, grpcio 1.84.0, httpx 0.28.1, maxminddb 3.2.0, minio 7.2.20, nats-py 2.16.0, nh3 0.3.7, openfeature-provider-flagd 0.5.2 (cap <0.5.3), openfeature-sdk 0.10.0, orjson 3.12.0 (3.13.0 рано), pgvector 0.5.0 (0.5.1 рано), pillow 12.3.0, pillow-avif-plugin 1.6.0, prometheus-client 0.26.0, protobuf 7.36.2, psutil 7.2.2, psycopg 3.3.6, pydantic 2.13.5 (cap <2.14.0), pydantic-settings 2.15.0, pyjwt 2.15.1, pyotp 2.10.0, python-magic 0.4.27, python-multipart 0.0.32, pyvips 3.2.0, pywebpush 2.5.0, redis 8.1.0, requests 2.34.2, rich 15.0.0, typer 0.27.2 (0.27.3 рано), zxcvbn 4.5.0.
- Dev: asgi-lifespan 2.1.0, atheris 3.1.0, bandit 1.9.4, deptry 0.25.1 (пин), diff-cover 10.6.0, maturin 1.15.0, mutmut 3.8.0 (пин), pact-python 3.4.1 (пин), pip-audit 2.10.1 (пин), pre-commit 4.6.2 (пин), pyright 1.1.414, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-cov 7.1.0, pytest-timeout 2.4.0, pytest-xdist 3.8.0, pyyaml 6.0.3 (пин), testcontainers 4.15.0, types-aiofiles 25.1.0.20260518, types-pyyaml 6.0.12.20260906, types-redis 4.6.0.20241004 (последний релиз 2024-10-04).
- Держатся намеренно: jsonschema 4.25.1 (dependabot ignore для >=4.26, новее 4.26.0), types-jsonschema 4.25.1.20251008 (новее 4.26.0.20261006); types-requests 2.33.0.20260906 (новее 2026-10-06, рано).
- security/detect-secrets-requirements.txt (кроме charset-normalizer): detect-secrets 1.5.0, PyYAML 6.0.3, requests 2.34.2, certifi 2026.7.22, idna 3.20, urllib3 2.8.0 это последние версии; все хэши есть на PyPI (PyYAML: wheel cp314 manylinux x86_64).
- Транзитивные (127): advisory на locked-версии только у werkzeug, остальные без advisory.

## Не удалось проверить
- Резолв с обновлениями (`uv lock`), pytest, ruff, mypy 2.4 и live-smoke не запускались (правила: только чтение). Совместимость проверена по requires_dist из PyPI, notes и grep по коду, а не запуском.
- Security: GitHub Advisory Database (pip, 6566 записей; uv в rust и pip). Записи только в OSV без GHSA не проверялись; pip-audit из CI не запускался.
- Notes не читались, проверены только метаданные PyPI: hypothesis, httpx2, fakeredis, pyroscope-io, python-dotenv, virtualenv, schemathesis, sqlmap, certifi, idna, requests, charset-normalizer. sentry-sdk 2.71.0 прочитан частично.
- Digest `python:3.14-slim-bookworm` 4ff4b92a: патч-версия не определена (не совпал с amd64-digest тегов 3.14.3-3.14.8, индекс 3.14.3 не проверен). Digest 23c59390 в containers/quality/Dockerfile.performance-rust не сопоставлен. Semgrep (docker-hook v1.168.0): образ не проверен; pip latest 1.180.0 (2026-10-07, рано).
- mypy 2.4: прочитана секция CHANGELOG; совместимость mypy-плагинов не проверена; тег `v2.3.1` у pre-commit/mirrors-mypy не проверен.
- Поведение Renovate для 0.x-минорных обновлений не проверено; `:automergeMinor` в extends означает автомерж minor по конфигурации.
- CVE, закрытые OpenSSL 4.0.2/4.0.3 в колёсах cryptography, не установлены.

## Команды (не выполнены)
```text
# 0. версия uv обязана быть 0.11.28 (required-version)
uv --version

# 1. патчи в lock (cooldown учитывается через exclude-newer = "7 days")
uv lock --upgrade-package werkzeug --upgrade-package python-dotenv --upgrade-package pyroscope-io --upgrade-package hypothesis --upgrade-package httpx2
uv lock --check

# 2. minor, отдельными PR (starlette и sqlalchemy по одному)
uv lock --upgrade-package fakeredis --upgrade-package sentry-sdk --upgrade-package virtualenv --upgrade-package schemathesis
uv lock --upgrade-package starlette
uv lock --upgrade-package sqlalchemy
uv lock --check

# 3. uv 0.11.28 -> 0.11.33
#    pyproject.toml: required-version = "==0.11.33"
#    backend.Dockerfile:13 (комментарий) и :15, Dockerfile.test:35 (комментарий) и :37:
#    ghcr.io/astral-sh/uv:0.11.33@sha256:8876e42c633ff18826b6bc2c1ebe8b4b0c4e056a2cab6e6a48e736ccc0bcad64
uv lock --check

# 4. base image: python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83
#    backend.Dockerfile:10 и :65, Dockerfile.test:3; до замены подтвердить тип digest (index или amd64), как у прежнего пина

# 5. security/detect-secrets-requirements.txt: charset-normalizer==3.5.2 и все --hash=sha256 из
#    https://pypi.org/pypi/charset-normalizer/3.5.2/json (urls[].digests.sha256), затем проверка:
python -m pip install --dry-run --no-deps --require-hashes --only-binary=:all: -r security/detect-secrets-requirements.txt

# 6. .github/workflows/deploy.yml, шаг «Install hash-locked smoke-test dependencies»:
#    urllib3==2.8.0, requests==2.34.2, certifi==2026.7.22, idna==3.20, charset-normalizer==3.5.2 с sha256 из PyPI
#    (предпочтительно заменить набор ссылкой на security/detect-secrets-requirements.txt)

# 7. .github/workflows/sqlmap.yml:60
uv pip install "sqlmap==1.10.9"

# 8. cryptography (заблокировано): после решения владельца по [tool.uv].exclude-newer-package.cryptography
uv lock --upgrade-package cryptography
uv lock --check
```

## Расхождения (важно)
- `[tool.uv].exclude-newer-package` содержит 4 постоянных исключения: cryptography 2026-08-01, h2 2026-08-04, mcp 2026-08-04, pyjwt 2026-09-29. `DEPENDENCY_COOLDOWN_EMERGENCY.md` называет единственным исключением targeted-команду. Из-за cryptography не попадают 50.0.1 и 50.0.2. Пакет mcp в lock отсутствует (только override).
- Два бота на одни манифесты: `renovate.json` и `.github/dependabot.yml` (uv, pip). Игнор jsonschema >=4.26 есть только в Dependabot; в Renovate такого правила нет.
- deploy.yml держит отдельный набор smoke-пинов (urllib3 2.7.0 с 3 CVE, requests 2.33.1, certifi 2026.4.22, idna 3.18, charset-normalizer 3.4.7). Он не совпадает с lock и с security-файлом и не покрыт pip-директорией Dependabot.
- pre-commit `mirrors-mypy` v1.15.0 против mypy 2.3.1 в lock.
- Устаревшие комментарии и цифры: protobuf `<7` в pyproject (lock: protobuf 7.36.2 и openfeature-provider-flagd 0.5.2, который требует protobuf>=7.35.1; authzed и OTel поддерживают <8); FIX-41-01 про несовместимость strawberry с pydantic 2.13 (lock: pydantic 2.13.5 + strawberry 0.327.7); ADR-035 пишет 258 пакетов, в lock 228.
- Два разных digest базового Python-образа: backend.Dockerfile и Dockerfile.test используют 4ff4b92a, containers/quality/Dockerfile.performance-rust использует 23c59390.
