$timeout = 30
$elapsed = 0
do {
  $null = pg_isready -h localhost -p 5432 -U test
  if ($LASTEXITCODE -eq 0) {
    return
  }
  Start-Sleep -Seconds 1
  $elapsed++
} while ($elapsed -lt $timeout)
throw "PostgreSQL was not ready in $timeout seconds"
