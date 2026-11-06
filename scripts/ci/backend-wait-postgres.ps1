$maxRetries = 30
$attempt = 0
do {
  pg_isready -h localhost -p 5432 -U test
  if ($LASTEXITCODE -eq 0) { break }
  $attempt++
  if ($attempt -ge $maxRetries) {
    throw "PostgreSQL was not ready after $maxRetries seconds"
  }
  Start-Sleep -Seconds 1
} while ($true)
