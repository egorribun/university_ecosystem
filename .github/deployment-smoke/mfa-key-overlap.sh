#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
user_agent="University-Ecosystem-MFA-Rotation-Smoke/1"
timeout_seconds="${MFA_SMOKE_TIMEOUT_SECONDS:-240}"
otp_ttl_seconds=600
otp_expiry_safety_seconds=30

fail() {
  echo "::error::$1" >&2
  exit 1
}

for command_name in curl jq date awk realpath; do
  command -v "$command_name" >/dev/null 2>&1 || fail "Required command '$command_name' is unavailable."
done

required=(
  MFA_SMOKE_BASE_URL MFA_SMOKE_MAILBOX_URL MFA_SMOKE_EMAIL
  MFA_SMOKE_PASSWORD MFA_SMOKE_MAILBOX_TOKEN MFA_SMOKE_STATE_DIR RUNNER_TEMP
)
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || fail "Required MFA rotation smoke input '$name' is empty."
done
[[ "$MFA_SMOKE_BASE_URL" =~ ^https://[^[:space:]]+$ ]] || fail "MFA_SMOKE_BASE_URL must be HTTPS."
[[ "$MFA_SMOKE_MAILBOX_URL" =~ ^https://[^[:space:]]+$ ]] || fail "MFA_SMOKE_MAILBOX_URL must be HTTPS."
[[ "$timeout_seconds" =~ ^[0-9]+$ ]] || fail "MFA_SMOKE_TIMEOUT_SECONDS must be numeric."
(( timeout_seconds >= 30 && timeout_seconds <= 600 )) || fail "MFA_SMOKE_TIMEOUT_SECONDS must be between 30 and 600."

runner_temp="$(realpath "$RUNNER_TEMP")"
state_dir="$(realpath "$MFA_SMOKE_STATE_DIR")"
[[ "$state_dir" == "$runner_temp"/* ]] || fail "MFA_SMOKE_STATE_DIR must stay under RUNNER_TEMP."
chmod 700 "$state_dir"
state_file="$state_dir/old-challenge.json"
old_verified_file="$state_dir/old-verified"
old_cookies="$state_dir/old-cookies.txt"
new_cookies="$state_dir/new-cookies.txt"
base_url="${MFA_SMOKE_BASE_URL%/}"

csrf_token() {
  local cookie_file="$1"
  awk '$6 == "csrf_token" { token=$7 } END { print token }' "$cookie_file"
}

bootstrap_csrf() {
  local cookie_file="$1"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --user-agent "$user_agent" \
    --cookie "$cookie_file" --cookie-jar "$cookie_file" \
    --output /dev/null "$base_url/api/v1/auth/csrf-cookie"
  [[ -n "$(csrf_token "$cookie_file")" ]] || fail "The API did not issue a CSRF cookie."
}

post_api() {
  local endpoint="$1"
  local cookie_file="$2"
  local payload_file="$3"
  local response_file="$4"
  local csrf
  local status
  csrf="$(csrf_token "$cookie_file")"
  [[ -n "$csrf" ]] || fail "CSRF cookie is unavailable for $endpoint."
  status="$(curl --silent --show-error --proto '=https' --tlsv1.2 \
    --user-agent "$user_agent" \
    --cookie "$cookie_file" --cookie-jar "$cookie_file" \
    --header "Content-Type: application/json" \
    --header "X-CSRF-Token: $csrf" \
    --request POST --data-binary "@$payload_file" \
    --output "$response_file" --write-out '%{http_code}' \
    "$base_url$endpoint")"
  [[ "$status" == "200" || "$status" == "202" ]] || fail "$endpoint returned HTTP $status."
}

issue_email_otp() {
  local cookie_file="$1"
  local response_file="$2"
  local payload_file="$state_dir/login-payload.json"
  bootstrap_csrf "$cookie_file"
  jq --null-input --arg email "$MFA_SMOKE_EMAIL" --arg password "$MFA_SMOKE_PASSWORD" \
    '{email: $email, password: $password, trust_device: false}' > "$payload_file"
  chmod 600 "$payload_file"
  post_api "/api/v1/auth/login/json" "$cookie_file" "$payload_file" "$response_file"
  jq --exit-status '
    .status == "mfa_required" and
    ([.methods[] | select(.method == "email_otp")] | length == 1)
  ' "$response_file" >/dev/null || fail "Login did not issue exactly one email OTP challenge."
  jq --raw-output '[.methods[] | select(.method == "email_otp")][0].challenge_token' \
    "$response_file"
}

await_delivery() {
  local generation="$1"
  local challenge_token="$2"
  local response_file="$3"
  local delivery_timeout_seconds="${4:-$timeout_seconds}"
  local payload_file="$state_dir/mailbox-$generation-request.json"
  local status
  jq --null-input --arg operation "await_email_otp" \
    --arg challenge_token "$challenge_token" \
    --argjson timeout_seconds "$delivery_timeout_seconds" \
    '{operation: $operation, challenge_token: $challenge_token, timeout_seconds: $timeout_seconds}' \
    > "$payload_file"
  chmod 600 "$payload_file"
  status="$(curl --silent --show-error --proto '=https' --tlsv1.2 \
    --header "Authorization: Bearer $MFA_SMOKE_MAILBOX_TOKEN" \
    --header "Content-Type: application/json" \
    --request POST --data-binary "@$payload_file" \
    --output "$response_file" --write-out '%{http_code}' \
    "$MFA_SMOKE_MAILBOX_URL")"
  [[ "$status" == "200" ]] || fail "Mailbox probe returned HTTP $status for $generation delivery."
  jq --exit-status --arg challenge_token "$challenge_token" '
    .status == "delivered" and
    .challenge_token == $challenge_token and
    (.delivery_id | type == "string" and test("^[0-9a-fA-F-]{36}$")) and
    (.code | type == "string" and test("^[0-9]{6}$")) and
    (.delivered_at | type == "string" and length > 0)
  ' "$response_file" >/dev/null || fail "Mailbox probe returned an invalid $generation delivery proof."
}

verify_email_otp() {
  local generation="$1"
  local cookie_file="$2"
  local challenge_token="$3"
  local code="$4"
  local payload_file="$state_dir/verify-$generation-request.json"
  local response_file="$state_dir/verify-$generation-response.json"
  jq --null-input --arg challenge_token "$challenge_token" --arg code "$code" \
    '{method: "email_otp", challenge_token: $challenge_token, code: $code}' \
    > "$payload_file"
  chmod 600 "$payload_file"
  post_api "/api/v1/auth/mfa/verify" "$cookie_file" "$payload_file" "$response_file"
  jq --exit-status '(.user.id | type == "string" and length > 0)' \
    "$response_file" >/dev/null || fail "$generation email OTP verification did not return a user."
  awk '$6 == "access_token_v2" && length($7) > 0 { found=1 } END { exit !found }' \
    "$cookie_file" || fail "$generation email OTP verification did not authenticate."
}

case "$mode" in
  prepare)
    [[ ! -e "$state_file" ]] || fail "Old-challenge state already exists; refusing stale reuse."
    : > "$old_cookies"
    chmod 600 "$old_cookies"
    old_login_response="$state_dir/old-login-response.json"
    old_challenge_token="$(issue_email_otp "$old_cookies" "$old_login_response")"
    [[ "$old_challenge_token" =~ ^[A-Za-z0-9_.-]{32,128}$ ]] || fail "Old challenge token is invalid."
    jq --null-input --arg challenge_token "$old_challenge_token" \
      --argjson queued_at_epoch "$(date +%s)" \
      '{challenge_token: $challenge_token, queued_at_epoch: $queued_at_epoch}' > "$state_file"
    chmod 600 "$state_file"
    ;;
  verify-old)
    [[ -s "$state_file" && -s "$old_cookies" ]] || fail "Prepared old challenge state is unavailable."
    old_challenge_token="$(jq --raw-output '.challenge_token // empty' "$state_file")"
    queued_at_epoch="$(jq --raw-output '.queued_at_epoch // empty' "$state_file")"
    [[ "$old_challenge_token" =~ ^[A-Za-z0-9_.-]{32,128}$ ]] || fail "Stored old challenge token is invalid."
    [[ "$queued_at_epoch" =~ ^[0-9]+$ ]] || fail "Stored queue timestamp is invalid."

    current_epoch="$(date +%s)"
    old_expires_at=$((queued_at_epoch + otp_ttl_seconds))
    old_delivery_timeout_seconds=$((old_expires_at - current_epoch - otp_expiry_safety_seconds))
    (( old_delivery_timeout_seconds > 0 )) || fail "Old challenge is too close to expiry for safe verification."
    if (( old_delivery_timeout_seconds > timeout_seconds )); then
      old_delivery_timeout_seconds="$timeout_seconds"
    fi

    old_delivery="$state_dir/old-delivery.json"
    await_delivery old "$old_challenge_token" "$old_delivery" "$old_delivery_timeout_seconds"
    old_delivered_at="$(date -d "$(jq --raw-output '.delivered_at' "$old_delivery")" +%s)"
    (( old_delivered_at >= queued_at_epoch )) || fail "Old delivery predates the queued overlap challenge."
    old_code="$(jq --raw-output '.code' "$old_delivery")"
    verify_email_otp old "$old_cookies" "$old_challenge_token" "$old_code"
    printf '%s' "$(date +%s)" > "$old_verified_file"
    chmod 600 "$old_verified_file"
    ;;
  verify-new)
    [[ -s "$old_verified_file" ]] || fail "Old-key overlap verification did not complete."
    old_delivery="$state_dir/old-delivery.json"
    [[ -s "$old_delivery" ]] || fail "Old delivery proof is unavailable."
    old_delivery_id="$(jq --raw-output '.delivery_id // empty' "$old_delivery")"
    [[ "$old_delivery_id" =~ ^[0-9a-fA-F-]{36}$ ]] || fail "Old delivery proof is invalid."

    : > "$new_cookies"
    chmod 600 "$new_cookies"
    new_login_response="$state_dir/new-login-response.json"
    new_challenge_token="$(issue_email_otp "$new_cookies" "$new_login_response")"
    [[ "$new_challenge_token" != "$old_challenge_token" ]] || fail "New issue reused the old challenge token."
    new_delivery="$state_dir/new-delivery.json"
    await_delivery new "$new_challenge_token" "$new_delivery"
    new_delivery_id="$(jq --raw-output '.delivery_id' "$new_delivery")"
    [[ "$new_delivery_id" != "$old_delivery_id" ]] || fail "New issue reused the old delivery envelope."
    new_code="$(jq --raw-output '.code' "$new_delivery")"
    verify_email_otp new "$new_cookies" "$new_challenge_token" "$new_code"
    ;;
  *)
    fail "Usage: $0 {prepare|verify-old|verify-new}"
    ;;
esac
