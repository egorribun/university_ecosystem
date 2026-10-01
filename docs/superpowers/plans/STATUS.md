# MVP — оперативный статус

Срез на 2026-10-01 UTC. Goal активен. [Мастер-план](MVP_MASTER_PLAN.md) задаёт
решения и очередь, [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовый scope.
Полная приёмка MVP и выпуск `v1.0.0` ещё не подтверждены.

## Рабочее состояние

- Работа идёт только на `egorribun`, в единственном PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306). Проверенный опубликованный source SHA — `02e00d9cae12ceaa176bdd4d95ae260bc0049aef`; `origin/main` — `78b9499079442191920835eed9de93b726cf36a1`. Текущие исправления ниже проверяются в локальном diff после этого SHA и ещё не являются evidence нового CI/release source.
- Root координирует три субагента GPT-6 Luna Max с раздельным владением файлами, проверяет результаты и выполняет Git-операции. Новые ветки/worktree не создаются. Три исторических detached checkout с ignored локальными данными не используются и не удалялись.
- Свежий Matrix run `36882838279`, attempt 1, на `02e00d9ca`: E2E WASM Build и backend unit shards 1/2 завершились с failure; shards 0/3 ещё выполнялись в последнем срезе. Три unit failures относятся к legacy worker-env default, пропущенному live contract и Docker ignore parity; все три исправлены и проходят локально. Downstream frontend/coverage/mutation gates пропущены после падения producer; это не успешная приёмка. Owned Live Acceptance run `36882837683` ещё выполнялся в последнем срезе.
- WASM: hosted compiler завершился, затем verifier отверг generated-package drift. Два pinned canonical builder output совпали побайтно; повторный compile использовал пустые target caches и действительно исполнил RUN. Image source records, post-build lock files и toolchain проверены. Root сравнил шесть source records и восемь package records с image export, обоими output и checkout. Обновлены только два отличавшихся `.wasm` и их provenance; verifier и строгие contracts сохранены. Root: verifier PASS, Node artifact/provenance/runtime/build tests **23 passed**, Python WASM workflow/Docker-parity + quality-configuration tests **46 passed**. Новый hosted CI после checkpoint ещё необходим.
- CodeQL #3368 указал clear-text storage на Compose override: его source — конструирование пути `resolved_root / ".secrets"`, а не чтение значений. Локальная переменная получила точное имя directory Path; sentinel tests проверяют отсутствие содержимого env/JWT/Temporal credentials в overlay. Закрытие alert требует свежего CodeQL.
- Security Policy Integrity красный из-за неподдерживаемого `gh api --fail-with-body` в trusted `pull_request_target` workflow из base `main`. Исправление уже есть в рабочей ветке, но этот event использует base workflow до обычного merge. Ruleset и bypass не менялись. Ранее исправленные required contexts Rust FFI и Spectral проверены read-only: повреждённых символов в них нет.
- Пользовательские `.env`, остановленные контейнеры, volumes и backups сохранены. Сырые credential-shaped логи/evidence остаются вне репозитория, в приватных каталогах. Rescue bundle из архивов хранится приватно; Git history не переписывается.

## Выполнено и независимо проверено root

- Опубликованный checkpoint `02e00d9ca` включает безопасный in-place CLI, изолированный state root/Compose override и paired restore с семью allowlisted DB URL fields, literal prefix mapping, rollback и outbox guards. Предшествующий локальный PostgreSQL proof не заменяет deployed acceptance или evidence resulting `main` SHA.
- Текущий backup diff исправляет отказ для поддерживаемых origin-relative S3 bases, например `/api/v1/img`, сохраняя строгие path guards и точное совпадение target settings. Регрессия выполняет paired snapshot/restore в FakeS3/Fake DB, переписывает URL с target prefix, сохраняет внешний URL и читает восстановленный DB URL через `S3Storage.read_file`. Все девять `tests/test_backup*.py`: **297 passed**, **1214/1214 statements**, **430/430 branches**, **0 partial**, **100%**. Root report: `%TEMP%\ue-root-backup-35656bd5448c4f05811f29e23af4c878.json`. Это scoped local evidence текущего diff, не глобальный coverage gate или live HTTP proof.
- Живой `up` на `02e00d9ca` завершился до build/Compose startup: Windows присвоил новой `.secrets` и файлам владельца `BUILTIN\Administrators`, поэтому strict owner check отказал. Ресурсы не запускались. Исправление сохраняет current-user/SYSTEM ACL и current-user owner при создании и атомарном обновлении marker; отказ для чужого state не ослаблен.
- RED воспроизвёл owner mismatch; GREEN прошёл реальный PowerShell `PrepareOnly` с новым Python-generated signed marker и проверкой ACL/owner env/key/token files. Source guard сужен до точных Dockerignore scopes: шесть real-Git регрессий запрещают ignored вложенные исходники, два controls допускают действительно исключённые artifacts/cache. Все guard exclusions проверяются на наличие точного Dockerignore rule. В оба build contexts добавлено только рекурсивное исключение Python bytecode cache; фактический checkout guard проходит. Root повторил полный focused live/control/startup/routing набор: **265 passed, 1 POSIX-only skip**. Это подготовка конфигурации; readiness полного стека, seed и live browser smoke ещё не подтверждены.
- Найден и исправлен пропуск существующего push-permission-denied contract в npm-команде live contracts. Root: workflow contracts **3 passed**, `npm run test:e2e:live:contract` **116 passed**, без skips. Статические contracts не заменяют исполнение браузерных сценариев.
- Текущий consolidated local preflight прошёл **9/9**, harness **27/27**; report: `artifacts/fast-preflight/root-acl-wasm-final.json`. Первоначальный focused-batch failure был реальным расхождением двух Docker ignore files; шесть generated-output правил синхронизированы без изменения тестового allowlist или строгой проверки. Root повторил quality configuration вместе с WASM contracts: **46 passed**, затем после source-guard исправления quality/policy contracts: **43 passed**. Applicable hooks для предшествующего 14-file diff прошли; после независимого ревью, сужения guard и дополнительных регрессий окончательные hooks ещё требуются.

## Следующие проверяемые результаты

1. Завершить независимое ревью и hooks окончательного diff; сохранить checkpoint в том же PR и проверить новый WASM/CodeQL/Matrix run.
2. На новом чистом SHA повторить owned in-place full startup в свежем приватном temp run root: 25 readiness probes, реальные Prometheus targets, demo seed и auth/roles/reset smoke. На время запуска заморозить source; обычный stop сохраняет данные.
3. После базовых gates получить свежий canonical coverage/mutation inventory; focused Stryker/mutmut запускать параллельно только при измеренном запасе ресурсов и неизменном source. Старые/неполные shard artifacts не подтверждают 100% viable score.
4. Настроить isolated deployed S3 backup/restore acceptance: текущие `MINIO_*` Compose variables не включают `STORAGE_BACKEND=s3`, а Caddy public route привязан к bucket `uploads`. Требуются поддерживаемый CLI runner, явный storage config и проверка public/private HTTP reads по восстановленным DB URLs; backend FakeS3 proof не закрывает этот этап. Измерить RPO/RTO и rollback.
5. Продолжить BE-02 для ADR-036 DDL phases на непустых Docker/kind DB, продуктовую/визуальную/performance приёмку и Gateway API/kind проверки по мастер-плану.

## Release gates и ограничения

Открыты: полный live E2E; 100% всех применимых coverage/viable mutation метрик;
три сопоставимых полных зелёных CI-прогона; визуальное утверждение; WS load;
deployed backup/restore, RPO/RTO и rollback; BE-02; Gateway API/kind live routes,
TLS/WS/gRPC и per-client policy parity; финальный security review; canonical
resulting-main evidence; публикация и проверка шести GHCR digests.

Не выполнять admin bypass, force-push, изменение branch protection, удаление
пользовательских данных/volumes/backups, rewrite миграций или создание второго PR.
Внешнее production, реальные SMTP/push-провайдеры, физические устройства, CDC и
field CWV остаются вне MVP. Goal закрывается после проверки выпущенного комплекта.
