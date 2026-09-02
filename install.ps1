<#
.SYNOPSIS
    Install / verify the Code Archaeologist (code-wiki) agent skill.

.DESCRIPTION
    The skill has zero external dependencies (Python 3.10+ standard library only),
    so "install" means:
      1. Verify a compatible Python is available.
      2. Optionally copy the skill into another project's .agents/skills/ folder.
      3. Optionally run a self-test that builds the bundled sample_src demo.

.PARAMETER Target
    Path to a project to install the skill into. The skill is copied to
    <Target>\<harness>\code-wiki with a fresh (empty) data/ folder.
    If omitted, the skill is only verified in place.

.PARAMETER Harness
    Target harness: agents (default), claude, cursor, windsurf, or zed.
    Selects where the skill folder lives relative to the project.

.PARAMETER Dir
    Custom install subpath (overrides -Harness), e.g. .myagent\skills\code-wiki.

.PARAMETER SelfTest
    Run the end-to-end pipeline against the bundled sample_src/ as a smoke test.

.EXAMPLE
    .\install.ps1 -SelfTest
    .\install.ps1 -Target C:\work\my-service -Harness claude
    .\install.ps1 -Target C:\work\my-service -Dir .myagent\skills\code-wiki
#>
param(
    [string]$Target,
    [ValidateSet("agents", "claude", "cursor", "windsurf", "zed")]
    [string]$Harness = "agents",
    [string]$Dir,
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$SkillSrc = Join-Path $RepoRoot ".agents\skills\code-wiki"

$HarnessDirs = @{
    agents   = ".agents\skills\code-wiki"
    claude   = ".claude\skills\code-wiki"
    cursor   = ".cursor\skills\code-wiki"
    windsurf = ".windsurf\skills\code-wiki"
    zed      = ".zed\skills\code-wiki"
}
if ($Dir) { $SkillSubdir = $Dir } else { $SkillSubdir = $HarnessDirs[$Harness] }
$SkillSubdirPosix = $SkillSubdir.Replace("\", "/")

function Find-Python {
    foreach ($candidate in @("python", "python3", "py")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            $ver = & $candidate -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) {
                $parts = $ver.Split(".")
                if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) {
                    return @{ Exe = $candidate; Version = $ver }
                }
            }
        }
    }
    return $null
}

Write-Host "Code Archaeologist -- skill installer" -ForegroundColor Cyan

$py = Find-Python
if (-not $py) {
    Write-Host "ERROR: Python 3.10+ not found on PATH. Install it from https://python.org and retry." -ForegroundColor Red
    exit 1
}
Write-Host ("OK   Python {0} found ({1})" -f $py.Version, $py.Exe) -ForegroundColor Green

if ($Target) {
    $dest = Join-Path $Target $SkillSubdir
    Write-Host ("Installing skill into {0} ..." -f $dest)
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $SkillSrc "scripts")   $dest -Recurse -Force
    Copy-Item (Join-Path $SkillSrc "templates") $dest -Recurse -Force
    Copy-Item (Join-Path $SkillSrc "SKILL.md")  $dest -Force
    # Fresh, empty data workspace (do not carry the demo vault over).
    $data = Join-Path $dest "data"
    New-Item -ItemType Directory -Force -Path (Join-Path $data "vault") | Out-Null
    '{ "nodes": [], "edges": [] }' | Out-File -Encoding utf8 (Join-Path $data "graph.json")
    '{}' | Out-File -Encoding utf8 (Join-Path $data "registry.json")
    New-Item -ItemType File -Force -Path (Join-Path $data "vault\.gitkeep") | Out-Null
    Write-Host "OK   Skill installed." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps (from $Target):"
    Write-Host "  $($py.Exe) $SkillSubdirPosix/scripts/build_wiki.py --src ./src"
    Write-Host "  $($py.Exe) $SkillSubdirPosix/scripts/build_graph.py"
    Write-Host "  $($py.Exe) $SkillSubdirPosix/scripts/build_html.py"
}

if ($SelfTest) {
    Write-Host ""
    Write-Host "Running self-test on bundled sample_src/ ..." -ForegroundColor Cyan
    Push-Location $RepoRoot
    try {
        & $py.Exe ".agents/skills/code-wiki/scripts/build_wiki.py" --src ./sample_src
        & $py.Exe ".agents/skills/code-wiki/scripts/build_graph.py"
        & $py.Exe ".agents/skills/code-wiki/scripts/build_html.py"
        Write-Host "OK   Self-test complete. Open .agents/skills/code-wiki/data/graph.html" -ForegroundColor Green
    } finally {
        Pop-Location
    }
}

if (-not $Target -and -not $SelfTest) {
    Write-Host ""
    Write-Host "Skill is ready to use in place. Try:  .\install.ps1 -SelfTest"
    Write-Host "Install into a project + harness:     .\install.ps1 -Target <path> -Harness claude"
}
