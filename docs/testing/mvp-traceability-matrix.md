# MVP Block 4 traceability matrix (ТЗ §2–13)

Verified against source on 2026-11-13; results pending hosted runs.

## Purpose

This matrix maps each applicable item of the MVP technical specification
(`docs/superpowers/plans/University_Ecosystem_MVP.md`, sections 2–13) to the
automated scenario that confirms it, the lane and browser matrix the scenario
actually runs, and the gaps that remain. It is the Block 4 evidence index for
the MVP stage-3 acceptance in
`docs/superpowers/plans/MVP_MASTER_PLAN.md`. The "Result on SHA" column is
filled only from hosted runs on `main`; no run is claimed here.

## Sources

- ТЗ: `docs/superpowers/plans/University_Ecosystem_MVP.md`, sections 2–13.
- Plan: `docs/superpowers/plans/MVP_MASTER_PLAN.md`, Block 4 (RU/EN and
  viewport policy, area bullets, acceptance).
- Live lane: `frontend/tests/e2e-live/*.live.spec.ts`, configured by
  `frontend/playwright.live.config.ts`.
- Mocked lane: `frontend/tests/e2e/*.spec.ts`, configured by
  `frontend/playwright.config.ts`.
- Unit: vitest files under `frontend/src/**/__tests__/` and `frontend/src/**/*.test.ts(x)`.
- Backend: pytest under `tests/`; files under `tests/integration/` need
  Postgres, Redis or Mailpit as noted per row.

Scenario cells give paths relative to `frontend/tests/` (live and mocked),
`frontend/` (unit) or the repository root (backend), followed by the exact
test title. Titles with `${...}` are templates; the parameter
values are stated in the row.

## Lane key

| Lane | Source | What the run actually uses |
|---|---|---|
| live | `frontend/tests/e2e-live/` | Real backend, database and seeded roles. Projects `desktop` (Desktop Chrome, 1440x900) and `mobile` (Pixel 7 device, 390x844). Both are Chromium. Config sets `locale: "ru-RU"`; dark theme is not set globally. `workers: 1`. A spec that calls `setViewportSize` overrides its project viewport, so the project name does not set the width for those specs. |
| mocked | `frontend/tests/e2e/` | Mocked API. Projects `chromium` (Desktop Chrome, default 1280x720), `firefox`, `webkit`, `mobile-webkit` (iPhone 15). The config does not set a locale; a spec runs in the Playwright default unless it sets the app language. Many specs skip non-Chromium projects or set their own viewport. |
| unit | `frontend/src/**` | vitest with jsdom. No layout engine: geometry claims are class or style checks only. |
| backend | `tests/` | pytest. Integration files need a live service as noted. |

Lane names in the table refer to these four lanes only.

## Status key

- **FULL**: an assertion covers the requirement in the lane that matters.
  Delivery, authentication, permissions and Web Push require the live lane.
- **PARTIAL**: an assertion covers part of the requirement, or only one
  width, locale or theme, or only unit or static checks.
- **NONE**: no test found for the requirement.
- **n/a**: a process item, not a product scenario.

## Matrix

Run matrix column: viewport(s), locales and themes the test body runs.
"project" means the width comes from the live project (1440 desktop, 390 mobile).

| ID | ТЗ item | Scenario | Lane | Run matrix | Not covered | Status | Result on SHA |
|---|---|---|---|---|---|---|---|
| R01 | §2 «Интерфейс входа и регистрации… минималистичного окна» | mocked `e2e/a11y-public.spec.ts` :: `${route.name} — ${theme.name} theme has no critical/serious axe violations` (routes `login`, `fallback`) | mocked | chromium 1280x720 (WebKit and mobile WebKit partly skipped); light and dark; locale not set | Registration page is not in the route list; no layout geometry; no 390/768/1440 | PARTIAL | pending hosted run |
| R02 | §2 «Регистрация» (form submit) | live `e2e-live/register-double-submit.live.spec.ts` :: `rapid double submit on a 360px registration form creates one account` | live | 360x800 (set by spec) in both projects; ru | Full registration form at 390/768/1440; EN; only the double-submit path | PARTIAL | pending hosted run |
| R03 | §2 «Провести аудит… подключения приложений-аутентификаторов (TOTP)» | live `e2e-live/totp-recovery.live.spec.ts` :: `TOTP enrollment enables login and recovery codes are single-use` | live | project viewport (1440, 390); ru | Enrollment UI at 360/768; EN | FULL | pending hosted run |
| R03b | §2 TOTP UI | mocked `e2e/mfa.spec.ts` :: `allows enabling TOTP in settings`; `completes login when an OTP challenge is returned`; `shows an error for invalid OTP attempts and allows retry` | mocked | default viewport in all four projects; locale not set | Mock only; does not prove backend TOTP | FULL | pending hosted run |
| R03c | §2 TOTP enrollment limits and races | backend `tests/test_aud237_totp_enrollment_revocation.py` :: `test_revoked_totp_enrollment_cannot_be_reactivated`; `test_concurrent_pending_totp_confirmations_share_one_factor_slot`; `test_active_totp_confirmation_remains_retryable_with_a_valid_code`; `test_pending_totp_confirmation_rechecks_the_one_factor_limit`; backend `tests/integration/test_infrastructure.py` :: `test_totp_budget_concurrent_redis_checks_are_atomic` (needs Redis) | backend | n/a | Enrollment-limit races are backend-only | FULL | pending hosted run |
| R04 | §2 «одноразовые коды на электронную почту» (login) | live `e2e-live/email-otp-mfa-login.live.spec.ts` :: `verified email OTP MFA is required and completes a fresh browser login` | live | project viewport (1440, 390); ru | EN; OTP entry at 360/768 | FULL | pending hosted run |
| R04b | §2 email OTP verification, resend, replay | live `e2e-live/email-otp-verification.live.spec.ts` :: `email verification retries, rotates its code on resend, and rejects replay` | live | project viewport; ru | The 429 branch is conditional (`if (rejected.status() === 429)`), so the test can pass without the limit being hit | FULL | pending hosted run |
| R04c | §2 email OTP UI | mocked `e2e/email-mfa.spec.ts` :: `shows the masked delivery hint and completes email-only login`; `enforces resend cooldown, rotates the token, and retries a wrong code`; `can return from recovery-code entry to the email challenge` (inside `Email MFA browser contract (${locale})`) | mocked | locale loop (ru, en); all four projects | Mock only | FULL | pending hosted run |
| R04d | §2 email OTP outbox and SMTP | backend `tests/integration/test_mfa_mailpit_outbox.py` :: `test_email_mfa_handler_outbox_smtp_retry_and_resend` (Postgres and Mailpit); `tests/test_mfa_smtp_deadline_contract.py` :: `test_hung_connect_is_abandoned_at_the_total_deadline`; `tests/test_mfa_smtp_cancellation_contract.py` :: `test_smtp_total_deadline_closes_a_drip_fed_connection`; `test_lost_data_ack_retries_with_the_same_message_id`; `test_smtp_cancellation_aborts_transport_and_cannot_send_later`; `test_smtp_failure_redacts_provider_content_and_closes_socket`; `test_durable_mfa_dispatch_failure_is_pii_free` | backend | n/a | Requires a Linux run bound to the SHA | FULL (pending Linux run) | pending hosted run |
| R05 | §2 «Упразднить… аппаратных ключей безопасности (Security Keys)» (negative) | backend `tests/test_mfa_webauthn_tombstone.py` :: `test_runtime_has_no_webauthn_references_or_models`; `test_webauthn_dependency_is_retired`; `test_security_policy_describes_only_current_mfa_factors`; `tests/test_mfa_openapi_artifacts_contract.py` :: `test_generated_types_sdk_and_msw_have_no_retired_authenticator_surface` | backend | n/a | No live or UI absence check; a grep of `frontend/src` finds no WebAuthn strings, but that grep is not a test | PARTIAL | pending hosted run |
| R06 | §2 «recovery, reset и token reuse» | live `e2e-live/password-reset.live.spec.ts` :: `a student resets with the Mailpit link without retaining tokens or following hostile redirects`; `legacy ${source} reset entry removes its token after the edge redirect` (source `query`, `path`) | live | project viewport; ru | EN; token reuse asserted only as HTTP 400 | FULL | pending hosted run |
| R07 | §2 «cooldown/TTL/attempt limits, правильные 401/429» | live `e2e-live/auth-login-lockout.live.spec.ts` :: `synthetic account reaches account lockout after the configured failed-login threshold` (401 per wrong attempt, then lockout); mocked `e2e/rate-limit-ux.spec.ts` :: `a persistent 429 shows a load error and manual retry recovers`; `retries a 429 after Retry-After and renders the successful response` | live + mocked | live: project viewport; ru. mocked: chromium and other projects | TTL expiry not tested; 429 from auth endpoints not asserted as a hard status | PARTIAL | pending hosted run |
| R08 | §2 «safe redirect» | live `e2e-live/auth-safe-redirect.live.spec.ts` :: `seeded login keeps ${label} on the same origin` (absolute external URL, protocol-relative URL, slash-backslash URL); mocked `e2e/login-flow.spec.ts` :: `state.from preservation: /login?redirect=/events lands on /events (W179 SW4)` | live + mocked | live: project viewport; ru. mocked: chromium only | Hostile redirect after reset is in R06 | FULL | pending hosted run |
| R09 | §2 session revocation (sibling sessions) | live `e2e-live/email-otp-mfa-login.live.spec.ts` :: `verified email OTP MFA is required and completes a fresh browser login` (body asserts the sibling WebSocket closes with code 4401 and reason "Session revoked"); mocked `e2e/app.spec.ts` :: `allows revoking secondary sessions from settings` | live + mocked | live: project viewport; ru. mocked: default viewport | Revocation through the settings UI is not in the live lane | FULL | pending hosted run |
| R10 | §3 «Оптимизировать логику трансформации навбара… Устранить просадки FPS» | live `e2e-live/navbar-layout-stability.live.spec.ts` :: `navbar compact-on-scroll keeps layout shift below 0.1` (desktop only; the body runs the RU/EN × light/dark spacing matrix at 1440, 1349 and 1350) | live | desktop 1440; ru and en; light and dark (the matrix); mobile skipped | FPS and frame timing are not measured anywhere (the spec uses requestAnimationFrame only to wait for layout); compact-on-scroll on mobile has no CLS check | PARTIAL | pending hosted run |
| R11 | §3 «полноценная поддержка логики на мобильных устройствах» (mobile navbar) | live `e2e-live/navbar-layout-stability.live.spec.ts` :: `mobile navbar shell geometry stays fixed through scrolling and route navigation` | live | 390 (set by spec) in both projects; ru | 360 and 768 not run; FPS on mobile not measured; no EN | PARTIAL | pending hosted run |
| R12 | §3 «Убрать лишнюю нижнюю подсветку (glow-эффект)» | unit `src/components/navbar/__tests__/NavbarPill.test.tsx` :: `uses only transform and opacity transitions without glow or breathing` | unit | jsdom | No visual or pixel check of the glow | PARTIAL | pending hosted run |
| R13 | §3 «Подвал сайта… SVG-иконку Telegram… унифицировать ссылки» | unit `src/components/layout/__tests__/Footer.test.tsx` :: `renders 2 social buttons (Telegram + Email) with aria-labels + security attrs`; `renders all 7 footer navigation links with footer-link-premium class`; `uses a filled four-track grid without media-query-driven glow` | unit | jsdom | Telegram SVG appearance not checked; no live footer look | PARTIAL | pending hosted run |
| R13b | §3 footer on phones | live `e2e-live/footer-bottom-navigation.live.spec.ts` :: `footer clears the bottom navigation on short and long production pages` (`/activity` and `/news`) | live | 390 (set by spec) in both projects; ru | 360, 768 and 1024 not run | PARTIAL | pending hosted run |
| R14 | §4 «Новости: …сброса скролла… при выборе… категорий по тегам» | mocked `e2e/category-scroll-stability.spec.ts` :: `${feed.path} categories never reset the scroll position to the top` (FEEDS `/events` and `/news`, so one template gives two tests) | mocked | chromium, firefox, webkit at 1280x800; mobile-webkit at iPhone 15 viewport; locale not set; fake clock 2026-06-27 | No live tag-change test; mock only | PARTIAL | pending hosted run |
| R14b | §4 news category bar stays the same height when sticky (supports R14) | mocked `e2e/category-scroll-stability.spec.ts` :: `news category bar keeps the same height when it becomes sticky` (2 px tolerance) | mocked | chromium 1280x800; mobile-webkit at iPhone 15 viewport | Mock only; not a live check | PARTIAL | pending hosted run |
| R15 | §4 «Мероприятия: …скачка страницы вверх при смене категории событий» | mocked `e2e/category-scroll-stability.spec.ts` :: `/events categories never reset the scroll position to the top` (same template as R14) | mocked | as R14 | Mock only; the events status tabs (Актуальные, Прошедшие) are not the category filter and are not tested here | PARTIAL | pending hosted run |
| R16 | §4 «сохранение scroll, back/forward» | live `e2e-live/news-scroll-restoration.live.spec.ts` :: `News feed Back/Forward restores the seeded article position in Russian and English`; live `e2e-live/events-scroll-restoration.live.spec.ts` :: `browser history restores the Events archive position in ${locale.code}` (ru, en); mocked `e2e/events-history-scroll-restoration.spec.ts` :: `events back navigation restores the feed reading position` | live + mocked | live: project viewport; ru and en. mocked: default | Tag change followed by Back is not tested | FULL | pending hosted run |
| R17 | §4 «Карта кампуса: …подброс… страницы… при взаимодействии с картой»; §5 «Коррекция взаимодействия» | live `e2e-live/map-gesture-isolation.live.spec.ts` :: `live map captures wheel zoom without page scroll or center drift` (1440, chromium); `live map leaves page scrolling available outside the map` (1440); `live mobile map keeps pinch and one-finger pan inside the map` (390); mocked `e2e/map-wheel-isolation.spec.ts` :: `MapLibre captures wheel zoom without scrolling the page or shifting its viewport`; `MapLibre captures a mobile two-finger pinch without page zoom or scroll` | live + mocked | live: chromium only; mocked: chromium only | The jump at the end of the interaction is not sampled as a separate check; no Firefox or WebKit live | PARTIAL | pending hosted run |
| R18 | §4 «Мероприятия: …выровнять строго по центру» (status tabs) | unit `src/features/events/components/__tests__/EventsHeader.test.tsx` :: `centers the status tablist across the available width`; `renders the sliding tab indicator with and without reduced motion`; live `e2e-live/events-tab-keyboard.live.spec.ts` :: `Events status tabs are keyboard navigable` (keyboard only, no geometry) | unit + live | unit: jsdom; live: project viewport, reduced motion, ru | No geometry (±1 px) check for the Events slider in any lane | PARTIAL | pending hosted run |
| R19 | §4 «Активность: отцентрировать ползунок… периодов» | live `e2e-live/activity-summary.live.spec.ts` :: `seeded student can view Activity summaries, change the period, and restore it after reload` (indicator matches the selected radio within 1 px on x, y, width and height) | live | project viewport (1440, 390); ru only; reduced motion | EN content not run (the spec's EN regex is never exercised); 360 and 768 not run | FULL | pending hosted run |
| R19b | §4 Activity period slider in the mocked lane | mocked `e2e/url-state-persistence.spec.ts` :: `/activity period persists across reload` | mocked | chromium only | No geometry assertion | PARTIAL | pending hosted run |
| R20 | §5 «лаги и микрофризы… при… анимациях зума» | live `e2e-live/map-zoom-longtask.live.spec.ts` :: `live MapLibre zoom has no main-thread long task at or above 50 ms` (longtask observer starts after the canvas is visible and the camera is finite; only zoom-in button steps are measured) | live | project viewport (1440, 390); ru; chromium only | Zoom only; wheel and pinch zoom not measured | PARTIAL | pending hosted run |
| R21 | §5 «лаги и микрофризы при первичной загрузке компонента карты» | none. The `measurementAvailable` block in `map-zoom-longtask` starts after the initial camera is read, so the first load is excluded | none | n/a | First-load long tasks are not measured in any lane | NONE | pending hosted run |
| R22 | §6 «Полный UI/UX редизайн»; «плавная отправка/получения сообщений» | live `e2e-live/messenger-realtime.live.spec.ts` :: `shows sent confirmation after the server accepts the message`; `a message is delivered, edited, and tombstoned in the other authenticated session` (ru/en × light/dark sample loop inside the test) | live | project viewport (1440, 390); ru base with ru/en × light/dark samples | Delivery is covered; the visual redesign is not (see manual checks); no 360 or 768 | PARTIAL | pending hosted run |
| R23 | §6 «Группы: …DM/groups, ordering/deduplication, reconnect» | live `e2e-live/messenger-reconnect-ordering.live.spec.ts` :: `two synthetic users receive ordered, exactly-once messages sent during a real reconnect` (direct chat); live `e2e-live/messenger-reconnect.live.spec.ts` :: `reconnect replays a missed message once in sequence and receives the next live message`; live `e2e-live/messenger-realtime.live.spec.ts` :: `direct-message replay stays ordered and exactly once across receiver reconnect` | live | project viewport; ru | All reconnect tests use direct chats; group ordering and deduplication across reconnect are not tested live | PARTIAL | pending hosted run |
| R24 | §6 reply, edit, delete, forward, reactions, typing | live `e2e-live/messenger-realtime.live.spec.ts` :: `a receiver reaction is delivered to the sender over the live WebSocket`; `a sender reply preserves its parent identity and reaches the receiver` (ru/en loop); `forwarding through the current-chat modal preserves attribution and reaches the receiver` (ru/en × light/dark loop); `a peer typing indicator appears and expires over the live socket` | live | project viewport; ru and en (in loops) | Delete (tombstone) is in R22 | FULL | pending hosted run |
| R25 | §6 «unread: прочтение участником A не сбрасывает unread участника B» | live `e2e-live/messenger-unread-read.live.spec.ts` :: `a real DM read receipt clears only that chat's unread state` (sender bubble sampled in ru and en × light and dark) | live | project viewport; ru and en × light and dark samples | Mock list unread is not checked | FULL | pending hosted run |
| R26 | §6 attachments: no unauthorised access; oversized uploads rejected | live `e2e-live/chat-attachment-isolation.live.spec.ts` :: `a non-member cannot download private attachments and oversized uploads are rejected` (ru/en × light/dark loop) | live | project viewport (1440, 390); ru and en × light and dark | Forwarded attachment deletion is backend-only (R27) | FULL | pending hosted run |
| R27 | §6 blob deletion only after the last reference is removed; safe redelivery | backend `tests/integration/test_chat_attachment_legacy_refs_postgres.py` :: `test_last_legacy_attachment_reference_controls_blob_lifetime` (Postgres); `tests/test_attachment_cleanup_reference_guard.py` :: `test_cleanup_skips_legacy_url_still_referenced_by_another_attachment`; `test_cleanup_database_error_never_deletes_an_unverified_blob`; `test_durable_cleanup_accepts_ambiguous_delete_only_after_absence_probe`; `test_durable_cleanup_naks_when_ambiguous_delete_cannot_be_verified` | backend | n/a | No live check | FULL | pending hosted run |
| R28 | §6 «Группы: min 3 / max 100 участников при создании» | backend `tests/test_chat_creation_service.py` :: `test_create_group_rejects_too_few_members` (two total rejected); `tests/test_chat_creation_service_closure.py` :: `test_create_group_rejects_too_many_and_missing_member` (100 other members, so 101 total, rejected; missing member gives 404); `tests/test_chat_api.py` :: `test_create_group_too_few_members` | backend | n/a | Exact accept boundaries (3 total and 100 total) are not asserted; the too-few test catches `Exception` broadly | PARTIAL | pending hosted run |
| R29 | §6 permissions: add and rename by members; remove by owner or self; 403 for outsiders; group operations refused for DM | live `e2e-live/messenger-membership-revocation.live.spec.ts` :: `a removed member loses detail, history, reactor, attachment, send, and live access`; live `e2e-live/messenger-group-isolation.live.spec.ts` :: `group events reach both members and never reach an authenticated non-member` (asserts 403 for a denied chat read and for a non-member send); mocked `e2e/group_management.spec.ts` :: `creates a group and manages members/title in group info panel` | live + mocked | live: project viewport; ru. mocked: chromium only | No live add/rename permission matrix; no live assertion that group operations are refused for a DM | PARTIAL | pending hosted run |
| R30 | §6 «после изменения membership старый WS/cache не сохраняет доступ» | live `e2e-live/messenger-membership-revocation.live.spec.ts` :: `a removed member loses detail, history, reactor, attachment, send, and live access` | live | project viewport; ru | Browser storage cache contents are not checked directly | FULL | pending hosted run |
| R31 | §6/§11 group message notification carries group name and author; quoted author gets one `chat.reply` | live `e2e-live/push-delivery.live.spec.ts` :: `quoted group author gets one chat.reply push with group context and no generic duplicate` (asserts the push title equals the group name; three participants) | live | project viewport; ru; Google Chrome persistent profile (skips elsewhere) | Other Web Push paths outside this test are covered in R51 | FULL | pending hosted run |
| R32 | §6 «Адаптивность… на смартфонах» (messenger) | mocked `e2e/visual-regression.spec.ts` :: `messenger page matches mobile snapshot` (375x812) and `messenger page matches desktop snapshot` (1280x720), both skipped unless `win32`; mocked `e2e/a11y-messenger.spec.ts` :: `messenger — ${theme.name} theme has no critical/serious axe violations`; live `e2e-live/messenger-a11y.live.spec.ts` :: `Messenger dialog supports keyboard access, restores scroll, and meets hit-target sizes` | mocked + live | snapshots: Chromium on Windows only. a11y mocked: Chromium light and dark. live: 360x800 (mobile project) and 1440x900 (desktop project) | Snapshot baselines exist only for Windows; no 768 in any messenger spec; no Linux baseline | PARTIAL | pending hosted run |
| R33 | §7 «полноценный личный кабинет»; «оптимизировать перерисовку… при обновлении данных» | live `e2e-live/profile-persistence.live.spec.ts` :: `profile editor cancellation and rejected oversized save preserve values before success`; `profile API rejects email changes outside the verified change flow`; live `e2e-live/avatar-persistence.live.spec.ts` :: `avatar upload persists across reload and rolls back server-rejected content` | live | project viewport; ru | Re-render counts are not measured; EN | FULL | pending hosted run |
| R34 | §7 «адаптивная сетка под все диапазоны» | mocked `e2e/profile-responsive.spec.ts` :: `profile grid remains responsive at mobile, tablet, and desktop widths` (390 stacked, 768 stacked, 1440 columns) | mocked | 390, 768, 1440; all four projects; locale not set | Not in the live lane; 360 and 1024 not run | FULL | pending hosted run |
| R35 | §7 «существующие достижения» (AchievementsSection kept) | unit `src/components/profile/__tests__/AchievementsSection.test.tsx` :: `uses the issuer fallback and reports the clicked achievement` | unit | jsdom | No end-to-end check | PARTIAL | pending hosted run |
| R36 | §7 and §2 CSRF on profile update | live `e2e-live/profile-csrf.live.spec.ts` :: `authenticated profile update rejects missing and invalid CSRF proof` | live | project viewport; ru | Only the profile write endpoint; other writes are not in the live lane | FULL (profile only) | pending hosted run |
| R37 | §8 «Редизайн модуля настроек… структуры»; «проверить сохранение, валидацию и применение» | live `e2e-live/settings-tabs-keyboard.live.spec.ts` :: `Settings tabs follow APG keyboard focus, activation, and panel association`; live `e2e-live/settings-password-change-rollback.live.spec.ts` :: `password settings reject a wrong current password and persist a corrected change`; live `e2e-live/settings-radio-focus.live.spec.ts` :: `Settings radio has a visible keyboard focus style`; `Semantic tokens preserve percentage alpha in both themes`; `Settings Snackbar content receives a real pointer click on Profile` | live | project viewport; ru; both themes in the token test | EN; the visual redesign is not checked (see manual checks) | FULL | pending hosted run |
| R38 | §8 theme and language preferences persist | live `e2e-live/settings-theme-roundtrip.live.spec.ts` :: `theme and language preferences survive reload and are restored` (ru and en; light and dark) | live | project viewport; ru, en; light, dark | Not checked after a device change | FULL | pending hosted run |
| R39 | §8 «пустые или некорректные ключи… сырых ключей в UI» (SSR pages) | live `e2e-live/ssr-hydration-i18n.live.spec.ts` :: `Russian dashboard SSR hydrates and preserves i18n across News navigation`; `English dashboard SSR hydrates and preserves i18n across News navigation`; `a public route renders one localized page metadata set instead of the root fallback`; live `e2e-live/schedule-hydration-i18n.live.spec.ts` :: `Russian schedule SSR markup hydrates without raw i18n keys`; `English schedule SSR markup hydrates without raw i18n keys` | live | project viewport; ru and en | Raw keys on settings, messenger and profile pages are not checked live | FULL (dashboard and schedule) | pending hosted run |
| R39b | §8 i18n parity across the app | unit `src/tests/pageTranslations.test.tsx` :: `switches activity page translations`; `switches settings translations including notifications`; unit `src/tests/translationParity.test.ts` :: `${lng} has matching keys in ${relativePath}`; mocked `e2e/i18n-switching.spec.ts` :: `switching locale updates visible text`; `settings language switcher changes locale in authenticated view` | unit + mocked | unit: jsdom; mocked: locale loop inside the spec | Static key parity is checked by the scanner (see `docs/testing/i18n-gate.md`); rendered raw-key detection is not run on every page | PARTIAL | pending hosted run |
| R40 | §9 «Улучшить представление… heatmap, trends, grades и comparison» (populated state) | unit `src/features/activity/components/__tests__/ActivityHeatmap.test.tsx` :: `renders exact heat levels, boundaries, labels, and legend semantics`; `src/features/activity/components/__tests__/ActivityTrendChart.test.tsx` :: `renders the trend svg + sr-only table with >= 2 points`; `src/features/activity/components/__tests__/ActivityComparativeCard.test.tsx` :: `renders a positive delta as an up-trend`; `src/features/activity/components/__tests__/GradesCard.closure.test.tsx` :: `renders 100-point formatting and rounds the animated value` | unit | jsdom | The live seed has no attendance or grades, so no populated Activity state is rendered end to end | PARTIAL | pending hosted run |
| R40b | §9 empty Activity baseline | live `e2e-live/activity-dashboard.live.spec.ts` :: `seeded student sees the supported empty Activity baseline` | live | project viewport; ru; reduced motion | Empty state only; EN | PARTIAL (empty state only) | pending hosted run |
| R41 | §9 «Не добавлять учебные цели, attendance или иные предметные функции» (negative) | none. `activity-dashboard.live.spec.ts` asserts the existing attendance widget at zero; that is a positive check of an existing widget, not a negative check | none | n/a | No assertion that no new goals or attendance features exist | NONE | pending hosted run |
| R42 | §10 Stories open by click on the avatar or circle | live `e2e-live/story-viewer-keyboard.live.spec.ts` :: `a seeded story traps focus, closes with Escape, restores focus, and releases scroll lock`; unit `src/components/stories/__tests__/DashboardStories.navigation.test.tsx` :: `navigates the real viewer without an optional story callback or uncaught errors` | live + unit | project viewport (1440, 390); ru | Live opening by a tap on a phone-size viewport is covered only by the mobile project | FULL | pending hosted run |
| R43 | §10 Stories keyboard and swipe | unit `src/components/stories/__tests__/StoryViewer.keyboard-close.test.tsx` :: `closes on Escape and returns focus to the story trigger`; unit `src/components/stories/__tests__/DashboardStories.closure.test.tsx` :: `closes safely when stories disappear before previous navigation`; unit `src/hooks/useSwipe.test.ts` :: `triggers onSwipeRight on a long fast horizontal +x swipe`; `triggers onSwipeLeft on a long fast horizontal -x swipe`; unit `src/hooks/useSwipeGesture.test.ts` :: `fires onSwipeClose past threshold and resets state` | unit | jsdom | No live ArrowLeft or ArrowRight test; no live or mocked touch swipe on the story viewer; `useSwipe` is tested as a generic hook, not as wired into the viewer | PARTIAL | pending hosted run |
| R44 | §10 Stories pause in hidden state | live `e2e-live/story-viewer-keyboard.live.spec.ts` :: `a seeded story pauses while hidden and resumes at the preserved progress`; `a seeded story preserves elapsed playback across a clock-controlled hidden tab` | live | project viewport (1440, 390); ru | Background-tab behaviour on a real mobile browser | FULL | pending hosted run |
| R45 | §10 and §13 «без утечек памяти» (Stories) | live `e2e-live/story-viewer-memory.live.spec.ts` :: `a seeded story viewer reaches a memory plateau after 20 open-close cycles` (asserts heap plateau, stable DOM counters and no story write requests) | live | project viewport (1440, 390); ru | Listener counts are collected but not asserted; only Stories are covered | FULL | pending hosted run |
| R46 | §10 Stories under reduced motion | live `e2e-live/story-viewer-reduced-motion.live.spec.ts` :: `StoryViewer stays keyboard-operable without meaningful motion under reduced motion` | live | project viewport; ru; reduced motion | — | FULL | pending hosted run |
| R47 | §10 «Отключить покачивание карточек при наведении на главной» | unit `src/components/dashboard/__tests__/DashboardHero.closure.test.tsx` :: `renders personalized greeting, a static special marker, and stories` (asserts no `group-hover:translate-x` class) | unit | jsdom | Class-level only; no live hover check | PARTIAL | pending hosted run |
| R48 | §10 functional hover micro-UX (scale and outline) | unit `src/components/dashboard/__tests__/DateBullet.closure.test.tsx` :: `renders a formatted default bullet` (asserts `hover:scale-105`); unit `src/components/dashboard/__tests__/EventsCard.test.tsx` :: `preserves the shell, event identity, and reduced-motion animation contracts` | unit | jsdom | Class-level only | PARTIAL | pending hosted run |
| R49 | §10 «пустые блоки не должны резервировать лишнее пустое пространство» (Home) | unit `src/components/dashboard/__tests__/ScheduleCard.test.tsx` :: `renders the empty state when a loaded student schedule has no data`; unit `src/components/dashboard/__tests__/EventsCard.test.tsx` :: `shows the empty state when no events match the scope`; unit `src/components/dashboard/__tests__/NewsCardList.test.tsx` :: `renders the empty-state message when there is no news and not loading` | unit | jsdom (no layout) | No vertical-gap geometry test in any lane | NONE (geometry) | pending hosted run |
| R50 | §11 publication of news, schedule changes, event announcements, service notices | live `e2e-live/notification-topics-delivery.live.spec.ts` :: `news, events, schedule changes and system releases reach the opted-in Chromium recipient` | live | project viewport; ru; Google Chrome persistent profile | Other browsers are out of scope for Web Push | FULL | pending hosted run |
| R51 | §11 new personal and group messages (in-app and push, dedup, quiet hours) | live `e2e-live/notification-in-app.live.spec.ts` :: `chat message creates one in-app notification during quiet hours and remains read and unique after reload`; live `e2e-live/push-delivery.live.spec.ts` :: `chat message reaches Chromium through its real push subscription` | live | project viewport; ru; Google Chrome persistent profile (push); Chromium (in-app) | — | FULL | pending hosted run |
| R52 | §11 quiet hours and opt-out | live `e2e-live/notification-preferences.live.spec.ts` :: `notification topics and quiet hours persist across reload and opt-out`; live `e2e-live/push-subscription.live.spec.ts` :: `Chromium push opt-in persists one native subscription and removes it on opt-out` | live | project viewport; Google Chrome persistent profile | — | FULL | pending hosted run |
| R53 | §11 browser permission requested only after an explicit user action | live `e2e-live/push-delivery.live.spec.ts` :: `permission is requested only after the explicit settings action`; live `e2e-live/push-permission-default.live.spec.ts` :: `Chromium leaves notification permission at default when settings are only opened`; live `e2e-live/push-permission-denied.live.spec.ts` :: `Chromium shows the denied notification permission without creating a subscription` | live | project viewport; ru; Chromium only; the subscribing push-delivery scenario runs in Google Chrome | — | FULL | pending hosted run |
| R54 | §11 «всплывающее окно предложения включить уведомления, его положением и отображением» | mocked `e2e/push-context-geometry.spec.ts` :: `contextual push offer stays inside 360x640`; `contextual push offer stays inside 1440x900`; unit `src/pages/settings/sections/__tests__/NotificationsSection.closure.test.tsx` :: `renders initialization, unsupported, and denied permission states` | mocked + unit | mocked: chromium at 360x640 and 1440x900 only; Notification API mocked; locale not set | No 390 or 768; no live check of the offer position; overlay display in real Chromium is not asserted | PARTIAL | pending hosted run |
| R55 | §11 in-app toast instead of system notification for visible clients | mocked `e2e/notifications.spec.ts` :: `shows in-app toast instead of system notification for visible clients` | mocked | default viewport; all four projects | Mock only | FULL (mock) | pending hosted run |
| R56 | §12 «Бургер-меню: …анимации выдвижения и компоновки» | live `e2e-live/navbar-layout-stability.live.spec.ts` :: `mobile drawer traps keyboard focus, closes with Escape, and releases scroll lock` (390 and 360); live `e2e-live/navbar-layout-stability.live.spec.ts` :: `tablet overflow navigation is keyboard operable and restores focus on Escape` (1024) | live | 390, 360 and 1024 (set by spec); ru | Drawer slide animation and the visual redesign are not asserted; 768 not run | PARTIAL | pending hosted run |
| R57 | §12 «Нижняя навигационная панель… геометрии… выравнивание секторов нажатия» | live `e2e-live/footer-bottom-navigation.live.spec.ts` :: `bottom navigation fits phones and the navbar drawer works at the tablet boundary` (bottom nav fixed, 44 px targets, edges inside the viewport at 390 and 360; drawer at 1024) | live | 390 and 360 (set by spec) in both projects; 1024; ru | Icon centring is not checked; 768 not run | PARTIAL | pending hosted run |
| R58 | §12 «отладка эффектов активного/нажатого состояния кнопок» | live `e2e-live/footer-bottom-navigation.live.spec.ts` :: `bottom navigation fits phones and the navbar drawer works at the tablet boundary` (asserts `aria-current="page"` after keyboard Enter on `/news`) | live | 390 and 360; ru | Pressed (`:active`) feedback and its visual state are not tested | PARTIAL | pending hosted run |
| R59 | §12 «Повышение производительности… при быстрых тапах и переходах» | none for the bottom navigation or drawer. `e2e-live/register-double-submit.live.spec.ts` covers rapid double submit on a form, not navigation | none | n/a | No rapid-tap test; no frame timing | NONE | pending hosted run |
| R60 | §12 hit-target geometry (44 px) | live `e2e-live/new-chat-hit-targets.live.spec.ts` :: `NewChat controls meet WCAG target sizes at mobile and desktop widths` (360x800 mobile, 1440x900 desktop); mocked `e2e/target-size-geometry.spec.ts` :: `foundation targets — navbar actions`; `foundation targets — shared Select options`; `foundation targets — schedule export menu` | live + mocked | live: 360 (mobile project), 1440 (desktop project); mocked: spec viewport | Stories and messenger list targets are not included | PARTIAL | pending hosted run |
| R61 | §12 focus trap, Escape and focus restore | live `e2e-live/messenger-focus-trap.live.spec.ts` :: `Tab and Shift+Tab keep focus inside the read-only new-chat dialog`; live `e2e-live/search-dialog-keyboard.live.spec.ts` :: `SearchDialog traps Tab and restores the original focus`; live `e2e-live/messenger-keyboard-focus.live.spec.ts` :: `Escape closes the new-chat dialog and restores keyboard focus to its trigger`; live `e2e-live/story-viewer-keyboard.live.spec.ts` :: `a seeded story traps focus, closes with Escape, restores focus, and releases scroll lock` | live | project viewport; ru | — | FULL | pending hosted run |
| R62 | §12 and §2 «200% zoom» | live `e2e-live/schedule-200-equivalent-reflow.live.spec.ts` :: `schedule reflows and remains keyboard-usable at a 200%-equivalent CSS viewport` (720x450, desktop project only) | live | 720x450; ru; desktop project only | Only the schedule; not News, messenger or profile; not on the mobile project | PARTIAL | pending hosted run |
| R63 | §12 and §2 reduced motion | mocked `e2e/a11y-enhanced.spec.ts` :: `/login — prefers-reduced-motion collapses animation durations`; unit `src/components/layout/__tests__/MobileBottomNav.reducedMotion.closure.test.tsx` :: `uses CSS reduced-motion fallbacks for the indicator and stable label`; live R46 (stories) | mocked + unit + live | mocked: chromium; unit: jsdom; live: stories only | Reduced motion of the bottom navigation is not checked in a browser | PARTIAL | pending hosted run |
| R64 | master Security and a11y: no serious or critical axe findings | live `e2e-live/core-a11y-live.live.spec.ts` :: `real student dashboard and settings have no serious or critical axe findings`; mocked `e2e/accessibility.spec.ts` :: `authenticated routes have no critical or serious axe violations` (skipped unless the `URL_STATE_E2E=true` build runs) | live + mocked | live: project viewport; ru. mocked: gated off by default | Authenticated axe in the mocked lane is gated off by default; messenger and profile live axe are not in this spec (messenger has R32) | FULL (live dashboard and settings) | pending hosted run |
| R65 | master SSR and PWA: no hydration mismatch | mocked `e2e/hydration.spec.ts` :: `does not produce React hydration errors on main SSR entrypoints`; live `e2e-live/production/ssr-document-render.spec.ts` :: `the requested language decides the server markup and not the other locale`; `${path} renders ${language} on the server with a bootstrap for hydration` | mocked + live | live: production SSR; ru and en | — | FULL | pending hosted run |
| R66 | master SSR and PWA: correct 404 | live `e2e-live/not-found-i18n.live.spec.ts` :: `unknown public document returns the localized 404 shell after initialization`; `English browser resolves localized 404 content after initialization`; mocked `e2e/error-recovery.spec.ts` :: `404 route shows a non-blank page (not a crash)` | live + mocked | live: project viewport; ru and en | — | FULL | pending hosted run |
| R67 | master SSR and PWA: correct 500 | none | none | n/a | No 500 page test in any lane | NONE | pending hosted run |
| R68 | master SSR and PWA: offline | live `e2e-live/pwa-offline-shell.live.spec.ts` :: `hydrates an unvisited public route from the precached shell while this context is offline` (Chromium only); mocked `e2e/offline.spec.ts` :: `shows offline fallback page when network is unavailable` (Chromium only) | live + mocked | live: project viewport, Chromium; mocked: chromium | — | FULL | pending hosted run |
| R69 | master SSR and PWA: service worker update without stale bundle | live `e2e-live/pwa-offline-shell.live.spec.ts` :: `updates the active service worker online and serves the new precached bundle offline` (Chromium only); mocked `e2e/audit375-service-worker.spec.ts` :: `forwards the cookie proof and deletes a terminal 403 while two active workers contend` | live + mocked | live: project viewport, Chromium | — | FULL | pending hosted run |
| R70 | master SSR and PWA: i18n in the offline shell | live `e2e-live/pwa-offline-shell-i18n.live.spec.ts` :: `the real offline app shell preserves ${language} i18n for an unvisited route` (en and ru) | live | Chromium only; en and ru | — | FULL | pending hosted run |
| R71 | master Security: CSRF | Same as R36 | live | project viewport; ru | Only the profile write endpoint | PARTIAL | pending hosted run |
| R72 | master Security: IDOR and cross-user access | live `e2e-live/chat-attachment-isolation.live.spec.ts` :: `a non-member cannot download private attachments and oversized uploads are rejected`; live `e2e-live/messenger-group-isolation.live.spec.ts` :: `group events reach both members and never reach an authenticated non-member`; admin RBAC rows R75 | live | project viewport | Profile and avatar IDOR are not in the live lane | PARTIAL | pending hosted run |
| R73 | master Security: open redirect | R08; live `e2e-live/aud178-reset-referer-csp.live.spec.ts` :: `reset fragment stays out of browser Referer and CSP report traffic` | live | project viewport | — | FULL | pending hosted run |
| R74 | master Security: XSS | live `e2e-live/production/ssr-csp-browser-negative.spec.ts` :: `blocks untrusted inline script while the server bootstrap hydrates`; `the untrusted probe executes when the response policies are removed` | live | production SSR in a browser | Tests the CSP only; no test renders user text (messages, news, profile name) containing script or event-handler markup | PARTIAL | pending hosted run |
| R75 | master Security and Admin: student and teacher denied admin pages and APIs | live `e2e-live/admin-audit-rbac.live.spec.ts` :: `${role} is denied the secure audit logs page and API`; live `e2e-live/admin-feature-flags-rbac.live.spec.ts` :: `${role} is denied access to feature-flag diagnostics`; live `e2e-live/admin-notifications-rbac.live.spec.ts` :: `${role} cannot view or mutate notification queue data`; live `e2e-live/admin-stories-rbac.live.spec.ts` :: `${role} cannot open story administration or mutate stories`; live `e2e-live/admin-users-rbac.live.spec.ts` :: `${role} cannot access the admin users page or full directory`; live `e2e-live/auth-roles.live.spec.ts` :: `${role} is denied access to admin pages, user listing, and feature flags` (roles `student`, `teacher`) | live | project viewport; ru; roles student and teacher | — | FULL | pending hosted run |
| R76 | master Admin: existing admin pages work | live `e2e-live/admin-audit-rbac.live.spec.ts` :: `admin can open secure audit logs and read the live audit endpoint`; live `e2e-live/admin-feature-flags-rbac.live.spec.ts` :: `admin can access feature-flag diagnostics`; live `e2e-live/admin-notifications-rbac.live.spec.ts` :: `admin can read the seeded notification queue without changing it`; live `e2e-live/admin-stories-smoke.live.spec.ts` :: `admin can review seeded active stories through the real admin page`; live `e2e-live/admin-users-rbac.live.spec.ts` :: `admin filters the live users directory by role without changing records`; mocked `e2e/admin-moderation.spec.ts` :: `admin sees the reports list` | live + mocked | live: project viewport; ru | Retry and purge of dead-letter jobs are mocked only (`e2e/admin-notifications.spec.ts` :: `allows admins to retry and purge dead-letter jobs`) | FULL (read paths) | pending hosted run |
| R77 | master Schedule: update conflict check excludes the current item; partial update; storage model unchanged | backend `tests/test_schedule_service_closure.py` :: `test_update_schedule_checks_effective_values_and_excludes_current_item`; `test_update_schedule_rejects_conflict_before_update_audit_or_commit`; `test_update_schedule_ignores_null_storage_fields_and_keeps_adjacent_updates`; `test_noop_update_with_real_optimizer_excludes_current_schedule`; integration `tests/integration/test_schedule_conflicts_postgres.py` :: `test_concurrent_updates_recheck_group_conflict_after_commit`; `test_update_refreshes_prefetched_row_after_waiting_for_lock` (Postgres) | backend | n/a | No UI test of the update-conflict message | FULL (backend) | pending hosted run |
| R78 | master Schedule views: keyboard, hydration, 200% | live `e2e-live/schedule-grid-keyboard.live.spec.ts` :: `Enter opens the lesson in the keyboard-selected schedule grid cell` (desktop project only); R62; R39; mocked `e2e/schedule-export.spec.ts` :: `downloads the rendered schedule as a PNG file`; mocked `e2e/schedule-offline.spec.ts` :: `loads schedule page from SW cache when network is offline` (Chromium only) | live + mocked | live: desktop 1440 only for the grid | Update-conflict message in the UI; keyboard grid on mobile | PARTIAL | pending hosted run |
| R79 | master Search: text search without an embeddings key | live `e2e-live/search-dialog-keyboard.live.spec.ts` :: `full-text search requires the controlled relevant results`; `full-text search requires visible matched-term highlights`; `full-text search requires the controlled empty state`; mocked `e2e/search-full-text.spec.ts` :: `search query returns a list of relevant results`; `matched terms are highlighted in search results`; `shows no-results message when query matches nothing` | live + mocked | live: project viewport (the spec sets 1440 in one test); ru | — | FULL | pending hosted run |
| R80 | master Search: semantic-only routes report unavailability without a zero-vector computation | backend `tests/test_services_mock.py` :: `test_vector_service_get_embedding_disabled`; `test_vector_service_search_similar_disabled`; `tests/test_aud339_semantic_search_etag.py` :: `test_semantic_search_cyrillic_etag_is_ascii_and_covers_inputs`; integration `tests/integration/test_aud257_vector_service_postgres.py` :: `test_vector_service_filters_nan_before_limit` (Postgres) | backend | n/a | No route-level test for the semantic endpoint returning unavailable when no provider is set; no UI test that the semantic toggle is absent | PARTIAL | pending hosted run |
| R81 | master Search: remove `EventRepository.get_analytics_data` `max_attendees` path | backend `tests/test_news_repository_closure.py` :: `test_get_analytics_data_with_date_filters` (news repository; the event method is not located by name) | backend | n/a | Removal of the `max_attendees` path is not verified | NONE | pending hosted run |
| R82 | §13 test coverage and quality standards | Process item. Coverage gates are in `quality/quality-contract.json` and CI; see the manual checks section | n/a | n/a | Not a product scenario | n/a | pending hosted run |
| R83 | master stage 3: mocked Firefox and WebKit | `e2e/category-scroll-stability.spec.ts` :: `news category bar keeps the same height when it becomes sticky` runs in all four projects; `e2e/offline.spec.ts` Chromium service-worker block is skipped elsewhere; `e2e/chat_workflow.spec.ts` and `e2e/group_management.spec.ts` are Chromium-only by design | mocked | firefox, webkit, mobile-webkit where not skipped | Live lane is Chromium only; messenger has no Firefox or WebKit live run | PARTIAL | pending hosted run |
| R84 | §12 «Мобильная адаптация» and §10 «адаптивность под любые экраны» (News reflow) | live `e2e-live/news-responsive-matrix.live.spec.ts` :: `seeded News core content reflows without page overflow in RU and EN` (widths 360, 390, 768, 1024, 1440) | live | 360, 390, 768, 1024, 1440 in both projects; ru and en | Applies to News only; not light and dark | FULL (News) | pending hosted run |

## Axis coverage

Each axis lists the rows and scenarios that confirm it, then the gaps. A
width or locale is "covered" only where the scenario body sets or loops over
it.

### Widths

- **390**: the live mobile project supplies 390 for specs that set no viewport
  (for example R03, R04, R06, R22 and the stories specs). Explicit 390 in R11,
  R13b, R56, R57 and R58. Mocked: profile-responsive (R34); visual-regression at
  375x812 (Windows only, R32).
  **Gap**: Web Push overlay (R54) is not run at 390; no live check of the login
  and registration screens at 390 (R02 runs at 360 only).
- **360**: explicit in R02, R56 (drawer), R57 and R58 (bottom navigation), R84
  (News). The mobile project uses 360x800 in R60 and R32 (live). Mocked push
  offer at 360x640 (R54).
  **Gap**: 360 is not run for the messenger list or chat view, profile,
  settings, stories, activity or notifications.
- **768**: live News reflow only (R84). Mocked profile-responsive (R34).
  **Gap**: no live messenger, bottom navigation, stories, activity, settings,
  notifications, admin, profile or schedule run at 768; no push offer at 768.
- **1024**: live drawer boundary (R56, R57) and News reflow (R84). No other
  1024 coverage.
  **Gap**: no 1024 check for the messenger, profile, activity or stories.
- **1440**: the live desktop project supplies 1440 for specs that set no
  viewport. Explicit 1440 in R10 (spacing matrix at 1440, 1349 and 1350), R17,
  R19, R29 and R79 (one test). Mocked profile-responsive (R34), push offer (R54),
  and visual-regression desktop (Windows only).
  **Gap**: messenger and profile visual baselines exist only for Windows.

### Locales

- **RU**: default for every live spec (config `locale: "ru-RU"`, and most
  specs set `ue:language` to `ru`). Mocked specs with explicit RU and EN loops:
  R04c (email MFA) and R39b (i18n switching).
- **EN** (live): R16 (news and events history), R24 (reply and forwarding
  loops), R25 and R26 (ru/en sample loops), R10 (spacing matrix ru/en),
  R22 (ru/en sample loop), R38 (theme and language round trip), R39
  (dashboard and schedule SSR), R70 (offline shell), R66 (404), R84 (News
  reflow), R65 (SSR markup).
  **Gap**: EN is not run for activity (the spec's EN regex is never used by a
  locale switch, R19), profile (R33), settings tabs and password (R37),
  stories (R42–R46), notifications (R50–R53), admin (R75–R76), messenger
  list and dialogs outside the sample loops, schedule grid (R78), search (R79),
  bottom navigation and drawer (R56–R58), push offer (R54), and the 360
  registration form (R02).
- **EN** (mocked): R04c (email MFA), R39b (i18n switching).
  **Gap**: mocked specs run in the Playwright default locale unless the spec
  sets one; the EN coverage in the mocked lane is limited to the specs above.

### Themes

- **Light**: default in every live spec; the config does not set colour
  scheme. Mocked: a11y-public (R01), a11y-messenger (R32).
- **Dark**: live only in the sample loops of R22, R24 (forwarding), R25, R26,
  R10 (spacing matrix), and the token test in R37 (both themes); the theme
  round trip (R38) sets both. Mocked: R01 and R32 (axe in dark), aud304 dark
  class variant (`e2e/aud304-dark-class-variant.spec.ts`), sent-bubble contrast
  (`e2e/sent-bubble-contrast.spec.ts`).
  **Gap**: no live dark run for stories, activity, profile, notifications,
  admin, bottom navigation, drawer, push offer or News. Dark is never forced by
  the live config, so every dark claim comes from a loop inside one spec.

### Roles

- **Student**: the role for most live specs (activity, messenger, news, events,
  map, settings, stories, schedule, search, navbar, footer, SSR, push, PWA).
- **Teacher**: positive live flows only in messenger (R22–R24 and R29–R31 as
  group members), notification topics (R50) and push (R31, R51, R53). Denial
  checks for teacher in R75.
  **Gap**: no live teacher flow for schedule, news, profile or settings; no
  live teacher check for the stories or activity pages beyond the R75 denials.
- **Admin**: read paths only (R76: audit, feature flags, notification queue,
  stories, users). Admin login is used by the MFA, reset and attachment specs
  (R04, R06, R26). Denial checks in R75 run as student and teacher against the
  admin pages.
  **Gap**: admin write paths (retry and purge of dead-letter jobs, story and
  user mutation) are mocked only (R76); the admin create-news flow is mocked only
  (`e2e/news-create-admin.spec.ts`).

## Manual checks

Each item below cannot be fully confirmed by an automated assertion, so the
acceptance record needs a dated manual note. The note must name the build SHA,
the device or browser, and the result.

| Check | ТЗ | Why it is manual | Required evidence |
|---|---|---|---|
| Visual design matches «матовый минимализм», «премиальный минимализм» and «стилистика ведущих современных веб-сервисов» across login, registration, footer, burger menu, messenger, profile, settings, stories and home | §2, §6, §7, §8, §10, §12 | Aesthetic judgement; tests check classes, geometry and axe rules, not look and feel | Screenshot review at 390, 768 and 1440, RU and EN, light and dark, against the design system |
| Telegram SVG icon is the official paper-plane mark and renders correctly | §3 | Asserts presence and aria labels only; identity of the mark is a visual decision | Visual comparison with the brand asset |
| Smoothness and perceived frame rate of compact navbar, map zoom and mobile bottom navigation on real mid-range devices | §3, §5, §12 | Headless Chromium timing is not representative of a phone; FPS is not measured in any lane | DevTools performance trace on one physical Android device and one iPhone |
| iOS Safari and Firefox behaviour for the live flows (map gestures, bottom navigation, Web Push as an installed PWA) | §5, §11, §12 | Live lane is Chromium only; WebKit and Firefox are mocked | Smoke run on a physical iPhone (installed PWA) and on Firefox; record outcome |
| Screen-reader announcements for the Events and Activity tabs, the Stories viewer, the messenger dialogs and the drawer | §12, §13 | axe checks rules and roles, not announced text | One NVDA or VoiceOver pass on each control, recorded |
| The OTP and reset emails as rendered by a real mail client | §2 | Mailpit checks content and headers; rendering in a real client is not automated | One rendered sample per template (RU and EN) |
| Exploratory acceptance of the whole MVP, including hidden bottlenecks | §13 «Формат сдачи» | §13 requires manual and automated verification together | Exploratory session notes with date, SHA and build |

## Gaps for stage 3

Ordered by risk to Block 4 acceptance. Each entry names the smallest test that
would close it. Duplicates are merged.

1. **Populated Activity widgets (§9, R40).** The live seed has no attendance or
   grades, so only the empty state renders end to end. Smallest: a populated
   case in `e2e-live/activity-summary.live.spec.ts` with seeded data, or a
   mocked `e2e/activity-populated.spec.ts` (new) at 390, 768 and 1440, RU and EN,
   light and dark.
2. **First-load map micro-freezes (§5, R21).** Not measured in any lane. Smallest:
   move the `measurementAvailable` block in
   `e2e-live/map-zoom-longtask.live.spec.ts` before the first canvas is shown.
3. **Group ordering and deduplication across reconnect (§6, R23).** Live tests use
   direct chats only. Smallest: a group variant in
   `e2e-live/messenger-reconnect-ordering.live.spec.ts`.
4. **Bottom navigation fast taps and pressed state (§12, R58, R59).** Smallest: a
   rapid-tap loop and a `:active` or pressed-state check in
   `e2e-live/footer-bottom-navigation.live.spec.ts` at 390 and 360.
5. **Home empty-card spacing (§10, R49).** No geometry in any lane. Smallest: a new
   `e2e/dashboard-empty-spacing.spec.ts` that mocks empty schedule, news and
   events and measures the vertical gaps at 390, 768 and 1440.
6. **Navbar FPS and mobile compact-on-scroll (§3, R10, R11).** FPS not measured;
   mobile geometry at 390 only. Smallest: frame sampling during scroll and a
   360 run in `e2e-live/navbar-layout-stability.live.spec.ts`.
7. **Stories keyboard arrows and touch swipe (§10, R43).** Unit only. Smallest:
   ArrowLeft, ArrowRight and a touch swipe in
   `e2e-live/story-viewer-keyboard.live.spec.ts`.
8. **Events status-tab centring (§4, R18).** Unit only. Smallest: a `boundingBox`
   check within 1 px in `e2e-live/events-tab-keyboard.live.spec.ts`, both projects.
9. **Tag-change scroll reset (§4, R14, R15).** Mock only, 1280 width. Smallest: a
   live variant in `e2e-live/news-scroll-restoration.live.spec.ts` that changes the
   category and asserts `scrollY` is unchanged.
10. **Contextual push offer (§11, R54).** Mocked at 360x640 and 1440x900 only. Smallest:
    add 390 and 768 to the viewport list in `e2e/push-context-geometry.spec.ts`,
    and a live position check.
11. **Messenger visuals and adaptivity (§6, R22, R32).** Snapshots are Windows-only,
    there is no 768 run, and there is no Linux baseline. Smallest: axe and geometry
    at 390, 768 and 1440 in `e2e/a11y-messenger.spec.ts`, which runs on Linux.
12. **Login and registration visuals (§2, R01).** Axe only, default width, and the
    registration page is not in the route list. Smallest: add `/register` to
    `e2e/a11y-public.spec.ts` and a geometry check at 390, 768 and 1440.
13. **500 page (master SSR and PWA, R67).** Not tested in any lane. Smallest: a 500
    route in `e2e/error-recovery.spec.ts`.
14. **XSS in user text (master Security, R74).** Only the CSP is tested. Smallest: a
    live message containing script markup, asserting it renders as text, in a new
    `e2e-live/chat-xss-render.live.spec.ts`.
15. **Semantic-only route unavailability (master Search, R80).** Service level only.
    Smallest: a route-level test under `tests/` for the endpoint with no provider.
16. **Group size accept boundaries (§6, R28).** Only the rejections are asserted;
    tests catch `Exception` broadly. Smallest: accept at 3 total and 100 total in
    `tests/test_chat_creation_service.py`, with exact exception types.
17. **Group permissions matrix (§6, R29).** Add and rename permissions and the
    DM refusal are not run live. Smallest: a live permission matrix in
    `e2e-live/messenger-membership-revocation.live.spec.ts`.
18. **Activity EN and stories/notification EN (§8, §9, §10, §11).** EN is not run
    in these areas. Smallest: an EN loop in `e2e-live/activity-summary.live.spec.ts`
    using a locale switch, and in the stories and notification live specs.
19. **Achievements end to end (§7, R35).** Unit only. Smallest: an e2e in
    `e2e/profile-settings.spec.ts` that clicks an achievement.
20. **Negative Activity constraint (§9, R41).** No assertion that no new goals or
    attendance features exist. Smallest: a static check in the Activity contract test.
21. **Teacher live flows (roles, see Axis coverage).** Only denial and messenger flows
    are live. Smallest: one teacher schedule or news read path in a new live spec.
22. **Memory evidence beyond Stories (§13, R45).** The memory plateau test covers
    Stories only. Smallest: a map and messenger memory check in the same pattern as
    `e2e-live/story-viewer-memory.live.spec.ts`.
