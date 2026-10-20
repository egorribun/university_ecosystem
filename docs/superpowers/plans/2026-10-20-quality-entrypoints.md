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

## Observed entrypoint RED and narrow corrections

Contract job 118441928877 has four intended failures: make exits 2 on the success path, the synthetic application is never reached in the export-failure case, and both downstream cases record no stage. Node job 118442417955 exposes root/tests versus tests and exit 0 versus 1 in all three blocked-output icon cases. Success/missing-source icon controls pass. These are actual child-process/configuration assertions, not inferred source defects.

AUD-082 changes only the intended pytest discovery path and restores the file's terminal newline. AUD-083 replaces the split heredoc with one continued Python command, retains canonical UTF-8/sorted/indented/newline export, normalizes the tracked schema, and leaves SDK/MSW generation in its existing command. The tracked schema is no longer removed. npm exec --no declines implicit installation when Prettier is missing; the synthetic npm argument oracle gains that exact safety flag, with all behavior assertions preserved. The original Make target's physical span is retained through readable continuations and explanatory comments; protected baseline line 188 is byte-identical and the baseline itself is untouched.

AUD-087 sets process.exitCode=1 in each existing output-error catch while continuing all later attempts. Logging, success, missing-source behavior and favicon byte format are unchanged. All corrected-source execution is pending; these three IDs are not yet accepted.

## AUD-088 rendered contract accepted

AUD-088 is accepted as the original rendered frontend/gateway positive-minimum defect. The two off-peak/daytime cases pass at 03:50:21/22 UTC and the disabled-state case at 03:50:23 in job 118442456006. They execute Helm against the tracked chart/dependency archives with synthetic CLI overrides and no dependency update or cluster contact. Hibernation remains disabled by default; no replicas, schedules or deployment settings change. This does not prove real KEDA zeroing, wake readiness, cron execution or availability. The verified lower bound becomes 87/512; other new findings remain open until their own corrected-source GREEN.

## Corrected entrypoints accepted

Source 1ed440f88de239971ce9e4e6900a41ed6adad7c3 and hosted checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b have identical tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. Contract job 118448021392 passes all four Make cases and totals 129 PASS. Node job 118448485714 passes all 596 cases, including JSONC discovery and all five real icon subprocess oracles. AUD-082/083/087 now have their own corrected-source GREEN and are accepted within the scopes above; no formatter, generator, baseline or security gate is bypassed.

## AUD-098 diagnostic IPC tests first

Two real Node subprocess cases preload the unchanged trace agent with IPC and an explicit environment. One leaves IPC open and requires natural successful exit without a dump/exit request; the other keeps a real timer active and requires the existing dump reply. The latter proves message delivery must survive any future channel unref. Readiness, exit, reply and cleanup waits are bounded; cleanup targets only the direct owned child, awaits close, then removes its temporary directory. The natural-exit case is expected to fail until observed otherwise. It does not prove real Vite producer completion or general process-tree cleanup.

## AUD-099 actual Spectral tests first

The existing spectral-lint job gains a bounded synthetic-fixture step after its existing pinned enforcement command. The checker extracts and requires the same immutable image from both existing commands; no image literal, dependency or pull is added. Docker uses --pull=never, --network=none and read-only mounts. The exact container ID comes from Docker's CID file; bounded cleanup preserves original failure and makes cleanup failure observable. Runner loss or unresponsive Docker can still leave cleanup unproven.

The fixture exercises 200-only/default-only/400/4XX across the five existing selected verbs, plus excluded HEAD/OPTIONS/TRACE controls. Acceptance requires ten response-rule warnings at the expected operation.responses paths, no such warnings for the positive/excluded controls, and preserved PII/OAS diagnostics. The production ruleset is unchanged for this first run, so missing warnings are expected; the actual pinned tool must establish RED and diagnostic locations before any rule correction. Runtime checks raise explicit errors rather than optimization-sensitive asserts. Unit guards validate checker failure handling but are not a substitute for actual Spectral execution.
