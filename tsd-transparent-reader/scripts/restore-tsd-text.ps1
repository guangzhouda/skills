param(
    [Parameter(Mandatory = $true)]
    [string[]]$Paths,

    [string]$BackupFolderName = '加密',

    [switch]$Force,

    [int]$TimeoutSeconds = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$readerScript = Join-Path $scriptRoot 'read-tsd-hidden.ps1'
$tsdHeader = [Text.Encoding]::ASCII.GetBytes('%TSD-Header-###%')
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Test-TsdHeader {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $stream = [IO.File]::Open($TargetPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        if ($stream.Length -lt $tsdHeader.Length) {
            return $false
        }

        $buffer = New-Object byte[] $tsdHeader.Length
        [void]$stream.Read($buffer, 0, $buffer.Length)

        for ($i = 0; $i -lt $tsdHeader.Length; $i++) {
            if ($buffer[$i] -ne $tsdHeader[$i]) {
                return $false
            }
        }

        return $true
    }
    finally {
        $stream.Dispose()
    }
}

function Read-TsdPlainText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSec
    )

    # 不要通过子进程 stdout 直接接多行文本；PowerShell 会把多行拆成字符串数组，
    # 后续 WriteAllText 时会被空格拼接，导致整份源码塌成单行。
    if ([Threading.Thread]::CurrentThread.GetApartmentState() -eq [Threading.ApartmentState]::STA) {
        return (& $readerScript -Path $TargetPath -TimeoutSeconds $TimeoutSec)
    }

    $tempPath = [IO.Path]::GetTempFileName()
    try {
        powershell -STA -ExecutionPolicy Bypass -File $readerScript `
            -Path $TargetPath `
            -TimeoutSeconds $TimeoutSec `
            -OutputPath $tempPath | Out-Null

        return [IO.File]::ReadAllText($tempPath)
    }
    finally {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force
        }
    }
}

foreach ($rawPath in $Paths) {
    $resolvedPath = (Resolve-Path -LiteralPath $rawPath).Path

    if (-not $Force -and -not (Test-TsdHeader -TargetPath $resolvedPath)) {
        Write-Output "SKIP`t$resolvedPath`t非 TSD 头文件"
        continue
    }

    # 先读明文，再移动原文件，避免读路径失效。
    $plainText = Read-TsdPlainText -TargetPath $resolvedPath -TimeoutSec $TimeoutSeconds
    if ($null -eq $plainText) {
        throw "读取明文失败: $resolvedPath"
    }

    $parent = Split-Path -Parent $resolvedPath
    $backupDir = Join-Path $parent $BackupFolderName
    if (-not (Test-Path -LiteralPath $backupDir)) {
        [void](New-Item -ItemType Directory -Path $backupDir)
    }

    $name = Split-Path -Leaf $resolvedPath
    $backupPath = Join-Path $backupDir $name

    if (Test-Path -LiteralPath $backupPath) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backupPath = Join-Path $backupDir ("{0}.{1}.bak" -f $name, $stamp)
    }

    Move-Item -LiteralPath $resolvedPath -Destination $backupPath
    [IO.File]::WriteAllText($resolvedPath, $plainText, $utf8NoBom)

    Write-Output "OK`t$resolvedPath`t$backupPath"
}
