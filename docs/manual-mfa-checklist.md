# MFA Manual Test Checklist

Use this checklist to validate the end-to-end TOTP-only multi-factor authentication flow before each release.

## 1. Enrollment
1. Sign in with a test account that does **not** have MFA enabled.
2. Navigate to **Settings → Security & MFA**.
3. Click **Set up authenticator app** and scan the QR code with an authenticator app.
4. Enter the generated 6-digit code and confirm setup.
5. Verify that the enrollment list now shows the authenticator with a timestamp and that the warning banner disappears.
6. (New) Sign out and back in so the session reflects the new factor; verify that the default method is displayed as TOTP in the UI.
7. Confirm that the **Set up authenticator app** button is disabled until the existing authenticator is removed.

## 2. Login verification
1. Sign out of the account.
2. Sign back in with the same account.
3. Confirm that the login screen prompts for a single authenticator code.
4. Enter a valid TOTP code and ensure the login succeeds.
5. Enter an invalid code and confirm that the UI shows the remaining attempt count and blocks access until a valid code is entered.

## 3. Session step-up
1. While signed in, open **Settings → Security & MFA**.
2. Attempt to revoke another active session (create one by logging in from a second browser if needed).
3. Confirm that a step-up dialog appears requesting the authenticator code.
4. Enter a valid TOTP code and ensure the sensitive action completes (the other session is revoked).

## 4. Recovery from invalid codes
1. Trigger a step-up or login challenge.
2. Enter invalid codes until the dialog reports that the challenge is locked.
3. Request a new challenge (retry login or click the refresh action if provided).
4. Confirm that a fresh challenge can be completed with a valid code and that the UI surfaces the refreshed state.

Document any anomalies (unexpected error states, missing copy, inability to complete actions) before shipping.
