# Audit quality entrypoint contracts

## Accepted artifact stability

AUD-086 has named, source-bound behavioral proof in job 118415281373, not merely aggregate job success. Seven paired shell/server stability cases pass at 2026-10-20 02:13:08 UTC; source aa7ea4265ec21ed9d88fc253785d0bc9660adb72 and test ce5227820d601c7412d7788f36431d287ab192b3 remain unchanged. The bounded sampling claim does not imply producer completion, full asset stability or general process-tree quiescence.

## AUD-082 tests first

The existing frontend quality-contract Node suite parses the real VS Code JSONC with the installed TypeScript parser, requires pytest enabled and the intended tests directory, and checks a known tracked test file. Current root/tests should fail the explicit path assertion before filesystem lookup. No settings change is included yet. A later single-value correction proves discovery configuration, not a physical VS Code session.

## AUD-083 tests first

Four automatically selected Contract Tests execute a copy of the actual Makefile using official runner GNU make and Python, through the existing bounded private collector. Each fixture owns synthetic app and npm files under tmp_path, an explicit fixture-only PATH, and a synthetic tracked-schema stand-in. Actual application startup, dependency downloads and actual SDK generation cannot run in this fixture.

Require successful export/normalization/generation ordering and retained schema; exporter failure must reach the synthetic application and preserve previous schema; normalization/generation failures must return nonzero at their intended recorded stages. Nonzero make alone is insufficient proof. The current split heredoc should fail before the synthetic application, exposing four meaningful assertions.

The actual frontend/openapi.json is tracked. After observed RED, replace only the broken recipe with canonical UTF-8/indent/sorted-key/newline export, normal frontend Prettier normalization and the existing quoted generate:api prefix. Remove the rm recipe rather than deleting the tracked schema. Do not add global .ONESHELL. These contracts prove recipe execution/order and preservation, not actual Prettier/SDK parity or transactional rollback; existing OpenAPI/MSW drift jobs remain authoritative.

## AUD-087 tests first

Five subprocess cases execute the unchanged icon-generator body in a temporary scripts/public layout, resolving only sharp to its real installed module. A small raw-pixel PNG avoids external inputs. Child execution has an explicit empty environment, a 30-second timeout and a 64-KiB output bound; finally removes the temporary tree. No tracked icon can be touched.

Success and missing-input behavior are preservation controls. Directory collisions at the first PNG, favicon only or all six output paths require nonzero exit while preserving best-effort attempts and successful outputs. Do not claim RED before hosted execution. Favicon's pre-existing PNG-format bytes are explicitly outside this exit-status correction. The tests extend the already-selected frontend quality-contract suite without new dependencies or selection scripts.

## AUD-088 named rendered-configuration proof

Current frontend/gateway templates already render zero minimums and complementary daytime cron, while hibernation remains disabled by default. Select the three existing tests/test_helm_keda_hibernation.py cases by extending only existing focused workflow line 155. Required redis and nats chart archives are already tracked; these tests use helm template --dependency-update=false with synthetic CLI overrides and do not install/apply or alter values.

The focused command precedes the later pinned Helm setup. Acceptance requires three explicit PASSED node IDs, not aggregate success, because the unchanged helper can skip if preinstalled Helm is absent. No skip is added or hidden. Passing proves the original positive-minimum configuration defect only, not live scaler behavior, cron timing, zeroing/wake readiness or availability. No operational enablement is requested or performed. Workflow split-line count and baseline coordinates remain unchanged.
