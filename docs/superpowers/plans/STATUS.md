# MVP closure status

Короткий операционный статус. Обновляется одной дельтой за сессию; история
уходит в git, а не в этот файл. Требования: [ТЗ MVP](University_Ecosystem_MVP.md).
Прежние handoff и continuation — в [archive/](archive/) и являются историей,
а не текущим статусом.

**Точка остановки 2026-09-29 (актуально — раздел 14; разделы 5 и 13 частично исторические):** все детали, состояние worktree агентов, порядок
продолжения и ловушки окружения — в [2026-09-29-handoff.md](2026-09-29-handoff.md).
Начинать с него.

Правила evidence (решение 2026-09-28): доказательство — это канонический CI
run, JUnit и отчёты мутаций. Независимое ревью обязательно только для
production-кода security/auth/data. RED→GREEN, fail-closed гейты и запрет
timeout-инфляции, exclusions, waivers и ручной перемаркировки сохраняются.
Мейнтейнер требует абсолютной чистоты кода и документации: документы
обновляются в том же коммите, что и поведение.

## Identity — 2026-09-29

| Что | Значение |
| --- | --- |
| Ветка / PR | `egorribun` / #1266 → `main` (`be8c6a197`, влит merge-ем `dfbb6561f`) |
| `origin/egorribun` | `634412103`; локально не запушено 15 коммитов (handoff, раздел 14); push ждёт terminal CI `36553547083` |
| CI | Matrix `36553547083` на `634412103` — ожидается первый прогон с backend-мутациями; push только после terminal |
| Security-PR | #1296 смержен в `main` 2026-09-28 (admin bypass, причина в merge-коммите) |

## Фазы

- [x] Ф0 CI разблокирован; фронтенд-инвентарь (run `36443355112`); backend — ждёт `36553547083`
- [x] Ф1 Security-PR #1296 смержен; проверить закрытие алертов после обновления графа
- [x] Ф2 Гигиена процесса: STATUS, архив планов, память, worktree/stash
- [ ] Ф3 Мутации до 100% viable — frontend волна 1 влита (`4b9e4a13d`, focused Stryker впереди); backend: 250 мутантов в 20 файлах, агенты в `../ue-b1..b3`
- [x] Ф4 Dependabot #1292–#1295 и #1298 в ветке; #1297 закрыт
- [ ] Ф5 Живой лейн: стенд, Mailpit, VAPID, `auth-roles` и `password-reset` спеки есть; CI workflow — нет
- [ ] Ф6 Продуктовая приёмка по ТЗ §§2–13 (+ admin, PWA/offline, SSR, слабые устройства, security-негативы)
- [ ] Ф6b Дизайн-ревью редизайнов ТЗ по скриншотам live-стенда
- [ ] Ф6c Чистота: мёртвые файлы, Python-зависимости и аудит md сделаны; осталось knip, Go, демо-данные, ws-hub нагрузка, review
- [ ] Ф7 Spelling RU, zero-warning build, BE-02 all phases, O1–O9 (Rust уже запинен 1.97.1)
- [ ] Ф8 SeaweedFS по умолчанию (WIP `../ue-w3`), Helm backup на rclone сделан, Grafana, restore
- [ ] Ф9 Локальный kind prod-like: TLS, Kyverno, ESO, HPA, chaos, rollback
- [ ] Ф10 Шесть immutable-образов, Trivy (просрочен `.trivyignore`), SBOM
- [ ] Ф11 Финальный SHA-bound аудит и документация
- [ ] Ф12 Merge #1266 и post-merge (каждый шаг — с разрешения)

## Мутационный долг

Frontend, CI `36443355112` (`a4caec3bf`, 2026-09-28): 35 959 killed, 1 306
ignored (ADR-040), **5 511 открыто** (5 431 survived, 36 timeout, 33 runtime
error, 11 no coverage) в 269 файлах: hooks 1 491, features 1 286, pages 1 242,
components 835. Инвентарь и срезы очередей — в ignored
`artifacts/quality/inventory-a4caec3bf/` (`build_inventory.py`, `queue_slice.py`
в `artifacts/quality/mutation-tools/`).

Backend: первый полный mutmut-прогон — `36553547083`. Известные семейства:
`NotificationDeadLetterPurged.from_dict`, `_unlink_ignore_missing`,
`InternalAccessMiddleware.__init__`, private static path, chat forward,
notification delivery, SMTP `cast`.

Порядок: волна 1 — security/auth/push; волна 2 — messenger/realtime; волна 3 —
файлы с ≥50 мутантами; волна 4 — хвост.

Волна 1:

- [x] Fork-safety `_auth_executor` (`da30b91f7`), security-ревью APPROVE.
- [x] `AdminFeatureFlagsFeature.tsx` — 26/26 killed (`2cdbef282`).
- [ ] Frontend auth (WIP `../ue-w1`): `ResetPassword` 115, `Register` 66,
  `useAuthApi` 46, `ForgotPassword` 44, `useLoginFlow` 37, `ssrAuth` 17.
- [ ] Frontend push (WIP `../ue-w2`): `usePushPreferences` 74, `subscribe` 70,
  `useDndSettings` 67.
- [ ] Backend-семейства — по точному списку из CI.

## Открытые решения

Подробности и рекомендации — handoff, раздел 10.

1. SPIFFE: `pyspiffe` не объявлен и не установлен; подсистема всегда
   «degraded», middleware fail-closed. Удалить или довести в kind.
2. `pyo3_sanitizer`: прод (`--no-dev`) санитизирует через `nh3`, dev/CI —
   нативно. Оставить один путь.
3. O9: подключить `heartbeat_watchdog.py` или закрыть ADR-ом.
4. Ф6b: индикатор силы пароля в `ResetPassword` не окрашивается.

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
4. 2026-09-29: абсолютная чистота кода и документации; устаревшее удаляется, а
   не копится.

## Согласованные ограничения MVP

CDC transport вне MVP (ADR-037). Реального staging нет — Docker Core/full и
локальный kind. Реальные SMTP и push-провайдеры заменены Mailpit и локальным
VAPID. Реальные устройства и field CWV — внешнее ограничение, фиксируется в
финальном аудите.
