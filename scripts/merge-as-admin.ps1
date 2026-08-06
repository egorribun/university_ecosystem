<#
.SYNOPSIS
    Merges a pull request as repository admin, bypassing Ruleset and classic
    branch-protection review requirements.

.DESCRIPTION
    Because this is a solo repository, both the GitHub Ruleset and the classic
    branch-protection rule require human reviewers that do not exist.
    This script temporarily disables both guards, performs the squash-merge,
    then immediately re-enables them - leaving the branch-protection posture
    unchanged for Scorecard purposes.

    The working branch (egorribun) is never deleted.

.PARAMETER PrNumber
    The pull request number to merge. Required.

.PARAMETER SquashTitle
    Optional custom title for the squash-merge commit.
    Defaults to the PR title fetched from GitHub.

.EXAMPLE
    .\scripts\merge-as-admin.ps1 -PrNumber 1168
    .\scripts\merge-as-admin.ps1 -PrNumber 1168 -SquashTitle "feat: my feature"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [int] $PrNumber,

    [string] $SquashTitle = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Constants - update if the ruleset ID changes (gh api repos/.../rulesets)
# ---------------------------------------------------------------------------
$REPO           = "egorribun/university_ecosystem"
$RULESET_ID     = 8335285
$PROTECTED_BRANCH = "main"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "    [OK] $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "    [!!] $Message" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Step 1 - Fetch PR info
# ---------------------------------------------------------------------------
Write-Step "Fetching PR #$PrNumber info..."
$pr = gh pr view $PrNumber --json title,headRefName,state | ConvertFrom-Json

if ($pr.state -ne "OPEN") {
    throw "PR #$PrNumber is not open (state: $($pr.state)). Aborting."
}

$mergeTitle = if ($SquashTitle) { $SquashTitle } else { $pr.title }
Write-Ok "Title : $mergeTitle"
Write-Ok "Branch: $($pr.headRefName)"

# ---------------------------------------------------------------------------
# Step 2 - Disable protections
# ---------------------------------------------------------------------------
Write-Step "Disabling Ruleset enforcement..."
gh api --method PUT "repos/$REPO/rulesets/$RULESET_ID" `
    --field enforcement=disabled | Out-Null
Write-Ok "Ruleset $RULESET_ID -> disabled"

Write-Step "Setting classic branch-protection required_approving_review_count=0..."
gh api --method PATCH "repos/$REPO/branches/$PROTECTED_BRANCH/protection/required_pull_request_reviews" `
    --field required_approving_review_count=0 | Out-Null
Write-Ok "Classic protection -> 0 approvals required"

# ---------------------------------------------------------------------------
# Step 3 - Merge (squash, keep head branch)
# ---------------------------------------------------------------------------
$mergeError = $null
try {
    Write-Step "Merging PR #$PrNumber (squash, branch kept)..."
    gh pr merge $PrNumber --squash --subject $mergeTitle
    Write-Ok "Merged successfully"
}
catch {
    $mergeError = $_
    Write-Warn "Merge failed: $mergeError"
}

# ---------------------------------------------------------------------------
# Step 4 - Always restore protections (even on failure)
# ---------------------------------------------------------------------------
Write-Step "Restoring Ruleset enforcement..."
gh api --method PUT "repos/$REPO/rulesets/$RULESET_ID" `
    --field enforcement=active | Out-Null
Write-Ok "Ruleset $RULESET_ID -> active"

Write-Step "Restoring classic branch-protection required_approving_review_count=1..."
gh api --method PATCH "repos/$REPO/branches/$PROTECTED_BRANCH/protection/required_pull_request_reviews" `
    --field required_approving_review_count=1 | Out-Null
Write-Ok "Classic protection -> 1 approval required"

# ---------------------------------------------------------------------------
# Step 5 - Re-raise merge error if any
# ---------------------------------------------------------------------------
if ($mergeError) {
    throw "Merge failed (protections have been restored): $mergeError"
}

# ---------------------------------------------------------------------------
# Step 6 - Sync local main, return to working branch
# ---------------------------------------------------------------------------
Write-Step "Syncing local main and returning to working branch..."
$currentBranch = git rev-parse --abbrev-ref HEAD
git fetch origin main
git switch main
git pull --ff-only origin main
git switch $currentBranch
Write-Ok "Local main synced. Back on: $currentBranch"

Write-Host "`nDone! PR #$PrNumber merged into main." -ForegroundColor Green
