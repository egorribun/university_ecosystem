# PRIVATE REVIEW CANDIDATE. Not integrated into the launcher.
# A lease owns the profile's open handle from preparation through scrubbing.

function Assert-TemporalBootstrapDirectory {
    param([Parameter(Mandatory=$true)][string]$DirectoryPath)
    $item = Get-Item -LiteralPath $DirectoryPath -Force -ErrorAction Stop
    if (-not $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'Temporal bootstrap directory must be an owned directory without a reparse point.'
    }
    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
        $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $acl = Get-Acl -LiteralPath $DirectoryPath -ErrorAction Stop
        if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -cne $sid) { throw 'Unexpected Temporal bootstrap directory owner.' }
        $seen = @{}
        foreach ($rule in $acl.Access) {
            if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { continue }
            $entrySid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
            if ($entrySid -cnotin @($sid, 'S-1-5-18') -or
                (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -ne [System.Security.AccessControl.FileSystemRights]::FullControl)) {
                throw 'Unexpected Temporal bootstrap directory access.'
            }
            $seen[$entrySid] = $true
        }
        if (-not $seen.ContainsKey($sid) -or -not $seen.ContainsKey('S-1-5-18')) { throw 'Incomplete Temporal bootstrap directory ACL.' }
    } else {
        $mode = [System.IO.File]::GetUnixFileMode($DirectoryPath)
        $unprivate = [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::GroupWrite -bor
            [System.IO.UnixFileMode]::GroupExecute -bor [System.IO.UnixFileMode]::OtherRead -bor
            [System.IO.UnixFileMode]::OtherWrite -bor [System.IO.UnixFileMode]::OtherExecute
        if (($mode -band $unprivate) -ne [System.IO.UnixFileMode]::None) { throw 'Temporal bootstrap directory must be private.' }
    }
}

function Get-TemporalBootstrapHandleIdentity {
    param([Parameter(Mandatory=$true)][System.IO.FileStream]$Stream)
    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
        if (-not ('TemporalBootstrapFileIdentity' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class TemporalBootstrapFileIdentity {
    [StructLayout(LayoutKind.Sequential)]
    private struct Info {
        public uint attributes, creationLow, creationHigh, accessLow, accessHigh, writeLow, writeHigh;
        public uint volume, sizeHigh, sizeLow, links, indexHigh, indexLow;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint mode, uint flags, IntPtr template);
    public static string Describe(SafeFileHandle handle) {
        Info i;
        if (!GetFileInformationByHandle(handle, out i)) throw new Win32Exception();
        if ((i.attributes & (0x10u | 0x400u)) != 0) throw new InvalidOperationException("Not a regular file");
        return i.volume + ":" + i.indexHigh + ":" + i.indexLow + ":" + i.links;
    }
    public static string PathId(string path) {
        using (SafeFileHandle handle = CreateFile(path, 0, 7, IntPtr.Zero, 3, 0x02000000u, IntPtr.Zero)) {
            if (handle.IsInvalid) throw new Win32Exception();
            Info i;
            if (!GetFileInformationByHandle(handle, out i)) throw new Win32Exception();
            return i.volume + ":" + i.indexHigh + ":" + i.indexLow;
        }
    }
}
'@
        }
        $fields = [TemporalBootstrapFileIdentity]::Describe($Stream.SafeFileHandle).Split(':')
        return [PSCustomObject]@{ Id = ($fields[0..2] -join ':'); Links = [uint32]$fields[3] }
    }
    if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Linux)) {
        throw 'Temporal bootstrap file identity is supported only on Windows and Linux.'
    }
    $stat = Get-Command 'stat' -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $fd = $Stream.SafeFileHandle.DangerousGetHandle().ToInt64()
    $description = @(& $stat.Source '-L' '-c' '%f:%d:%i:%h' '--' "/proc/$PID/fd/$fd" 2>$null)
    if ($LASTEXITCODE -ne 0 -or $description.Count -ne 1 -or $description[0] -notmatch '^([0-9a-fA-F]+):([0-9]+):([0-9]+):([0-9]+)$') {
        throw 'Cannot inspect Temporal bootstrap open file identity.'
    }
    if (([Convert]::ToInt32($Matches[1], 16) -band 0xF000) -ne 0x8000) { throw 'Temporal bootstrap profile is not a regular file.' }
    return [PSCustomObject]@{ Id = "$($Matches[2]):$($Matches[3])"; Links = [uint32]$Matches[4] }
}

function Assert-TemporalBootstrapIdentity {
    param([Parameter(Mandatory=$true)]$Lease, [switch]$RequirePath, [switch]$RequireSingleLink)
    $openIdentity = Get-TemporalBootstrapHandleIdentity -Stream $Lease.ProfileStream
    if ($openIdentity.Id -cne $Lease.Identity -or ($RequireSingleLink -and $openIdentity.Links -ne 1)) {
        throw 'Temporal bootstrap profile identity or link count changed.'
    }
    if ($RequirePath) {
        Assert-EnvironmentFileLeafPath -Path $Lease.ProfilePath
        $probe = [System.IO.FileStream]::new($Lease.ProfilePath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try { $pathIdentity = Get-TemporalBootstrapHandleIdentity -Stream $probe } finally { $probe.Dispose() }
        if ($pathIdentity.Id -cne $Lease.Identity -or ($RequireSingleLink -and $pathIdentity.Links -ne 1)) {
            throw 'Temporal bootstrap profile path no longer identifies its leased file.'
        }
    }
}

function Write-TemporalBootstrapLease {
    param([Parameter(Mandatory=$true)]$Lease, [Parameter(Mandatory=$true)][AllowEmptyString()][string]$Content, [switch]$Scrub)
    # A scrub always clears the trusted open handle, even if the path was swapped.
    # Minting requires both the signed bind path and the handle to match.
    Assert-TemporalBootstrapIdentity -Lease $Lease -RequirePath:(!$Scrub) -RequireSingleLink:(!$Scrub)
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Content)
    $Lease.ProfileStream.Position = 0
    $Lease.ProfileStream.SetLength(0)
    $Lease.ProfileStream.Write($bytes, 0, $bytes.Length)
    $Lease.ProfileStream.Flush($true)
    Assert-TemporalBootstrapIdentity -Lease $Lease -RequirePath:(!$Scrub) -RequireSingleLink:(!$Scrub)
}

function Enter-TemporalBootstrapLease {
    param([Parameter(Mandatory=$true)][string]$StateRoot)
    $directory = Join-Path $StateRoot '.temporal-bootstrap'
    $profile = Join-Path $directory 'profile.toml'
    $marker = Join-Path $directory 'owner.marker'
    $lockPath = Join-Path $directory 'profile.lock'
    $windows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
    if (-not (Test-Path -LiteralPath $directory)) {
        if ($windows) {
            [System.IO.Directory]::CreateDirectory($directory) | Out-Null
            $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $icacls = Get-Command 'icacls.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1
            $null = & $icacls.Source $directory '/reset' 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Cannot reset Temporal bootstrap directory ACL.' }
            $null = & $icacls.Source $directory '/setowner' "*$sid" 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Cannot set Temporal bootstrap directory owner.' }
            $null = & $icacls.Source $directory '/inheritance:r' '/grant:r' "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Cannot protect Temporal bootstrap directory.' }
        } else {
            $mode = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor [System.IO.UnixFileMode]::UserExecute
            [System.IO.Directory]::CreateDirectory($directory, $mode) | Out-Null
        }
    }
    Assert-TemporalBootstrapDirectory -DirectoryPath $directory
    try {
        $lock = [System.IO.FileStream]::new($lockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None, 4096, [System.IO.FileOptions]::DeleteOnClose)
    } catch { throw 'Temporal bootstrap lease already exists or cannot be created. After confirming no launcher is running and 5 minutes have elapsed, remove only profile.lock from the private stand state, then retry.' }
    $stream = $null
    try {
        Assert-EnvironmentFileLeafPath -Path $profile
        Assert-EnvironmentFileLeafPath -Path $marker
        $profileExists = Test-Path -LiteralPath $profile
        $markerExists = Test-Path -LiteralPath $marker
        if ($profileExists -ne $markerExists) { throw 'Ambiguous Temporal bootstrap profile; refusing to open or truncate it.' }
        $mode = if ($profileExists) { [System.IO.FileMode]::Open } else { [System.IO.FileMode]::CreateNew }
        $stream = [System.IO.FileStream]::new($profile, $mode, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::ReadWrite)
        $id = Get-TemporalBootstrapHandleIdentity -Stream $stream
        if ($id.Links -ne 1) { throw 'Temporal bootstrap profile has more than one link.' }
        if ($markerExists) {
            if (([System.IO.FileInfo]::new($marker)).Length -gt 256 -or [System.IO.File]::ReadAllText($marker) -cne $id.Id) {
                throw 'Temporal bootstrap profile does not match the previously created file.'
            }
        } else {
            $markerStream = [System.IO.FileStream]::new($marker, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
            try {
                $markerBytes = [System.Text.Encoding]::ASCII.GetBytes($id.Id)
                $markerStream.Write($markerBytes, 0, $markerBytes.Length)
                $markerStream.Flush($true)
            } finally { $markerStream.Dispose() }
        }
        $lease = [PSCustomObject]@{ ProfilePath = $profile; ProfileStream = $stream; Identity = $id.Id; LockStream = $lock }
        Assert-TemporalBootstrapIdentity -Lease $lease -RequirePath -RequireSingleLink
        if ($windows) {
            # No delete sharing while the handle is open; the verified file cannot be renamed.
            $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $icacls = Get-Command 'icacls.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1
            $null = & $icacls.Source $profile '/setowner' "*$sid" 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Cannot set Temporal bootstrap profile owner.' }
            $acl = Get-Acl -LiteralPath $profile -ErrorAction Stop
            if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -cne $sid) { throw 'Unexpected Temporal bootstrap profile owner.' }
            foreach ($rule in $acl.Access) {
                if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { continue }
                if ($rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -cnotin @($sid, 'S-1-5-18')) { throw 'Unexpected Temporal bootstrap profile ACL.' }
            }
        } else {
            # /proc handle path, rather than the mutable bind pathname.
            $fd = $stream.SafeFileHandle.DangerousGetHandle().ToInt64()
            $handlePath = "/proc/$PID/fd/$fd"
            $readable = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::OtherRead
            [System.IO.File]::SetUnixFileMode($handlePath, $readable)
            if ([System.IO.File]::GetUnixFileMode($handlePath) -ne $readable) { throw 'Temporal bootstrap profile is not readable by the initializer.' }
        }
        Write-TemporalBootstrapLease -Lease $lease -Content '' -Scrub
        return $lease
    } catch {
        if ($null -ne $stream) { $stream.Dispose() }
        $lock.Dispose()
        throw
    }
}

function Exit-TemporalBootstrapLease {
    param([Parameter(Mandatory=$true)]$Lease)
    try { Write-TemporalBootstrapLease -Lease $Lease -Content '' -Scrub }
    finally { $Lease.ProfileStream.Dispose(); $Lease.LockStream.Dispose() }
}

function New-TemporalBootstrapProfile {
    param([Parameter(Mandatory=$true)][string]$PrivateKeyPath, [Parameter(Mandatory=$true)]$Lease)
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $header = [PSCustomObject]@{ alg = 'RS256'; kid = 'primary'; typ = 'JWT' }
    $payload = [PSCustomObject]@{ sub = 'temporal-namespace-bootstrap'; aud = 'temporal'; iat = $now; exp = $now + 300; jti = [Guid]::NewGuid().ToString('N'); permissions = @('default:admin') }
    $headerBytes = [System.Text.Encoding]::UTF8.GetBytes(($header | ConvertTo-Json -Compress))
    $payloadBytes = [System.Text.Encoding]::UTF8.GetBytes(($payload | ConvertTo-Json -Compress))
    $signingInput = "$(ConvertTo-Base64Url $headerBytes).$(ConvertTo-Base64Url $payloadBytes)"
    $rsa = [System.Security.Cryptography.RSA]::Create()
    try {
        $rsa.ImportFromPem([System.IO.File]::ReadAllText($PrivateKeyPath))
        $signature = $rsa.SignData([System.Text.Encoding]::UTF8.GetBytes($signingInput), [System.Security.Cryptography.HashAlgorithmName]::SHA256, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    } finally { $rsa.Dispose() }
    $token = "$signingInput.$(ConvertTo-Base64Url $signature)"
    $profile = "[profile.default]`naddress = '127.0.0.1:7233'`nnamespace = 'default'`napi_key = '$token'`n[profile.default.tls]`ndisabled = true`n"
    Write-TemporalBootstrapLease -Lease $Lease -Content $profile
}

function Assert-TemporalBootstrapNoReparseComponents {
    param([Parameter(Mandatory=$true)][string]$Path)
    $current = [System.IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrEmpty($current)) {
        $file = [System.IO.FileInfo]::new($current)
        $directory = [System.IO.DirectoryInfo]::new($current)
        if ($null -ne $file.LinkTarget -or $null -ne $directory.LinkTarget) {
            throw 'Temporal bootstrap Compose bind source contains a link.'
        }
        try {
            $attributes = [System.IO.File]::GetAttributes($current)
            if ($attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Temporal bootstrap Compose bind source contains a reparse point.' }
        } catch [System.IO.FileNotFoundException] { }
          catch [System.IO.DirectoryNotFoundException] { }
        $parent = [System.IO.Path]::GetDirectoryName($current)
        if ($parent -ceq $current) { break }
        $current = $parent
    }
}

function Get-TemporalBootstrapComposeVersion {
    if ($script:TemporalBootstrapComposeVersionCaptured -eq $true) {
        return [string]$script:TemporalBootstrapComposeVersionText
    }
    $script:TemporalBootstrapComposeVersionCaptured = $true
    $script:TemporalBootstrapComposeVersionText = ''
    try {
        $versionOutput = @(docker compose version --short 2>$null)
        $versionExitCode = $LASTEXITCODE
        if ($versionExitCode -ne 0 -or $versionOutput.Count -ne 1) { return '' }
        $versionText = ([string]$versionOutput[0]).Trim()
        if ($versionText -cnotmatch '^v?\d+\.\d+\.\d+$') { return '' }
        $script:TemporalBootstrapComposeVersionText = $versionText
        return $versionText
    } catch {
        return ''
    }
}

function Test-TemporalBootstrapNoHostPathCreation {
    param([Parameter(Mandatory=$true)]$Mount)
    $bindProperty = $Mount.PSObject.Properties['bind']
    if ($null -eq $bindProperty -or $bindProperty.Value -isnot [pscustomobject]) {
        return $false
    }
    # Normalized bind:{} has version-dependent meaning: Compose v2.38.2 uses
    # compose-go v2.7.1, where false is omitted; newer compose-go releases use
    # OptOut (true by default), where short syntax's true is also omitted.
    # Only the exact source-verified legacy version may omit this field.
    $createProperty = $bindProperty.Value.PSObject.Properties['create_host_path']
    if ($null -eq $createProperty) {
        $composeVersion = Get-TemporalBootstrapComposeVersion
        return ($composeVersion -ceq 'v2.38.2' -or $composeVersion -ceq '2.38.2')
    }
    return ($createProperty.Value -is [bool] -and $createProperty.Value -eq $false)
}

function Assert-InPlaceTemporalBootstrapModel {
    param([Parameter(Mandatory=$true)]$ComposeModel, [Parameter(Mandatory=$true)][string]$StateRoot, [Parameter(Mandatory=$true)][string]$ProjectRoot)
    $services = $ComposeModel.PSObject.Properties['services'].Value
    if ($null -eq $services) { throw 'Temporal bootstrap Compose services are missing.' }
    $volumeInventory = $ComposeModel.PSObject.Properties['volumes'].Value
    if ($null -eq $volumeInventory) { throw 'Temporal bootstrap Compose volume inventory is missing.' }
    foreach ($definition in $volumeInventory.PSObject.Properties) {
        $volume = $definition.Value
        if ($null -eq $volume -or $volume.external -eq $true -or
            ([string]$volume.driver -cnotin @('', 'local')) -or
            ($null -ne $volume.driver_opts -and @($volume.driver_opts.PSObject.Properties).Count -ne 0)) {
            throw 'Temporal bootstrap Compose volumes must use the unconfigured local driver.'
        }
    }
    $init = $services.PSObject.Properties['temporal-namespace-init'].Value
    $expectedImage = 'temporalio/admin-tools:1.30.7@sha256:bbdf5fe91b288c17442efbbfb42daa3668d09cfa8ebeb078d6fd475a97f66b81'
    if ($null -eq $init -or [string]$init.image -cne $expectedImage -or
        [string]$init.network_mode -cne 'service:temporal' -or
        $null -ne $init.networks -or [string]$init.user -cne '1000:1000' -or
        $init.read_only -ne $true -or $init.privileged -eq $true -or
        ($init.cap_drop -join "`n") -cne 'ALL' -or
        @($init.cap_add | Where-Object { $null -ne $_ }).Count -ne 0 -or
        ($init.security_opt -join "`n") -cne 'no-new-privileges:true' -or
        ($init.entrypoint -join "`n") -cne "/bin/sh`n/etc/temporal/namespace-init.sh" -or
        @($init.command | Where-Object { $null -ne $_ }).Count -ne 0 -or
        ($null -ne $init.environment -and @($init.environment.PSObject.Properties).Count -ne 0)) {
        throw 'Temporal bootstrap Compose isolation is invalid.'
    }
    # These fields can run another program or add an alternate host mount while
    # the short-lived profile is readable; the pinned initializer needs none.
    foreach ($field in @('build', 'healthcheck', 'post_start', 'pre_stop', 'devices', 'device_cgroup_rules', 'pid', 'ipc', 'userns_mode')) {
        $property = $init.PSObject.Properties[$field]
        if ($null -ne $property -and $null -ne $property.Value) {
            throw 'Temporal bootstrap initializer has an unsupported execution or namespace option.'
        }
    }
    $expectedTmpfs = @(
        '/tmp:uid=1000,gid=1000,mode=0700,noexec,nosuid,nodev',
        '/run/temporal-bootstrap-runtime:uid=1000,gid=1000,mode=0700,noexec,nosuid,nodev'
    ) | Sort-Object -CaseSensitive
    if ((@($init.tmpfs | Sort-Object -CaseSensitive) -join "`n") -cne ($expectedTmpfs -join "`n")) {
        throw 'Temporal bootstrap temporary mounts are invalid.'
    }
    $server = $services.PSObject.Properties['temporal'].Value
    $expectedServerImage = 'temporalio/server:1.30.7@sha256:dc8dc6fffa29de3bad7f5c39cb406db3104053fbb0c2494e7c76016211bc99b0'
    $expectedHealth = "CMD-SHELL`nwget -q --spider --timeout=3 http://127.0.0.1:8000/metrics || exit 1"
    $serverKeys = @($server.environment.PSObject.Properties.Name | Sort-Object -CaseSensitive)
    if ($null -eq $server -or [string]$server.image -cne $expectedServerImage -or
        ($server.entrypoint -join "`n") -cne "/bin/sh`n/etc/temporal/wave144-entrypoint.sh" -or
        @($server.command | Where-Object { $null -ne $_ }).Count -ne 0 -or
        ($server.healthcheck.test -join "`n") -cne $expectedHealth -or
        ($serverKeys -join "`n") -cne "BIND_ON_IP`nPOSTGRES_PWD`nPOSTGRES_USER`nTEMPORAL_JWKS_URL`nTEMPORAL_SERVICES" -or
        [string]$server.environment.BIND_ON_IP -cne '0.0.0.0' -or
        [string]$server.environment.TEMPORAL_SERVICES -cne 'frontend,history,matching,worker,internal-frontend' -or
        [string]$server.environment.TEMPORAL_JWKS_URL -cne 'https://caddy:8443/.well-known/jwks.json') {
        throw 'Temporal bootstrap server identity or configuration is invalid.'
    }
    foreach ($field in @('build', 'post_start', 'pre_stop', 'devices', 'device_cgroup_rules', 'pid', 'ipc', 'userns_mode', 'user')) {
        $property = $server.PSObject.Properties[$field]
        if ($null -ne $property -and $null -ne $property.Value) {
            throw 'Temporal bootstrap server has an unsupported execution or namespace option.'
        }
    }
    $admin = [System.IO.Path]::GetFullPath((Join-Path $StateRoot '.temporal-bootstrap/profile.toml'))
    $workerToken = [System.IO.Path]::GetFullPath((Join-Path $StateRoot '.secrets/temporal_api_key'))
    Assert-TemporalBootstrapNoReparseComponents -Path $workerToken
    try { $workerTokenItem = Get-Item -LiteralPath $workerToken -Force -ErrorAction Stop }
    catch { throw 'Temporal worker token bind source is missing.' }
    if ($workerTokenItem.PSIsContainer -or ($workerTokenItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'Temporal worker token bind source is not a regular file.'
    }
    $workerTokenProbe = [System.IO.FileStream]::new($workerToken, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try { $workerTokenFileIdentity = Get-TemporalBootstrapHandleIdentity -Stream $workerTokenProbe }
    finally { $workerTokenProbe.Dispose() }
    if ($workerTokenFileIdentity.Links -ne 1) { throw 'Temporal worker token has an unverified hard-link alias.' }
    $workerTokenIdentities = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    [void]$workerTokenIdentities.Add($workerTokenFileIdentity.Id)
    $tokenAncestor = [System.IO.Path]::GetDirectoryName($workerToken)
    while (-not [string]::IsNullOrEmpty($tokenAncestor)) {
        if (Test-Path -LiteralPath $tokenAncestor -PathType Container) {
            [void]$workerTokenIdentities.Add((Get-TemporalBootstrapPathIdentity -Path $tokenAncestor))
        }
        $parent = [System.IO.Path]::GetDirectoryName($tokenAncestor)
        if ($parent -ceq $tokenAncestor) { break }
        $tokenAncestor = $parent
    }
    $expected = @{
        '/etc/temporal/namespace-init.sh' = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'scripts/temporal/namespace-init.sh'))
        '/run/temporal-bootstrap/profile.toml' = $admin
        '/run/temporal-worker/token' = [System.IO.Path]::GetFullPath((Join-Path $StateRoot '.secrets/temporal_api_key'))
    }
    $comparison = if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    $seen = @{}
    if (@($init.volumes).Count -ne $expected.Count) {
        throw 'Temporal bootstrap Compose mount rejected (mount_count).'
    }
    foreach ($mount in $init.volumes) {
        $target = [string]$mount.target
        if (-not $expected.ContainsKey($target) -or $seen.ContainsKey($target)) {
            throw 'Temporal bootstrap Compose mount rejected (target_or_duplicate).'
        }
        if ([string]$mount.type -cne 'bind') {
            throw 'Temporal bootstrap Compose mount rejected (mount_type).'
        }
        if ($mount.read_only -ne $true) {
            throw 'Temporal bootstrap Compose mount rejected (read_only).'
        }
        if (-not (Test-TemporalBootstrapNoHostPathCreation -Mount $mount)) {
            throw 'Temporal bootstrap Compose mount rejected (create_host_path).'
        }
        $source = [string]$mount.source
        if (-not [System.IO.Path]::IsPathFullyQualified($source)) {
            throw 'Temporal bootstrap Compose mount rejected (source_not_absolute).'
        }
        $canonicalSource = [System.IO.Path]::GetFullPath($source)
        if (-not [string]::Equals($canonicalSource, $expected[$target], $comparison)) {
            throw 'Temporal bootstrap Compose mount rejected (source_not_exact).'
        }
        $seen[$target] = $true
    }
    $serverSources = @{
        '/etc/temporal/config/docker.yaml' = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'services/temporal/config.yaml'))
        '/etc/temporal/wave144-entrypoint.sh' = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'services/temporal/entrypoint.sh'))
    }
    $serverSeen = @{}
    if (@($server.volumes).Count -ne 3 -or
        [string]$volumeInventory.PSObject.Properties['temporal-jwks-ca'].Value.name -cne "$($ComposeModel.name)_temporal-jwks-ca") {
        throw 'Temporal bootstrap server trust mounts are invalid.'
    }
    foreach ($mount in $server.volumes) {
        $target = [string]$mount.target
        if ($serverSeen.ContainsKey($target) -or $mount.read_only -ne $true) { throw 'Temporal bootstrap server mount is invalid.' }
        if ($target -ceq '/etc/temporal/jwks-ca') {
            if ([string]$mount.type -cne 'volume' -or [string]$mount.source -cne 'temporal-jwks-ca') { throw 'Temporal bootstrap CA volume is invalid.' }
        } elseif (-not $serverSources.ContainsKey($target) -or [string]$mount.type -cne 'bind' -or
            -not [System.IO.Path]::IsPathFullyQualified([string]$mount.source) -or
            -not [string]::Equals([System.IO.Path]::GetFullPath([string]$mount.source), $serverSources[$target], $comparison)) {
            throw 'Temporal bootstrap server configuration bind is invalid.'
        }
        $serverSeen[$target] = $true
    }
    foreach ($service in $services.PSObject.Properties) {
        $mode = [string]$service.Value.network_mode
        if ($service.Name -cne 'temporal-namespace-init' -and
            ($mode -ceq 'service:temporal' -or $mode.StartsWith('container:', [StringComparison]::Ordinal))) {
            throw 'Another service may not share the Temporal network namespace.'
        }
        $pidMode = [string]$service.Value.pid
        if ($service.Name -cne 'temporal-namespace-init' -and
            ($pidMode -ceq 'host' -or $pidMode -ceq 'service:temporal' -or $pidMode.StartsWith('container:', [StringComparison]::Ordinal))) {
            throw 'Another service may not observe the Temporal process namespace.'
        }
        foreach ($field in @('configs', 'secrets', 'volumes_from')) {
            $property = $service.Value.PSObject.Properties[$field]
            if ($null -ne $property -and $null -ne $property.Value -and
                @($property.Value | Where-Object { $null -ne $_ }).Count -ne 0) {
                throw 'Temporal bootstrap refuses alternate Compose mount mechanisms.'
            }
        }
        foreach ($mount in @($service.Value.volumes)) {
            if ($null -eq $mount -or [string]$mount.type -cne 'bind') { continue }
            # The daemon socket is a fixed platform path on Docker Desktop and
            # /var/run may itself be a system symlink on Linux. It is not a
            # host-state bind and is allowed only for the established proxy.
            if ($service.Name -ceq 'docker-log-proxy' -and [string]$mount.source -ceq '/var/run/docker.sock' -and
                [string]$mount.target -ceq '/var/run/docker.sock' -and $mount.read_only -eq $true) { continue }
            if (-not [System.IO.Path]::IsPathFullyQualified([string]$mount.source)) { throw 'Temporal bootstrap Compose bind source is invalid.' }
            $source = [System.IO.Path]::GetFullPath([string]$mount.source)
            Assert-TemporalBootstrapNoReparseComponents -Path $source
            $prefix = $source.TrimEnd([char[]]@('/', '\')) + [System.IO.Path]::DirectorySeparatorChar
            if ([string]::Equals($admin, $source, $comparison) -or $admin.StartsWith($prefix, $comparison)) {
                if ($service.Name -cne 'temporal-namespace-init' -or
                    -not [string]::Equals($admin, $source, $comparison) -or
                    [string]$mount.target -cne '/run/temporal-bootstrap/profile.toml' -or $mount.read_only -ne $true) {
                    throw 'Temporal bootstrap profile is exposed through another bind.'
                }
            }
            $tokenAlias = $false
            if ((Test-Path -LiteralPath $source -PathType Leaf) -or (Test-Path -LiteralPath $source -PathType Container)) {
                $tokenAlias = $workerTokenIdentities.Contains((Get-TemporalBootstrapPathIdentity -Path $source))
            }
            $tokenAncestor = [string]::Equals($workerToken, $source, $comparison) -or $workerToken.StartsWith($prefix, $comparison)
            if ($tokenAncestor -or $tokenAlias) {
                $target = [string]$mount.target
                $exactTokenSource = [string]::Equals($workerToken, $source, $comparison)
                $allowedInitializer = $service.Name -ceq 'temporal-namespace-init' -and
                    $exactTokenSource -and $target -ceq '/run/temporal-worker/token' -and $mount.read_only -eq $true -and
                    (Test-TemporalBootstrapNoHostPathCreation -Mount $mount)
                $allowedFileProcessor = $service.Name -ceq 'file-processor' -and
                    $exactTokenSource -and $target -ceq '/app/.secrets/temporal_api_key' -and $mount.read_only -eq $true -and
                    (Test-TemporalBootstrapNoHostPathCreation -Mount $mount)
                if (-not ($allowedInitializer -or $allowedFileProcessor)) {
                    throw 'Temporal worker token is exposed through an unapproved bind.'
                }
            }
        }
    }
}

function Assert-TemporalBootstrapUnconfiguredVolume {
    param([Parameter(Mandatory=$true)][string]$Name)
    if ($Name -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$') { throw 'A running container volume cannot be verified.' }
    # Ask Docker only for the fields needed to identify host-backed aliases;
    # do not request volume labels or unrelated metadata.
    $format = '{{.Name}}|{{.Driver}}|{{.Scope}}|{{json .Options}}'
    $output = @(docker volume inspect --format $format $Name 2>$null)
    if ($LASTEXITCODE -ne 0 -or $output.Count -ne 1) { throw 'Cannot inspect an existing Temporal bootstrap volume.' }
    $fields = ([string]$output[0]).Split([char[]]@('|'), 4)
    if ($fields.Count -ne 4 -or $fields[0] -cne $Name -or $fields[1] -cne 'local' -or $fields[2] -cne 'local') {
        throw 'An existing volume is not an unconfigured local volume.'
    }
    if ($fields[3] -cnotin @('null', '{}')) { throw 'An existing volume has unverified backing options.' }
}

function Assert-InPlaceTemporalBootstrapVolumeSafety {
    param([Parameter(Mandatory=$true)]$ComposeModel)
    # The existing ownership guard checks labels. Inspect existing actual
    # volumes as well: a stale local-driver bind must not expose this profile.
    $existing = @(docker volume ls --quiet 2>$null)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Temporal bootstrap volume inventory.' }
    foreach ($definition in $ComposeModel.volumes.PSObject.Properties) {
        $name = [string]$definition.Value.name
        if ([string]::IsNullOrWhiteSpace($name)) { throw 'Temporal bootstrap volume has no resolved name.' }
        if ($existing -cnotcontains $name) { continue }
        Assert-TemporalBootstrapUnconfiguredVolume -Name $name
    }
}

function Add-TemporalBootstrapDockerErrorClass {
    param(
        [Parameter(Mandatory=$true)][hashtable]$State,
        [Parameter(Mandatory=$true)][System.Management.Automation.ErrorRecord]$Record
    )
    # Classify a bounded prefix in memory; retain only finite classifications.
    # The shared hashtable survives ForEach-Object's pipeline scope without
    # collecting ErrorRecords or their potentially sensitive messages.
    $State.Seen = $true
    $exceptionType = $Record.Exception.GetType().FullName
    if ($exceptionType -ceq 'System.Management.Automation.NativeCommandExitException') {
        # PowerShell can emit this after the real stderr records. It is an exit
        # status notification, not an additional explanation from the daemon.
        return
    }
    if ($State.Records -ge 8) { $State.Capped = $true; return }
    $State.Records++
    $kind = 'unknown'
    if ($exceptionType -ceq 'System.Management.Automation.CommandNotFoundException') {
        $kind = 'command-unavailable'
    } else {
        $message = [string]$Record.Exception.Message
        $remaining = 8192 - $State.Characters
        if ($remaining -le 0) { $State.Capped = $true; return }
        $length = [Math]::Min(2048, $remaining)
        if ($message.Length -gt $length) {
            $State.Capped = $true
            $message = $message.Substring(0, $length)
        }
        $State.Characters += $message.Length
        $classes = [System.Collections.Generic.List[string]]::new()
        if ($message -match '(?i)template parsing error|error parsing template|can.t evaluate field|template:.*executing') { $classes.Add('format-template') }
        if ($message -match '(?i)no such (image|container|object)|no such object:') { $classes.Add('missing-object') }
        if ($message -match '(?i)cannot connect to the docker daemon|is the docker daemon running|error during connect|connection refused') { $classes.Add('daemon-unreachable') }
        if ($message -match '(?i)permission denied|access is denied|access denied|unauthorized|authentication required') { $classes.Add('access-denied') }
        if ($message -match '(?i)context .*does not exist|context .*not found|unable to resolve docker endpoint') { $classes.Add('context-unavailable') }
        if ($message -match '(?i)client version .*too (old|new)|client is newer than server|minimum supported api version|unsupported api version') { $classes.Add('client-api') }
        if ($message -match '(?i)x509:|tls handshake|certificate signed by unknown authority|certificate has expired') { $classes.Add('tls') }
        if ($classes.Count -eq 1) { $kind = $classes[0] }
        elseif ($classes.Count -gt 1) { $kind = 'multiple' }
    }
    if ($State.Kind -ceq 'none') { $State.Kind = $kind }
    elseif ($State.Kind -cne $kind) { $State.Kind = 'multiple' }
}

function Write-TemporalBootstrapDockerInspectDiagnostic {
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet(
            'temporal-server-image', 'temporal-init-image',
            'temporal-server-container', 'temporal-init-container',
            'network-namespace-target', 'network-namespace-mode',
            'pid-namespace-target', 'pid-namespace-mode',
            'peer-network-mode', 'peer-pid-mode', 'peer-mount-metadata'
        )][string]$Phase,
        [Parameter(Mandatory=$true)][ValidateSet('command-failed', 'invalid-output-shape', 'invalid-json')][string]$Result,
        [Parameter(Mandatory=$true)][hashtable]$State,
        [Parameter(Mandatory=$true)][bool]$CommandThrew,
        [AllowNull()]$ExitCode
    )
    try {
        $kind = [string]$State.Kind
        if ($kind -cnotin @('none', 'unknown', 'command-unavailable', 'format-template', 'missing-object', 'daemon-unreachable', 'access-denied', 'context-unavailable', 'client-api', 'tls', 'multiple')) { $kind = 'unknown' }
        if ($State.Capped) { $kind = 'bounded' }
        $exitClass = if ($null -eq $ExitCode) { 'unavailable' } elseif ($ExitCode -eq 0) { 'zero' } else { 'nonzero' }
        $platform = 'other'
        if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) { $platform = 'windows' }
        elseif ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Linux)) { $platform = 'linux' }
        elseif ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::OSX)) { $platform = 'macos' }
        $edition = if ($PSVersionTable.PSEdition -ceq 'Core') { 'core' } elseif ($PSVersionTable.PSEdition -ceq 'Desktop') { 'desktop' } else { 'other' }
        $nativePreference = Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
        $nativeErrors = if ($null -eq $nativePreference) { 'unavailable' } elseif ($nativePreference.Value -eq $true) { 'enabled' } else { 'disabled' }
        $errorAction = if ($ErrorActionPreference -eq 'Stop') { 'stop' } elseif ($ErrorActionPreference -eq 'Continue') { 'continue' } else { 'other' }
        $command = Get-Command -Name docker -ErrorAction SilentlyContinue
        $commandKind = if ($null -eq $command) { 'unresolved' } elseif ($command.CommandType -eq 'Application') { 'application' } elseif ($command.CommandType -eq 'Function') { 'function' } elseif ($command.CommandType -eq 'Alias') { 'alias' } else { 'other' }
        $hostSet = -not [string]::IsNullOrEmpty($env:DOCKER_HOST)
        $contextSet = -not [string]::IsNullOrEmpty($env:DOCKER_CONTEXT)
        $configSet = -not [string]::IsNullOrEmpty($env:DOCKER_CONFIG)
        $tlsVerifySet = -not [string]::IsNullOrEmpty($env:DOCKER_TLS_VERIFY)
        $apiVersionSet = -not [string]::IsNullOrEmpty($env:DOCKER_API_VERSION)
        [Console]::Error.WriteLine("TEMPORAL_BOOTSTRAP_RUNTIME_INSPECT phase=$Phase result=$Result error_class=$kind error_present=$([bool]$State.Seen) error_capped=$([bool]$State.Capped) command_threw=$CommandThrew exit=$exitClass platform=$platform edition=$edition native_errors=$nativeErrors error_action=$errorAction docker_command=$commandKind docker_host_set=$hostSet docker_context_set=$contextSet docker_config_set=$configSet docker_tls_verify_set=$tlsVerifySet docker_api_version_set=$apiVersionSet")
    } catch { }
}

function Get-TemporalBootstrapDockerObject {
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet(
            'temporal-server-image', 'temporal-init-image',
            'temporal-server-container', 'temporal-init-container',
            'network-namespace-target', 'network-namespace-mode',
            'pid-namespace-target', 'pid-namespace-mode',
            'peer-network-mode', 'peer-pid-mode', 'peer-mount-metadata'
        )]
        [string]$Phase,
        [Parameter(Mandatory=$true)][string[]]$Arguments
    )
    $errorClass = @{ Seen = $false; Capped = $false; Records = 0; Characters = 0; Kind = 'none' }
    $commandThrew = $false
    $commandExitCode = $null
    try {
        $output = @(docker @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                try { Add-TemporalBootstrapDockerErrorClass -State $errorClass -Record $_ }
                catch { $errorClass.Seen = $true; $errorClass.Kind = 'unknown' }
            } else { $_ }
        })
        $commandExitCode = $LASTEXITCODE
    } catch {
        $commandThrew = $true
        # Only a native exit exception guarantees LASTEXITCODE was refreshed.
        # Launch/PowerShell failures must not report an inherited stale value.
        if ($_.Exception.GetType().FullName -ceq 'System.Management.Automation.NativeCommandExitException') {
            $commandExitCode = $LASTEXITCODE
        }
        try { Add-TemporalBootstrapDockerErrorClass -State $errorClass -Record $_ }
        catch { $errorClass.Seen = $true; $errorClass.Kind = 'unknown' }
    }
    if ($commandThrew -or $commandExitCode -ne 0) {
        Write-TemporalBootstrapDockerInspectDiagnostic -Phase $Phase -Result 'command-failed' -State $errorClass -CommandThrew $commandThrew -ExitCode $commandExitCode
        throw 'Cannot inspect Temporal bootstrap runtime identity.'
    }
    if ($output.Count -ne 1) {
        Write-TemporalBootstrapDockerInspectDiagnostic -Phase $Phase -Result 'invalid-output-shape' -State $errorClass -CommandThrew $commandThrew -ExitCode $commandExitCode
        throw 'Cannot inspect Temporal bootstrap runtime identity.'
    }
    try { return ($output[0] | ConvertFrom-Json -ErrorAction Stop) }
    catch {
        Write-TemporalBootstrapDockerInspectDiagnostic -Phase $Phase -Result 'invalid-json' -State $errorClass -CommandThrew $commandThrew -ExitCode $commandExitCode
        throw 'Cannot parse Temporal bootstrap runtime identity.'
    }
}

function Get-TemporalBootstrapContainerId {
    param([Parameter(Mandatory=$true)][string]$Service)
    $ids = @(docker compose @ComposeArgs --env-file $EnvFile ps --all --quiet --no-trunc $Service 2>$null)
    if ($LASTEXITCODE -ne 0 -or $ids.Count -ne 1 -or [string]$ids[0] -cnotmatch '^[0-9a-f]{64}$') {
        throw 'Temporal bootstrap requires one exact service container.'
    }
    return [string]$ids[0]
}

function Assert-TemporalBootstrapRuntimeEnvironment {
    param([Parameter(Mandatory=$true)]$Image, [Parameter(Mandatory=$true)]$Container, [AllowNull()]$Overrides)
    $expected = [System.Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    foreach ($entry in @($Image.Config.Env)) {
        if ($null -eq $entry) { continue }
        $index = ([string]$entry).IndexOf('=')
        if ($index -le 0 -or $expected.ContainsKey(([string]$entry).Substring(0, $index))) { throw 'Temporal image environment is invalid.' }
        $expected.Add(([string]$entry).Substring(0, $index), ([string]$entry).Substring($index + 1))
    }
    if ($null -ne $Overrides) {
        foreach ($property in $Overrides.PSObject.Properties) { $expected[[string]$property.Name] = [string]$property.Value }
    }
    $actual = [System.Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    foreach ($entry in @($Container.Config.Env)) {
        if ($null -eq $entry) { continue }
        $index = ([string]$entry).IndexOf('=')
        if ($index -le 0 -or $actual.ContainsKey(([string]$entry).Substring(0, $index))) { throw 'Temporal container environment is invalid.' }
        $actual.Add(([string]$entry).Substring(0, $index), ([string]$entry).Substring($index + 1))
    }
    if ($actual.Count -ne $expected.Count) { throw 'Temporal container environment differs from its reviewed model.' }
    foreach ($name in $expected.Keys) {
        if (-not $actual.ContainsKey($name) -or $actual[$name] -cne $expected[$name]) {
            throw 'Temporal container environment differs from its reviewed model.'
        }
    }
}

function ConvertFrom-TemporalRuntimeBindPath {
    param([Parameter(Mandatory=$true)][string]$Path)
    $windows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
    if ($windows -and $Path.StartsWith('\\', [StringComparison]::Ordinal)) {
        throw 'A network-share bind source cannot be verified against local Temporal state.'
    }
    # Docker Desktop presents a Windows bind as this Linux VM path on some
    # versions. Unknown translations fail closed during the comparison below.
    if ($windows -and $Path -cmatch '^/run/desktop/mnt/host/([a-zA-Z])/(.*)$') {
        return [System.IO.Path]::GetFullPath("$($Matches[1]):/$($Matches[2])")
    }
    if (-not [System.IO.Path]::IsPathFullyQualified($Path)) { throw 'Temporal runtime bind source cannot be mapped to the host.' }
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-TemporalBootstrapRuntimeMounts {
    param([Parameter(Mandatory=$true)]$Container, [Parameter(Mandatory=$true)][hashtable]$Expected)
    $windows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
    $comparison = if ($windows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    $seen = @{}
    if (@($Container.Mounts).Count -ne $Expected.Count) { throw 'Temporal runtime mount inventory is invalid.' }
    foreach ($mount in $Container.Mounts) {
        $target = [string]$mount.Destination
        if (-not $Expected.ContainsKey($target) -or $seen.ContainsKey($target) -or $mount.RW -ne $false) { throw 'Temporal runtime mount is invalid.' }
        $expectedMount = $Expected[$target]
        if ([string]$mount.Type -cne [string]$expectedMount.Type) { throw 'Temporal runtime mount type is invalid.' }
        if ($expectedMount.Type -ceq 'bind') {
            $source = ConvertFrom-TemporalRuntimeBindPath -Path ([string]$mount.Source)
            if (-not [string]::Equals($source, [string]$expectedMount.Source, $comparison)) { throw 'Temporal runtime bind source differs from the reviewed model.' }
        } elseif ([string]$mount.Name -cne [string]$expectedMount.Source) {
            throw 'Temporal runtime volume differs from the reviewed model.'
        }
        $seen[$target] = $true
    }
}

function Resolve-TemporalBootstrapExistingPath {
    param([Parameter(Mandatory=$true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($full)
    if ([string]::IsNullOrEmpty($root)) { throw 'A running bind source has no host root.' }
    $resolved = $root
    $remaining = $full.Substring($root.Length)
    foreach ($part in $remaining.Split([char[]]@('/', '\'), [StringSplitOptions]::RemoveEmptyEntries)) {
        $candidate = Join-Path $resolved $part
        try { $item = Get-Item -LiteralPath $candidate -Force -ErrorAction Stop }
        catch { throw 'A running bind source cannot be verified on the host.' }
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            try { $target = $item.ResolveLinkTarget($true) } catch { throw 'A running bind alias cannot be resolved.' }
            if ($null -eq $target) { throw 'A running bind alias cannot be resolved.' }
            $resolved = [System.IO.Path]::GetFullPath($target.FullName)
        } else {
            $resolved = [System.IO.Path]::GetFullPath($candidate)
        }
    }
    return $resolved
}

function Get-TemporalBootstrapPathIdentity {
    param([Parameter(Mandatory=$true)][string]$Path)
    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
        # The profile handle check initializes this narrowly scoped native type.
        try { return [TemporalBootstrapFileIdentity]::PathId($Path) }
        catch { throw 'A running bind source file identity cannot be verified.' }
    }
    if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Linux)) {
        throw 'Temporal bootstrap path identity is supported only on Windows and Linux.'
    }
    $stat = Get-Command 'stat' -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $output = @(& $stat.Source '-L' '-c' '%d:%i' '--' $Path 2>$null)
    if ($LASTEXITCODE -ne 0 -or $output.Count -ne 1 -or $output[0] -cnotmatch '^[0-9]+:[0-9]+$') {
        throw 'A running bind source file identity cannot be verified.'
    }
    return [string]$output[0]
}

function Test-TemporalBootstrapSharedNamespace {
    param([AllowEmptyString()][string]$Mode, [Parameter(Mandatory=$true)][string]$ServerId,
        [Parameter(Mandatory=$true)][string]$InitId, [Parameter(Mandatory=$true)][ValidateSet('NetworkMode','PidMode')][string]$Field)
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    for ($depth = 0; $depth -lt 128; $depth++) {
        if ($Field -ceq 'PidMode' -and $Mode -ceq 'host') { return $true }
        if (-not $Mode.StartsWith('container:', [StringComparison]::Ordinal)) {
            if ($Field -ceq 'PidMode' -and $Mode -cnotin @('', 'private')) { throw 'A running process namespace mode is unsupported.' }
            return $false
        }
        $reference = $Mode.Substring('container:'.Length)
        if ($reference -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$') { throw 'A running network namespace reference is invalid.' }
        $targetPhase = if ($Field -ceq 'NetworkMode') { 'network-namespace-target' } else { 'pid-namespace-target' }
        $targetId = [string](Get-TemporalBootstrapDockerObject -Phase $targetPhase -Arguments @('container', 'inspect', '--format', '{{json .Id}}', $reference))
        if ($targetId -cnotmatch '^[0-9a-f]{64}$' -or -not $seen.Add($targetId)) { throw 'A running network namespace chain is invalid.' }
        if ($targetId -ceq $ServerId -or $targetId -ceq $InitId) { return $true }
        $format = if ($Field -ceq 'NetworkMode') { '{{json .HostConfig.NetworkMode}}' } else { '{{json .HostConfig.PidMode}}' }
        $modePhase = if ($Field -ceq 'NetworkMode') { 'network-namespace-mode' } else { 'pid-namespace-mode' }
        $nextMode = Get-TemporalBootstrapDockerObject -Phase $modePhase -Arguments @('container', 'inspect', '--format', $format, $targetId)
        if ($null -eq $nextMode) { throw 'A running namespace cannot be verified.' }
        $Mode = [string]$nextMode
        if ($Field -ceq 'NetworkMode' -and [string]::IsNullOrWhiteSpace($Mode)) { throw 'A running network namespace cannot be verified.' }
    }
    throw 'A running network namespace chain is too deep.'
}

function Assert-TemporalBootstrapRunningPeers {
    param([Parameter(Mandatory=$true)][string]$ServerId, [Parameter(Mandatory=$true)][string]$InitId,
        [Parameter(Mandatory=$true)][string]$StateRoot, [Parameter(Mandatory=$true)][string]$ExpectedProjectName)
    $running = @(docker ps --no-trunc --quiet 2>$null)
    if ($LASTEXITCODE -ne 0 -or $running -cnotcontains $ServerId) { throw 'Cannot verify the running Temporal network inventory.' }
    $windows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
    $comparison = if ($windows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    $profile = Resolve-TemporalBootstrapExistingPath -Path (Join-Path $StateRoot '.temporal-bootstrap/profile.toml')
    $profileProbe = [System.IO.FileStream]::new($profile, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try { $profileIdentity = Get-TemporalBootstrapHandleIdentity -Stream $profileProbe }
    finally { $profileProbe.Dispose() }
    if ($profileIdentity.Links -ne 1) { throw 'Temporal bootstrap profile has an unverified hard-link alias.' }
    $workerToken = Resolve-TemporalBootstrapExistingPath -Path (Join-Path $StateRoot '.secrets/temporal_api_key')
    $workerProbe = [System.IO.FileStream]::new($workerToken, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try { $workerIdentity = Get-TemporalBootstrapHandleIdentity -Stream $workerProbe }
    finally { $workerProbe.Dispose() }
    if ($workerIdentity.Links -ne 1) { throw 'Temporal worker token has an unverified hard-link alias.' }
    $protectedIdentities = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $ancestor = $profile
    while (-not [string]::IsNullOrEmpty($ancestor)) {
        [void]$protectedIdentities.Add((Get-TemporalBootstrapPathIdentity -Path $ancestor))
        $parent = [System.IO.Path]::GetDirectoryName($ancestor)
        if ($parent -ceq $ancestor) { break }
        $ancestor = $parent
    }
    $workerProtectedIdentities = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $ancestor = $workerToken
    while (-not [string]::IsNullOrEmpty($ancestor)) {
        [void]$workerProtectedIdentities.Add((Get-TemporalBootstrapPathIdentity -Path $ancestor))
        $parent = [System.IO.Path]::GetDirectoryName($ancestor)
        if ($parent -ceq $ancestor) { break }
        $ancestor = $parent
    }
    $checkedVolumes = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($peerId in $running) {
        if ([string]$peerId -cnotmatch '^[0-9a-f]{64}$' -or [string]$peerId -ceq $InitId) { throw 'A running container identity is invalid for Temporal bootstrap.' }
        $mode = [string](Get-TemporalBootstrapDockerObject -Phase 'peer-network-mode' -Arguments @('container', 'inspect', '--format', '{{json .HostConfig.NetworkMode}}', [string]$peerId))
        if ([string]::IsNullOrWhiteSpace($mode) -or (Test-TemporalBootstrapSharedNamespace -Mode $mode -ServerId $ServerId -InitId $InitId -Field 'NetworkMode')) {
            throw 'A running container shares or obscures the Temporal network namespace.'
        }
        $pidValue = Get-TemporalBootstrapDockerObject -Phase 'peer-pid-mode' -Arguments @('container', 'inspect', '--format', '{{json .HostConfig.PidMode}}', [string]$peerId)
        if ($null -eq $pidValue) { throw 'A running process namespace cannot be verified.' }
        $pidMode = [string]$pidValue
        if ($pidMode -ceq 'host' -or (Test-TemporalBootstrapSharedNamespace -Mode $pidMode -ServerId $ServerId -InitId $InitId -Field 'PidMode')) {
            throw 'A running container can observe a Temporal process namespace.'
        }
        $peerFormat = '{"Labels":{{json .Config.Labels}},"Mounts":{{json .Mounts}}}'
        $peer = Get-TemporalBootstrapDockerObject -Phase 'peer-mount-metadata' -Arguments @('container', 'inspect', '--format', $peerFormat, [string]$peerId)
        $labelsProperty = $peer.PSObject.Properties['Labels']
        $mountsProperty = $peer.PSObject.Properties['Mounts']
        if ($null -eq $labelsProperty -or $null -eq $mountsProperty -or $null -eq $peer.Labels) {
            throw 'A running container mount inventory cannot be verified.'
        }
        $labels = $peer.Labels
        if ($null -eq $peer.Mounts) { $mounts = @() } else { $mounts = @($peer.Mounts) }
        foreach ($mount in $mounts) {
            if ($null -eq $mount) { throw 'A running container mount entry is invalid.' }
            switch -CaseSensitive ([string]$mount.Type) {
                'bind' {
                    $bindSource = ConvertFrom-TemporalRuntimeBindPath -Path ([string]$mount.Source)
                    $source = [string]$bindSource
                    # Docker Desktop's daemon socket is a VM-local socket, not
                    # a Windows host bind. The daemon itself is trusted.
                    if ($windows -and $bindSource -ceq '/var/run/docker.sock') { continue }
                    $source = Resolve-TemporalBootstrapExistingPath -Path $bindSource
                    $prefix = $source.TrimEnd([char[]]@('/', '\')) + [System.IO.Path]::DirectorySeparatorChar
                    if ([string]::Equals($source, $profile, $comparison) -or $profile.StartsWith($prefix, $comparison) -or
                        $protectedIdentities.Contains((Get-TemporalBootstrapPathIdentity -Path $source))) {
                        throw 'A running container can read the Temporal bootstrap profile.'
                    }
                    $tokenPrefix = $source.TrimEnd([char[]]@('/', '\')) + [System.IO.Path]::DirectorySeparatorChar
                    $tokenExposed = [string]::Equals($source, $workerToken, $comparison) -or
                        $workerToken.StartsWith($tokenPrefix, $comparison) -or
                        $workerProtectedIdentities.Contains((Get-TemporalBootstrapPathIdentity -Path $source))
                    if ($tokenExposed) {
                        $serviceName = [string]$labels.PSObject.Properties['com.docker.compose.service'].Value
                        $projectName = [string]$labels.PSObject.Properties['com.docker.compose.project'].Value
                        if ($serviceName -cne 'file-processor' -or $projectName -cne $ExpectedProjectName -or
                            -not [string]::Equals([System.IO.Path]::GetFullPath($bindSource), $workerToken, $comparison) -or
                            -not [string]::Equals($source, $workerToken, $comparison) -or
                            [string]$mount.Destination -cne '/app/.secrets/temporal_api_key' -or $mount.RW -ne $false) {
                            throw 'A running container can read the Temporal worker token.'
                        }
                    }
                }
                'volume' {
                    $name = [string]$mount.Name
                    if ($name -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$') { throw 'A running container volume cannot be verified.' }
                    if ($checkedVolumes.Add($name)) {
                        Assert-TemporalBootstrapUnconfiguredVolume -Name $name
                    }
                }
                'tmpfs' { }
                default { throw 'A running container mount type cannot be verified.' }
            }
        }
    }
}

function Assert-InPlaceTemporalBootstrapRuntime {
    param([Parameter(Mandatory=$true)]$ComposeModel, [Parameter(Mandatory=$true)][string]$StateRoot, [Parameter(Mandatory=$true)][string]$ProjectRoot)
    $project = [string]$ComposeModel.name
    if ($project -cnotmatch '^[a-z0-9][a-z0-9_-]{0,62}$' -or
        ($null -ne $script:LiveStandOwner -and
            -not [string]::IsNullOrWhiteSpace([string]$script:LiveStandOwner.project_name) -and
            $project -cne [string]$script:LiveStandOwner.project_name)) {
        throw 'Temporal bootstrap project identity is invalid.'
    }
    $serverModel = $ComposeModel.services.PSObject.Properties['temporal'].Value
    $initModel = $ComposeModel.services.PSObject.Properties['temporal-namespace-init'].Value
    $imageFormat = '{"Id":{{json .Id}},"Config":{"User":{{json .Config.User}},"Env":{{json .Config.Env}}}}'
    $serverImage = Get-TemporalBootstrapDockerObject -Phase 'temporal-server-image' -Arguments @('image', 'inspect', '--format', $imageFormat, [string]$serverModel.image)
    $initImage = Get-TemporalBootstrapDockerObject -Phase 'temporal-init-image' -Arguments @('image', 'inspect', '--format', $imageFormat, [string]$initModel.image)
    if ([string]$serverImage.Id -cnotmatch '^sha256:[0-9a-f]{64}$' -or
        [string]$initImage.Id -cnotmatch '^sha256:[0-9a-f]{64}$' -or
        [string]$serverImage.Config.User -cne 'temporal') { throw 'Temporal image identities are invalid.' }
    $serverId = Get-TemporalBootstrapContainerId -Service 'temporal'
    $initId = Get-TemporalBootstrapContainerId -Service 'temporal-namespace-init'
    # Select only the owned containers' fields required for identity. In
    # particular, never request State.Health.Log or raw container diagnostics.
    $format = '{"Id":{{json .Id}},"Image":{{json .Image}},' +
        '"Config":{"User":{{json .Config.User}},"Env":{{json .Config.Env}},"Labels":{{json .Config.Labels}},' +
        '"Entrypoint":{{json .Config.Entrypoint}},"Cmd":{{json .Config.Cmd}},"Healthcheck":{{json .Config.Healthcheck}}},' +
        '"State":{"Status":{{json .State.Status}},"Running":{{json .State.Running}},' +
        '"Health":{{if .State.Health}}{"Status":{{json .State.Health.Status}}}{{else}}null{{end}}},' +
        '"HostConfig":{"NetworkMode":{{json .HostConfig.NetworkMode}},"ReadonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},' +
        '"Privileged":{{json .HostConfig.Privileged}},"CapDrop":{{json .HostConfig.CapDrop}},"CapAdd":{{json .HostConfig.CapAdd}},' +
        '"SecurityOpt":{{json .HostConfig.SecurityOpt}},"PidMode":{{json .HostConfig.PidMode}},"UsernsMode":{{json .HostConfig.UsernsMode}},' +
        '"Devices":{{json .HostConfig.Devices}},"DeviceCgroupRules":{{json .HostConfig.DeviceCgroupRules}},"Tmpfs":{{json .HostConfig.Tmpfs}}},' +
        '"Mounts":{{json .Mounts}}}'
    $server = Get-TemporalBootstrapDockerObject -Phase 'temporal-server-container' -Arguments @('container', 'inspect', '--format', $format, $serverId)
    $init = Get-TemporalBootstrapDockerObject -Phase 'temporal-init-container' -Arguments @('container', 'inspect', '--format', $format, $initId)
    foreach ($pair in @(@($server, $serverId, 'temporal', $serverImage), @($init, $initId, 'temporal-namespace-init', $initImage))) {
        $container, $id, $service, $image = $pair
        if ([string]$container.Id -cne $id -or [string]$container.Image -cne [string]$image.Id -or
            [string]$container.Config.Labels.PSObject.Properties['com.docker.compose.project'].Value -cne $project -or
            [string]$container.Config.Labels.PSObject.Properties['com.docker.compose.service'].Value -cne $service) {
            throw 'Temporal runtime container or image does not belong to the reviewed service.'
        }
    }
    if ($server.State.Running -ne $true -or [string]$server.State.Health.Status -cne 'healthy' -or
        [string]$server.Config.User -cne [string]$serverImage.Config.User -or
        $server.HostConfig.Privileged -eq $true -or
        @($server.HostConfig.CapAdd | Where-Object { $null -ne $_ }).Count -ne 0 -or
        @($server.HostConfig.Devices | Where-Object { $null -ne $_ }).Count -ne 0 -or
        @($server.HostConfig.DeviceCgroupRules | Where-Object { $null -ne $_ }).Count -ne 0 -or
        [string]$server.HostConfig.NetworkMode -cnotin @("${project}_internal", "${project}_published_ports") -or
        [string]$server.HostConfig.PidMode -cnotin @('', 'private') -or
        [string]$server.HostConfig.UsernsMode -cnotin @('', 'private') -or
        ($server.Config.Entrypoint -join "`n") -cne "/bin/sh`n/etc/temporal/wave144-entrypoint.sh" -or
        @($server.Config.Cmd | Where-Object { $null -ne $_ }).Count -ne 0 -or
        ($server.Config.Healthcheck.Test -join "`n") -cne "CMD-SHELL`nwget -q --spider --timeout=3 http://127.0.0.1:8000/metrics || exit 1") {
        throw 'Temporal runtime server is not the reviewed healthy listener.'
    }
    if ([string]$init.State.Status -cne 'created' -or $init.State.Running -ne $false -or
        [string]$init.HostConfig.NetworkMode -cne "container:$serverId" -or
        [string]$init.Config.User -cne '1000:1000' -or $init.HostConfig.ReadonlyRootfs -ne $true -or
        $init.HostConfig.Privileged -eq $true -or ($init.HostConfig.CapDrop -join "`n") -cne 'ALL' -or
        @($init.HostConfig.Devices | Where-Object { $null -ne $_ }).Count -ne 0 -or
        @($init.HostConfig.DeviceCgroupRules | Where-Object { $null -ne $_ }).Count -ne 0 -or
        [string]$init.HostConfig.PidMode -cnotin @('', 'private') -or
        [string]$init.HostConfig.UsernsMode -cnotin @('', 'private') -or
        @($init.HostConfig.CapAdd | Where-Object { $null -ne $_ }).Count -ne 0 -or
        ($init.HostConfig.SecurityOpt -join "`n") -cne 'no-new-privileges:true' -or
        ($init.Config.Entrypoint -join "`n") -cne "/bin/sh`n/etc/temporal/namespace-init.sh" -or
        @($init.Config.Cmd | Where-Object { $null -ne $_ }).Count -ne 0 -or $null -ne $init.Config.Healthcheck) {
        throw 'Temporal runtime initializer is not isolated in the reviewed namespace.'
    }
    $tmpfs = $init.HostConfig.Tmpfs
    if ($null -eq $tmpfs -or @($tmpfs.PSObject.Properties).Count -ne 2) { throw 'Temporal runtime temporary mounts are invalid.' }
    foreach ($target in @('/tmp', '/run/temporal-bootstrap-runtime')) {
        $options = [string]$tmpfs.PSObject.Properties[$target].Value
        if ((@($options -split ',' | Sort-Object -CaseSensitive) -join ',') -cne
            (@('uid=1000','gid=1000','mode=0700','noexec','nosuid','nodev' | Sort-Object -CaseSensitive) -join ',')) {
            throw 'Temporal runtime temporary mount options are invalid.'
        }
    }
    Assert-TemporalBootstrapRuntimeEnvironment -Image $serverImage -Container $server -Overrides $serverModel.environment
    Assert-TemporalBootstrapRuntimeEnvironment -Image $initImage -Container $init -Overrides $null
    Assert-TemporalBootstrapRuntimeMounts -Container $server -Expected @{
        '/etc/temporal/config/docker.yaml' = @{ Type='bind'; Source=[System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'services/temporal/config.yaml')) }
        '/etc/temporal/wave144-entrypoint.sh' = @{ Type='bind'; Source=[System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'services/temporal/entrypoint.sh')) }
        '/etc/temporal/jwks-ca' = @{ Type='volume'; Source="${project}_temporal-jwks-ca" }
    }
    Assert-TemporalBootstrapRuntimeMounts -Container $init -Expected @{
        '/etc/temporal/namespace-init.sh' = @{ Type='bind'; Source=[System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'scripts/temporal/namespace-init.sh')) }
        '/run/temporal-bootstrap/profile.toml' = @{ Type='bind'; Source=[System.IO.Path]::GetFullPath((Join-Path $StateRoot '.temporal-bootstrap/profile.toml')) }
        '/run/temporal-worker/token' = @{ Type='bind'; Source=[System.IO.Path]::GetFullPath((Join-Path $StateRoot '.secrets/temporal_api_key')) }
    }
    # Do not trust the current project model to describe orphan or foreign
    # containers. Read only network/mount metadata for every running peer.
    Assert-TemporalBootstrapRunningPeers -ServerId $serverId -InitId $initId -StateRoot $StateRoot -ExpectedProjectName $project
    return $initId
}

function Invoke-TemporalBootstrapDockerBounded {
    param([Parameter(Mandatory=$true)][string[]]$Arguments, [Parameter(Mandatory=$true)][int]$TimeoutSeconds, [string]$Executable = '')
    if ([string]::IsNullOrEmpty($Executable)) { $Executable = (Get-Command docker -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source }
    if ($TimeoutSeconds -lt 1 -or $TimeoutSeconds -gt 240) { throw 'Temporal bootstrap Docker timeout is invalid.' }
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Executable
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'Cannot start Temporal bootstrap Docker command.' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true)
            $null = $process.WaitForExit(5000)
            throw 'Temporal bootstrap Docker command timed out.'
        }
        $output = $stdout.GetAwaiter().GetResult()
        $null = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw 'Temporal bootstrap Docker command failed.' }
        return $output.Trim()
    } finally { $process.Dispose() }
}
