[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$InputPaths,

    [Parameter(Mandatory = $true)]
    [string]$OutputArchive,

    [ValidateSet("7z", "zip")]
    [string]$Format = "7z",

    [ValidateRange(0, 9)]
    [int]$Level = 5,

    [switch]$Solid,
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

$resolvedInputs = @()
foreach ($p in $InputPaths) {
    $item = Resolve-Path -Path $p -ErrorAction Stop
    $resolvedInputs += $item.Path
}

$outParent = Split-Path -Path $OutputArchive -Parent
if ($outParent -and -not (Test-Path $outParent)) {
    New-Item -Path $outParent -ItemType Directory | Out-Null
}

$args = @(
    "a",
    "-t$Format",
    $OutputArchive,
    "-mx=$Level",
    "-y"
)

if ($Solid -and $Format -eq "7z") {
    $args += "-ms=on"
}

if ($Password) {
    $args += "-p$Password"
    if ($Format -eq "7z") {
        # Encrypt file names for 7z archives when password is provided.
        $args += "-mhe=on"
    }
}

$args += $resolvedInputs

& $sevenZip @args
if ($LASTEXITCODE -ne 0) {
    throw "7-Zip compression failed with exit code $LASTEXITCODE"
}

Write-Output "Created archive: $OutputArchive"
