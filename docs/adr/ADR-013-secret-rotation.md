# ADR-013: Secret Rotation Strategy

## Status
Accepted (Wave 32, 2026-03-26)

## Context
The platform manages multiple categories of secrets: JWT signing keys, CSRF HMAC secrets, database credentials, Redis passwords, NATS auth tokens, and internal HMAC secrets. Currently, rotation requires manual intervention and service restarts.

## Decision
Implement a layered rotation strategy with three tiers based on rotation frequency and blast radius.

### Tier 1: Hot-Rotatable (no restart)
| Secret | Mechanism | Frequency |
|--------|-----------|-----------|
| JWT RS256 public key | JWKS hot-reload (MOD-W17-03) | On-demand |
| JWT RS256 private key | Backend `keys.rotated` NATS subject | On-demand |
| Session signing key | In-memory rotation via config reload | Weekly |

### Tier 2: Warm-Rotatable (graceful restart)
| Secret | Mechanism | Frequency |
|--------|-----------|-----------|
| CSRF HMAC secret | ExternalSecret refresh (1 min) + rolling restart | Monthly |
| Internal HMAC secret | ExternalSecret + rolling restart | Monthly |
| Audit log secret | ExternalSecret + rolling restart | Quarterly |
| MFA TOTP encryption ring | Active key encrypts; retained ring entries decrypt legacy enrollments; bounded database rotation plus restart | On demand |

### Tier 3: Cold-Rotatable (maintenance window)
| Secret | Mechanism | Frequency |
|--------|-----------|-----------|
| DATABASE_URL credentials | Vault dynamic secrets + connection pool drain | Quarterly |
| Redis password | Vault + Sentinel failover | Quarterly |
| NATS auth token | NKey migration (DEBT-07) | Annually |

### Rotation Procedure
1. **Generate new secret** in Vault (or manually for Tier 3)
2. **Update ExternalSecret** — ESO refreshes every 1 min (TD-22-04)
3. **Trigger rolling restart**: `kubectl rollout restart deployment/backend`
4. **Verify**: Check Prometheus `http_request_duration_seconds` for error spikes
5. **Rollback**: If errors, revert Vault secret version

### Dual-Key Window
For JWT RS256, the backend signs with the new key while the gateway accepts both old and new via JWKS (multiple keys in the `keys` array). This provides a zero-downtime rotation window.

TOTP enrollment ciphertext uses a dedicated Fernet key ring, separate from
Spotify token encryption. New writes use only the active TOTP key. During a
bounded migration, non-active TOTP entries may retain legacy ciphertext keys,
including a former Spotify key, solely for decryption. The active TOTP key must
not reuse any Spotify key or Spotify's `SECRET_KEY`-derived fallback. A legacy
entry may be removed only after the migration utility can read the complete
enrollment table without it.


If existing enrollment ciphertext used Spotify's former `SECRET_KEY` fallback,
operators must recover the exact historical `SECRET_KEY` from the secret manager;
the currently configured key is not evidence of the historical value. The old
fallback is `urlsafe_b64encode(SHA-256(UTF-8(SECRET_KEY.strip())))`, matching the
former Spotify encryption helper. Generate a protected legacy ring entry with:

```sh
python scripts/derive_legacy_totp_key_entry.py \
  --historical-secret-key-file /protected/operator-input/previous-secret-key \
  --output-file /protected/operator-output/totp-legacy-entry
```

The helper is POSIX-only. It reads the input file privately, creates the output
exclusively with requested mode `0600` (subject to the process umask), and never
writes key material to stdout or logs. Treat the output as a secret file and
provision its entry only as a non-active legacy TOTP ring member. Do not use the
current `SECRET_KEY` unless its identity as the historical value has been
independently verified. If the historical key is unavailable, do not remove the
old decrypt path or claim the ciphertext has been migrated; resolve the
operator-side key recovery before rotation.

### Monitoring
- `gateway_jwks_key_rotations_total` — tracks JWKS rotations
- `external_secret_sync_status` — ESO sync health
- Alert: `ExternalSecretSyncFailed` fires if sync fails for >5 min

## Consequences
- JWT key rotation achieves zero downtime via dual-key JWKS
- Credential rotation for DB/Redis still requires maintenance window until Vault dynamic secrets are adopted
- All secrets are stored in Vault — no K8s Secret manifests contain plaintext (ESO manages the bridge)
- TOTP and Spotify ciphertext use separate active key material; legacy TOTP key retirement requires an operator-verified data migration.
- The rotation procedure above is the canonical runbook for this decision;
  deployment prerequisites and environment-specific secret wiring are
  documented in [`docs/DEPLOY.md`](../DEPLOY.md) and its
  [English counterpart](../DEPLOY.en.md).
