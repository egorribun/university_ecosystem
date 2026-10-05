# MVP — оперативный статус

Срез на 2026-10-06 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Goal активен. Приёмка и выпуск `v1.0.0` не подтверждены.

## Последний проверенный runtime source

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Последний source с runtime-проверками — `e2ba2c3bc77369c7a18e4f0efb40fe7b0705c99d`. Это не утверждение о
  текущем HEAD. Подробная история сохранена в [неизменяемом checkpoint](https://github.com/egorribun/university_ecosystem/blob/18a86a90038ef7ce25e73b678223e04eebbf5e9e/docs/superpowers/plans/STATUS.md);
  исторические результаты не подтверждают другой SHA.
- Root выполняет Git и остаётся единственным tracked writer; три GPT-6 Luna Max
  ведут backend, frontend и CI/инфраструктуру. `AUDIT_PROMPT.md`
  включён по поручению пользователя; он не заменяет текущее поручение.

## Hosted CI для e2ba

- [Matrix 37358382479](https://github.com/egorribun/university_ecosystem/actions/runs/37358382479),
  attempt 1: point-in-time снимок около 2026-10-05 21:03 UTC — 178 jobs:
  108 success, 15 cancelled, 15 skipped, 3 in progress, 37 queued. У отменённых
  jobs не было runner или выполненных steps; Actions API не сообщает причину.
  Результат неполный, не all-green и не завершённый mutation gate. Слепых
  повторов и ослабления timeout/quality gates не было.
- [Owned Live 37358381991](https://github.com/egorribun/university_ecosystem/actions/runs/37358381991)
  завершился success. [Unauthenticated Routes Smoke 37358381722](https://github.com/egorribun/university_ecosystem/actions/runs/37358381722)
  прошёл на attempt 2 после ошибки передачи артефакта на attempt 1. Это только
  результаты этих двух ограниченных сценариев.

## Live и DR для e2ba

- Owned source был запущен и seeded. Synthetic avatar API upload и профиль
  подтвердили сохранённую ссылку; исходное изображение — WebP, 96 bytes. Source
  HTTP и S3 Head/Get совпали по длине, MIME и SHA-256:
  `0e309491348e6f30381cd0f83790651a09b3351b632cd2b449021727c336cf29`.
- Avatar UI: V8 desktop upload вернул HTTP 200, но изображение не отобразилось;
  mobile не отправил POST. Попытка Service Worker bypass была некорректна и не
  считается объяснением. В V9 обнаружен старый V8 launcher; V9 не запускался
  как исправленная цепочка. V9.1 готовится для нового clean source.
- Для RunId `5384eb7a3b8b43db98458d194527c34a` созданы paired DB/S3 snapshot и
  восстановленная целевая БД/корзина. Read-only target S3 Head/Get совпал с
  исходным WebP. Обычная проверка обнаружила production `TypeError` в
  `S3Storage.read_file`: bounded read вызывал `read(size)` у aiohttp response,
  возвращённого `StreamingBody.__aenter__`. Повторного restore поверх цели не было.
- После этого root запустил verifier на той же цели и pinned runner с read-only
  overlay кандидата `app/services/storage.py`. Overlay-проверка прошла: одна
  migration head, одна восстановленная ссылка и bounded read на 2 bytes. Это
  диагностическая проверка исправленного кандидата; она не подтверждает
  исходный production runtime, полноценную app-level готовность или RPO/RTO.
- Следовательно, физическое восстановление DB/S3 выполнено, но production
  verifier на новом source, отдельный app runtime и полное измерение RTO
  остаются незакрытыми. Перед очисткой старого owned стенда требуется
  проверенный приватный экспорт paired snapshot.

## Исправления и оставшиеся gates

- Исправление сохраняет `StreamingBody` при чтении, ограничения размера,
  timeout и проверку целостности. RED воспроизведён на прежнем коде;
  регрессии используют установленный реальный `StreamingBody`, включая
  truncated-object `IncompleteReadError` и закрытие response.
- После интеграции локальный canonical набор S3/storage, search rebuild
  и private attachments прошёл 262/262; Ruff check и format прошли.
  Добавлена typed `reindex48` регрессия неполного bulk rebuild с сохранением
  прежнего индекса. Свежий canonical mutation credit ещё не получен.
- MFA duplicate-resend regression для исторического frontend ID 904
  интегрирована; canonical module прошёл 15/15. Точное историческое изменение
  воспроизводило RED; это не заменяет новый Stryker inventory.
- Required preflight прошёл 9/9 (типы, lint, format, i18n, contracts, harness);
  применимые staged pre-commit checks прошли. Это локальные проверки,
  не release evidence и не подтверждение нового runtime source.
- Далее нужны новый clean source и CI, проверки целевой БД/S3/app runtime, avatar UI V9.1 и
  объяснение runnerless CI cancellations по доступным фактам, без blind retry.
- Блоки 4/5: RU/EN, light/dark, responsive widths, live traceability ТЗ,
  cold SSR/PWA, visual review и утверждённые baselines.
- Блок 6 и release gates открыты: 100% применимого coverage и 100% viable
  mutation score, три
  полных зелёных CI, migrations/rollback, BE-02, WS load, полный backup RPO/RTO,
  Envoy Gateway/kind, recovery, независимый review 63 audit IDs, шесть certified
  GHCR digests, kind acceptance и выпуск `v1.0.0`.

## Ограничения

Сохранять пользовательские env, volumes, backups и Git history. Не применять
admin bypass, force-push, global prune или изменение branch protection. Внешний
production, реальные SMTP/push, физические устройства, CDC и field CWV вне MVP.
