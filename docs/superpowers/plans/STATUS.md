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
| Последний push | `4aed00f09` — fix(ci): classify advisory progress diagnostic steps |
| CI | Matrix на `4aed00f09` запущен; предыдущий `36362444946` на `035e2d2` упал только на неклассифицированных O9-шагах |
| Security-PR | #1296 `security/default-branch-alerts` → `main`: anyio, httpx2/httpcore2, urllib3 floor, js-yaml; merge — только с подтверждения |

## Фазы

- [x] Ф0.1 CI-контракт `continue-on-error` для O9-диагностики
- [ ] Ф0.2 Полный terminal CI на `4aed00f09`, свежий инвентарь мутаций
- [ ] Ф1 Security-PR #1296: зелёный CI → merge (с подтверждения) → 0 алертов
- [x] Ф2 Гигиена: STATUS, архив планов, память, инвентарь worktree (решения ниже)
- [ ] Ф3 Мутации до 100% viable (волны 1–4)
- [ ] Ф4 Dependabot #1292–#1295 в ветку (mutmut 3.8 — после Ф3 backend)
- [ ] Ф5 Живой лейн приёмки: compose live overlay, Mailpit, VAPID, роли
- [ ] Ф6 Продуктовая приёмка по ТЗ §§2–13
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

## Сохранённое WIP (не удалять без решения мейнтейнера)

| Место | Состояние на 2026-09-28 |
| --- | --- |
| `../ue-e2e` | 3 изменённых файла: News/Events routes, `app.spec.ts` |
| `../ue-mm` | 13 изменённых tracked, backend mutation WIP |
| `../ue-mm2` | `storage.py` + новый key-boundary тест |
| `../ue-mut-A` | 52 tracked + 31 untracked: auth fork, lifespan, chat, ci.yml |
| `../ue-mut-B` | 38 tracked: storage, frontend events, ci.yml |
| `../ue-mut-C` | 31 tracked: docs, db-perf workflow |
| `~/.codex/worktrees/c0-owned-stand` | SMTP cast candidate, auth, Stories |
| `~/.codex/worktrees/ci-catalog-needs` | O6 catalog v5 (уже интегрирован в `c1f0b57f7`) |
| `~/.codex/worktrees/mutation-diagnostics` | O9 WIP (интегрирован в `c1f0b57f7`) |
| stash@{0..3} | 8 / 50 / 17 / 14 файлов, от 2026-09-25 и 2026-09-27 |

Все worktree с junction на `node_modules`: удалять только после
`cmd /c rmdir <junction>`, затем `git worktree remove`. Новые агенты работают
в отдельных worktree, старые не переиспользуются до решения.

## Открытые решения мейнтейнера

1. Merge security-PR #1296 после зелёного CI.
2. Судьба старых worktree и stash: сохранить патчи в `artifacts/wip/` и удалить,
   или оставить.
3. Трекать ли `docs/audits/AUDIT_PLATFORM_FULL.md` в git как есть.
4. Feature flags: все четыре (`new-chat-ui`, `semantic-search`,
   `push-batching`, `graphql-subscriptions`) объявлены в
   `app/core/feature_flags.py` и `k8s/flagd/flags.json` и показаны на
   admin-странице Feature Flags, но `is_enabled` нигде не вызывается —
   переключатели ни на что не влияют. Удалить их (страница станет пустой)
   или подключить реальные потребители.

## Согласованные ограничения MVP

CDC transport вне MVP (ADR-037). Реального staging нет — Docker Core/full и
локальный kind. Реальные SMTP и push-провайдеры заменены Mailpit и локальным
VAPID. Реальные устройства и field CWV — внешнее ограничение, фиксируется в
финальном аудите.
