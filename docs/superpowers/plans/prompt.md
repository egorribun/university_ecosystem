Продолжи автономное закрытие master plan University Ecosystem от текущего egorribun SHA a604c1f1a4d3b62f4594b29f63a32c52e6d292bb. Работай на ветке egorribun
Сначала прочитай корневой AGENTS.md, доменные AGENTS.md затронутых областей и quality/quality-contract.json. Используй systematic debugging + TDD; не ослабляй 100% coverage/mutation/security gates, не добавляй exclusions/quarantines/suppressions без доказанного false positive. Никаких Co-Authored-By. Коммиты quality/testing не связывать с waves.

Текущий PR: https://github.com/egorribun/university_ecosystem/pull/1257, CI run 33055425675. Из подтвержденных blockers:
1) CodeQL: .github/workflows/release.yml lines around checkout/use of inputs.release-sha — cache poisoning because privileged default-branch workflow checks out dispatch-controlled SHA. Fix trust boundary fail-closed: privileged workflow code must come from immutable trusted main workflow/source; validate exact main SHA before executing checked-out scripts; no untrusted cache/tool execution.
2) Alembic/Squawk: migration 148642dd1207 emits changing-column-type and adding-not-nullable-field warnings and job fails. Redesign migration safely (phased/backfill/check constraint/validated conversion as applicable), preserve upgrade/downgrade and PostgreSQL tests.
3) Backend test failure: tests/test_schemas_closure.py::test_dead_letter_job_ids_are_unique_and_non_empty passes invalid strings a/a/b to UUID schema. Correct contract test and ensure duplicate valid UUID rejection.
4) mutmut shards 1/8 and 5/8: isolated mutants tree misses security/audit-allowlist.yaml, causing stats baseline failure. Fix mutation-copy/inventory inputs rather than skipping the test; verify all shards.
5) Frontend unit shard failure: Profile.behavior save test observes saving=true and missing snackbar; diagnose async race/contract, fix product/test deterministically.
6) E2E failures across Chromium/Firefox/WebKit/mobile: missing sessions accordion, missing MFA recovery-code field, duplicate/ambiguous headings and Settings buttons, offline indicator absent, navigation race/NS_BINDING_ABORTED. Determine product regression versus stale selectors; fix accessibility/behavior and deterministic Playwright contracts, do not paper over with arbitrary timeouts.
7) Frontend Stryker shards fail initial dry run because shared tests fail; resolve root test defects, then ensure 100% viable mutation score.
8) Unauthenticated dark-theme smoke was cancelled; rerun after fixes and distinguish intentional skips.
9) Continue monitoring full CI because run is still active; inventory every final failure, not only list above.

Required workflow:
- Reproduce focused failures locally from exact logs/artifacts.
- RED -> GREEN -> refactor with focused tests.
- Run harness 29/29, typecheck/lint/build, focused Python/frontend/E2E, actionlint/security checks, git diff --check, then proportional full regression.
- Perform independent security review of release workflow changes.
- Make small coherent commits on your worktree branch; do not merge, force-push, or mutate the user's main checkout. Report commit SHAs and exact verification.
- After CI closure, identify remaining external-only work: merge to main, canonical exact-six image producer, immutable digest Docker smoke, staging Kubernetes/TLS/observability/CWV, production/release and SHA-bound audit. Do not claim completion without evidence.

Что конкретно осталось в коде и CI:
Исправить CodeQL-замечание в release.yml: сейчас workflow_dispatch позволяет privileged checkout SHA, пришедшего из недоверенного input.
Сделать миграцию 148642dd1207 безопасной для PostgreSQL:изменение типа groups.id;
установка NOT NULL для active_sessions.signing_key.

Исправить backend-тест dead-letter UUID: тест использует невалидные строки вместо валидных дублирующихся UUID.
Починить изолированную среду Python mutation testing: в дереве мутантов отсутствует security/audit-allowlist.yaml.
Закрыть frontend unit failures:асинхронное сохранение профиля/snackbar;
отдельная ошибка или unhandled rejection в первом шарде.

Закрыть Playwright-регрессии:sessions accordion;
MFA recovery-code form;
неоднозначные заголовки и кнопки;
offline state;
навигационная гонка News/Events;
Firefox/WebKit-специфичные сбои.

После стабилизации frontend unit/E2E повторно прогнать Stryker: многие mutation shards сейчас падают ещё на initial dry run.
Повторить отменённый dark unauthenticated smoke и дождаться завершения Schemathesis, Lighthouse и оставшихся matrix jobs.
Создать и отправить исправляющие коммиты, затем добиться полностью зелёной fresh CI-матрицы на новом SHA.