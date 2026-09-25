# ADR-041: Canonical Push Topic Preferences

## Status

Accepted

## Date

2026-09-25

## Context

Push delivery filters by five canonical topics (`news.published`,
`schedule.changed`, `events.published`, `chat.message.created`,
`system.release`). Two stores held topic state:

- `user_push_topics` (`UserPushTopic`): one row per user. The delivery filter
  `filter_user_ids_by_topic` already treated "no row" as the all-topics
  default and an explicit `[]` row as an opt-out of every topic.
- `push_subscriptions.topics`: a per-device copy. An empty list means
  "unrestricted, gated only by the user row" in `subscription_supports_topic`.

A review of the pending push account-boundary work (safe-pause handoff
§0.000 D) found that these stores disagreed and leaked across accounts:

1. `POST /push/subscribe` looked an endpoint up without an owner filter and
   silently transferred it to the caller. With `topics` omitted it kept
   `existing.topics` through `resolve_topics`, so user B inherited user A's
   topic list on a shared browser.
2. `_refresh_user_topic_preferences` rewrote the user row as the union of the
   user's subscription topics after every subscribe and unsubscribe. An empty
   union **deleted** the row. An explicit opt-out saved through
   `PATCH /push/subscribe/topics` was therefore reverted to "all topics" by
   the next resubscribe or by removing the last device.
3. The frontend persisted subscriptions before `/users/me` confirmed the
   identity. Placeholder users (`ssr-stub`, the encrypted-cache `-1`) and
   profile-cache fallbacks produced implicit `topics: []` posts. Bundles
   already cached in browsers keep sending the server-returned `[]` for
   users on the default.

On 2026-09-25 the maintainer chose to make the per-user row canonical.

## Decision

`UserPushTopic` is the single source of truth for a user's topic preference:

| Row | Meaning |
| --- | --- |
| none | default: every allowed topic |
| `[]` | explicit opt-out of every topic |
| list | only the listed topics |

`push_subscriptions.topics` is a mirror of that preference (`[]` when there is
no row) and never an independent input.

`POST /push/subscribe` (`_bind_subscription_to_user` and
`resolve_subscription_topics_for_user`):

- binds the endpoint to the authenticated caller, including on the
  `IntegrityError` recovery path, and logs `push.subscribe.owner_changed`
  when the owner changes;
- with `topics` omitted **or** `[]`, mirrors the caller's canonical row
  without writing it. `[]` keeps this meaning for compatibility with cached
  bundles; it is not an opt-out on this endpoint;
- with a non-empty list (after normalization), performs an explicit
  preference update through `synchronize_user_topics`, mirrored to every
  subscription of the caller. A list that normalizes to nothing (only unknown
  topics) is treated as omitted;
- never reads or modifies the previous owner's row or other devices.

`PATCH /push/subscribe/topics` with `[]` is the only way to opt out of every
topic. `POST /push/unsubscribe` removes the device and never changes the
preference. `_refresh_user_topic_preferences` and `resolve_topics` are
removed. `GET /push/topics` returns `has_preferences` and `updated_at` so the
client can distinguish "default" from "opted out".

The frontend never sends topics implicitly and persists a subscription only
for an identity confirmed by the live auth store (no placeholders, no profile
cache). The backend remains the final authority when a request races an
account switch.

Browser notification permission is per browser, not per account. The
frontend therefore treats a browser endpoint and its local consent as owned
by the account that enabled push there (the `push:last_owner` marker):

- only that account's confirmed login re-binds the endpoint or recovers lost
  consent automatically;
- another account on the same browser sees push as disabled and must enable
  it explicitly;
- logout detaches the endpoint on the server (`POST /push/unsubscribe`)
  while keeping the browser subscription and the owner marker, so the same
  account resumes push on its next login. If that unbind fails, the browser
  revokes the endpoint itself; if it times out, the marker stays so the
  next account's login retires it;
- when a different account signs in on a browser whose marker names
  another account, the browser subscription is revoked, so an account whose
  session expired without logout stops receiving notifications there;
- a cached profile id is not proof of the session's account: the boot sync
  verifies it with `GET /users/me`, while login, MFA and refresh pass the
  account id from their authenticated responses;
- topic toggles stay disabled until the canonical preference has loaded,
  so a placeholder selection can never overwrite a stored opt-out.

## Consequences

- Browsers that enabled push before the owner marker existed keep their
  server binding and keep receiving notifications, but are not re-synced
  automatically until the user toggles push once.

- Delivery semantics are consistent across in-app and Web Push: an opt-out
  row also suppresses in-app notifications for those topics, because
  `filter_user_ids_by_topic` runs before notification rows are created.
- Opt-outs that the old refresh deleted cannot be restored; no history of
  them exists. Existing rows written by the refresh (a union of device topics)
  become the user's explicit preference.
- An explicit list posted on a first subscribe races only with the same
  user's concurrent request; the existing three-attempt `IntegrityError`
  retry handles the primary-key conflict on `user_push_topics`.
- No schema or OpenAPI change is required for the subscribe contract.

## Alternatives considered

- **POST `[]` as opt-out.** Rejected: bundles cached before this change send
  the server's `[]` for default users on every sync and would opt them out
  of every notification.
- **Store every allowed topic on subscriptions without a row.** Rejected:
  topics added later would not reach users on the default.
- **Reject transfers with 409.** Rejected: a browser endpoint legitimately
  moves between accounts on a shared device; the server must rebind it to the
  authenticated caller.

## References

- [ADR-017](ADR-017-domain-oriented-test-files.md)
- `app/services/push_topics.py` (`filter_user_ids_by_topic`,
  `subscription_supports_topic`, `resolve_subscription_topics_for_user`)
- `tests/test_push_subscription_ownership.py`
