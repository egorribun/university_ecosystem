# MFA Manual Test Checklist

Use this checklist for a manual smoke of the supported MFA flows before a
release. The checklist is limited to the product's RU and EN UI/localization
scope: repeat the same scenarios once with the browser/application locale set
to Russian and once with it set to English. It does not certify translations
for other locales.

The API uses the HttpOnly `access_token_v2` cookie for an authenticated
session. The login response does not return an access token in its JSON body;
the browser must retain the cookie. Obtain the CSRF cookie through
`GET /api/v1/auth/csrf-cookie` when the client flow requires it.

## 1. TOTP enrollment

1. Sign in with a test account that has no active MFA factor.
2. Open **Settings → Security & MFA** and start authenticator-app setup.
3. Scan the displayed QR code (or use the displayed secret) and submit a
   current six-digit code.
4. Confirm that the enrollment is listed with its timestamp and that the
   setup control is no longer offered while an active enrollment exists.
5. Sign out and sign in again. Confirm that the challenge offers TOTP and that
   the UI copy is complete in both RU and EN.
6. Remove the enrollment only after completing the requested fresh MFA
   verification. Verify that the factor disappears and can be enrolled again.

The corresponding API operations are `POST /api/v1/auth/mfa/totp/start`,
`POST /api/v1/auth/mfa/totp/confirm`, and
`DELETE /api/v1/auth/mfa/totp/{enrollment_id}`. A pending enrollment can be
cancelled through `DELETE /api/v1/auth/mfa/totp/pending/{enrollment_id}`.

## 2. Email OTP

1. With an authenticated account, start email MFA enablement from the same
   security settings screen and complete the fresh-MFA prompt.
2. Verify that the message is sent to the expected address without exposing
   the OTP in the UI, URL, or JSON response.
3. Enter the valid code and confirm that email MFA is shown as enabled.
4. Start email verification again, exercise resend/rate-limit messaging, and
   complete a valid challenge.
5. Disable email MFA only after the fresh-MFA confirmation and verify the
   factor status in the UI.

The API operations are `POST /api/v1/auth/mfa/email/enable`,
`POST /api/v1/auth/mfa/email/verification/start`,
`POST /api/v1/auth/mfa/email/resend`, and `DELETE /api/v1/auth/mfa/email`.

## 3. Login verification and recovery codes

1. Sign out and sign in again. Confirm that the available methods match the
   enrolled factors (TOTP and/or email OTP).
2. Submit an invalid code and confirm that the remaining-attempt feedback is
   localized and that access is not granted.
3. Generate recovery codes from the security settings after fresh MFA. Verify
   that the codes are shown once, are not returned by later API responses, and
   that the UI instructs the tester to store them safely.
4. Use one recovery code for a login or step-up challenge. Confirm that it is
   accepted once and rejected if immediately reused.
5. Verify that the remaining-code state is refreshed after successful use.

The relevant API operations are `POST /api/v1/auth/mfa/recovery-codes` and
`POST /api/v1/auth/mfa/verify`; login is available through
`POST /api/v1/auth/login/json` (JSON) or
`POST /api/v1/auth/login` (form-compatible).

## 4. Session step-up

1. While signed in, open the active-session list.
2. Attempt to revoke another session (use a second browser if needed).
3. Confirm that the action requires a fresh MFA step-up and that TOTP, email
   OTP, or a recovery code is handled according to the enrolled factors.
4. Complete the challenge and verify that only the selected session is
   revoked. Confirm that the current browser keeps its `access_token_v2`
   session.

The session operations are `GET /api/v1/auth/sessions`,
`DELETE /api/v1/auth/sessions/{session_id}`, and
`POST /api/v1/auth/sessions/revoke-others`.

## 5. Failure and localization checks

For each RU and EN pass, record any missing translation, incorrect method
label, leaked token/OTP, stale factor status, unexpected 4xx/5xx response, or
inability to complete an action. A green automated test or a successful API
call does not replace this browser-level check.
