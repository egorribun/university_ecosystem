# Go Services Coverage Report Aggregator
# Natively computes statement coverage across all services

$services = @(
    @{ Name = "gateway"; Path = "services/gateway" },
    @{ Name = "ws-hub"; Path = "services/ws-hub" },
    @{ Name = "file-processor"; Path = "services/file-processor" },
    @{ Name = "uni-cli"; Path = "services/cmd/uni-cli" }
)

Write-Host "=========================================="
Write-Host "        Go Services Coverage Report       "
Write-Host "=========================================="

foreach ($svc in $services) {
    $covFile = Join-Path $svc.Path "coverage.out"
    $absPath = Resolve-Path $covFile -ErrorAction SilentlyContinue
    if ($absPath) {
        $out = go tool cover -func="$($absPath.Path)"
        $lastLine = $out[-1]
        $pct = ($lastLine -split '\s+')[-1]
        Write-Host ("{0,-20} : {1}" -f $svc.Name, $pct)
    } else {
        Write-Host ("{0,-20} : No coverage.out found" -f $svc.Name)
    }
}
Write-Host "=========================================="
