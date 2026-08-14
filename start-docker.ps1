<#
.SYNOPSIS
    Start the University Ecosystem site using Docker Compose.

.DESCRIPTION
    Builds and starts all Docker containers for the full site.
    Generates secure secrets if .env / .env.docker don't exist.
    Reconciles the MinIO bucket and auxiliary databases on every start.

.EXAMPLE
    .\start-docker.ps1            # Start (no rebuild)
    .\start-docker.ps1 -Build     # Build (cached) then start
    .\start-docker.ps1 -Rebuild   # Build (no-cache) then start
    .\start-docker.ps1 -Down      # Stop all containers
    .\start-docker.ps1 -Logs                  # Follow all logs
    .\start-docker.ps1 -Logs -LogService backend  # Follow one service
#>

param(
    [switch]$Build,
    [switch]$Rebuild,
    [switch]$Down,
    [switch]$Logs,
    [string]$LogService = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$ComposeFile = "docker-compose.full.yml"
$EnvFile = ".env.docker"
$EnvCompose = ".env"
$OpenSslFallbackImage = "alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"

# -- Helpers ------------------------------------------------------------------

function Write-Status  { param([string]$Msg) Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Err     { param([string]$Msg) Write-Host "[-] $Msg" -ForegroundColor Red }
function Write-Warn    { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }

function New-Secret {
    param([int]$Length = 32)
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    $builder = [System.Text.StringBuilder]::new($Length)
    for ($i = 0; $i -lt $Length; $i++) {
        $index = [System.Security.Cryptography.RandomNumberGenerator]::GetInt32($chars.Length)
        $null = $builder.Append($chars[$index])
    }
    return $builder.ToString()
}

function New-HexSecret {
    param([int]$Length = 32)
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes($Length)
    return [System.Convert]::ToHexString($bytes).ToLowerInvariant()
}

function New-FernetKey {
    # Fernet requires exactly 32 random bytes encoded with padded URL-safe
    # Base64. Keep this native so a fresh launcher does not depend on Python.
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    return [System.Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText(
        (Join-Path $ProjectRoot $Path),
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Get-EnvEntry {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Key
    )

    $absolutePath = Join-Path $ProjectRoot $Path
    if (-not (Test-Path -LiteralPath $absolutePath)) { return $null }

    $prefix = "$Key="
    $line = Get-Content -LiteralPath $absolutePath -ErrorAction SilentlyContinue |
        Where-Object { $_.StartsWith($prefix, [StringComparison]::Ordinal) } |
        Select-Object -First 1
    if ($null -eq $line) { return $null }
    return $line.Substring($prefix.Length).Trim()
}

function Set-EnvEntry {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Key,
        [Parameter(Mandatory=$true)][string]$Value
    )

    $absolutePath = Join-Path $ProjectRoot $Path
    $prefix = "$Key="
    $found = $false
    $updated = @(
        Get-Content -LiteralPath $absolutePath -ErrorAction SilentlyContinue |
            ForEach-Object {
                if ($_.StartsWith($prefix, [StringComparison]::Ordinal)) {
                    $found = $true
                    "$Key=$Value"
                } else {
                    $_
                }
            }
    )
    if (-not $found) { $updated += "$Key=$Value" }
    Write-Utf8NoBom -Path $Path -Content "$(($updated -join "`n").TrimEnd())`n"
}

function Ensure-ImgproxyEnvironment {
    # .env.docker is canonical because both the backend signer and imgproxy read
    # it. Keep .env synchronized for Compose interpolation and migrate the old
    # frontend URL, which could never serve signed image paths.
    $specs = @(
        @{ Key = "IMGPROXY_KEY"; Bytes = 32 },
        @{ Key = "IMGPROXY_SALT"; Bytes = 32 }
    )

    foreach ($spec in $specs) {
        $value = Get-EnvEntry -Path $EnvFile -Key $spec.Key
        # Accept any even-length hex value of at least 32 bytes. This matches
        # the backend validator and preserves deliberately longer user keys.
        $pattern = "^(?:[0-9a-fA-F]{2}){$($spec.Bytes),}$"
        if (-not $value -or $value -notmatch $pattern) {
            $value = New-HexSecret -Length $spec.Bytes
            Set-EnvEntry -Path $EnvFile -Key $spec.Key -Value $value
            Write-Ok "Generated $($spec.Key) for signed image URLs"
        }

        if ((Get-EnvEntry -Path $EnvCompose -Key $spec.Key) -ne $value) {
            Set-EnvEntry -Path $EnvCompose -Key $spec.Key -Value $value
        }
    }

    $baseUrl = Get-EnvEntry -Path $EnvFile -Key "IMGPROXY_BASE_URL"
    if (-not $baseUrl -or $baseUrl -eq "http://localhost:8081") {
        $baseUrl = "http://localhost/imgproxy"
        Set-EnvEntry -Path $EnvFile -Key "IMGPROXY_BASE_URL" -Value $baseUrl
        Write-Ok "Configured IMGPROXY_BASE_URL through Caddy"
    }
    if ((Get-EnvEntry -Path $EnvCompose -Key "IMGPROXY_BASE_URL") -ne $baseUrl) {
        Set-EnvEntry -Path $EnvCompose -Key "IMGPROXY_BASE_URL" -Value $baseUrl
    }
}

function Ensure-MetricsEnvironment {
    # Prometheus authenticates to the backend /metrics endpoint. Keep one
    # launcher-managed credential in both environment files so the backend and
    # Prometheus receive the same value without committing it to the repository.
    # prometheus.yml intentionally uses a fixed non-secret identity. Do not
    # preserve an arbitrary legacy username or the two sides will disagree.
    $username = "metrics_scraper"

    $password = Get-EnvEntry -Path $EnvFile -Key "METRICS_BASIC_AUTH_PASSWORD"
    if (-not $password -or $password.Length -lt 32 -or $password -match "CHANGE_ME") {
        $password = New-Secret -Length 48
        Write-Ok "Generated backend metrics scrape credentials"
    }

    foreach ($path in @($EnvFile, $EnvCompose)) {
        Set-EnvEntry -Path $path -Key "ENABLE_METRICS_ENDPOINT" -Value "true"
        Set-EnvEntry -Path $path -Key "METRICS_BASIC_AUTH_USERNAME" -Value $username
        Set-EnvEntry -Path $path -Key "METRICS_BASIC_AUTH_PASSWORD" -Value $password
    }
}

function Ensure-ApplicationSecrets {
    # Remove development fallbacks that couple unrelated security domains to
    # SECRET_KEY. .env.docker remains canonical and .env is synchronized for
    # values interpolated directly into Compose service environments.
    $specs = @(
        @{ Key = "CSRF_HMAC_SECRET"; Length = 48; Fernet = $false },
        @{ Key = "INTERNAL_HMAC_SECRET"; Length = 48; Fernet = $false },
        @{ Key = "IDEMPOTENCY_HMAC_SECRET"; Length = 48; Fernet = $false },
        @{ Key = "SPOTIFY_TOKEN_SECRET"; Length = 44; Fernet = $true },
        @{ Key = "SPOTIFY_OAUTH_STATE_SECRET"; Length = 48; Fernet = $false }
    )

    foreach ($spec in $specs) {
        $value = Get-EnvEntry -Path $EnvFile -Key $spec.Key
        $invalid = -not $value -or $value -match "CHANGE_ME"
        if ($spec.Fernet) {
            $invalid = $invalid -or $value -notmatch '^[A-Za-z0-9_-]{43}=$'
        } else {
            $invalid = $invalid -or $value.Length -lt 32
        }

        if ($invalid) {
            $value = if ($spec.Fernet) { New-FernetKey } else { New-Secret -Length $spec.Length }
            Write-Ok "Generated independent $($spec.Key)"
        }

        foreach ($path in @($EnvFile, $EnvCompose)) {
            if ((Get-EnvEntry -Path $path -Key $spec.Key) -ne $value) {
                Set-EnvEntry -Path $path -Key $spec.Key -Value $value
            }
        }
    }
}

function Ensure-JwtEnvironment {
    # The launcher-managed keypair is the single signing source for both the
    # full and base Compose modes, so keep their environment files aligned.
    foreach ($path in @($EnvFile, $EnvCompose)) {
        Set-EnvEntry -Path $path -Key "ALGORITHM" -Value "RS256"
        Set-EnvEntry -Path $path -Key "JWT_PRIVATE_KEY_PATH" -Value ".secrets/jwt_rs256.pem"
    }
}

function Ensure-DockerConfigRevision {
    # Compose does not notice changes inside bind-mounted files. Fold every
    # runtime configuration file into a deterministic label so `compose up`
    # recreates only the affected configuration-driven services after a pull.
    $relativePaths = @(
        "config/nats.conf.template",
        "services/temporal/config.yaml",
        "services/temporal/entrypoint.sh",
        "infrastructure/observability/prometheus.yml",
        "infrastructure/observability/alerts/gateway.yaml",
        "infrastructure/observability/tempo.yaml",
        "infrastructure/observability/loki.yaml",
        "infrastructure/observability/alloy/config.alloy",
        "infrastructure/observability/grafana/provisioning/datasources/datasources.yaml",
        "infrastructure/Caddyfile"
    )
    $manifest = foreach ($relativePath in $relativePaths) {
        $absolutePath = Join-Path $ProjectRoot $relativePath
        if (-not (Test-Path -LiteralPath $absolutePath)) {
            throw "Runtime configuration file is missing: $relativePath"
        }
        "$relativePath=$((Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256).Hash)"
    }

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes(($manifest -join "`n"))
        $revision = [System.Convert]::ToHexString($sha256.ComputeHash($bytes)).ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }

    foreach ($path in @($EnvFile, $EnvCompose)) {
        Set-EnvEntry -Path $path -Key "DOCKER_CONFIG_REVISION" -Value $revision
    }
}

# Validate an existing launcher-managed private key before treating it as an
# idempotent result. A truncated or public-only PEM would otherwise make every
# backend restart fail until the user manually deleted the file.
function Test-JwtRs256PrivateKey {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $pem = [System.IO.File]::ReadAllText($Path)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($pem)
            $privateParameters = $rsa.ExportParameters($true)
            return $rsa.KeySize -ge 2048 -and $null -ne $privateParameters.D -and $privateParameters.D.Length -gt 0
        } finally {
            $rsa.Dispose()
        }
    } catch {
        return $false
    }
}

# Wave 137 SW1: Generate RSA-2048 keypair for backend JWT RS256 signing.
# Idempotent only after validating the existing private key.
# Uses .NET 8 native PEM export (PowerShell 7+ ships .NET 8 with
# RSA.ExportPkcs8PrivateKeyPem). Falls back to OpenSSL if available.
# Closes W135 sec.Honesty #9 SSR auth-at-edge layer (jose.createRemoteJWKSet
# requires RS256; pre-W137 dev backend signed HS256).
function New-JwtRs256Key {
    param([string]$OutputPath = ".secrets/jwt_rs256.pem")

    $absoluteOutputPath = Join-Path $ProjectRoot $OutputPath
    if (Test-JwtRs256PrivateKey -Path $absoluteOutputPath) {
        Write-Ok "RSA-2048 keypair already exists at $OutputPath (idempotent skip)"
        return
    }
    if (Test-Path -LiteralPath $absoluteOutputPath) {
        Write-Warn "RSA private key at $OutputPath is invalid; regenerating"
    }

    Write-Status "Generating RSA-2048 keypair for JWT RS256 signing..."

    $secretsDir = Split-Path $absoluteOutputPath -Parent
    if (-not (Test-Path $secretsDir)) {
        New-Item -ItemType Directory -Path $secretsDir -Force | Out-Null
    }

    $pem = $null
    try {
        # Path A: .NET 8 native PEM export (preferred, no external deps)
        $rsa = [System.Security.Cryptography.RSA]::Create(2048)
        try {
            $pem = $rsa.ExportPkcs8PrivateKeyPem()
        } finally {
            $rsa.Dispose()
        }
    } catch {
        # Path B: host openssl fallback (requires openssl in PATH)
        if (Get-Command openssl -ErrorAction SilentlyContinue) {
            $tempKey = [System.IO.Path]::GetTempFileName()
            try {
                $null = openssl genrsa -out $tempKey 2048 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $pem = Get-Content $tempKey -Raw
                }
            } finally {
                Remove-Item $tempKey -ErrorAction SilentlyContinue
            }
        }

        # Path C: docker fallback (runs openssl in lightweight container if host openssl unavailable)
        if (-not $pem -and (Get-Command docker -ErrorAction SilentlyContinue)) {
            Write-Status "Falling back to Docker openssl for keypair generation..."
            $pem = docker run --rm $OpenSslFallbackImage sh -c "apk add --no-cache openssl >/dev/null 2>&1; openssl genrsa 2048 2>/dev/null" 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0 -or $pem -notmatch "BEGIN (RSA )?PRIVATE KEY") {
                $pem = $null
            }
        }
    }

    if (-not $pem) {
        throw "Failed to generate RSA private key - neither .NET, host openssl, nor docker openssl succeeded."
    }

    [System.IO.File]::WriteAllText(
        $absoluteOutputPath,
        $pem.Trim(),
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Ok "Generated RSA-2048 keypair at $OutputPath"
}

# Derive the RSA public key used directly by file-processor. Temporal validates
# through the backend JWKS endpoint, which serves the same private key's public
# component. Re-derive on each launcher run and update only when content drifted
# so a deliberately replaced private key cannot leave a stale verifier behind.
function New-JwtRs256PublicKey {
    param(
        [string]$PrivateKeyPath = ".secrets/jwt_rs256.pem",
        [string]$OutputPath = ".secrets/jwt_rs256.pub.pem"
    )

    $absolutePrivateKeyPath = Join-Path $ProjectRoot $PrivateKeyPath
    $absoluteOutputPath = Join-Path $ProjectRoot $OutputPath

    if (-not (Test-Path $absolutePrivateKeyPath)) {
        throw "Cannot derive public key: private key not found at $PrivateKeyPath. Run New-JwtRs256Key first."
    }

    Write-Status "Deriving RSA-2048 public key from $PrivateKeyPath..."

    $publicPem = $null
    try {
        # Path A: .NET 8 native - RSA.ImportFromPem + ExportSubjectPublicKeyInfoPem
        $privatePem = [System.IO.File]::ReadAllText($absolutePrivateKeyPath)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($privatePem)
            $publicPem = $rsa.ExportSubjectPublicKeyInfoPem()
        } finally {
            $rsa.Dispose()
        }
    } catch {
        # Path B: host openssl fallback (requires openssl in PATH)
        if (Get-Command openssl -ErrorAction SilentlyContinue) {
            $publicPem = openssl rsa -in $absolutePrivateKeyPath -pubout 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) {
                $publicPem = $null
            }
        }

        # Path C: docker fallback (mounts .secrets dir and runs openssl rsa -pubout)
        if (-not $publicPem -and (Get-Command docker -ErrorAction SilentlyContinue)) {
            $secretDirAbs = Split-Path $absolutePrivateKeyPath -Parent
            $privKeyFile = Split-Path $absolutePrivateKeyPath -Leaf
            $publicPem = docker run --rm -v "${secretDirAbs}:/secrets:ro" $OpenSslFallbackImage sh -c "apk add --no-cache openssl >/dev/null 2>&1; openssl rsa -in /secrets/${privKeyFile} -pubout 2>/dev/null" 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0 -or $publicPem -notmatch "BEGIN PUBLIC KEY") {
                $publicPem = $null
            }
        }
    }

    if (-not $publicPem) {
        throw "Failed to derive RSA public key - neither .NET, host openssl, nor docker openssl succeeded."
    }

    $publicPem = $publicPem.Trim()
    if (Test-Path -LiteralPath $absoluteOutputPath) {
        $existingPublicPem = [System.IO.File]::ReadAllText($absoluteOutputPath).Trim()
        if ($existingPublicPem -ceq $publicPem) {
            Write-Ok "RSA-2048 public key at $OutputPath is current (idempotent skip)"
            return
        }
        Write-Warn "RSA public key at $OutputPath does not match the private key; updating"
    }

    [System.IO.File]::WriteAllText(
        $absoluteOutputPath,
        $publicPem,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Ok "Derived RSA-2048 public key at $OutputPath"
}

# Wave 141 SW4: helper for base64url encoding (JWT spec). Used by
# New-TemporalServiceToken below. Generic enough to share with future helpers.
function ConvertTo-Base64Url {
    param([Parameter(Mandatory=$true)][byte[]]$Bytes)
    return [System.Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function ConvertFrom-Base64Url {
    param([Parameter(Mandatory=$true)][string]$Value)
    $padded = $Value.Replace('-', '+').Replace('_', '/')
    switch ($padded.Length % 4) {
        2 { $padded += '==' }
        3 { $padded += '=' }
        1 { throw "Invalid base64url value" }
    }
    return [System.Convert]::FromBase64String($padded)
}

function Test-TemporalServiceToken {
    param(
        [Parameter(Mandatory=$true)][string]$Token,
        [Parameter(Mandatory=$true)][string]$PrivateKeyPath,
        [Parameter(Mandatory=$true)][string]$Subject,
        [Parameter(Mandatory=$true)][string]$Audience,
        [int]$MinimumValiditySeconds = 604800
    )

    try {
        $parts = $Token.Trim().Split('.')
        if ($parts.Count -ne 3) { return $false }

        $headerJson = [System.Text.Encoding]::UTF8.GetString((ConvertFrom-Base64Url $parts[0]))
        $payloadJson = [System.Text.Encoding]::UTF8.GetString((ConvertFrom-Base64Url $parts[1]))
        $header = $headerJson | ConvertFrom-Json
        $payload = $payloadJson | ConvertFrom-Json
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

        if ($header.alg -ne 'RS256' -or $header.kid -ne 'primary') { return $false }
        if ($payload.sub -ne $Subject -or $payload.aud -ne $Audience) { return $false }
        if (-not $payload.jti -or $null -eq $payload.iat -or $null -eq $payload.exp) { return $false }
        if ([long]$payload.iat -gt ($now + 60)) { return $false }
        if ([long]$payload.exp -le ($now + $MinimumValiditySeconds)) { return $false }

        $pem = [System.IO.File]::ReadAllText($PrivateKeyPath)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($pem)
            $signedBytes = [System.Text.Encoding]::UTF8.GetBytes("$($parts[0]).$($parts[1])")
            $signature = ConvertFrom-Base64Url $parts[2]
            return $rsa.VerifyData(
                $signedBytes,
                $signature,
                [System.Security.Cryptography.HashAlgorithmName]::SHA256,
                [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
            )
        } finally {
            $rsa.Dispose()
        }
    } catch {
        return $false
    }
}

# Wave 141 SW4: mint long-lived service token (~1 year exp) signed with the
# same RSA private key backend uses for its JWTs. Token has sub=
# file-processor-service + aud=temporal claims so Temporal's default JWT claim
# mapper (W141 SW2 verified - common/authorization/default_jwt_claim_mapper.go)
# recognizes it via the JWKS endpoint at /.well-known/jwks.json.
#
# Closes W137 sec.Honesty #5 + W140 NEW #6 (joined with SW3 image swap + SW5 Go
# credentials attach to form the full Path (a-auth) chain).
#
# Idempotent: keeps an existing token only after its claims, lifetime, algorithm,
# and RSA signature have been validated. Invalid or near-expiry tokens are
# replaced automatically.
#
# Security framing: this is a STATIC long-lived service token (no rotation).
# Acceptable for dev compose where the threat model is "anyone with host
# filesystem access". Production K8s deployments use managed Temporal Cloud /
# Helm chart with proper rotation infrastructure - this token NEVER ships to
# production.
#
# Issue temporalio/temporal#8218 mitigation: subject claim name is hardcoded
# as "sub" in default_jwt_claim_mapper.go:19. We mint with sub=
# file-processor-service to match this hardcoded expectation.
function New-TemporalServiceToken {
    param(
        [string]$PrivateKeyPath = ".secrets/jwt_rs256.pem",
        [string]$OutputPath = ".secrets/temporal_api_key",
        [string]$Subject = "file-processor-service",
        [string]$Audience = "temporal",
        [int]$ExpirationSeconds = 31536000  # 1 year (dev-only)
    )

    $absoluteOutputPath = Join-Path $ProjectRoot $OutputPath
    $absolutePrivateKeyPath = Join-Path $ProjectRoot $PrivateKeyPath
    if (-not (Test-Path $absolutePrivateKeyPath)) {
        throw "Cannot mint Temporal service token: private key not found at $PrivateKeyPath. Run New-JwtRs256Key first."
    }

    if (Test-Path $absoluteOutputPath) {
        $existingToken = [System.IO.File]::ReadAllText($absoluteOutputPath).Trim()
        if (Test-TemporalServiceToken -Token $existingToken -PrivateKeyPath $absolutePrivateKeyPath -Subject $Subject -Audience $Audience) {
            Write-Ok "Valid existing Temporal service token at $OutputPath (idempotent skip)"
            return
        }
        Write-Warn "Temporal service token at $OutputPath is invalid or near expiry; regenerating"
        Remove-Item -LiteralPath $absoluteOutputPath -Force
    }

    $days = [Math]::Round($ExpirationSeconds / 86400)
    Write-Status "Minting Temporal service token (sub=$Subject, aud=$Audience, $days days valid)..."

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $exp = $now + $ExpirationSeconds
    $jti = [Guid]::NewGuid().ToString("N")
    $headerObj  = [PSCustomObject]@{ alg = 'RS256'; kid = 'primary'; typ = 'JWT' }
    $payloadObj = [PSCustomObject]@{
        sub = $Subject
        aud = $Audience
        iat = $now
        exp = $exp
        jti = $jti
    }

    $headerJson  = $headerObj  | ConvertTo-Json -Compress
    $payloadJson = $payloadObj | ConvertTo-Json -Compress

    $headerB64  = ConvertTo-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($headerJson))
    $payloadB64 = ConvertTo-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($payloadJson))

    $signingInput = "$headerB64.$payloadB64"

    $signatureB64 = $null
    try {
        # Path A: .NET 8 native - RSA.ImportFromPem + SignData
        $pem = [System.IO.File]::ReadAllText($absolutePrivateKeyPath)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($pem)
            $signingInputBytes = [System.Text.Encoding]::UTF8.GetBytes($signingInput)
            $signatureBytes    = $rsa.SignData(
                $signingInputBytes,
                [System.Security.Cryptography.HashAlgorithmName]::SHA256,
                [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
            )
            $signatureB64 = ConvertTo-Base64Url $signatureBytes
        } finally {
            $rsa.Dispose()
        }
    } catch {
        # Path B: host openssl fallback (requires openssl in PATH)
        if (Get-Command openssl -ErrorAction SilentlyContinue) {
            $tempInputFile = [System.IO.Path]::GetTempFileName()
            $tempSigFile   = [System.IO.Path]::GetTempFileName()
            try {
                [System.IO.File]::WriteAllText($tempInputFile, $signingInput, [System.Text.Encoding]::UTF8)
                $null = openssl dgst -sha256 -sign $absolutePrivateKeyPath -out $tempSigFile $tempInputFile 2>&1
                if ($LASTEXITCODE -eq 0 -and (Test-Path $tempSigFile)) {
                    $signatureBytes = [System.IO.File]::ReadAllBytes($tempSigFile)
                    $signatureB64   = ConvertTo-Base64Url $signatureBytes
                }
            } finally {
                Remove-Item $tempInputFile, $tempSigFile -ErrorAction SilentlyContinue
            }
        }

        # Path C: docker fallback (runs openssl in alpine container)
        if (-not $signatureB64 -and (Get-Command docker -ErrorAction SilentlyContinue)) {
            $secretDirAbs = Split-Path $absolutePrivateKeyPath -Parent
            $privKeyFile  = Split-Path $absolutePrivateKeyPath -Leaf
            $sigOut = docker run --rm -v "${secretDirAbs}:/secrets:ro" $OpenSslFallbackImage sh -c "apk add --no-cache openssl >/dev/null 2>&1; printf '%s' '$signingInput' | openssl dgst -sha256 -sign /secrets/${privKeyFile} 2>/dev/null | base64 | tr -d '\r\n' | tr '+/' '-_' | tr -d '='" 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0 -and $sigOut.Trim()) {
                $signatureB64 = $sigOut.Trim()
            }
        }
    }

    if (-not $signatureB64) {
        throw "Failed to sign Temporal service token - neither .NET, host openssl, nor docker openssl succeeded."
    }

    $token = "$signingInput.$signatureB64"

    [System.IO.File]::WriteAllText(
        $absoluteOutputPath,
        $token,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Ok "Generated Temporal service token at $OutputPath ($days days valid)"
}

function Test-ServiceHttp {
    param([string]$Url, [int]$Timeout = 2)
    try { (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $Timeout).StatusCode -eq 200 }
    catch { $false }
}

function Wait-PrometheusTargets {
    param([int]$Timeout = 75)

    $expectedJobs = @(
        "prometheus", "backend", "notifications-worker", "redis-exporter",
        "minio", "tempo", "loki", "pyroscope", "gateway"
    )
    $deadline = (Get-Date).AddSeconds($Timeout)
    $lastProblems = @("Prometheus target API has not responded yet")

    do {
        try {
            $response = Invoke-RestMethod `
                -Uri "http://localhost:9090/api/v1/targets?state=active" `
                -TimeoutSec 5
            $targets = @($response.data.activeTargets)
            $lastProblems = @()

            foreach ($job in $expectedJobs) {
                $jobTargets = @($targets | Where-Object { $_.labels.job -eq $job })
                if ($jobTargets.Count -eq 0) {
                    $lastProblems += "${job}: missing target"
                    continue
                }
                foreach ($target in $jobTargets) {
                    if ($target.health -ne "up") {
                        $reason = if ($target.lastError) { $target.lastError } else { "health=$($target.health)" }
                        $lastProblems += "${job}: $reason"
                    }
                }
            }

            if ($lastProblems.Count -eq 0) { return $true }
        } catch {
            $lastProblems = @("Prometheus target API: $($_.Exception.Message)")
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    foreach ($problem in $lastProblems) { Write-Err "  $problem" }
    return $false
}

# -- Prerequisite: Docker running ---------------------------------------------

Write-Status "Checking Docker..."
$dockerOk = $false
try {
    $null = docker info 2>$null
    $dockerOk = $LASTEXITCODE -eq 0
} catch { }

if (-not $dockerOk) {
    Write-Err "Docker is not running. Start Docker Desktop and try again."
    exit 1
}

# -- Handle -Down -------------------------------------------------------------

if ($Down) {
    Write-Status "Stopping all containers..."
    $envArgs = if (Test-Path $EnvFile) { @("--env-file", $EnvFile) } else { @() }
    docker compose -f $ComposeFile @envArgs down
    $composeExitCode = $LASTEXITCODE
    if ($composeExitCode -ne 0) {
        Write-Err "Failed to stop containers."
        exit $composeExitCode
    }
    Write-Ok "All containers stopped"
    exit $composeExitCode
}

# -- Handle -Logs -------------------------------------------------------------

if ($Logs) {
    $envArgs = if (Test-Path $EnvFile) { @("--env-file", $EnvFile) } else { @() }
    if ($LogService) {
        docker compose -f $ComposeFile @envArgs logs -f $LogService
    } else {
        docker compose -f $ComposeFile @envArgs logs -f
    }
    $composeExitCode = $LASTEXITCODE
    if ($composeExitCode -ne 0) {
        Write-Err "Failed to read container logs."
    }
    exit $composeExitCode
}

# -- Generate secrets ---------------------------------------------------------

$generated = $false

$needsEnvDocker = -not (Test-Path $EnvFile)
$needsEnvCompose = -not (Test-Path $EnvCompose)

if ($needsEnvDocker -and $needsEnvCompose) {
    # Both missing - fresh setup, generate from scratch
    Write-Status "Generating environment files with secure secrets..."

    $postgresPassword = New-Secret -Length 32
    $secretKey         = New-Secret -Length 64
    $minioPassword     = New-Secret -Length 32
    $redisPassword     = New-Secret -Length 32
    $elasticPassword   = New-Secret -Length 32
    $natsPassword      = New-Secret -Length 32
    $spicedbKey        = New-Secret -Length 32
    $wsHubSecret       = New-Secret -Length 32
    $grafanaPassword   = New-Secret -Length 32
    $metricsPassword   = New-Secret -Length 48
    $imgproxyKey       = New-HexSecret -Length 32
    $imgproxySalt      = New-HexSecret -Length 32
    $csrfHmacSecret    = New-Secret -Length 48
    $internalHmacSecret = New-Secret -Length 48
    $idempotencyHmacSecret = New-Secret -Length 48
    $spotifyTokenSecret = New-FernetKey
    $spotifyOauthStateSecret = New-Secret -Length 48

    # -- .env.docker (container env_file) ---------------------------------
    $dockerEnv = @"
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university
SECRET_KEY=$secretKey
ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem
ACCESS_TOKEN_EXPIRE_MINUTES=30
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword
ELASTIC_PASSWORD=$elasticPassword
NATS_USER=app
NATS_PASSWORD=$natsPassword
SPICEDB_PRESHARED_KEY=$spicedbKey
WS_HUB_INTERNAL_SECRET=$wsHubSecret
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
REDIS_PASSWORD=$redisPassword
ENABLE_METRICS_ENDPOINT=true
METRICS_BASIC_AUTH_USERNAME=metrics_scraper
METRICS_BASIC_AUTH_PASSWORD=$metricsPassword
IMGPROXY_KEY=$imgproxyKey
IMGPROXY_SALT=$imgproxySalt
IMGPROXY_BASE_URL=http://localhost/imgproxy
VAPID_SUBJECT=mailto:admin@example.com
ENVIRONMENT=development
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
SPOTIFY_SCOPES=
CSRF_HMAC_SECRET=$csrfHmacSecret
INTERNAL_HMAC_SECRET=$internalHmacSecret
IDEMPOTENCY_HMAC_SECRET=$idempotencyHmacSecret
SPOTIFY_TOKEN_SECRET=$spotifyTokenSecret
SPOTIFY_OAUTH_STATE_SECRET=$spotifyOauthStateSecret
"@
    Write-Utf8NoBom $EnvFile $dockerEnv

    # -- .env (compose interpolation) -------------------------------------
    $composeEnv = @"
# Auto-generated by start-docker.ps1 - used for docker compose interpolation.
# Passwords MUST match .env.docker. Re-run start-docker.ps1 after editing.
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university
SECRET_KEY=$secretKey
ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword
ELASTIC_PASSWORD=$elasticPassword
NATS_USER=app
NATS_PASSWORD=$natsPassword
SPICEDB_PRESHARED_KEY=$spicedbKey
WS_HUB_INTERNAL_SECRET=$wsHubSecret
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
REDIS_PASSWORD=$redisPassword
ENABLE_METRICS_ENDPOINT=true
METRICS_BASIC_AUTH_USERNAME=metrics_scraper
METRICS_BASIC_AUTH_PASSWORD=$metricsPassword
IMGPROXY_KEY=$imgproxyKey
IMGPROXY_SALT=$imgproxySalt
IMGPROXY_BASE_URL=http://localhost/imgproxy
ENVIRONMENT=development
VAPID_SUBJECT=mailto:admin@example.com
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
SPOTIFY_SCOPES=
CSRF_HMAC_SECRET=$csrfHmacSecret
INTERNAL_HMAC_SECRET=$internalHmacSecret
IDEMPOTENCY_HMAC_SECRET=$idempotencyHmacSecret
SPOTIFY_TOKEN_SECRET=$spotifyTokenSecret
SPOTIFY_OAUTH_STATE_SECRET=$spotifyOauthStateSecret
"@
    Write-Utf8NoBom $EnvCompose $composeEnv

    Write-Ok "Generated $EnvFile and $EnvCompose with secure secrets"
    $generated = $true
} elseif ($needsEnvDocker -and -not $needsEnvCompose) {
    # .env exists but .env.docker missing - copy .env as base for .env.docker
    Write-Warn ".env.docker missing - deriving from .env..."
    Copy-Item $EnvCompose $EnvFile
    Write-Ok "Created $EnvFile from $EnvCompose"
    $generated = $true
} elseif (-not $needsEnvDocker -and $needsEnvCompose) {
    # .env.docker exists but .env missing - derive .env from .env.docker
    Write-Warn ".env missing - deriving from .env.docker..."
    Copy-Item $EnvFile $EnvCompose
    Write-Ok "Created $EnvCompose from $EnvFile"
    $generated = $true
}

# Enable signed imgproxy URLs for both fresh and pre-existing local setups.
Ensure-ImgproxyEnvironment

# Enable authenticated Prometheus scraping for fresh and existing setups.
Ensure-MetricsEnvironment

# Give each application security domain an independent launcher-managed key.
Ensure-ApplicationSecrets

# Keep RS256 settings coherent in both supported Compose environment files.
Ensure-JwtEnvironment

# Make bind-mounted configuration changes visible to Compose's config hash.
Ensure-DockerConfigRevision

# -- Sync check: ensure .env has all required vars ----------------------------

if (-not $generated) {
    $envContent = Get-Content $EnvCompose -Raw -ErrorAction SilentlyContinue
    $missing = @()
    foreach ($key in @("WS_HUB_INTERNAL_SECRET", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD", "SPICEDB_PRESHARED_KEY", "GRAFANA_ADMIN_PASSWORD")) {
        if ($envContent -notmatch "(?m)^$key=") {
            $missing += $key
        }
    }
    if ($missing.Count -gt 0) {
        Write-Warn "Missing vars in .env: $($missing -join ', '). Reading from .env.docker..."
        $dockerLines = Get-Content $EnvFile -ErrorAction SilentlyContinue
        $patch = ""
        foreach ($key in $missing) {
            $line = $dockerLines | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
            if ($line) { $patch += "`n$line" }
        }
        if ($patch) {
            Add-Content -Path $EnvCompose -Value $patch -NoNewline:$false
            Write-Ok "Patched .env with missing vars"
        }
    }
}

# -- Wave 137 SW1: Generate RSA-2048 keypair for JWT RS256 signing -------------
# Backend reads .secrets/jwt_rs256.pem at startup (jwt_settings.py:202-205).
# Volume-mounted into container at /app/.secrets/jwt_rs256.pem.
New-JwtRs256Key -OutputPath ".secrets/jwt_rs256.pem"

# Derive the public key used directly by file-processor. Temporal obtains the
# same key from backend's JWKS endpoint and now waits for backend readiness, so
# its first authenticated request cannot race an empty key-provider cache.
New-JwtRs256PublicKey -PrivateKeyPath ".secrets/jwt_rs256.pem" -OutputPath ".secrets/jwt_rs256.pub.pem"

# -- Wave 141 SW4: Mint Temporal service token (RS256 JWT) ---------------------
# file-processor (W141 SW5) reads .secrets/temporal_api_key and attaches it to
# Temporal client via client.NewAPIKeyStaticCredentials(token). Temporal's
# default JWT claim mapper (W141 SW2 verified) validates via the JWKS endpoint
# at /.well-known/jwks.json. Existing tokens are retained only after their
# claims, expiry, algorithm, and RSA signature pass validation.
New-TemporalServiceToken

# -- Wave 137 SW2: SECRET_KEY drift detection .env <-> .env.docker ---------------
# Closes W136 polish-v2 finding: gateway's JWT_SECRET env reads from .env via
# compose's ${SECRET_KEY} substitution, while backend's env_file reads .env.docker.
# If .env's SECRET_KEY drifts (e.g. stale Pydantic placeholder), gateway HS256
# fallback path validates against the wrong secret -> 401 on every request.
# Less critical post-W137 SW1 RS256 (gateway uses JWKS path) but kept for
# defense-in-depth: fallback HS256 path must remain coherent.
if ((Test-Path $EnvFile) -and (Test-Path $EnvCompose)) {
    $envDockerSecret = (Select-String -Path $EnvFile -Pattern "^SECRET_KEY=(.+)$" -ErrorAction SilentlyContinue).Matches.Groups[1].Value
    $envComposeSecret = (Select-String -Path $EnvCompose -Pattern "^SECRET_KEY=(.+)$" -ErrorAction SilentlyContinue).Matches.Groups[1].Value

    if ($envDockerSecret -and $envComposeSecret -and $envDockerSecret -ne $envComposeSecret) {
        Write-Warn "SECRET_KEY drift detected between .env and .env.docker"
        Write-Status "Syncing .env SECRET_KEY to match .env.docker (canonical source)..."

        # Line-based replacement avoids regex special-char hazards in the
        # secret value (which is alphanumeric per New-Secret but defensive).
        $newLine = "SECRET_KEY=$envDockerSecret"
        $envComposeContent = (Get-Content $EnvCompose -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_ -match "^SECRET_KEY=") { $newLine } else { $_ }
        }) -join "`n"

        Write-Utf8NoBom $EnvCompose $envComposeContent.TrimEnd()
        Write-Ok "Synced .env SECRET_KEY (defense-in-depth for HS256 fallback path)"
    }
}

# -- Build --------------------------------------------------------------------

if ($Rebuild) {
    Write-Status "Rebuilding ALL images (no cache)..."
    docker compose -f $ComposeFile --env-file $EnvFile build --no-cache
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Build failed. Check output above."
        exit 1
    }
    Write-Ok "All images rebuilt"
} elseif ($Build) {
    Write-Status "Building images (cached)..."
    docker compose -f $ComposeFile --env-file $EnvFile build
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Build failed. Check output above."
        exit 1
    }
    Write-Ok "Images built"
}

# -- Start services -----------------------------------------------------------

Write-Status "Starting containers..."
# Compose recreates only services whose image or effective configuration
# changed. This keeps repeat starts fast while --remove-orphans retires services
# removed from the supported topology.
docker compose -f $ComposeFile --env-file $EnvFile up -d --remove-orphans
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to start containers."
    docker compose -f $ComposeFile --env-file $EnvFile ps --all
    docker compose -f $ComposeFile --env-file $EnvFile logs --tail=50 migrations postgres-databases-init minio-init spicedb-migrate temporal-admin-tools temporal-namespace-init backend outbox-worker 2>$null
    exit 1
}

# -- Health check loop --------------------------------------------------------

Write-Status "Waiting for services..."
$timeout = 300
$elapsed = 0
$services = [ordered]@{
    postgres      = @{ type = "docker"; service = "postgres"; ready = $false }
    redis         = @{ type = "docker"; service = "redis"; ready = $false }
    redisexporter = @{ type = "docker"; service = "redis-exporter"; ready = $false }
    backend       = @{ type = "docker"; service = "backend"; ready = $false }
    elasticsearch = @{ type = "docker"; service = "elasticsearch"; ready = $false }
    gateway       = @{ type = "http"; service = "gateway"; url = "http://localhost:8080/health"; ready = $false }
    minio         = @{ type = "http"; service = "minio"; url = "http://localhost:9001/"; ready = $false }
    temporal      = @{ type = "docker"; service = "temporal"; ready = $false }
    grafana       = @{ type = "http"; service = "grafana"; url = "http://localhost:3000/api/health"; ready = $false }
    notifications = @{ type = "docker"; service = "notifications-worker"; ready = $false }
    prometheus    = @{ type = "http"; service = "prometheus"; url = "http://localhost:9090/-/healthy"; ready = $false }
    # Probe a rendered route, not only the lightweight process health endpoint.
    # The first SSR render after an image update can take several seconds while
    # Node warms module caches, so give it a bounded one-time warmup window.
    frontend      = @{ type = "http"; service = "frontend"; url = "http://localhost:8081/login"; timeout = 20; ready = $false }
    imgproxy      = @{ type = "docker"; service = "imgproxy"; ready = $false }
    nats          = @{ type = "docker"; service = "nats"; ready = $false }
    outbox        = @{ type = "docker"; service = "outbox-worker"; ready = $false }
    spicedb       = @{ type = "docker"; service = "spicedb"; ready = $false }
    wshub         = @{ type = "http"; service = "ws-hub"; url = "http://localhost:8083/health"; ready = $false }
    caddy         = @{ type = "http"; service = "caddy"; url = "http://localhost/healthz"; ready = $false }
    site          = @{ type = "http"; service = "caddy"; url = "http://localhost/login"; timeout = 20; ready = $false }
    fileprocessor = @{ type = "docker"; service = "file-processor"; ready = $false }
    loki          = @{ type = "docker"; service = "loki-healthprobe"; ready = $false }
    tempo         = @{ type = "docker"; service = "tempo-healthprobe"; ready = $false }
    alloy         = @{ type = "docker"; service = "alloy"; ready = $false }
    pyroscope     = @{ type = "http"; service = "pyroscope"; url = "http://localhost:4040/ready"; ready = $false }
}

do {
    Start-Sleep -Seconds 5
    $elapsed += 5

    foreach ($name in $services.Keys) {
        if ($services[$name].ready) { continue }

        if ($services[$name].type -eq "docker") {
            $serviceName = $services[$name].service
            $infoStr = & { $ErrorActionPreference = "SilentlyContinue"; docker compose -f $ComposeFile --env-file $EnvFile ps $serviceName --format json 2>$null } | Out-String
            $info = if ($infoStr -match "\{") { $infoStr | ConvertFrom-Json } else { $null }
            $h = if ($info -is [array]) { $info[0].Health } else { $info.Health }
            $state = if ($info -is [array]) { $info[0].State } else { $info.State }
            if ($h -eq "healthy" -or ((-not $h) -and $state -eq "running")) {
                $services[$name].ready = $true
            }
        } else {
            $requestTimeout = if ($services[$name].ContainsKey("timeout")) {
                $services[$name].timeout
            } else {
                2
            }
            if (Test-ServiceHttp -Url $services[$name].url -Timeout $requestTimeout) {
                $services[$name].ready = $true
            }
        }
    }

    # Status line
    $statParts = @()
    foreach ($name in $services.Keys) {
        $icon = if ($services[$name].ready) { "+" } else { "." }
        $color = if ($services[$name].ready) { "Green" } else { "DarkGray" }
        $statParts += @{ name = $name; icon = $icon; color = $color }
    }
    Write-Host -NoNewline "  "
    foreach ($p in $statParts) {
        Write-Host -NoNewline "[$($p.icon)] $($p.name)  " -ForegroundColor $p.color
    }
    Write-Host ""  # newline

    $allReady = ($services.Values | Where-Object { -not $_.ready }).Count -eq 0

} while (-not $allReady -and $elapsed -lt $timeout)

if (-not $allReady) {
    Write-Err "Timeout after ${timeout}s. Failing services:"
    foreach ($name in $services.Keys) {
        if (-not $services[$name].ready) {
            $serviceName = $services[$name].service
            Write-Err "  $name ($serviceName) - showing last 15 log lines:"
            docker compose -f $ComposeFile --env-file $EnvFile logs --tail=15 $serviceName 2>$null
            Write-Host ""
        }
    }
    exit 1
}

Write-Status "Validating Prometheus scrape targets..."
if (-not (Wait-PrometheusTargets)) {
    Write-Err "Prometheus has missing or unhealthy scrape targets."
    exit 1
}
Write-Ok "Prometheus scrape targets are healthy"

# -- Done ---------------------------------------------------------------------

Write-Host ""
Write-Ok "University Ecosystem is running!"
Write-Host ""
Write-Host "  >> Site (use this):  http://localhost/" -ForegroundColor Green
Write-Host "     Caddy reverse proxy routes /api/* -> gateway:8080 -> backend:8000," -ForegroundColor DarkGray
Write-Host "     /ws/* -> ws-hub:8081, /sw.js -> frontend:3000, default -> frontend:3000." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Direct service ports (admin/debug only - browser API calls won't work)" -ForegroundColor Gray
Write-Host "  Frontend (Node SSR):  http://localhost:8081  (no /api proxy - use http://localhost/)" -ForegroundColor DarkYellow
Write-Host "  Gateway API:          http://localhost:8080" -ForegroundColor DarkYellow
Write-Host "  Backend API:          http://localhost:8000  (127.0.0.1 only)" -ForegroundColor DarkYellow
Write-Host "  API Docs:             http://localhost:8000/docs" -ForegroundColor DarkYellow
Write-Host "  WS Hub:               http://localhost:8083" -ForegroundColor DarkYellow
Write-Host "  MinIO Console:        http://localhost:9001" -ForegroundColor DarkYellow
Write-Host "  Grafana:              http://localhost:3000" -ForegroundColor DarkYellow
Write-Host "  Prometheus:           http://localhost:9090" -ForegroundColor DarkYellow
Write-Host "  Pyroscope:            http://localhost:4040" -ForegroundColor DarkYellow
Write-Host "  Alloy:                http://localhost:12345" -ForegroundColor DarkYellow
Write-Host ""
Write-Host "Seed data:" -ForegroundColor Cyan
Write-Host "  1) Demo content (idempotent - student user + news + events + schedule + stories):"
Write-Host "       docker exec -w /app university_ecosystem-backend-1 python scripts/seed_demo_data.py"
Write-Host "       Login: test@university.dev / TestPass@2024x"
Write-Host "  2) Admin content (idempotent - admin user + 6 users + 12 audit logs + 4 dead-letter jobs):"
Write-Host "       docker cp scripts/seed_admin_data.py university_ecosystem-backend-1:/app/seed_admin_data.py"
Write-Host "       docker exec -w /app university_ecosystem-backend-1 python seed_admin_data.py"
Write-Host "       Login: admin@university.dev / Admin@2024test"
Write-Host ""
Write-Host "Commands:" -ForegroundColor Gray
Write-Host "  Stop:      .\start-docker.ps1 -Down"
Write-Host "  Logs:      .\start-docker.ps1 -Logs"
Write-Host "  Logs svc:  .\start-docker.ps1 -Logs -LogService backend"
Write-Host "  Build:     .\start-docker.ps1 -Build"
Write-Host "  Rebuild:   .\start-docker.ps1 -Rebuild   (no cache)"
