"""Regression contract for private POSIX env-file creation in start-docker.ps1."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

SOURCE_ENV = "AUD253_SOURCE_PATH"
PWSH_ENV = "AUD253_PWSH"


POWERSHELL_HARNESS = r"""
param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$TestRoot
)
class Aud253FailingTruncateStream {
    [System.IO.FileStream] $InnerStream
    [bool] $Disposed

    Aud253FailingTruncateStream([System.IO.FileStream] $innerStream) {
        $this.InnerStream = $innerStream
        $this.Disposed = $false
    }

    [void] SetLength([long] $value) {
        throw [System.IO.IOException]::new('AUD253_SYNTHETIC_SETLENGTH_FAILURE')
    }

    [void] Dispose() {
        $this.InnerStream.Dispose()
        $this.Disposed = $true
    }
}
class Aud253FailingTruncateAndDisposeStream {
    [System.IO.FileStream] $InnerStream
    [bool] $DisposeAttempted
    [bool] $InnerDisposed

    Aud253FailingTruncateAndDisposeStream([System.IO.FileStream] $innerStream) {
        $this.InnerStream = $innerStream
        $this.DisposeAttempted = $false
        $this.InnerDisposed = $false
    }

    [void] SetLength([long] $value) {
        throw [System.IO.IOException]::new('AUD253_SYNTHETIC_SETLENGTH_FAILURE')
    }

    [void] Dispose() {
        $this.DisposeAttempted = $true
        $this.InnerStream.Dispose()
        $this.InnerDisposed = $true
        throw [System.IO.IOException]::new('AUD253_SYNTHETIC_DISPOSE_FAILURE')
    }
}
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 or newer is required.' }
$script:LiveStateMode = $false
$script:StateRoot = [System.IO.Path]::GetFullPath($TestRoot)
$null = [System.IO.Directory]::CreateDirectory($script:StateRoot)
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Launcher source does not parse.' }
$definitions = @{}
foreach ($definition in $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    $definitions[$definition.Name] = $definition
}
$common = @(
    'Resolve-StatePath',
    'Set-LiveStandPrivateFileMode',
    'Write-Utf8NoBom'
)
foreach ($name in $common) {
    if (-not $definitions.ContainsKey($name)) { throw "Required source function is missing: $name" }
    Invoke-Expression $definitions[$name].Extent.Text
}
$liveModeText = $definitions['Set-LiveStandPrivateFileMode'].Extent.Text
if ($liveModeText -notmatch 'Get-Command\s+"icacls\.exe"' -or $liveModeText -notmatch '"/reset"' -or $liveModeText -notmatch '"/setowner"') {
    throw 'Existing Windows live-state ACL controls are missing.'
}
function Get-ModeText([string]$Path) {
    return ([Convert]::ToString([int][System.IO.File]::GetUnixFileMode($Path), 8)).PadLeft(4, '0')
}
if (-not $definitions.ContainsKey('New-EnvironmentFileStream')) {
    throw 'Candidate must expose the private stream factory for cleanup-failure testing.'
}
$modernFunctions = @(
    'Assert-EnvironmentFileLeafPath',
    'Set-EnvironmentFilePrivateMode',
    'New-EnvironmentFileStream',
    'Open-EnvironmentFileForWrite',
    'Copy-EnvironmentFile'
)
$missingModernFunctions = @($modernFunctions | Where-Object { -not $definitions.ContainsKey($_) })
if ($missingModernFunctions.Count -gt 0) {
    throw "Required environment-file helpers are missing: $($missingModernFunctions -join ', ')"
}
foreach ($name in $modernFunctions) {
    Invoke-Expression $definitions[$name].Extent.Text
}
$environmentModeText = $definitions['Set-EnvironmentFilePrivateMode'].Extent.Text
if ($environmentModeText -notmatch '(?s)if\s*\(\$LiveStateMode\)\s*\{\s*Set-LiveStandPrivateFileMode\s+-Path\s+\$Path\s*return' -or
    $environmentModeText -notmatch 'OSPlatform\]::Windows' -or
    $environmentModeText -notmatch '(?s)OSPlatform\]::Windows\s*\)\s*\)\s*\{\s*return') {
    throw 'Live helper dispatch or non-live Windows ACL preservation changed.'
}
$runningOnWindows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)
function Test-ByteSequenceEqual {
    param([byte[]]$Left, [byte[]]$Right)
    if ($Left.Length -ne $Right.Length) { return $false }
    for ($index = 0; $index -lt $Left.Length; $index++) {
        if ($Left[$index] -ne $Right[$index]) { return $false }
    }
    return $true
}

$outsidePath = Join-Path $script:StateRoot 'outside.env'
$outsideExpected = 'AUD253_TARGET=synthetic-fixture'
$linkSourcePath = Join-Path $script:StateRoot 'link-source.env'
$writeLink = Join-Path $script:StateRoot 'write-link.env'
$copyLink = Join-Path $script:StateRoot 'copy-link.env'
$sourceLink = Join-Path $script:StateRoot 'source-link.env'
[System.IO.File]::WriteAllText($outsidePath, $outsideExpected)
[System.IO.File]::WriteAllText($linkSourcePath, 'source bytes')
if (-not $runningOnWindows) {
    $sourceMode = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor
        [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::OtherRead
    [System.IO.File]::SetUnixFileMode($outsidePath, $sourceMode)
    [System.IO.File]::SetUnixFileMode($linkSourcePath, $sourceMode)
}
[System.IO.File]::CreateSymbolicLink($writeLink, $outsidePath) | Out-Null
[System.IO.File]::CreateSymbolicLink($copyLink, $outsidePath) | Out-Null
[System.IO.File]::CreateSymbolicLink($sourceLink, $linkSourcePath) | Out-Null
$danglingTarget = Join-Path $script:StateRoot 'missing-link-target.env'
$danglingLink = Join-Path $script:StateRoot 'dangling-link.env'
[System.IO.File]::CreateSymbolicLink($danglingLink, $danglingTarget) | Out-Null
$outsidePermissionsBefore = if ($runningOnWindows) { (Get-Acl -LiteralPath $outsidePath).Sddl } else { Get-ModeText $outsidePath }

$copyBytesTarget = Join-Path $script:StateRoot 'copy-bytes.env'
Copy-EnvironmentFile -SourcePath $linkSourcePath -DestinationPath $copyBytesTarget
$copyBytesMatched = Test-ByteSequenceEqual -Left ([System.IO.File]::ReadAllBytes($linkSourcePath)) -Right ([System.IO.File]::ReadAllBytes($copyBytesTarget))

$writeDirectory = Join-Path $script:StateRoot 'write-directory'
$copyDestinationDirectory = Join-Path $script:StateRoot 'copy-destination-directory'
$copySourceDirectory = Join-Path $script:StateRoot 'copy-source-directory'
$copySourceDirectoryTarget = Join-Path $script:StateRoot 'copy-source-directory-target'
$sourceDirectoryChild = Join-Path $copySourceDirectory 'child.env'
[System.IO.Directory]::CreateDirectory($writeDirectory) | Out-Null
[System.IO.Directory]::CreateDirectory($copyDestinationDirectory) | Out-Null
[System.IO.Directory]::CreateDirectory($copySourceDirectory) | Out-Null
[System.IO.File]::WriteAllText($sourceDirectoryChild, 'directory bytes')

$writeSymlinkRejected = $true
$copySymlinkRejected = $true
$sourceSymlinkRejected = $true
$danglingLeafRejected = $false
$danglingWriteRejected = $true
$danglingCopyDestinationRejected = $true
$danglingSourceRejected = $true
$danglingTargetsAbsent = $true
$writeDirectoryRejected = $true
$copyDestinationDirectoryRejected = $true
$copySourceDirectoryRejected = $true
$targetUnchanged = $true
$copyDirectoryUnchanged = $true
$writeDirectoryUnchanged = $true
$sourceDirectoryTargetAbsent = $true
foreach ($liveMode in @($false, $true)) {
    $script:LiveStateMode = $liveMode
    $beforeWrite = [System.IO.File]::ReadAllBytes($outsidePath)
    try { Write-Utf8NoBom -Path $writeLink -Content 'AUD253_TARGET=must-not-be-written'; $writeSymlinkRejected = $false } catch { }
    if (-not (Test-ByteSequenceEqual -Left $beforeWrite -Right ([System.IO.File]::ReadAllBytes($outsidePath)))) { $targetUnchanged = $false }
    $permissionsAfterWrite = if ($runningOnWindows) { (Get-Acl -LiteralPath $outsidePath).Sddl } else { Get-ModeText $outsidePath }
    if ($permissionsAfterWrite -cne $outsidePermissionsBefore) { $targetUnchanged = $false }

    $beforeCopy = [System.IO.File]::ReadAllBytes($outsidePath)
    try { Copy-EnvironmentFile -SourcePath $linkSourcePath -DestinationPath $copyLink; $copySymlinkRejected = $false } catch { }
    if (-not (Test-ByteSequenceEqual -Left $beforeCopy -Right ([System.IO.File]::ReadAllBytes($outsidePath)))) { $targetUnchanged = $false }
    $permissionsAfterCopy = if ($runningOnWindows) { (Get-Acl -LiteralPath $outsidePath).Sddl } else { Get-ModeText $outsidePath }
    if ($permissionsAfterCopy -cne $outsidePermissionsBefore) { $targetUnchanged = $false }

    $danglingLeafRejected = $false
try { Assert-EnvironmentFileLeafPath -Path $danglingLink } catch {
    $danglingLeafRejected = $_.Exception.Message -eq 'Environment file path refuses reparse points.'
}
$sourceLinkDestination = Join-Path $script:StateRoot 'source-link-destination.env'
    try { Copy-EnvironmentFile -SourcePath $sourceLink -DestinationPath $sourceLinkDestination; $sourceSymlinkRejected = $false } catch { }
    if (Test-Path -LiteralPath $sourceLinkDestination) { $sourceSymlinkRejected = $false }

    try { Write-Utf8NoBom -Path $danglingLink -Content 'must-not-be-written'; $danglingWriteRejected = $false } catch { }
    try { Copy-EnvironmentFile -SourcePath $linkSourcePath -DestinationPath $danglingLink; $danglingCopyDestinationRejected = $false } catch { }
    $danglingSourceDestination = Join-Path $script:StateRoot 'dangling-source-destination.env'
    try { Copy-EnvironmentFile -SourcePath $danglingLink -DestinationPath $danglingSourceDestination; $danglingSourceRejected = $false } catch { }
    if ((Test-Path -LiteralPath $danglingTarget) -or (Test-Path -LiteralPath $danglingSourceDestination)) { $danglingTargetsAbsent = $false }

    try { Write-Utf8NoBom -Path $writeDirectory -Content 'must-not-be-written'; $writeDirectoryRejected = $false } catch { }
    if (@(Get-ChildItem -LiteralPath $writeDirectory -Force).Count -ne 0) { $writeDirectoryUnchanged = $false }
    try { Copy-EnvironmentFile -SourcePath $linkSourcePath -DestinationPath $copyDestinationDirectory; $copyDestinationDirectoryRejected = $false } catch { }
    if (@(Get-ChildItem -LiteralPath $copyDestinationDirectory -Force).Count -ne 0) { $copyDirectoryUnchanged = $false }

    try { Copy-EnvironmentFile -SourcePath $copySourceDirectory -DestinationPath $copySourceDirectoryTarget; $copySourceDirectoryRejected = $false } catch { }
    if (Test-Path -LiteralPath $copySourceDirectoryTarget) { $sourceDirectoryTargetAbsent = $false }
}
$script:LiveStateMode = $false
if (-not $copyBytesMatched -or -not $writeSymlinkRejected -or -not $copySymlinkRejected -or
    -not $sourceSymlinkRejected -or -not $danglingLeafRejected -or
    -not $danglingWriteRejected -or -not $danglingCopyDestinationRejected -or
    -not $danglingSourceRejected -or -not $danglingTargetsAbsent -or -not $writeDirectoryRejected -or
    -not $copyDestinationDirectoryRejected -or -not $copySourceDirectoryRejected -or
    -not $targetUnchanged -or -not $copyDirectoryUnchanged -or
    -not $writeDirectoryUnchanged -or -not $sourceDirectoryTargetAbsent) {
    throw 'Environment-file leaf safety behavior failed.'
}

if ($runningOnWindows) {
    $existingPath = Join-Path $script:StateRoot 'windows-existing.env'
    [System.IO.File]::WriteAllText($existingPath, 'AUD253_SYNTHETIC=old-fixture')
    $before = (Get-Acl -LiteralPath $existingPath).Sddl
    Write-Utf8NoBom -Path $existingPath -Content 'AUD253_SYNTHETIC=new-fixture'
    $after = (Get-Acl -LiteralPath $existingPath).Sddl
    if ($before -cne $after) { throw 'Windows non-live writer changed the file ACL.' }
    $script:LiveStateMode = $true
    $livePath = Join-Path $script:StateRoot 'windows-live.env'
    Write-Utf8NoBom -Path $livePath -Content 'AUD253_SYNTHETIC=live-fixture'
    $script:LiveStateMode = $false
    $liveOwner = (Get-Acl -LiteralPath $livePath).Owner
    if ([string]::IsNullOrWhiteSpace($liveOwner)) { throw 'Windows live ACL helper did not assign an owner.' }
    Write-Output 'AUD253_RESULT=windowsNonLiveAclUnchanged,liveAclHelperPreserved'
    exit 0
}

$opener = $definitions['Open-EnvironmentFileForWrite'].Extent.Text
$modeIndex = $opener.IndexOf('[System.IO.File]::SetUnixFileMode', [StringComparison]::Ordinal)
$openIndex = $opener.IndexOf('New-EnvironmentFileStream -Path $absolutePath -Options $options', [StringComparison]::Ordinal)
$truncateIndex = $opener.IndexOf('$stream.SetLength(0)', [StringComparison]::Ordinal)
$factoryText = $definitions['New-EnvironmentFileStream'].Extent.Text
if ($modeIndex -lt 0 -or $openIndex -lt 0 -or $truncateIndex -lt 0 -or $modeIndex -gt $openIndex -or $openIndex -gt $truncateIndex -or
    $factoryText -notmatch '\[System.IO.FileStream\]::new\(\$Path,\s*\$Options\)') {
    throw 'Existing env file must be made private before opening/truncation, using the real file-stream factory.'
}
if ($opener -notmatch '\$options\.UnixCreateMode\s*=\s*\$ownerReadWrite') {
    throw 'New POSIX files must receive owner-only mode at creation.'
}
$writer = $definitions['Write-Utf8NoBom'].Extent.Text
$writerGuardIndex = $writer.IndexOf('Assert-EnvironmentFileLeafPath -Path $absolutePath', [StringComparison]::Ordinal)
$writeAllTextIndex = $writer.IndexOf('[System.IO.File]::WriteAllText', [StringComparison]::Ordinal)
if ($writerGuardIndex -lt 0 -or ($writeAllTextIndex -ge 0 -and $writerGuardIndex -gt $writeAllTextIndex)) {
    throw "Environment-file write must validate its leaf before writing."
}
if ($writer -notmatch 'Open-EnvironmentFileForWrite\s+-Path\s+\$absolutePath') {
    throw 'Generated env writer does not use the secure open routine.'
}
$copyText = $definitions['Copy-EnvironmentFile'].Extent.Text
$copySourceGuardIndex = $copyText.IndexOf('Assert-EnvironmentFileLeafPath -Path $absoluteSource', [StringComparison]::Ordinal)
$copyDestinationGuardIndex = $copyText.IndexOf('Assert-EnvironmentFileLeafPath -Path $absoluteDestination', [StringComparison]::Ordinal)
$copyItemIndex = $copyText.IndexOf('Copy-Item -LiteralPath', [StringComparison]::Ordinal)
$copyOpenIndex = $copyText.IndexOf('Open-EnvironmentFileForWrite', [StringComparison]::Ordinal)
if ($copySourceGuardIndex -lt 0 -or $copyDestinationGuardIndex -lt 0 -or
    ($copyItemIndex -ge 0 -and ($copySourceGuardIndex -gt $copyItemIndex -or $copyDestinationGuardIndex -gt $copyItemIndex)) -or
    ($copyOpenIndex -ge 0 -and ($copySourceGuardIndex -gt $copyOpenIndex -or $copyDestinationGuardIndex -gt $copyOpenIndex))) {
    throw "Environment-file copy must validate both leaves before copying."
}
if ($copyText -notmatch 'Open-EnvironmentFileForWrite\s+-Path\s+\$absoluteDestination') {
    throw 'POSIX env copy does not use the secure open routine.'
}
$sourceText = [System.IO.File]::ReadAllText($SourcePath)
if ($sourceText -notmatch 'Copy-EnvironmentFile\s+-SourcePath\s+\$EnvCompose\s+-DestinationPath\s+\$EnvFile' -or
    $sourceText -notmatch 'Copy-EnvironmentFile\s+-SourcePath\s+\$EnvFile\s+-DestinationPath\s+\$EnvCompose') {
    throw 'Both launcher env-copy call sites must use the secure copy routine.'
}

$productionFactory = (Get-Command New-EnvironmentFileStream -CommandType Function).ScriptBlock
$script:aud253FailureStream = $null
$setLengthFailurePath = Join-Path $script:StateRoot 'setlength-failure.env'
Set-Item -Path Function:New-EnvironmentFileStream -Value {
    param([string]$Path, [System.IO.FileStreamOptions]$Options)
    $innerStream = [System.IO.FileStream]::new($Path, $Options)
    $script:aud253FailureStream = [Aud253FailingTruncateStream]::new($innerStream)
    return $script:aud253FailureStream
}
$setLengthFailureObserved = $false
try {
    $null = Open-EnvironmentFileForWrite -Path $setLengthFailurePath
} catch {
    $setLengthFailureObserved = $_.Exception.Message -ceq 'AUD253_SYNTHETIC_SETLENGTH_FAILURE'
} finally {
    Set-Item -Path Function:New-EnvironmentFileStream -Value $productionFactory
}
$setLengthFailureMode = if (Test-Path -LiteralPath $setLengthFailurePath) {
    Get-ModeText $setLengthFailurePath
} else {
    'missing'
}
$setLengthFailureDisposed = $null -ne $script:aud253FailureStream -and $script:aud253FailureStream.Disposed
if (-not $setLengthFailureObserved -or -not $setLengthFailureDisposed -or $setLengthFailureMode -ne '0600') {
    Write-Output "AUD253_FAILURE_TEST observed=$setLengthFailureObserved disposed=$setLengthFailureDisposed mode=$setLengthFailureMode"
    throw 'SetLength failure must preserve its error, dispose the opened stream, and keep the created file private.'
}
$script:aud253DualFailureStream = $null
$dualFailurePath = Join-Path $script:StateRoot 'setlength-and-dispose-failure.env'
Set-Item -Path Function:New-EnvironmentFileStream -Value {
    param([string]$Path, [System.IO.FileStreamOptions]$Options)
    $innerStream = [System.IO.FileStream]::new($Path, $Options)
    $script:aud253DualFailureStream = [Aud253FailingTruncateAndDisposeStream]::new($innerStream)
    return $script:aud253DualFailureStream
}
$dualFailureException = $null
try {
    $null = Open-EnvironmentFileForWrite -Path $dualFailurePath
} catch {
    $dualFailureException = $_.Exception
} finally {
    Set-Item -Path Function:New-EnvironmentFileStream -Value $productionFactory
}
$dualFailureMessages = @()
if ($dualFailureException -is [System.AggregateException]) {
    $dualFailureMessages = @($dualFailureException.InnerExceptions | ForEach-Object { $_.Message })
}
$dualFailureDisposeAttempted = $null -ne $script:aud253DualFailureStream -and
    $script:aud253DualFailureStream.DisposeAttempted
$dualFailureInnerDisposed = $null -ne $script:aud253DualFailureStream -and
    $script:aud253DualFailureStream.InnerDisposed
$dualFailureMode = if (Test-Path -LiteralPath $dualFailurePath) {
    Get-ModeText $dualFailurePath
} else {
    'missing'
}
if ($dualFailureException -isnot [System.AggregateException] -or
    $dualFailureMessages.Count -ne 2 -or
    $dualFailureMessages[0] -cne 'AUD253_SYNTHETIC_SETLENGTH_FAILURE' -or
    $dualFailureMessages[1] -cne 'AUD253_SYNTHETIC_DISPOSE_FAILURE' -or
    -not $dualFailureDisposeAttempted -or -not $dualFailureInnerDisposed -or
    $dualFailureMode -ne '0600') {
    $dualFailureType = if ($null -eq $dualFailureException) { 'missing' } else { $dualFailureException.GetType().FullName }
    Write-Output "AUD253_DUAL_FAILURE_TEST type=$dualFailureType messages=$($dualFailureMessages -join '|') disposeAttempted=$dualFailureDisposeAttempted innerDisposed=$dualFailureInnerDisposed mode=$dualFailureMode"
    throw 'SetLength and Dispose failures must both be preserved, the stream must be closed, and the created file must remain private.'
}
$interruptedPath = Join-Path $script:StateRoot 'interrupted.env'
$interruptedStream = Open-EnvironmentFileForWrite -Path $interruptedPath
$interruptedBefore = Get-ModeText $interruptedPath
$interruptedLength = (Get-Item -LiteralPath $interruptedPath).Length
$interruptedStream.Dispose()
$failedWrite = $false
try { $interruptedStream.Write([byte[]]@(65), 0, 1) } catch { $failedWrite = $true }
$interruptedAfter = Get-ModeText $interruptedPath

$existingPath = Join-Path $script:StateRoot 'existing.env'
[System.IO.File]::WriteAllText($existingPath, 'AUD253_OLD_SYNTHETIC=fixture')
$sourceMode = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor
    [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::OtherRead
[System.IO.File]::SetUnixFileMode($existingPath, $sourceMode)
$existingStream = Open-EnvironmentFileForWrite -Path $existingPath
$existingBeforeContent = Get-ModeText $existingPath
$existingEmptyLength = (Get-Item -LiteralPath $existingPath).Length
$existingStream.Dispose()
Write-Utf8NoBom -Path $existingPath -Content 'AUD253_SYNTHETIC=existing-fixture'

$generatedPath = Join-Path $script:StateRoot 'generated.env'
Write-Utf8NoBom -Path $generatedPath -Content 'AUD253_SYNTHETIC=generated-fixture'
$copySource = Join-Path $script:StateRoot 'copy-source.env'
$copyNew = Join-Path $script:StateRoot 'copy-new.env'
$copyExisting = Join-Path $script:StateRoot 'copy-existing.env'
[System.IO.File]::WriteAllText($copySource, 'AUD253_SYNTHETIC=copy-fixture')
[System.IO.File]::SetUnixFileMode($copySource, $sourceMode)
Copy-EnvironmentFile -SourcePath $copySource -DestinationPath $copyNew
[System.IO.File]::WriteAllText($copyExisting, 'AUD253_OLD_SYNTHETIC=copy-fixture')
[System.IO.File]::SetUnixFileMode($copyExisting, $sourceMode)
Copy-EnvironmentFile -SourcePath $copySource -DestinationPath $copyExisting


$script:LiveStateMode = $true
$livePath = Join-Path $script:StateRoot 'live.env'
Write-Utf8NoBom -Path $livePath -Content 'AUD253_SYNTHETIC=live-fixture'
$script:LiveStateMode = $false
$actual = [ordered]@{
    setLengthFailureObserved = $setLengthFailureObserved
    setLengthFailureDisposed = $setLengthFailureDisposed
    setLengthFailureMode = $setLengthFailureMode
    dualFailureMessagesPreserved = $dualFailureMessages.Count -eq 2
    dualFailureStreamClosed = $dualFailureInnerDisposed
    generated = Get-ModeText $generatedPath
    copyNew = Get-ModeText $copyNew
    copyExisting = Get-ModeText $copyExisting
    interruptedBefore = $interruptedBefore
    interruptedAfter = $interruptedAfter
    interruptedLength = $interruptedLength
    failedWrite = $failedWrite
    existingBeforeContent = $existingBeforeContent
    existingEmptyLength = $existingEmptyLength
    existingFinal = Get-ModeText $existingPath
    live = Get-ModeText $livePath
    writeSymlinkRejected = $writeSymlinkRejected
    copySymlinkRejected = $copySymlinkRejected
}
Write-Output ("AUD253_RESULT=" + (($actual.GetEnumerator() | ForEach-Object { "$($_.Key):$($_.Value)" }) -join ','))
if ($actual.generated -ne '0600' -or $actual.copyNew -ne '0600' -or $actual.copyExisting -ne '0600' -or
    $actual.interruptedBefore -ne '0600' -or $actual.interruptedAfter -ne '0600' -or
    $actual.interruptedLength -ne 0 -or -not $actual.failedWrite -or
    $actual.existingBeforeContent -ne '0600' -or $actual.existingEmptyLength -ne 0 -or
    $actual.existingFinal -ne '0600' -or $actual.live -ne '0600' -or
    -not $actual.writeSymlinkRejected -or -not $actual.copySymlinkRejected) {
    throw 'AUD-253 env-file private-mode contract failed.'
}
"""


def _powershell_executable() -> str:
    configured = os.environ.get(PWSH_ENV)
    executable = configured or shutil.which("pwsh")
    assert executable, "PowerShell 7 is required for this launcher contract test."
    return executable


def _run_powershell(
    command: list[str], environment: dict[str, str]
) -> tuple[int, str, str]:
    async def run() -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode is None:
            raise AssertionError("PowerShell process did not report an exit code.")
        return (
            process.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    return asyncio.run(run())


def test_nonlive_environment_files_are_private_before_writing(tmp_path: Path) -> None:
    source = Path(
        os.environ.get(
            SOURCE_ENV,
            Path(__file__).resolve().parents[1] / "start-docker.ps1",
        )
    ).resolve(strict=True)
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    if os.name != "nt":
        state_root.chmod(0o700)
    cache_root = tmp_path / "cache"
    cache_root.mkdir(mode=0o700)
    if os.name != "nt":
        cache_root.chmod(0o700)

    harness = tmp_path / "aud253-harness.ps1"
    harness.write_text(POWERSHELL_HARNESS, encoding="utf-8")
    command = [
        _powershell_executable(),
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(harness),
        "-SourcePath",
        str(source),
        "-TestRoot",
        str(state_root.resolve()),
    ]
    previous_umask = None
    if os.name != "nt":
        previous_umask = os.umask(0)
    try:
        environment = os.environ.copy()
        environment["XDG_CACHE_HOME"] = str(cache_root)
        if os.name != "nt":
            environment["TMPDIR"] = str(state_root)
        returncode, stdout, stderr = _run_powershell(command, environment)
        output = stdout + stderr
        assert returncode == 0, f"PowerShell launcher contract failed:\n{output}"
        assert "AUD253_RESULT=" in stdout, (
            "PowerShell harness returned no contract result."
        )
        if os.name != "nt":
            assert "setLengthFailureObserved:True" in stdout
            assert "setLengthFailureDisposed:True" in stdout
            assert "setLengthFailureMode:0600" in stdout
            assert "dualFailureMessagesPreserved:True" in stdout
            assert "dualFailureStreamClosed:True" in stdout
        else:
            assert "windowsNonLiveAclUnchanged,liveAclHelperPreserved" in stdout
        assert "AUD253_SYNTHETIC=" not in output, (
            "Harness must not print env-file fixture contents."
        )
    finally:
        if previous_umask is not None:
            os.umask(previous_umask)
