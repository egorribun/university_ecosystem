#!/usr/bin/env bash
# Go Services Coverage Report Aggregator
set -euo pipefail

echo "=========================================="
echo "        Go Services Coverage Report       "
echo "=========================================="

declare -A services=(
  ["gateway"]="services/gateway"
  ["ws-hub"]="services/ws-hub"
  ["file-processor"]="services/file-processor"
  ["uni-cli"]="services/cmd/uni-cli"
)

for name in "${!services[@]}"; do
  path="${services[$name]}"
  cov_file="$path/coverage.out"
  if [[ -f "$cov_file" ]]; then
    pct=$(go tool cover -func="$cov_file" | tail -1 | awk '{print $3}')
    printf "%-20s : %s\n" "$name" "$pct"
  else
    printf "%-20s : No coverage.out found\n" "$name"
  fi
done
echo "=========================================="
