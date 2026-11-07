# Testcontainers pulls these images lazily.  A transient
# Docker Hub token/registry timeout must not turn a healthy
# integration suite into a false-negative CI failure.
$images = @(
  "nats:2.15.0-alpine@sha256:ac8f88a6494bffc2c2a5289a0ca61cb28a9145c11ba5677cf24265d07f46d8d4",
  "postgres:15-alpine@sha256:fe0737ba566a2c5b2a28f34433c0a423261900ec17b9bf7ad115e1aae7e57f1b",
  "redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2",
  "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
)
$maxAttempts = 5

foreach ($image in $images) {
  $available = $false
  for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    docker image inspect $image *> $null
    if ($LASTEXITCODE -eq 0) {
      $available = $true
      break
    }

    Write-Host "Pulling $image (attempt $attempt/$maxAttempts)"
    docker pull $image
    if ($LASTEXITCODE -eq 0) {
      $available = $true
      break
    }

    if ($attempt -lt $maxAttempts) {
      $delaySeconds = [int][math]::Pow(2, $attempt)
      Write-Host "Retrying $image in $delaySeconds seconds"
      Start-Sleep -Seconds $delaySeconds
    }
  }

  if (-not $available) {
    throw "Unable to make testcontainer image available after $maxAttempts attempts: $image"
  }
}
