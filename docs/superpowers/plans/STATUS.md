# MVP — оперативный статус

Срез: 2026-10-12 18:31 UTC. Автономная работа возобновлена по поручению
владельца; root интегрирует проверенный локальный пакет. Основания:
[мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md),
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) и
[audit index](../../audits/INDEX.md). Выпуск v1.0.0 ещё не подтверждён.

## Git, CI и дополнительный объём

- Один checkout, ветка `egorribun`, существующий PR #1306. Опубликованный
  HEAD `def2832269c525d0ecc2f77b7534469a3c249911`, tree
  `7595564d461730d56479a471d267ff8606971330`. Коммиты владельца и merge main
  сохранены. Текущий локальный пакет не закоммичен и не опубликован;
  изменения и приватные кандидаты сохранены для продолжения.
- Ruleset `8335285`: 78 уникальных context/integration pairs и CodeQL
  `code_scanning`. Решение владельца 2026-10-12 добавило четыре security checks
  вместо двух compatibility contexts. Q1/Q4 сохранены; CodeQL blocking,
  Semgrep в pre-commit; coverage floors и 100% patch не снижались.
- Последний strict78 snapshot опубликованного `def283226`: 73 SUCCESS,
  4 FAILURE, 1 SKIPPED. Receipt
  `ci-required78-def283-refresh-20261012-1791811962175.json`,
  SHA-256 `A1733C90B663EAEF94B73BB1175E9DC084AA3DA1B59FF1CA6C93ED63553E9EB2`.
  CodeQL SUCCESS; новых alerts нет. Три первичных failures — backend shard 0,
  backend shard 2 и Renovate Strict; CI Success зависит от них, Coverage skipped.
  Локальные совместимые исправления pins/contracts подготовлены и проверены;
  исправленный опубликованный SHA и свежие required results ещё нужны.
- В объём включены [AUDIT-2026-10](../../audits/AUDIT-2026-10.md) и
  [dependency updates](../../audits/dependency-updates-2026-10/README.md).
  Это исходные снимки, а не подтверждение текущих OPEN/CLOSED.
  Сначала P1/security/data, затем остальные подтверждённые находки и обновления.

## Локальные исправления и границы доказательств

- Сохранены исправления AUD-005/008, 025/026/028, 164/167, 165, 166/458,
  168/169, 170/171/172 и 173/174. Дальнейшие изменения включают durable outbox
  для news/events/comments (AUD-197/198), проверку владельца event image и
  сохранение media с недоказанной принадлежностью (AUD-180), JWKS egress и
  привязку NetworkPolicy к release (AUD-188), обязательный ENVIRONMENT (AUD-190).
  Сохранение legacy news media — ограниченная защита от удаления чужого файла;
  полный owner-bearing contract и retention ещё открыты.
- Backend: широкий прогон дал 1029 PASS / 17 SKIP и два устаревших ожидания
  немедленного enqueue. Оба заменены проверкой pending source event в outbox,
  связанного с созданной сущностью и locale; узкий итоговый прогон ниже зелёный.
  Mypy прошёл для 345 файлов, Ruff для app прошёл. Полный повтор после последних
  тестовых изменений и current-source coverage остаются pending.
- Реальный PostgreSQL 17: пять AUD-038 проверок прошли, включая историческую
  цепочку миграций с непустой DEFAULT partition, UUID/data/PK/FK и routing.
  Четыре outbox integration tests прошли с rollback/commit, повторной обработкой
  и deduplication. Тестовые БД и контейнеры завершены; исходные данные сохранены.
  AUD-230: регрессия воспроизвела потерю tenant_id, затем 10 проверок прошли
  с сохранением tenant/user до head и реальным `alembic check` без drift.
  Девять nullable tenant columns/FK/indexes принадлежат migration metadata;
  runtime ORM не менялся. Guard `817f27c23b204ac0813c93766bb879c7`:
  source stable, owned children 0. ADR-036 фиксирует утверждённый rollback barrier;
  исторический тест не сертифицирует production downgrade ниже него (AUD-324).
- Helm: 381 PASS / 15 POSIX SKIP; затем все шесть затронутых соседних контрактов
  прошли после актуализации точного backend egress. Ruff/actionlint прошли.
  Это render/contract evidence, не kind deployment proof.
- AUD-185: Gitleaks теперь расширяет стандартные правила; существующий allowlist
  не расширен. Реальный scanner через stdin: synthetic canary пропускается старой
  конфигурацией, обнаруживается новой, чистый ввод проходит; содержимое не
  выводилось. Обычный pre-commit: Gitleaks прошёл; ошибки типов, тестовых secret
  fixtures и SSR HTML assertions исправлены без новых suppressions/baseline
  entries. Повторный контроль: 21 Python PASS с реальным PG17, Mypy 345 файлов
  PASS, 14 Node SSR PASS; guard `9888966181f4449b8f8654be9e045bfd`, source stable,
  owned children 0. Полный pre-commit прошёл все code/scanner checks; остановился
  только на обновлении номеров строк baseline. Root подтвердил неизменность
  finding identities и scanner settings и повторно включил baseline в staging.
  Обычный commit должен повторно пройти hooks без изменения исходников.
- AUD-186/187: новые inline secret suppressions проверяются по immutable Git
  delta; quoted Unicode paths и недоступный Git обрабатываются корректно.
  Protected-path matcher дополнен восемью точными verifier paths и двумя
  прямыми contract tests без изменения доверия к owner PR или permissions.
  Итоговый guard `33088e9964094df8be0cb778c596f401`: 62 PASS,
  Ruff PASS, actionlint PASS; source stable, owned children 0.
- AUD-231: native TanStack nonce и no-store HTML интегрированы; Node static/offline
  контракты — 23 PASS, Python CSP/default-policy parity и Gitleaks — 10 PASS.
  После исправления типов тестов и public-HTML ожидания контрольный прогон дал
  13 PASS; TypeScript и ESLint без предупреждений прошли. Production build и
  реальный concurrent SSR nonce probe прошли с действующими CI caps 2048 MiB RSS /
  1536 MiB heap: guard `fc67e7b871ce496f8714de1d3d15f6c7`, source stable,
  owned children 0. E2E проверяет nonce inline scripts/CSP, разные request nonce,
  no-store HTML, immutable assets и health response.
- AUD-462: v4 интегрирован после peer review; все четыре Go package tests прошли
  на Windows. Guard `19f1778ec9184eb192b9c0ad04763bb9`: source stable,
  owned children 0. Bounded write drain, временный fail-closed fence и join/replay
  epoch сохраняются; mutex не удерживается на socket I/O. Linux race pending:
  загрузка pinned образа не уложилась в 360 секунд; Windows PASS её не заменяет.
- AUD-223: удаление failed gate state больше не разрешает Stop. RED воспроизведён;
  полный contract/shared-loader прогон — 47 PASS, guard
  `77f2e83183d54e999f608db50c0192b3`. Writer bootstrap сохранён.
- AUD-226: Alembic включён в существующую Python coverage/provenance цепочку,
  Tier 0/floors/required contexts сохранены. Contract-прогон: 266 PASS / 1 SKIP,
  один неверный workflow-step assertion исправлен и отдельно прошёл; actionlint
  прошёл. Диагностический PG17-прогон и существующие migration unit tests дали
  59,53% statements / 29,98% branches; это частичная выборка, не полный backend
  aggregate. Действующий 100% floor не пройден и не снижался; дополнительные
  семантические PG-тесты готовятся, current-source gate остаётся pending.
  Backend GraphQL retirement и ограниченный Gateway egress — private candidates,
  ещё не интегрированы; news media ownership/retention продолжается.
- urllib3/Werkzeug lock обновлён и синхронизирован. Ammonia 4.2.1 допускается
  cooldown, но кандидат не применён; нужен реальный WASM rebuild/provenance.
  Caddy 2.11.7 не допущен до 2026-10-13 05:52:45 UTC.
  Остальной dependency report не считается закрытым.

## Следующие действия

1. Пройти обычные hooks с повторным stage `.secrets.baseline`, опубликовать
   согласованный пакет в существующий PR и получить свежие 78 required results
   и CodeQL. Измерить current-source migration coverage, завершить Linux race
   и проверить следующие private candidates; закрытия привязать к evidence.
2. Новый Core на чистом опубликованном source: Core32, затем два последовательных
   full runs (inventory 198, ожидаемо 190 PASS/8 SKIP), seed stop/start.
   Старый Core `8295b807` остановлен, данные сохранены; не перезапускать.
3. News/Events/Schedule: 36 captures RU/EN light/dark 390/768/1440;
   отдельно 360/1024 risk/a11y/reduced motion, main JS <500 KB и LHCI 21 sample.
   Утверждён только Home12 `ddbbc84d`; остальные pixels/baselines pending.
4. Один paired DB/S3 backup/restore в изолированные цели с чтением объекта по
   restored DB reference; final-source SEC-07/RUST-P3-03 и auth/session/data review.
   Продолжить audit/dependency пакет и согласование решений владельца с ТЗ/ADR.
5. Frozen RC, full smoke, ordinary merge, свежие resulting-main checks,
   producer шести образов и release `v1.0.0`.

Живой стенд остановлен, данные сохранены; тестовые контейнеры завершены.
Root и три GPT-6 Luna Max работают в одном checkout, Git только у root.
Один heavy workload: admission RAM≤75%/free≥8GiB,
остановка ≥85%/<4GiB. Исключение только serial Linux screenshots:
старт≤80%/≥6GiB, browser≤1GiB/2CPU. Удалять только доказанно owned временные
ресурсы; Core data, caches, env/volumes/backups и rescue bundle сохранять.
Q2/Q3, global mutation, kind certification, три comparable CI и RPO/RTO — v1.1.
