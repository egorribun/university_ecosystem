# Keep all caller-controlled values in the step environment.
# Interpolating them into PowerShell source would turn a
# reusable-workflow input into executable runner code.
$parallelWorkers = [int]$env:PARALLEL_WORKERS
$parallelArgs = @()
if ($parallelWorkers -ne -1) {
  if ($parallelWorkers -eq 0) {
    $parallelArgs = @("-n", "auto")
  } else {
    $parallelArgs = @("-n", [string]$parallelWorkers)
  }
}

$failFastArgs = @()
if ([System.Convert]::ToBoolean($env:FAIL_FAST)) {
  $failFastArgs = @("-x")
}

$shardArgs = @()
$shardSuffix = "full"
$coverageXmlName = "coverage.xml"
$coverageJsonName = "coverage.json"
$shardId = [int]$env:SHARD_ID
$numShards = [int]$env:NUM_SHARDS
if ($numShards -gt 1) {
  if ($shardId -lt 0 -or $shardId -ge $numShards) {
    throw "shard-id must be between 0 and num-shards - 1"
  }
  $shardArgs = @(
    "--shard-id=$shardId",
    "--num-shards=$numShards"
  )
  $shardSuffix = "shard-$shardId"
  $coverageXmlName = "coverage-$shardSuffix.xml"
  $coverageJsonName = "coverage-$shardSuffix.json"
}

$pytestArgs = @($env:TEST_PATTERN)
$pytestArgs += "--timeout-disable-debugger-detection"
$pytestArgs += $parallelArgs
$pytestArgs += $shardArgs
$pytestArgs += $failFastArgs

# pytest-cov must not enforce a whole-suite floor on an
# individual shard. The aggregate coverage-policy-gate
# combines the raw data files below and enforces the floor
# once all shards are present.
$coverageDataFile = ".coverage"
if ($numShards -gt 1) {
  $coverageDataFile = ".coverage.$shardId"
}
$env:COVERAGE_FILE = $coverageDataFile

# Ensure the artifact output folder exists
New-Item -ItemType Directory -Force artifacts/coverage/python | Out-Null

$pytestArgs += @(
  "--ignore=tests/test_schemathesis_api.py",
  "--ignore=tests/integration/test_quarantine_reservations_postgres.py",
  "--cov=app",
  "--cov=alembic/versions",
  "--cov-report=xml:$coverageXmlName",
  "--cov-report=json:artifacts/coverage/python/$coverageJsonName",
  "--cov-report=term-missing",
  "--junitxml=pytest-report.xml",
  "--dist=loadgroup"
)

$coverageThreshold = [int]$env:COVERAGE_THRESHOLD
if ($numShards -le 1 -and $coverageThreshold -gt 0) {
  $pytestArgs += "--cov-fail-under=$coverageThreshold"
} else {
  $pytestArgs += "--cov-fail-under=0"
}

uv run pytest @pytestArgs
