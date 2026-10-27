<#
.SYNOPSIS
  Offline Step-16 validation. No database, no live LLM, no CV access. Exits 1 if ANY check fails.
  Run from anywhere:  powershell -ExecutionPolicy Bypass -File .\backend\scripts\offline_validate.ps1
  -StrictScope : also fail if protected production paths differ from HEAD (default: report only)
  -Artifact    : optionally validate an existing artifact JSON with the contract checker
  Every check prints its ACTUAL exit code (success and failure).
#>
[CmdletBinding()]
param([switch]$StrictScope, [string]$Artifact)
$ErrorActionPreference = 'Stop'
$backend = Split-Path -Parent $PSScriptRoot
Set-Location $backend
$py = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$script:failures = @()

function Invoke-Check {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Action
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        $script:failures += "$Name (exit $code)"
        Write-Host "FAILED (exit=$code): $Name" -ForegroundColor Red
    } else {
        Write-Host "OK (exit=$code): $Name" -ForegroundColor Green
    }
}

$repo = $null
try { $repo = (& git -C $backend rev-parse --show-toplevel).Trim() } catch { }
if (-not $repo) { $script:failures += 'git repository not found' }

Invoke-Check 'compile all python (app, scripts, tests)' { & $py -m compileall -q app scripts tests }

Invoke-Check 'focused inspection/scoring/contract tests (DB+LLM blocked)' {
    & $py scripts\offline_guard_pytest.py tests\test_inspection_core.py tests\test_inspection_serialization.py `
        tests\test_inspection_integration.py tests\test_artifact_contract.py tests\test_career_fit_edge_cases.py `
        tests\test_career_fit_independent_verification.py tests\test_manual_validation_workflow.py
}

Invoke-Check 'broad pytest (DB+LLM blocked; test_b1_evidence_matching deselected: it writes to the DB)' {
    & $py scripts\offline_guard_pytest.py tests --deselect tests/test_profile_agent_smoke.py::test_b1_evidence_matching
}

foreach ($m in 'tests.test_career_fit_service_unit','tests.test_skill_gap_service_unit','tests.test_skill_gap_agent_unit',
               'tests.test_learning_roadmap_agent_unit','tests.test_skill_normalizer_unit') {
    $module = $m
    Invoke-Check "standalone unit script $module (DB blocked)" { & $py scripts\offline_guard_pytest.py --module $module }
}

if ($repo) {
    Invoke-Check 'git diff --check (unstaged)' { & git -C $repo diff --check }
    Invoke-Check 'git diff --check (staged)'   { & git -C $repo diff --cached --check }

    Invoke-Check '.env / upload / artifacts are git-ignored and untracked' {
        $bad = @()
        foreach ($p in 'backend/.env','upload/cv.pdf','backend/artifacts/manual_validation/x.json') {
            & git -C $repo check-ignore -q -- $p
            if ($LASTEXITCODE -ne 0) { $bad += "not ignored: $p" }
        }
        $tracked = @(& git -C $repo ls-files -- backend/.env upload backend/artifacts)
        if ($tracked.Count -gt 0) { $bad += "tracked: $($tracked -join ', ')" }
        $bad | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        $global:LASTEXITCODE = [int]($bad.Count -gt 0)
    }

    Invoke-Check 'scope report: protected production paths changed vs HEAD' {
        $protected = 'backend/app/services/career_fit_service.py','backend/app/services/skill_gap_service.py',
                     'backend/app/services/retrieval_service.py','backend/app/agents/','backend/app/workflows/',
                     'backend/app/schemas/','backend/app/repositories/','backend/config/scoring_weights.yaml'
        $changed = @(& git -C $repo diff --name-only HEAD) + @(& git -C $repo ls-files --others --exclude-standard)
        $hits = @($changed | Where-Object { $f = $_; $protected | Where-Object { $f.StartsWith($_) } })
        if ($hits.Count -gt 0) { Write-Host "REVIEW (protected paths differ from HEAD):" -ForegroundColor Yellow; $hits | ForEach-Object { "  $_" } }
        else { Write-Host 'no protected path differs from HEAD' }
        $global:LASTEXITCODE = [int]($StrictScope -and $hits.Count -gt 0)
    }
}

if ($Artifact) {
    Invoke-Check "artifact contract: $Artifact" { & $py scripts\check_artifact.py $Artifact }
}

Write-Host ''
if ($script:failures.Count -gt 0) {
    Write-Host 'OFFLINE VALIDATION FAILED:' -ForegroundColor Red
    $script:failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
Write-Host 'ALL OFFLINE CHECKS PASSED (no DB, no live LLM, no CV access)' -ForegroundColor Green
exit 0