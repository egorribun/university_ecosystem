# Quarterly flaky-test audit runbook

This runbook is the review procedure for quarantined tests and the recovery
exercise required before a quality certification is renewed.

## 1. Review the quarantine register

1. Read `quality/quality-contract.json` and list every entry in `quarantines`.
2. Run the complete test command with `--run-quarantined` in the affected
   component. A quarantine is a temporary diagnostic mode, never a passing
   substitute for the normal gate.
3. Verify each entry has an owner, issue/evidence link, and a future
   `expires_on` date. Expired entries fail the audit and must be removed or
   fixed in the same change.
4. For each failure, classify the cause as product defect, test defect,
   environment/fixture instability, or an external dependency. Attach the
   reproducer and at least three consecutive clean reruns before removing the
   quarantine.
5. Re-run the normal gate without `--run-quarantined` and confirm that the
   required-check matrix is unchanged.

Useful commands:

```powershell
python scripts/quality/validate_quality_contract.py
python -m pytest --run-quarantined
python -m pytest -q tests/test_quality_contract.py tests/test_quality_configuration.py
```

## 2. Flake-rate evidence

Record the test identifier, workflow run URL, retry count, first failure,
environment, and final disposition. Do not “fix” a flake by increasing retries
without recording the underlying failure. Repeated retries hide regressions and
are not evidence of reliability.

## 3. Disaster-recovery exercise

Perform this checklist at least quarterly and after a migration or storage
layout change:

1. Restore a recent production-like database snapshot into an isolated
   environment; keep the original snapshot immutable.
2. Verify row counts and representative relationships for users, events,
   registrations, news, messages, and audit records.
3. Run `alembic upgrade head`, then execute the application smoke suite.
4. Run the documented downgrade/upgrade round-trip on a disposable copy and
   compare schema metadata plus representative data checksums.
5. Restore object-storage metadata and verify a sample of file hashes,
   permissions, and download authorization.
6. Exercise Redis/Valkey and NATS recovery, then confirm health, metrics,
   tracing, and alert delivery.
7. Record RTO/RPO measurements, deviations, and follow-up owners. A recovery
   test without measured timings is incomplete.

The exercise is complete only when the evidence, limitations, and open actions
are attached to the release certification record. Never use this runbook to
delete production data; all downgrade and restore validation uses disposable
copies.
