# MVP — оперативный статус

Срез на 2026-10-06 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Работа приостановлена по поручению пользователя. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Последний source с runtime-проверками — `9f0208621f47b04883b488cc62dcf64eb055e70c`.
  Эти результаты не подтверждают автоматически следующий HEAD.
- Root — единственный tracked writer и владелец Git. Три GPT-6 Luna Max
  завершили текущие операции; незавершённые приватные материалы сохранены.
- Интегрированы SmartImage source-keyed fallback и versioned srcset,
  регрессии rotated legacy audit signature и persisted `NewsUpdated` payload.
  Root независимо проверил RED/GREEN до интеграции. После интеграции canonical
  affected frontend tests: 76/76; backend audit/news tests: 38/38.
  Это не canonical mutation credit и не release certification.

## Hosted CI для 9f0208621

- [Matrix 37376193756](https://github.com/egorribun/university_ecosystem/actions/runs/37376193756),
  attempt 1: снимок 2026-10-05 23:47:20 UTC — 312 jobs: 135 success,
  31 failure, 16 in progress, 118 queued, 12 skipped. Все 31 failures в этом
  снимке — backend incremental mutation groups. Полный результат не получен.
- Producer PR-merge SHA `458de86f458283aa9fa16c7aa8b0697025a6070d`
  отличается от source HEAD; tree совпадает:
  `ac46399765c0ce504cc7fbe570a77089a7254164`. Обе привязки сохранены.
- [Owned Live 37376192633](https://github.com/egorribun/university_ecosystem/actions/runs/37376192633)
  и [Unauthenticated Routes Smoke 37376192623](https://github.com/egorribun/university_ecosystem/actions/runs/37376192623)
  завершились success. Это ограниченные сценарии, не полная приёмка ТЗ.
- Свежая backend universe — 54 457. Root независимо валидировал canonical
  evidence групп 1–21: 749 selected, 608 killed, 141 survived. Агент отдельно
  валидировал 33 группы: 1181 selected, 970 killed, 211 survived; root replay
  расширенного набора ещё нужен. Все числа частичные, не global score.
- Group 4: 31 killed, 4 survived, без timeout/no-tests. Audit49 и News12
  закрыты локальными regression controls; нужен новый producer. Redis15
  type-cast и NATS80 server-default equivalence требуют разбора по контракту,
  без ручного Killed или произвольных exclusions.
- Coverage artifact содержит 100% применимых показателей; integrity checks
  пройдены. Полный локальный validator ограничен отсутствием Git/inventory
  в artifact-only каталоге. Frontend shard 0: 20 killed; global gate открыт.

## Live и диагностика

- Owned 9f source запущен и seeded. Первый локальный smoke: 17 passed,
  1 failed, 2 skipped; desktop admin denial вызвал page error. Повторный
  диагностический auth-roles набор на прогретом стенде: 16 passed, 2 skipped.
  Исходная ошибка не воспроизведена; причина и исправление не подтверждены.
- Avatar V9.3: desktop/mobile POST вернули HTTP 200, page errors — 0.
  Default и корректный CDP SW-bypass получили HTTP 200 и AVIF image signature;
  UI assertion naturalWidth всё ещё failed. Причина не установлена.
  Viewport/lazy loading остаётся гипотезой. SmartImage defects независимо
  воспроизведены; их связь с этим live failure не доказана.
- V9.4 в `C:/Temp/ue-avatar-ui-diagnostic-e2ba-20261005/v9.4` — незавершённая
  unsealed копия со старыми manifest/seal. Не запускать. После возобновления
  завершить schema, hashes, offline contracts и listing, затем использовать
  runtime на фактическом clean source.
- Owned stand state:
  `C:/Temp/ue-live-acceptance/run-orchestrator-9f0208621-20261006-de281e7d9ff54f07a4a49b5e22d6359e`.
  Для паузы используется `stop`, сохраняющий volumes, env и evidence.
  После смены source нельзя приписывать этому стенду новый HEAD.

## Восстановление и сохранность

- Старый e2ba paired DB/S3 snapshot экспортирован приватно; root проверил
  hashes и ACL. Owned teardown старого стенда завершён: его containers,
  volumes и networks удалены, env/secrets/backups/evidence сохранены.
- Новый DR RunId `6751bb0189fa45c2a6a2c6820e79b922` — private plan:
  clock не начат, runtime не создан. Target launcher и bounded profile/image
  probe прошли offline проверки. Source quiescence и resource snapshot
  helpers требуют актуальной привязки.
- App-level restore, RPO/RTO, SpiceDB graph и search parity не подтверждены.
  После нового HEAD нужен новый source-bound DR run, без старого clock.
- Приватные receipts и патчи сохранены в
  `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157` и доменных bundles.
  Release требует канонических переносимых artifacts. Приватные scratch
  каталоги сохранены после отклонения удаления проверкой безопасности.

## После явного возобновления

- Проверить Git/PR/CI на фактическом HEAD, получить новые canonical mutation
  результаты для интегрированных тестов и продолжить приоритетные survivors.
- Завершить avatar V9.4, воспроизвести cold admin error, выполнить source-bound
  app restore и измерить RPO/RTO.
- Блоки 4/5 открыты: полная live traceability ТЗ, RU/EN, light/dark,
  responsive widths, SSR/PWA, performance и visual approval.
- Открыты 100% viable mutation score, три полных зелёных CI,
  migrations/rollback, BE-02, WS load, Envoy Gateway/kind, review 63 audit IDs,
  шесть certified GHCR digests и выпуск `v1.0.0`.

## Ограничения

Сохранять пользовательские env, volumes, backups и Git history. Не применять
admin bypass, force-push, global prune или изменение branch protection. Внешний
production, реальные SMTP/push, физические устройства, CDC и field CWV вне MVP.
