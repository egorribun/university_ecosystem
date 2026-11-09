# Root-level owned PostgreSQL proofs run in the full unit shard.
$images = @(
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
