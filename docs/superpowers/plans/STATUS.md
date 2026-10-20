# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-20 (Europe/Istanbul). План — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Приоритет и подтверждённый прогресс

Закрыть все 512 исходных AUD IDs [октябрьского аудита](../../audits/AUDIT-2026-10.md). Принятая нижняя граница — **152/512 (29,7%)**; [ledger](../../audits/AUDIT-2026-10.md#evidence-checkpoint-152-verified-original-aud-ids). Исправление, commit и отдельный успешный тест не заменяют приёмку. К продуктовой приёмке MVP вернуться после аудита.

Работа идёт только на `egorribun`, в одном checkout, через [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git; максимум три GPT-6 Luna Max с непересекающимися файлами. Удалённые операции — GitHub plugin. Новые проектные ветки/worktree, force-push, bypass, merge/deploy не выполняются.

## Проверенные source и CI

Последний полностью принятый CI checkpoint — [e15027a](https://github.com/egorribun/university_ecosystem/commit/e15027afdb4793838de373463654fb9ffc31d079), [Matrix 39240974262](https://github.com/egorribun/university_ecosystem/actions/runs/39240974262): 21 SUCCESS / два SKIP workflows; 78 required context/app pairs сверены — 77 SUCCESS / один NEUTRAL, без missing/duplicates/pending/failures. Подробности Python/frontend/PG/coverage и допустимого Checkov NEUTRAL сохранены в аудите. Owned Live этого checkpoint подтверждает auth/role/reset smoke, без full smoke, deployment и устранения исторического RSS-margin risk.

Последний проверяемый hosted source — [c84441f3](https://github.com/egorribun/university_ecosystem/commit/c84441f31ef9345df0ae32c5d617b12c370c9c98), [Matrix 39465395305](https://github.com/egorribun/university_ecosystem/actions/runs/39465395305). Checkout c5c21bf242592bac73d3e323acf7dac7e2c99959 имеет exact tree 9c29c2e4846a3f38484798f4fae4d135a4a12693. Полный CI не принят; каждый следующий source требует собственных checks.

- Hosted PostgreSQL job 118777833587: **206 PASS / девять штатных SKIP**. Все три quarantine concurrency/late-PUT/migration-DDL cases именованно PASS; upgrade и ожидаемый отказ irreversible downgrade проверены.
- Source/Test Inventory job 118775343852 отказал на старом policy head 202610120002 вместо 202610200001. Точечная синхронизация сохраняет 40 прежних exception records, добавляет только существующий UUIDv7-mixin record для quarantine_reservations.id и отражает source-derived 46 tables / 126 defaults. Root ordinary cohort: 27 PASS; actual generator/output/check PASS. Собственный hosted recheck ещё требуется.
- Gitleaks job 118775340779 отказал на 845 findings; root проверил, что все они относятся к 94 commits из ancestry base и лежат вне intended base..head. Причина воспроизведена локальным Git fixture: depth-one fetch после полного checkout делает base shallow и расширяет разность истории. Correction сохраняет полный fetch и запрещает scanner launch на shallow checkout. Root complete contracts: 21 PASS. Подавления не добавлены; собственный hosted recheck ещё требуется.
- Backend shard-0: 832 PASS / один известный FAIL на отсутствующем NATS outage step. Shard-1: 3761 PASS / 30 штатных SKIP / один FAIL устаревшего security workflow contract. Контракт теперь требует полного ancestry для Gitleaks и узнаёт новое имя scanner step, сохраняя прежний policy-before-scanner guard; root: 31 PASS в двух полных модулях и один PASS отдельного disposition contract. Owned Live job 118775342603 — SUCCESS; это обычный smoke, не полный AUD-174 proof.
- Performance run 39465394994: текущий Rust job 118775341779 — SUCCESS. Исторический FAIL 58ff776a на batch_detect_conflicts/100 сохранён в аудите; same-harness attribution не выполнена и не требуется подменять ею текущий gate. WS-Hub job 118775341113 отказал на prefetch base dependencies до измерений; это пока не установленная Go-регрессия. Artifact разбирается отдельно; gate и пороги сохранены.

## Карантин и actual Core evidence

AUD-241 пока не добавлен к принятому ledger. В c844 интегрированы durable storage-scoped quota-before-PUT, cross-worker reservations и TTL для подтверждённых stored objects. Root ordinary cohort: 412 PASS / zero SKIP; два service modules — 647 statements / 246 branches, 100% строк и ветвей. Root7 actual PostgreSQL: **3 PASS / zero SKIP**, три database receipts, реальные DDL/index/constraint проверки, стабильные source pins и exact-ID cleanup; host guard PASS. Прежний Root5 outer-runner SystemExit defect исправлен отдельно; его исторический exit 1 сохранён в evidence. Неопределённые pending writes занимают квоту до fenced reconciliation; versioned S3 и неполный inventory запрещают admission. Новая миграция не входит в finite131; текущие coverage/quality gates сохраняются.

Actual local Core c844 поднят штатно: readiness через published IPv4 и trusted-proxy refresh PASS. Browser/display origin сохранён. BuildKit остановлен после сборки, cache сохранён; startup guard PASS, sourceStable=true, zero recorded owned processes.

Точечный AUD-174 прогон: **два browser PASS**, затем общий Caddy verifier FAIL. Diagnostic repeat подтвердил успешный redaction parser для первого проекта, но повторная full ownership проверка исчерпала общий 25-second deadline. Это не принятая end-to-end redaction/visual проверка. Готовится batching тех же exact-ID runtime inspections без удаления проверок или увеличения бюджета. Core затем штатно остановлен с данными; stop guard PASS. Работающих принадлежащих прогону контейнеров нет.

Root проверил batching candidate на всех 23 остановленных owned containers: 15 с Health и восемь без него, одна bounded inspection за 0,201 секунды. Первый шаблон воспроизводимо отказал на отсутствующем Health; исправленный использует безопасный lookup, сохраняет восемь mount identity fields и отклоняет неоднозначные IDs/JSON. Полный canonical launcher cohort: **2064 PASS / zero SKIP**, fast preflight: **10/10 PASS**, ordinary pre-commit/pre-push: PASS. Реальная browser/redaction проверка исправленного source ещё требуется.

## Следующие действия

1. Принять и опубликовать проверенные inventory/Gitleaks corrections, выполнить ordinary hooks, trusted source scan и собственные hosted checks. В c844 обычные hooks, полный detect-secrets verifier и полный merge-aware local Gitleaks scan прошли; это не заменяет проверку следующего source.
2. Опубликовать проверенные AUD-141 (concurrent bookmark operations) и AUD-085 (actual Tailwind named utilities), затем принять их own-source evidence. Root canonical cohort: 35 PASS; полный frontend format check PASS. Это ещё не закрытие AUD IDs или новая визуальная приёмка.
3. Принять Caddy batching и повторить actual AUD-174 proof; затем продолжить operational holds AUD-164/167/169. Browser, deployed infrastructure и визуальная приёмка остаются отдельными видами evidence.
4. Продолжить [NATS spec](../specs/2026-10-18-owned-nats-outbox-acceptance.md), [outage plan](2026-10-19-owned-nats-outage.md) и [Docker observation](2026-10-20-owned-nats-docker-observation.md). SQL имеет ограниченный actual PG proof; HTTP/broker/composite/pin factory — private contracts. Composite deadline defect исправлен в private v2; lease-bootstrap integration gap сохраняется. Outage activation выключена.
5. Закрывать оставшиеся AUD IDs, причину отказа Go prefetch и AUD-015 Cyrillic PDF export с именованными source-bound доказательствами. Тематические планы: [UI lifecycle](2026-10-19-ui-lifecycle-reconciliation.md), [cleanup/timing](2026-10-20-runtime-cleanup-timing.md), [quality entrypoints](2026-10-20-quality-entrypoints.md).

## Неизменные границы

Detect-secrets baseline — 319 identities; dispositions — 264. Отдельное Gitleaks-разрешение ограничено 25 точными историческими fingerprints. Все 78 required context/app pairs, blocking CodeQL, hooks и finite131 migration exception до 2026-11-13 сохраняются. Changed/unmatched identities остаются блокирующими. Q1/Q4 migration действует; Q2/Q3 — v1.1; глобальный mutation score не повышается ради MVP.

Перед тяжёлым прогоном: RAM ≤75% / free ≥8 GiB; остановка при RAM ≥85% / free <4 GiB. Отдельное исключение для одиночных Linux screenshots: ≤80% / ≥6 GiB, container ≤1 GiB / 2 CPU. Удалять только доказанно принадлежащие работе ресурсы; чужие процессы и prune не трогать.

Manifest source_sha остаётся null. Actual RC, main/bootstrap activation, pre-merge full smoke, следующие визуальные пакеты и deployment — отдельные этапы. Home12 ранее утверждён только в своём exact scope; новые CSS/PDF изменения не получают визуального одобрения автоматически. Merge/deploy и NATS outage не выполнены.
