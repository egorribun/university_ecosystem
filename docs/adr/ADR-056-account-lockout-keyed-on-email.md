# ADR-056: Account lockout keyed on email

## Status

Accepted by the owner on 2026-11-23 for the synthetic internal MVP demo,
retaining the existing source behavior. Real-user or public deployment requires
a separate decision.

## Context

The credential validator checks the failed-attempt history for the normalized
email before verifying a password. That history is keyed on email, including
identifiers that do not correspond to an account. It is not partitioned by IP.
Consequently failures from different sources contribute to the same lockout,
and a user with the correct password cannot log in while it is active. This
protects the password check but lets another party temporarily deny access to
an account if its email is known. Rate limits are a separate control and do not
eliminate this availability trade-off.

## Decision

Retain the email-keyed behavior for the MVP. The owner accepts the availability
risk for a demo using synthetic accounts and data.

The default `auth_lockout_thresholds` is `5:30,8:300,10:3600`: the thresholds
are counts of retained failed attempts and the durations are seconds. The
service fetches up to the ten most recent attempts, adds each applicable
duration to the oldest timestamp in that slice, and uses the latest unexpired
deadline. At the ten-attempt threshold that deadline is one hour after the oldest
attempt. The shorter thresholds can stop login before later attempts. The history
window defaults to 1,440 minutes. Both settings are configurable.

While a lock is active, both form and JSON login return HTTP 423 before password
verification, with a `Retry-After` header. For the same request locale and
lockout state, the public problem detail is the same for a known or unknown
email. Request-specific trace identifiers and remaining time may differ. A
successful login after expiry clears that email's failed-attempt history.
The request-level 401 and 423 messages use the request locale. This decision
does not assert that all timing or side channels are indistinguishable.

## Consequences and follow-up

- Legitimate users can be locked out even when their own password is correct.
- A per-`(email, IP)` policy or a step-up challenge is deferred to v1.1. Its
  design must assess shared or changing addresses, distributed attempts, abuse,
  recovery, privacy, and usability before replacing the current behavior.
- The focused login tests use synthetic accounts and pre-seeded failed-attempt
  records to check enforcement, expiry, and the known/unknown public response.

## References

- [Credential validation](../../app/services/auth/credential_validator.py)
- [Lockout service](../../app/services/auth/lockout.py)
- [Default thresholds](../../app/core/config/mixins/rate_limit_settings.py)
- [MVP backlog](../superpowers/plans/MVP_MASTER_PLAN.md#12-backlog-v11)
- [ADR-053: MVP authentication](ADR-053-operator-scoped-mvp-authentication.md)
