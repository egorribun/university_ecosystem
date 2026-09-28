# MVP closure status

Короткий операционный статус. Обновляется одной дельтой за сессию; история
уходит в git, а не в этот файл. Требования: [ТЗ MVP](University_Ecosystem_MVP.md).
Прежние handoff и continuation — в [archive/](archive/) и являются историей,
а не текущим статусом.

Правила evidence (решение 2026-09-28): доказательство — это канонический CI
run, JUnit и отчёты мутаций. Независимое ревью обязательно только для
production-кода security/auth/data. RED→GREEN, fail-closed гейты и запрет
timeout-инфляции, exclusions, waivers и ручной перемаркировки сохраняются.

## Identity — 2026-09-28

| Что | Значение |
| --- | --- |
| Ветка / PR | `egorribun` / #1266 → `main` (`481dba81e`) |
| Последний push | `7466912e6` — merge `main` (#1292, #1293, #1295, #1296) и pip-группа #1294 |
| CI | Полная матрица на `7466912e6` запущена; прогон на `4aed00f09` заменён новым push |
| Security-PR | #1296 смержен в `main` 2026-09-28 (admin bypass, причина в merge-коммите) |

## Пауза 2026-09-28 (лимит сессии) — начать здесь

- Все коммиты запушены в `egorribun` до `8c64befb7` (см. `git log`). CI на
  этом SHA — источник свежего инвентаря мутаций (Ф0.2): дождаться terminal,
  скачать shard-артефакты.
- Агенты волны 1 работали в `../ue-w1` (auth: `useLoginFlow`,
  `ResetPassword`, `Register`, `ssrAuth`) и `../ue-w2` (push: `subscribe`,
  `usePushPreferences`, `useDndSettings`). Их WIP не отревьюен и не
  перенесён: сначала `git -C ../ue-w1 diff` / `../ue-w2`, focused Stryker по
  каждому файлу, затем перенос в ROOT. Логи — `artifacts/agent-w*/` внутри
  worktree. В обоих worktree junction на `node_modules`: удалять только после
  `[IO.Directory]::Delete(junction, $false)`.
- Ф5 стенд: `scripts/live_stand.py up` дошёл до сборки образов. Найдено и
  исправлено: health-probe file-processor (`8c64befb7`). **Открыто:** runtime
  стадия `services/caddy/Dockerfile` пинит apk-версии (`libapk=3.0.7-r0`,
  `libcrypto3=3.5.8-r0`, `curl=8.20.0-r0` и др.), которых уже нет в
  репозитории Alpine — `apk add` падает с exit 4. Обновить пины до текущих
  версий `caddy:2.11.4-alpine` и контракт-тест; заодно проверить xcaddy
  `--replace` x/net v0.56.0 / x/text v0.39.0 против grpc 1.83.2 (требует
  x/net ≥0.58.0). Worktree `../ue-live` существует, контейнеров стенда нет.
- Далее: снятие селекторов логина с живого стенда в браузере →
  `frontend/playwright.live.config.ts` + `frontend/tests/e2e-live/`.
- `../ue-sec` — worktree ветки `ci/dependabot-uv-ecosystem` (#1298 смержен),
  можно удалить.

## Фазы

- [x] Ф0.1 CI-контракт `continue-on-error` для O9-диагностики
- [ ] Ф0.2 Полный terminal CI на `4aed00f09`, свежий инвентарь мутаций
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

Frontend, последний полный инвентарь (run `36194161259`, 2026-09-27):
6 083 мутанта в 295 файлах. После него изменено 80 файлов, поэтому число
будет пересчитано по CI на `4aed00f09`.

| Очередь | Файлов | Мутантов | Остаток |
| --- | --- | --- | --- |
| A | 108 | 2 378 | пересчёт |
| B | 116 | 2 220 | пересчёт |
| C | 71 | 1 485 | пересчёт |

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
- [ ] Frontend auth: `useLoginFlow`, `ResetPassword`, `Register`, `ssrAuth` (агент).
- [ ] Frontend push: `subscribe`, `usePushPreferences`, `useDndSettings` (агент).
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
