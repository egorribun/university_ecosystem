# MVP — оперативный статус

Срез на 2026-10-10, 04:00 UTC.
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Выпуск `v1.0.0` ещё не подтверждён; автономная работа продолжается.

## Границы работы

- Только `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root владеет Git/интеграцией; до трёх GPT-6 Luna Max работают в непересекающихся областях.
- Q1/Q4 migration и разрешённые 14+1 removals выполнены. Ruleset `8335285`:
  76 required context/integration pairs; остальные правила сохранены.
  CodeQL blocking, Semgrep в pre-commit; Tier 0 и нынешние floors/100% patch сохраняются.
- Q2/Q3, global mutation score, comparable CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — v1.1. Один paired DB/S3 restore нужен для MVP.
- ADR-006 сохраняет tombstone/WS revoke до commit и conservative sibling logout
  при rollback. ГУУ — внутреннее демо; данные синтетические.

## Опубликованный CI checkpoint

Hosted evidence относится к `e537137a917c3ec647f3c7ef7126f21e144a7673`,
tree `56180c1656fba5cfe6d5660a31b87b7b778dc4a3`.
Fetch 03:37 UTC: origin/egorribun совпадает; main/merge-base
`6fa133b57f62c554162876d4e6d8349f8060fce9`; PR открыт.

- Exact-head final: 138 checks — 115 SUCCESS/23 SKIPPED, failures/running0.
  Required join: 76/76 SUCCESS, missing/duplicates0; все skips вне required set.
- [Matrix 38009644006/a1](https://github.com/egorribun/university_ecosystem/actions/runs/38009644006)
  SUCCESS. Harness policy/final-LF и News readiness fixes опубликованы с ordinary hooks.
- Bundle report: budget violations0; initial JS gzip380055/430080,
  CSS39511/40960, lazy280782/286720 bytes. Это transfer-budget proof, не LHCI.
  Rust/WASM coverage, crypto/browser parity и source-bound producer/consumer PASS на PR SHA.
- Wall span43m42; цель PR≤15min остаётся открытой. Wall span не является DAG critical path.
  Transport failures старых image pulls не переносятся на этот зелёный snapshot.
- Пакет ниже требует новых hosted results на своём SHA; e537 не заменяет их.

## Проверенная интеграция и Core

- Core e537 `run-1faec800-7fcf-47a0-8cc2-1222b0f07e16`:
  up, admin-only seed до demo seed, readiness/cookie policy и targeted News4/4 PASS.
  Первый full: **117 PASS/73 FAIL/8 SKIP**; второй не запускался.
- Этот Core штатно остановлен 03:27 UTC с signed-owner/daemon/resource checks;
  owned children0, source stable. Env, тома, данные и evidence сохранены.
  Ранее retired states и два временных Linux browser server не запускать повторно.
- Reviewed production fixes: MFA ring validation до любого изменения env;
  сохранение/синхронизация валидных rings, независимая fresh generation и worker isolation.
  Settings удаляет только default tab0 из URL, сохраняя остальные search values.
- Live test fixes: раскрытие Push accordion, точные Password labels,
  CSRF lockout, hydration регистрации, ожидание реального SW update,
  точный RU TOTP accordion title, same-origin Stories write и native persistent
  Push profiles с проверяемой очисткой.
  Исходные assertions, deadlines и восемь expected skips сохранены.
- HTTP diagnostics теперь различает Messenger/attachment failures; a11y diagnostics
  выводит только bounded axe colors/ratio. Full-page scope и serious/critical gate сохранены.
- Проверки интеграции: Node contracts169/169, final TOTP contract1/1; Settings18/18;
  весь TypeScript и frontend lint PASS, warnings0; Ruff/Prettier/diff check PASS.
- Полный Python startup/parser:1497 PASS/4 FAIL/1 platform SKIP.
  Все шесть новых MFA fail-closed cases PASS; прежние39 decoding warnings устранены.
  Четыре failure — decoding неиспользуемого mklink output в Windows test helper.
  После узкого bytes fix именно эти четыре теста **4/4 PASS** с thread warnings как errors.
  Форматирование MFA test file не изменило Python AST.
- Detect-secrets выявил публичный алфавит Base64URL в тестовом helper.
  Он выражен через стандартный модуль string с тем же набором64 символов;
  root/peer review CLEAR, scanner exclusions не добавлены, targeted hook PASS.
  Первая ошибочная правка owner-key fixture отменена; исходные fixture bytes сохранены.
  Весь итоговый startup-state test file:15 PASS/1 platform SKIP, warnings0.
- Новая живая приёмка этой интеграции ещё не выполнена. Planned fresh unique state:
  `run-e4bb144a-89bc-4ef9-ae51-eb40b5fce8aa`; readiness/cookie helpers static reviewed,
  source SHA привязывается после обычного commit.

## Открытые критерии

- Native V15:20 cycles/hidden7s и прочие gates PASS, strict exact-DOM FAIL:
  baseline716 nodes/437 listeners, после всех20 closes670/435.
  Sampling correction не устранила отличие; источник46 nodes/2 listeners не доказан.
  CSS/cleanup defect не подтверждён. Следующий шаг — неизменный canonical Story memory test.
- Full-page Core axe ранее дал serious color-contrast в Settings обоих проектов.
  Ограниченный legacy Settings audit03:00 дал HTTP200/axe0 при иной scope/motion;
  этот результат не закрывает full-page gate. Actual contrast colors ещё не получены.
- Fresh all-five-topic Push/auth/MFA/WS, остальные Core failures, два consecutive
  full runs190 PASS + exact8 skips/198 total, visual approvals и LHCI21/7 routes открыты.
  Desktop narrow footer geometry и Native требуют измерения; hypotheses не являются fixes.
- Owner утвердил только Home12 `ddbbc84d`; PNG/provenance сохранены byte-for-byte.
  Новый SHA или технический capture не означает одобрения новых bytes.
- Seed stop/start persistence и paired isolated DB/S3 restore ещё NOT RUN.
  Prepared restore/read-probe/avatar packages не заменяют actual snapshot/restore proof.
- [63 audit IDs](../../audits/INDEX.md#findings-ledger): historical60 CLOSED/2 DECLINED/1 OPEN
  не являются RC certification. Revalidation открыта; CodeQL3382/3383 уже dismissed,
  не повторять и не расширять разрешение.
- Full frozen-RC smoke, ordinary merge, fresh main checks, шесть signed source-bound
  images/SBOM/provenance и tag/release notes `v1.0.0` ещё не выполнены.

## Следующие действия и ресурсы

1. Опубликовать reviewed пакет с ordinary hooks, restage `.secrets.baseline`;
   fresh required-check results и unique Core на clean successor SHA.
2. Admin-only seed перед demo seed, readiness/cookie policy, затронутые live scenarios;
   исправить реальные failures и затем два consecutive full190+8 на неизменном RC.
3. Visual/LHCI, Native/Push/auth/WS, persistence/paired restore, security revalidation;
   frozen-RC full smoke → ordinary merge → main gates → image producer → release.

Документационная консолидация сохранена:82 authored Markdown согласованы с кодом/ADR;
superseded audits и одноразовый prompt удалены после переноса требований.
Canonical ownership — [docs index](../../README.md#documentation-ownership).
Git history, migrations, private rescue bundle и его inventory сохраняются.

Один heavy workload: startup RAM≤75%/free≥8GiB, stop≥85%/free<4GiB.
Serial Linux screenshots: owner exception≤80%/≥6GiB, browser1GiB/2CPU.
После остановки Core RAM≈41%/free≈19GiB; диск C≈200GiB свободно.
Owned builder stopped, cap4GiB/no swap/2CPU; полезный cache сохранён.
Account refresh03:51 UTC:39% weekly consumed/61% remaining, ordinary usage allowed.
Чужие процессы, Docker/WSL, env/data/backups и rescue bundle не очищать.
