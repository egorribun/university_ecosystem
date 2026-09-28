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

## Возобновление 2026-09-28 (после лимита)

- CI на `63751e61d` упал на четырёх контрактах, задетых этими изменениями
  (ledger Semgrep для SHA-1, перенос строк ошибок PowerShell на Linux, тег
  `!reset`, хеши detect-secrets runner) — исправлено в `a4caec3bf`.
- Блокеры стенда сняты: health-probe file-processor (`8c64befb7`) и
  apk-пины Caddy (`acc44de4c`); стенд пересобирается.
- **MinIO недоступен:** `quay.io/minio/minio` и `quay.io/minio/mc` отвечают
  401. Базовый compose-стек не стартует на чистой машине, Helm backup-job не
  скачает mc. Ф8 (SeaweedFS) стала обязательной; стенд переведён на
  SeaweedFS (`354f967a5`). Старый том MinIO читается только MinIO-сервером,
  собранным из исходников по тегу.
- WIP агентов прошлой сессии пуст (лимит оборвал их до изменений); агент
  по auth-файлам волны 1 перезапущен в `../ue-w1`, push-файлы ждут слота.

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
