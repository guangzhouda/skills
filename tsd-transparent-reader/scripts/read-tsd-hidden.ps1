param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Path,

    [string]$OutputPath,

    [int]$TimeoutSeconds = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tsdHeaderText = '%TSD-Header-###%'
$fallbackExtension = '.c'

if (-not (Test-Path -LiteralPath $Path)) {
    throw "文件不存在: $Path"
}

# 使用记事本受信路径读取透明解密后的正文，并在读取后立即关闭记事本。
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace Win32 {
  public static class User32 {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr childAfter, string className, string windowName);

    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, StringBuilder lParam);

    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
  }
}
"@

function Invoke-NotepadRead {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSec
    )

    $proc = Start-Process -FilePath 'notepad.exe' -ArgumentList $TargetPath -WindowStyle Minimized -PassThru

    try {
        $deadline = (Get-Date).AddSeconds($TimeoutSec)
        do {
            Start-Sleep -Milliseconds 200
            $proc.Refresh()
        } until ($proc.MainWindowHandle -ne 0 -or (Get-Date) -gt $deadline)

        if ($proc.MainWindowHandle -eq 0) {
            throw '未找到记事本窗口句柄'
        }

        [Win32.User32]::ShowWindowAsync($proc.MainWindowHandle, 6) | Out-Null
        Start-Sleep -Milliseconds 200

        $editHandle = [Win32.User32]::FindWindowEx([IntPtr]$proc.MainWindowHandle, [IntPtr]::Zero, 'Edit', $null)
        if ($editHandle -eq [IntPtr]::Zero) {
            throw '未找到记事本编辑控件'
        }

        $wmGetTextLength = 0x000E
        $wmGetText = 0x000D
        $length = [int][Win32.User32]::SendMessage($editHandle, $wmGetTextLength, [IntPtr]::Zero, [IntPtr]::Zero)

        $builder = New-Object System.Text.StringBuilder ($length + 1)
        [void][Win32.User32]::SendMessage($editHandle, $wmGetText, [IntPtr]($length + 1), $builder)
        return $builder.ToString()
    }
    finally {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force
        }
    }
}

function Test-TsdCipherText {
    param(
        [AllowNull()]
        [string]$Content
    )

    if ($null -eq $Content) {
        return $false
    }

    return $Content.StartsWith($tsdHeaderText, [System.StringComparison]::Ordinal)
}

function Read-TsdContent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSec
    )

    $directContent = Invoke-NotepadRead -TargetPath $TargetPath -TimeoutSec $TimeoutSec
    if (-not (Test-TsdCipherText -Content $directContent)) {
        return $directContent
    }

    $tempDir = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
    $baseName = [IO.Path]::GetFileNameWithoutExtension($TargetPath)
    if ([string]::IsNullOrWhiteSpace($baseName)) {
        $baseName = 'tsd-fallback'
    }

    $fallbackPath = Join-Path $tempDir ($baseName + $fallbackExtension)

    try {
        [void](New-Item -ItemType Directory -Path $tempDir -Force)
        Copy-Item -LiteralPath $TargetPath -Destination $fallbackPath -Force

        $fallbackContent = Invoke-NotepadRead -TargetPath $fallbackPath -TimeoutSec $TimeoutSec
        if (Test-TsdCipherText -Content $fallbackContent) {
            throw "记事本读取仍返回 TSD 密文，已尝试原始扩展名和 $fallbackExtension 回退: $TargetPath"
        }

        return $fallbackContent
    }
    finally {
        if (Test-Path -LiteralPath $tempDir) {
            Remove-Item -LiteralPath $tempDir -Recurse -Force
        }
    }
}

$plainText = Read-TsdContent -TargetPath (Resolve-Path -LiteralPath $Path).Path -TimeoutSec $TimeoutSeconds

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $plainText
    return
}

$outputParent = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($outputParent) -and -not (Test-Path -LiteralPath $outputParent)) {
    [void](New-Item -ItemType Directory -Path $outputParent -Force)
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($OutputPath, $plainText, $utf8NoBom)
