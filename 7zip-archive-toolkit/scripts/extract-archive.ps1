[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Archive,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [switch]$Flat,
    [switch]$OverwriteAll,
    [string]$Password
)

$ErrorActionPreference = "Stop"

function Resolve-SevenZip {
    $cmd = Get-Command 7z -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $defaultPath = "C:\Program Files\7-Zip\7z.exe"
    if (Test-Path $defaultPath) { return $defaultPath }

    throw "7z.exe not found. Install 7-Zip or add it to PATH."
}

$sevenZip = Resolve-SevenZip

$archivePath = Resolve-Path -Path $Archive -ErrorAction Stop
if (-not (Test-Path $OutputDir)) {
    New-Item -Path $OutputDir -ItemType Directory | Out-Null
}

$mode = if ($Flat) { "e" } else { "x" }
$args = @(
    $mode,
    $archivePath.Path,
    "-o$OutputDir"
)

if ($OverwriteAll) {
    $args += "-y"
} else {
    # Skip existing files by default to avoid accidental overwrite.
    $args += "-aos"
}

if ($Password) {
    $args += "-p$Password"
}

& $sevenZip @args
if ($LASTEXITCODE -ne 0) {
    throw "7-Zip extraction failed with exit code $LASTEXITCODE"
}

Write-Output "Extracted to: $OutputDir"
