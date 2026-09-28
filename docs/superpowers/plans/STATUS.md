# MVP closure status

Короткий операционный статус. Обновляется одной дельтой за сессию; история
уходит в git, а не в этот файл. Требования: [ТЗ MVP](University_Ecosystem_MVP.md).
Прежние handoff и continuation — в [archive/](archive/) и являются историей,
а не текущим статусом.

Правила evidence (решение 2026-09-28): доказательство — это канонический CI
run, JUnit и отчёты мутаций. Независимое ревью обязательно только для
production-кода security/auth/data. RED→GREEN, fail-closed гейты и запрет
timeout-инфляции, exclusions, waivers и ручной перемаркировки сохраняются.

## Identity — 2026-09-29

| Что | Значение |
| --- | --- |
| Ветка / PR | `egorribun` / #1266 → `main` (`be8c6a197`, #1298 влит merge-ем) |
| Последний push | `dfbb6561f` — merge `main` поверх `ee90ce97e` |
| CI | Полная матрица на `dfbb6561f`; прогон `36443355112` (`a4caec3bf`) дал фронтенд-инвентарь, backend-мутации там были пропущены |
| Security-PR | #1296 смержен в `main` 2026-09-28 (admin bypass, причина в merge-коммите) |

## Сессия 2026-09-29

- Прогон `36443355112`: все 64 Stryker-шарда отработали (инвентарь ниже).
  Stats-шард mutmut 1/8 упал: `tests/test_live_stand.py` читает
  `docker-compose.live.yml`, которого не было в песочнице mutmut, и все
  backend-группы были пропущены. Исправлено в `862eeb7cd` с контрактом «каждый
  корневой `docker-compose*.yml` копируется».
- Helm backup-job: `mc` → rclone 1.75.1 по digest, ключ `backup.s3ClientImage`
  (`ee90ce97e`); загрузка проверена вживую на SeaweedFS 4.47 (UID 1000, RO rootfs).
- Legacy-том `university_ecosystem_minio-data`: бакет `uploads` пуст (148 КБ
  метаданных). Кэшированный образ MinIO (digest `14cea493…`) помечен
  `local/minio-legacy:RELEASE.2025-09-07T16-13-09Z` и сохранён в
  `../university_ecosystem_backups/2026-09-29/` — сборка из исходников не нужна.
- Ф8 в работе (агент, `../ue-w3`): SeaweedFS по умолчанию во всех compose,
  удаление cutover-overlay и anti-rollback-механики, fail-closed guard на
  непустой legacy-том без `S3_CUTOVER_ACK`, ADR-042.
- Ф6b: индикатор силы пароля в `ResetPassword` никогда не окрашивался
  (`ProgressBar` не принимает `color`) — дизайн-недочёт для ревью.
- Стенд `ue-live` остановлен (тома сохранены), пересборка после волны 1.
## Фазы

- [x] Ф0.1 CI-контракт `continue-on-error` для O9-диагностики
- [x] Ф0.2 Terminal CI `36443355112`, фронтенд-инвентарь; backend — на `dfbb6561f`
- [x] Ф1 Security-PR #1296 смержен; проверить закрытие алертов после обновления графа
- [x] Ф2 Гигиена: STATUS, архив планов, память, инвентарь worktree (решения ниже)
- [ ] Ф3 Мутации до 100% viable (волны 1–4)
- [x] Ф4 #1292, #1293, #1295 пришли merge-ем `main`; #1294 перенесён без `grpcio-health-checking` (не используется, 1.84 несовместим с protobuf 6). #1297 закрыт (менял `pyproject.toml` без `uv.lock`, `jsonschema` 4.26 несовместим с semgrep); #1298 переводит Dependabot на экосистему `uv` — смержен в `main`
- [ ] Ф5 Живой лейн приёмки: compose live overlay, Mailpit, VAPID, роли
- [ ] Ф6 Продуктовая приёмка по ТЗ §§2–13 (+ admin, PWA/offline, SSR, слабые устройства, security-негативы)
- [ ] Ф6b Дизайн-ревью редизайнов ТЗ по скриншотам live-стенда
- [ ] Ф6c Неиспользуемые зависимости и мёртвый код, демо-данные, нагрузка ws-hub, security- и code-review ветки
- [ ] Ф7 Spelling RU, zero-warning build, Rust pin, BE-02 all phases, O1–O9
- [ ] Ф8 Docker Core/full, Grafana provisioning, SeaweedFS cutover, restore
- [ ] Ф9 Локальный kind prod-like: TLS, Kyverno, ESO, HPA, chaos, rollback
- [ ] Ф10 Шесть immutable-образов, Trivy, SBOM
- [ ] Ф11 Финальный SHA-bound аудит и документация
- [ ] Ф12 Merge #1266 и post-merge (каждый шаг — с разрешения)

## Мутационный долг

Frontend, CI `36443355112` (`a4caec3bf`, 2026-09-28): 35 959 killed, 1 306
ignored (ADR-040), **5 511 открыто** (5 431 survived, 36 timeout, 33 runtime
error, 11 no coverage) в 269 файлах: hooks 1 491, features 1 286, pages 1 242,
components 835. Инвентарь и срезы очередей — в ignored
`artifacts/quality/inventory-a4caec3bf/` (`build_inventory.py`, `queue_slice.py`).
Backend: известные семейства — auth reset timeouts (fork-наследование
`_auth_executor`, доказано на Linux), `NotificationDeadLetterPurged.from_dict`,
`_unlink_ignore_missing`, `InternalAccessMiddleware.__init__`, private static
path, chat forward, notification delivery, SMTP `cast`.

Порядок: волна 1 — security/auth; волна 2 — messenger/realtime; волна 3 —
файлы с ≥50 мутантами; волна 4 — хвост.

Волна 1, прогресс:

- [x] Fork-safety `_auth_executor` (`da30b91f7`): Linux RED (зависание
  дочернего процесса) → GREEN, security-ревью APPROVE.
- [x] `AdminFeatureFlagsFeature.tsx` — 26/26 killed (`2cdbef282`).
- [ ] Frontend auth (агент, `../ue-w1`): `ResetPassword` 115, `Register` 66, `useAuthApi` 46, `ForgotPassword` 44, `useLoginFlow` 37, `ssrAuth` 17.
- [ ] Frontend push (агент, `../ue-w2`): `usePushPreferences` 74, `subscribe` 70, `useDndSettings` 67.
- [ ] Backend-семейства — по точному списку из CI.
- [ ] Бэклог из ревью: module-level executor-ы в `analytics` и
  `minio_storage` (тот же класс fork-дефекта, сейчас не достижим: gunicorn
  без `--preload`); кэши по `id(loop)` → `WeakKeyDictionary`; глобальный
  `_push_semaphore` в `webpush`.

## Незавершённая работа

Старые worktree и все stash разобраны и удалены 2026-09-28. Почти весь их WIP
уже был в HEAD или вытеснен новыми версиями. Бэкап и классификация лежат в
ignored `artifacts/wip/2026-09-28/`; неинтегрированные правки, которые ещё
нужны, — в `keep/`: fork-safe `_auth_executor` (волна 1), SMTP `cast` и три
мелких мутационных патча. Агенты фазы 3 работают в новых worktree.

## Решения мейнтейнера 2026-09-28

1. Security-PR #1296 смержен, несмотря на красные проверки, унаследованные от
   `main` (они же красные на собственном CI `main` `481dba81e`, run
   `34989574430`). Merge с admin bypass выполнил мейнтейнер, причина
   записана в merge-коммит (AGENTS.md §5).
2. Feature flags: четыре флага без единого потребителя удалены; OpenFeature/
   flagd и read-only страница диагностики остаются, страница показывает
   честное пустое состояние. Новый флаг регистрируется только вместе с кодом,
   который его читает.
3. `docs/audits/AUDIT_PLATFORM_FULL.md` пока не закрыт: открыты BE-02
   (deployed-catalog preflight, фазы 8–9) и RUST-P3-03 (final-SHA evidence).
   В фазе 11 его ledger переносится в финальный аудит, после чего файл
   удаляется.

## Согласованные ограничения MVP

CDC transport вне MVP (ADR-037). Реального staging нет — Docker Core/full и
локальный kind. Реальные SMTP и push-провайдеры заменены Mailpit и локальным
VAPID. Реальные устройства и field CWV — внешнее ограничение, фиксируется в
финальном аудите.
