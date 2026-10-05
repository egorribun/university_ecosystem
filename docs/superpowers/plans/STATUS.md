# MVP — оперативный статус

Срез на 2026-10-05 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Goal активен. Приёмка и выпуск `v1.0.0` не подтверждены.

## Рабочий контекст

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Последний проверенный live source: `18a86a90038ef7ce25e73b678223e04eebbf5e9e`.
  HEAD, origin и PR head совпали перед запуском этого стенда; checkout был чист.
  Следующие исправления требуют нового source-bound live прогона и CI.
- Root интегрирует и выполняет Git; три GPT-6 Luna Max ведут backend, frontend и CI/инфраструктуру.
  Во время source freeze агенты готовят приватные кандидаты, root остаётся единственным tracked writer.
- [AUDIT_PROMPT.md](AUDIT_PROMPT.md) включён по поручению пользователя; шаблон не заменяет поручение.
- Подробные предыдущие checkpoints сохранены в [STATUS родительского source](https://github.com/egorribun/university_ecosystem/blob/18a86a90038ef7ce25e73b678223e04eebbf5e9e/docs/superpowers/plans/STATUS.md).
  Исторические результаты не подтверждают новый SHA.

## Hosted evidence

- [Matrix 37331344636](https://github.com/egorribun/university_ecosystem/actions/runs/37331344636), attempt 1, source `18a86a900`:
  полный результат не получен. Разобранные backend mutation groups доходят до viable-score gate
  и падают на результате мутаций; ошибки запуска/runtime в этих логах не обнаружены.
  Новые regression tests пока не имеют canonical kill credit.
  Group 1 отдельно validated: 35/35 complete, 32 Killed / 3 Survived,
  0 unselected/timeout/runtime; primary/final proofs совпали. Это не итог кампании.
- [Matrix 37236971603](https://github.com/egorribun/university_ecosystem/actions/runs/37236971603),
  attempt 1, PR head `01ffea1b5`, producer merge `95b8ba18`: одинаковое дерево `286c57c1`.
  Backend: 128/128 groups validated, 4 540 selected, canonical 3 770 Killed / 770 Survived;
  primary 3 684 Killed / 856 Survived отдельно. Run completed/failure; 0 proof errors.
  Frontend: 64/64 identities/hashes/source validated, 42 913 assigned;
  gate отклонил 4 666 Survived / 30 Timeout / 31 RuntimeError / 1 NoCoverage.
- [Owned live acceptance 37236971288](https://github.com/egorribun/university_ecosystem/actions/runs/37236971288)
  завершился success на `01ffea1b5`; он подтверждает перечисленный PR smoke,
  а не полную продуктовую, визуальную или disaster-recovery приёмку.
- Для final main source нужны новые canonical evidence и три сопоставимых полных зелёных прогона.

## Сохранённые локальные результаты

- Frontend unit suite на `40bec3868800f7411d045c4468e593df63d84ab0`:
  719 файлов / 8 642 tests; statements 19 141/19 141, branches 13 680/13 680,
  functions 4 561/4 561, lines 17 123/17 123 — 100% каждой применимой метрики.
  Shuffle seed 1306006 также прошёл; это исторический unit scope.
- Backend/tooling affected union на `5edca1efafacfee272507cf407db6c4d9ee1f4be`:
  1 646 уникальных tests / 102 файла, полный setup/call/teardown без skips/errors/дублей.
  Это не полный backend suite или deployed PostgreSQL/RLS/NATS integration.
- Profile save: реальный PUT, payload, закрытие editor и сохранение после reload;
  Chromium 3/3 без retries. Grade/MFA exact-mutant controls остаются локальными.
- Проверенные исправления auth/admin guards, chat reload, cache, MFA epoch/IP buckets,
  session expiry, notifications locale и events observer перечислены в предыдущем STATUS.
  Их наличие в Git не заменяет свежую release certification.

## Живая приёмка source `18a86a900`

- Owned full Compose: запуск, readiness и synthetic seed прошли.
  Smoke: 18 passed / 2 project-scope skips. Admin/notifications: первый прогон 5/6;
  cold dashboard React #418 открыт. Поздний warm успех не закрывает cold failure.
- Avatar API: upload 200, persisted profile и generated image GET 200;
  WebP 96 bytes, HTTP/S3 Head/Get совпали по длине, MIME и SHA-256.
  Avatar UI desktop/mobile не прошёл; причина ещё не установлена.
- Приватная диагностика v4/v5 ошибочно выбирала старый testDir из v2;
  новая инструментализация не засчитана. В v6 фактический путь исправлен:
  2 valid / 0 invalid records, оба сценария упали до выбора файла.
  Гипотезы о rate limits/SW/декодировании не считаются доказанными.
- DR runner собран с pinned PostgreSQL 17 tools, source-bound backend и CLI.
  Read-only DB metadata и pg_dump прошли, dump 953 926 bytes.
  Snapshot упал: импорт StorageSettings инициализировал global app settings
  и потребовал отсутствующие auth secrets до обращения к source S3.
- Создан только пустой owned backup bucket; paired manifest не опубликован.
  Restore DB/bucket не созданы, фактический restore и RPO/RTO не выполнены.
  Приватные offline tests admission/role helpers не заменяют живое восстановление.
- После неудачного snapshot исходные контейнеры были возвращены в работу;
  публичный synthetic объект сохранился. Identity snapshot не заявляет quiescence.
- Перед teardown экспортированы и сверены 16 файлов evidence. Удалены только ресурсы
  текущего owned project; все прежние container IDs и volume names сохранились:
  175 containers / 94 volumes, 0 running. Удалены 8 owned image tags;
  затем по build receipt удалены 3 retired DR/source tags, без force/global prune.

## Исправления после live checkpoint

- Standalone backup CLI читает только storage settings, не импортируя app config.
  Сохранены dotenv selection, process-env priority, backend allowlist и S3 guards.
  Root fresh-process RED → GREEN; независимое scoped review без замечаний.
- Root canonical backup/paired restore/grades suite: 265/265, полный teardown GREEN.
  Три teardown errors приватного fixture loader не воспроизвелись в canonical checkout;
  этот приватный прогон не засчитан, общая DB fixture не изменялась.
- MFA stale-operation regression: root 14/14 GREEN; старое завершение запроса
  не сбрасывает busy новой сессии. Grade title_en проверяется точным persisted значением.
- Типизированы Redis/NATS фикстуры без изменения их сценариев; lock override
  восстанавливается session monkeypatch. Root auth/users suite 44/44 GREEN.
  Остальной strict typing debt и canonical mutation closure остаются открытыми.
- Root preflight 9/9, pre-commit и оба режима Markdown link checker GREEN.
  Secret baseline содержит прежние 319 identities; изменены только metadata/offsets.
  После небольшой правки test dotenv helper его шесть сценариев повторно прошли.
  Локальные проверки не являются release evidence нового source.

## Следующие действия

- Опубликовать checkpoint в том же PR после завершающих staged checks.
- Поднять новый owned source на чистом SHA; avatar UI выполнить первым после seed.
  Диагностика должна различать auth/register/profile/settings stages без вывода credentials.
- Повторить paired DB/S3 snapshot и restore с новым RunId, подтверждённым quiescence
  для snapshot, проверкой persisted references и исходного content tuple через target API.
  Отдельно обеспечить least-privilege target role и изолированные runtime dependencies;
  SpiceDB требует собственной БД/миграционной роли, full graph restore ещё не доказан.
- Продолжить блоки 4/5: RU/EN, light/dark, 360/390/768/1024/1440,
  live traceability ТЗ, cold SSR/PWA, small visual packages и утверждение baselines.
- Закрывать блок 6 по актуальному exact inventory: behavioral regression → canonical run;
  без waivers, exclusions, ручных Killed или timeout inflation.
- Выполнить deployed migrations/rollback и BE-02, WS load, backup RPO/RTO,
  Envoy Gateway/kind, failure recovery и независимый review всех 63 audit IDs.
- Final gates: 100% applicable coverage/viable mutation, три full green CI,
  approved visuals, resulting-main evidence, шесть certified GHCR digests,
  их kind acceptance и release `v1.0.0`. Все эти допуски остаются открытыми.

## Границы

Windows: Node 24.21.0, uv 0.11.28, Docker CLI/Engine доступны.
Тяжёлые локальные workloads запускаются по измеренному ресурсу; cleanup проверяет owner.
Сохраняются пользовательские `.env`, volumes, backups, Git и история миграций.
Admin bypass, force-push и изменение защиты ветки запрещены.
Внешнее production, реальные SMTP/push, физические устройства, CDC и field CWV вне MVP.
